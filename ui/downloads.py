"""Controlador de descargas y panel de progreso fijo en la parte inferior."""
import logging
import os
import time

import flet as ft

from core.jobs import DownloadJob, JobCallbacks, TITLE_TEMPLATE
from .widgets import MUTED

logger = logging.getLogger(__name__)

UPDATE_INTERVAL = 0.12  # segundos entre refrescos de la barra




class DownloadController:
    def __init__(self, app):
        self.app = app
        self.job = None
        self.preparing = False
        self._on_success = None
        self._after = None
        self._last_paint = 0.0
        self._stage = None
        self._build_panel()

    # ------------------------------------------------------------ estado
    @property
    def busy(self):
        return self.preparing or self.job is not None

    @property
    def t(self):
        return self.app.t

    # ------------------------------------------------------------ panel
    def _build_panel(self):
        self.title = ft.Text("", weight=ft.FontWeight.W_600, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
        self.status = ft.Text("", size=12, color=MUTED, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
        self.counter = ft.Text("", size=13, color=MUTED)
        self.song_bar = ft.ProgressBar(value=None, bar_height=6, border_radius=3)
        self.total_bar = ft.ProgressBar(value=0, bar_height=3, border_radius=2, color=ft.Colors.TERTIARY)
        self.pause_btn = ft.IconButton(icon=ft.Icons.PAUSE, on_click=lambda e: self.toggle_pause())
        self.cancel_btn = ft.IconButton(icon=ft.Icons.CLOSE, on_click=lambda e: self.cancel(),
                                        icon_color=ft.Colors.ERROR)
        self.panel = ft.Container(
            visible=False,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
            border_radius=16,
            padding=ft.Padding(16, 12, 8, 14),
            margin=ft.Margin(24, 0, 24, 16),
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.DOWNLOADING, color=ft.Colors.PRIMARY),
                            ft.Column([self.title, self.status], spacing=0, expand=True),
                            self.counter,
                            self.pause_btn,
                            self.cancel_btn,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    self.song_bar,
                    self.total_bar,
                ],
                spacing=8,
            ),
        )

    def refresh_texts(self):
        self.pause_btn.tooltip = self.t("pause")
        self.cancel_btn.tooltip = self.t("cancel")

    def _paint(self, force=False):
        now = time.monotonic()
        if not force and now - self._last_paint < UPDATE_INTERVAL:
            return
        self._last_paint = now
        try:
            self.panel.update()
        except Exception:
            logger.warning("No se pudo refrescar el panel", exc_info=True)

    def _set_busy(self, busy_before):
        if busy_before != self.busy:
            self.app.on_busy_changed()

    # ------------------------------------------------------------ API
    def start(self, prepare, on_success=None, after=None):
        """prepare() se ejecuta en otro hilo y devuelve la lista de DownloadItem.

        after(items) se ejecuta en el hilo de descarga al terminar (p. ej. para crear la .m3u8)."""
        if self.busy:
            self.app.toast(self.t("busy_downloading"))
            return
        was_busy = self.busy
        self.preparing = True
        self._on_success = on_success
        self._after = after
        self.refresh_texts()
        self.title.value = self.t("preparing")
        self.status.value = ""
        self.counter.value = ""
        self.song_bar.value = None
        self.total_bar.value = 0
        self.pause_btn.icon = ft.Icons.PAUSE
        self.pause_btn.disabled = True
        self.panel.visible = True
        self._set_busy(was_busy)
        self._paint(force=True)
        self.app.page.run_thread(self._prepare, prepare)

    def _prepare(self, prepare):
        """Hilo secundario: resuelve qué descargar (puede consultar YouTube)."""
        try:
            items = prepare()
        except Exception as exc:
            logger.exception("No se pudo preparar la descarga")
            self.app.ui(self._finish_preparing)
            self.app.alert(self.t("error_title"), str(exc), icon=ft.Icons.ERROR_OUTLINE, color=ft.Colors.ERROR)
            return
        self.app.ui(self._start_job, items)

    def _start_job(self, items):
        if not items:
            self._finish_preparing()
            return
        self.preparing = False
        cfg = self.app.config
        self.job = DownloadJob(
            items=items,
            settings=cfg.download_settings(),
            default_outtmpl=os.path.join(cfg.music_folder, TITLE_TEMPLATE),
            workers=cfg.threads,
            after=self._after,
            # Los avisos llegan desde los hilos de descarga: se ejecutan en el bucle de Flet
            callbacks=JobCallbacks(lambda *a: self.app.ui(self._on_progress, *a),
                                   lambda *a: self.app.ui(self._on_item_done, *a),
                                   lambda *a: self.app.ui(self._on_finished, *a)),
        )
        self.counter.value = self.t("progress_items", 0, len(items))
        self.title.value = items[0].label or self.t("preparing")
        self.status.value = self.t("stage_starting")
        self.pause_btn.disabled = False
        self._paint(force=True)
        self.job.start()

    def _finish_preparing(self):
        self.preparing = False
        self.panel.visible = False
        self._paint(force=True)
        self.app.on_busy_changed()

    def toggle_pause(self):
        job = self.job
        if not job:
            return
        if job.is_paused:
            job.resume()
            self.pause_btn.icon = ft.Icons.PAUSE
            self.pause_btn.tooltip = self.t("pause")
        else:
            job.pause()
            self.pause_btn.icon = ft.Icons.PLAY_ARROW
            self.pause_btn.tooltip = self.t("resume")
            self.status.value = self.t("paused")
        self._paint(force=True)

    def cancel(self):
        if self.job:
            self.job.cancel()  # on_finished cierra el panel

    # ------------------------------------------------------------ callbacks (otros hilos)
    def _on_progress(self, percent, stage, label):
        job = self.job
        if not job:
            return
        if label:
            self.title.value = label
        key = f"stage_{stage}"
        self.status.value = self.t(key, percent) if stage == "downloading" else self.t(key)
        if job.is_paused:
            self.status.value = self.t("paused")
        self.song_bar.value = percent / 100
        self.total_bar.value = (job.completed + percent / 100) / max(job.total, 1)
        changed = stage != self._stage
        self._stage = stage
        self._paint(force=changed)

    def _on_item_done(self, done, total):
        self.counter.value = self.t("progress_items", done, total)
        self.total_bar.value = done / max(total, 1)
        self._paint(force=True)

    def _on_finished(self, failed, cancelled):
        job, self.job = self.job, None
        self.app.state.library_stale = True  # hay canciones nuevas en la carpeta
        self.panel.visible = False
        self._paint(force=True)
        self.app.on_busy_changed()
        if cancelled:
            self.app.toast(self.t("cancelled"))
            return
        total = job.total if job else 0
        if not failed:
            if self._on_success:
                self._on_success()
            self.app.alert(self.t("done_title"),
                           self.t("done_text_one") if total == 1 else self.t("done_text", total),
                           icon=ft.Icons.CHECK_CIRCLE, color=ft.Colors.PRIMARY, open_folder=True)
        else:
            lines = "\n".join(f"• {name}: {error}" for name, error in failed)
            self.app.alert(self.t("partial_title"),
                           f"{self.t('partial_text', total - len(failed), total)}\n\n{lines}",
                           icon=ft.Icons.WARNING_AMBER, color=ft.Colors.TERTIARY, open_folder=True)
