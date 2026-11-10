import logging
import sys
import time
from logging.handlers import RotatingFileHandler

import flet as ft

from core import paths, tools
from core.config import Config
from ui import theme
from ui.app import EasyTunrApp, setup_window
from ui.i18n import I18n
from ui.uithread import call_ui
from ui.titlebar import TitleBar
from ui.widgets import app_logo


def setup_logging():
    handlers = [RotatingFileHandler(paths.log_file(), maxBytes=1_000_000, backupCount=2, encoding="utf-8")]
    if sys.stderr is not None:  # en la app empaquetada (sin consola) no hay stderr
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
    logging.getLogger("flet").setLevel(logging.WARNING)
    logging.getLogger("flet_desktop").setLevel(logging.WARNING)


def show_setup(page, config, on_ready):
    """Pantalla de primera ejecución: descarga yt-dlp, FFmpeg y Deno si faltan."""
    t = I18n(config.get("language"))
    detail = ft.Text("", size=12, color=ft.Colors.ON_SURFACE_VARIANT)
    bar = ft.ProgressBar(value=None, width=420, bar_height=6, border_radius=3)
    body = ft.Column(
        [
            app_logo(88),
            ft.Text(t("setup_title"), size=22, weight=ft.FontWeight.W_600),
            ft.Text(t("setup_text"), color=ft.Colors.ON_SURFACE_VARIANT),
            bar,
            detail,
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        alignment=ft.MainAxisAlignment.CENTER,
        spacing=16,
    )
    page.add(ft.Column([
        TitleBar(page).build(),
        ft.Container(body, expand=True, alignment=ft.Alignment.CENTER),
    ], expand=True, spacing=0))

    last_paint = [0.0]

    def on_status(name, done, total):
        now = time.monotonic()
        if now - last_paint[0] < 0.15 and done != total:
            return
        last_paint[0] = now
        bar.value = done / total if total else None
        detail.value = t("setup_tool", name, f"{done / 1_048_576:.0f}" + (f" / {total / 1_048_576:.0f}" if total else ""))
        call_ui(page, page.update)

    def worker():
        errors = tools.install_missing(on_status)
        if errors:
            body.controls[2] = ft.Text(t("setup_failed"), color=ft.Colors.ERROR, text_align=ft.TextAlign.CENTER)
            detail.value = "\n".join(errors)
            bar.visible = False
            body.controls.append(ft.FilledButton(content=t("continue"), on_click=lambda e: on_ready()))
            call_ui(page, page.update)
        else:
            call_ui(page, on_ready)

    page.run_thread(worker)


def main(page: ft.Page):
    config = Config()
    setup_window(page)
    theme.apply(page, config)

    def start():
        tools.update_ytdlp_in_background()  # yt-dlp se rompe a menudo cuando YouTube cambia algo
        EasyTunrApp(page, config)

    if tools.missing_tools():
        show_setup(page, config, start)
    else:
        start()


if __name__ == "__main__":
    setup_logging()
    ft.run(main, assets_dir=paths.resource_path("assets"))
