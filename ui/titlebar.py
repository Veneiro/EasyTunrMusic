"""Barra de título propia (sustituye a la de Windows) con el estilo de la app."""
import time

import flet as ft

from .widgets import MUTED, app_logo

HEIGHT = 40
BUTTON_WIDTH = 46
DOUBLE_CLICK_SECONDS = 0.4


def hide_native_title_bar(page: ft.Page):
    page.window.title_bar_hidden = True
    page.window.title_bar_buttons_hidden = True


class TitleBar:
    def __init__(self, page: ft.Page, title="EasyTunrMusic"):
        self.page = page
        self.title = title
        self.max_btn = self._button(self._max_icon(), self._toggle_maximize)
        self._last_press = 0.0
        page.window.on_event = self._on_window_event

    # ---------------------------------------------------------- piezas
    def _max_icon(self):
        return ft.Icons.FILTER_NONE if self.page.window.maximized else ft.Icons.CROP_SQUARE

    @staticmethod
    def _button(icon, on_click, hover=None, icon_hover=None):
        return ft.IconButton(
            icon=icon,
            icon_size=16,
            icon_color=MUTED,
            hover_color=hover or ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE),
            width=BUTTON_WIDTH, height=HEIGHT,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=0), padding=0,
                                 icon_color={ft.ControlState.HOVERED: icon_hover} if icon_hover else None),
            on_click=lambda e: on_click(),
        )

    def build(self):
        drag = ft.WindowDragArea(
            ft.Container(
                ft.Row([app_logo(18), ft.Text(self.title, size=13, color=MUTED, weight=ft.FontWeight.W_500)],
                       spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.Padding(14, 0, 0, 0),
                height=HEIGHT,
                alignment=ft.Alignment.CENTER_LEFT,
            ),
            # Doble clic para maximizar/restaurar. Ni `maximizable` ni `on_double_tap`
            # funcionan en Windows porque el arrastre nativo se come el segundo clic,
            # así que se detectan dos pulsaciones seguidas a mano.
            maximizable=False,
            on_drag_start=self._on_press,
            expand=True,
        )
        buttons = ft.Row([
            self._button(ft.Icons.REMOVE, self._minimize),
            self.max_btn,
            self._button(ft.Icons.CLOSE, self._close, hover=ft.Colors.RED_700, icon_hover=ft.Colors.WHITE),
        ], spacing=0)
        return ft.Column([
            ft.Row([drag, buttons], spacing=0, height=HEIGHT),
            ft.Divider(height=1, thickness=1, color=ft.Colors.OUTLINE_VARIANT),
        ], spacing=0)

    # ---------------------------------------------------------- acciones
    def _on_press(self, e):
        now = time.monotonic()
        if now - self._last_press < DOUBLE_CLICK_SECONDS:
            self._last_press = 0.0
            self._toggle_maximize()
        else:
            self._last_press = now

    def _minimize(self):
        self.page.window.minimized = True
        self.page.update()

    def _toggle_maximize(self):
        self.page.window.maximized = not self.page.window.maximized
        self.page.update()
        self._sync_max_icon()

    def _close(self):
        self.page.run_task(self.page.window.close)

    def _on_window_event(self, e):
        if e.type in (ft.WindowEventType.MAXIMIZE, ft.WindowEventType.UNMAXIMIZE):
            self._sync_max_icon()

    def _sync_max_icon(self):
        self.max_btn.icon = self._max_icon()
        try:
            self.max_btn.update()
        except Exception:
            pass
