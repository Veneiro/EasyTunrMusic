# EasyTunrMusic

Application to download songs and playlists with multiple configuration options.

## Usage

Install it with the setup file and open it from the Start menu. The interface is built with [Flet](https://flet.dev) (Flutter for Python), with light and dark themes and several accent colors.

You can search for songs and download them just by entering a query, but you can also download songs or playlists by using their URL. Currently, the app only works with YouTube due to Spotify’s DRM restrictions, but I’ll look into the possibility of supporting Spotify links in the future.

There are also some audio settings available for downloads under the "Audio" section. I believe there are enough options for most users, but if you notice an important one missing, feel free to let me know.

## Running from source / building

- **Run from source:** double-click `EasyTunrMusic.bat`. It sets up Python and the libraries in `runtime\` the first time.
- **Build the installer:** double-click `build.bat` (needs Python 3.9+ and [Inno Setup 6](https://jrsoftware.org/isinfo.php)). It produces `dist\EasyTunrMusic\` (portable) and `dist\installer\EasyTunrMusic-Setup-X.Y.Z.exe`. The version is set in `core/__init__.py`.

The app keeps its external tools (yt-dlp, FFmpeg, Deno) in `%LOCALAPPDATA%\EasyTunrMusic\bin`. It downloads any that are missing on first launch, and checks for yt-dlp updates every 12 hours, so YouTube changes don't require a new release. Logs go to `%LOCALAPPDATA%\EasyTunrMusic\easytunrmusic.log`.

Code layout: `core/` holds all download, audio, configuration and Spotify-import logic with no GUI dependency; `ui/` is the Flet interface on top of it; `main.py` starts the app.

# EasyTunrMusic

Aplicación para descargar canciones y listas de reproducción con múltiples opciones de configuración.

## Uso

Instálala con el archivo de instalación y ábrela desde el menú Inicio. La interfaz está hecha con [Flet](https://flet.dev) (Flutter para Python), con tema claro y oscuro y varios colores a elegir.

Puedes buscar canciones y descargarlas simplemente introduciendo una consulta, pero también puedes descargar canciones o listas de reproducción usando su URL. Actualmente, la aplicación solo funciona con YouTube debido a las restricciones de DRM de Spotify, pero en el futuro revisaré la posibilidad de admitir enlaces de Spotify.

También tienes algunas configuraciones de audio disponibles para las descargas en la sección "Audio". Creo que hay opciones suficientes para la mayoría de los usuarios, pero si ves que falta alguna opción importante, no dudes en decírmelo.
