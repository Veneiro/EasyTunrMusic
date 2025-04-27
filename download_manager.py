import os
import re
import yt_dlp
from threading import Thread
from concurrent.futures import ThreadPoolExecutor
from translations import TRANSLATIONS
from utils import clean_folder_name

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
            if app.normalization_var.get() != "off":
                if app.normalization_var.get() == "custom":
                    norm_args = ['-filter:a', f'loudnorm=I={app.custom_lufs_i_var.get()}:LRA={app.custom_lufs_lra_var.get()}:TP={app.custom_lufs_tp_var.get()}']
                else:
                    norm_args = ['-filter:a', 'loudnorm=I=-14:TP=-1.5:LRA=11'] if app.normalization_var.get() == "lufs_14" else \
                                ['-filter:a', 'loudnorm=I=-23:TP=-2:LRA=7']
                postprocessors.append({'key': 'FFmpegPostProcessor', 'args': norm_args})
            if app.dynamic_compression_var.get():
                postprocessors.append({'key': 'FFmpegPostProcessor', 'args': ['-filter:a', 'acompressor=threshold=-21dB:ratio=9:attack=200:release=1000']})
            if app.codec_var.get() in ["flac", "wav", "alac"]:
                postprocessors.append({
                    'key': 'FFmpegPostProcessor',
                    'args': [f'-sample_fmt', f's{app.bit_depth_var.get()}', f'-ar', app.sample_rate_var.get()]
                })
            if app.channels_var.get() == "mono":
                postprocessors.append({'key': 'FFmpegPostProcessor', 'args': ['-ac', '1']})
            elif app.channels_var.get() == "multichannel":
                postprocessors.append({'key': 'FFmpegPostProcessor', 'args': ['-ac', '6']})
            ydl_opts['postprocessors'] = postprocessors
        if app.keep_original_var.get():
            ydl_opts['keepvideo'] = True
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
    except Exception as e:
        video_id = video_url.split('v=')[-1] if 'v=' in video_url else 'Desconocido'
        app.failed_videos.append((video_id, str(e)))
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
                app.root.after(0, lambda: app.progress_status_label.config(
                    text=f"{TRANSLATIONS[app.language_var.get()]['progress_status'].split(':')[0]}: Descargando... {percent:.1f}%"))
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
            app.root.after(0, lambda: app.progress_status_label.config(
                text=f"{TRANSLATIONS[app.language_var.get()]['progress_status'].split(':')[0]}: Descargando {app.completed_videos} de {app.total_videos} videos..."
            ))
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
            if app.normalization_var.get() != "off":
                if app.normalization_var.get() == "custom":
                    norm_args = ['-filter:a', f'loudnorm=I={app.custom_lufs_i_var.get()}:LRA={app.custom_lufs_lra_var.get()}:TP={app.custom_lufs_tp_var.get()}']
                else:
                    norm_args = ['-filter:a', 'loudnorm=I=-14:TP=-1.5:LRA=11'] if app.normalization_var.get() == "lufs_14" else \
                                ['-filter:a', 'loudnorm=I=-23:TP=-2:LRA=7']
                postprocessors.append({'key': 'FFmpegPostProcessor', 'args': norm_args})
            if app.dynamic_compression_var.get():
                postprocessors.append({'key': 'FFmpegPostProcessor', 'args': ['-filter:a', 'acompressor=threshold=-21dB:ratio=9:attack=200:release=1000']})
            if app.codec_var.get() in ["flac", "wav", "alac"]:
                postprocessors.append({
                    'key': 'FFmpegPostProcessor',
                    'args': [f'-sample_fmt', f's{app.bit_depth_var.get()}', f'-ar', app.sample_rate_var.get()]
                })
            if app.channels_var.get() == "mono":
                postprocessors.append({'key': 'FFmpegPostProcessor', 'args': ['-ac', '1']})
            elif app.channels_var.get() == "multichannel":
                postprocessors.append({'key': 'FFmpegPostProcessor', 'args': ['-ac', '6']})
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