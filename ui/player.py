"""Mini reproductor fijo en la parte inferior (usa flet-audio).

Además de reproducir, pausar y saltar: modo aleatorio equilibrado (core/shuffle.py),
repetición (lista o canción), silencio, cola editable y letra de la canción
(sincronizada si hay un .lrc al lado).
"""
import logging
import os
import time

import flet as ft
import flet_audio as fa

from core import library, lyrics
from core.shuffle import PlayHistory, smart_shuffle
from .widgets import MUTED, fmt_duration

logger = logging.getLogger(__name__)

POSITION_PAINT_INTERVAL = 0.25
COUNT_AS_PLAYED_MS = 30_000   # a partir de aquí (o de la mitad) cuenta como escuchada
REPEAT_MODES = ("off", "all", "one")
REPEAT_ICONS = {"off": ft.Icons.REPEAT_ROUNDED, "all": ft.Icons.REPEAT_ROUNDED, "one": ft.Icons.REPEAT_ONE_ROUNDED}


class Player:
    def __init__(self, app):
        self.app = app
        self.queue = []            # orden de reproducción (barajado si el aleatorio está activo)
        self.original = []         # orden en que se añadieron, para volver al desactivar el aleatorio
        self.index = -1
        self.state = "stopped"     # stopped | loading | playing | paused
        self.duration_ms = 0
        self.position_ms = 0
        self.shuffle = bool(app.config.get("player_shuffle"))
        repeat = app.config.get("player_repeat")
        self.repeat = repeat if repeat in REPEAT_MODES else "off"
        self._token = 0            # invalida cargas antiguas al cambiar de canción rápido
        self._dragging = False
        self._last_paint = 0.0
        self._muted_volume = None  # volumen antes de silenciar
        self._lyrics_view = None   # diálogo de letra abierto: (ListView, [tiempos], índice resaltado)
        self.history = PlayHistory()
        self._counted = False      # la canción actual ya se apuntó en el historial
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
        self.shuffle_btn = ft.IconButton(icon=ft.Icons.SHUFFLE_ROUNDED, icon_size=20,
                                         on_click=lambda e: self.toggle_shuffle())
        self.repeat_btn = ft.IconButton(icon=ft.Icons.REPEAT_ROUNDED, icon_size=20,
                                        on_click=lambda e: self.cycle_repeat())
        self.prev_btn = ft.IconButton(icon=ft.Icons.SKIP_PREVIOUS_ROUNDED, on_click=lambda e: self.previous())
        self.next_btn = ft.IconButton(icon=ft.Icons.SKIP_NEXT_ROUNDED, on_click=lambda e: self.next())
        self.elapsed = ft.Text("0:00", size=12, color=MUTED, width=44, text_align=ft.TextAlign.RIGHT)
        self.total = ft.Text("0:00", size=12, color=MUTED, width=44)
        self.seek = ft.Slider(min=0, max=1, value=0, expand=True, on_change_start=self._seek_start,
                              on_change=self._seek_move, on_change_end=self._seek_end)
        self.mute_btn = ft.IconButton(icon=ft.Icons.VOLUME_UP_ROUNDED, icon_size=18, icon_color=MUTED,
                                      on_click=lambda e: self.toggle_mute())
        self.volume = ft.Slider(min=0, max=1, value=self.audio.volume, width=100, on_change=self._volume_changed,
                                on_change_end=self._volume_saved)
        self.lyrics_btn = ft.IconButton(icon=ft.Icons.LYRICS_OUTLINED, icon_size=20, icon_color=MUTED,
                                        on_click=lambda e: self.show_lyrics())
        self.queue_btn = ft.IconButton(icon=ft.Icons.QUEUE_MUSIC_ROUNDED, icon_size=20, icon_color=MUTED,
                                       on_click=lambda e: self.show_queue())
        self.close_btn = ft.IconButton(icon=ft.Icons.CLOSE, icon_color=MUTED, on_click=lambda e: self.stop())
        self.bar = ft.Container(
            visible=False,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
            border_radius=16,
            padding=ft.Padding(12, 8, 12, 8),
            margin=ft.Margin(24, 0, 24, 16),
            content=ft.Row([
                self.cover,
                ft.Column([self.title, self.artist], spacing=0, width=200),
                ft.Column([
                    ft.Row([
                        self.shuffle_btn,
                        self.prev_btn,
                        ft.Stack([self.play_btn, self.spinner_layer], width=48, height=48),
                        self.next_btn,
                        self.repeat_btn,
                    ], alignment=ft.MainAxisAlignment.CENTER, spacing=4),
                    ft.Row([self.elapsed, self.seek, self.total], spacing=0,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ], spacing=0, expand=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                ft.Row([self.lyrics_btn, self.queue_btn, self.mute_btn, self.volume], spacing=0,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                self.close_btn,
            ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        )
        self._paint_modes()
        self.refresh_texts()

    def refresh_texts(self):
        t = self.t
        self.prev_btn.tooltip = t("player_previous")
        self.next_btn.tooltip = t("player_next")
        self.lyrics_btn.tooltip = t("player_lyrics")
        self.queue_btn.tooltip = t("player_queue")
        self.close_btn.tooltip = t("player_close")
        self.shuffle_btn.tooltip = t("player_shuffle_on") if self.shuffle else t("player_shuffle_off")
        self.repeat_btn.tooltip = t(f"player_repeat_{self.repeat}")
        self.mute_btn.tooltip = t("player_unmute") if self._muted_volume is not None else t("player_mute")

    def _paint_modes(self):
        """Colores e iconos de aleatorio, repetir y silencio según su estado."""
        self.shuffle_btn.icon_color = ft.Colors.PRIMARY if self.shuffle else MUTED
        self.repeat_btn.icon = REPEAT_ICONS[self.repeat]
        self.repeat_btn.icon_color = MUTED if self.repeat == "off" else ft.Colors.PRIMARY
        muted = self._muted_volume is not None or self.audio.volume == 0
        self.mute_btn.icon = ft.Icons.VOLUME_OFF_ROUNDED if muted else ft.Icons.VOLUME_UP_ROUNDED

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

    # ---------------------------------------------------------- cola
    def play_list(self, tracks, index, shuffle=None):
        """Reproduce `tracks[index]` y deja el resto como cola.

        shuffle=True/False fuerza el modo aleatorio (botón "Aleatorio" de la Biblioteca)."""
        if not tracks:
            return
        if shuffle is not None and shuffle != self.shuffle:
            self.shuffle = shuffle
            self.app.config.set("player_shuffle", shuffle)
            self._paint_modes()
            self.refresh_texts()
        self.original = list(tracks)
        if self.shuffle:
            # Sin canción elegida (botón "Aleatorio"), también la primera la decide el aleatorio
            first = tracks[index] if index is not None else None
            self.queue, self.index = smart_shuffle(tracks, self.history.recent(), first=first), 0
        else:
            self.queue, self.index = list(tracks), index or 0
        self._load()

    def play_next(self, track):
        """Pone la canción justo después de la actual."""
        if not self.current:
            self.play_list([track], 0)
            return
        self.queue.insert(self.index + 1, track)
        position = self.original.index(self.current) + 1 if self.current in self.original else len(self.original)
        self.original.insert(position, track)
        self.app.toast(self.t("player_added_next", track.title))

    def add_to_queue(self, track):
        if not self.current:
            self.play_list([track], 0)
            return
        self.queue.append(track)
        self.original.append(track)
        self.app.toast(self.t("player_added_queue", track.title))

    def toggle_shuffle(self):
        self.shuffle = not self.shuffle
        self.app.config.set("player_shuffle", self.shuffle)
        current = self.current
        if current:
            if self.shuffle:
                # La canción actual sigue sonando; las demás se barajan detrás
                self.queue = smart_shuffle(self.original, self.history.recent(), first=current)
                self.index = 0
            else:
                self.queue = list(self.original)
                self.index = next((i for i, tr in enumerate(self.queue) if tr is current), 0)
        self._paint_modes()
        self.refresh_texts()
        self._paint()

    def cycle_repeat(self):
        self.repeat = REPEAT_MODES[(REPEAT_MODES.index(self.repeat) + 1) % len(REPEAT_MODES)]
        self.app.config.set("player_repeat", self.repeat)
        self._paint_modes()
        self.refresh_texts()
        self._paint()
        self.app.toast(self.t(f"player_repeat_{self.repeat}"))

    # ---------------------------------------------------------- control
    def _load(self):
        track = self.current
        if not track:
            return
        self._token += 1
        token = self._token
        self._counted = False
        self._show_track(track)
        self._set_state("loading")
        self.bar.visible = True
        self._close_lyrics()
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
        elif self.repeat == "all" and self.queue:
            self._restart_list()

    def _restart_list(self):
        """Vuelve al principio de la cola (con el aleatorio, en un orden nuevo)."""
        if self.shuffle and len(self.queue) > 1:
            # Orden nuevo; lo recién escuchado va al final y no repite la que acaba de sonar
            self.queue = smart_shuffle(self.queue, self.history.recent(), avoid_first=self.queue[-1])
        self.index = 0
        self._load()

    def previous(self):
        if self.position_ms > 3000 or (self.index == 0 and self.repeat != "all"):
            self.app.page.run_task(self.audio.seek, 0)
        elif self.index > 0:
            self.index -= 1
            self._load()
        elif self.queue:  # repetir lista: de la primera se pasa a la última
            self.index = len(self.queue) - 1
            self._load()

    def stop(self):
        self._token += 1
        if self.state in ("playing", "paused"):
            self.app.page.run_task(self.audio.pause)
        self._set_state("stopped")
        self.queue, self.original, self.index = [], [], -1
        self.bar.visible = False
        self._close_lyrics()
        self._paint()

    def forget(self, path):
        """Una canción se ha borrado: si es la actual, se para; si no, se quita de la cola."""
        key = os.path.normcase(path)
        if self.current and os.path.normcase(self.current.path) == key:
            self.stop()
            return
        current = self.current
        self.original = [tr for tr in self.original if os.path.normcase(tr.path) != key]
        self.queue = [tr for tr in self.queue if os.path.normcase(tr.path) != key]
        if current:
            self.index = next((i for i, tr in enumerate(self.queue) if tr is current), 0)

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
        threshold = min(COUNT_AS_PLAYED_MS, max(self.duration_ms // 2, 1))
        if not self._counted and self.current and self.state == "playing" and self.position_ms >= threshold:
            self._counted = True
            self.app.page.run_thread(self.history.add, self.current)
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
        self._follow_lyrics()

    def _on_state(self, e):
        state = getattr(e.state, "name", str(e.state)).upper()
        if state == "PLAYING":
            self._set_state("playing")
        elif state == "PAUSED":
            self._set_state("paused")
        elif state == "COMPLETED":
            if self.repeat == "one":
                self._load()
                return
            if self.index + 1 < len(self.queue) or self.repeat == "all":
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

    def seek_to(self, seconds):
        self.position_ms = int(seconds * 1000)
        if self.state in ("playing", "paused"):
            self.app.page.run_task(self.audio.seek, self.position_ms)

    def _volume_changed(self, e):
        self.audio.volume = e.control.value
        self.audio.update()
        if self._muted_volume is not None and e.control.value > 0:
            self._muted_volume = None  # mover la barra quita el silencio
        self._paint_modes()
        self.refresh_texts()
        self.mute_btn.update()

    def _volume_saved(self, e):
        self.app.config.set("volume", round(e.control.value, 2))

    def toggle_mute(self):
        if self._muted_volume is None:
            self._muted_volume = self.audio.volume or 0.8
            self.audio.volume = 0
        else:
            self.audio.volume, self._muted_volume = self._muted_volume, None
        self.volume.value = self.audio.volume
        self.audio.update()
        self._paint_modes()
        self.refresh_texts()
        self._paint()

    # ---------------------------------------------------------- cola (diálogo)
    def show_queue(self):
        t = self.t
        if not self.queue:
            return
        listview = ft.ListView(expand=True, spacing=2)

        def jump(i):
            self.app.page.pop_dialog()
            self.index = i
            self._load()

        def remove(track):
            current = self.current
            if track is current:
                return
            self.queue = [tr for tr in self.queue if tr is not track]
            self.original = [tr for tr in self.original if tr is not track]
            self.index = next((i for i, tr in enumerate(self.queue) if tr is current), 0)
            fill()

        def fill():
            rows = []
            for i, track in enumerate(self.queue):
                playing = i == self.index
                rows.append(ft.ListTile(
                    leading=ft.Icon(ft.Icons.GRAPHIC_EQ if playing else ft.Icons.MUSIC_NOTE,
                                    color=ft.Colors.PRIMARY if playing else MUTED),
                    title=ft.Text(track.title, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                                  color=ft.Colors.PRIMARY if playing else None,
                                  weight=ft.FontWeight.W_600 if playing else None),
                    subtitle=ft.Text(" · ".join(x for x in [track.artist, fmt_duration(track.duration)] if x),
                                     size=12, color=MUTED, max_lines=1),
                    trailing=None if playing else ft.IconButton(
                        icon=ft.Icons.REMOVE_CIRCLE_OUTLINE, icon_color=MUTED, tooltip=t("remove"),
                        on_click=lambda e, tr=track: remove(tr)),
                    on_click=lambda e, i=i: jump(i),
                    selected=playing, dense=True, shape=ft.RoundedRectangleBorder(radius=12),
                ))
            listview.controls = rows
            try:
                listview.update()
            except Exception:
                pass

        fill()
        upcoming = len(self.queue) - self.index - 1
        self.app.page.show_dialog(ft.AlertDialog(
            title=ft.Column([ft.Text(t("player_queue")),
                             ft.Text(t("player_queue_upcoming", upcoming), size=13, color=MUTED)], spacing=2),
            content=ft.Container(listview, width=520, height=420),
            actions=[ft.TextButton(content=t("close"), on_click=lambda e: self.app.page.pop_dialog())],
        ))
        # Que se vea la canción actual aunque la cola sea larga
        if self.index > 3:
            self.app.page.run_task(listview.scroll_to, offset=max(0, (self.index - 2) * 56), duration=0)

    # ---------------------------------------------------------- letra (diálogo)
    def show_lyrics(self):
        track = self.current
        if not track:
            return
        timed, plain = lyrics.read_for(track.path)
        if not timed and not plain:
            self.app.toast(self.t("player_no_lyrics"))
            return
        if timed:
            rows = [ft.Container(
                ft.Text(line or "♪", size=17, color=MUTED, text_align=ft.TextAlign.CENTER),
                padding=ft.Padding(8, 6, 8, 6), border_radius=8, alignment=ft.Alignment.CENTER,
                on_click=lambda e, s=start: self.seek_to(s), key=ft.ScrollKey(f"lyric-{i}"),
            ) for i, (start, line) in enumerate(timed)]
            # Column y no ListView: scroll_to(scroll_key=...) no funciona con ListView
            listview = ft.Column(rows, expand=True, spacing=2, scroll=ft.ScrollMode.AUTO,
                                 horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
            self._lyrics_view = (listview, [start for start, _ in timed], -1)
            content = listview
        else:
            content = ft.Column([ft.Text(plain, size=15, selectable=True)], scroll=ft.ScrollMode.AUTO, expand=True)
        self.app.page.show_dialog(ft.AlertDialog(
            title=ft.Column([ft.Text(track.title),
                             ft.Text(track.artist or "", size=13, color=MUTED)], spacing=2),
            content=ft.Container(content, width=560, height=440),
            actions=[ft.TextButton(content=self.t("close"), on_click=lambda e: self._close_lyrics(pop=True))],
            on_dismiss=lambda e: self._close_lyrics(),
        ))
        self._follow_lyrics(force=True)

    def _close_lyrics(self, pop=False):
        was_open = self._lyrics_view is not None
        self._lyrics_view = None
        if pop and was_open:
            self.app.page.pop_dialog()

    def _follow_lyrics(self, force=False):
        """Resalta la línea que suena y desplaza la letra para que se vea."""
        if not self._lyrics_view:
            return
        listview, starts, shown = self._lyrics_view
        seconds = self.position_ms / 1000
        current = -1
        for i, start in enumerate(starts):
            if start <= seconds + 0.2:
                current = i
            else:
                break
        if current == shown and not force:
            return
        for i, row in enumerate(listview.controls):
            text = row.content
            active = i == current
            text.color = ft.Colors.PRIMARY if active else MUTED
            text.weight = ft.FontWeight.W_700 if active else None
            row.bgcolor = ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY) if active else None
        self._lyrics_view = (listview, starts, current)
        try:
            listview.update()
            if current >= 0:
                self.app.page.run_task(listview.scroll_to, scroll_key=f"lyric-{max(0, current - 3)}",
                                       duration=300)
        except Exception:
            pass
