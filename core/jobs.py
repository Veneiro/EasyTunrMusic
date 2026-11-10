"""Cola de descargas con hilos, pausa y cancelación. Sin dependencias de la UI.

Los callbacks se llaman desde hilos secundarios: la interfaz es responsable de
pasarlos a su propio hilo (en tkinter, con root.after).
"""
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

from . import audio, library, lyrics, net, spotify_link, tagging, ytdlp
from .process import ProcessGroup, Cancelled
from .settings import DownloadSettings
from .utils import clean_folder_name

logger = logging.getLogger(__name__)

TITLE_TEMPLATE = "%(title)s.%(ext)s"

# Reparto de la barra de progreso de cada canción cuando hay posprocesado.
DOWNLOAD_SHARE = 0.8


@dataclass
class DownloadItem:
    url: str
    label: str = ""
    outtmpl: Optional[str] = None
    title_hint: str = ""  # título esperado del vídeo, para detectar nombres repetidos
    alternatives: List[str] = field(default_factory=list)  # otros vídeos si este falla
    track: Optional[object] = None  # spotify.Track: sus datos se escriben en el archivo
    result_path: Optional[str] = None  # archivo final, cuando termina bien


def subfolder(music_folder, name, fallback):
    folder = os.path.join(music_folder, clean_folder_name(name or fallback))
    os.makedirs(folder, exist_ok=True)
    return folder


def playlist_items(url, music_folder):
    """Resuelve una lista de YouTube en elementos que se guardan en su propia carpeta."""
    title, videos = ytdlp.resolve_playlist(url)
    if not videos:
        return title, []
    folder = subfolder(music_folder, title, "Playlist")
    template = os.path.join(folder, TITLE_TEMPLATE)
    return title, [DownloadItem(u, t, template, title_hint=t) for u, t in videos]


def spotify_folder(music_folder, playlist_name):
    return os.path.join(music_folder, clean_folder_name(playlist_name or "Spotify"))


def spotify_items(matches, music_folder, playlist_name):
    """Elementos para canciones de Spotify, con el nombre 'Título - Artista'."""
    folder = subfolder(music_folder, playlist_name, "Spotify")
    return [
        DownloadItem(m.url, f"{m.track.title} - {m.track.artist}".strip(" -"),
                     os.path.join(folder, f"{clean_folder_name(m.filename)}.%(ext)s"),
                     alternatives=[c.url for c in m.alternatives if c.url],
                     track=m.track)
        for m in matches
    ]


def write_spotify_playlist(music_folder, playlist_name, tracks):
    """Crea '<lista>.m3u8' con las canciones de la lista que hay en la carpeta, en su orden."""
    from .spotify import existing_files, track_basename
    folder = spotify_folder(music_folder, playlist_name)
    existing = existing_files(folder)
    files = [existing[track_basename(t).lower()] for t in tracks if track_basename(t).lower() in existing]
    if files:
        return library.write_m3u(os.path.join(folder, f"{clean_folder_name(playlist_name)}.m3u8"), files)
    return None


def write_items_playlist(items, name):
    """Crea una lista .m3u8 con lo descargado, en la carpeta de la primera canción."""
    files = [i.result_path for i in items if i.result_path and os.path.exists(i.result_path)]
    if files:
        folder = os.path.dirname(files[0])
        return library.write_m3u(os.path.join(folder, f"{clean_folder_name(name)}.m3u8"), files)
    return None


@dataclass
class JobCallbacks:
    # (porcentaje 0-100, etapa, etiqueta de la canción). Etapas: downloading,
    # postprocessing, analyzing, normalizing, filtering, finalizing, done.
    on_progress: Callable[[float, str, str], None] = lambda *_: None
    # (completadas, total)
    on_item_done: Callable[[int, int], None] = lambda *_: None
    # (fallos [(id, error)], cancelado)
    on_finished: Callable[[List[Tuple[str, str]], bool], None] = lambda *_: None


@dataclass
class DownloadJob:
    items: List[DownloadItem]
    settings: DownloadSettings
    default_outtmpl: str
    workers: int = 4
    callbacks: JobCallbacks = field(default_factory=JobCallbacks)
    # Se llama en el hilo de trabajo al terminar (si no se canceló), con todos los elementos
    after: Optional[Callable[[List[DownloadItem]], None]] = None

    def __post_init__(self):
        self._dedupe_names()
        self.group = ProcessGroup()
        self.failed: List[Tuple[str, str]] = []
        self.completed = 0
        self._lock = threading.Lock()
        self._resume = threading.Event()
        self._resume.set()

    def _dedupe_names(self):
        """Canciones con el mismo título en la misma carpeta se escribirían en el
        mismo archivo a la vez: a partir de la segunda se añade " (2)", " (3)"...
        Solo se puede saber de antemano por la etiqueta; yt-dlp pone el título real."""
        seen = {}
        for item in self.items:
            template = item.outtmpl or self.default_outtmpl
            name = (item.title_hint or item.label).strip().lower()
            if not template.endswith(TITLE_TEMPLATE) or not name:
                continue
            key = (os.path.dirname(template).lower(), name)
            seen[key] = seen.get(key, 0) + 1
            if seen[key] > 1:
                item.outtmpl = os.path.join(os.path.dirname(template), f"%(title)s ({seen[key]}).%(ext)s")

    # -------------------------------------------------------------- control
    @property
    def total(self):
        return len(self.items)

    @property
    def is_paused(self):
        return not self._resume.is_set()

    @property
    def is_cancelled(self):
        return self.group.cancelled.is_set()

    def pause(self):
        """Las canciones en curso terminan; las siguientes esperan."""
        self._resume.clear()

    def resume(self):
        self._resume.set()

    def cancel(self):
        self.group.cancel()
        self._resume.set()

    def start(self):
        thread = threading.Thread(target=self._run, name="download-job", daemon=True)
        thread.start()
        return thread

    # -------------------------------------------------------------- trabajo
    def _run(self):
        workers = max(1, min(int(self.workers or 1), 16))
        try:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                list(pool.map(self._process, self.items))
            if self.after and not self.is_cancelled:
                try:
                    self.after(self.items)
                except Exception:
                    logger.exception("Fallo al terminar el lote de descargas")
        finally:
            self.callbacks.on_finished(list(self.failed), self.is_cancelled)

    def _wait_if_paused(self):
        while not self._resume.wait(timeout=0.2):
            pass
        if self.is_cancelled:
            raise Cancelled()

    def _process(self, item: DownloadItem):
        cb = self.callbacks
        label = item.label
        try:
            self._wait_if_paused()
            extract = self.settings.extract_audio
            share = DOWNLOAD_SHARE if extract else 1.0

            def on_download(status, percent):
                if status == "downloading" and percent is not None:
                    cb.on_progress(percent * share, "downloading", label)
                elif status == "finished":
                    cb.on_progress(share * 100, "postprocessing" if extract else "done", label)

            path = self._download_with_fallback(item, on_download)
            if extract and path:
                audio.postprocess(path, self.settings, self.group,
                                  lambda stage, pct: cb.on_progress(pct, stage, label))
            if path and os.path.exists(path):
                self._finish_file(item, path)
                item.result_path = path
        except Cancelled:
            return
        except Exception as exc:
            if self.is_cancelled:
                return
            video_id = item.url.split("v=")[-1] if "v=" in item.url else item.url
            logger.exception("Fallo al descargar %s", item.url)
            with self._lock:
                self.failed.append((label or video_id, str(exc).strip() or repr(exc)))
        finally:
            if not self.is_cancelled:
                with self._lock:
                    self.completed += 1
                    done = self.completed
                cb.on_item_done(done, self.total)

    def _download_with_fallback(self, item, on_download):
        """Si el vídeo no se puede descargar (bloqueado, borrado...), prueba los alternativos."""
        urls = [item.url] + [u for u in item.alternatives if u and u != item.url]
        for attempt, url in enumerate(urls):
            try:
                return ytdlp.download(url, item.outtmpl or self.default_outtmpl,
                                      self.settings, self.group, on_download)
            except ytdlp.YtDlpError as exc:
                if self.is_cancelled or attempt == len(urls) - 1:
                    raise
                logger.warning("No se pudo descargar %s (%s); se prueba otro vídeo", url, exc)
                self.callbacks.on_progress(0.0, "retrying", item.label)
        return None

    def _finish_file(self, item, path):
        """Etiquetas de Spotify, carátula y letra. Nunca hace fallar la descarga."""
        track = item.track
        want_tags = track is not None and self.settings.metadata
        if not (want_tags or self.settings.lyrics):
            return
        self.callbacks.on_progress(99.0, "tagging", item.label)
        synced = plain = None
        if self.settings.lyrics:
            try:
                # Duración real del archivo final (ya recortado por SponsorBlock y convertido):
                # la letra sincronizada solo se guarda si coincide con ella
                title, artist, file_duration = tagging.read_basic(path)
                if track is not None:
                    synced, plain = lyrics.fetch(track.title, track.artist, track.album, track.duration,
                                                 file_duration=file_duration or None)
                else:
                    title, artist = lyrics.guess_from_video_title(title, artist)
                    synced, plain = lyrics.fetch(title, artist, duration=file_duration or None,
                                                 file_duration=file_duration or None)
                if synced:
                    lyrics.write_lrc(path, synced)
            except Exception:
                logger.warning("No se pudo guardar la letra de %s", path, exc_info=True)
        if want_tags:
            cover = None
            if os.path.splitext(path)[1].lower() != ".webm":  # webm no admite etiquetas
                cover_url = track.cover_url or spotify_link.cover_url_for(track.spotify_id)
                if cover_url:
                    try:
                        cover = net.get(cover_url, timeout=20)
                    except Exception:
                        logger.info("No se pudo descargar la carátula %s", cover_url, exc_info=True)
            tagging.write_tags(path, track, cover, plain)
