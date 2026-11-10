import ctypes
import logging
import os
import sys
import threading
import tkinter as tk
from logging.handlers import RotatingFileHandler
from tkinter import ttk as tkttk

from core import paths, tools


def setup_logging():
    handlers = [RotatingFileHandler(paths.log_file(), maxBytes=1_000_000, backupCount=2, encoding="utf-8")]
    if sys.stderr is not None:  # en la app empaquetada (sin consola) no hay stderr
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")


def prepare_tools(root):
    """Si falta yt-dlp, FFmpeg o Deno, los descarga mostrando una ventana de progreso.

    Devuelve la lista de errores (vacía si todo fue bien).
    """
    if not tools.missing_tools():
        return []

    root.title("EasyTunrMusic")
    root.geometry("420x130")
    root.resizable(False, False)
    frame = tk.Frame(root, padx=20, pady=20)
    frame.pack(fill="both", expand=True)
    label = tk.Label(frame, text="Preparando componentes (solo la primera vez)...", font=("Segoe UI", 10))
    label.pack(anchor="w")
    bar = tkttk.Progressbar(frame, length=380, mode="determinate", maximum=100)
    bar.pack(pady=10)
    detail = tk.Label(frame, text="", font=("Segoe UI", 9), fg="#666")
    detail.pack(anchor="w")

    result = {}

    def on_status(name, done, total):
        def update():
            mb = done / 1_048_576
            if total:
                bar.configure(mode="determinate", value=done / total * 100)
                detail.config(text=f"Descargando {name}: {mb:.0f} / {total / 1_048_576:.0f} MB")
            else:
                detail.config(text=f"Descargando {name}: {mb:.0f} MB")
        root.after(0, update)

    def worker():
        result["errors"] = tools.install_missing(on_status)
        root.after(0, root.quit)

    threading.Thread(target=worker, daemon=True).start()
    root.mainloop()
    frame.destroy()
    return result.get("errors", [])


def main():
    setup_logging()
    if os.name == "nt":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("EasyTunrMusic")

    root = tk.Tk()
    root.iconbitmap(paths.resource_path("icon.ico"))

    errors = prepare_tools(root)
    if errors:
        from tkinter import messagebox
        messagebox.showwarning(
            "EasyTunrMusic",
            "No se pudieron descargar algunos componentes:\n\n" + "\n".join(errors) +
            "\n\nRevisa tu conexión y vuelve a abrir la app.",
        )

    # yt-dlp se rompe a menudo cuando YouTube cambia algo: se actualiza solo
    tools.update_ytdlp_in_background()

    from downloader_app import DownloaderApp  # después de preparar las herramientas
    DownloaderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
