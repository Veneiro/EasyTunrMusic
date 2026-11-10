"""Rutas de la aplicación, válidas tanto desde el código fuente como empaquetada."""
import os
import sys
import tempfile

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


def _is_inside(path, parent):
    try:
        return os.path.commonpath([os.path.normcase(path), os.path.normcase(parent)]) == os.path.normcase(parent)
    except ValueError:  # unidades distintas
        return False


def _is_writable_dir(path):
    """Comprueba de verdad que se puede escribir (os.access no es fiable en Windows)."""
    try:
        os.makedirs(path, exist_ok=True)
        fd, probe = tempfile.mkstemp(prefix=".etm_", dir=path)
        os.close(fd)
        os.remove(probe)
        return True
    except OSError:
        return False


def is_usable_music_folder(path):
    """False si la carpeta está dentro de la instalación o de Program Files, o no es escribible."""
    path = os.path.abspath(os.path.expandvars(os.path.expanduser(path)))
    protected = []
    if IS_FROZEN:
        protected.append(install_dir())
    protected += [os.environ.get(v) for v in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432")]
    if any(p and _is_inside(path, os.path.abspath(p)) for p in protected):
        return False
    drive = os.path.splitdrive(path)[0]
    if not os.path.isdir(path) and drive and not os.path.isdir(drive + os.sep):
        return True  # unidad externa desconectada: se respeta la elección del usuario
    return _is_writable_dir(path)


def default_music_folder():
    """Instalada: Música del usuario. Desde el código: carpeta 'Música' del proyecto."""
    if IS_FROZEN:
        return os.path.join(os.path.expanduser("~"), "Music", APP_NAME)
    return os.path.join(install_dir(), "Música")
