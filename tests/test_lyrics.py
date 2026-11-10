"""Letras: búsqueda en LRCLIB (simulada), sincronía con el archivo y lectura de .lrc."""
import unittest
from unittest import mock

from core import lyrics

SYNCED = "[00:01.00]Hola\n[00:05.50]Adiós"


def lrclib_result(duration, synced=SYNCED, plain="Hola\nAdiós", name="Time"):
    return {"trackName": name, "duration": duration, "syncedLyrics": synced, "plainLyrics": plain,
            "instrumental": False}


class FetchTest(unittest.TestCase):
    def fetch(self, results, **kwargs):
        with mock.patch.object(lyrics.net, "get_json", return_value=results):
            return lyrics.fetch("Time", "Pink Floyd", **kwargs)

    def test_letra_sincronizada_cuando_el_archivo_dura_lo_mismo(self):
        self.assertEqual(self.fetch([lrclib_result(413)], duration=413, file_duration=414),
                         (SYNCED, "Hola\nAdiós"))

    def test_solo_letra_sin_tiempos_si_el_archivo_dura_distinto(self):
        # Videoclip con 20 s de intro: la letra sincronizada quedaría desfasada
        synced, plain = self.fetch([lrclib_result(413)], duration=413, file_duration=433)
        self.assertIsNone(synced)
        self.assertEqual(plain, "Hola\nAdiós")

    def test_descarta_letras_de_otra_version(self):
        self.assertEqual(self.fetch([lrclib_result(520)], duration=413), (None, None))

    def test_prefiere_la_sincronizada(self):
        results = [lrclib_result(413, synced=None), lrclib_result(414)]
        self.assertEqual(self.fetch(results, duration=413)[0], SYNCED)

    def test_sin_conexion_no_falla(self):
        with mock.patch.object(lyrics.net, "get_json", side_effect=OSError("sin red")):
            self.assertEqual(lyrics.fetch("Time", "Pink Floyd", duration=413), (None, None))


class LrcTest(unittest.TestCase):
    def test_parse_lrc(self):
        self.assertEqual(lyrics.parse_lrc("[00:01.50]Hola\n[01:02.3][02:00.00]Estribillo\n[ar:Alguien]\n"),
                         [(1.5, "Hola"), (62.3, "Estribillo"), (120.0, "Estribillo")])

    def test_titulo_de_video(self):
        self.assertEqual(lyrics.guess_from_video_title("Pink Floyd - Time (Official Audio)"), ("Time", "Pink Floyd"))
        self.assertEqual(lyrics.guess_from_video_title("Hello", "Adele - Topic"), ("Hello", "Adele"))


if __name__ == "__main__":
    unittest.main()
