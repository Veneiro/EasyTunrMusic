"""Configuración persistente (~/.easytunrmusic/config.json), compatible con versiones anteriores."""
import json
import logging
import os
from dataclasses import fields

from . import paths
from .settings import DownloadSettings

logger = logging.getLogger(__name__)

DEFAULTS = {
    "language": "es",
    "theme_mode": "system",      # system | light | dark
    "accent": "orange",
    "threads": "4",
    "check_updates": True,
    "volume": 0.8,
    "music_folder": None,        # None -> paths.default_music_folder()
    "codec": "mp3",
    "bitrate": "192",
    "bit_depth": "16",
    "sample_rate": "44100",
    "channels": "stereo",
    "normalization": "off",
    "custom_lufs_i": "-14",
    "custom_lufs_lra": "11",
    "custom_lufs_tp": "-1.5",
    "extract_audio": True,
    "metadata": True,
    "extract_thumbnail": False,
    "keep_original": False,
    "dynamic_compression": False,
}

AUDIO_KEYS = [f.name for f in fields(DownloadSettings)]
GENERAL_KEYS = ["language", "theme_mode", "accent", "threads", "music_folder", "check_updates"]

_LEGACY_LANGUAGES = {"Español": "es", "Spanish": "es", "English": "en", "Inglés": "en"}


class Config:
    def __init__(self, path=None):
        self.path = path or os.path.join(paths.config_dir(), "config.json")
        self.data = dict(DEFAULTS)
        self.load()

    def load(self):
        try:
            if os.path.exists(self.path):
                with open(self.path, encoding="utf-8") as f:
                    stored = json.load(f)
                if isinstance(stored, dict):
                    self.data.update(stored)
        except Exception:
            logger.exception("No se pudo leer la configuración; se usan valores por defecto")
        self._migrate()

    def _migrate(self):
        lang = self.data.get("language")
        self.data["language"] = _LEGACY_LANGUAGES.get(lang, lang if lang in ("es", "en") else "es")
        # La versión tkinter guardaba un tema de ttkbootstrap ("litera", "darkly", ...)
        if "theme" in self.data and "theme_mode" not in self._stored_keys():
            self.data["theme_mode"] = "dark" if self.data.get("theme") == "darkly" else "system"
        for key in ("threads", "bitrate", "bit_depth", "sample_rate"):
            self.data[key] = str(self.data.get(key) or DEFAULTS[key])
        # Las versiones antiguas guardaban la carpeta "Música" junto al programa, que
        # instalado queda en Program Files y no se puede escribir sin ser administrador.
        folder = self.data.get("music_folder")
        if folder and not paths.is_usable_music_folder(folder):
            logger.warning("Carpeta de música no válida (%s); se usa %s", folder, paths.default_music_folder())
            self.data["music_folder"] = None
            if "music_folder" in self._stored_keys():
                self.save()

    def _stored_keys(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()

    def save(self):
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
            os.replace(tmp, self.path)
        except Exception:
            logger.exception("No se pudo guardar la configuración")

    def get(self, key):
        return self.data.get(key, DEFAULTS.get(key))

    def set(self, key, value):
        if self.data.get(key) != value:
            self.data[key] = value
            self.save()

    def reset(self, keys):
        for key in keys:
            self.data[key] = DEFAULTS[key]
        self.save()

    @property
    def music_folder(self):
        return self.data.get("music_folder") or paths.default_music_folder()

    def download_settings(self):
        return DownloadSettings(**{k: self.get(k) for k in AUDIO_KEYS})

    @property
    def threads(self):
        try:
            return max(1, min(int(self.get("threads")), 8))
        except (TypeError, ValueError):
            return 4
