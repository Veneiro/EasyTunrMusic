"""Envoltorio del ejecutable yt-dlp.exe.

Se usa el ejecutable oficial (y no la librería de Python) para que pueda
actualizarse solo con `yt-dlp -U` aunque la app esté empaquetada.
"""
import json
import logging
import os
import re
import subprocess
import tempfile
import threading

from . import tools
from .process import ProcessGroup, Cancelled, run_quiet

logger = logging.getLogger(__name__)

PROGRESS_PREFIX = "ETM|"
PROGRESS_TEMPLATE = (
    "download:" + PROGRESS_PREFIX +
    "%(progress.status)s|%(progress.downloaded_bytes)s|"
    "%(progress.total_bytes)s|%(progress.total_bytes_estimate)s|%(progress._percent_str)s"
)


class YtDlpError(RuntimeError):
    pass


def _base_cmd():
    """Argumentos comunes: salida UTF-8, sin configs ajenas y con FFmpeg/Deno localizados."""
    tools.ytdlp_ready.wait(timeout=180)
    cmd = [tools.require_ytdlp(), "--ignore-config", "--encoding", "utf-8", "--no-colors"]
    ffmpeg = tools.ffmpeg_exe()
    if ffmpeg:
        cmd += ["--ffmpeg-location", os.path.dirname(ffmpeg)]
    deno = tools.deno_exe()
    if deno:
        cmd += ["--js-runtimes", f"deno:{deno}"]
    return cmd


def _error_text(stderr_text, returncode):
    lines = [l.strip() for l in stderr_text.splitlines() if l.strip()]
    errors = [l for l in lines if l.startswith("ERROR")]
    if errors:
        return errors[-1].removeprefix("ERROR:").strip()
    if lines:
        return lines[-1]
    return f"yt-dlp terminó con código {returncode}"


# ------------------------------------------------------------------ información

def extract_info(url, flat=True, timeout=300):
    """Metadatos de una URL o búsqueda (`ytsearch10:...`) sin descargar."""
    cmd = _base_cmd() + ["-J", "--no-warnings"]
    if flat:
        cmd.append("--flat-playlist")
    cmd += ["--", url]
    code, out, err = run_quiet(cmd, timeout=timeout)
    if code != 0 or not out.strip():
        raise YtDlpError(_error_text(err, code))
    return json.loads(out)


def search(query, limit=10):
    """Lista de entradas (dict) de una búsqueda en YouTube."""
    info = extract_info(f"ytsearch{limit}:{query}")
    return info.get("entries") or []


def entry_url(entry):
    url = entry.get("webpage_url") or entry.get("url") or ""
    if url and not re.match(r"https?://", url):
        url = f"https://www.youtube.com/watch?v={url}"
    return url


def is_playlist_entry(entry):
    url = entry.get("url") or entry.get("webpage_url") or ""
    return (entry.get("ie_key") or "").lower() == "youtubeplaylist" or "playlist?list=" in url


def resolve_playlist(url):
    """Devuelve (título, [urls de los vídeos])."""
    info = extract_info(url, flat=True)
    entries = info.get("entries") or []
    urls = [entry_url(e) for e in entries if e and (e.get("url") or e.get("webpage_url"))]
    return info.get("title") or "", urls


# ------------------------------------------------------------------ descarga

def build_download_args(settings, outtmpl):
    args = ["-f", "bestaudio/best", "-o", outtmpl, "--no-playlist"]
    if settings.extract_audio:
        args += ["-x", "--audio-format", settings.codec]
        if settings.is_lossy:
            args += ["--audio-quality", f"{settings.bitrate}K"]
        if settings.metadata:
            args.append("--embed-metadata")
            if settings.codec != "wav":  # WAV no admite carátula incrustada
                args.append("--embed-thumbnail")
        if settings.extract_thumbnail:
            args.append("--write-thumbnail")
    if settings.keep_original:
        args.append("-k")
    return args


def _parse_progress(line):
    """Devuelve (estado, porcentaje|None) de una línea de progreso, o None."""
    if not line.startswith(PROGRESS_PREFIX):
        return None
    parts = line[len(PROGRESS_PREFIX):].split("|")
    if len(parts) < 5:
        return None
    status, downloaded, total, estimate, percent_str = parts[:5]

    def num(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    done, size = num(downloaded), num(total) or num(estimate)
    percent = None
    if done is not None and size:
        percent = done / size * 100.0
    else:
        cleaned = re.sub(r"[^0-9.,]", "", percent_str).replace(",", ".")
        percent = num(cleaned)
    if percent is not None:
        percent = max(0.0, min(100.0, percent))
    return status, percent


def download(url, outtmpl, settings, group: ProcessGroup, on_progress=None):
    """Descarga una URL. on_progress(estado, porcentaje). Devuelve la ruta final o None."""
    fd, paths_file = tempfile.mkstemp(prefix="etm_", suffix=".txt")
    os.close(fd)
    cmd = _base_cmd() + build_download_args(settings, outtmpl) + [
        "--newline", "--quiet", "--progress", "--progress-delta", "0.25",
        "--progress-template", PROGRESS_TEMPLATE,
        "--print-to-file", "after_move:filepath", paths_file,
        "--", url,
    ]
    stderr_lines = []
    proc = group.popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def drain_stderr():
        for raw in proc.stderr:
            stderr_lines.append(raw.decode("utf-8", errors="replace"))

    reader = threading.Thread(target=drain_stderr, daemon=True)
    reader.start()
    try:
        for raw in proc.stdout:
            parsed = _parse_progress(raw.decode("utf-8", errors="replace").strip())
            if parsed and on_progress:
                on_progress(*parsed)
        proc.wait()
        reader.join(timeout=5)
        if group.cancelled.is_set():
            raise Cancelled()
        if proc.returncode != 0:
            raise YtDlpError(_error_text("".join(stderr_lines), proc.returncode))
        with open(paths_file, encoding="utf-8", errors="replace") as f:
            final = [l.strip() for l in f if l.strip()]
        return final[-1] if final else None
    finally:
        group.release(proc)
        try:
            os.remove(paths_file)
        except OSError:
            pass
