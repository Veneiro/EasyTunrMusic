"""Cola de descargas: vídeos alternativos si uno no se puede descargar."""
import unittest
from unittest import mock

from core import jobs, ytdlp
from core.jobs import DownloadItem, DownloadJob
from core.settings import DownloadSettings


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


if __name__ == "__main__":
    unittest.main()
