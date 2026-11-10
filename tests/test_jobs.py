"""Cola de descargas: vídeos alternativos y letra según la duración real del archivo."""
import unittest
from unittest import mock

from core import jobs, ytdlp
from core.jobs import DownloadItem, DownloadJob
from core.settings import DownloadSettings
from core.spotify import Track


class FallbackTest(unittest.TestCase):
    def job(self, item):
        return DownloadJob([item], DownloadSettings(), "out/%(title)s.%(ext)s")

    def test_prueba_el_siguiente_video_si_uno_esta_bloqueado(self):
        item = DownloadItem("https://youtu.be/bloqueado", "Canción",
                            alternatives=["https://youtu.be/bueno", "https://youtu.be/otro"])
        calls = []

        def fake_download(url, *args, **kwargs):
            calls.append(url)
            if url.endswith("bloqueado"):
                raise ytdlp.YtDlpError("Video unavailable. It was blocked due to the claimed content by SME.")
            return "out/Canción.mp3"

        with mock.patch.object(jobs.ytdlp, "download", side_effect=fake_download):
            path = self.job(item)._download_with_fallback(item, None)
        self.assertEqual(path, "out/Canción.mp3")
        self.assertEqual(calls, ["https://youtu.be/bloqueado", "https://youtu.be/bueno"])

    def test_si_fallan_todos_avisa_del_error(self):
        item = DownloadItem("https://youtu.be/a", "Canción", alternatives=["https://youtu.be/b"])
        with mock.patch.object(jobs.ytdlp, "download", side_effect=ytdlp.YtDlpError("no disponible")):
            with self.assertRaises(ytdlp.YtDlpError):
                self.job(item)._download_with_fallback(item, None)


class FinishFileTest(unittest.TestCase):
    def test_la_letra_se_valida_con_la_duracion_del_archivo(self):
        track = Track("Time", "Pink Floyd", 413, album="The Dark Side of the Moon")
        job = DownloadJob([], DownloadSettings(lyrics=True, metadata=False), "")
        with mock.patch.object(jobs.tagging, "read_basic", return_value=("Time", "Pink Floyd", 433.0)), \
                mock.patch.object(jobs.lyrics, "fetch", return_value=(None, "letra")) as fetch, \
                mock.patch.object(jobs.lyrics, "write_lrc") as write_lrc:
            job._finish_file(DownloadItem("x", "Time", track=track), "Time - Pink Floyd.mp3")
        self.assertEqual(fetch.call_args.kwargs["file_duration"], 433.0)
        write_lrc.assert_not_called()


if __name__ == "__main__":
    unittest.main()
