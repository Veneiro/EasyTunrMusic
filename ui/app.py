"""Ventana principal: navegación lateral, sección activa y panel de descargas."""
import logging
import os
from dataclasses import dataclass, field
from typing import List, Optional

import flet as ft

from core import paths
from core.config import Config
from . import theme
from .downloads import DownloadController
from .i18n import I18n
from .library import PlaylistView, SearchView, SongsView, SpotifyView
from .music import MusicView
from .player import Player
from .settings import AboutView, AudioView, SettingsView
from .updater import Updater
from .uithread import call_ui
from .titlebar import TitleBar, hide_native_title_bar

logger = logging.getLogger(__name__)


@dataclass
class AppState:
    """Lo que el usuario ha escrito o añadido; sobrevive a cambios de sección e idioma."""
    search_query: str = ""
    searching: bool = False
    search_results: List[dict] = field(default_factory=list)
    search_queue: List[dict] = field(default_factory=list)
    song_url: str = ""
    checking_link: bool = False
    songs: List[dict] = field(default_factory=list)
    playlist_url: str = ""
    spotify_loading: bool = False
    spotify_status: str = ""
    spotify_link: str = ""
    spotify_matches: list = field(default_factory=list)   # spotify.Match listas para descargar
    spotify_missing: list = field(default_factory=list)   # spotify.Track sin coincidencia fiable
    spotify_done: list = field(default_factory=list)      # spotify.Track que ya están en la carpeta
    spotify_tracks: list = field(default_factory=list)    # la lista completa, en su orden (para la .m3u8)
    spotify_truncated: bool = False
    spotify_total: int = 0
    spotify_name: str = ""
    ytdlp_version: Optional[str] = None
    library_tracks: Optional[list] = None   # None = aún no se ha leído la carpeta
    library_root: str = ""
    library_stale: bool = False
    library_scanning: bool = False
    library_query: str = ""
    library_folder: str = ""


NAV = [
    ("nav_search", ft.Icons.SEARCH_OUTLINED, ft.Icons.SEARCH),
    ("nav_songs", ft.Icons.LINK_OUTLINED, ft.Icons.LINK),
    ("nav_playlist", ft.Icons.PLAYLIST_PLAY_OUTLINED, ft.Icons.PLAYLIST_PLAY),
    ("nav_spotify", ft.Icons.LIBRARY_MUSIC_OUTLINED, ft.Icons.LIBRARY_MUSIC),
    ("nav_library", ft.Icons.HEADPHONES_OUTLINED, ft.Icons.HEADPHONES),
    ("nav_audio", ft.Icons.TUNE_OUTLINED, ft.Icons.TUNE),
    ("nav_settings", ft.Icons.SETTINGS_OUTLINED, ft.Icons.SETTINGS),
    ("nav_about", ft.Icons.INFO_OUTLINE, ft.Icons.INFO),
]


class EasyTunrApp:
    def __init__(self, page: ft.Page, config: Config):
        self.page = page
        self.config = config
        self.t = I18n(config.get("language"))
        self.state = AppState()
        self.file_picker = ft.FilePicker()
        self.downloads = DownloadController(self)
        self.updater = Updater(self)
        self.player = Player(self)
        self.views = [SearchView(self), SongsView(self), PlaylistView(self), SpotifyView(self),
                      MusicView(self), AudioView(self), SettingsView(self), AboutView(self)]
        self.index = 0

        theme.apply(page, config)
        page.on_keyboard_event = self._on_key
        self.content = ft.Container(expand=True, padding=ft.Padding(32, 28, 32, 16))
        self.rail = self._build_rail()
        page.controls.clear()
        page.add(ft.Column([
            TitleBar(page).build(),
            ft.Row(
                [self.rail, ft.VerticalDivider(width=1),
                 ft.Column([self.content, self.downloads.panel, self.player.bar], expand=True, spacing=0)],
                expand=True, spacing=0,
            ),
        ], expand=True, spacing=0))
        self.refresh_view()
        if config.get("check_updates"):
            self.updater.check_in_background()

    # ---------------------------------------------------------- estructura
    def _build_rail(self):
        return ft.NavigationRail(
            selected_index=self.index,
            label_type=ft.NavigationRailLabelType.ALL,
            group_alignment=-0.85,
            leading=ft.Container(height=8),  # el logo ya está en la barra de título
            destinations=[ft.NavigationRailDestination(icon=icon, selected_icon=selected, label=self.t(key))
                          for key, icon, selected in NAV],
            on_change=lambda e: self.go(e.control.selected_index),
        )

    def go(self, index):
        self.index = index
        self.rail.selected_index = index
        self.refresh_view()

    def ui(self, fn, *args):
        """Ejecuta fn en el bucle de eventos de Flet. Úsalo para tocar la interfaz desde hilos."""
        call_ui(self.page, fn, *args)

    def refresh_view(self):
        """Reconstruye la sección activa a partir del estado (seguro desde cualquier hilo)."""
        self.ui(self._refresh_view_now)

    def _refresh_view_now(self):
        try:
            self.content.content = self.views[self.index].build()
            self.page.update()
        except Exception:
            logger.exception("No se pudo dibujar la sección %s", self.index)

    def set_language(self, lang):
        self.config.set("language", lang)
        self.t = I18n(lang)
        for dest, (key, _, _) in zip(self.rail.destinations, NAV):
            dest.label = self.t(key)
        self.downloads.refresh_texts()
        self.refresh_view()

    def apply_theme(self):
        theme.apply(self.page, self.config)
        self.page.update()

    def on_player_changed(self):
        view = self.views[self.index]
        if hasattr(view, "on_player_changed"):
            view.on_player_changed()

    def on_busy_changed(self):
        # Habilita o deshabilita los botones de descarga de la sección visible
        self.refresh_view()

    # ---------------------------------------------------------- utilidades
    def toast(self, message):
        self.ui(lambda: self.page.show_dialog(ft.SnackBar(
            ft.Text(message), behavior=ft.SnackBarBehavior.FLOATING, width=480, duration=3500)))

    def alert(self, *args, **kwargs):
        self.ui(lambda: self._alert_now(*args, **kwargs))

    def _alert_now(self, title, text, icon=ft.Icons.INFO_OUTLINE, color=ft.Colors.PRIMARY, open_folder=False):
        def close(e=None):
            self.page.pop_dialog()

        def open_and_close(e):
            close()
            self.open_music_folder()

        actions = []
        if open_folder:
            actions.append(ft.TextButton(content=self.t("open_folder"), icon=ft.Icons.FOLDER_OPEN,
                                         on_click=open_and_close))
        actions.append(ft.FilledButton(content=self.t("close"), on_click=close))
        dialog = ft.AlertDialog(
            icon=ft.Icon(icon, color=color, size=40),
            title=ft.Text(title, text_align=ft.TextAlign.CENTER),
            content=ft.Container(
                ft.Column([ft.Text(text, selectable=True)], scroll=ft.ScrollMode.AUTO),
                width=460, height=300,
            ) if len(text) > 400 or text.count("\n") > 8 else ft.Text(text, selectable=True, width=460),
            actions=actions,
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dialog)

    def open_music_folder(self):
        folder = self.config.music_folder
        try:
            os.makedirs(folder, exist_ok=True)
            os.startfile(folder)
        except OSError as exc:
            self.alert(self.t("error_title"), str(exc), icon=ft.Icons.ERROR_OUTLINE, color=ft.Colors.ERROR)

    def _on_key(self, e: ft.KeyboardEvent):
        if not e.ctrl:
            return
        key = (e.key or "").lower()
        if key == "f":
            self.go(0)
            self.views[0].focus()
        elif key == "p":
            self.downloads.toggle_pause()
        elif key == "o":
            self.open_music_folder()


def setup_window(page: ft.Page):
    page.title = "EasyTunrMusic"
    page.padding = 0
    page.spacing = 0
    page.window.icon = paths.resource_path("icon.ico")
    page.window.width = 1120
    page.window.height = 760
    page.window.min_width = 880
    page.window.min_height = 600
    hide_native_title_bar(page)  # se usa la barra de título propia (ui/titlebar.py)
