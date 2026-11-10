"""Duplicados, listas .m3u8 y carpeta de música."""
import os
import tempfile
import unittest
from unittest import mock

from core import paths
from core.library import Track, find_duplicates, write_m3u


def T(path, title, artist, duration):
    return Track(path=path, title=title, artist=artist, duration=duration)


class DuplicatesTest(unittest.TestCase):
    def setUp(self):
        self.tracks = [
            T(r"M\Time - Pink Floyd.mp3", "Time", "Pink Floyd", 426),
            T(r"M\yt\Pink Floyd – Time (Official Audio).mp3", "Pink Floyd – Time (Official Audio)", "Pink Floyd", 425),
            T(r"M\Time (Live).mp3", "Time (Live)", "Pink Floyd", 426),
            T(r"M\Hello - Adele.mp3", "Hello", "Adele", 295),
            T(r"M\Hello - Lionel Richie.mp3", "Hello", "Lionel Richie", 295),
            T(r"M\Bohemian Rhapsody - Remastered 2011 - Queen.mp3", "Bohemian Rhapsody - Remastered 2011", "Queen", 354),
            T(r"M\x\Queen - Bohemian Rhapsody (Official Video).mp3", "Queen - Bohemian Rhapsody (Official Video)",
              "Queen Official", 355),
            T(r"M\x\Bohemian Rhapsody (cover).mp3", "Bohemian Rhapsody (Cover)", "Some Guy", 354),
        ]

    def groups(self):
        return [sorted(os.path.basename(t.path) for t in g) for g in find_duplicates(self.tracks)]

    def test_encuentra_la_misma_cancion_con_distinto_titulo(self):
        groups = self.groups()
        self.assertIn(["Pink Floyd – Time (Official Audio).mp3", "Time - Pink Floyd.mp3"], groups)
        self.assertIn(["Bohemian Rhapsody - Remastered 2011 - Queen.mp3",
                       "Queen - Bohemian Rhapsody (Official Video).mp3"], groups)

    def test_no_mezcla_directos_covers_ni_otros_artistas(self):
        self.assertEqual(len(self.groups()), 2)


class M3uTest(unittest.TestCase):
    def test_rutas_relativas_y_orden(self):
        with tempfile.TemporaryDirectory() as folder:
            sub = os.path.join(folder, "Lista")
            files = [os.path.join(sub, "B.mp3"), os.path.join(sub, "A.mp3")]
            playlist = write_m3u(os.path.join(sub, "Lista.m3u8"), files)
            with open(playlist, encoding="utf-8") as f:
                self.assertEqual(f.read().splitlines(), ["#EXTM3U", "B.mp3", "A.mp3"])


class MusicFolderTest(unittest.TestCase):
    def test_carpetas_protegidas_o_de_la_instalacion(self):
        with mock.patch.object(paths, "IS_FROZEN", True), \
                mock.patch.object(paths, "install_dir", lambda: r"C:\Program Files\EasyTunrMusic"):
            self.assertFalse(paths.is_usable_music_folder(r"C:\Program Files\EasyTunrMusic\_internal\Música"))
            self.assertFalse(paths.is_usable_music_folder(os.path.join(
                os.environ.get("ProgramFiles", r"C:\Program Files"), "Otra")))

    def test_carpeta_normal_y_disco_desconectado(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertTrue(paths.is_usable_music_folder(os.path.join(folder, "Música")))
        # Una unidad que no existe se respeta (disco externo desconectado)
        missing = next((f"{d}:\\" for d in "QXYZ" if not os.path.exists(f"{d}:\\")), None)
        if missing:
            self.assertTrue(paths.is_usable_music_folder(missing + "Musica"))


if __name__ == "__main__":
    unittest.main()
