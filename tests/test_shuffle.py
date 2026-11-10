"""Aleatorio equilibrado del reproductor."""
import os
import random
import tempfile
import unittest
from dataclasses import dataclass

from core.shuffle import PlayHistory, _path_key, artist_key, smart_shuffle


@dataclass(eq=False)
class T:
    path: str
    title: str
    artist: str
    folder: str = ""


SPEC = {"Pink Floyd": 12, "The Warning": 6, "Queen": 4, "ABBA": 3, "Ghost": 2, "Prince": 1, "Adele": 1, "Sam Cooke": 1}
LIBRARY = [T(f"C:/musica/{a}-{i}.mp3", f"{a} {i}", a) for a, n in SPEC.items() for i in range(n)]


def adjacent_same_artist(order):
    return sum(artist_key(a) == artist_key(b) for a, b in zip(order, order[1:]))


class SmartShuffleTest(unittest.TestCase):
    def test_no_pierde_ni_duplica_canciones(self):
        rng = random.Random(1)
        for _ in range(100):
            result = smart_shuffle(LIBRARY, rng=rng)
            self.assertEqual(sorted(map(id, result)), sorted(map(id, LIBRARY)))

    def test_reparte_los_artistas(self):
        rng = random.Random(2)
        smart = [adjacent_same_artist(smart_shuffle(LIBRARY, rng=rng)) for _ in range(300)]
        pure = []
        for _ in range(300):
            order = list(LIBRARY)
            rng.shuffle(order)
            pure.append(adjacent_same_artist(order))
        self.assertLess(sum(smart) / len(smart), 0.5)          # casi nunca dos seguidas
        self.assertGreater(sum(pure) / len(pure), 4)            # el aleatorio puro, muchas

    def test_no_repite_el_orden(self):
        rng = random.Random(3)
        orders = {tuple(map(id, smart_shuffle(LIBRARY, rng=rng))) for _ in range(200)}
        self.assertEqual(len(orders), 200)

    def test_lo_escuchado_hace_poco_va_hacia_el_final(self):
        rng = random.Random(4)
        recent_tracks = LIBRARY[::4]
        recent = [_path_key(t) for t in recent_tracks]
        recent_pos, other_pos = [], []
        for _ in range(300):
            for i, track in enumerate(smart_shuffle(LIBRARY, recent=recent, rng=rng)):
                (recent_pos if track in recent_tracks else other_pos).append(i)
        self.assertGreater(sum(recent_pos) / len(recent_pos), sum(other_pos) / len(other_pos) + 4)
        # ...pero no se excluyen: a veces siguen saliendo pronto
        self.assertTrue(any(p < len(LIBRARY) // 4 for p in recent_pos))

    def test_cancion_fija_al_principio_y_evitar_la_ultima(self):
        rng = random.Random(5)
        current, last = LIBRARY[0], LIBRARY[7]
        for _ in range(100):
            self.assertIs(smart_shuffle(LIBRARY, first=current, rng=rng)[0], current)
            self.assertIsNot(smart_shuffle(LIBRARY, avoid_first=last, rng=rng)[0], last)

    def test_listas_minimas(self):
        self.assertEqual(smart_shuffle([]), [])
        one = LIBRARY[:1]
        self.assertEqual(smart_shuffle(one), one)
        self.assertEqual(smart_shuffle(one, first=one[0]), one)


class PlayHistoryTest(unittest.TestCase):
    def test_guarda_sin_repetir_y_lo_ultimo_al_final(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "history.json")
            history = PlayHistory(path)
            for track in (LIBRARY[0], LIBRARY[1], LIBRARY[0]):
                history.add(track)
            self.assertEqual(PlayHistory(path).recent(), [_path_key(LIBRARY[1]), _path_key(LIBRARY[0])])


if __name__ == "__main__":
    unittest.main()
