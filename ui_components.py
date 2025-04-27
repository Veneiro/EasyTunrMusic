import tkinter as tk
from tkinter import ttk, filedialog
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.scrolled import ScrolledFrame
from translations import TRANSLATIONS
from download_manager import download_search_songs, start_songs_download, start_playlist_download
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

def create_search_tab(app):
    lang = app.language_var.get()
    logging.debug(f"Creating search tab with language: {lang}")
    search_tab = tk.Frame(app.notebook, bg=app.style.colors.bg)

    search_label = ttk.Label(search_tab, text=TRANSLATIONS[lang]['search_label'], font=('Segoe UI', 12, 'bold'))
    search_label.pack(pady=10, anchor="center")
    app.widget_translation_keys[str(id(search_label))] = 'search_label'

    ttk.Entry(search_tab, textvariable=app.search_query_var, width=60, bootstyle=SECONDARY).pack(pady=10, anchor="center")

    search_button = ttk.Button(search_tab, text=TRANSLATIONS[lang]['search_button'], command=app.open_search_results)
    search_button.pack(pady=10, anchor="center")
    app.widget_translation_keys[str(id(search_button))] = 'search_button'

    queue_label = ttk.Label(search_tab, text=TRANSLATIONS[lang]['queue_label'])
    queue_label.pack(pady=10, anchor="center")
    app.widget_translation_keys[str(id(queue_label))] = 'queue_label'

    app.search_song_listbox = tk.Listbox(search_tab, width=60, height=8, font=('Segoe UI', 10), bg='#FFFFFF', relief='flat', borderwidth=1)
    app.search_song_listbox.pack(pady=10, anchor="center")

    # Visualización estática de la carpeta de destino
    create_destination_display(search_tab, app, editable=False)

    search_action_frame = tk.Frame(search_tab, bg=app.style.colors.bg)
    search_action_frame.pack(pady=10)

    remove_button = ttk.Button(search_action_frame, text=TRANSLATIONS[lang]['remove_button'], command=app.remove_search_song, bootstyle=SECONDARY)
    remove_button.pack(side='left', padx=5)
    app.widget_translation_keys[str(id(remove_button))] = 'remove_button'

    download_queue_button = ttk.Button(search_action_frame, text=TRANSLATIONS[lang]['download_queue_button'], command=lambda: download_search_songs(app))
    download_queue_button.pack(side='left', padx=5)
    app.widget_translation_keys[str(id(download_queue_button))] = 'download_queue_button'

    app.search_status_label = tk.Label(search_tab, text=TRANSLATIONS[lang]['status_waiting_search'], wraplength=500, bg=app.style.colors.bg, font=('Segoe UI', 10))
    app.search_status_label.pack(pady=10)
    app.widget_translation_keys[str(id(app.search_status_label))] = 'status_waiting_search'

    return search_tab

def create_songs_tab(app):
    lang = app.language_var.get()
    logging.debug(f"Creating songs tab with language: {lang}")
    songs_tab = tk.Frame(app.notebook, bg=app.style.colors.bg)

    songs_label = ttk.Label(songs_tab, text=TRANSLATIONS[lang]['songs_label'], font=('Segoe UI', 12, 'bold'))
    songs_label.pack(pady=10, anchor="center")
    app.widget_translation_keys[str(id(songs_label))] = 'songs_label'

    ttk.Entry(songs_tab, textvariable=app.song_entry_var, width=60, bootstyle=SECONDARY).pack(pady=10, anchor="center")

    app.add_button = ttk.Button(songs_tab, text=TRANSLATIONS[lang]['add_button'], command=app.add_song)
    app.add_button.pack(pady=10, anchor="center")
    app.widget_translation_keys[str(id(app.add_button))] = 'add_button'

    remove_button = ttk.Button(songs_tab, text=TRANSLATIONS[lang]['remove_button'], command=app.remove_song, bootstyle=SECONDARY)
    remove_button.pack(pady=10, anchor="center")
    app.widget_translation_keys[str(id(remove_button))] = 'remove_button'

    app.song_listbox = tk.Listbox(songs_tab, width=60, height=10, font=('Segoe UI', 10), bg='#FFFFFF', relief='flat', borderwidth=1)
    app.song_listbox.pack(pady=10, anchor="center")

    # Visualización estática de la carpeta de destino
    create_destination_display(songs_tab, app, editable=False)

    songs_button_frame = tk.Frame(songs_tab, bg=app.style.colors.bg)
    songs_button_frame.pack(pady=10)

    app.songs_download_button = ttk.Button(songs_button_frame, text=TRANSLATIONS[lang]['download_button'], command=lambda: start_songs_download(app))
    app.songs_download_button.pack(side='left', padx=5)
    app.widget_translation_keys[str(id(app.songs_download_button))] = 'download_button'

    app.songs_pause_button = ttk.Button(songs_button_frame, text=TRANSLATIONS[lang]['pause_button'], command=app.toggle_pause, state='disabled', bootstyle=SECONDARY)
    app.songs_pause_button.pack(side='left', padx=5)
    app.widget_translation_keys[str(id(app.songs_pause_button))] = 'pause_button'

    app.songs_cancel_button = ttk.Button(songs_button_frame, text=TRANSLATIONS[lang]['cancel_button'], command=app.cancel_download, state='disabled', bootstyle=DANGER)
    app.songs_cancel_button.pack(side='left', padx=5)
    app.widget_translation_keys[str(id(app.songs_cancel_button))] = 'cancel_button'

    app.songs_status_label = tk.Label(songs_tab, text=TRANSLATIONS[lang]['status_waiting_songs'], wraplength=500, bg=app.style.colors.bg, font=('Segoe UI', 10))
    app.songs_status_label.pack(pady=10)
    app.widget_translation_keys[str(id(app.songs_status_label))] = 'status_waiting_songs'

    return songs_tab

def create_playlist_tab(app):
    lang = app.language_var.get()
    logging.debug(f"Creating playlist tab with language: {lang}")
    playlist_tab = tk.Frame(app.notebook, bg=app.style.colors.bg)
    
    playlist_label = ttk.Label(playlist_tab, text=TRANSLATIONS[lang]['playlist_label'], font=('Segoe UI', 12, 'bold'))
    playlist_label.pack(pady=10, anchor="center")
    app.widget_translation_keys[str(id(playlist_label))] = 'playlist_label'
    
    ttk.Entry(playlist_tab, textvariable=app.playlist_url_var, width=60, bootstyle=SECONDARY).pack(pady=10, anchor="center")

    # Visualización estática de la carpeta de destino
    create_destination_display(playlist_tab, app, editable=False)

    playlist_button_frame = tk.Frame(playlist_tab, bg=app.style.colors.bg)
    playlist_button_frame.pack(pady=10)
    
    app.playlist_download_button = ttk.Button(playlist_button_frame, text=TRANSLATIONS[lang]['download_playlist_button'], command=lambda: start_playlist_download(app))
    app.playlist_download_button.pack(side='left', padx=5)
    app.widget_translation_keys[str(id(app.playlist_download_button))] = 'download_playlist_button'
    
    app.playlist_pause_button = ttk.Button(playlist_button_frame, text=TRANSLATIONS[lang]['pause_button'], command=app.toggle_pause, state='disabled', bootstyle=SECONDARY)
    app.playlist_pause_button.pack(side='left', padx=5)
    app.widget_translation_keys[str(id(app.playlist_pause_button))] = 'pause_button'
    
    app.playlist_cancel_button = ttk.Button(playlist_button_frame, text=TRANSLATIONS[lang]['cancel_button'], command=app.cancel_download, state='disabled', bootstyle=DANGER)
    app.playlist_cancel_button.pack(side='left', padx=5)
    app.widget_translation_keys[str(id(app.playlist_cancel_button))] = 'cancel_button'

    app.playlist_status_label = tk.Label(playlist_tab, text=TRANSLATIONS[lang]['status_waiting_playlist'], wraplength=500, bg=app.style.colors.bg, font=('Segoe UI', 10))
    app.playlist_status_label.pack(pady=10)
    app.widget_translation_keys[str(id(app.playlist_status_label))] = 'status_waiting_playlist'

    return playlist_tab

def create_audio_options_tab(app):
    lang = app.language_var.get()
    logging.debug(f"Creating audio options tab with language: {lang}")
    audio_tab = tk.Frame(app.notebook, bg=app.style.colors.bg)
    logging.debug("Created audio_tab frame")

    # Define a custom style for ScrolledFrame to remove borders
    style = ttk.Style()
    style.configure('Custom.ScrolledFrame.TFrame', background=app.style.colors.bg, borderwidth=0)

    # Create ScrolledFrame for scrollable content
    scrolled_frame = ScrolledFrame(audio_tab, autohide=True, bootstyle=SECONDARY, style='Custom.ScrolledFrame.TFrame')
    scrolled_frame.pack(fill='both', expand=True, padx=20, pady=20)
    logging.debug("Packed scrolled_frame")

    # Main container for quality options
    app.quality_frame = tk.Frame(scrolled_frame, bg=app.style.colors.bg)
    app.quality_frame.pack(fill='x', pady=10, padx=10)
    logging.debug("Packed quality_frame inside scrolled_frame")

    # Title
    quality_label = ttk.Label(app.quality_frame, text=TRANSLATIONS[lang]['audio_quality_label'], font=('Segoe UI', 14, 'bold'))
    quality_label.pack(pady=(0, 10), anchor="center")
    app.widget_translation_keys[str(id(quality_label))] = 'audio_quality_label'
    logging.debug(f"Added quality_label with text: {quality_label.cget('text')}")

    # Codec and Channels frame
    codec_channels_frame = tk.Frame(app.quality_frame, bg=app.style.colors.bg)
    codec_channels_frame.pack(fill='x', pady=5)
    
    codec_label = ttk.Label(codec_channels_frame, text=TRANSLATIONS[lang]['codec_label'])
    codec_label.pack(side='left', padx=5)
    app.widget_translation_keys[str(id(codec_label))] = 'codec_label'
    codec_combobox = ttk.Combobox(codec_channels_frame, textvariable=app.codec_var, 
                                 values=["mp3", "aac", "opus", "flac", "wav", "alac"], 
                                 state='readonly', width=12, bootstyle=SECONDARY)
    codec_combobox.pack(side='left', padx=5)
    logging.debug(f"Added codec_label and codec_combobox with values: {codec_combobox['values']}")

    channels_label = ttk.Label(codec_channels_frame, text=TRANSLATIONS[lang]['channels_label'])
    channels_label.pack(side='left', padx=20)
    app.widget_translation_keys[str(id(channels_label))] = 'channels_label'
    channels_combobox = ttk.Combobox(codec_channels_frame, textvariable=app.channels_var, 
                                    values=["stereo", "mono", "multichannel"], state='readonly', width=12, bootstyle=SECONDARY)
    channels_combobox.pack(side='left', padx=5)
    logging.debug(f"Added channels_label and channels_combobox")

    # Bitrate frame
    app.bitrate_frame = tk.Frame(app.quality_frame, bg=app.style.colors.bg)
    app.bitrate_frame.pack(fill='x', pady=10)
    bitrate_label = ttk.Label(app.bitrate_frame, text=TRANSLATIONS[lang]['bitrate_label'])
    bitrate_label.pack(side='left', padx=5)
    app.widget_translation_keys[str(id(bitrate_label))] = 'bitrate_label'
    bitrate_combobox = ttk.Combobox(app.bitrate_frame, textvariable=app.bitrate_var, 
                                   values=["32", "48", "64", "96", "128", "160", "192", "256", "320"], 
                                   state='readonly', width=12, bootstyle=SECONDARY)
    bitrate_combobox.pack(side='left', padx=5)
    logging.debug(f"Created bitrate_frame with bitrate_label and bitrate_combobox")

    # Lossless frame
    app.lossless_frame = tk.Frame(app.quality_frame, bg=app.style.colors.bg)
    app.lossless_frame.pack(fill='x', pady=10)
    bit_depth_label = ttk.Label(app.lossless_frame, text=TRANSLATIONS[lang]['bit_depth_label'])
    bit_depth_label.pack(side='left', padx=5)
    app.widget_translation_keys[str(id(bit_depth_label))] = 'bit_depth_label'
    bit_depth_combobox = ttk.Combobox(app.lossless_frame, textvariable=app.bit_depth_var, 
                                     values=["16", "24", "32"], state='readonly', width=12, bootstyle=SECONDARY)
    bit_depth_combobox.pack(side='left', padx=5)
    sample_rate_label = ttk.Label(app.lossless_frame, text=TRANSLATIONS[lang]['sample_rate_label'])
    sample_rate_label.pack(side='left', padx=20)
    app.widget_translation_keys[str(id(sample_rate_label))] = 'sample_rate_label'
    sample_rate_combobox = ttk.Combobox(app.lossless_frame, textvariable=app.sample_rate_var, 
                                       values=["44100", "48000", "96000", "192000"], state='readonly', width=12, bootstyle=SECONDARY)
    sample_rate_combobox.pack(side='left', padx=5)
    logging.debug(f"Created lossless_frame with bit_depth_label, bit_depth_combobox, sample_rate_label, sample_rate_combobox")

    # Checkbuttons frame
    checkbuttons_frame = tk.Frame(app.quality_frame, bg=app.style.colors.bg)
    checkbuttons_frame.pack(fill='x', pady=10)
    dynamic_compression_check = ttk.Checkbutton(checkbuttons_frame, text=TRANSLATIONS[lang]['dynamic_compression'], 
                                               variable=app.dynamic_compression_var, bootstyle=INFO)
    dynamic_compression_check.pack(anchor="w", padx=5, pady=2)
    app.widget_translation_keys[str(id(dynamic_compression_check))] = 'dynamic_compression'
    extract_audio_check = ttk.Checkbutton(checkbuttons_frame, text=TRANSLATIONS[lang]['extract_audio'], 
                                         variable=app.extract_audio_var, bootstyle=INFO)
    extract_audio_check.pack(anchor="w", padx=5, pady=2)
    app.widget_translation_keys[str(id(extract_audio_check))] = 'extract_audio'
    metadata_check = ttk.Checkbutton(checkbuttons_frame, text=TRANSLATIONS[lang]['include_metadata'], 
                                    variable=app.metadata_var, bootstyle=INFO)
    metadata_check.pack(anchor="w", padx=5, pady=2)
    app.widget_translation_keys[str(id(metadata_check))] = 'include_metadata'
    thumbnail_check = ttk.Checkbutton(checkbuttons_frame, text=TRANSLATIONS[lang]['extract_thumbnail'], 
                                     variable=app.extract_thumbnail_var, bootstyle=INFO)
    thumbnail_check.pack(anchor="w", padx=5, pady=2)
    app.widget_translation_keys[str(id(thumbnail_check))] = 'extract_thumbnail'
    keep_original_check = ttk.Checkbutton(checkbuttons_frame, text=TRANSLATIONS[lang]['keep_original'], 
                                         variable=app.keep_original_var, bootstyle=INFO)
    keep_original_check.pack(anchor="w", padx=5, pady=2)
    app.widget_translation_keys[str(id(keep_original_check))] = 'keep_original'
    logging.debug("Added checkbuttons: dynamic_compression, extract_audio, include_metadata, extract_thumbnail, keep_original")

    # Separator
    ttk.Separator(app.quality_frame, orient='horizontal').pack(fill='x', pady=10)

    # Normalization frame
    normalization_frame = tk.Frame(app.quality_frame, bg=app.style.colors.bg)
    normalization_frame.pack(fill='x', pady=5)
    normalization_label = ttk.Label(normalization_frame, text=TRANSLATIONS[lang]['normalization_label'])
    normalization_label.pack(side='left', padx=5)
    app.widget_translation_keys[str(id(normalization_label))] = 'normalization_label'
    normalization_combobox = ttk.Combobox(normalization_frame, textvariable=app.normalization_var, 
                                         values=["off", "lufs_14", "lufs_23", "custom"], state='readonly', width=12, bootstyle=SECONDARY)
    normalization_combobox.pack(side='left', padx=5)
    logging.debug(f"Added normalization_label and normalization_combobox")

    # Custom normalization frame (initially hidden)
    app.custom_norm_frame = tk.Frame(app.quality_frame, bg=app.style.colors.bg)
    lufs_i_label = ttk.Label(app.custom_norm_frame, text=TRANSLATIONS[lang]['lufs_i_label'])
    lufs_i_label.pack(side='left', padx=5)
    app.widget_translation_keys[str(id(lufs_i_label))] = 'lufs_i_label'
    lufs_i_entry = ttk.Entry(app.custom_norm_frame, textvariable=app.custom_lufs_i_var, width=8, bootstyle=SECONDARY)
    lufs_i_entry.pack(side='left', padx=5)
    lufs_lra_label = ttk.Label(app.custom_norm_frame, text=TRANSLATIONS[lang]['lufs_lra_label'])
    lufs_lra_label.pack(side='left', padx=20)
    app.widget_translation_keys[str(id(lufs_lra_label))] = 'lufs_lra_label'
    lufs_lra_entry = ttk.Entry(app.custom_norm_frame, textvariable=app.custom_lufs_lra_var, width=8, bootstyle=SECONDARY)
    lufs_lra_entry.pack(side='left', padx=5)
    lufs_tp_label = ttk.Label(app.custom_norm_frame, text=TRANSLATIONS[lang]['lufs_tp_label'])
    lufs_tp_label.pack(side='left', padx=20)
    app.widget_translation_keys[str(id(lufs_tp_label))] = 'lufs_tp_label'
    lufs_tp_entry = ttk.Entry(app.custom_norm_frame, textvariable=app.custom_lufs_tp_var, width=8, bootstyle=SECONDARY)
    lufs_tp_entry.pack(side='left', padx=5)
    logging.debug("Created custom_norm_frame with lufs_i_label, lufs_i_entry, lufs_lra_label, lufs_lra_entry, lufs_tp_label, lufs_tp_entry")

    # Function to update custom normalization visibility
    def update_normalization_visibility(*args):
        if app.normalization_var.get() == "custom":
            app.custom_norm_frame.pack(fill='x', pady=10)
        else:
            app.custom_norm_frame.pack_forget()
    
    # Bind the normalization combobox to update visibility
    normalization_combobox.bind('<<ComboboxSelected>>', lambda event: update_normalization_visibility())
    # Also trace the variable for programmatic changes
    app.normalization_var.trace_add("write", update_normalization_visibility)
    # Initial check to hide if not custom
    update_normalization_visibility()

    logging.debug("Completed creation of audio options tab")
    return audio_tab

def create_options_tab(app):
    lang = app.language_var.get()
    logging.debug(f"Creating options tab with language: {lang}")
    options_tab = tk.Frame(app.notebook, bg=app.style.colors.bg)

    # Main container
    main_frame = tk.Frame(options_tab, bg=app.style.colors.bg)
    main_frame.pack(fill='both', expand=True, padx=20, pady=20)

    # Title
    options_label = ttk.Label(main_frame, text=TRANSLATIONS[lang]['options_tab'], font=('Segoe UI', 14, 'bold'))
    options_label.pack(pady=(0, 10), anchor="center")
    app.widget_translation_keys[str(id(options_label))] = 'options_tab'

    # Language frame
    language_frame = tk.Frame(main_frame, bg=app.style.colors.bg)
    language_frame.pack(fill='x', pady=5)
    language_label = ttk.Label(language_frame, text=TRANSLATIONS[lang]['language_label'])
    language_label.pack(side='left', padx=5)
    app.widget_translation_keys[str(id(language_label))] = 'language_label'
    language_combobox = ttk.Combobox(language_frame, state='readonly', width=15, bootstyle=SECONDARY)
    language_combobox.pack(side='left', padx=5)
    app.widget_translation_keys[str(id(language_combobox))] = 'language_combobox'

    # Language values
    language_map = {
        "es": "Español",
        "en": "English"
    }
    language_combobox['values'] = list(language_map.values())
    language_combobox.set(language_map.get(app.language_var.get(), "Español"))

    def on_language_select(event):
        selected_display = language_combobox.get()
        display_to_code = {
            "Español": "es",
            "English": "en",
        }
        code = display_to_code.get(selected_display)
        if code:
            logging.debug(f"Language selected: {selected_display} -> {code}")
            app.language_var.set(code)

    language_combobox.bind('<<ComboboxSelected>>', on_language_select)

    # Theme frame
    theme_frame = tk.Frame(main_frame, bg=app.style.colors.bg)
    theme_frame.pack(fill='x', pady=5)
    theme_label = ttk.Label(theme_frame, text=TRANSLATIONS[lang]['theme_label'])
    theme_label.pack(side='left', padx=5)
    app.widget_translation_keys[str(id(theme_label))] = 'theme_label'
    theme_combobox = ttk.Combobox(theme_frame, state='readonly', width=15, bootstyle=SECONDARY)
    theme_combobox.pack(side='left', padx=5)
    app.widget_translation_keys[str(id(theme_combobox))] = 'theme_combobox'

    # Theme values with stable mapping
    theme_map = {
        "litera": {"es": "Claro", "en": "Light"},
        "darkly": {"es": "Oscuro", "en": "Dark"},
        "flatly": {"es": "Plano", "en": "Flat"}
    }
    theme_display_values = [theme_map[theme][lang] for theme in theme_map]
    theme_combobox['values'] = theme_display_values
    current_theme = app.theme_var.get()
    theme_combobox.set(theme_map.get(current_theme, theme_map["litera"])[lang])

    def on_theme_select(event):
        selected_display = theme_combobox.get()
        logging.debug(f"Theme selected: {selected_display}")
        # Map display value back to theme code
        for theme, translations in theme_map.items():
            if selected_display in translations.values():
                app.theme_var.set(theme)
                logging.debug(f"Mapped {selected_display} to theme code: {theme}")
                break
        else:
            logging.warning(f"Could not map theme display value: {selected_display}")

    theme_combobox.bind('<<ComboboxSelected>>', on_theme_select)

    # Threads frame
    threads_frame = tk.Frame(main_frame, bg=app.style.colors.bg)
    threads_frame.pack(fill='x', pady=5)
    threads_label = ttk.Label(threads_frame, text=TRANSLATIONS[lang]['threads_label'])
    threads_label.pack(side='left', padx=5)
    app.widget_translation_keys[str(id(threads_label))] = 'threads_label'
    threads_combobox = ttk.Combobox(threads_frame, textvariable=app.threads_var, 
                                   values=[str(i) for i in range(1, 9)], width=5, state='readonly', bootstyle=SECONDARY)
    threads_combobox.pack(side='left', padx=5)

    # Separator
    ttk.Separator(main_frame, orient='horizontal').pack(fill='x', pady=10)

    # Destination folder
    create_destination_display(main_frame, app, editable=True)

    return options_tab

def create_destination_display(parent, app, editable=False):
    """Crea un cuadro para mostrar o editar la carpeta de destino."""
    lang = app.language_var.get()

    # Frame para organizar el contenido
    destination_frame = tk.Frame(parent, bg=app.style.colors.bg)
    destination_frame.pack(pady=10, padx=20, fill="x", anchor="center")

    if editable:
        # Cuadro de texto editable para mostrar/escribir la carpeta de destino
        destination_entry = ttk.Entry(destination_frame, textvariable=app.music_folder_var, width=50, bootstyle=SECONDARY)
        destination_entry.pack(side="left", padx=5, fill="x", expand=True)

        # Botón con ícono de carpeta para seleccionar la carpeta
        def select_folder():
            folder = filedialog.askdirectory(initialdir=app.music_folder_var.get(), title=TRANSLATIONS[lang]['destination'].split(":")[0])
            if folder:
                app.music_folder_var.set(folder)  # Actualiza la variable
                app.save_config()  # Guarda la configuración

        select_folder_button = ttk.Button(destination_frame, text="📁", command=select_folder, width=3, bootstyle=SECONDARY)
        select_folder_button.pack(side="right", padx=5)
    else:
        # Etiqueta estática para mostrar la carpeta de destino
        destination_label = ttk.Label(destination_frame, text=TRANSLATIONS[lang]['destination'].format(app.music_folder_var.get()), wraplength=400, font=('Segoe UI', 10), anchor="center")
        destination_label.pack(side="top", padx=5, fill="x", expand=True)
        app.widget_translation_keys[str(id(destination_label))] = 'destination'

    return destination_frame

def create_about_tab(app):
    """Crea la pestaña de información (About)."""
    lang = app.language_var.get()
    logging.debug(f"Creating about tab with language: {lang}")
    about_tab = tk.Frame(app.notebook, bg=app.style.colors.bg)

    # Título
    about_title = ttk.Label(about_tab, text=TRANSLATIONS[lang]['about_title'], font=('Segoe UI', 16, 'bold'))
    about_title.pack(pady=10, anchor="center")
    app.widget_translation_keys[str(id(about_title))] = 'about_title'

    # Descripción
    description_label = ttk.Label(
        about_tab,
        text=TRANSLATIONS[lang]['about_description'],
        wraplength=600,
        font=('Segoe UI', 10),
        justify="center"
    )
    description_label.pack(pady=10, anchor="center")
    app.widget_translation_keys[str(id(description_label))] = 'about_description'

    # Atajos de teclado
    shortcuts_title = ttk.Label(about_tab, text=TRANSLATIONS[lang]['shortcuts_title'], font=('Segoe UI', 12, 'bold'))
    shortcuts_title.pack(pady=10, anchor="center")
    app.widget_translation_keys[str(id(shortcuts_title))] = 'shortcuts_title'

    shortcuts_label = ttk.Label(
        about_tab,
        text=TRANSLATIONS[lang]['shortcuts_text'],
        wraplength=600,
        font=('Segoe UI', 10),
        justify="center"
    )
    shortcuts_label.pack(pady=5, anchor="center")
    app.widget_translation_keys[str(id(shortcuts_label))] = 'shortcuts_text'

    # Copyright
    copyright_label = ttk.Label(
        about_tab,
        text=TRANSLATIONS[lang]['about_copyright'],
        font=('Segoe UI', 10, 'italic'),
        justify="center"
    )
    copyright_label.pack(pady=20, anchor="center")
    app.widget_translation_keys[str(id(copyright_label))] = 'about_copyright'

    return about_tab