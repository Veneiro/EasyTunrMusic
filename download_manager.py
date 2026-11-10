"""Puente entre la interfaz tkinter y el núcleo de descargas (paquete `core`).

Aquí solo se leen las variables de la UI, se lanza un `DownloadJob` y se
devuelven sus avisos al hilo de tkinter. Toda la lógica de descarga y audio
vive en `core/`.
"""
import logging
import os
import re
from threading import Thread

from core import ytdlp
from core.jobs import DownloadItem, DownloadJob, JobCallbacks
from core.settings import DownloadSettings
from translations import TRANSLATIONS
from utils import clean_folder_name

logger = logging.getLogger(__name__)

STAGE_TEXT = {
    'es': {
        'downloading': 'Descargando... {:.1f}%',
        'postprocessing': 'Iniciando postprocesado...',
        'analyzing': 'Analizando audio...',
        'normalizing': 'Aplicando normalización...',
        'filtering': 'Aplicando filtros...',
        'finalizing': 'Finalizando archivo...',
        'done': 'Completado',
        'items': 'Descargando {} de {}...',
        'preparing': 'Preparando la descarga...',
    },
    'en': {
        'downloading': 'Downloading... {:.1f}%',
        'postprocessing': 'Starting postprocessing...',
        'analyzing': 'Analyzing audio...',
        'normalizing': 'Applying normalization...',
        'filtering': 'Applying filters...',
        'finalizing': 'Finalizing file...',
        'done': 'Done',
        'items': 'Downloading {} of {}...',
        'preparing': 'Preparing download...',
    },
}


def _t(app, key):
    return TRANSLATIONS[app.language_var.get()][key]


def _stage(app, key):
    return STAGE_TEXT.get(app.language_var.get(), STAGE_TEXT['en'])[key]


def _ui(app, fn):
    """Ejecuta fn en el hilo de tkinter (seguro desde cualquier hilo)."""
    app.post(fn)


def _fail(app, key, detail=None):
    """Cierra la descarga con un error; el texto se traduce ya en el hilo de tkinter."""
    def show():
        text = _t(app, key)
        app.finalize_download(error_message=text.format(detail) if detail is not None else text)
    _ui(app, show)


def _set_status(app, text):
    label = getattr(app, 'progress_status_label', None)
    if label is not None and label.winfo_exists():
        prefix = _t(app, 'progress_status').split(':')[0]
        label.config(text=f"{prefix}: {text}")


def build_settings(app):
    """Copia las opciones de la UI a un objeto inmutable (solo desde el hilo de tkinter)."""
    return DownloadSettings(
        codec=app.codec_var.get(),
        bitrate=app.bitrate_var.get(),
        bit_depth=app.bit_depth_var.get(),
        sample_rate=app.sample_rate_var.get(),
        channels=app.channels_var.get(),
        normalization=app.normalization_var.get(),
        custom_lufs_i=app.custom_lufs_i_var.get(),
        custom_lufs_tp=app.custom_lufs_tp_var.get(),
        custom_lufs_lra=app.custom_lufs_lra_var.get(),
        extract_audio=app.extract_audio_var.get(),
        metadata=app.metadata_var.get(),
        extract_thumbnail=app.extract_thumbnail_var.get(),
        keep_original=app.keep_original_var.get(),
        dynamic_compression=app.dynamic_compression_var.get(),
    )


def _to_item(entry, music_folder, spotify_playlist_name):
    """Convierte las distintas formas de entrada de la UI en un DownloadItem."""
    if isinstance(entry, dict):
        url = entry.get('url', '')
        label = f"{entry.get('title', '')} - {entry.get('artist', '')}".strip(' -')
        outtmpl = None
        if entry.get('source') == 'spotify_csv' and entry.get('filename'):
            folder = os.path.join(music_folder, clean_folder_name(spotify_playlist_name or 'Spotify CSV'))
            os.makedirs(folder, exist_ok=True)
            outtmpl = os.path.join(folder, f"{clean_folder_name(entry['filename'])}.%(ext)s")
        return DownloadItem(url, label, outtmpl) if url else None
    if isinstance(entry, (tuple, list)) and entry:
        label = " - ".join(str(part) for part in entry[1:3] if part)
        return DownloadItem(entry[0], label) if entry[0] else None
    return DownloadItem(entry) if entry else None


def _prepare(app, entries, is_playlist, settings, music_folder, workers, spotify_name):
    """Hilo secundario: resuelve listas y crea los elementos a descargar."""
    try:
        default_outtmpl = os.path.join(music_folder, '%(title)s.%(ext)s')
        if is_playlist:
            items = []
            for entry in entries:
                url = entry.get('url', '') if isinstance(entry, dict) else entry
                title, urls = ytdlp.resolve_playlist(url)
                if not urls:
                    _fail(app, 'error_not_playlist')
                    return
                folder = os.path.join(music_folder, clean_folder_name(title or "Lista de reproducción"))
                os.makedirs(folder, exist_ok=True)
                outtmpl = os.path.join(folder, '%(title)s.%(ext)s')
                items.extend(DownloadItem(u, '', outtmpl) for u in urls)
        else:
            items = [i for i in (_to_item(e, music_folder, spotify_name) for e in entries) if i]

        if not items:
            _fail(app, 'error_no_songs')
            return
        _ui(app, lambda: _launch(app, items, settings, default_outtmpl, workers))
    except Exception as exc:
        logger.exception("No se pudo preparar la descarga")
        _fail(app, 'error_process_url', str(exc))


def _launch(app, items, settings, default_outtmpl, workers):
    """Hilo de tkinter: abre la ventana de progreso y arranca el trabajo."""
    app.hide_spinner()
    app.total_videos = len(items)
    app.completed_videos = 0
    app.create_progress_window(len(items))

    def on_progress(percent, stage, label):
        def update():
            app.video_progress_var.set(percent)
            total = max(app.total_videos, 1)
            app.global_progress_var.set((app.completed_videos + percent / 100) / total * 100)
            text = _stage(app, stage)
            text = text.format(percent) if '{' in text else text
            _set_status(app, f"{label} | {text}" if label else text)
        _ui(app, update)

    def on_item_done(done, total):
        def update():
            app.completed_videos = done
            app.global_progress_var.set(done / max(total, 1) * 100)
            _set_status(app, _stage(app, 'items').format(done, total))
        _ui(app, update)

    def on_finished(failed, cancelled):
        def update():
            app.current_job = None
            if cancelled:
                return  # cancel_download ya cerró la descarga
            app.failed_videos = failed
            app.finalize_download()
        _ui(app, update)

    job = DownloadJob(items, settings, default_outtmpl, workers,
                      JobCallbacks(on_progress, on_item_done, on_finished))
    app.current_job = job
    job.start()


def start_download(app, entries, is_playlist):
    """Punto de entrada común para todas las pestañas."""
    if getattr(app, 'current_job', None) is not None:
        return
    app.failed_videos = []
    app.global_progress_var.set(0.0)
    app.video_progress_var.set(0.0)
    app.total_videos = 0
    app.completed_videos = 0
    app.is_paused = False
    app.is_cancelled = False
    app.is_playlist = is_playlist
    try:
        workers = int(app.threads_var.get())
    except (TypeError, ValueError):
        workers = 4
    app.show_spinner()
    Thread(
        target=_prepare,
        args=(app, list(entries), is_playlist, build_settings(app), app.music_folder,
              workers, getattr(app, 'spotify_playlist_name', '')),
        daemon=True,
    ).start()


# --- Funciones usadas por los botones de la UI -------------------------------

def download_search_songs(app):
    if not app.search_song_urls:
        app.show_result_message('error', _t(app, 'error_no_songs'))
        return
    start_download(app, app.search_song_urls, False)


def download_search_playlist(app, listbox, window):
    selection = listbox.curselection()
    if not selection:
        app.show_result_message('warning', _t(app, 'error_select_playlist'))
        return
    _title, url, is_playlist = app.search_results[selection[0]]
    if not is_playlist:
        app.show_result_message('error', _t(app, 'error_not_playlist'))
        return
    window.destroy()
    start_download(app, [url], True)


def start_songs_download(app):
    if not app.song_urls:
        app.show_result_message('error', _t(app, 'error_no_songs'))
        return
    app.songs_download_button.configure(state='disabled')
    app.songs_pause_button.configure(state='normal')
    app.songs_cancel_button.configure(state='normal')
    start_download(app, app.song_urls, False)


def start_playlist_download(app):
    url = app.playlist_url_var.get().strip()
    if not url:
        app.show_result_message('error', _t(app, 'error_no_playlist'))
        return
    if not re.match(r'https?://', url):
        app.show_result_message('error', _t(app, 'error_invalid_url'))
        return
    app.playlist_download_button.configure(state='disabled')
    app.playlist_pause_button.configure(state='normal')
    app.playlist_cancel_button.configure(state='normal')
    start_download(app, [url], True)


def start_spotify_download(app):
    if not app.spotify_song_urls:
        app.show_result_message('error', _t(app, 'error_no_songs'))
        return
    app.spotify_download_button.configure(state='disabled')
    app.spotify_pause_button.configure(state='normal')
    app.spotify_cancel_button.configure(state='normal')
    start_download(app, app.spotify_song_urls, False)
