import tkinter as tk
from tkinter import ttk, filedialog
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import os
import json
import csv
from queue import Queue, Empty
from threading import Thread
from concurrent.futures import ThreadPoolExecutor, as_completed
from translations import TRANSLATIONS
from ui_components import create_search_tab, create_songs_tab, create_playlist_tab, create_spotify_csv_tab, create_audio_options_tab, create_options_tab, create_about_tab
from download_manager import download_search_playlist, start_songs_download, start_playlist_download, start_spotify_download
from core import paths, ytdlp
import logging
import re

class DownloaderApp:
    # Valores predeterminados para la configuración
    DEFAULT_CONFIG = {
        "language": "es",
        "theme": "litera",
        "threads": "4",
        "music_folder": None,  # Se establece en __init__ con paths.default_music_folder()
        "codec": "mp3",
        "bitrate": "192",
        "bit_depth": "16",
        "sample_rate": "44100",
        "channels": "stereo",
        "normalization": "off",
        "custom_lufs_i": "-14",
        "custom_lufs_lra": "11",
        "custom_lufs_tp": "-1.5",
        "extract_audio": True,
        "metadata": True,
        "extract_thumbnail": False,
        "keep_original": False,
        "dynamic_compression": False,
    }
    def __init__(self, root):
        self.root = root

        # Establecer el ícono de la ventana
        self.icon_path = paths.resource_path("icon.ico")
        self.root.iconbitmap(self.icon_path)

        # Tamaño de la ventana
        window_width = 980
        window_height = 680

        # Obtener tamaño de la pantalla
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()

        # Calcular posición centrada
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2

        # Configurar geometría de la ventana centrada
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        self.root.resizable(False, False)

        # Directorio persistente para la configuración
        self.config_dir = paths.config_dir()

        # Initialize music folder and linked variable *before* loading config
        self.music_folder = paths.default_music_folder()
        self.music_folder_var = tk.StringVar(value=self.music_folder)
        self.DEFAULT_CONFIG["music_folder"] = self.music_folder

        # Load configuration
        self.config_file = os.path.join(self.config_dir, "config.json")
        self.load_config()

        # Update music folder from config (if available)
        self.music_folder = self.config.get("music_folder") or paths.default_music_folder()
        self.music_folder_var.set(self.music_folder)
        self._ensure_music_folder()

        # Map legacy language names to codes
        self.language_map = {
            'Español': 'es',
            'Spanish': 'es',
            'English': 'en',
            'Inglés': 'en'
        }
        config_lang = self.config.get("language", "es")
        initial_lang = self.language_map.get(config_lang, config_lang)
        logging.debug(f"Initial language from config: {config_lang}, mapped to: {initial_lang}")

        # Initialize language_var
        self.language_var = tk.StringVar(value=initial_lang)
        self.language_var.trace_add("write", self.on_language_change)

        # Initialize theme_var and apply theme
        self.theme_var = tk.StringVar(value=self.config.get("theme", "litera"))
        self.theme_var.trace_add("write", lambda *args: [self.update_theme(), self.save_config()])

        # Initialize ttkbootstrap style with the loaded theme
        self.style = ttk.Style(self.theme_var.get())
        self.root.configure(bg=self.style.colors.bg)

        # Spinner de carga
        self.loading_spinner = ttk.Progressbar(self.root, mode='indeterminate', bootstyle=INFO)
        self.loading_spinner.place(relx=0.5, rely=0.5, anchor='center')
        self.loading_spinner.lower()

        # Initialize other variables
        self.search_query_var = tk.StringVar()
        self.song_entry_var = tk.StringVar()
        self.playlist_url_var = tk.StringVar()
        self.threads_var = tk.StringVar(value="4")
        self.codec_var = tk.StringVar(value=self.config.get("codec", "mp3"))
        self.bitrate_var = tk.StringVar(value=self.config.get("bitrate", "192"))
        self.bit_depth_var = tk.StringVar(value=self.config.get("bit_depth", "16"))
        self.sample_rate_var = tk.StringVar(value=self.config.get("sample_rate", "44100"))
        self.channels_var = tk.StringVar(value=self.config.get("channels", "stereo"))
        self.normalization_var = tk.StringVar(value=self.config.get("normalization", "off"))
        self.custom_lufs_i_var = tk.StringVar(value=self.config.get("custom_lufs_i", "-14"))
        self.custom_lufs_lra_var = tk.StringVar(value=self.config.get("custom_lufs_lra", "11"))
        self.custom_lufs_tp_var = tk.StringVar(value=self.config.get("custom_lufs_tp", "-1.5"))
        self.extract_audio_var = tk.BooleanVar(value=self.config.get("extract_audio", True))
        self.metadata_var = tk.BooleanVar(value=self.config.get("metadata", True))
        self.extract_thumbnail_var = tk.BooleanVar(value=self.config.get("extract_thumbnail", False))
        self.keep_original_var = tk.BooleanVar(value=self.config.get("keep_original", False))
        self.dynamic_compression_var = tk.BooleanVar(value=self.config.get("dynamic_compression", False))
        self.failed_videos = []
        self.global_progress_var = tk.DoubleVar(value=0.0)
        self.video_progress_var = tk.DoubleVar(value=0.0)
        self._ui_queue = Queue()  # actualizaciones de la UI enviadas desde otros hilos
        self.total_videos = 0
        self.completed_videos = 0
        self.is_paused = False
        self.is_cancelled = False
        self.current_job = None
        self.is_playlist = False
        self.song_urls = []
        self.search_song_urls = []
        self.spotify_song_urls = []
        self.spotify_playlist_name = "Spotify CSV"
        self.current_download_label = ""
        self.search_results = []
        self.quality_frame_visible = False
        self.bitrate_frame_visible = False
        self.lossless_frame_visible = False
        self.custom_norm_frame_visible = False
        self.progress_window = None
        self.widget_translation_keys = {}

        # Configure styles
        self.style.configure('TNotebook', background=self.style.colors.bg, tabmargins=(10, 10, 0, 0))
        self.style.configure('TNotebook.Tab', font=('Segoe UI', 10), padding=[18, 8], background='#FFFFFF')
        self.style.map('TNotebook.Tab', background=[('selected', '#FFFFFF'), ('active', '#E6E6E6')])
        self.style.configure('TButton', font=('Segoe UI', 10), padding=8, bootstyle=PRIMARY)
        self.style.configure('TLabel', font=('Segoe UI', 10))
        self.style.configure('TEntry', font=('Segoe UI', 10), padding=5)
        self.style.configure('TCombobox', font=('Segoe UI', 10), padding=5)
        self.style.configure('TCheckbutton', font=('Segoe UI', 10))
        self.style.configure('TProgressbar', thickness=10, bootstyle=INFO)

        # Create main interface with tabs
        self.notebook = ttk.Notebook(self.root, bootstyle=PRIMARY)
        self.notebook.pack(padx=20, pady=20, fill='both', expand=True)

        # Create tabs
        logging.debug("Creating tabs")
        self.search_tab = create_search_tab(self)
        self.songs_tab = create_songs_tab(self)
        self.playlist_tab = create_playlist_tab(self)
        self.spotify_csv_tab = create_spotify_csv_tab(self)
        self.audio_tab = create_audio_options_tab(self)
        self.options_tab = create_options_tab(self)
        self.about_tab = create_about_tab(self)

        # Add tabs
        lang = self.language_var.get()
        logging.debug(f"Adding tabs with language: {lang}")
        self.notebook.add(self.search_tab, text=TRANSLATIONS[lang]['search_tab'])
        self.notebook.tab(self.search_tab, state='normal')
        self.notebook.add(self.songs_tab, text=TRANSLATIONS[lang]['songs_tab'])
        self.notebook.tab(self.songs_tab, state='normal')
        self.notebook.add(self.playlist_tab, text=TRANSLATIONS[lang]['playlist_tab'])
        self.notebook.tab(self.playlist_tab, state='normal')
        self.notebook.add(self.spotify_csv_tab, text=TRANSLATIONS[lang]['spotify_tab'])
        self.notebook.tab(self.spotify_csv_tab, state='normal')
        self.notebook.add(self.audio_tab, text=TRANSLATIONS[lang]['audio_tab'])
        self.notebook.tab(self.audio_tab, state='normal')
        self.notebook.add(self.options_tab, text=TRANSLATIONS[lang]['options_tab'])
        self.notebook.tab(self.options_tab, state='normal')
        self.notebook.add(self.about_tab, text="About")

        # Set up trace callbacks
        self.codec_var.trace("w", self.update_codec_options)
        self.normalization_var.trace("w", self.update_norm_options)
        self.song_entry_var.trace("w", self.update_quality_frame)
        self.playlist_url_var.trace("w", self.update_quality_frame)
        self.search_query_var.trace("w", self.update_quality_frame)
        for var in [self.codec_var, self.bitrate_var, self.bit_depth_var, self.sample_rate_var, self.channels_var,
                    self.normalization_var, self.custom_lufs_i_var, self.custom_lufs_lra_var, self.custom_lufs_tp_var]:
            var.trace("w", lambda *args: self.save_config())
        for var in [self.extract_audio_var, self.metadata_var, self.extract_thumbnail_var, self.keep_original_var,
                    self.dynamic_compression_var]:
            var.trace("w", lambda *args: self.save_config())

        # Initialize visibility
        self.update_codec_options()
        self.update_norm_options()

        # Initial language and theme update
        self.update_theme()
        self.update_language()

        # Añadir shortcuts
        self.add_shortcuts()

        # Asociar la tecla Enter con la función correspondiente
        self.root.bind("<Return>", self.handle_enter_key)

        self._drain_ui_queue()

    def post(self, fn):
        """Programa fn en el hilo de tkinter. Seguro de llamar desde cualquier hilo."""
        self._ui_queue.put(fn)

    def _drain_ui_queue(self):
        try:
            while True:
                fn = self._ui_queue.get_nowait()
                try:
                    fn()
                except Exception:
                    logging.exception("Error al actualizar la interfaz")
        except Empty:
            pass
        self.root.after(50, self._drain_ui_queue)

    def reset_to_defaults(self, scope="all"):
        """Restaura la configuración a los valores predeterminados."""
        logging.debug(f"Resetting configuration to defaults (scope: {scope})")

        if scope in ["all", "general"]:
            self.language_var.set(self.DEFAULT_CONFIG["language"])
            self.theme_var.set(self.DEFAULT_CONFIG["theme"])
            self.threads_var.set(self.DEFAULT_CONFIG["threads"])
            self.music_folder_var.set(self.DEFAULT_CONFIG["music_folder"])
            self.music_folder = self.DEFAULT_CONFIG["music_folder"]
            if not os.path.exists(self.music_folder):
                os.makedirs(self.music_folder)

        if scope in ["all", "audio"]:
            self.codec_var.set(self.DEFAULT_CONFIG["codec"])
            self.bitrate_var.set(self.DEFAULT_CONFIG["bitrate"])
            self.bit_depth_var.set(self.DEFAULT_CONFIG["bit_depth"])
            self.sample_rate_var.set(self.DEFAULT_CONFIG["sample_rate"])
            self.channels_var.set(self.DEFAULT_CONFIG["channels"])
            self.normalization_var.set(self.DEFAULT_CONFIG["normalization"])
            self.custom_lufs_i_var.set(self.DEFAULT_CONFIG["custom_lufs_i"])
            self.custom_lufs_lra_var.set(self.DEFAULT_CONFIG["custom_lufs_lra"])
            self.custom_lufs_tp_var.set(self.DEFAULT_CONFIG["custom_lufs_tp"])
            self.extract_audio_var.set(self.DEFAULT_CONFIG["extract_audio"])
            self.metadata_var.set(self.DEFAULT_CONFIG["metadata"])
            self.extract_thumbnail_var.set(self.DEFAULT_CONFIG["extract_thumbnail"])
            self.keep_original_var.set(self.DEFAULT_CONFIG["keep_original"])
            self.dynamic_compression_var.set(self.DEFAULT_CONFIG["dynamic_compression"])

        # Actualizar la interfaz
        self.update_language()
        self.update_theme()
        self.update_codec_options()
        self.update_norm_options()

        # Guardar la configuración restaurada
        self.save_config()
        logging.debug("Configuration reset and saved")

    def handle_enter_key(self, event):
        """Handle the Enter key based on the active tab."""
        active_tab_index = self.notebook.index("current")
        if active_tab_index == 0:  # Pestaña de búsqueda
            self.open_search_results()
        elif active_tab_index == 1:  # Pestaña de canciones
            self.add_song()
        elif active_tab_index == 2:  # Pestaña de lista de reproducción
            start_playlist_download(self)

    def add_shortcuts(self):
        """Define keyboard shortcuts for the application."""
        self.root.bind("<Control-f>", lambda event: self.open_search_results())  # Buscar canciones o listas
        self.root.bind("<Control-d>", lambda event: start_songs_download(self))  # Descargar canciones
        self.root.bind("<Control-p>", lambda event: self.toggle_pause())         # Pausar/Continuar descarga
        self.root.bind("<Control-c>", lambda event: self.cancel_download())      # Cancelar descarga
        self.root.bind("<Control-Shift-E>", lambda event: self.language_var.set("es"))  # Cambiar idioma a Español
        self.root.bind("<Control-Shift-I>", lambda event: self.language_var.set("en"))  # Cambiar idioma a Inglés
        self.root.bind("<Control-o>", lambda event: self.open_destination_folder())     # Abrir carpeta de destino

    def open_destination_folder(self):
        """Open the destination folder in the file explorer."""
        folder = self.music_folder_var.get()
        if os.path.exists(folder):
            os.startfile(folder)
        else:
            self.show_result_message('error', TRANSLATIONS[self.language_var.get()]['error_invalid_folder'])

    def show_spinner(self):
        """Muestra el spinner de carga."""
        self.loading_spinner.lift()  # Trae el spinner al frente
        self.loading_spinner.start()  # Inicia la animación del spinner

    def hide_spinner(self):
        """Oculta el spinner de carga."""
        self.loading_spinner.stop()  # Detiene la animación del spinner
        self.loading_spinner.lower()  # Envía el spinner al fondo

    def on_language_change(self, *args):
        """Handle language_var changes."""
        new_lang = self.language_var.get()
        logging.debug(f"on_language_change triggered with language_var: {new_lang}")
        if new_lang not in ['es', 'en']:
            logging.warning(f"Invalid language code: {new_lang}, resetting to 'es'")
            self.language_var.set('es')
            return
        logging.debug(f"Calling update_language for: {new_lang}")
        self.update_language()
        self.save_config()

    def load_config(self):
        """Load configuration from config.json."""
        self.config = {}
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
        except Exception as e:
            logging.error(f"Error loading config: {e}")

    def _ensure_music_folder(self):
        """Crea la carpeta de destino; si no se puede (p. ej. disco quitado), vuelve a la predeterminada."""
        try:
            os.makedirs(self.music_folder, exist_ok=True)
        except OSError:
            logging.warning("No se puede usar la carpeta %s; se usa la predeterminada", self.music_folder)
            self.music_folder = paths.default_music_folder()
            self.music_folder_var.set(self.music_folder)
            os.makedirs(self.music_folder, exist_ok=True)

    def save_config(self):
        """Guarda la configuración en config.json."""
        self.config.update({
            "language": self.language_var.get(),
            "theme": self.theme_var.get(),
            "codec": self.codec_var.get(),
            "bitrate": self.bitrate_var.get(),
            "bit_depth": self.bit_depth_var.get(),
            "sample_rate": self.sample_rate_var.get(),
            "channels": self.channels_var.get(),
            "normalization": self.normalization_var.get(),
            "custom_lufs_i": self.custom_lufs_i_var.get(),
            "custom_lufs_lra": self.custom_lufs_lra_var.get(),
            "custom_lufs_tp": self.custom_lufs_tp_var.get(),
            "extract_audio": self.extract_audio_var.get(),
            "metadata": self.metadata_var.get(),
            "extract_thumbnail": self.extract_thumbnail_var.get(),
            "keep_original": self.keep_original_var.get(),
            "dynamic_compression": self.dynamic_compression_var.get(),
            "music_folder": self.music_folder_var.get(),  # Guardar la carpeta de destino
        })
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logging.error(f"Error saving config: {e}")

    def update_language(self):
        """Actualiza los textos de la interfaz y estilos según el idioma."""
        lang = self.language_var.get()
        logging.debug(f"Updating language to: {lang}")
        if lang not in TRANSLATIONS:
            logging.error(f"Language {lang} not found in TRANSLATIONS, defaulting to 'es'")
            lang = 'es'
            self.language_var.set(lang)

        self.root.title(TRANSLATIONS[lang]['title'])

        # Actualizar títulos de las pestañas
        self.notebook.tab(self.search_tab, text=TRANSLATIONS[lang]['search_tab'])
        self.notebook.tab(self.songs_tab, text=TRANSLATIONS[lang]['songs_tab'])
        self.notebook.tab(self.playlist_tab, text=TRANSLATIONS[lang]['playlist_tab'])
        self.notebook.tab(self.spotify_csv_tab, text=TRANSLATIONS[lang]['spotify_tab'])
        self.notebook.tab(self.audio_tab, text=TRANSLATIONS[lang]['audio_tab'])
        self.notebook.tab(self.options_tab, text=TRANSLATIONS[lang]['options_tab'])
        self.notebook.tab(self.about_tab, text=TRANSLATIONS[lang]['about_tab'])

        # Actualizar textos de los widgets
        self._update_widget_text(self.search_tab, lang)
        self._update_widget_text(self.songs_tab, lang)
        self._update_widget_text(self.playlist_tab, lang)
        self._update_widget_text(self.spotify_csv_tab, lang)
        self._update_widget_text(self.audio_tab, lang)
        self._update_widget_text(self.options_tab, lang)
        self._update_widget_text(self.about_tab, lang)

        # Actualizar etiquetas de estado
        self.search_status_label.config(text=TRANSLATIONS[lang]['status_waiting_search'])
        self.songs_status_label.config(text=TRANSLATIONS[lang]['status_waiting_songs'])
        self.playlist_status_label.config(text=TRANSLATIONS[lang]['status_waiting_playlist'])
        self.spotify_status_label.config(text=TRANSLATIONS[lang]['status_waiting_spotify'])

        # Reaplicar tema para garantizar consistencia
        self.update_theme()

    def _update_widget_text(self, widget, lang):
        """Recursively update widget texts based on stored translation keys."""
        widget_id = str(id(widget))
        if widget_id in self.widget_translation_keys:
            key = self.widget_translation_keys[widget_id]
            if isinstance(widget, (tk.Label, ttk.Label, tk.Button, ttk.Button, ttk.Checkbutton)):
                current_text = widget.cget('text')
                new_text = TRANSLATIONS[lang][key]
                if key == 'destination':
                    new_text = new_text.format(self.music_folder)
                widget.config(text=new_text)
                logging.debug(f"Updated widget {widget_id} (type: {type(widget).__name__}) from '{current_text}' to '{new_text}' for key: {key}")
            elif isinstance(widget, ttk.Combobox):
                if key == 'language_combobox':
                    language_map = {
                        "es": "Español",
                        "en": "English"
                    }
                    widget['values'] = list(language_map.values())
                    widget.set(language_map.get(self.language_var.get(), "Español"))
                    logging.debug(f"Updated language combobox {widget_id} to: {widget.get()}, values: {widget['values']}")
                elif key == 'theme_combobox':
                    theme_map = {
                        "litera": TRANSLATIONS[lang]['theme_litera'],
                        "darkly": TRANSLATIONS[lang]['theme_darkly'],
                        "flatly": TRANSLATIONS[lang]['theme_flatly']
                    }
                    widget['values'] = list(theme_map.values())
                    widget.set(theme_map.get(self.theme_var.get(), TRANSLATIONS[lang]['theme_litera']))
                    logging.debug(f"Updated theme combobox {widget_id} to: {widget.get()}")

        elif isinstance(widget, (tk.Frame, ttk.Frame)):
            logging.debug(f"Processing frame {widget_id} with {len(widget.winfo_children())} children")
            for child in widget.winfo_children():
                self._update_widget_text(child, lang)
        else:
            logging.debug(f"Skipped widget {widget_id} (type: {type(widget).__name__}) - no translation key")

    def update_theme(self):
        """Update interface theme."""
        theme = self.theme_var.get()
        logging.debug(f"Updating theme to: {theme}")
        self.style.theme_use(theme)
        self.root.configure(bg=self.style.colors.bg)

        # Reaplicar configuraciones de fuente personalizadas
        self.style.configure('TLabel', font=('Segoe UI', 10))
        self.style.configure('TButton', font=('Segoe UI', 10))
        self.style.configure('TEntry', font=('Segoe UI', 10))
        self.style.configure('TCombobox', font=('Segoe UI', 10))
        self.style.configure('TCheckbutton', font=('Segoe UI', 10))
        self.style.configure('TNotebook.Tab', font=('Segoe UI', 12))  # Pestañas más grandes

        # Actualizar colores de fondo para las pestañas y widgets
        for tab in [self.search_tab, self.songs_tab, self.playlist_tab, self.audio_tab, self.options_tab]:
            tab.configure(bg=self.style.colors.bg)
            for widget in tab.winfo_children():
                self._update_widget_style(widget)

    def _update_widget_style(self, widget):
        """Update widget styles recursively, applying bg only to supported widgets."""
        if isinstance(widget, (tk.Label, tk.Frame)):  # Only apply bg to tk.Label and tk.Frame
            widget.configure(bg=self.style.colors.bg)
            logging.debug(f"Set bg for widget {id(widget)} (type: {type(widget).__name__})")
        elif isinstance(widget, (ttk.Frame, ttk.Label, ttk.Button, ttk.Entry, ttk.Combobox, ttk.Checkbutton, ttk.Progressbar)):
            # ttk widgets are styled by the theme, no need to set bg
            logging.debug(f"Skipped bg for ttk widget {id(widget)} (type: {type(widget).__name__})")
        if isinstance(widget, (tk.Frame, ttk.Frame)):  # Recurse into frames
            for child in widget.winfo_children():
                self._update_widget_style(child)

    def update_destination_folder(self, new_folder):
        """Actualiza la carpeta de destino y guarda la configuración."""
        if new_folder:  # Solo actualizar si se proporciona una nueva carpeta
            self.music_folder_var.set(new_folder)
            self.music_folder = new_folder
            if not os.path.exists(new_folder):
                os.makedirs(new_folder)
            # Actualizar la configuración y guardarla
            self.config["music_folder"] = new_folder
            self.save_config()

    def create_progress_window(self, num_videos):
        """Create floating window for progress bars."""
        self.progress_window = tk.Toplevel(self.root)
        self.progress_window.iconbitmap(self.icon_path)
        lang = self.language_var.get()
        self.progress_window.title(TRANSLATIONS[lang]['progress_title'])
        self.progress_window.geometry("500x250")
        self.progress_window.resizable(False, False)
        self.progress_window.configure(bg=self.style.colors.bg)

        # Center window
        window_width = 500
        window_height = 250
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.progress_window.geometry(f"{window_width}x{window_height}+{x}+{y}")

        # Disable main window
        self.progress_window.grab_set()
        self.root.attributes('-disabled', 1)

        # Content frame
        self.content_frame = tk.Frame(self.progress_window, bg=self.style.colors.bg)
        self.content_frame.pack(padx=20, pady=20, fill='both', expand=True)

        # Progress components
        progress_label = ttk.Label(self.content_frame, text=TRANSLATIONS[lang]['progress_title'], font=('Segoe UI', 14, 'bold'))
        progress_label.pack(pady=10)
        self.widget_translation_keys[str(id(progress_label))] = 'progress_title'
        self.progress_status_label = tk.Label(self.content_frame, text=TRANSLATIONS[lang]['progress_status'], wraplength=450, bg=self.style.colors.bg, font=('Segoe UI', 10))
        self.progress_status_label.pack(pady=10)
        self.widget_translation_keys[str(id(self.progress_status_label))] = 'progress_status'

        # Video progress bar
        video_label = ttk.Label(self.content_frame, text=TRANSLATIONS[lang]['progress_video'])
        video_label.pack(pady=5)
        self.widget_translation_keys[str(id(video_label))] = 'progress_video'
        self.progress_video_bar = ttk.Progressbar(self.content_frame, orient="horizontal", length=450, mode="determinate", variable=self.video_progress_var)
        self.progress_video_bar.pack(pady=5)

        # Global progress bar (for multiple videos)
        if num_videos > 1:
            global_label = ttk.Label(self.content_frame, text=TRANSLATIONS[lang]['progress_global'])
            global_label.pack(pady=5)
            self.widget_translation_keys[str(id(global_label))] = 'progress_global'
            self.progress_global_bar = ttk.Progressbar(self.content_frame, orient="horizontal", length=450, mode="determinate", variable=self.global_progress_var)
            self.progress_global_bar.pack(pady=5)

        # Action buttons
        action_frame = tk.Frame(self.content_frame, bg=self.style.colors.bg)
        action_frame.pack(pady=10)
        self.progress_pause_button = ttk.Button(action_frame, text=TRANSLATIONS[lang]['pause_button'], command=self.toggle_pause, bootstyle=SECONDARY)
        self.progress_pause_button.pack(side='left', padx=5)
        self.widget_translation_keys[str(id(self.progress_pause_button))] = 'pause_button'
        cancel_button = ttk.Button(action_frame, text=TRANSLATIONS[lang]['cancel_button'], command=self.cancel_download, bootstyle=DANGER)
        cancel_button.pack(side='left', padx=5)
        self.widget_translation_keys[str(id(cancel_button))] = 'cancel_button'

    def show_result_message(self, message_type, message):
        """Show success, warning, or error message in floating window."""
        lang = self.language_var.get()
        # Los avisos de validación pueden llegar sin ventana de progreso abierta
        if not self.progress_window or not self.progress_window.winfo_exists():
            self.create_progress_window(1)
        # Clear existing content
        for widget in self.content_frame.winfo_children():
            widget.destroy()

        # Configure title and colors based on message type
        if message_type == 'success':
            self.progress_window.title(TRANSLATIONS[lang]['success_title'])
            icon = "✔"
            icon_color = 'green'
            bootstyle = SUCCESS
        elif message_type == 'warning':
            self.progress_window.title(TRANSLATIONS[lang]['warning_title'])
            icon = "⚠"
            icon_color = 'orange'
            bootstyle = WARNING
        else:  # error
            self.progress_window.title(TRANSLATIONS[lang]['error_title'])
            icon = "✖"
            icon_color = 'red'
            bootstyle = DANGER

        # Adjust window size
        self.progress_window.geometry("500x200")

        # Show icon and message
        ttk.Label(self.content_frame, text=icon, font=('Segoe UI', 24), foreground=icon_color).pack(pady=10)
        ttk.Label(self.content_frame, text=message, font=('Segoe UI', 10), wraplength=450).pack(pady=10)
        accept_button = ttk.Button(self.content_frame, text=TRANSLATIONS[lang]['accept_button'], command=self.destroy_progress_window, bootstyle=bootstyle)
        accept_button.pack(pady=10)
        self.widget_translation_keys[str(id(accept_button))] = 'accept_button'

    def destroy_progress_window(self):
        if self.progress_window:
            self.progress_window.grab_release()
            self.progress_window.destroy()
            self.progress_window = None
        self.root.attributes('-disabled', 0)
        self.root.lift()  # Trae la ventana principal al frente

    def toggle_pause(self):
        job = self.current_job
        if job is None:
            return
        self.is_paused = not self.is_paused
        if self.is_paused:
            job.pause()
        else:
            job.resume()
        lang = self.language_var.get()
        pause_text = TRANSLATIONS[lang]['resume_button'] if self.is_paused else TRANSLATIONS[lang]['pause_button']
        self.songs_pause_button.configure(text=pause_text)
        self.widget_translation_keys[str(id(self.songs_pause_button))] = 'resume_button' if self.is_paused else 'pause_button'
        self.playlist_pause_button.configure(text=pause_text)
        self.widget_translation_keys[str(id(self.playlist_pause_button))] = 'resume_button' if self.is_paused else 'pause_button'
        if hasattr(self, 'spotify_pause_button'):
            self.spotify_pause_button.configure(text=pause_text)
            self.widget_translation_keys[str(id(self.spotify_pause_button))] = 'resume_button' if self.is_paused else 'pause_button'
        if hasattr(self, 'progress_pause_button'):
            self.progress_pause_button.configure(text=pause_text)
            self.widget_translation_keys[str(id(self.progress_pause_button))] = 'resume_button' if self.is_paused else 'pause_button'
        status_text = TRANSLATIONS[lang]['status_paused'] if self.is_paused else \
                      TRANSLATIONS[lang]['status_downloading'] if self.total_videos <= 1 else \
                      TRANSLATIONS[lang]['status_downloading_multiple'].format(self.completed_videos, self.total_videos)
        self.songs_status_label.config(text=f"{TRANSLATIONS[lang]['progress_status'].split(':')[0]}: {status_text}")
        self.playlist_status_label.config(text=f"{TRANSLATIONS[lang]['progress_status'].split(':')[0]}: {status_text}")
        self.search_status_label.config(text=f"{TRANSLATIONS[lang]['progress_status'].split(':')[0]}: {status_text}")
        if hasattr(self, 'spotify_status_label'):
            self.spotify_status_label.config(text=f"{TRANSLATIONS[lang]['progress_status'].split(':')[0]}: {status_text}")
        if hasattr(self, 'progress_status_label'):
            self.progress_status_label.config(text=f"{TRANSLATIONS[lang]['progress_status'].split(':')[0]}: {status_text}")

    def cancel_download(self):
        job = self.current_job
        if job is None:
            return
        self.is_cancelled = True
        job.cancel()  # mata los procesos de yt-dlp/ffmpeg en curso
        self.current_job = None
        self.finalize_download(error_message=TRANSLATIONS[self.language_var.get()]['error_title'])

    def finalize_download(self, error_message=None):
        self.hide_spinner()
        if self.is_paused:
            self.is_paused = False
            pause_text = TRANSLATIONS[self.language_var.get()]['pause_button']
            for name in ('songs_pause_button', 'playlist_pause_button', 'spotify_pause_button'):
                button = getattr(self, name, None)
                if button is not None:
                    button.configure(text=pause_text)
                    self.widget_translation_keys[str(id(button))] = 'pause_button'
        self.songs_download_button.configure(state='normal')
        self.songs_pause_button.configure(state='disabled')
        self.songs_cancel_button.configure(state='disabled')
        self.playlist_download_button.configure(state='normal')
        self.playlist_pause_button.configure(state='disabled')
        self.playlist_cancel_button.configure(state='disabled')
        if hasattr(self, 'spotify_download_button'):
            self.spotify_download_button.configure(state='normal')
        if hasattr(self, 'spotify_pause_button'):
            self.spotify_pause_button.configure(state='disabled')
        if hasattr(self, 'spotify_cancel_button'):
            self.spotify_cancel_button.configure(state='disabled')
        self.global_progress_var.set(0.0)
        self.video_progress_var.set(0.0)
        if error_message:
            self.show_result_message('error', error_message)
        else:
            if self.failed_videos:
                error_message = TRANSLATIONS[self.language_var.get()]['warning_failed_videos'].format(
                    "\n".join(f"- {video_id}: {error}" for video_id, error in self.failed_videos)
                )
                self.show_result_message('warning', error_message)
            else:
                self.show_result_message('success', TRANSLATIONS[self.language_var.get()]['success_download'])
        self.update_quality_frame()

    def open_search_results(self):
        query = self.search_query_var.get().strip()
        lang = self.language_var.get()
        if not query:
            self.show_result_message('error', TRANSLATIONS[lang]['error_no_query'])
            return

        self.search_results = []
        self.search_status_label.config(text=TRANSLATIONS[lang]['status_searching'])
        self.show_spinner()  # Mostrar spinner

        def search():
            try:
                entries = ytdlp.search(query, 10)
                if not entries:
                    self.post(lambda: self.search_status_label.config(text=TRANSLATIONS[lang]['status_search_error']))
                    self.post(lambda: self.show_result_message('warning', TRANSLATIONS[lang]['status_search_error']))
                    return
                results = [(entry.get('title') or 'Sin título', ytdlp.entry_url(entry), ytdlp.is_playlist_entry(entry))
                           for entry in entries]

                def show():
                    self.search_results = results
                    self.show_results_window()
                self.post(show)
            except Exception as e:
                msg = TRANSLATIONS[lang]['error_process_url'].format(str(e))
                self.post(lambda: self.search_status_label.config(text=TRANSLATIONS[lang]['status_search_error']))
                self.post(lambda: self.show_result_message('error', msg))
            finally:
                self.post(self.hide_spinner)

        Thread(target=search, daemon=True).start()

    def show_results_window(self):
        lang = self.language_var.get()
        results_window = tk.Toplevel(self.root)
        results_window.iconbitmap(self.icon_path)
        results_window.title(TRANSLATIONS[lang]['results_title'])
        results_window.geometry("500x400")
        results_window.resizable(False, False)
        results_window.configure(bg=self.style.colors.bg)

        window_width = 500
        window_height = 400
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        results_window.geometry(f"{window_width}x{window_height}+{x}+{y}")

        results_label = ttk.Label(results_window, text=TRANSLATIONS[lang]['results_label'], font=('Segoe UI', 14, 'bold'))
        results_label.pack(pady=10, anchor="center")
        self.widget_translation_keys[str(id(results_label))] = 'results_label'
        results_listbox = tk.Listbox(results_window, width=60, height=12, font=('Segoe UI', 10), bg='#FFFFFF', relief='flat', borderwidth=1)
        results_listbox.pack(pady=10, anchor="center")

        for title, _, is_playlist in self.search_results:
            display_text = f"[{'Lista' if is_playlist else 'Canción'}] {title}" if lang == 'es' else f"[{'Playlist' if is_playlist else 'Song'}] {title}"
            results_listbox.insert(tk.END, display_text)

        action_frame = tk.Frame(results_window, bg=self.style.colors.bg)
        action_frame.pack(pady=10)
        add_to_queue_button = ttk.Button(action_frame, text=TRANSLATIONS[lang]['add_to_queue_button'], command=lambda: self.add_to_search_queue(results_listbox, results_window))
        add_to_queue_button.pack(side='left', padx=5)
        self.widget_translation_keys[str(id(add_to_queue_button))] = 'add_to_queue_button'
        download_playlist_button = ttk.Button(action_frame, text=TRANSLATIONS[lang]['download_playlist_button'], command=lambda: download_search_playlist(self, results_listbox, results_window))
        download_playlist_button.pack(side='left', padx=5)
        self.widget_translation_keys[str(id(download_playlist_button))] = 'download_playlist_button'
        close_button = ttk.Button(action_frame, text=TRANSLATIONS[lang]['close_button'], command=results_window.destroy, bootstyle=SECONDARY)
        close_button.pack(side='left', padx=5)
        self.widget_translation_keys[str(id(close_button))] = 'close_button'

        self.search_status_label.config(text=TRANSLATIONS[lang]['status_search_results'].format(len(self.search_results)))
        self.update_quality_frame()

    def add_to_search_queue(self, listbox, window):
        lang = self.language_var.get()
        selection = listbox.curselection()
        if not selection:
            self.show_result_message('warning', TRANSLATIONS[lang]['error_no_selection'])
            return
        index = selection[0]
        title, url, is_playlist = self.search_results[index]
        if is_playlist:
            self.show_result_message('error', TRANSLATIONS[lang]['error_select_song'])
            return
        self.search_song_urls.append(url)
        self.search_song_listbox.insert(tk.END, title)
        self.search_status_label.config(text=TRANSLATIONS[lang]['status_song_added'].format(len(self.search_song_urls)))
        self.update_quality_frame()
        window.destroy()

    def remove_search_song(self):
        lang = self.language_var.get()
        selection = self.search_song_listbox.curselection()
        if not selection:
            self.show_result_message('warning', TRANSLATIONS[lang]['error_remove_song'])
            return
        index = selection[0]
        self.search_song_listbox.delete(index)
        self.search_song_urls.pop(index)
        self.search_status_label.config(text=TRANSLATIONS[lang]['status_song_removed'].format(len(self.search_song_urls)))
        self.update_quality_frame()

    def add_song(self):
        url = self.song_entry_var.get().strip()
        lang = self.language_var.get()
        if not url:
            self.show_result_message('error', TRANSLATIONS[lang]['error_no_query'])
            return
        if not re.match(r'https?://', url):
            self.show_result_message('error', TRANSLATIONS[lang]['error_invalid_url'])
            return

        self.add_button.configure(state='disabled')
        self.songs_status_label.config(text=TRANSLATIONS[lang]['status_processing'])
        self.show_spinner()

        def process_song():
            try:
                info = ytdlp.extract_info(url, flat=True)
                if ytdlp.is_playlist_entry(info) or 'playlist?list=' in url or 'entries' in info:
                    self.post(lambda: self.show_result_message('error', TRANSLATIONS[lang]['error_playlist_in_songs']))
                    self.post(lambda: self.songs_status_label.config(text=TRANSLATIONS[lang]['status_waiting_songs']))
                    return

                title = info.get('title') or ('Sin título' if lang == 'es' else 'No title')
                author = info.get('uploader') or info.get('channel') or ('Desconocido' if lang == 'es' else 'Unknown')

                def add_to_list():
                    self.song_urls.append((url, title, author))
                    self.song_listbox.insert(tk.END, f"{title} - {author}")
                    self.song_entry_var.set("")
                    self.songs_status_label.config(text=TRANSLATIONS[lang]['status_song_added'].format(len(self.song_urls)))
                    self.update_quality_frame()
                self.post(add_to_list)
            except Exception as e:
                msg = TRANSLATIONS[lang]['error_process_url'].format(str(e))
                self.post(lambda: self.show_result_message('error', msg))
                self.post(lambda: self.songs_status_label.config(text=TRANSLATIONS[lang]['status_waiting_songs']))
            finally:
                self.post(lambda: self.add_button.configure(state='normal'))
                self.post(self.hide_spinner)  # Ocultar spinner

        Thread(target=process_song, daemon=True).start()

    def load_spotify_csv(self):
        lang = self.language_var.get()
        csv_path = filedialog.askopenfilename(
            title=TRANSLATIONS[lang]['spotify_select_csv'],
            filetypes=[("CSV", "*.csv"), ("All files", "*.*")]
        )
        if not csv_path:
            return

        self.spotify_playlist_name = os.path.splitext(os.path.basename(csv_path))[0] or "Spotify CSV"

        self.spotify_status_label.config(text=TRANSLATIONS[lang]['status_processing'])
        self.show_spinner()

        def normalize_text(value):
            return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', ' ', (value or '').lower())).strip()

        def token_set(value):
            normalized = normalize_text(value)
            return {token for token in normalized.split(' ') if token}

        def score_candidate(entry, title, artist, expected_seconds=None):
            entry_title = entry.get('title', '') or ''
            uploader = entry.get('uploader', '') or entry.get('channel', '') or ''
            full_text = f"{entry_title} {uploader}"
            full_tokens = token_set(full_text)
            title_tokens = token_set(title)
            artist_tokens = token_set(artist)

            score = 0
            if title_tokens:
                title_overlap = len(title_tokens & full_tokens) / max(len(title_tokens), 1)
                score += title_overlap * 70
            if artist_tokens:
                artist_overlap = len(artist_tokens & full_tokens) / max(len(artist_tokens), 1)
                score += artist_overlap * 40

            bad_keywords = ['live', 'karaoke', 'cover', 'remix', 'nightcore', 'sped up', 'reverb', 'instrumental', '8d']
            lowered_title = entry_title.lower()
            query_text = f"{title} {artist}".lower()
            for keyword in bad_keywords:
                if keyword in lowered_title and keyword not in query_text:
                    score -= 25

            duration = entry.get('duration')
            if expected_seconds and isinstance(duration, (int, float)):
                diff = abs(float(duration) - float(expected_seconds))
                if diff <= 8:
                    score += 20
                elif diff <= 20:
                    score += 10
                elif diff > 45:
                    score -= 30

            return score

        def process_csv():
            try:
                with open(csv_path, 'r', encoding='utf-8-sig', newline='') as file:
                    sample = file.read(4096)
                    file.seek(0)
                    try:
                        dialect = csv.Sniffer().sniff(sample, delimiters=",;")
                    except csv.Error:
                        dialect = csv.excel
                    reader = csv.DictReader(file, dialect=dialect)
                    rows = list(reader)

                if not rows:
                    self.post(lambda: self.spotify_status_label.config(text=TRANSLATIONS[lang]['status_waiting_spotify']))
                    return

                title_key = next((k for k in (reader.fieldnames or []) if k.lower().strip() in ['track name', 'name', 'title', 'track']), None)
                artist_key = next((k for k in (reader.fieldnames or []) if k.lower().strip() in ['artist name(s)', 'artist', 'artists', 'album artist name']), None)
                duration_key = next((k for k in (reader.fieldnames or []) if k.lower().strip() in ['duration (ms)', 'duration_ms', 'duration']), None)
                if not title_key and reader.fieldnames:
                    title_key = reader.fieldnames[0]

                tracks = []
                for row in rows:
                    title = (row.get(title_key, '') if title_key else '').strip()
                    artist = (row.get(artist_key, '') if artist_key else '').strip()
                    if not title:
                        continue
                    duration_seconds = None
                    if duration_key:
                        raw_duration = (row.get(duration_key, '') or '').strip()
                        if raw_duration.isdigit():
                            duration_seconds = int(raw_duration) / 1000 if int(raw_duration) > 1000 else int(raw_duration)
                    tracks.append((title, artist, duration_seconds))

                def best_match(track):
                    """Busca la canción en YouTube y devuelve (puntuación, entrada) o None."""
                    title, artist, duration_seconds = track
                    try:
                        entries = ytdlp.search(f"\"{title}\" {artist} official audio".strip(), 8)
                    except Exception:
                        logging.exception("Búsqueda fallida para %s - %s", title, artist)
                        return None
                    scored = [(score_candidate(e, title, artist, duration_seconds), e) for e in entries]
                    return max(scored, key=lambda item: item[0]) if scored else None

                # Varias búsquedas a la vez; el resultado mantiene el orden del CSV
                matches = [None] * len(tracks)
                with ThreadPoolExecutor(max_workers=4) as pool:
                    futures = {pool.submit(best_match, track): i for i, track in enumerate(tracks)}
                    for done_count, future in enumerate(as_completed(futures), start=1):
                        matches[futures[future]] = future.result()
                        found = sum(1 for m in matches if m and m[0] >= 30)
                        self.post(lambda i=done_count, total=len(tracks), f=found: self.spotify_status_label.config(
                            text=TRANSLATIONS[lang]['status_spotify_resolving'].format(i, total, f)
                        ))

                resolved = []
                used_filenames = {}
                for (title, artist, _), match in zip(tracks, matches):
                    if not match or match[0] < 30:
                        continue
                    entry = match[1]
                    url = ytdlp.entry_url(entry)
                    if not url:
                        continue
                    base_filename = f"{title} - {artist}".strip(" -") or title
                    count = used_filenames.get(base_filename, 0) + 1
                    used_filenames[base_filename] = count
                    resolved.append({
                        'url': url,
                        'title': title,
                        'artist': artist,
                        'resolved_title': entry.get('title', ''),
                        'source': 'spotify_csv',
                        'filename': f"{base_filename} ({count})" if count > 1 else base_filename,
                    })

                def update_ui_with_results():
                    self.spotify_song_urls.clear()
                    self.spotify_song_listbox.delete(0, tk.END)
                    for item in resolved:
                        self.spotify_song_urls.append(item)
                        display_text = f"{item['title']} - {item['artist']}"
                        if item.get('resolved_title'):
                            display_text = f"{display_text} → {item['resolved_title']}"
                        self.spotify_song_listbox.insert(tk.END, display_text)
                    self.spotify_status_label.config(text=TRANSLATIONS[lang]['status_spotify_loaded'].format(len(self.spotify_song_urls)))
                    self.update_quality_frame()

                self.post(update_ui_with_results)
            except Exception as e:
                msg = TRANSLATIONS[lang]['error_process_url'].format(str(e))
                self.post(lambda: self.show_result_message('error', msg))
                self.post(lambda: self.spotify_status_label.config(text=TRANSLATIONS[lang]['status_waiting_spotify']))
            finally:
                self.post(self.hide_spinner)

        Thread(target=process_csv, daemon=True).start()

    def remove_spotify_song(self):
        lang = self.language_var.get()
        selection = self.spotify_song_listbox.curselection()
        if not selection:
            self.show_result_message('warning', TRANSLATIONS[lang]['error_remove_song'])
            return
        index = selection[0]
        self.spotify_song_listbox.delete(index)
        self.spotify_song_urls.pop(index)
        self.spotify_status_label.config(text=TRANSLATIONS[lang]['status_song_removed'].format(len(self.spotify_song_urls)))
        self.update_quality_frame()

    def start_spotify_csv_download(self):
        start_spotify_download(self)

    def remove_song(self):
        lang = self.language_var.get()
        selection = self.song_listbox.curselection()
        if not selection:
            self.show_result_message('warning', TRANSLATIONS[lang]['error_remove_song'])
            return
        index = selection[0]
        self.song_listbox.delete(index)
        self.song_urls.pop(index)
        self.songs_status_label.config(text=TRANSLATIONS[lang]['status_song_removed'].format(len(self.song_urls)))
        self.update_quality_frame()

    def update_quality_frame(self, *args):
        """Actualiza la visibilidad y sincronización de las opciones de calidad de audio."""
        has_search_songs = len(self.search_song_urls) > 0
        has_songs = len(self.song_urls) > 0
        has_spotify_songs = len(self.spotify_song_urls) > 0
        has_playlist = self.playlist_url_var.get().strip()
        has_search = len(self.search_results) > 0

        if (has_search_songs or has_songs or has_spotify_songs or has_playlist or has_search) and not self.quality_frame_visible:
            logging.debug("Packing quality_frame in audio_tab")
            self.quality_frame.pack(fill='x', pady=10, padx=10)
            self.quality_frame_visible = True
            self.update_codec_options()
            self.update_norm_options()
        elif not (has_search_songs or has_songs or has_spotify_songs or has_playlist or has_search) and self.quality_frame_visible:
            logging.debug("Unpacking quality_frame from audio_tab")
            self.quality_frame.pack_forget()
            self.bitrate_frame.pack_forget()
            self.lossless_frame.pack_forget()
            self.custom_norm_frame.pack_forget()
            self.bitrate_frame_visible = False
            self.lossless_frame_visible = False
            self.custom_norm_frame_visible = False
            self.quality_frame_visible = False

        # Sincronizar las opciones de audio con las variables globales
        self.config.update({
            "codec": self.codec_var.get(),
            "bitrate": self.bitrate_var.get(),
            "bit_depth": self.bit_depth_var.get(),
            "sample_rate": self.sample_rate_var.get(),
            "channels": self.channels_var.get(),
            "normalization": self.normalization_var.get(),
            "custom_lufs_i": self.custom_lufs_i_var.get(),
            "custom_lufs_lra": self.custom_lufs_lra_var.get(),
            "custom_lufs_tp": self.custom_lufs_tp_var.get(),
        })
        self.save_config()

    def update_codec_options(self, *args):
        codec = self.codec_var.get()
        logging.debug(f"Updating codec options: codec={codec}")
        sample_rate_options = {
            "mp3": ["32000", "44100", "48000"],
            "aac": ["44100", "48000"],
            "opus": ["48000"],
            "flac": ["44100", "48000", "96000", "192000"],
            "wav": ["44100", "48000", "96000", "192000"],
            "alac": ["44100", "48000", "96000", "192000"],
        }
        allowed_rates = sample_rate_options.get(codec, ["44100", "48000", "96000", "192000"])
        if hasattr(self, 'sample_rate_combobox'):
            self.sample_rate_combobox.configure(values=allowed_rates)
        if self.sample_rate_var.get() not in allowed_rates:
            self.sample_rate_var.set(allowed_rates[0])
        # Keep layout stable; only enable/disable controls per codec
        if not self.bitrate_frame_visible:
            self.bitrate_frame.pack(pady=10)
            self.bitrate_frame_visible = True
        if not self.lossless_frame_visible:
            self.lossless_frame.pack(pady=10)
            self.lossless_frame_visible = True

        is_lossy = codec in ["mp3", "aac", "opus"]
        if hasattr(self, 'bitrate_combobox'):
            self.bitrate_combobox.configure(state='readonly' if is_lossy else 'disabled')
        if hasattr(self, 'bit_depth_combobox'):
            self.bit_depth_combobox.configure(state='readonly' if not is_lossy else 'disabled')

    def update_norm_options(self, *args):
        norm = self.normalization_var.get()
        logging.debug(f"Updating normalization options: norm={norm}")
        if norm == "custom":
            if not self.custom_norm_frame_visible:
                logging.debug("Packing custom_norm_frame")
                self.custom_norm_frame.pack(pady=10)
                self.custom_norm_frame_visible = True
        else:
            if self.custom_norm_frame_visible:
                logging.debug("Unpacking custom_norm_frame")
                self.custom_norm_frame.pack_forget()
                self.custom_norm_frame_visible = False
                