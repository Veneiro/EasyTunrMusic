import os
import re
import logging
import json
import subprocess
import yt_dlp
from threading import Thread
from concurrent.futures import ThreadPoolExecutor
from translations import TRANSLATIONS
from utils import clean_folder_name

logger = logging.getLogger(__name__)

def get_loudnorm_targets(app):
    if app.normalization_var.get() == "custom":
        return (
            app.custom_lufs_i_var.get(),
            app.custom_lufs_tp_var.get(),
            app.custom_lufs_lra_var.get(),
        )
    if app.normalization_var.get() == "lufs_14":
        return ("-14", "-1.5", "11")
    return ("-23", "-2", "7")

def parse_loudnorm_json(output_text):
    start = output_text.rfind("{")
    end = output_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(output_text[start:end + 1])
    except json.JSONDecodeError:
        return None

def apply_audio_postprocess(app, input_path):
    if not os.path.exists(input_path):
        return

    codec = app.codec_var.get()
    effective_rate = get_effective_sample_rate(codec, app.sample_rate_var.get())
    needs_lossless_fmt = codec in ["flac", "wav", "alac"]

    base_args = [
        'ffmpeg', '-y', '-i', input_path,
        '-map_metadata', '0', '-vn',
    ]
    output_args = ['-c:a', codec if codec != 'alac' else 'alac']
    if codec in ["mp3", "aac", "opus"]:
        output_args.extend(['-b:a', f"{app.bitrate_var.get()}k"])
    if app.channels_var.get() == "mono":
        output_args.extend(['-ac', '1'])
    elif app.channels_var.get() == "multichannel":
        output_args.extend(['-ac', '6'])
    if effective_rate:
        output_args.extend(['-ar', effective_rate])
    if needs_lossless_fmt:
        output_args.extend(['-sample_fmt', f's{app.bit_depth_var.get()}'])

    filter_chain = []
    if app.dynamic_compression_var.get():
        filter_chain.append('acompressor=threshold=-21dB:ratio=9:attack=200:release=1000')

    base_root, base_ext = os.path.splitext(input_path)
    temp_path = base_root + '.tmp' + base_ext

    if app.normalization_var.get() != "off":
        target_i, target_tp, target_lra = get_loudnorm_targets(app)
        pass1_filters = list(filter_chain)
        pass1_filters.append(
            f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:print_format=json"
        )
        pass1_cmd = base_args + ['-af', ','.join(pass1_filters), '-f', 'null', '-']
        pass1 = subprocess.run(pass1_cmd, capture_output=True, text=True)
        analysis = parse_loudnorm_json(pass1.stderr or pass1.stdout or "")
        if not analysis:
            raise RuntimeError("Failed to analyze loudnorm output")

        measured_i = analysis.get('input_i')
        measured_lra = analysis.get('input_lra')
        measured_tp = analysis.get('input_tp')
        measured_thresh = analysis.get('input_thresh')
        offset = analysis.get('target_offset')

        pass2_filters = list(filter_chain)
        pass2_filters.append(
            "loudnorm="
            f"I={target_i}:TP={target_tp}:LRA={target_lra}:"
            f"measured_I={measured_i}:measured_LRA={measured_lra}:"
            f"measured_TP={measured_tp}:measured_thresh={measured_thresh}:"
            f"offset={offset}:linear=true:print_format=summary"
        )
        pass2_cmd = base_args + ['-af', ','.join(pass2_filters)] + output_args + [temp_path]
        subprocess.run(pass2_cmd, check=True, capture_output=True)
    else:
        if filter_chain:
            base_args += ['-af', ','.join(filter_chain)]
        cmd = base_args + output_args + [temp_path]
        subprocess.run(cmd, check=True, capture_output=True)

    os.replace(temp_path, input_path)

def get_effective_sample_rate(codec, sample_rate_str):
    try:
        target_rate = int(sample_rate_str)
    except (TypeError, ValueError):
        return sample_rate_str

    codec = (codec or "").lower()
    supported_map = {
        'mp3': [32000, 44100, 48000],
        'aac': [44100, 48000],
        'opus': [48000],
    }
    if codec in supported_map:
        supported = supported_map[codec]
        if target_rate in supported:
            return str(target_rate)
        closest = min(supported, key=lambda rate: abs(rate - target_rate))
        logger.warning("Sample rate %s not supported for %s, using %s", target_rate, codec, closest)
        return str(closest)

    return str(target_rate)

def download_video(app, video_url, output_template):
    if app.is_cancelled:
        return
    while app.is_paused:
        if app.is_cancelled:
            return
        import time
        time.sleep(0.1)
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': output_template,
            'progress_delta': 0.01,
            'quiet': True,
            'progress_hooks': [lambda d: video_progress_hook(app, d)],
        }
        if app.extract_audio_var.get():
            postprocessors = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': app.codec_var.get(),
            }]
            if app.codec_var.get() in ["mp3", "aac", "opus"]:
                postprocessors[0]['preferredquality'] = app.bitrate_var.get()
            if app.metadata_var.get():
                postprocessors.append({'key': 'FFmpegMetadata'})
                postprocessors.append({'key': 'EmbedThumbnail'})
                ydl_opts['writethumbnail'] = True
            if app.extract_thumbnail_var.get():
                ydl_opts['writethumbnail'] = True

            ydl_opts['postprocessors'] = postprocessors
        if app.keep_original_var.get():
            ydl_opts['keepvideo'] = True
        output_path = None
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            if info and app.extract_audio_var.get():
                base_path = ydl.prepare_filename(info)
                output_path = os.path.splitext(base_path)[0] + f".{app.codec_var.get()}"
        if output_path:
            apply_audio_postprocess(app, output_path)
    except Exception as e:
        video_id = video_url.split('v=')[-1] if 'v=' in video_url else 'Desconocido'
        error_text = str(e).strip() or repr(e)
        logger.exception("Download failed for video_id=%s", video_id)
        app.failed_videos.append((video_id, error_text))
    finally:
        app.download_queue.put(1)

def video_progress_hook(app, d):
    if app.is_cancelled:
        return
    if d['status'] == 'downloading':
        percent_str = d.get('_percent_str', '0%').strip('%').replace(' ', '')
        try:
            percent = float(percent_str)
            app.root.after(0, lambda: app.video_progress_var.set(percent))
            if app.total_videos > 1:
                app.root.after(0, lambda: app.global_progress_var.set((app.completed_videos + percent / 100) / app.total_videos * 100))
            else:
                app.root.after(0, lambda: app.global_progress_var.set(percent))
                def update_label():
                    if hasattr(app, 'progress_status_label') and app.progress_status_label.winfo_exists():
                        app.progress_status_label.config(
                            text=f"{TRANSLATIONS[app.language_var.get()]['progress_status'].split(':')[0]}: Descargando... {percent:.1f}%")
                app.root.after(0, update_label)
        except ValueError:
            pass
    elif d['status'] == 'finished':
        app.root.after(0, lambda: app.video_progress_var.set(100.0))
        if app.total_videos <= 1:
            app.root.after(0, lambda: app.global_progress_var.set(100.0))

def update_progress(app):
    while not app.download_queue.empty():
        app.download_queue.get()
        app.completed_videos += 1
        if app.total_videos > 0:
            progress = (app.completed_videos / app.total_videos) * 100
            app.root.after(0, lambda: app.global_progress_var.set(progress))
            def update_status():
                if hasattr(app, 'progress_status_label') and app.progress_status_label.winfo_exists():
                    app.progress_status_label.config(
                        text=f"{TRANSLATIONS[app.language_var.get()]['progress_status'].split(':')[0]}: Descargando {app.completed_videos} de {app.total_videos} videos..."
                    )
            app.root.after(0, update_status)
    if app.completed_videos < app.total_videos and not app.is_cancelled:
        app.root.after(100, lambda: update_progress(app))
    elif app.completed_videos == app.total_videos or app.is_cancelled:
        app.finalize_download()

def download(app, urls, is_playlist):
    try:
        video_urls = []
        app.is_playlist = is_playlist

        ydl_opts_info = {
            'quiet': True,
            'noplaylist': False,
            'extract_flat': True,
        }
        if is_playlist:
            for url in urls:
                with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
                    info = ydl.extract_info(url, download=False)
                    if 'entries' in info and len(info['entries']) > 0:
                        video_urls.extend([entry['url'] for entry in info['entries'] if entry.get('url')])
                    else:
                        app.finalize_download(error_message=TRANSLATIONS[app.language_var.get()]['error_not_playlist'])
                        return
        else:
            video_urls = urls

        if not video_urls:
            app.finalize_download(error_message=TRANSLATIONS[app.language_var.get()]['error_no_songs'])
            return

        app.total_videos = len(video_urls)
        app.create_progress_window(app.total_videos)

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(app.music_folder, '%(title)s.%(ext)s'),
            'progress_delta': 0.01,
            'ignoreerrors': True,
            'progress_hooks': [lambda d: video_progress_hook(app, d)],
        }
        if app.extract_audio_var.get():
            postprocessors = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': app.codec_var.get(),
            }]
            if app.codec_var.get() in ["mp3", "aac", "opus"]:
                postprocessors[0]['preferredquality'] = app.bitrate_var.get()
            if app.metadata_var.get():
                postprocessors.append({'key': 'FFmpegMetadata'})
                postprocessors.append({'key': 'EmbedThumbnail'})
                ydl_opts['writethumbnail'] = True
            if app.extract_thumbnail_var.get():
                ydl_opts['writethumbnail'] = True

            ydl_opts['postprocessors'] = postprocessors
        if app.keep_original_var.get():
            ydl_opts['keepvideo'] = True

        output_template = ydl_opts['outtmpl']
        if is_playlist:
            playlist_title = "Lista de reproducción"
            with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
                info = ydl.extract_info(urls[0], download=False)
                if 'title' in info:
                    playlist_title = info['title']
            playlist_folder = os.path.join(app.music_folder, clean_folder_name(playlist_title))
            if not os.path.exists(playlist_folder):
                os.makedirs(playlist_folder)
            output_template = os.path.join(playlist_folder, '%(title)s.%(ext)s')

        update_progress(app)
        max_workers = int(app.threads_var.get())
        app.executor = ThreadPoolExecutor(max_workers=max_workers)
        futures = [app.executor.submit(download_video, app, url, output_template) for url in video_urls]
        for future in futures:
            future.result()
        app.executor = None

    except Exception as e:
        app.finalize_download(error_message=f"{TRANSLATIONS[app.language_var.get()]['error_process_url'].format(str(e))}")

def download_search_songs(app):
    lang = app.language_var.get()
    if not app.search_song_urls:
        app.show_result_message('error', TRANSLATIONS[lang]['error_no_songs'])
        return

    app.failed_videos = []
    app.global_progress_var.set(0.0)
    app.video_progress_var.set(0.0)
    app.total_videos = 0
    app.completed_videos = 0
    app.is_paused = False
    app.is_cancelled = False
    app.is_playlist = False
    Thread(target=download, args=(app, app.search_song_urls, False)).start()

def download_search_playlist(app, listbox, window):
    lang = app.language_var.get()
    selection = listbox.curselection()
    if not selection:
        app.show_result_message('warning', TRANSLATIONS[lang]['error_select_playlist'])
        return
    index = selection[0]
    title, url, is_playlist = app.search_results[index]
    if not is_playlist:
        app.show_result_message('error', TRANSLATIONS[lang]['error_not_playlist'])
        return

    app.failed_videos = []
    app.global_progress_var.set(0.0)
    app.video_progress_var.set(0.0)
    app.total_videos = 0
    app.completed_videos = 0
    app.is_paused = False
    app.is_cancelled = False
    app.is_playlist = True
    Thread(target=download, args=(app, [url], True)).start()
    window.destroy()

def start_songs_download(app):
    lang = app.language_var.get()
    if not app.song_urls:
        app.show_result_message('error', TRANSLATIONS[lang]['error_no_songs'])
        return

    app.failed_videos = []
    app.global_progress_var.set(0.0)
    app.video_progress_var.set(0.0)
    app.total_videos = 0
    app.completed_videos = 0
    app.is_paused = False
    app.is_cancelled = False
    app.is_playlist = False
    app.songs_download_button.configure(state='disabled')
    app.songs_pause_button.configure(state='normal')
    app.songs_cancel_button.configure(state='normal')
    urls = [song[0] for song in app.song_urls]
    Thread(target=download, args=(app, urls, False)).start()

def start_playlist_download(app):
    lang = app.language_var.get()
    url = app.playlist_url_var.get().strip()
    if not url:
        app.show_result_message('error', TRANSLATIONS[lang]['error_no_playlist'])
        return
    if not re.match(r'https?://', url):
        app.show_result_message('error', TRANSLATIONS[lang]['error_invalid_url'])
        return

    app.failed_videos = []
    app.global_progress_var.set(0.0)
    app.video_progress_var.set(0.0)
    app.total_videos = 0
    app.completed_videos = 0
    app.is_paused = False
    app.is_cancelled = False
    app.is_playlist = True
    app.playlist_download_button.configure(state='disabled')
    app.playlist_pause_button.configure(state='normal')
    app.playlist_cancel_button.configure(state='normal')
    Thread(target=download, args=(app, [url], True)).start()