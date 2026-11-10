"""Aviso de nueva versión y actualización desde la propia app."""
import logging
import time
import webbrowser

import flet as ft

from core import __version__, updates
from .widgets import MUTED

logger = logging.getLogger(__name__)


class Updater:
    def __init__(self, app):
        self.app = app
        self.checking = False
        self.dialog = None

    @property
    def t(self):
        return self.app.t

    # ---------------------------------------------------------- comprobar
    def check_in_background(self, manual=False):
        if self.checking:
            return
        self.checking = True
        self.app.page.run_thread(self._check, manual)

    def _check(self, manual):
        try:
            info = updates.check()
        except Exception:
            logger.warning("No se pudo comprobar si hay actualizaciones", exc_info=True)
            if manual:
                self.app.toast(self.t("update_check_failed"))
            return
        finally:
            self.checking = False
        if info:
            logger.info("Nueva versión disponible: %s", info.version)
            self.app.ui(self._show_offer, info)
        elif manual:
            self.app.toast(self.t("up_to_date", __version__))

    # ---------------------------------------------------------- diálogo
    def _show_offer(self, info):
        t = self.t
        notes = info.notes or t("update_no_notes")
        can_install = updates.can_self_update()
        self.status = ft.Text(t("update_current", __version__), color=MUTED)
        self.progress = ft.ProgressBar(value=0, visible=False, bar_height=6, border_radius=3)
        self.later_btn = ft.TextButton(content=t("later"), on_click=lambda e: self._close())
        self.go_btn = ft.FilledButton(
            content=t("update_now") if can_install else t("update_open_page"),
            icon=ft.Icons.SYSTEM_UPDATE_ALT if can_install else ft.Icons.OPEN_IN_NEW,
            on_click=lambda e: self._start(info),
        )
        self.dialog = ft.AlertDialog(
            modal=True,
            icon=ft.Icon(ft.Icons.NEW_RELEASES, color=ft.Colors.PRIMARY, size=40),
            title=ft.Text(t("update_title", info.version), text_align=ft.TextAlign.CENTER),
            content=ft.Container(
                ft.Column([
                    self.status,
                    # El Markdown ya se desplaza solo: necesita una altura fija y no
                    # puede ir dentro de otra columna con scroll (Flutter no lo dibuja)
                    ft.Container(
                        ft.Markdown(notes, selectable=True,
                                    extension_set=ft.MarkdownExtensionSet.GITHUB_FLAVORED),
                        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, border_radius=12,
                        padding=14, height=200,
                    ),
                    self.progress,
                ], spacing=12, tight=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                width=480,
            ),
            actions=[self.later_btn, self.go_btn],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.app.page.show_dialog(self.dialog)

    def _close(self):
        self.app.page.pop_dialog()
        self.dialog = None

    # ---------------------------------------------------------- actualizar
    def _start(self, info):
        if not updates.can_self_update():
            webbrowser.open(info.page_url)
            self._close()
            return
        if self.app.downloads.busy:
            self.app.toast(self.t("update_wait_downloads"))
            return
        self.later_btn.disabled = True
        self.go_btn.disabled = True
        self.progress.visible = True
        self.status.value = self.t("update_downloading", "0")
        self.dialog.update()
        self.app.page.run_thread(self._download, info)

    def _download(self, info):
        last = [0.0]

        def on_progress(done, total):
            now = time.monotonic()
            if now - last[0] < 0.15 and done != total:
                return
            last[0] = now
            mb = f"{done / 1_048_576:.0f} / {total / 1_048_576:.0f} MB" if total else f"{done / 1_048_576:.0f} MB"
            self.app.ui(self._set_progress, done / total if total else None, self.t("update_downloading", mb))

        try:
            path = updates.download_installer(info, on_progress)
        except Exception as exc:
            logger.exception("Fallo al descargar la actualización")
            self.app.ui(self._failed, str(exc))
            return
        self.app.ui(self._install, path)

    def _set_progress(self, value, text):
        if not self.dialog:
            return
        self.progress.value = value
        self.status.value = text
        self.dialog.update()

    def _failed(self, message):
        if not self.dialog:
            return
        self.progress.visible = False
        self.status.value = self.t("update_failed", message)
        self.status.color = ft.Colors.ERROR
        self.later_btn.disabled = False
        self.go_btn.disabled = False
        self.dialog.update()

    def _install(self, path):
        self._set_progress(None, self.t("update_installing"))
        try:
            updates.launch_installer(path)
        except Exception as exc:
            logger.exception("No se pudo lanzar el instalador")
            self._failed(str(exc))
            return
        # El instalador espera a que la app se cierre y la vuelve a abrir al terminar
        self.app.page.run_task(self.app.page.window.destroy)
