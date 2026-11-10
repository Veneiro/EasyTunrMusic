"""Enlaces de Spotify: reconocimiento y lectura de la página pública (simulada)."""
import json
import unittest
from unittest import mock

from core import spotify_link


def embed_page(entity):
    data = {"props": {"pageProps": {"state": {"data": {"entity": entity}}}}}
    return f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></html>'.encode()


class ParseLinkTest(unittest.TestCase):
    def test_formatos(self):
        pid = "37i9dQZF1DX4UtSsGT1Sbe"
        for text in (f"https://open.spotify.com/playlist/{pid}?si=abc",
                     f"https://open.spotify.com/intl-es/playlist/{pid}",
                     f"https://open.spotify.com/embed/playlist/{pid}",
                     f"spotify:playlist:{pid}"):
            self.assertEqual(spotify_link.parse_link(text), ("playlist", pid), text)
        self.assertEqual(spotify_link.parse_link("spotify:track:4u7EnebtmKWzUH433cf5Qv"),
                         ("track", "4u7EnebtmKWzUH433cf5Qv"))
        self.assertIsNone(spotify_link.parse_link("https://www.youtube.com/watch?v=abc"))


class LoadEmbedTest(unittest.TestCase):
    def test_album(self):
        entity = {
            "type": "album", "name": "The Dark Side of the Moon",
            "visualIdentity": {"image": [{"url": "small", "maxHeight": 64}, {"url": "big", "maxHeight": 640}]},
            "trackList": [
                {"title": "Time", "subtitle": "Pink Floyd", "duration": 413000,
                 "uri": "spotify:track:3TO7bbrUKrOSPGRTB5MeCz"},
                {"title": "Money", "subtitle": "Pink Floyd", "duration": 382000, "uri": "spotify:track:x"},
            ],
        }
        with mock.patch.object(spotify_link.net, "get", return_value=embed_page(entity)):
            collection = spotify_link.load("https://open.spotify.com/album/4LH4d3cOWNNsVw41Gqt2kv")
        self.assertEqual(collection.name, "The Dark Side of the Moon")
        self.assertFalse(collection.truncated)
        first = collection.tracks[0]
        self.assertEqual((first.title, first.artist, first.duration), ("Time", "Pink Floyd", 413))
        self.assertEqual((first.album, first.cover_url, first.track_number), ("The Dark Side of the Moon", "big", 1))
        self.assertEqual(first.spotify_id, "3TO7bbrUKrOSPGRTB5MeCz")

    def test_playlist_de_100_avisa_de_que_puede_faltar(self):
        tracks = [{"title": f"Canción {i}", "subtitle": "Alguien", "duration": 200000} for i in range(100)]
        with mock.patch.object(spotify_link.net, "get", return_value=embed_page({"name": "Larga", "trackList": tracks})):
            collection = spotify_link.load("https://open.spotify.com/playlist/37i9dQZF1DX4UtSsGT1Sbe")
        self.assertTrue(collection.truncated)
        self.assertEqual(len(collection.tracks), 100)

    def test_pagina_cambiada(self):
        with mock.patch.object(spotify_link.net, "get", return_value=b"<html>nada</html>"):
            with self.assertRaises(spotify_link.SpotifyLinkError):
                spotify_link.load("https://open.spotify.com/album/4LH4d3cOWNNsVw41Gqt2kv")


if __name__ == "__main__":
    unittest.main()
