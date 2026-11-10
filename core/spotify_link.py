"""Importación directa de enlaces de Spotify (playlist, álbum o canción).

Se usa la página pública "embed" de Spotify (la que se inserta en otras webs), que
da título, artistas y duración sin necesidad de cuenta ni claves. Para playlists solo
muestra las primeras 100 canciones; las más largas se importan exportándolas a CSV.
"""
import json
import logging
import re
import urllib.error
from dataclasses import dataclass, field
from typing import List

from . import net
from .spotify import Track

logger = logging.getLogger(__name__)

EMBED_LIMIT = 100
LINK_RE = re.compile(
    r"(?:open\.spotify\.com/(?:intl-[a-z-]+/)?(?:embed/)?|spotify:)(playlist|album|track)[/:]([A-Za-z0-9]{22})",
    re.I)
NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)


class SpotifyLinkError(RuntimeError):
    pass


@dataclass
class SpotifyCollection:
    name: str
    kind: str                       # playlist | album | track
    tracks: List[Track] = field(default_factory=list)
    truncated: bool = False         # la página pública solo da las primeras 100 canciones


def parse_link(text):
    """(tipo, id) de un enlace o URI de Spotify, o None."""
    match = LINK_RE.search(text or "")
    return (match.group(1).lower(), match.group(2)) if match else None


def is_spotify_link(text):
    return parse_link(text) is not None


def load(text):
    parsed = parse_link(text)
    if not parsed:
        raise SpotifyLinkError("El enlace no es de una playlist, álbum o canción de Spotify")
    return _load_embed(*parsed)


# ------------------------------------------------------------------ página pública

def _year(release):
    if isinstance(release, dict):
        release = release.get("isoString") or ""
    return (release or "")[:10]


def _cover(entity):
    images = (entity.get("visualIdentity") or {}).get("image") or []
    if images:
        return max(images, key=lambda i: i.get("maxHeight") or 0).get("url") or ""
    sources = (entity.get("coverArt") or {}).get("sources") or []
    return sources[0].get("url", "") if sources else ""


def _track_id(uri):
    return (uri or "").split(":")[-1] if (uri or "").startswith("spotify:track:") else ""


def _load_embed(kind, item_id):
    try:
        html = net.get(f"https://open.spotify.com/embed/{kind}/{item_id}", timeout=20).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise SpotifyLinkError("Spotify no encuentra ese enlace (¿es privado o se ha borrado?)") from exc
        raise SpotifyLinkError(f"Spotify respondió con un error ({exc.code})") from exc
    except urllib.error.URLError as exc:
        raise SpotifyLinkError(f"No se pudo conectar con Spotify: {exc.reason}") from exc

    match = NEXT_DATA_RE.search(html)
    try:
        entity = json.loads(match.group(1))["props"]["pageProps"]["state"]["data"]["entity"]
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise SpotifyLinkError("No se pudo leer la página de Spotify (puede que haya cambiado)") from exc

    name = entity.get("name") or entity.get("title") or "Spotify"
    if kind == "track":
        artists = ", ".join(a.get("name", "") for a in entity.get("artists") or [] if a.get("name"))
        track = Track(name, artists, (entity.get("duration") or 0) / 1000 or None,
                      release_date=_year(entity.get("releaseDate")), spotify_id=item_id)
        return SpotifyCollection(f"{name} - {artists}".strip(" -"), kind, [track])

    album = name if kind == "album" else ""
    cover = _cover(entity) if kind == "album" else ""
    tracks = []
    for number, item in enumerate(entity.get("trackList") or [], start=1):
        title = (item.get("title") or "").strip()
        if not title:
            continue
        tracks.append(Track(
            title, (item.get("subtitle") or "").replace(" ", " ").strip(),
            (item.get("duration") or 0) / 1000 or None,
            album=album, release_date=_year(entity.get("releaseDate")),
            spotify_id=_track_id(item.get("uri")), cover_url=cover,
            track_number=number if kind == "album" else None,
        ))
    if not tracks:
        raise SpotifyLinkError("No se encontraron canciones en ese enlace")
    return SpotifyCollection(name, kind, tracks, truncated=kind == "playlist" and len(tracks) >= EMBED_LIMIT)


# ------------------------------------------------------------------ carátulas

def cover_url_for(track_id):
    """Carátula del álbum de una canción mediante el oEmbed público de Spotify (640 px si existe)."""
    if not track_id:
        return ""
    try:
        data = net.get_json("https://open.spotify.com/oembed", {"url": f"spotify:track:{track_id}"}, timeout=15)
    except Exception:
        logger.debug("Sin carátula de Spotify para %s", track_id, exc_info=True)
        return ""
    url = data.get("thumbnail_url") or ""
    # Mismo identificador de imagen, tamaño 640x640 en lugar de 300x300
    return url.replace("ab67616d00001e02", "ab67616d0000b273")
