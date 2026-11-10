"""Letras de canciones desde LRCLIB (https://lrclib.net), gratis y sin clave.

Se guarda un .lrc (letra sincronizada) junto a la canción, que entienden la mayoría
de reproductores, y la letra sin tiempos se incrusta en el propio archivo. Solo se
acepta un resultado si su duración coincide con la de la canción, para no poner la
letra de otra versión u otra canción.
"""
import logging
import os
import re
import urllib.error

from . import net
from .spotify import BRACKETS_RE, DASH_RE, _norm, _split_artists, _split_title

logger = logging.getLogger(__name__)

API = "https://lrclib.net/api"
MAX_DURATION_DIFF = 3.0


def _pick(results, title, duration):
    wanted = _norm(title)
    best = None
    for item in results or []:
        if not (item.get("syncedLyrics") or item.get("plainLyrics")) or item.get("instrumental"):
            continue
        if duration and abs(float(item.get("duration") or 0) - duration) > MAX_DURATION_DIFF:
            continue
        if not duration and _norm(item.get("trackName")) != wanted:
            continue
        if best is None or (item.get("syncedLyrics") and not best.get("syncedLyrics")):
            best = item
    return best


def fetch(title, artist, album="", duration=None, file_duration=None):
    """(letra sincronizada, letra sin tiempos), con None donde no la haya.

    duration: duración de la canción, para encontrar la letra correcta.
    file_duration: duración real del archivo descargado. La letra sincronizada sigue
    los tiempos de la canción original: si el archivo dura distinto (videoclip con
    intro, otra versión...), quedaría desfasada, así que solo se devuelve la letra
    sin tiempos, que no puede desfasarse."""
    core = _split_title(title)[0] or title
    artists = _split_artists(artist)
    primary = artists[0] if artists else artist
    if not core or not primary:
        return None, None
    found = None
    try:
        if album and duration:
            try:
                item = net.get_json(f"{API}/get", {"track_name": core, "artist_name": primary,
                                                  "album_name": album, "duration": int(round(duration))})
                found = _pick([item], core, duration)
            except urllib.error.HTTPError as exc:
                if exc.code != 404:
                    raise
        if not found:
            results = net.get_json(f"{API}/search", {"track_name": core, "artist_name": primary})
            found = _pick(results, core, duration)
    except Exception:
        logger.info("No se pudo consultar LRCLIB para %s - %s", primary, core, exc_info=True)
        return None, None
    if not found:
        return None, None
    synced = found.get("syncedLyrics") or None
    if synced and not synced_fits(found.get("duration"), file_duration):
        logger.info("Letra sincronizada descartada para %s - %s: el archivo dura %s s y la letra %s s",
                    primary, core, file_duration, found.get("duration"))
        synced = None
    return synced, found.get("plainLyrics") or None


def synced_fits(lyrics_duration, file_duration):
    """True si la letra sincronizada encaja con el archivo (o no se puede comprobar)."""
    if not file_duration or not lyrics_duration:
        return True
    return abs(float(lyrics_duration) - float(file_duration)) <= MAX_DURATION_DIFF


def guess_from_video_title(video_title, uploader=""):
    """(título, artista) a partir de "Artista - Canción (Official Video)"."""
    cleaned = BRACKETS_RE.sub(" ", video_title or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    parts = DASH_RE.split(cleaned, maxsplit=1)
    if len(parts) == 2:
        return parts[1].strip(), parts[0].strip()
    artist = re.sub(r"\s*-\s*topic$|vevo$", "", uploader or "", flags=re.I).strip()
    return cleaned, artist


def write_lrc(audio_path, synced):
    path = os.path.splitext(audio_path)[0] + ".lrc"
    with open(path, "w", encoding="utf-8") as f:
        f.write(synced.strip() + "\n")
    return path


# ------------------------------------------------------------------ lectura (reproductor)

LRC_LINE_RE = re.compile(r"\[(\d+):(\d+(?:[.:]\d+)?)\]")


def parse_lrc(text):
    """[(segundos, línea)] ordenado. Una línea puede llevar varias marcas de tiempo."""
    lines = []
    for raw in (text or "").splitlines():
        stamps = LRC_LINE_RE.findall(raw)
        if not stamps:
            continue
        lyric = LRC_LINE_RE.sub("", raw).strip()
        for minutes, seconds in stamps:
            try:
                lines.append((int(minutes) * 60 + float(seconds.replace(":", ".")), lyric))
            except ValueError:
                continue
    return sorted(lines, key=lambda item: item[0])


def _embedded_lyrics(path):
    from mutagen import File as MutagenFile
    try:
        audio = MutagenFile(path)
    except Exception:
        return ""
    tags = getattr(audio, "tags", None)
    if not tags:
        return ""
    try:
        if hasattr(tags, "getall"):  # ID3
            uslt = tags.getall("USLT")
            return str(uslt[0].text) if uslt else ""
        for key in ("\xa9lyr", "lyrics", "LYRICS", "unsyncedlyrics"):
            value = tags.get(key)
            if value:
                return str(value[0] if isinstance(value, list) else value)
    except Exception:
        logger.debug("No se pudo leer la letra de %s", path, exc_info=True)
    return ""


def read_for(path):
    """(líneas con tiempo del .lrc, letra sin tiempos) de una canción descargada."""
    lrc = os.path.splitext(path)[0] + ".lrc"
    timed = []
    if os.path.exists(lrc):
        try:
            with open(lrc, encoding="utf-8", errors="replace") as f:
                timed = parse_lrc(f.read())
        except OSError:
            pass
    plain = "" if timed else _embedded_lyrics(path)
    return timed, plain.strip()
