import tkinter as tk
from tkinter import ttk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import os
import json
from queue import Queue
from threading import Thread
from translations import TRANSLATIONS
from ui_components import create_search_tab, create_songs_tab, create_playlist_tab, create_audio_options_tab, create_options_tab, create_about_tab
from download_manager import download, download_search_songs, download_search_playlist, start_songs_download, start_playlist_download
from utils import clean_folder_name
import yt_dlp
import logging
import re
import sys

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

class DownloaderApp:
    # Valores predeterminados para la configuración
    DEFAULT_CONFIG = {
        "language": "es",
        "theme": "litera",
        "threads": "4",
        "music_folder": None,  # Se establecerá dinámicamente en __init__ usando script_dir
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
        if hasattr(sys, '_MEIPASS'):
            icon_path = os.path.join(sys._MEIPASS, "icon.ico")
        else:
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
        self.root.iconbitmap(icon_path)

        # Tamaño de la ventana
        window_width = 745
        window_height = 650

        # Obtener tamaño de la pantalla
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()

        # Calcular posición centrada
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2

        # Configurar geometría de la ventana centrada
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        self.root.resizable(False, False)

        # Inicializar script_dir
        self.script_dir = os.path.dirname(os.path.abspath(__file__))

        # Crear un directorio persistente para la configuración
        self.config_dir = os.path.join(os.path.expanduser("~"), ".easytunrmusic")
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir)
        
        # Initialize music folder and linked variable *before* loading config
        self.music_folder = os.path.join(self.script_dir, "Música")
        self.music_folder_var = tk.StringVar(value=self.music_folder)
        self.DEFAULT_CONFIG["music_folder"] = self.music_folder
        
        # Load configuration
        self.config_file = os.path.join(self.config_dir, "config.json")
        self.load_config()

        # Update music folder from config (if available)
        self.music_folder = self.config.get("music_folder", os.path.join(self.script_dir, "Música"))
        self.music_folder_var.set(self.music_folder)
        if not os.path.exists(self.music_folder):
            os.makedirs(self.music_folder)

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
        self.download_queue = Queue()
        self.total_videos = 0
        self.completed_videos = 0
        self.is_paused = False
        self.is_cancelled = False
        self.executor = None
        self.is_playlist = False
        self.song_urls = []
        self.search_song_urls = []
        self.search_results = []
        self.quality_frame_visible = False
        self.bitrate_frame_visible = False
        self.lossless_frame_visible = False
        self.custom_norm_frame_visible = False
        self.progress_window = None
        self.widget_translation_keys = {}

        # Configure styles
        self.style.configure('TNotebook', background=self.style.colors.bg, tabmargins=(10, 10, 0, 0))
        self.style.configure('TNotebook.Tab', font=('Segoe UI', 10), padding=[15, 8], background='#FFFFFF')
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
        
        # Load music folder from configuration
        default_music_folder = os.path.join(self.script_dir, "Música")
        self.music_folder = self.config.get("music_folder", default_music_folder)
        self.music_folder_var.set(self.music_folder)  # Error: music_folder_var doesn't exist yet
        if not os.path.exists(self.music_folder):
            os.makedirs(self.music_folder)

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
        self.notebook.tab(self.audio_tab, text=TRANSLATIONS[lang]['audio_tab'])
        self.notebook.tab(self.options_tab, text=TRANSLATIONS[lang]['options_tab'])
        self.notebook.tab(self.about_tab, text=TRANSLATIONS[lang]['about_tab'])
    
        # Actualizar textos de los widgets
        self._update_widget_text(self.search_tab, lang)
        self._update_widget_text(self.songs_tab, lang)
        self._update_widget_text(self.playlist_tab, lang)
        self._update_widget_text(self.audio_tab, lang)
        self._update_widget_text(self.options_tab, lang)
        self._update_widget_text(self.about_tab, lang)
    
        # Actualizar etiquetas de estado
        self.search_status_label.config(text=TRANSLATIONS[lang]['status_waiting_search'])
        self.songs_status_label.config(text=TRANSLATIONS[lang]['status_waiting_songs'])
        self.playlist_status_label.config(text=TRANSLATIONS[lang]['status_waiting_playlist'])
    
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
        self.progress_window.iconbitmap(os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico"))
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
        self.is_paused = not self.is_paused
        lang = self.language_var.get()
        pause_text = TRANSLATIONS[lang]['resume_button'] if self.is_paused else TRANSLATIONS[lang]['pause_button']
        self.songs_pause_button.configure(text=pause_text)
        self.widget_translation_keys[str(id(self.songs_pause_button))] = 'resume_button' if self.is_paused else 'pause_button'
        self.playlist_pause_button.configure(text=pause_text)
        self.widget_translation_keys[str(id(self.playlist_pause_button))] = 'resume_button' if self.is_paused else 'pause_button'
        if hasattr(self, 'progress_pause_button'):
            self.progress_pause_button.configure(text=pause_text)
            self.widget_translation_keys[str(id(self.progress_pause_button))] = 'resume_button' if self.is_paused else 'pause_button'
        status_text = TRANSLATIONS[lang]['status_paused'] if self.is_paused else \
                      TRANSLATIONS[lang]['status_downloading'] if self.total_videos <= 1 else \
                      TRANSLATIONS[lang]['status_downloading_multiple'].format(self.completed_videos, self.total_videos)
        self.songs_status_label.config(text=f"{TRANSLATIONS[lang]['progress_status'].split(':')[0]}: {status_text}")
        self.playlist_status_label.config(text=f"{TRANSLATIONS[lang]['progress_status'].split(':')[0]}: {status_text}")
        self.search_status_label.config(text=f"{TRANSLATIONS[lang]['progress_status'].split(':')[0]}: {status_text}")
        if hasattr(self, 'progress_status_label'):
            self.progress_status_label.config(text=f"{TRANSLATIONS[lang]['progress_status'].split(':')[0]}: {status_text}")

    def cancel_download(self):
        self.is_cancelled = True
        if self.executor:
            self.executor._threads.clear()
        self.finalize_download(error_message=TRANSLATIONS[self.language_var.get()]['error_title'])

    def finalize_download(self, error_message=None):
        self.songs_download_button.configure(state='normal')
        self.songs_pause_button.configure(state='disabled')
        self.songs_cancel_button.configure(state='disabled')
        self.playlist_download_button.configure(state='normal')
        self.playlist_pause_button.configure(state='disabled')
        self.playlist_cancel_button.configure(state='disabled')
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
                ydl_opts = {
                    'quiet': True,
                    'extract_flat': True,
                    'force_generic_extractor': False,
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    results = ydl.extract_info(f"ytsearch10:{query}", download=False)
                    if 'entries' not in results:
                        self.root.after(0, lambda: self.search_status_label.config(text=TRANSLATIONS[lang]['status_search_error']))
                        self.root.after(0, lambda: self.show_result_message('warning', TRANSLATIONS[lang]['status_search_error']))
                        return
    
                    for entry in results['entries']:
                        title = entry.get('title', 'Sin título')
                        url = entry.get('url', entry.get('webpage_url', ''))
                        is_playlist = entry.get('ie_key', '').lower() in ['youtubeplaylist'] or 'playlist?list=' in url
                        self.search_results.append((title, url, is_playlist))
    
                    self.root.after(0, self.show_results_window)
                    pass
            except Exception as e:
                self.root.after(0, lambda: self.search_status_label.config(text=TRANSLATIONS[lang]['status_search_error']))
                self.root.after(0, lambda: self.show_result_message('error', f"{TRANSLATIONS[lang]['error_process_url'].format(str(e))}"))
            finally:
                self.root.after(0, self.hide_spinner) 
    
        Thread(target=search).start()

    def show_results_window(self):
        lang = self.language_var.get()
        results_window = tk.Toplevel(self.root)
        results_window.iconbitmap(os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico"))
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
                ydl_opts = {
                    'quiet': True,
                    'extract_flat': True,
                    'force_generic_extractor': False,
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    is_playlist = info.get('ie_key', '').lower() in ['youtubeplaylist'] or 'playlist?list=' in url
                    if is_playlist or 'entries' in info:
                        self.root.after(0, lambda: self.show_result_message('error', TRANSLATIONS[lang]['error_playlist_in_songs']))
                        self.root.after(0, lambda: self.songs_status_label.config(text=TRANSLATIONS[lang]['status_waiting_songs']))
                        return
    
                    title = info.get('title', 'Sin título' if lang == 'es' else 'No title')
                    author = info.get('uploader', info.get('channel', 'Desconocido' if lang == 'es' else 'Unknown'))
                    display_text = f"{title} - {author}"
                    self.root.after(0, lambda: self.song_urls.append((url, title, author)))
                    self.root.after(0, lambda: self.song_listbox.insert(tk.END, display_text))
                    self.root.after(0, lambda: self.song_entry_var.set(""))
                    self.root.after(0, lambda: self.songs_status_label.config(
                        text=TRANSLATIONS[lang]['status_song_added'].format(len(self.song_urls))))
                    self.root.after(0, self.update_quality_frame)
                    pass
            except Exception as e:
                self.root.after(0, lambda: self.show_result_message('error',
                                                                    TRANSLATIONS[lang]['error_process_url'].format(str(e))))
                self.root.after(0, lambda: self.songs_status_label.config(text=TRANSLATIONS[lang]['status_waiting_songs']))
            finally:
                self.root.after(0, lambda: self.add_button.configure(state='normal'))
                self.root.after(0, self.hide_spinner)  # Ocultar spinner

        Thread(target=process_song).start()
        
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
        has_playlist = self.playlist_url_var.get().strip()
        has_search = len(self.search_results) > 0
    
        if (has_search_songs or has_songs or has_playlist or has_search) and not self.quality_frame_visible:
            logging.debug("Packing quality_frame in audio_tab")
            self.quality_frame.pack(fill='x', pady=10, padx=10)
            self.quality_frame_visible = True
            self.update_codec_options()
            self.update_norm_options()
        elif not (has_search_songs or has_songs or has_playlist or has_search) and self.quality_frame_visible:
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
        if codec in ["mp3", "aac", "opus"]:
            if not self.bitrate_frame_visible:
                logging.debug("Packing bitrate_frame")
                self.bitrate_frame.pack(pady=10)
                self.bitrate_frame_visible = True
            if self.lossless_frame_visible:
                logging.debug("Unpacking lossless_frame")
                self.lossless_frame.pack_forget()
                self.lossless_frame_visible = False
        else:
            if self.bitrate_frame_visible:
                logging.debug("Unpacking bitrate_frame")
                self.bitrate_frame.pack_forget()
                self.bitrate_frame_visible = False
            if not self.lossless_frame_visible:
                logging.debug("Packing lossless_frame")
                self.lossless_frame.pack(pady=10)
                self.lossless_frame_visible = True

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
                