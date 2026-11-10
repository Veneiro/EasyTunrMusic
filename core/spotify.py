"""Importación de playlists de Spotify exportadas a CSV (p. ej. con Exportify).

Cada canción se busca en YouTube y se elige el resultado que mejor encaja por
título, artista y duración. Los candidatos que no pasan una validación estricta
(título incompleto, artista ausente, versión distinta, duración muy diferente o
palabras de sobra que indican otra canción) se descartan: es preferible no
descargar nada a descargar una canción equivocada.
"""
import csv
import json
import logging
import os
import re
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from typing import List, Optional

from . import paths, ytdlp
from .utils import clean_folder_name

logger = logging.getLogger(__name__)

SEARCH_LIMIT = 10

# Palabras que indican una versión distinta de la original. Si aparecen en el
# vídeo y no en la canción (o al revés), el candidato se descarta.
VERSION_WORDS = {
    "live", "vivo", "directo", "concert", "concierto", "karaoke", "cover",
    "remix", "nightcore", "sped", "slowed", "reverb", "instrumental", "8d",
    "acoustic", "acustico", "acustica", "unplugged", "mashup", "reaction",
    "tutorial", "lesson", "boosted", "bootleg", "extended", "demo",
    "orchestral", "orquestal", "symphonic", "sinfonico", "piano", "acapella",
    "cappella", "lofi", "vaporwave", "parody", "parodia",
}

# Palabras habituales en títulos de YouTube que no cambian la canción.
NOISE_WORDS = {
    "official", "oficial", "video", "videoclip", "clip", "musical", "music",
    "musica", "audio", "lyrics", "lyric", "letra", "letras", "visualizer",
    "visualiser", "hd", "hq", "4k", "uhd", "mv", "explicit", "clean", "version",
    "remastered", "remaster", "remasterizado", "original", "mix", "edit",
    "radio", "single", "album", "full", "song", "ft", "feat", "featuring",
    "with", "con", "by", "prod", "x", "and", "y", "the", "el", "la", "los",
    "las", "of", "de", "a", "en", "topic", "vevo", "espanol", "english",
    "sub", "subs", "subtitulada", "subtitulado", "traducida", "traduccion",
    "new", "nuevo", "estreno", "premiere", "stereo", "mono", "quality",
}

FEAT_RE = re.compile(r"[(\[]\s*(?:feat|ft|featuring|with|con)\b[^)\]]*[)\]]", re.I)
BRACKETS_RE = re.compile(r"[(\[][^)\]]*[)\]]")
DASH_RE = re.compile(r"\s+[-–—]\s+")
NUMERIC_RE = re.compile(r"^\d+[pk]?$")


AUDIO_EXTS = {".mp3", ".m4a", ".aac", ".opus", ".ogg", ".oga", ".flac", ".wav", ".webm"}
CACHE_DAYS = 60
MAX_ALTERNATIVES = 5


@dataclass
class Track:
    title: str
    artist: str
    duration: Optional[float] = None
    album: str = ""
    release_date: str = ""
    isrc: str = ""
    spotify_id: str = ""
    cover_url: str = ""
    track_number: Optional[int] = None


@dataclass
class Candidate:
    """Un vídeo de YouTube para una canción. score es None si no pasa la validación."""
    url: str
    title: str
    channel: str = ""
    duration: Optional[float] = None
    score: Optional[float] = None

    @property
    def valid(self):
        return self.score is not None


@dataclass
class Match:
    track: Track
    url: str
    video_title: str
    filename: str
    video_duration: Optional[float] = None
    alternatives: List[Candidate] = field(default_factory=list)  # otros vídeos válidos, por orden

    @property
    def duration_diff(self):
        if self.track.duration and self.video_duration:
            return abs(self.video_duration - self.track.duration)
        return None


def read_csv(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as file:
        sample = file.read(4096)
        file.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(file, dialect=dialect)
        rows = list(reader)
        fieldnames = reader.fieldnames or []

    def find(names):
        by_name = {_norm(k): k for k in fieldnames if k}
        return next((by_name[n] for n in names if n in by_name), None)

    title_key = find(TITLE_COLUMNS) or _first_text_column(fieldnames, rows)
    artist_key = find(ARTIST_COLUMNS)
    duration_key = find(DURATION_COLUMNS)
    album_key = find(ALBUM_COLUMNS)
    release_key = find(["album release date", "release date", "album date", "fecha de lanzamiento"])
    isrc_key = find(["isrc"])
    id_key = find(["track uri", "spotify track id", "track id", "spotify id", "uri"])
    number_key = find(["track number", "numero de pista"])

    tracks = []
    for row in rows:
        title = (row.get(title_key) or "").strip() if title_key else ""
        if not title:
            continue
        artist = (row.get(artist_key) or "").strip() if artist_key else ""
        artist = ", ".join(_split_artists(artist)) or artist  # "A,B" o "A;B" -> "A, B"
        duration = _parse_duration(row.get(duration_key) if duration_key else None)
        album = (row.get(album_key) or "").strip() if album_key else ""
        release = (row.get(release_key) or "").strip() if release_key else ""
        isrc = (row.get(isrc_key) or "").strip() if isrc_key else ""
        spotify_id = (row.get(id_key) or "").strip().split(":")[-1] if id_key else ""
        number = (row.get(number_key) or "").strip() if number_key else ""
        tracks.append(Track(title, artist, duration, album, release, isrc,
                            spotify_id if re.fullmatch(r"[A-Za-z0-9]{22}", spotify_id) else "",
                            track_number=int(number) if number.isdigit() else None))
    return tracks


# Nombres de columna (normalizados) de Exportify, de otros exportadores y en español.
TITLE_COLUMNS = ["track name", "song name", "song", "track title", "title", "name", "track",
                 "cancion", "titulo", "nombre", "tema"]
ARTIST_COLUMNS = ["artist name s", "artist names", "artist s", "artists", "artist", "artist name",
                  "artista s", "artistas", "artista", "album artist name s", "album artist name"]
DURATION_COLUMNS = ["duration ms", "duration_ms", "track duration ms", "duration", "length",
                    "time", "duracion", "tiempo"]
ALBUM_COLUMNS = ["album name", "album", "album title"]


def _first_text_column(fieldnames, rows):
    """Primera columna que no sea numérica (evita usar '#' o la posición como título)."""
    sample = rows[:20]
    for name in fieldnames:
        values = [(r.get(name) or "").strip() for r in sample]
        if any(values) and not all(re.fullmatch(r"[\d.,:\s-]*", v) for v in values):
            return name
    return None


def _parse_duration(raw):
    """Segundos a partir de milisegundos, segundos, 'm:ss' o 'h:mm:ss'."""
    raw = (raw or "").strip()
    if not raw:
        return None
    if ":" in raw:
        try:
            seconds = 0.0
            for part in raw.split(":"):
                seconds = seconds * 60 + float(part)
            return seconds or None
        except ValueError:
            return None
    try:
        value = float(raw.replace(",", "."))
    except ValueError:
        return None
    if value <= 0:
        return None
    return value / 1000 if value > 3600 else value


# ------------------------------------------------------------------ normalización

def _norm(value):
    """Minúsculas, sin tildes ni apóstrofos y con la puntuación como espacios."""
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(c for c in value if not unicodedata.combining(c)).lower()
    value = value.replace("&", " and ").replace("'", "").replace("’", "")
    return re.sub(r"[\W_]+", " ", value).strip()


def _tokens(value):
    return set(_norm(value).split())


def _compact(value):
    return _norm(value).replace(" ", "")


def _split_artists(artist):
    return [a.strip() for a in re.split(r"[;,]", artist or "") if a.strip()]


def _split_title(title):
    """Separa el título de Spotify en (núcleo, extras opcionales).

    "Under Pressure - Remastered 2011" -> ("Under Pressure", "Remastered 2011")
    "Waka Waka (This Time for Africa)" -> ("Waka Waka", "This Time for Africa")
    """
    title = FEAT_RE.sub(" ", title or "")
    parts = DASH_RE.split(title, maxsplit=1)
    head = parts[0]
    extra = parts[1] if len(parts) > 1 else ""
    core = BRACKETS_RE.sub(" ", head)
    if not _tokens(core):  # título entero entre paréntesis
        core = head
    extra = " ".join([extra] + re.findall(r"[(\[]([^)\]]*)[)\]]", head))
    return core.strip(), extra.strip()


def _video_core(video_title):
    """Parte del título del vídeo que nombra la canción: sin paréntesis ni lo que
    va tras '|' o '//', donde suelen ir el álbum, el sello o 'Official Video'."""
    head = re.split(r"\||//", video_title or "", maxsplit=1)[0]
    return BRACKETS_RE.sub(" ", head)


# ------------------------------------------------------------------ puntuación

def _artist_coverage(artist, video_tokens, uploader):
    compact = _compact(artist)
    if len(compact) >= 4 and compact in _compact(uploader):
        return 1.0  # "BadBunnyVEVO", "Adele - Topic"...
    tokens = _tokens(artist)
    significant = tokens - {"the", "el", "la", "los", "las"} or tokens
    if not significant:
        return 0.0
    return len(significant & (video_tokens | _tokens(uploader))) / len(significant)


def score_candidate(entry, track):
    """Puntuación del vídeo para la canción, o None si no es la misma canción."""
    video_title = entry.get("title") or ""
    uploader = entry.get("uploader") or entry.get("channel") or ""
    video_tokens = _tokens(video_title)
    if not video_tokens:
        return None

    core, extra = _split_title(track.title)
    core_tokens = _tokens(core)
    extra_tokens = _tokens(extra)
    artists = _split_artists(track.artist)
    artist_tokens = set().union(*(_tokens(a) for a in artists)) if artists else set()

    # 1. El título de la canción tiene que estar (casi) entero en el del vídeo.
    if core_tokens:
        found = len(core_tokens & video_tokens)
        missing = len(core_tokens) - found
        if missing > len(core_tokens) // 4:
            return None
        title_cov = found / len(core_tokens)
    else:
        title_cov = 0.0

    # 2. Alguno de los artistas tiene que aparecer en el título o en el canal.
    artist_cov = max((_artist_coverage(a, video_tokens, uploader) for a in artists), default=1.0)
    if artist_cov < 0.5:
        return None

    # 3. Misma versión: ni "live"/"cover"/"remix" de más, ni "remix" de menos.
    track_words = _tokens(track.title)
    wanted = (track_words & VERSION_WORDS) - artist_tokens
    present = (video_tokens & VERSION_WORDS) - track_words - artist_tokens - _tokens(uploader)
    if present or not wanted <= video_tokens:
        return None

    # 4. Palabras de sobra en el título del vídeo suelen indicar otra canción
    #    ("Amor" frente a "Amor Prohibido").
    album_tokens = _tokens(track.album)

    def unexpected(tokens):
        return {
            t for t in tokens
            if t not in core_tokens and t not in extra_tokens and t not in artist_tokens
            and t not in album_tokens and t not in NOISE_WORDS and not NUMERIC_RE.match(t)
        }

    leftover = unexpected(_tokens(_video_core(video_title)))
    if len(leftover) > len(core_tokens) // 2:
        return None
    # El texto extra entre paréntesis no descarta, pero se prefieren títulos limpios.
    bracket_extra = unexpected(video_tokens) - leftover

    # 5. La duración, si se conoce, tiene que ser parecida.
    duration_bonus = 0.0
    duration = entry.get("duration")
    if track.duration and isinstance(duration, (int, float)) and duration > 0:
        diff = abs(float(duration) - float(track.duration))
        if diff > max(25.0, track.duration * 0.12):
            return None
        # La misma grabación que en Spotify suele durar lo mismo al segundo.
        duration_bonus = (35 if diff <= 2 else 28 if diff <= 4 else 18 if diff <= 8
                          else 8 if diff <= 15 else -10)

    score = (title_cov * 50 + artist_cov * 30 + duration_bonus
             - len(leftover) * 5 - min(len(bracket_extra), 5) * 2)
    lowered = uploader.lower()
    if lowered.endswith(" - topic") or "vevo" in lowered or (
            artists and _compact(artists[0]) and _compact(artists[0]) in _compact(uploader)):
        score += 10  # canal oficial o audio subido por la discográfica
    return score


def _queries(track):
    core, extra = _split_title(track.title)
    flavor = " ".join(sorted(_tokens(extra) & VERSION_WORDS))
    artists = _split_artists(track.artist)
    primary = artists[0] if artists else ""
    song = f"{core} {flavor}".strip()
    yield f"{primary} {song} audio".strip()
    yield f"\"{core}\" {' '.join(artists)} {flavor}".strip()


def _candidate(entry, track):
    return Candidate(
        url=ytdlp.entry_url(entry),
        title=entry.get("title") or "",
        channel=entry.get("uploader") or entry.get("channel") or "",
        duration=entry.get("duration") if isinstance(entry.get("duration"), (int, float)) else None,
        score=score_candidate(entry, track),
    )


def find_candidates(track):
    """Vídeos válidos para la canción, del mejor al peor (lista vacía si ninguno encaja)."""
    seen = set()
    for query in _queries(track):
        try:
            entries = ytdlp.search(query, SEARCH_LIMIT)
        except Exception:
            logger.exception("Búsqueda fallida para %s - %s", track.title, track.artist)
            continue
        valid = []
        for entry in entries:
            if not entry:
                continue
            key = entry.get("id") or entry.get("url")
            if key in seen:
                continue
            seen.add(key)
            candidate = _candidate(entry, track)
            if candidate.valid and candidate.url:
                valid.append(candidate)
        if valid:
            return sorted(valid, key=lambda c: c.score, reverse=True)
    logger.info("Sin coincidencia fiable para %s - %s", track.title, track.artist)
    return []


def search_candidates(track, query, limit=SEARCH_LIMIT):
    """Búsqueda manual: todos los resultados, los válidos primero y por puntuación."""
    entries = ytdlp.search(query, limit)
    results = [_candidate(e, track) for e in entries if e]
    results = [c for c in results if c.url]
    return sorted(results, key=lambda c: (c.valid, c.score or 0), reverse=True)


# ------------------------------------------------------------------ caché de búsquedas

_cache_lock = threading.Lock()


def _cache_path():
    return os.path.join(paths.data_dir(), "spotify_matches.json")


def _cache_key(track):
    return f"{_norm(track.title)}|{_norm(track.artist)}|{int(round(track.duration or 0))}"


def _load_cache():
    try:
        with open(_cache_path(), encoding="utf-8") as f:
            data = json.load(f)
        limit = time.time() - CACHE_DAYS * 86400
        return {k: v for k, v in data.items() if isinstance(v, dict) and v.get("ts", 0) >= limit}
    except (OSError, ValueError):
        return {}


def _save_cache(cache):
    with _cache_lock:
        try:
            tmp = _cache_path() + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False)
            os.replace(tmp, _cache_path())
        except OSError:
            logger.warning("No se pudo guardar la caché de búsquedas", exc_info=True)


def remember_choice(track, candidate):
    """Guarda en la caché el vídeo elegido a mano para que se use la próxima vez."""
    cache = _load_cache()
    previous = [Candidate(**c) for c in cache.get(_cache_key(track), {}).get("candidates", [])]
    ordered = [candidate] + [c for c in previous if c.url != candidate.url]
    cache[_cache_key(track)] = {"ts": time.time(), "candidates": [asdict(c) for c in ordered[:MAX_ALTERNATIVES + 1]]}
    _save_cache(cache)


# ------------------------------------------------------------------ resolución

def track_basename(track):
    """Nombre de archivo (sin extensión) con el que se guarda la canción."""
    return clean_folder_name(f"{track.title} - {track.artist}".strip(" -") or track.title)


def existing_files(folder):
    """{nombre sin extensión en minúsculas: ruta} de las canciones que ya hay en la carpeta."""
    found = {}
    try:
        for name in os.listdir(folder):
            stem, ext = os.path.splitext(name)
            if ext.lower() in AUDIO_EXTS and ".tmp" not in stem.lower():
                found[stem.lower()] = os.path.join(folder, name)
    except OSError:
        pass
    return found


def split_downloaded(tracks, folder):
    """Separa (pendientes, ya descargadas) según los archivos que hay en la carpeta."""
    existing = existing_files(folder)
    pending, done = [], []
    for track in tracks:
        (done if track_basename(track).lower() in existing else pending).append(track)
    return pending, done


def _match_from(track, candidates, filename):
    best = candidates[0]
    return Match(track, best.url, best.title, filename, best.duration, candidates[1:MAX_ALTERNATIVES + 1])


def resolve(tracks, on_progress=None, workers=4):
    """Busca cada canción en YouTube. on_progress(hechas, total, encontradas).

    Devuelve (coincidencias en el orden recibido, canciones sin coincidencia fiable).
    Las búsquedas con éxito se guardan en caché para no repetirlas.
    """
    cache = _load_cache()
    results = [None] * len(tracks)
    pending = []
    for i, track in enumerate(tracks):
        cached = cache.get(_cache_key(track))
        if cached and cached.get("candidates"):
            results[i] = [Candidate(**c) for c in cached["candidates"]]
        else:
            pending.append(i)

    done = len(tracks) - len(pending)
    if on_progress:
        on_progress(done, len(tracks), done)
    if pending:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(find_candidates, tracks[i]): i for i in pending}
            for future in as_completed(futures):
                i = futures[future]
                results[i] = future.result()
                if results[i]:
                    cache[_cache_key(tracks[i])] = {
                        "ts": time.time(),
                        "candidates": [asdict(c) for c in results[i][:MAX_ALTERNATIVES + 1]],
                    }
                done += 1
                if on_progress:
                    on_progress(done, len(tracks), sum(1 for r in results if r))
        _save_cache(cache)

    matches, missing, used = [], [], {}
    for track, candidates in zip(tracks, results):
        if not candidates:
            missing.append(track)
            continue
        base = track_basename(track)
        used[base.lower()] = used.get(base.lower(), 0) + 1
        filename = f"{base} ({used[base.lower()]})" if used[base.lower()] > 1 else base
        matches.append(_match_from(track, candidates, filename))
    return matches, missing


def match_with(track, candidate, alternatives=()):
    """Coincidencia elegida a mano (desde la pantalla de revisión)."""
    others = [c for c in alternatives if c.url != candidate.url and c.valid]
    return Match(track, candidate.url, candidate.title, track_basename(track), candidate.duration,
                 others[:MAX_ALTERNATIVES])
