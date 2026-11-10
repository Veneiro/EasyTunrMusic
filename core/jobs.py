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

from . import audio, ytdlp
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


def spotify_items(matches, music_folder, playlist_name):
    """Elementos para canciones de un CSV de Spotify, con el nombre 'Título - Artista'."""
    folder = subfolder(music_folder, playlist_name, "Spotify CSV")
    return [
        DownloadItem(m.url, f"{m.track.title} - {m.track.artist}".strip(" -"),
                     os.path.join(folder, f"{clean_folder_name(m.filename)}.%(ext)s"))
        for m in matches
    ]


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

            path = ytdlp.download(item.url, item.outtmpl or self.default_outtmpl,
                                  self.settings, self.group, on_download)
            if extract and path:
                audio.postprocess(path, self.settings, self.group,
                                  lambda stage, pct: cb.on_progress(pct, stage, label))
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
