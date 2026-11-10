"""Importación de playlists de Spotify exportadas a CSV (p. ej. con Exportify).

Cada canción se busca en YouTube y se elige el resultado que mejor encaja por
título, artista y duración.
"""
import csv
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Optional

from . import ytdlp

logger = logging.getLogger(__name__)

MIN_SCORE = 30
BAD_KEYWORDS = ["live", "karaoke", "cover", "remix", "nightcore", "sped up", "reverb", "instrumental", "8d"]


@dataclass
class Track:
    title: str
    artist: str
    duration: Optional[float] = None


@dataclass
class Match:
    track: Track
    url: str
    video_title: str
    filename: str


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
        return next((k for k in fieldnames if k.lower().strip() in names), None)

    title_key = find(["track name", "name", "title", "track"]) or (fieldnames[0] if fieldnames else None)
    artist_key = find(["artist name(s)", "artist", "artists", "album artist name"])
    duration_key = find(["duration (ms)", "duration_ms", "duration"])

    tracks = []
    for row in rows:
        title = (row.get(title_key) or "").strip() if title_key else ""
        if not title:
            continue
        artist = (row.get(artist_key) or "").strip() if artist_key else ""
        duration = None
        raw = (row.get(duration_key) or "").strip() if duration_key else ""
        if raw.isdigit():
            duration = int(raw) / 1000 if int(raw) > 1000 else int(raw)
        tracks.append(Track(title, artist, duration))
    return tracks


def _tokens(value):
    normalized = re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (value or "").lower())).strip()
    return {t for t in normalized.split(" ") if t}


def score_candidate(entry, track):
    entry_title = entry.get("title") or ""
    uploader = entry.get("uploader") or entry.get("channel") or ""
    full_tokens = _tokens(f"{entry_title} {uploader}")
    score = 0.0
    title_tokens = _tokens(track.title)
    if title_tokens:
        score += len(title_tokens & full_tokens) / len(title_tokens) * 70
    artist_tokens = _tokens(track.artist)
    if artist_tokens:
        score += len(artist_tokens & full_tokens) / len(artist_tokens) * 40

    lowered = entry_title.lower()
    query = f"{track.title} {track.artist}".lower()
    for keyword in BAD_KEYWORDS:
        if keyword in lowered and keyword not in query:
            score -= 25

    duration = entry.get("duration")
    if track.duration and isinstance(duration, (int, float)):
        diff = abs(float(duration) - float(track.duration))
        if diff <= 8:
            score += 20
        elif diff <= 20:
            score += 10
        elif diff > 45:
            score -= 30
    return score


def _best_entry(track):
    try:
        entries = ytdlp.search(f"\"{track.title}\" {track.artist} official audio".strip(), 8)
    except Exception:
        logger.exception("Búsqueda fallida para %s - %s", track.title, track.artist)
        return None
    scored = [(score_candidate(e, track), e) for e in entries]
    return max(scored, key=lambda item: item[0]) if scored else None


def resolve(tracks, on_progress=None, workers=4):
    """Busca cada canción en YouTube. on_progress(hechas, total, encontradas).

    Devuelve una lista de Match en el orden del CSV (las no encontradas se omiten).
    """
    best = [None] * len(tracks)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_best_entry, t): i for i, t in enumerate(tracks)}
        for done, future in enumerate(as_completed(futures), start=1):
            best[futures[future]] = future.result()
            if on_progress:
                on_progress(done, len(tracks), sum(1 for b in best if b and b[0] >= MIN_SCORE))

    matches, used = [], {}
    for track, result in zip(tracks, best):
        if not result or result[0] < MIN_SCORE:
            continue
        url = ytdlp.entry_url(result[1])
        if not url:
            continue
        base = f"{track.title} - {track.artist}".strip(" -") or track.title
        used[base] = used.get(base, 0) + 1
        filename = f"{base} ({used[base]})" if used[base] > 1 else base
        matches.append(Match(track, url, result[1].get("title") or "", filename))
    return matches
