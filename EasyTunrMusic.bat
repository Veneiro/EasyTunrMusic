@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title EasyTunrMusic
cd /d "%~dp0"

rem ============================================================
rem  EasyTunrMusic - lanzador portable
rem  La primera vez descarga Python y las librerias en
rem  la carpeta "runtime" (no toca el sistema ni el PATH global).
rem  Las siguientes veces solo abre la app.
rem ============================================================

set "APP_DIR=%~dp0"
set "RT=%APP_DIR%runtime"
set "PY_DIR=%RT%\python"
set "VENV=%RT%\venv"
set "PY_VER=3.12.10"
set "PY_URL=https://www.python.org/ftp/python/%PY_VER%/python-%PY_VER%-amd64.exe"

if not exist "%RT%" mkdir "%RT%"

rem ---------- 1. Python ----------
set "BASE_PY="
if exist "%PY_DIR%\python.exe" set "BASE_PY=%PY_DIR%\python.exe"

if not defined BASE_PY (
    rem Probar un Python ya instalado (>=3.9 y con tkinter)
    for %%C in ("py -3" "python") do (
        if not defined BASE_PY (
            %%~C -c "import sys, sysconfig, tkinter; sys.exit(0 if sys.version_info >= (3,9) and sysconfig.get_platform().startswith('win') else 1)" >nul 2>&1
            if !errorlevel! == 0 (
                for /f "delims=" %%P in ('%%~C -c "import sys; print(sys.executable)"') do set "BASE_PY=%%P"
            )
        )
    )
)

if not defined BASE_PY (
    echo [1/3] Descargando Python %PY_VER% ^(solo la primera vez^)...
    curl -L --fail -o "%RT%\python-installer.exe" "%PY_URL%"
    if errorlevel 1 goto :error_net
    echo       Instalando Python en "%PY_DIR%"...
    "%RT%\python-installer.exe" /quiet InstallAllUsers=0 PrependPath=0 Include_launcher=0 Include_test=0 Include_doc=0 Include_tcltk=1 Include_pip=1 Shortcuts=0 AssociateFiles=0 TargetDir="%PY_DIR%"
    del "%RT%\python-installer.exe" >nul 2>&1
    if not exist "%PY_DIR%\python.exe" (
        echo [ERROR] No se pudo instalar Python.
        goto :fail
    )
    set "BASE_PY=%PY_DIR%\python.exe"
) else (
    echo [1/3] Python encontrado: !BASE_PY!
)

rem ---------- 2. Entorno virtual + librerias ----------
if not exist "%VENV%\Scripts\python.exe" (
    echo [2/3] Creando entorno virtual...
    "%BASE_PY%" -m venv "%VENV%"
    if not exist "%VENV%\Scripts\python.exe" (
        echo [ERROR] No se pudo crear el entorno virtual.
        goto :fail
    )
    "%VENV%\Scripts\python.exe" -m pip install --upgrade pip --quiet --disable-pip-version-check
)

echo [2/3] Comprobando librerias...
"%VENV%\Scripts\python.exe" -m pip install -r "%APP_DIR%requirements.txt" --quiet --disable-pip-version-check
if errorlevel 1 (
    "%VENV%\Scripts\python.exe" -c "import ttkbootstrap" >nul 2>&1
    if errorlevel 1 goto :error_net
    echo       Sin conexion: se usan las librerias ya instaladas.
)

rem yt-dlp, FFmpeg y Deno los descarga y actualiza la propia app
rem en %LOCALAPPDATA%\EasyTunrMusic\bin la primera vez que se abre.

rem ---------- 3. Lanzar la app ----------
echo [3/3] Abriendo EasyTunrMusic...
start "" "%VENV%\Scripts\pythonw.exe" "%APP_DIR%main.py"
exit /b 0

:error_net
echo.
echo [ERROR] Fallo una descarga. Revisa tu conexion a Internet y vuelve a intentarlo.
:fail
echo.
pause
exit /b 1
