"""Utilidades para lanzar procesos externos sin ventana de consola y poder cancelarlos."""
import os
import subprocess
import threading

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


class Cancelled(Exception):
    """La operación fue cancelada por el usuario."""


class ProcessGroup:
    """Registro de procesos vivos para poder matarlos todos al cancelar."""

    def __init__(self):
        self._lock = threading.Lock()
        self._procs = set()
        self.cancelled = threading.Event()

    def popen(self, cmd, **kwargs):
        if self.cancelled.is_set():
            raise Cancelled()
        kwargs.setdefault("creationflags", CREATE_NO_WINDOW)
        kwargs.setdefault("stdin", subprocess.DEVNULL)
        proc = subprocess.Popen(cmd, **kwargs)
        with self._lock:
            self._procs.add(proc)
        if self.cancelled.is_set():
            kill_tree(proc)
        return proc

    def release(self, proc):
        with self._lock:
            self._procs.discard(proc)

    def run(self, cmd):
        """Como subprocess.run(capture_output=True) pero cancelable."""
        proc = self.popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            out, err = proc.communicate()
        finally:
            self.release(proc)
        if self.cancelled.is_set():
            raise Cancelled()
        return proc.returncode, out or b"", err or b""

    def cancel(self):
        self.cancelled.set()
        with self._lock:
            procs = list(self._procs)
        for proc in procs:
            kill_tree(proc)


def kill_tree(proc):
    """Mata el proceso y sus hijos (yt-dlp.exe lanza un proceso hijo, y este a ffmpeg)."""
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
            capture_output=True, creationflags=CREATE_NO_WINDOW,
        )
    else:
        proc.kill()


def run_quiet(cmd, timeout=None):
    """Ejecuta un comando corto sin ventana y devuelve (código, stdout, stderr) como texto."""
    result = subprocess.run(
        cmd, capture_output=True, timeout=timeout,
        stdin=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW,
    )
    return (
        result.returncode,
        result.stdout.decode("utf-8", errors="replace"),
        result.stderr.decode("utf-8", errors="replace"),
    )
