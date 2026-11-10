"""Localiza, descarga y actualiza las herramientas externas: yt-dlp, FFmpeg y Deno.

Orden de búsqueda de cada herramienta:
  1. Carpeta de herramientas del usuario (%LOCALAPPDATA%\\EasyTunrMusic\\bin), escribible.
  2. Carpeta "bin" junto a la app (la que incluye el instalador).
  3. El PATH del sistema (salvo yt-dlp, que tiene que ser el ejecutable oficial
     para poder actualizarse solo con -U).

yt-dlp vive en la carpeta del usuario para poder actualizarse sin permisos de
administrador; si el instalador trae una copia, se usa como semilla.
"""
import logging
import os
import shutil
import tempfile
import threading
import time
import urllib.request
import zipfile

from . import paths
from .process import run_quiet

logger = logging.getLogger(__name__)

YTDLP_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
DENO_URL = "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip"

UPDATE_INTERVAL_SECONDS = 12 * 3600
USER_AGENT = "EasyTunrMusic"

# Se marca cuando yt-dlp está listo (tras comprobar actualizaciones), para no
# lanzar descargas mientras el ejecutable se está sustituyendo.
ytdlp_ready = threading.Event()
ytdlp_ready.set()


class ToolMissingError(RuntimeError):
    pass


# ---------------------------------------------------------------- localizar

def _first_existing(*candidates):
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def ytdlp_exe():
    user_copy = os.path.join(paths.tools_dir(), "yt-dlp.exe")
    if not os.path.isfile(user_copy):
        seed = os.path.join(paths.bundled_bin_dir(), "yt-dlp.exe")
        if os.path.isfile(seed):
            try:
                shutil.copy2(seed, user_copy)
            except OSError:
                logger.exception("No se pudo copiar yt-dlp.exe del instalador")
                return seed
    return user_copy if os.path.isfile(user_copy) else None


def ffmpeg_exe():
    return _first_existing(
        os.path.join(paths.tools_dir(), "ffmpeg.exe"),
        os.path.join(paths.bundled_bin_dir(), "ffmpeg.exe"),
        shutil.which("ffmpeg"),
    )


def deno_exe():
    return _first_existing(
        os.path.join(paths.tools_dir(), "deno.exe"),
        os.path.join(paths.bundled_bin_dir(), "deno.exe"),
        shutil.which("deno"),
    )


def require_ytdlp():
    exe = ytdlp_exe()
    if not exe:
        raise ToolMissingError("yt-dlp no está disponible. Reinicia la app con conexión a Internet.")
    return exe


def require_ffmpeg():
    exe = ffmpeg_exe()
    if not exe:
        raise ToolMissingError("FFmpeg no está disponible. Reinicia la app con conexión a Internet.")
    return exe


def missing_tools():
    """Herramientas que habría que descargar antes de poder usar la app."""
    missing = []
    if not ytdlp_exe():
        missing.append("yt-dlp")
    if not ffmpeg_exe():
        missing.append("ffmpeg")
    if not deno_exe():
        missing.append("deno")
    return missing


# ---------------------------------------------------------------- descargar

def _download(url, dest, on_progress=None):
    """Descarga a un temporal y lo mueve al final, para no dejar archivos a medias."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(dest), suffix=".part")
    try:
        with urllib.request.urlopen(request, timeout=60) as resp, os.fdopen(fd, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if on_progress:
                    on_progress(done, total)
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _extract_from_zip(zip_path, names, dest_dir):
    """Extrae del zip los archivos cuyo nombre base esté en `names` (en cualquier subcarpeta)."""
    found = set()
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            base = os.path.basename(member.filename)
            if base in names and base not in found:
                target = os.path.join(dest_dir, base)
                with zf.open(member) as src, open(target + ".part", "wb") as dst:
                    shutil.copyfileobj(src, dst)
                os.replace(target + ".part", target)
                found.add(base)
    missing = set(names) - found
    if missing:
        raise RuntimeError(f"No se encontró {', '.join(sorted(missing))} en {os.path.basename(zip_path)}")


def install_tool(name, on_progress=None):
    """Descarga una herramienta a la carpeta del usuario."""
    dest_dir = paths.tools_dir()
    if name == "yt-dlp":
        _download(YTDLP_URL, os.path.join(dest_dir, "yt-dlp.exe"), on_progress)
        return
    url, files = {
        "ffmpeg": (FFMPEG_URL, ("ffmpeg.exe", "ffprobe.exe")),
        "deno": (DENO_URL, ("deno.exe",)),
    }[name]
    zip_path = os.path.join(dest_dir, f"{name}.zip")
    try:
        _download(url, zip_path, on_progress)
        _extract_from_zip(zip_path, files, dest_dir)
    finally:
        if os.path.exists(zip_path):
            os.remove(zip_path)


def install_missing(on_status=None):
    """Descarga lo que falte. on_status(tool, done_bytes, total_bytes)."""
    errors = []
    for name in missing_tools():
        logger.info("Descargando %s", name)
        try:
            install_tool(name, lambda done, total, n=name: on_status and on_status(n, done, total))
        except Exception as exc:
            logger.exception("Fallo al descargar %s", name)
            errors.append(f"{name}: {exc}")
    return errors


# ---------------------------------------------------------------- actualizar

def _stamp_file():
    return os.path.join(paths.data_dir(), "ytdlp_last_update")


def ytdlp_version():
    exe = ytdlp_exe()
    if not exe:
        return None
    try:
        code, out, _ = run_quiet([exe, "--version"], timeout=60)
        return out.strip() if code == 0 else None
    except Exception:
        return None


def update_ytdlp(force=False):
    """Ejecuta `yt-dlp -U` como mucho cada 12 h. Devuelve un texto con el resultado."""
    exe = ytdlp_exe()
    if not exe or os.path.dirname(exe) != paths.tools_dir():
        return "yt-dlp no está en la carpeta de usuario; no se actualiza."
    stamp = _stamp_file()
    if not force and os.path.exists(stamp) and time.time() - os.path.getmtime(stamp) < UPDATE_INTERVAL_SECONDS:
        return "yt-dlp comprobado recientemente."

    ytdlp_ready.clear()
    try:
        code, out, err = run_quiet([exe, "-U"], timeout=180)
        message = (out + err).strip().splitlines()
        result = message[-1] if message else f"yt-dlp -U terminó con código {code}"
        if code == 0:
            with open(stamp, "w", encoding="utf-8") as f:
                f.write(result)
        logger.info("Actualización de yt-dlp: %s", result)
        return result
    except Exception as exc:
        logger.exception("No se pudo actualizar yt-dlp")
        return f"No se pudo actualizar yt-dlp: {exc}"
    finally:
        ytdlp_ready.set()


def update_ytdlp_in_background():
    threading.Thread(target=update_ytdlp, name="ytdlp-update", daemon=True).start()
