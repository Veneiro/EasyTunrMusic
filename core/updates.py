"""Actualizaciones de la app a partir de las releases de GitHub.

Flujo: check() consulta la última release; si es más nueva que la versión
actual, download_installer() baja su instalador (EasyTunrMusic-Setup-X.Y.Z.exe)
y launch_installer() lo ejecuta en modo silencioso. El instalador tiene el
mismo AppId, así que actualiza la instalación existente y vuelve a abrir la app.
"""
import hashlib
import json
import logging
import os
import re
import subprocess
import urllib.request
from dataclasses import dataclass
from typing import Optional

from . import __version__, paths
from .tools import download_file, USER_AGENT

logger = logging.getLogger(__name__)

REPO = "Veneiro/EasyTunrMusic"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
# Se puede sobrescribir para probar el actualizador con una release falsa
API_URL = os.environ.get("ETM_UPDATE_API", f"https://api.github.com/repos/{REPO}/releases/latest")
INSTALLER_RE = re.compile(r"^EasyTunrMusic-Setup-[\w.\-]+\.exe$", re.I)

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200


@dataclass
class UpdateInfo:
    version: str
    notes: str
    page_url: str
    asset_name: str
    asset_url: str
    size: int
    sha256: Optional[str]


class UpdateError(RuntimeError):
    pass


def parse_version(text):
    """'v2.10.1' -> (2, 10, 1). Lo que no sea número se ignora."""
    numbers = re.findall(r"\d+", (text or "").split("-")[0])
    return tuple(int(n) for n in numbers[:3]) + (0,) * (3 - len(numbers[:3]))


def is_newer(candidate, current=__version__):
    return parse_version(candidate) > parse_version(current)


def check(current=__version__, timeout=10):
    """Devuelve UpdateInfo si hay una versión más nueva con instalador, o None."""
    request = urllib.request.Request(API_URL, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        release = json.load(resp)
    if release.get("draft") or release.get("prerelease"):
        return None
    tag = release.get("tag_name") or ""
    if not is_newer(tag, current):
        return None
    asset = next((a for a in release.get("assets") or [] if INSTALLER_RE.match(a.get("name") or "")), None)
    if not asset:
        logger.info("La release %s no tiene instalador; se ignora", tag)
        return None
    digest = asset.get("digest") or ""
    return UpdateInfo(
        version=tag.lstrip("vV"),
        notes=(release.get("body") or "").strip(),
        page_url=release.get("html_url") or RELEASES_PAGE,
        asset_name=asset["name"],
        asset_url=asset["browser_download_url"],
        size=int(asset.get("size") or 0),
        sha256=digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else None,
    )


def can_self_update():
    """Solo la app instalada con el instalador puede actualizarse sola."""
    return paths.IS_FROZEN and os.path.isfile(os.path.join(paths.install_dir(), "unins000.exe"))


def download_installer(info, on_progress=None):
    folder = os.path.join(paths.data_dir(), "updates")
    os.makedirs(folder, exist_ok=True)
    for old in os.listdir(folder):  # instaladores de actualizaciones anteriores
        try:
            os.remove(os.path.join(folder, old))
        except OSError:
            pass
    target = os.path.join(folder, info.asset_name)
    download_file(info.asset_url, target, on_progress)
    if info.sha256:
        digest = hashlib.sha256()
        with open(target, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest().lower() != info.sha256:
            os.remove(target)
            raise UpdateError("El instalador descargado no coincide con el publicado (SHA-256). Inténtalo de nuevo.")
    return target


def _installed_for_all_users():
    """Si la app está en Program Files hay que actualizar en modo 'todos los usuarios'."""
    install = os.path.normcase(paths.install_dir())
    roots = [os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramW6432")]
    return any(r and install.startswith(os.path.normcase(r) + os.sep) for r in roots)


def launch_installer(installer_path):
    """Ejecuta el instalador sin asistente; al terminar vuelve a abrir la app."""
    args = [installer_path, "/SILENT", "/SP-", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/UPDATE=1",
            "/ALLUSERS" if _installed_for_all_users() else "/CURRENTUSER"]
    logger.info("Lanzando actualización: %s", args)
    subprocess.Popen(args, close_fds=True, creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP)
