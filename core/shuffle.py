"""Aleatorio "inteligente" para el reproductor.

Un aleatorio puro suena peor de lo que parece: junta canciones del mismo artista y
repite las mismas al principio. Este reparte mejor sin dejar de ser impredecible:

1. Reparto por artista: las canciones de cada artista se colocan repartidas a lo
   largo de la lista (con un desfase y un pequeño desorden al azar), de modo que un
   artista con 6 canciones de 30 suena más o menos una de cada cinco.
2. Lo escuchado hace poco va hacia el final: cuanto más reciente, más se retrasa.
   Es un empujón progresivo, no una exclusión: si la lista es corta, sigue sonando.
3. Repaso final para que no queden dos canciones del mismo artista seguidas
   cuando se puede evitar.
"""
import json
import logging
import os
import random
import threading

from . import paths
from .spotify import _norm, _split_artists

logger = logging.getLogger(__name__)

HISTORY_SIZE = 300          # canciones recordadas como "escuchadas hace poco"
RECENT_PUSH = 0.6           # cuánto se retrasa (en fracción de la lista) lo más reciente
JITTER = 0.35               # desorden dentro del reparto de cada artista (0 = reparto exacto)


def artist_key(track):
    """Artista principal normalizado; sin artista, la carpeta (suele ser el álbum o la lista)."""
    artists = _split_artists(getattr(track, "artist", "") or "")
    if artists:
        return _norm(artists[0])
    return "folder:" + (getattr(track, "folder", "") or "").lower()


def _path_key(track):
    return os.path.normcase(os.path.abspath(track.path))


def smart_shuffle(tracks, recent=(), first=None, avoid_first=None, rng=None):
    """Devuelve una nueva lista con `tracks` en orden aleatorio equilibrado.

    recent: claves de ruta de lo escuchado últimamente, de la más antigua a la más reciente.
    first: canción que debe ir la primera (la que ya está sonando).
    avoid_first: canción que no debería ir la primera (la que acaba de sonar).
    """
    rng = rng or random.Random()
    pool = [tr for tr in tracks if tr is not first]
    if not pool:
        return [first] if first is not None else []

    # 1. Reparto por artista: posición en [0, 1) para cada canción
    groups = {}
    for track in pool:
        groups.setdefault(artist_key(track), []).append(track)
    positions = {}
    for items in groups.values():
        rng.shuffle(items)
        n = len(items)
        offset = rng.random() / n
        for i, track in enumerate(items):
            jitter = (rng.random() - 0.5) * JITTER / n
            positions[id(track)] = offset + i / n + jitter

    # 2. Lo reciente, hacia el final (más cuanto más reciente)
    recent = list(recent)
    if recent:
        rank = {key: (i + 1) / len(recent) for i, key in enumerate(recent)}
        for track in pool:
            weight = rank.get(_path_key(track))
            if weight:
                positions[id(track)] += RECENT_PUSH * weight

    ordered = sorted(pool, key=lambda tr: positions[id(tr)])

    # 3. Evitar dos seguidas del mismo artista (y no repetir la que acaba de sonar)
    result = [first] if first is not None else []
    if avoid_first is not None and not result and len(ordered) > 1 and ordered[0] is avoid_first:
        ordered.append(ordered.pop(0))
    result.extend(ordered)
    _spread_neighbours(result, start=1 if first is not None else 0)
    return result


def _spread_neighbours(items, start=0):
    """Si dos canciones seguidas son del mismo artista, cambia la segunda por la
    siguiente que sea de otro (sin tocar la primera posición fija)."""
    keys = [artist_key(tr) for tr in items]
    for i in range(max(start, 1), len(items)):
        if keys[i] != keys[i - 1]:
            continue
        for j in range(i + 1, len(items)):
            if keys[j] != keys[i - 1]:
                items[i], items[j] = items[j], items[i]
                keys[i], keys[j] = keys[j], keys[i]
                break


# ------------------------------------------------------------------ historial de escucha

class PlayHistory:
    """Últimas canciones escuchadas (guardadas en %LOCALAPPDATA%\\EasyTunrMusic)."""

    def __init__(self, path=None):
        self.path = path or os.path.join(paths.data_dir(), "play_history.json")
        self._lock = threading.Lock()
        self.items = self._load()

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            return [str(x) for x in data][-HISTORY_SIZE:] if isinstance(data, list) else []
        except (OSError, ValueError):
            return []

    def add(self, track):
        key = _path_key(track)
        with self._lock:
            self.items = [k for k in self.items if k != key] + [key]
            self.items = self.items[-HISTORY_SIZE:]
            snapshot = list(self.items)
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False)
            os.replace(tmp, self.path)
        except OSError:
            logger.debug("No se pudo guardar el historial de escucha", exc_info=True)

    def recent(self):
        with self._lock:
            return list(self.items)
