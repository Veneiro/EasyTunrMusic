"""Secciones de Audio, Ajustes y Acerca de."""
import os
import webbrowser

import flet as ft

from core import __version__, paths, tools
from core.config import AUDIO_KEYS
from core.settings import LOSSY_CODECS
from .theme import ACCENTS
from .widgets import MUTED, app_logo, card, dropdown, page_header, section, setting_switch

REPO_URL = "https://github.com/Veneiro/EasyTunrMusic"

CODECS = [("mp3", "MP3"), ("aac", "AAC (M4A)"), ("opus", "Opus"),
          ("flac", "FLAC"), ("alac", "ALAC (M4A)"), ("wav", "WAV")]
BITRATES = ["96", "128", "160", "192", "256", "320"]
SAMPLE_RATES = {
    "mp3": ["32000", "44100", "48000"],
    "aac": ["44100", "48000"],
    "opus": ["48000"],
}
LOSSLESS_RATES = ["44100", "48000", "96000", "192000"]


class AudioView:
    def __init__(self, app):
        self.app = app

    def _set(self, key, value, rerender=False):
        self.app.config.set(key, value)
        if rerender:
            self.app.refresh_view()

    def build(self):
        t, cfg = self.app.t, self.app.config
        codec = cfg.get("codec")
        lossy = codec in LOSSY_CODECS
        rates = SAMPLE_RATES.get(codec, LOSSLESS_RATES)
        if cfg.get("sample_rate") not in rates:
            cfg.set("sample_rate", rates[0] if "44100" not in rates else "44100")
        bitrates = BITRATES if cfg.get("bitrate") in BITRATES else BITRATES + [cfg.get("bitrate")]

        fmt = section(t("format_section"), [
            ft.ResponsiveRow([
                dropdown(t("codec"), codec, CODECS,
                         lambda e: self._set("codec", e.control.value, rerender=True)),
                dropdown(t("channels"), cfg.get("channels"),
                         [("stereo", t("ch_stereo")), ("mono", t("ch_mono")),
                          ("multichannel", t("ch_multichannel"))],
                         lambda e: self._set("channels", e.control.value)),
                dropdown(t("bitrate"), cfg.get("bitrate"), [(b, b) for b in bitrates],
                         lambda e: self._set("bitrate", e.control.value), disabled=not lossy,
                         col={"xs": 12, "md": 4}),
                dropdown(t("bit_depth"), cfg.get("bit_depth"), [(d, d) for d in ("16", "24", "32")],
                         lambda e: self._set("bit_depth", e.control.value), disabled=lossy,
                         col={"xs": 12, "md": 4}),
                dropdown(t("sample_rate"), cfg.get("sample_rate"), [(r, r) for r in rates],
                         lambda e: self._set("sample_rate", e.control.value),
                         col={"xs": 12, "md": 4}),
            ], run_spacing=12),
            ft.Text(t("lossless_note"), size=12, color=MUTED, visible=not lossy),
        ], icon=ft.Icons.GRAPHIC_EQ)

        norm = cfg.get("normalization")

        def lufs_field(key, label):
            return ft.TextField(label=label, value=str(cfg.get(key)), width=150,
                                on_blur=lambda e: self._set(key, e.control.value.strip() or cfg.get(key)),
                                on_submit=lambda e: self._set(key, e.control.value.strip() or cfg.get(key)))

        volume = section(t("volume_section"), [
            ft.ResponsiveRow([
                dropdown(t("normalization"), norm,
                         [("off", t("norm_off")), ("lufs_14", t("norm_lufs_14")),
                          ("lufs_23", t("norm_lufs_23")), ("custom", t("norm_custom"))],
                         lambda e: self._set("normalization", e.control.value, rerender=True)),
            ]),
            ft.Row([lufs_field("custom_lufs_i", t("lufs_i")),
                    lufs_field("custom_lufs_lra", t("lufs_lra")),
                    lufs_field("custom_lufs_tp", t("lufs_tp"))],
                   wrap=True, visible=norm == "custom"),
            setting_switch(t("dynamic_compression"), t("dynamic_compression_hint"),
                           cfg.get("dynamic_compression"),
                           lambda e: self._set("dynamic_compression", e.control.value)),
        ], icon=ft.Icons.VOLUME_UP)

        extras = section(t("extras_section"), [
            setting_switch(t("extract_audio"), t("extract_audio_hint"), cfg.get("extract_audio"),
                           lambda e: self._set("extract_audio", e.control.value)),
            setting_switch(t("metadata"), t("metadata_hint"), cfg.get("metadata"),
                           lambda e: self._set("metadata", e.control.value)),
            setting_switch(t("extract_thumbnail"), None, cfg.get("extract_thumbnail"),
                           lambda e: self._set("extract_thumbnail", e.control.value)),
            setting_switch(t("keep_original"), None, cfg.get("keep_original"),
                           lambda e: self._set("keep_original", e.control.value)),
        ], icon=ft.Icons.TUNE)

        return ft.Column(
            [
                ft.Row([page_header(t("audio_title"), t("audio_subtitle")), ft.Container(expand=True),
                        ft.TextButton(content=t("reset"), icon=ft.Icons.RESTART_ALT,
                                      on_click=lambda e: self._reset())]),
                fmt, volume, extras,
            ],
            spacing=16, scroll=ft.ScrollMode.AUTO, expand=True,
        )

    def _reset(self):
        self.app.config.reset(AUDIO_KEYS)
        self.app.toast(self.app.t("reset_done"))
        self.app.refresh_view()


class SettingsView:
    def __init__(self, app):
        self.app = app

    def build(self):
        t, cfg, s = self.app.t, self.app.config, self.app.state

        theme_mode = ft.SegmentedButton(
            segments=[
                ft.Segment(value="system", label=ft.Text(t("theme_system")), icon=ft.Icon(ft.Icons.BRIGHTNESS_AUTO)),
                ft.Segment(value="light", label=ft.Text(t("theme_light")), icon=ft.Icon(ft.Icons.LIGHT_MODE)),
                ft.Segment(value="dark", label=ft.Text(t("theme_dark")), icon=ft.Icon(ft.Icons.DARK_MODE)),
            ],
            selected=[cfg.get("theme_mode")],
            on_change=lambda e: self._set_theme(e.control.selected[0]),
        )

        current_accent = cfg.get("accent")
        accents = ft.Row([
            ft.Container(
                width=36, height=36, border_radius=18, bgcolor=color, tooltip=name.capitalize(),
                border=ft.Border.all(3, ft.Colors.ON_SURFACE) if name == current_accent else None,
                content=ft.Icon(ft.Icons.CHECK, color=ft.Colors.WHITE, size=18) if name == current_accent else None,
                alignment=ft.Alignment.CENTER,
                on_click=lambda e, n=name: self._set_accent(n),
                ink=True,
            )
            for name, color in ACCENTS.items()
        ], spacing=10, wrap=True)

        appearance = section(t("appearance_section"), [
            ft.ResponsiveRow([
                dropdown(t("language"), cfg.get("language"), [("es", "Español"), ("en", "English")],
                         lambda e: self.app.set_language(e.control.value)),
            ]),
            ft.Text(t("theme"), size=13, color=MUTED), theme_mode,
            ft.Text(t("accent"), size=13, color=MUTED), accents,
        ], icon=ft.Icons.PALETTE)

        self.threads_label = ft.Text(str(cfg.threads), weight=ft.FontWeight.W_600, width=24)
        downloads = section(t("downloads_section"), [
            ft.Text(t("destination"), size=13, color=MUTED),
            ft.Row([
                ft.TextField(value=cfg.music_folder, read_only=True, expand=True, border_radius=12,
                             prefix_icon=ft.Icons.FOLDER_OUTLINED),
                ft.OutlinedButton(content=t("change"), on_click=self._pick_folder),
                ft.IconButton(icon=ft.Icons.OPEN_IN_NEW, tooltip=t("open_folder"),
                              on_click=lambda e: self.app.open_music_folder()),
            ]),
            ft.Text(t("threads"), size=13, color=MUTED),
            ft.Row([
                ft.Slider(value=cfg.threads, min=1, max=8, divisions=7, label="{value}", expand=True,
                          on_change=self._threads_changing, on_change_end=self._threads_changed),
                self.threads_label,
            ]),
        ], icon=ft.Icons.DOWNLOAD)

        version = s.ytdlp_version
        self.version_text = ft.Text(t("ytdlp_version", version) if version else t("ytdlp_unknown"))
        self.update_btn = ft.OutlinedButton(content=t("check_updates"), icon=ft.Icons.REFRESH,
                                            on_click=lambda e: self._check_updates())
        components = section(t("tools_section"), [
            ft.Row([ft.Icon(ft.Icons.EXTENSION, color=MUTED), self.version_text, ft.Container(expand=True),
                    self.update_btn,
                    ft.TextButton(content=t("open_logs"), on_click=lambda e: os.startfile(paths.log_file()))],
                   wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ], icon=ft.Icons.BUILD_OUTLINED)

        if version is None:
            self.app.page.run_thread(self._load_version)

        return ft.Column(
            [
                ft.Row([page_header(t("settings_title")), ft.Container(expand=True),
                        ft.TextButton(content=t("reset"), icon=ft.Icons.RESTART_ALT,
                                      on_click=lambda e: self._reset())]),
                appearance, downloads, components,
            ],
            spacing=16, scroll=ft.ScrollMode.AUTO, expand=True,
        )

    # ---------------------------------------------------------- acciones
    def _set_theme(self, mode):
        self.app.config.set("theme_mode", mode)
        self.app.apply_theme()

    def _set_accent(self, name):
        self.app.config.set("accent", name)
        self.app.apply_theme()
        self.app.refresh_view()

    def _threads_changing(self, e):
        self.threads_label.value = str(int(e.control.value))
        self.threads_label.update()

    def _threads_changed(self, e):
        self.app.config.set("threads", str(int(e.control.value)))

    async def _pick_folder(self, e):
        folder = await self.app.file_picker.get_directory_path(
            dialog_title=self.app.t("destination"), initial_directory=self.app.config.music_folder)
        if folder:
            self.app.config.set("music_folder", folder)
            self.app.refresh_view()

    def _load_version(self):
        self.app.state.ytdlp_version = tools.ytdlp_version() or ""
        t = self.app.t
        v = self.app.state.ytdlp_version
        self.version_text.value = t("ytdlp_version", v) if v else t("ytdlp_unknown")
        self.app.ui(self._try_update, self.version_text)

    def _check_updates(self):
        t = self.app.t
        self.update_btn.disabled = True
        self.update_btn.content = t("checking_updates")
        self.update_btn.update()

        def worker():
            message = tools.update_ytdlp(force=True)
            self.app.state.ytdlp_version = None
            self.app.toast(message)
            self.update_btn.disabled = False
            self.update_btn.content = t("check_updates")
            self.app.ui(self._try_update, self.update_btn)
            self._load_version()

        self.app.page.run_thread(worker)

    @staticmethod
    def _try_update(control):
        try:
            control.update()
        except Exception:  # la sección ya no está en pantalla
            pass

    def _reset(self):
        cfg = self.app.config
        language_before = cfg.get("language")
        cfg.reset(["language", "theme_mode", "accent", "threads", "music_folder"])
        self.app.apply_theme()
        self.app.toast(self.app.t("reset_done"))
        if cfg.get("language") != language_before:
            self.app.set_language(cfg.get("language"))
        else:
            self.app.refresh_view()


class AboutView:
    def __init__(self, app):
        self.app = app

    def build(self):
        t = self.app.t

        def shortcut(keys, text):
            return ft.Row([
                ft.Container(ft.Text(keys, size=12, weight=ft.FontWeight.W_600),
                             bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, border_radius=6,
                             padding=ft.Padding(8, 4, 8, 4), width=90, alignment=ft.Alignment.CENTER),
                ft.Text(text),
            ], spacing=12)

        return ft.Column(
            [
                card(ft.Row([
                    app_logo(80),
                    ft.Column([
                        ft.Text("EasyTunrMusic", size=26, weight=ft.FontWeight.W_600),
                        ft.Text(f"v{__version__}", color=MUTED),
                        ft.Text(t("about_text")),
                    ], spacing=4, expand=True),
                ], spacing=20), padding=24),
                section(t("shortcuts"), [
                    shortcut("Ctrl + F", t("shortcut_search")),
                    shortcut("Ctrl + P", t("shortcut_pause")),
                    shortcut("Ctrl + O", t("shortcut_folder")),
                ], icon=ft.Icons.KEYBOARD),
                ft.Row([
                    ft.TextButton(content=t("source_code"), icon=ft.Icons.CODE,
                                  on_click=lambda e: webbrowser.open(REPO_URL)),
                    ft.Text("© 2025 Veneiro · MIT", color=MUTED),
                ]),
            ],
            spacing=16, scroll=ft.ScrollMode.AUTO, expand=True,
        )
