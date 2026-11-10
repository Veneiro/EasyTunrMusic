"""Secciones para elegir qué descargar: búsqueda, enlaces, listas y Spotify."""
import logging
import os
import re
import webbrowser

import flet as ft

from core import spotify, spotify_link, ytdlp
from core.jobs import (DownloadItem, playlist_items, spotify_folder, spotify_items,
                       write_items_playlist, write_spotify_playlist)
from .widgets import (MUTED, card, empty_state, fmt_duration, item_tile, list_header, page_header)

logger = logging.getLogger(__name__)

URL_RE = re.compile(r"^https?://", re.I)


def _safe_update(app, control):
    """Refresca un control desde cualquier hilo (en el bucle de Flet)."""
    def run():
        try:
            control.update()
        except Exception:  # el control ya no está en pantalla (se cambió de sección)
            pass
    app.ui(run)


def _card_column():
    """Columna de un recuadro de lista: estira su contenido a todo el ancho
    para que el estado vacío y la lista queden centrados en el recuadro."""
    return ft.Column(expand=True, spacing=6, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)


def _download_button(app, count, on_click):
    return ft.FilledButton(
        content=app.t("download_n", count) if count else app.t("download"),
        icon=ft.Icons.DOWNLOAD,
        on_click=on_click,
        disabled=not count or app.downloads.busy,
    )


def _input(value, hint, on_change, on_submit, icon):
    return ft.TextField(
        value=value, hint_text=hint, prefix_icon=icon,
        on_change=on_change, on_submit=on_submit,
        expand=True, border_radius=12, filled=True, border_width=0,
    )


# ============================================================== Buscar
class SearchView:
    def __init__(self, app):
        self.app = app

    def build(self):
        t, s = self.app.t, self.app.state
        self.query = _input(s.search_query, t("search_hint"),
                            lambda e: setattr(s, "search_query", e.control.value),
                            lambda e: self.search(), ft.Icons.SEARCH)
        self.query.autofocus = True
        self.spinner = ft.ProgressRing(width=22, height=22, stroke_width=2.5, visible=s.searching)
        self.results = _card_column()
        self.queue = _card_column()
        self._render_results()
        self._render_queue()
        return ft.Column(
            [
                page_header(t("search_title"), t("search_subtitle")),
                ft.Row([self.query, self.spinner,
                        ft.FilledButton(content=t("search_button"), icon=ft.Icons.SEARCH,
                                        on_click=lambda e: self.search(), height=48)],
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([card(self.results, expand=3), card(self.queue, expand=2)],
                       expand=True, spacing=16, vertical_alignment=ft.CrossAxisAlignment.STRETCH),
            ],
            expand=True, spacing=20,
        )

    def focus(self):
        try:
            self.query.focus()
        except Exception:
            pass

    # ---------------------------------------------------------- búsqueda
    def search(self):
        s, t = self.app.state, self.app.t
        query = (s.search_query or "").strip()
        if not query:
            self.app.toast(t("search_empty"))
            return
        if s.searching:
            return
        s.searching = True
        self.spinner.visible = True
        _safe_update(self.app, self.spinner)
        self.app.page.run_thread(self._search_worker, query)

    def _search_worker(self, query):
        s, t = self.app.state, self.app.t
        try:
            entries = ytdlp.search(query, 15)
            s.search_results = [{
                "url": ytdlp.entry_url(e),
                "title": e.get("title") or "?",
                "channel": e.get("channel") or e.get("uploader") or "",
                "duration": e.get("duration"),
                "is_playlist": ytdlp.is_playlist_entry(e),
            } for e in entries if ytdlp.entry_url(e)]
            if not s.search_results:
                self.app.toast(t("search_no_results"))
        except Exception as exc:
            logger.exception("Búsqueda fallida")
            self.app.alert(t("error_title"), str(exc), icon=ft.Icons.ERROR_OUTLINE, color=ft.Colors.ERROR)
        finally:
            s.searching = False
            self.spinner.visible = False
            self._render_results()
            _safe_update(self.app, self.spinner)
            _safe_update(self.app, self.results)

    # ---------------------------------------------------------- render
    def _render_results(self):
        t, s = self.app.t, self.app.state
        queued = {item["url"] for item in s.search_queue}
        rows = []
        for r in s.search_results:
            subtitle = " · ".join(x for x in [t("playlist") if r["is_playlist"] else r["channel"],
                                              fmt_duration(r["duration"])] if x)
            if r["is_playlist"]:
                trailing = ft.TextButton(content=t("download_playlist"), icon=ft.Icons.DOWNLOAD,
                                         disabled=self.app.downloads.busy,
                                         on_click=lambda e, r=r: self._download_playlist(r))
                icon = ft.Icons.PLAYLIST_PLAY
            else:
                in_queue = r["url"] in queued
                trailing = ft.IconButton(
                    icon=ft.Icons.CHECK if in_queue else ft.Icons.ADD,
                    tooltip=t("already_in_queue") if in_queue else t("add_to_queue"),
                    disabled=in_queue,
                    on_click=lambda e, r=r: self._add(r),
                )
                icon = ft.Icons.MUSIC_NOTE
            rows.append(item_tile(r["title"], subtitle, icon, trailing))
        body = (ft.ListView(rows, expand=True, spacing=2) if rows
                else empty_state(ft.Icons.TRAVEL_EXPLORE, t("search_subtitle")))
        self.results.controls = [list_header(t("results"), len(rows) or None), body]

    def _render_queue(self):
        t, s = self.app.t, self.app.state
        rows = [item_tile(item["title"], item.get("channel"), ft.Icons.MUSIC_NOTE,
                          ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, tooltip=t("remove"),
                                        on_click=lambda e, i=i: self._remove(i)))
                for i, item in enumerate(s.search_queue)]
        body = (ft.ListView(rows, expand=True, spacing=2) if rows
                else empty_state(ft.Icons.QUEUE_MUSIC, t("queue_empty")))
        actions = [ft.TextButton(content=t("clear"), on_click=lambda e: self._clear())] if rows else []
        self.queue.controls = [
            list_header(t("queue"), len(rows) or None, actions),
            body,
            ft.Row([_download_button(self.app, len(rows), lambda e: self._download_queue())],
                   alignment=ft.MainAxisAlignment.END),
        ]

    def _refresh_lists(self):
        self._render_results()
        self._render_queue()
        _safe_update(self.app, self.results)
        _safe_update(self.app, self.queue)

    # ---------------------------------------------------------- acciones
    def _add(self, result):
        s = self.app.state
        if any(i["url"] == result["url"] for i in s.search_queue):
            return
        s.search_queue.append(dict(result))
        self._refresh_lists()

    def _remove(self, index):
        del self.app.state.search_queue[index]
        self._refresh_lists()

    def _clear(self):
        self.app.state.search_queue.clear()
        self._refresh_lists()

    def _download_queue(self):
        snapshot = list(self.app.state.search_queue)
        urls = {i["url"] for i in snapshot}

        def on_success():
            s = self.app.state
            s.search_queue = [i for i in s.search_queue if i["url"] not in urls]
            self.app.refresh_view()

        self.app.downloads.start(lambda: [DownloadItem(i["url"], i["title"], title_hint=i["title"]) for i in snapshot], on_success)

    def _download_playlist(self, result):
        folder = self.app.config.music_folder
        not_playlist = self.app.t("error_not_playlist")

        names = {}

        def prepare():
            names["title"], items = playlist_items(result["url"], folder)
            if not items:
                raise ValueError(not_playlist)
            return items

        self.app.downloads.start(prepare, after=lambda items: write_items_playlist(items, names.get("title") or "Playlist"))


# ============================================================== Enlaces
class SongsView:
    def __init__(self, app):
        self.app = app

    def build(self):
        t, s = self.app.t, self.app.state
        self.url = _input(s.song_url, t("url_hint"),
                          lambda e: setattr(s, "song_url", e.control.value),
                          lambda e: self.add(), ft.Icons.LINK)
        self.url.autofocus = True
        self.spinner = ft.ProgressRing(width=22, height=22, stroke_width=2.5, visible=s.checking_link)
        self.list = _card_column()
        self._render()
        return ft.Column(
            [
                page_header(t("songs_title"), t("songs_subtitle")),
                ft.Row([self.url, self.spinner,
                        ft.FilledButton(content=t("add"), icon=ft.Icons.ADD, on_click=lambda e: self.add(), height=48)],
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                card(self.list, expand=True),
            ],
            expand=True, spacing=20,
        )

    def _render(self):
        t, s = self.app.t, self.app.state
        rows = [item_tile(song["title"], " · ".join(x for x in [song["author"], fmt_duration(song.get("duration"))] if x),
                          ft.Icons.MUSIC_NOTE,
                          ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, tooltip=t("remove"),
                                        on_click=lambda e, i=i: self._remove(i)))
                for i, song in enumerate(s.songs)]
        body = (ft.ListView(rows, expand=True, spacing=2) if rows
                else empty_state(ft.Icons.LINK, t("songs_empty")))
        actions = [ft.TextButton(content=t("clear"), on_click=lambda e: self._clear())] if rows else []
        self.list.controls = [
            list_header(t("nav_songs"), len(rows) or None, actions),
            body,
            ft.Row([_download_button(self.app, len(rows), lambda e: self._download())],
                   alignment=ft.MainAxisAlignment.END),
        ]

    def _refresh(self):
        self._render()
        _safe_update(self.app, self.list)

    def add(self):
        t, s = self.app.t, self.app.state
        url = (s.song_url or "").strip()
        if not URL_RE.match(url):
            self.app.toast(t("error_invalid_url"))
            return
        if "playlist?list=" in url:
            self.app.toast(t("error_playlist_in_songs"))
            return
        if any(song["url"] == url for song in s.songs):
            self.app.toast(t("already_in_queue"))
            return
        if s.checking_link:
            return
        s.checking_link = True
        self.spinner.visible = True
        _safe_update(self.app, self.spinner)
        self.app.page.run_thread(self._check_worker, url)

    def _check_worker(self, url):
        t, s = self.app.t, self.app.state
        try:
            info = ytdlp.extract_info(url, flat=True)
            if "entries" in info or ytdlp.is_playlist_entry(info):
                self.app.toast(t("error_playlist_in_songs"))
                return
            s.songs.append({
                "url": url,
                "title": info.get("title") or url,
                "author": info.get("uploader") or info.get("channel") or "",
                "duration": info.get("duration"),
            })
            s.song_url = ""
            self.url.value = ""
            _safe_update(self.app, self.url)
            self._refresh()
        except Exception as exc:
            logger.exception("Enlace no válido: %s", url)
            self.app.alert(t("error_title"), str(exc), icon=ft.Icons.ERROR_OUTLINE, color=ft.Colors.ERROR)
        finally:
            s.checking_link = False
            self.spinner.visible = False
            _safe_update(self.app, self.spinner)

    def _remove(self, index):
        del self.app.state.songs[index]
        self._refresh()

    def _clear(self):
        self.app.state.songs.clear()
        self._refresh()

    def _download(self):
        snapshot = list(self.app.state.songs)
        urls = {song["url"] for song in snapshot}

        def on_success():
            s = self.app.state
            s.songs = [song for song in s.songs if song["url"] not in urls]
            self.app.refresh_view()

        items = [DownloadItem(song["url"], f"{song['title']} - {song['author']}".strip(" -"), title_hint=song["title"])
                 for song in snapshot]
        self.app.downloads.start(lambda: items, on_success)


# ============================================================== Listas
class PlaylistView:
    def __init__(self, app):
        self.app = app

    def build(self):
        t, s = self.app.t, self.app.state
        self.url = _input(s.playlist_url, t("playlist_hint"),
                          lambda e: setattr(s, "playlist_url", e.control.value),
                          lambda e: self.download(), ft.Icons.PLAYLIST_PLAY)
        self.url.autofocus = True
        folder = self.app.config.music_folder
        return ft.Column(
            [
                page_header(t("playlist_title"), t("playlist_subtitle")),
                ft.Row([self.url,
                        ft.FilledButton(content=t("download"), icon=ft.Icons.DOWNLOAD, height=48,
                                        disabled=self.app.downloads.busy, on_click=lambda e: self.download())],
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                card(ft.Row([
                    ft.Icon(ft.Icons.FOLDER_OUTLINED, color=MUTED),
                    ft.Text(folder, color=MUTED, expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.TextButton(content=t("open_folder"), on_click=lambda e: self.app.open_music_folder()),
                ])),
            ],
            spacing=20,
        )

    def download(self):
        t, s = self.app.t, self.app.state
        url = (s.playlist_url or "").strip()
        if not URL_RE.match(url):
            self.app.toast(t("error_invalid_url"))
            return
        folder = self.app.config.music_folder
        not_playlist = t("error_not_playlist")

        names = {}

        def prepare():
            names["title"], items = playlist_items(url, folder)
            if not items:
                raise ValueError(not_playlist)
            return items

        def on_success():
            s.playlist_url = ""
            self.app.refresh_view()

        self.app.downloads.start(prepare, on_success,
                                 after=lambda items: write_items_playlist(items, names.get("title") or "Playlist"))


# ============================================================== Spotify
class SpotifyView:
    """Importa una playlist, álbum o canción de Spotify (enlace o CSV), deja revisar
    qué vídeo se ha elegido para cada canción y descarga solo lo que falta."""

    def __init__(self, app):
        self.app = app

    def build(self):
        t, s = self.app.t, self.app.state
        self.link = _input(s.spotify_link, t("spotify_link_hint"),
                           lambda e: setattr(s, "spotify_link", e.control.value),
                           lambda e: self.load_link(), ft.Icons.LINK)
        self.status = ft.Text(self._status_text(), color=MUTED)
        self.progress = ft.ProgressBar(value=None, visible=s.spotify_loading, bar_height=4, border_radius=2)
        self.link_btn = ft.FilledButton(content=t("spotify_load_link"), icon=ft.Icons.DOWNLOAD_FOR_OFFLINE,
                                        on_click=lambda e: self.load_link(), disabled=s.spotify_loading, height=48)
        self.load_btn = ft.OutlinedButton(content=t("spotify_load"), icon=ft.Icons.UPLOAD_FILE,
                                          on_click=self.pick_csv, disabled=s.spotify_loading, height=48)
        self.list = _card_column()
        self._render()
        return ft.Column(
            [
                page_header(t("spotify_title"), t("spotify_subtitle")),
                ft.Row([self.link, self.link_btn, self.load_btn], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                self.status,
                self.progress,
                card(self.list, expand=True),
            ],
            expand=True, spacing=12,
        )

    # ---------------------------------------------------------- render
    def _status_text(self):
        s, t = self.app.state, self.app.t
        if s.spotify_loading:
            return s.spotify_status
        if s.spotify_total:
            return t("spotify_summary", len(s.spotify_matches), len(s.spotify_missing), len(s.spotify_done))
        return ""

    def _render(self):
        t, s = self.app.t, self.app.state
        rows = []
        for i, track in enumerate(s.spotify_missing):
            rows.append(item_tile(
                self._label(track), t("spotify_not_found"), ft.Icons.WARNING_AMBER_ROUNDED,
                ft.Row([
                    ft.TextButton(content=t("spotify_search_manual"), icon=ft.Icons.SEARCH,
                                  on_click=lambda e, i=i: self._open_chooser(missing_index=i)),
                    ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, tooltip=t("remove"),
                                  on_click=lambda e, i=i: self._remove_missing(i)),
                ], tight=True, spacing=0)))
        for i, m in enumerate(s.spotify_matches):
            diff = m.duration_diff
            detail = f"→ {m.video_title}"
            if diff is not None:
                detail += f"  ·  {t('spotify_diff', int(round(diff)))}"
            rows.append(item_tile(
                self._label(m.track), detail, ft.Icons.MUSIC_NOTE,
                ft.Row([
                    ft.IconButton(icon=ft.Icons.OPEN_IN_NEW, tooltip=t("spotify_preview"),
                                  on_click=lambda e, url=m.url: webbrowser.open(url)),
                    ft.IconButton(icon=ft.Icons.SWAP_HORIZ, tooltip=t("spotify_change"),
                                  on_click=lambda e, i=i: self._open_chooser(match_index=i)),
                    ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, tooltip=t("remove"),
                                  on_click=lambda e, i=i: self._remove(i)),
                ], tight=True, spacing=0)))

        if rows:
            body = ft.ListView(rows, expand=True, spacing=2)
        elif s.spotify_total and s.spotify_done:
            body = empty_state(ft.Icons.CHECK_CIRCLE_OUTLINE, t("spotify_all_downloaded"))
        else:
            body = empty_state(ft.Icons.LIBRARY_MUSIC, t("spotify_empty"))
        footer = [_download_button(self.app, len(s.spotify_matches), lambda e: self._download())]
        if s.spotify_truncated:
            footer.insert(0, ft.Row([ft.Icon(ft.Icons.INFO_OUTLINE, size=18, color=ft.Colors.TERTIARY),
                                     ft.Text(t("spotify_truncated"), size=12, color=MUTED, expand=True)],
                                    expand=True))
        self.list.controls = [
            list_header(s.spotify_name or t("nav_spotify"), len(rows) or None),
            body,
            ft.Row(footer, alignment=ft.MainAxisAlignment.END, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ]

    @staticmethod
    def _label(track):
        return f"{track.title} — {track.artist}".strip(" —")

    def _refresh(self):
        self._render()
        self.status.value = self._status_text()
        _safe_update(self.app, self.list)
        _safe_update(self.app, self.status)

    # ---------------------------------------------------------- carga
    def load_link(self):
        t, s = self.app.t, self.app.state
        text = (s.spotify_link or "").strip()
        if not spotify_link.is_spotify_link(text):
            self.app.toast(t("spotify_invalid_link"))
            return
        if not s.spotify_loading:
            self.app.page.run_thread(self._load_worker, text, True)

    async def pick_csv(self, e):
        t = self.app.t
        files = await self.app.file_picker.pick_files(
            dialog_title=t("spotify_pick"), allowed_extensions=["csv"],
            file_type=ft.FilePickerFileType.CUSTOM)
        if files and files[0].path and not self.app.state.spotify_loading:
            self.app.page.run_thread(self._load_worker, files[0].path, False)

    def _load_worker(self, source, is_link):
        t, s, cfg = self.app.t, self.app.state, self.app.config
        s.spotify_loading = True
        s.spotify_status = t("spotify_reading")
        self.progress.value = None
        self._sync_status()
        try:
            truncated = False
            if is_link:
                collection = spotify_link.load(source)
                name, tracks, truncated = collection.name, collection.tracks, collection.truncated
            else:
                tracks = spotify.read_csv(source)
                name = os.path.splitext(os.path.basename(source))[0] or "Spotify"
            if not tracks:
                self.app.toast(t("spotify_no_tracks"))
                return

            # Sincronización: lo que ya está en la carpeta de la lista no se vuelve a buscar
            pending, done = spotify.split_downloaded(tracks, spotify_folder(cfg.music_folder, name))
            s.spotify_status = t("spotify_resolving", 0, len(pending), 0)
            self._sync_status()

            def on_progress(done_count, total, found):
                s.spotify_status = t("spotify_resolving", done_count, total, found)
                self.progress.value = done_count / total if total else None
                self._sync_status()

            matches, missing = spotify.resolve(pending, on_progress) if pending else ([], [])
            s.spotify_name, s.spotify_tracks, s.spotify_total = name, tracks, len(tracks)
            s.spotify_matches, s.spotify_missing, s.spotify_done = matches, missing, done
            s.spotify_truncated = truncated
        except spotify_link.SpotifyLinkError as exc:
            self.app.alert(t("error_title"), str(exc), icon=ft.Icons.ERROR_OUTLINE, color=ft.Colors.ERROR)
        except Exception as exc:
            logger.exception("Fallo al importar de Spotify")
            self.app.alert(t("error_title"), str(exc), icon=ft.Icons.ERROR_OUTLINE, color=ft.Colors.ERROR)
        finally:
            s.spotify_loading = False
            self.progress.value = None
            self._render()
            self._sync_status()
            _safe_update(self.app, self.list)

    def _sync_status(self):
        s = self.app.state
        self.status.value = self._status_text()
        self.progress.visible = s.spotify_loading
        self.load_btn.disabled = self.link_btn.disabled = s.spotify_loading
        for c in (self.status, self.progress, self.load_btn, self.link_btn):
            _safe_update(self.app, c)

    # ---------------------------------------------------------- edición
    def _remove(self, index):
        del self.app.state.spotify_matches[index]
        self._refresh()

    def _remove_missing(self, index):
        del self.app.state.spotify_missing[index]
        self._refresh()

    def _open_chooser(self, match_index=None, missing_index=None):
        """Diálogo para elegir otro vídeo (o buscar uno para una canción no encontrada)."""
        t, s = self.app.t, self.app.state
        if match_index is not None:
            match = s.spotify_matches[match_index]
            track = match.track
            current = [spotify.Candidate(match.url, match.video_title, duration=match.video_duration, score=1.0)]
            known = current + list(match.alternatives)
        else:
            track = s.spotify_missing[missing_index]
            known = []

        primary = (track.artist.replace(";", ",").split(",")[0]).strip()
        query = ft.TextField(value=f"{primary} {track.title}".strip(), hint_text=t("chooser_hint"),
                             prefix_icon=ft.Icons.SEARCH, expand=True, border_radius=12, filled=True,
                             border_width=0, on_submit=lambda e: search())
        spinner = ft.ProgressRing(width=20, height=20, stroke_width=2.5, visible=False)
        results = ft.ListView(expand=True, spacing=2)
        candidates = list(known)

        def choose(candidate):
            new_match = spotify.match_with(track, candidate, candidates)
            if match_index is not None:
                s.spotify_matches[match_index] = new_match
            else:
                del s.spotify_missing[missing_index]
                s.spotify_matches.insert(0, new_match)
            spotify.remember_choice(track, candidate)
            self.app.page.pop_dialog()
            self._refresh()

        def row(c):
            diff = abs(c.duration - track.duration) if c.duration and track.duration else None
            meta = " · ".join(x for x in [c.channel, fmt_duration(c.duration),
                                          t("spotify_diff", int(round(diff))) if diff is not None else ""] if x)
            return ft.ListTile(
                leading=ft.Icon(ft.Icons.CHECK_CIRCLE if c.valid else ft.Icons.HELP_OUTLINE,
                                color=ft.Colors.PRIMARY if c.valid else ft.Colors.OUTLINE,
                                tooltip=t("chooser_valid") if c.valid else t("chooser_unverified")),
                title=ft.Text(c.title, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                subtitle=ft.Text(meta, size=12, color=MUTED, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                trailing=ft.IconButton(icon=ft.Icons.OPEN_IN_NEW, tooltip=t("spotify_preview"),
                                       on_click=lambda e, url=c.url: webbrowser.open(url)),
                on_click=lambda e, c=c: choose(c),
                dense=True, shape=ft.RoundedRectangleBorder(radius=12),
            )

        def show(message=None):
            if candidates:
                results.controls = [row(c) for c in candidates]
            else:
                results.controls = [ft.Container(ft.Text(message or t("chooser_empty"), color=MUTED),
                                                 padding=16, alignment=ft.Alignment.CENTER)]
            _safe_update(self.app, results)

        def worker(text):
            try:
                found = spotify.search_candidates(track, text)
                seen = {c.url for c in known}
                candidates[:] = known + [c for c in found if c.url not in seen]
                message = t("chooser_none")
            except Exception as exc:
                logger.exception("Búsqueda manual fallida")
                message = t("chooser_failed", exc)
            spinner.visible = False
            _safe_update(self.app, spinner)
            show(message)

        def search():
            text = (query.value or "").strip()
            if not text:
                return
            spinner.visible = True
            _safe_update(self.app, spinner)
            self.app.page.run_thread(worker, text)

        show()
        self.app.page.show_dialog(ft.AlertDialog(
            title=ft.Column([ft.Text(t("chooser_title")),
                             ft.Text(self._label(track) + (f"  ·  {fmt_duration(track.duration)}" if track.duration else ""),
                                     size=13, color=MUTED)], spacing=2),
            content=ft.Container(
                ft.Column([ft.Row([query, spinner], vertical_alignment=ft.CrossAxisAlignment.CENTER), results],
                          spacing=12, expand=True),
                width=620, height=420),
            actions=[ft.TextButton(content=t("close"), on_click=lambda e: self.app.page.pop_dialog())],
        ))
        if not candidates:
            search()

    # ---------------------------------------------------------- descarga
    def _download(self):
        s = self.app.state
        matches, name, folder = list(s.spotify_matches), s.spotify_name, self.app.config.music_folder
        all_tracks = list(s.spotify_tracks)
        downloaded = {id(m) for m in matches}

        def on_success():
            s.spotify_done = s.spotify_done + [m.track for m in matches]
            s.spotify_matches = [m for m in s.spotify_matches if id(m) not in downloaded]
            self.app.refresh_view()

        self.app.downloads.start(lambda: spotify_items(matches, folder, name), on_success,
                                 after=lambda items: write_spotify_playlist(folder, name, all_tracks))
