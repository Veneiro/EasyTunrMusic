"""Sección Biblioteca: canciones de la carpeta de descargas, con reproductor."""
import logging
import os

import flet as ft

from core import library
from .widgets import MUTED, card, empty_state, fmt_duration, list_header, page_header

logger = logging.getLogger(__name__)

ALL = "__all__"


def _safe_update(control):
    try:
        control.update()
    except Exception:
        pass


class MusicView:
    def __init__(self, app):
        self.app = app

    def build(self):
        t, s = self.app.t, self.app.state
        folder = self.app.config.music_folder
        if s.library_tracks is None or s.library_stale or s.library_root != folder:
            self.rescan()

        self.spinner = ft.ProgressRing(width=20, height=20, stroke_width=2.5, visible=s.library_scanning)
        self.search = ft.TextField(
            value=s.library_query, hint_text=t("library_search"), prefix_icon=ft.Icons.SEARCH,
            on_change=self._query_changed, expand=True, border_radius=12, filled=True, border_width=0,
        )
        self.folder_dd = ft.Dropdown(
            value=s.library_folder or ALL, options=self._folder_options(), on_select=self._folder_changed,
            width=260, leading_icon=ft.Icons.FOLDER_OUTLINED,
        )
        self.list = ft.Column(expand=True, spacing=6, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self._render()
        return ft.Column(
            [
                ft.Row([
                    page_header(t("library_title"), folder),
                    ft.Container(expand=True),
                    self.spinner,
                    ft.IconButton(icon=ft.Icons.REFRESH, tooltip=t("refresh"), on_click=lambda e: self.rescan()),
                    ft.TextButton(content=t("open_folder"), icon=ft.Icons.FOLDER_OPEN,
                                  on_click=lambda e: self.app.open_music_folder()),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([self.search, self.folder_dd], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                card(self.list, expand=True),
            ],
            expand=True, spacing=16,
        )

    # ---------------------------------------------------------- datos
    def rescan(self):
        s = self.app.state
        if s.library_scanning:
            return
        s.library_scanning = True
        s.library_stale = False
        self.app.page.run_thread(self._scan_worker, self.app.config.music_folder)

    def _scan_worker(self, folder):
        s = self.app.state
        try:
            tracks = library.scan(folder)
        except Exception:
            logger.exception("No se pudo leer la biblioteca")
            tracks = []
        s.library_tracks, s.library_root = tracks, folder
        s.library_scanning = False
        self.app.ui(self._after_scan)

    def _after_scan(self):
        if self.app.views[self.app.index] is self:
            self.app.refresh_view()

    def _filtered(self):
        s = self.app.state
        query = (s.library_query or "").strip().lower()
        tracks = s.library_tracks or []
        if s.library_folder and s.library_folder != ALL:
            prefix = s.library_folder
            tracks = [tr for tr in tracks if tr.folder == prefix or tr.folder.startswith(prefix + os.sep)]
        if query:
            words = query.split()
            tracks = [tr for tr in tracks if all(w in tr.search_text for w in words)]
        return tracks

    def _folder_options(self):
        t = self.app.t
        top = sorted({tr.folder.split(os.sep)[0] for tr in (self.app.state.library_tracks or []) if tr.folder},
                     key=str.lower)
        return [ft.DropdownOption(key=ALL, text=t("library_all_folders"))] + \
               [ft.DropdownOption(key=f, text=f) for f in top]

    # ---------------------------------------------------------- render
    def _render(self):
        t, s = self.app.t, self.app.state
        tracks = self._filtered()
        current = self.app.player.current
        current_path = os.path.normcase(current.path) if current else None

        rows = [self._row(tr, i, tracks, current_path) for i, tr in enumerate(tracks)]
        if rows:
            body = ft.ListView(rows, expand=True, spacing=2)
        elif s.library_tracks is None or s.library_scanning:
            body = empty_state(ft.Icons.HOURGLASS_EMPTY, t("scanning"))
        elif s.library_tracks:
            body = empty_state(ft.Icons.SEARCH_OFF, t("library_no_match"))
        else:
            body = empty_state(ft.Icons.HEADPHONES, t("library_empty"))
        play_all = [ft.FilledButton(content=t("play_all"), icon=ft.Icons.PLAY_ARROW_ROUNDED,
                                    on_click=lambda e: self.app.player.play_list(tracks, 0))] if rows else []
        self.list.controls = [list_header(t("library_songs"), len(rows) or None, play_all), body]

    def _row(self, track, index, tracks, current_path):
        t = self.app.t
        playing = current_path == os.path.normcase(track.path)
        if track.cover:
            leading = ft.Image(src=track.cover, width=40, height=40, fit=ft.BoxFit.COVER, border_radius=8)
        else:
            leading = ft.Container(
                ft.Icon(ft.Icons.GRAPHIC_EQ if playing else ft.Icons.MUSIC_NOTE, size=20,
                        color=ft.Colors.ON_SECONDARY_CONTAINER),
                bgcolor=ft.Colors.SECONDARY_CONTAINER, width=40, height=40, border_radius=8,
                alignment=ft.Alignment.CENTER)
        subtitle = " · ".join(x for x in [track.artist, track.album or track.folder] if x)
        menu = ft.PopupMenuButton(
            icon=ft.Icons.MORE_VERT,
            items=[
                ft.PopupMenuItem(content=t("play"), icon=ft.Icons.PLAY_ARROW_ROUNDED,
                                 on_click=lambda e: self.app.player.play_list(tracks, index)),
                ft.PopupMenuItem(content=t("open_external"), icon=ft.Icons.OPEN_IN_NEW,
                                 on_click=lambda e: self._open_external(track)),
                ft.PopupMenuItem(content=t("show_in_folder"), icon=ft.Icons.FOLDER_OPEN,
                                 on_click=lambda e: library.show_in_folder(track.path)),
                ft.PopupMenuItem(content=t("delete"), icon=ft.Icons.DELETE_OUTLINE,
                                 on_click=lambda e: self._confirm_delete(track)),
            ],
        )
        return ft.ListTile(
            leading=leading,
            title=ft.Text(track.title, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                          color=ft.Colors.PRIMARY if playing else None,
                          weight=ft.FontWeight.W_600 if playing else None),
            subtitle=ft.Text(subtitle, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, color=MUTED, size=12)
            if subtitle else None,
            trailing=ft.Row([ft.Text(fmt_duration(track.duration), color=MUTED, size=12), menu],
                            tight=True, spacing=4),
            on_click=lambda e: self.app.player.play_list(tracks, index),
            selected=playing,
            dense=True,
            shape=ft.RoundedRectangleBorder(radius=12),
        )

    def on_player_changed(self):
        """Resalta la canción que suena."""
        self._render()
        _safe_update(self.list)

    # ---------------------------------------------------------- acciones
    def _query_changed(self, e):
        self.app.state.library_query = e.control.value
        self._render()
        _safe_update(self.list)

    def _folder_changed(self, e):
        self.app.state.library_folder = "" if e.control.value == ALL else e.control.value
        self._render()
        _safe_update(self.list)

    def _open_external(self, track):
        try:
            os.startfile(track.path)
        except OSError as exc:
            self.app.toast(str(exc))

    def _confirm_delete(self, track):
        t = self.app.t

        def do_delete(e):
            self.app.page.pop_dialog()
            try:
                self.app.player.forget(track.path)
                library.delete_track(track)
            except OSError as exc:
                self.app.alert(t("error_title"), str(exc), icon=ft.Icons.ERROR_OUTLINE, color=ft.Colors.ERROR)
                return
            s = self.app.state
            s.library_tracks = [tr for tr in (s.library_tracks or []) if tr.path != track.path]
            self.app.toast(t("deleted"))
            self.app.refresh_view()

        self.app.page.show_dialog(ft.AlertDialog(
            icon=ft.Icon(ft.Icons.DELETE_OUTLINE, color=ft.Colors.ERROR, size=36),
            title=ft.Text(t("delete_title"), text_align=ft.TextAlign.CENTER),
            content=ft.Text(t("delete_text", track.title), width=420),
            actions=[
                ft.TextButton(content=t("cancel"), on_click=lambda e: self.app.page.pop_dialog()),
                ft.FilledButton(content=t("delete"), icon=ft.Icons.DELETE_OUTLINE, on_click=do_delete,
                                style=ft.ButtonStyle(bgcolor=ft.Colors.ERROR, color=ft.Colors.ON_ERROR)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        ))
