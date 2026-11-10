"""Mini reproductor fijo en la parte inferior (usa flet-audio)."""
import logging
import os
import time

import flet as ft
import flet_audio as fa

from core import library
from .widgets import MUTED, fmt_duration

logger = logging.getLogger(__name__)

POSITION_PAINT_INTERVAL = 0.25


class Player:
    def __init__(self, app):
        self.app = app
        self.queue = []
        self.index = -1
        self.state = "stopped"     # stopped | loading | playing | paused
        self.duration_ms = 0
        self.position_ms = 0
        self._token = 0            # invalida cargas antiguas al cambiar de canción rápido
        self._dragging = False
        self._last_paint = 0.0
        # Un único reproductor que se reutiliza cambiando `src`
        self.audio = fa.Audio(
            src="", autoplay=False, volume=float(app.config.get("volume") or 0.8),
            release_mode=fa.ReleaseMode.STOP,
            on_duration_change=self._on_duration, on_position_change=self._on_position,
            on_state_change=self._on_state,
        )
        self._build()

    @property
    def t(self):
        return self.app.t

    @property
    def current(self):
        return self.queue[self.index] if 0 <= self.index < len(self.queue) else None

    # ---------------------------------------------------------- interfaz
    def _build(self):
        self.cover = ft.Container(width=48, height=48, border_radius=10, bgcolor=ft.Colors.SECONDARY_CONTAINER,
                                  alignment=ft.Alignment.CENTER, clip_behavior=ft.ClipBehavior.ANTI_ALIAS)
        self.title = ft.Text("", weight=ft.FontWeight.W_600, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
        self.artist = ft.Text("", size=12, color=MUTED, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
        self.play_btn = ft.IconButton(icon=ft.Icons.PLAY_ARROW_ROUNDED, icon_size=30,
                                      style=ft.ButtonStyle(bgcolor=ft.Colors.PRIMARY, color=ft.Colors.ON_PRIMARY),
                                      on_click=lambda e: self.toggle())
        self.spinner = ft.ProgressRing(width=26, height=26, stroke_width=3)
        # Capa del indicador de carga sobre el botón: oculta del todo cuando no carga,
        # porque si no se queda encima y se come los clics del botón
        self.spinner_layer = ft.Container(self.spinner, alignment=ft.Alignment.CENTER,
                                          width=48, height=48, visible=False)
        self.elapsed = ft.Text("0:00", size=12, color=MUTED, width=44, text_align=ft.TextAlign.RIGHT)
        self.total = ft.Text("0:00", size=12, color=MUTED, width=44)
        self.seek = ft.Slider(min=0, max=1, value=0, expand=True, on_change_start=self._seek_start,
                              on_change=self._seek_move, on_change_end=self._seek_end)
        self.volume = ft.Slider(min=0, max=1, value=self.audio.volume, width=110, on_change=self._volume_changed,
                                on_change_end=lambda e: self.app.config.set("volume", round(e.control.value, 2)))
        self.bar = ft.Container(
            visible=False,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
            border_radius=16,
            padding=ft.Padding(12, 8, 12, 8),
            margin=ft.Margin(24, 0, 24, 16),
            content=ft.Row([
                self.cover,
                ft.Column([self.title, self.artist], spacing=0, width=220),
                ft.Column([
                    ft.Row([
                        ft.IconButton(icon=ft.Icons.SKIP_PREVIOUS_ROUNDED, on_click=lambda e: self.previous()),
                        ft.Stack([self.play_btn, self.spinner_layer], width=48, height=48),
                        ft.IconButton(icon=ft.Icons.SKIP_NEXT_ROUNDED, on_click=lambda e: self.next()),
                    ], alignment=ft.MainAxisAlignment.CENTER, spacing=4),
                    ft.Row([self.elapsed, self.seek, self.total], spacing=0,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ], spacing=0, expand=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                ft.Row([ft.Icon(ft.Icons.VOLUME_UP_ROUNDED, size=18, color=MUTED), self.volume], spacing=0),
                ft.IconButton(icon=ft.Icons.CLOSE, icon_color=MUTED, on_click=lambda e: self.stop()),
            ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        )

    def refresh_texts(self):
        pass  # los botones del reproductor no tienen texto

    def _paint(self):
        try:
            self.bar.update()
        except Exception:
            pass
        self.app.on_player_changed()

    def _show_track(self, track):
        self.title.value = track.title
        self.artist.value = " · ".join(x for x in [track.artist, track.album] if x) or os.path.basename(track.folder)
        self.cover.content = (ft.Image(src=track.cover, width=48, height=48, fit=ft.BoxFit.COVER) if track.cover
                              else ft.Icon(ft.Icons.MUSIC_NOTE, color=ft.Colors.ON_SECONDARY_CONTAINER))
        self.duration_ms = int(track.duration * 1000)
        self.position_ms = 0
        self.seek.max = max(self.duration_ms, 1)
        self.seek.value = 0
        self.elapsed.value = "0:00"
        self.total.value = fmt_duration(track.duration) or "0:00"

    def _set_state(self, state):
        self.state = state
        self.spinner_layer.visible = state == "loading"
        self.play_btn.icon = ft.Icons.PAUSE_ROUNDED if state == "playing" else ft.Icons.PLAY_ARROW_ROUNDED
        self.play_btn.opacity = 0.3 if state == "loading" else 1

    # ---------------------------------------------------------- control
    def play_list(self, tracks, index):
        """Reproduce `tracks[index]` y deja el resto como cola (anterior/siguiente)."""
        self.queue = list(tracks)
        self.index = index
        self._load()

    def _load(self):
        track = self.current
        if not track:
            return
        self._token += 1
        token = self._token
        self._show_track(track)
        self._set_state("loading")
        self.bar.visible = True
        self._paint()
        self.app.page.run_thread(self._prepare, track, token)

    def _prepare(self, track, token):
        """Hilo: convierte el archivo si el reproductor no lo admite (Opus/ALAC)."""
        try:
            path = library.playable_path(track)
        except Exception as exc:
            logger.exception("No se puede reproducir %s", track.path)
            self.app.ui(self._failed, token, str(exc))
            return
        self.app.ui(self._start, token, path)

    def _start(self, token, path):
        if token != self._token:
            return  # el usuario ya eligió otra canción
        self.audio.src = path
        self.audio.update()
        self.app.page.run_task(self.audio.play)

    def _failed(self, token, message):
        if token != self._token:
            return
        self._set_state("stopped")
        self._paint()
        self.app.toast(self.t("player_error", message))

    def toggle(self):
        if not self.current or self.state == "loading":
            return
        if self.state == "playing":
            self.app.page.run_task(self.audio.pause)
        elif self.state == "paused":
            self.app.page.run_task(self.audio.resume)
        else:
            self._load()

    def next(self):
        if self.index + 1 < len(self.queue):
            self.index += 1
            self._load()

    def previous(self):
        if self.position_ms > 3000 or self.index == 0:
            self.app.page.run_task(self.audio.seek, 0)
        elif self.index > 0:
            self.index -= 1
            self._load()

    def stop(self):
        self._token += 1
        if self.state in ("playing", "paused"):
            self.app.page.run_task(self.audio.pause)
        self._set_state("stopped")
        self.queue, self.index = [], -1
        self.bar.visible = False
        self._paint()

    def forget(self, path):
        """Una canción se ha borrado: si es la actual, se para."""
        if self.current and os.path.normcase(self.current.path) == os.path.normcase(path):
            self.stop()

    # ---------------------------------------------------------- eventos del audio
    def _on_duration(self, e):
        ms = getattr(e.duration, "in_milliseconds", None)
        if ms:
            self.duration_ms = int(ms)
            self.seek.max = max(self.duration_ms, 1)
            self.total.value = fmt_duration(self.duration_ms / 1000)
            self._paint()

    def _on_position(self, e):
        # La posición llega en milisegundos (int); la duración, como ft.Duration
        ms = getattr(e.position, "in_milliseconds", e.position)
        if not isinstance(ms, (int, float)) or self._dragging:
            return
        self.position_ms = int(ms)
        now = time.monotonic()
        if now - self._last_paint < POSITION_PAINT_INTERVAL:
            return
        self._last_paint = now
        self.seek.value = min(self.position_ms, self.seek.max)
        self.elapsed.value = fmt_duration(self.position_ms / 1000) or "0:00"
        try:
            self.bar.update()
        except Exception:
            pass

    def _on_state(self, e):
        state = getattr(e.state, "name", str(e.state)).upper()
        if state == "PLAYING":
            self._set_state("playing")
        elif state == "PAUSED":
            self._set_state("paused")
        elif state == "COMPLETED":
            if self.index + 1 < len(self.queue):
                self.next()
                return
            self._set_state("stopped")
            self.position_ms = 0
            self.seek.value = 0
            self.elapsed.value = "0:00"
        elif state == "STOPPED" and self.state != "loading":
            self._set_state("stopped")
        self._paint()

    # ---------------------------------------------------------- barra de posición y volumen
    def _seek_start(self, e):
        self._dragging = True

    def _seek_move(self, e):
        self.elapsed.value = fmt_duration(e.control.value / 1000) or "0:00"
        self.elapsed.update()

    def _seek_end(self, e):
        self._dragging = False
        self.position_ms = int(e.control.value)
        if self.state in ("playing", "paused"):
            self.app.page.run_task(self.audio.seek, self.position_ms)

    def _volume_changed(self, e):
        self.audio.volume = e.control.value
        self.audio.update()
