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
                    ft.Container(page_header(t("library_title"), folder), expand=True),
                    self.spinner,
                    ft.IconButton(icon=ft.Icons.REFRESH, tooltip=t("refresh"), on_click=lambda e: self.rescan()),
                    ft.IconButton(icon=ft.Icons.CONTENT_COPY, tooltip=t("library_duplicates"),
                                  on_click=lambda e: self._show_duplicates()),
                    ft.IconButton(icon=ft.Icons.PLAYLIST_ADD_CHECK, tooltip=t("library_export_m3u"),
                                  on_click=self._export_m3u),
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
        play_all = [
            ft.OutlinedButton(content=t("shuffle_all"), icon=ft.Icons.SHUFFLE_ROUNDED,
                              on_click=lambda e: self.app.player.play_list(tracks, None, shuffle=True)),
            ft.FilledButton(content=t("play_all"), icon=ft.Icons.PLAY_ARROW_ROUNDED,
                            on_click=lambda e: self.app.player.play_list(tracks, 0, shuffle=False)),
        ] if rows else []
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
                ft.PopupMenuItem(content=t("play_next"), icon=ft.Icons.PLAYLIST_PLAY_ROUNDED,
                                 on_click=lambda e: self.app.player.play_next(track)),
                ft.PopupMenuItem(content=t("add_to_queue"), icon=ft.Icons.QUEUE_MUSIC_ROUNDED,
                                 on_click=lambda e: self.app.player.add_to_queue(track)),
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

    # ---------------------------------------------------------- listas y duplicados
    async def _export_m3u(self, e):
        t, s = self.app.t, self.app.state
        tracks = self._filtered()
        if not tracks:
            self.app.toast(t("library_no_match") if s.library_tracks else t("library_empty"))
            return
        root = self.app.config.music_folder
        folder = os.path.join(root, s.library_folder) if s.library_folder else root
        name = (os.path.basename(s.library_folder) if s.library_folder else t("library_songs")) + ".m3u8"
        path = await self.app.file_picker.save_file(
            dialog_title=t("library_export_m3u"), file_name=name, initial_directory=folder,
            file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=["m3u8", "m3u"])
        if not path:
            return
        if not path.lower().endswith((".m3u8", ".m3u")):
            path += ".m3u8"
        try:
            library.write_m3u(path, [tr.path for tr in tracks])
            self.app.toast(t("m3u_saved", path))
        except OSError as exc:
            self.app.alert(t("error_title"), str(exc), icon=ft.Icons.ERROR_OUTLINE, color=ft.Colors.ERROR)

    def _show_duplicates(self):
        t, s = self.app.t, self.app.state
        groups = library.find_duplicates(s.library_tracks or [])
        if not groups:
            self.app.toast(t("duplicates_none"))
            return
        deleted = []

        def size_mb(path):
            try:
                return f"{os.path.getsize(path) / 1048576:.1f} MB"
            except OSError:
                return ""

        def dup_row(track):
            trailing = ft.Container()

            def ask(e):
                trailing.content = ft.FilledButton(
                    content=t("delete"), icon=ft.Icons.DELETE_OUTLINE, on_click=confirm,
                    style=ft.ButtonStyle(bgcolor=ft.Colors.ERROR, color=ft.Colors.ON_ERROR))
                _safe_update(trailing)

            def confirm(e):
                try:
                    self.app.player.forget(track.path)
                    library.delete_track(track)
                except OSError as exc:
                    self.app.toast(str(exc))
                    return
                deleted.append(track.path)
                trailing.content = ft.Text(t("deleted"), color=MUTED, size=12)
                _safe_update(trailing)

            trailing.content = ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, tooltip=t("delete"), on_click=ask)
            ext = os.path.splitext(track.path)[1].lstrip(".").upper()
            meta = " · ".join(x for x in [track.folder or os.path.basename(self.app.config.music_folder),
                                          fmt_duration(track.duration), size_mb(track.path), ext] if x)
            return ft.ListTile(
                title=ft.Text(os.path.basename(track.path), max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                subtitle=ft.Text(meta, size=12, color=MUTED),
                trailing=trailing, dense=True, shape=ft.RoundedRectangleBorder(radius=12),
                on_click=lambda e: library.show_in_folder(track.path),
            )

        controls = []
        for group in groups:
            first = group[0]
            controls.append(ft.Text(" — ".join(x for x in [first.title, first.artist] if x),
                                    weight=ft.FontWeight.W_600))
            controls.extend(dup_row(tr) for tr in group)
            controls.append(ft.Divider(height=8))

        def sync_deleted(e=None):
            if deleted:
                gone = set(deleted)
                deleted.clear()
                s.library_tracks = [tr for tr in (s.library_tracks or []) if tr.path not in gone]
                self.app.refresh_view()

        def close(e=None):
            self.app.page.pop_dialog()
            sync_deleted()

        self.app.page.show_dialog(ft.AlertDialog(
            icon=ft.Icon(ft.Icons.CONTENT_COPY, color=ft.Colors.PRIMARY, size=32),
            title=ft.Text(t("duplicates_title"), text_align=ft.TextAlign.CENTER),
            content=ft.Container(ft.Column([ft.Text(t("duplicates_text", len(groups)), color=MUTED),
                                            ft.ListView(controls, expand=True, spacing=2)], expand=True),
                                 width=620, height=440),
            actions=[ft.TextButton(content=t("close"), on_click=close)],
            on_dismiss=sync_deleted,
        ))
