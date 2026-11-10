# EasyTunrMusic

Application to download songs and playlists with multiple configuration options.

## Usage

Install it with the setup file and open it from the Start menu. The interface is built with [Flet](https://flet.dev) (Flutter for Python), with light and dark themes and several accent colors.

You can search for songs and download them just by entering a query, or download songs and playlists from their YouTube URL.

### Spotify playlists, albums and songs

Spotify's audio is protected by DRM, so the app doesn't download from Spotify: it reads the list of songs and looks each one up on YouTube, picking the video that matches the title, artist and duration (official uploads are preferred, and covers, live versions or remixes are skipped unless that's what the Spotify song is).

- **Paste a Spotify link** (playlist, album or song) and it's imported directly. Without signing in, Spotify only shows the first 100 songs of a playlist, so for longer playlists:
- **Load a CSV** exported from Spotify (for example with [Exportify](https://exportify.net)). It works with playlists of any size.

Before downloading you can review every song: which video was chosen and how far its duration is from Spotify's, play it on YouTube, swap it for another one or search manually for the songs that weren't found. If a video turns out to be blocked, the next best match is downloaded instead. When you import the same list again, the songs you already have are skipped, so only new songs are downloaded.

Imported songs are saved with Spotify's title, artist, album, year and cover art, and each playlist gets a `.m3u8` file you can open in other players (phone, car...).

### Audio options

The "Audio" section has the format and quality settings (MP3, AAC, Opus, FLAC, ALAC, WAV), volume normalization and a few extras:

- **Download lyrics**: saves synced lyrics (`.lrc`) next to each song, from [LRCLIB](https://lrclib.net). They are only kept when the song's length matches, so they stay in sync.
- **Remove non-music parts**: trims intros and dialogue from music videos using [SponsorBlock](https://sponsor.ajay.app).

### Library and player

The "Library" section lists everything in your download folder, with a built-in player: shuffle (spreads artists out and leaves recently played songs for later), repeat, play queue and synced lyrics. It can also find duplicate songs and export what you're viewing as a `.m3u8` playlist.

## Running from source / building

- **Run from source:** double-click `EasyTunrMusic.bat`. It sets up Python and the libraries in `runtime\` the first time.
- **Run the tests:** `python -m unittest discover -s tests -t .` from the project folder. They don't need internet access or the external tools.
- **Build the installer:** double-click `build.bat` (needs Python 3.9+ and [Inno Setup 6](https://jrsoftware.org/isinfo.php)). It produces `dist\EasyTunrMusic\` (portable) and `dist\installer\EasyTunrMusic-Setup-X.Y.Z.exe`. The version is set in `core/__init__.py`.

- **Publish a release:** set `__version__` in `core/__init__.py` (e.g. `"2.0.1"`), write the notes in `release-notes/2.0.1.md`, commit and push, then `git tag v2.0.1 && git push origin v2.0.1`. The GitHub Actions workflow (`.github/workflows/release.yml`) builds the installer on Windows and creates the GitHub release with it and those notes, which the app shows as "what's new". Nothing has to be uploaded by hand.

**Automatic updates:** the installed app checks the latest GitHub release every time it opens (can be turned off in Settings). If there is a newer version, it shows its notes and, on "Update now", downloads `EasyTunrMusic-Setup-X.Y.Z.exe`, verifies its SHA-256, runs it silently and reopens itself on the new version. Settings, music and downloaded tools are kept.

The app keeps its external tools (yt-dlp, FFmpeg, Deno) in `%LOCALAPPDATA%\EasyTunrMusic\bin`. It downloads any that are missing on first launch, and checks for yt-dlp updates every 12 hours, so YouTube changes don't require a new release. Logs go to `%LOCALAPPDATA%\EasyTunrMusic\easytunrmusic.log`.

Code layout: `core/` holds all download, audio, configuration and Spotify-import logic with no GUI dependency (song matching in `spotify.py`, Spotify links in `spotify_link.py`, tags in `tagging.py`, lyrics in `lyrics.py`, shuffle in `shuffle.py`); `ui/` is the Flet interface on top of it; `tests/` covers the core; `main.py` starts the app.

# EasyTunrMusic

Aplicación para descargar canciones y listas de reproducción con múltiples opciones de configuración.

## Uso

Instálala con el archivo de instalación y ábrela desde el menú Inicio. La interfaz está hecha con [Flet](https://flet.dev) (Flutter para Python), con tema claro y oscuro y varios colores a elegir.

Puedes buscar canciones y descargarlas simplemente introduciendo una consulta, o descargar canciones y listas de reproducción a partir de su enlace de YouTube.

### Playlists, álbumes y canciones de Spotify

El audio de Spotify está protegido con DRM, así que la app no descarga de Spotify: lee la lista de canciones y busca cada una en YouTube, eligiendo el vídeo que coincide en título, artista y duración (se prefieren las subidas oficiales y se descartan covers, directos o remixes, salvo que la canción de Spotify sea eso).

- **Pega un enlace de Spotify** (playlist, álbum o canción) y se importa directamente. Sin iniciar sesión, Spotify solo muestra las primeras 100 canciones de una playlist, así que para las más largas:
- **Carga un CSV** exportado de Spotify (por ejemplo con [Exportify](https://exportify.net)). Funciona con playlists de cualquier tamaño.

Antes de descargar puedes revisar cada canción: qué vídeo se ha elegido y cuánto se diferencia su duración de la de Spotify, escucharlo en YouTube, cambiarlo por otro o buscar a mano las que no se encontraron. Si un vídeo resulta estar bloqueado, se descarga el siguiente mejor candidato. Al volver a importar la misma lista, las canciones que ya tienes se saltan y solo se descargan las nuevas.

Las canciones importadas se guardan con el título, artista, álbum, año y carátula de Spotify, y cada playlist tiene su archivo `.m3u8` para abrirla en otros reproductores (móvil, coche...).

### Opciones de audio

En la sección "Audio" están el formato y la calidad (MP3, AAC, Opus, FLAC, ALAC, WAV), la normalización del volumen y algunos extras:

- **Descargar letras**: guarda la letra sincronizada (`.lrc`) junto a cada canción, desde [LRCLIB](https://lrclib.net). Solo se guarda si la duración coincide con la de la canción, para que vaya a tiempo.
- **Quitar partes sin música**: recorta intros y diálogos de los videoclips con [SponsorBlock](https://sponsor.ajay.app).

### Biblioteca y reproductor

La sección "Biblioteca" muestra todo lo que hay en tu carpeta de descargas, con un reproductor integrado: aleatorio (reparte los artistas y deja para más tarde lo que has escuchado hace poco), repetir, cola de reproducción y letra sincronizada. También puede buscar canciones duplicadas y exportar lo que estés viendo como lista `.m3u8`.
