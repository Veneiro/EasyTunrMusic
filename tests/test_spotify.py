"""Emparejamiento de canciones de Spotify con vídeos de YouTube y lectura de CSV."""
import os
import tempfile
import unittest

from core import spotify
from core.spotify import Track, score_candidate


def video(title, channel="", duration=None):
    return {"title": title, "channel": channel, "duration": duration}


class ScoreCandidateTest(unittest.TestCase):
    def accepts(self, track, title, channel="", duration=None):
        self.assertIsNotNone(score_candidate(video(title, channel, duration), track),
                             f"debería aceptar {title!r} para {track.title!r}")

    def rejects(self, track, title, channel="", duration=None):
        self.assertIsNone(score_candidate(video(title, channel, duration), track),
                          f"debería rechazar {title!r} para {track.title!r}")

    def test_otra_cancion_del_mismo_artista(self):
        track = Track("Amor de Verdad", "Bad Bunny", 200)
        self.rejects(track, "Bad Bunny - Tití Me Preguntó", "Bad Bunny", 205)
        self.rejects(track, "Bad Bunny - Amor Prohibido", "Bad Bunny", 198)

    def test_titulo_corto_con_palabras_de_mas(self):
        self.rejects(Track("Amor", "Bad Bunny", 200), "Bad Bunny - Amor Prohibido", "Bad Bunny", 198)

    def test_mismo_titulo_otro_artista(self):
        self.rejects(Track("Hello", "Adele", 295), "Lionel Richie - Hello", "LionelRichieVEVO", 295)

    def test_versiones_distintas(self):
        self.rejects(Track("Alive", "Pearl Jam", 341), "Pearl Jam - Alive (Live at Pinkpop)", "Pearl Jam", 345)
        self.rejects(Track("Hello", "Adele", 295), "Hello - Adele (Cover by John)", "John", 290)
        self.rejects(Track("Diggy Diggy Hole", "Wind Rose", 315), "Diggy Diggy Hole (Orchestral)", "Wind Rose", 317)
        # Se pide el remix: la original no vale
        self.rejects(Track("Despacito - Remix", "Luis Fonsi;Daddy Yankee;Justin Bieber", 228),
                     "Luis Fonsi - Despacito ft. Daddy Yankee", "LuisFonsiVEVO", 230)

    def test_palabras_de_version_por_subcadena(self):
        # "live" dentro de "Oliver" no es un directo
        self.accepts(Track("Oliver", "Some Band", 200), "Some Band - Oliver", "x", 200)
        self.accepts(Track("Piano Man", "Billy Joel", 336), "Billy Joel - Piano Man (Audio)", "Billy Joel", 337)

    def test_duracion_muy_distinta(self):
        self.rejects(Track("Time", "Pink Floyd", 413), "Pink Floyd - Time (Official Music Video)", "Pink Floyd", 500)

    def test_casos_buenos(self):
        self.accepts(Track("Hello", "Adele", 295), "Hello", "Adele - Topic", 296)
        self.accepts(Track("Under Pressure - Remastered 2011", "Queen;David Bowie", 248),
                     "Under Pressure (Remastered 2011)", "This Is Queen", 249)
        self.accepts(Track("Sweet Child O' Mine", "Guns N' Roses", 356),
                     "Guns N' Roses - Sweet Child O' Mine", "Rock", 355)
        self.accepts(Track("Despacito - Remix", "Luis Fonsi;Daddy Yankee;Justin Bieber", 228),
                     "Luis Fonsi, Daddy Yankee - Despacito (Remix) [Lyrics] Ft. Justin Bieber", "Unique", 229)

    def test_el_album_no_cuenta_como_palabras_de_mas(self):
        track = Track("Cuando Perriabas", "Bad Bunny", 190, album="X 100PRE")
        self.accepts(track, "BAD BUNNY - CUANDO PERRIABAS | X100PRE [Visualizer]", "Bad Bunny", 190)

    def test_canal_oficial_y_duracion_exacta_puntuan_mas(self):
        track = Track("Hello", "Adele", 295)
        oficial = score_candidate(video("Hello", "Adele - Topic", 295), track)
        subida = score_candidate(video("Adele - Hello", "Canal cualquiera", 305), track)
        self.assertGreater(oficial, subida)


class SplitTitleTest(unittest.TestCase):
    def test_sufijos_de_spotify(self):
        self.assertEqual(spotify._split_title("Under Pressure - Remastered 2011"), ("Under Pressure", "Remastered 2011"))
        self.assertEqual(spotify._split_title("Starboy (feat. Daft Punk)")[0], "Starboy")
        self.assertEqual(spotify._split_title("Waka Waka (This Time for Africa)"), ("Waka Waka", "This Time for Africa"))


class ReadCsvTest(unittest.TestCase):
    def write(self, text):
        fd, path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        self.addCleanup(os.remove, path)
        return path

    def test_formato_con_columna_song_y_duracion_mm_ss(self):
        # El formato que hacía buscar "1", "2"... (el número de fila) en vez del título
        path = self.write(
            "#,Song,Artist,BPM,Duration,Album,Album Date,Spotify Track Id,ISRC\n"
            '1,"Hooked On A Feeling","Blue Swede,Björn Skifs",118,02:52,"Hooked On A Feeling",'
            "1974-04-01,6Ac4NVYYl2U73QiTt11ZKd,SEAMA7343050\n")
        [track] = spotify.read_csv(path)
        self.assertEqual(track.title, "Hooked On A Feeling")
        self.assertEqual(track.artist, "Blue Swede, Björn Skifs")
        self.assertEqual(track.duration, 172)
        self.assertEqual(track.album, "Hooked On A Feeling")
        self.assertEqual(track.isrc, "SEAMA7343050")
        self.assertEqual(track.spotify_id, "6Ac4NVYYl2U73QiTt11ZKd")

    def test_formato_exportify(self):
        path = self.write(
            "Track URI,Track Name,Artist Name(s),Album Name,Duration (ms)\n"
            "spotify:track:4u7EnebtmKWzUH433cf5Qv,Bohemian Rhapsody - Remastered 2011,Queen,"
            "A Night At The Opera,354320\n")
        [track] = spotify.read_csv(path)
        self.assertEqual((track.title, track.artist), ("Bohemian Rhapsody - Remastered 2011", "Queen"))
        self.assertAlmostEqual(track.duration, 354.32)
        self.assertEqual(track.spotify_id, "4u7EnebtmKWzUH433cf5Qv")

    def test_punto_y_coma_y_columnas_en_espanol(self):
        path = self.write("Canción;Artista;Duración\nLa Canción;J Balvin;4:02\n")
        [track] = spotify.read_csv(path)
        self.assertEqual((track.title, track.artist, track.duration), ("La Canción", "J Balvin", 242))

    def test_sin_columna_de_titulo_no_usa_la_numerica(self):
        path = self.write("#,Nombre raro,Artist\n1,Yellow,Coldplay\n2,Clocks,Coldplay\n")
        self.assertEqual([t.title for t in spotify.read_csv(path)], ["Yellow", "Clocks"])

    def test_duraciones(self):
        parse = spotify._parse_duration
        self.assertEqual(parse("02:52"), 172)
        self.assertEqual(parse("1:02:03"), 3723)
        self.assertEqual(parse("172000"), 172)
        self.assertEqual(parse("172"), 172)
        self.assertIsNone(parse(""))
        self.assertIsNone(parse("abc"))


class DownloadedTest(unittest.TestCase):
    def test_separa_las_canciones_ya_descargadas(self):
        with tempfile.TemporaryDirectory() as folder:
            done, pending = Track("Time", "Pink Floyd"), Track("Money", "Pink Floyd")
            open(os.path.join(folder, spotify.track_basename(done) + ".mp3"), "w").close()
            open(os.path.join(folder, "Money - Pink Floyd.tmp.mp3"), "w").close()  # a medias: no cuenta
            self.assertEqual(spotify.split_downloaded([done, pending], folder), ([pending], [done]))


if __name__ == "__main__":
    unittest.main()
