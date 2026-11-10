"""Biblioteca de música: lee la carpeta de descargas y prepara archivos para reproducir.

- scan() recorre la carpeta (y subcarpetas) y lee título, artista, álbum,
  duración y carátula de cada archivo con mutagen.
- playable_path() devuelve un archivo que el reproductor de la app puede abrir:
  Windows no reproduce Opus/Vorbis ni ALAC, así que esos se convierten a un
  FLAC temporal (sin pérdida) con FFmpeg y se guardan en una caché.
"""
import base64
import hashlib
import logging
import os
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional

from . import paths, tools
from .process import run_quiet, CREATE_NO_WINDOW

logger = logging.getLogger(__name__)

AUDIO_EXTS = {".mp3", ".m4a", ".aac", ".opus", ".ogg", ".oga", ".flac", ".wav", ".webm"}
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
# Códecs que el reproductor (Media Foundation de Windows) abre directamente
NATIVE_CODECS = {"mp3", "aac", "flac"}
PLAY_CACHE_LIMIT = 1024 * 1024 * 1024  # 1 GB de conversiones temporales como máximo


@dataclass
class Track:
    path: str
    title: str
    artist: str = ""
    album: str = ""
    duration: float = 0.0
    folder: str = ""           # subcarpeta relativa a la carpeta de música ("" = raíz)
    cover: Optional[str] = None  # ruta a una imagen de carátula (caché o archivo al lado)
    mtime: float = 0.0
    search_text: str = field(default="", repr=False)


# ---------------------------------------------------------------- lectura

def _first(tags, *keys):
    if not tags:
        return ""
    for key in keys:
        try:
            value = tags.get(key)
        except Exception:
            value = None
        if value is None:
            continue
        if isinstance(value, list):
            value = value[0] if value else ""
        text = getattr(value, "text", value)
        if isinstance(text, list):
            text = text[0] if text else ""
        text = str(text).strip()
        if text:
            return text
    return ""


def _embedded_cover(audio):
    """Bytes de la carátula incrustada, si la hay (MP3, M4A, FLAC, Ogg/Opus)."""
    try:
        pictures = getattr(audio, "pictures", None)  # FLAC
        if pictures:
            return pictures[0].data
        tags = audio.tags
        if tags is None:
            return None
        if hasattr(tags, "getall"):  # ID3 (MP3)
            apic = tags.getall("APIC")
            if apic:
                return apic[0].data
        covr = tags.get("covr") if hasattr(tags, "get") else None  # MP4/M4A
        if covr:
            return bytes(covr[0])
        block = tags.get("metadata_block_picture") if hasattr(tags, "get") else None  # Ogg
        if block:
            from mutagen.flac import Picture
            return Picture(base64.b64decode(block[0])).data
    except Exception:
        logger.debug("No se pudo leer la carátula", exc_info=True)
    return None


def _cache_key(path, mtime):
    return hashlib.sha1(f"{path}|{mtime}".encode("utf-8", "replace")).hexdigest()


def _cover_for(path, audio, mtime):
    covers = os.path.join(paths.data_dir(), "covers")
    key = _cache_key(path, mtime)
    for ext in (".jpg", ".png"):
        cached = os.path.join(covers, key + ext)
        if os.path.exists(cached):
            return cached
    data = _embedded_cover(audio) if audio is not None else None
    if data:
        os.makedirs(covers, exist_ok=True)
        ext = ".png" if data[:8] == b"\x89PNG\r\n\x1a\n" else ".jpg"
        target = os.path.join(covers, key + ext)
        try:
            with open(target, "wb") as f:
                f.write(data)
            return target
        except OSError:
            pass
    stem = os.path.splitext(path)[0]  # miniatura guardada aparte (opción "Guardar miniatura")
    for ext in IMAGE_EXTS:
        if os.path.exists(stem + ext):
            return stem + ext
    return None


def read_track(path, root):
    from mutagen import File as MutagenFile
    stat = os.stat(path)
    try:
        audio = MutagenFile(path)
    except Exception:
        audio = None
    tags = getattr(audio, "tags", None)
    stem = os.path.splitext(os.path.basename(path))[0]
    title = _first(tags, "TIT2", "\xa9nam", "title") or stem
    artist = _first(tags, "TPE1", "\xa9ART", "artist", "TPE2", "aART", "albumartist")
    album = _first(tags, "TALB", "\xa9alb", "album")
    duration = float(getattr(getattr(audio, "info", None), "length", 0) or 0)
    folder = os.path.relpath(os.path.dirname(path), root)
    folder = "" if folder == "." else folder
    track = Track(path=path, title=title, artist=artist, album=album, duration=duration,
                  folder=folder, cover=_cover_for(path, audio, stat.st_mtime), mtime=stat.st_mtime)
    track.search_text = " ".join([title, artist, album, folder, stem]).lower()
    return track


def scan(root) -> List[Track]:
    """Todas las canciones de la carpeta, las más recientes primero."""
    tracks = []
    if not root or not os.path.isdir(root):
        return tracks
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            lower = name.lower()
            ext = os.path.splitext(lower)[1]
            if ext not in AUDIO_EXTS or ".tmp." in lower or lower.endswith(".part"):
                continue
            try:
                tracks.append(read_track(os.path.join(dirpath, name), root))
            except Exception:
                logger.warning("No se pudo leer %s", name, exc_info=True)
    tracks.sort(key=lambda t: t.mtime, reverse=True)
    return tracks


# ---------------------------------------------------------------- reproducción

def _ffprobe():
    ffmpeg = tools.ffmpeg_exe()
    if ffmpeg:
        candidate = os.path.join(os.path.dirname(ffmpeg), "ffprobe.exe")
        if os.path.isfile(candidate):
            return candidate
    import shutil
    return shutil.which("ffprobe")


def audio_codec(path):
    probe = _ffprobe()
    if not probe:
        return None
    try:
        code, out, _ = run_quiet([probe, "-v", "error", "-select_streams", "a:0",
                                  "-show_entries", "stream=codec_name", "-of", "csv=p=0", path], timeout=30)
        return out.strip().lower() if code == 0 else None
    except Exception:
        return None


def needs_conversion(path):
    codec = audio_codec(path)
    if codec is None:  # sin ffprobe: decidir por la extensión
        return os.path.splitext(path)[1].lower() in {".opus", ".ogg", ".oga", ".webm"}
    return codec not in NATIVE_CODECS and not codec.startswith("pcm_")


def _trim_cache(folder):
    try:
        files = [os.path.join(folder, f) for f in os.listdir(folder)]
        files.sort(key=os.path.getmtime)
        total = sum(os.path.getsize(f) for f in files)
        while files and total > PLAY_CACHE_LIMIT:
            oldest = files.pop(0)
            total -= os.path.getsize(oldest)
            os.remove(oldest)
    except OSError:
        pass


def playable_path(track: Track):
    """Ruta que el reproductor puede abrir (convierte Opus/ALAC a FLAC si hace falta)."""
    if not needs_conversion(track.path):
        return track.path
    folder = os.path.join(paths.data_dir(), "playcache")
    os.makedirs(folder, exist_ok=True)
    target = os.path.join(folder, _cache_key(track.path, track.mtime) + ".flac")
    if os.path.exists(target):
        os.utime(target)  # marcar como usado recientemente
        return target
    _trim_cache(folder)
    tmp = target + ".part.flac"
    cmd = [tools.require_ffmpeg(), "-y", "-v", "error", "-i", track.path, "-map", "0:a:0", "-vn", "-c:a", "flac", tmp]
    result = subprocess.run(cmd, capture_output=True, stdin=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
    if result.returncode != 0 or not os.path.exists(tmp):
        raise RuntimeError(result.stderr.decode("utf-8", "replace").strip() or "FFmpeg no pudo convertir el archivo")
    os.replace(tmp, target)
    return target


# ---------------------------------------------------------------- acciones

def show_in_folder(path):
    subprocess.Popen(["explorer", "/select,", os.path.normpath(path)], creationflags=CREATE_NO_WINDOW)


def delete_track(track: Track):
    """Borra el archivo y su miniatura aparte (mismo nombre), si existe."""
    os.remove(track.path)
    stem = os.path.splitext(track.path)[0]
    for ext in IMAGE_EXTS:
        try:
            os.remove(stem + ext)
        except OSError:
            pass


# ---------------------------------------------------------------- listas y duplicados

def write_m3u(path, files):
    """Lista de reproducción .m3u8 (UTF-8) con rutas relativas a su carpeta."""
    folder = os.path.dirname(os.path.abspath(path))
    lines = ["#EXTM3U"]
    for file in files:
        try:
            rel = os.path.relpath(file, folder)
        except ValueError:  # otra unidad
            rel = file
        lines.append(rel)
    os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\n".join(lines) + "\n")
    return path
