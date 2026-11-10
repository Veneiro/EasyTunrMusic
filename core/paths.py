"""Rutas de la aplicación, válidas tanto desde el código fuente como empaquetada."""
import os
import sys

APP_NAME = "EasyTunrMusic"
IS_FROZEN = bool(getattr(sys, "frozen", False))


def install_dir():
    """Carpeta donde está instalada la app (la del .exe, o la raíz del proyecto)."""
    if IS_FROZEN:
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_path(*parts):
    """Ruta a un recurso empaquetado (icono, etc.)."""
    base = getattr(sys, "_MEIPASS", install_dir())
    return os.path.join(base, *parts)


def bundled_bin_dir():
    """Herramientas incluidas por el instalador (solo lectura)."""
    return os.path.join(install_dir(), "bin")


def data_dir():
    """Datos de usuario escribibles: %LOCALAPPDATA%\\EasyTunrMusic."""
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def tools_dir():
    """Herramientas que la app descarga y actualiza (yt-dlp, ffmpeg, deno)."""
    path = os.path.join(data_dir(), "bin")
    os.makedirs(path, exist_ok=True)
    return path


def config_dir():
    """Se mantiene la carpeta histórica para no perder la configuración existente."""
    path = os.path.join(os.path.expanduser("~"), ".easytunrmusic")
    os.makedirs(path, exist_ok=True)
    return path


def log_file():
    return os.path.join(data_dir(), "easytunrmusic.log")


def default_music_folder():
    """Instalada: Música del usuario. Desde el código: carpeta 'Música' del proyecto."""
    if IS_FROZEN:
        return os.path.join(os.path.expanduser("~"), "Music", APP_NAME)
    return os.path.join(install_dir(), "Música")
