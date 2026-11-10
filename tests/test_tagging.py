"""Etiquetas de Spotify escritas en el archivo (WAV generado al vuelo: no hace falta FFmpeg)."""
import importlib.util
import os
import tempfile
import unittest
import wave

from core import tagging
from core.spotify import Track

HAS_MUTAGEN = importlib.util.find_spec("mutagen") is not None

# JPEG mínimo: basta con la cabecera para que se guarde como carátula
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xd9"


@unittest.skipUnless(HAS_MUTAGEN, "mutagen no está instalado")
class WriteTagsTest(unittest.TestCase):
    def test_wav_con_etiquetas_caratula_y_letra(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "prueba.wav")
            with wave.open(path, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(8000)
                w.writeframes(b"\x00\x00" * 8000)
            track = Track("Hooked On A Feeling", "Blue Swede, Björn Skifs", 172, album="Hooked On A Feeling",
                          release_date="1974-04-01", isrc="SEAMA7343050", track_number=1)
            self.assertTrue(tagging.write_tags(path, track, cover=JPEG, lyrics="Letra"))

            from mutagen.wave import WAVE
            tags = WAVE(path).tags
            self.assertEqual(str(tags["TIT2"]), "Hooked On A Feeling")
            self.assertEqual(str(tags["TPE1"]), "Blue Swede, Björn Skifs")  # no "Blue Swede/Björn Skifs"
            self.assertEqual(str(tags["TALB"]), "Hooked On A Feeling")
            self.assertEqual(str(tags["TSRC"]), "SEAMA7343050")
            self.assertEqual(tags.getall("APIC")[0].data, JPEG)
            self.assertEqual(tags.getall("USLT")[0].text, "Letra")
            self.assertEqual(tagging.read_basic(path)[:2], ("Hooked On A Feeling", "Blue Swede, Björn Skifs"))

    def test_formato_no_compatible_no_falla(self):
        self.assertFalse(tagging.write_tags("cancion.webm", Track("x", "y")))


if __name__ == "__main__":
    unittest.main()
