@echo off
rem Genera dist\EasyTunrMusic (app portable) y dist\installer\EasyTunrMusic-Setup-X.Y.Z.exe
rem Opciones: -RefreshTools (vuelve a descargar yt-dlp/FFmpeg/Deno)  -SkipInstaller
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\build.ps1" %*
if errorlevel 1 (
    echo.
    echo [ERROR] El build ha fallado.
    pause
    exit /b 1
)
pause
