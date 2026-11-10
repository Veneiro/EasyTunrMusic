# Build de EasyTunrMusic: ejecutable (PyInstaller) + instalador (Inno Setup).
#
# Uso:  powershell -ExecutionPolicy Bypass -File packaging\build.ps1 [-RefreshTools] [-SkipInstaller]
#   -RefreshTools   vuelve a descargar yt-dlp, FFmpeg y Deno aunque ya esten en packaging\vendor
#   -SkipInstaller  genera solo la carpeta dist\EasyTunrMusic, sin compilar el instalador
#
# Resultado:
#   dist\EasyTunrMusic\                        app portable (se puede comprimir en .zip)
#   dist\installer\EasyTunrMusic-Setup-X.Y.Z.exe

param(
    [switch]$RefreshTools,
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # Invoke-WebRequest es mucho mas rapido sin barra
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Root      = Split-Path -Parent $PSScriptRoot
$BuildVenv = Join-Path $Root ".build-venv"
$Vendor    = Join-Path $PSScriptRoot "vendor\bin"
$Dist      = Join-Path $Root "dist"
$Work      = Join-Path $Root "build\pyinstaller"
$AppDist   = Join-Path $Dist "EasyTunrMusic"

function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }

# ------------------------------------------------------------------ version
$initPy = Get-Content (Join-Path $Root "core\__init__.py") -Raw
if ($initPy -notmatch '__version__\s*=\s*"([^"]+)"') { throw "No se encontro __version__ en core\__init__.py" }
$Version = $Matches[1]
Write-Host "EasyTunrMusic $Version" -ForegroundColor Green

# ------------------------------------------------------------------ python
Step "Buscando Python (CPython de Windows con tkinter)"
$check = "import sys, sysconfig, tkinter; sys.exit(0 if sys.version_info >= (3,9) and sysconfig.get_platform().startswith('win') else 1)"
$BasePy = $null
foreach ($cand in @(@("py", "-3"), @("python"))) {
    $exe = $cand[0]; $args0 = $cand[1..($cand.Length)]
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
    & $exe @args0 -c $check 2>$null
    if ($LASTEXITCODE -eq 0) {
        $BasePy = (& $exe @args0 -c "import sys; print(sys.executable)").Trim()
        break
    }
}
if (-not $BasePy) { throw "No se encontro un Python valido. Instala Python 3.9+ desde python.org." }
Write-Host "Python: $BasePy"

$Py = Join-Path $BuildVenv "Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Step "Creando entorno de build"
    & $BasePy -m venv $BuildVenv
    if ($LASTEXITCODE -ne 0) { throw "No se pudo crear el entorno virtual" }
}
Step "Instalando dependencias de build"
& $Py -m pip install --quiet --disable-pip-version-check --upgrade pip
& $Py -m pip install --quiet --disable-pip-version-check -r (Join-Path $Root "requirements.txt") pyinstaller
if ($LASTEXITCODE -ne 0) { throw "Fallo pip install" }

# ------------------------------------------------------------------ herramientas
Step "Preparando yt-dlp, FFmpeg y Deno en packaging\vendor\bin"
New-Item -ItemType Directory -Force $Vendor | Out-Null

# curl.exe (incluido en Windows 10/11): Invoke-WebRequest de PowerShell 5.1 es
# lentisimo con archivos grandes.
function Get-File($url, $dest) {
    & curl.exe -L --fail --silent --show-error --retry 3 -o $dest $url
    if ($LASTEXITCODE -ne 0) { throw "Fallo la descarga de $url" }
}

function Get-ZipTool($url, $names) {
    $zip = Join-Path $env:TEMP ("etm_" + [IO.Path]::GetRandomFileName() + ".zip")
    $tmp = Join-Path $env:TEMP ("etm_" + [IO.Path]::GetRandomFileName())
    try {
        Get-File $url $zip
        Expand-Archive -LiteralPath $zip -DestinationPath $tmp -Force
        foreach ($name in $names) {
            $found = Get-ChildItem -Path $tmp -Recurse -Filter $name | Select-Object -First 1
            if (-not $found) { throw "$name no esta en $url" }
            Copy-Item $found.FullName (Join-Path $Vendor $name) -Force
        }
    } finally {
        Remove-Item $zip -Force -ErrorAction SilentlyContinue
        Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

if ($RefreshTools -or -not (Test-Path (Join-Path $Vendor "yt-dlp.exe"))) {
    Write-Host "Descargando yt-dlp..."
    Get-File "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe" (Join-Path $Vendor "yt-dlp.exe")
}
if ($RefreshTools -or -not (Test-Path (Join-Path $Vendor "ffmpeg.exe"))) {
    Write-Host "Descargando FFmpeg..."
    Get-ZipTool "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" @("ffmpeg.exe", "ffprobe.exe")
}
if ($RefreshTools -or -not (Test-Path (Join-Path $Vendor "deno.exe"))) {
    Write-Host "Descargando Deno..."
    Get-ZipTool "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip" @("deno.exe")
}
Get-ChildItem $Vendor | ForEach-Object { "{0,-12} {1,8:N1} MB" -f $_.Name, ($_.Length / 1MB) }

# ------------------------------------------------------------------ pyinstaller
Step "Generando el ejecutable con PyInstaller"
if (Test-Path $AppDist) { Remove-Item $AppDist -Recurse -Force }
$icon = Join-Path $Root "icon.ico"
Push-Location $Root
try {
    & $Py -m PyInstaller --noconfirm --clean --windowed --onedir `
        --name EasyTunrMusic `
        --icon $icon `
        --add-data "$icon;." `
        --collect-data ttkbootstrap `
        --distpath $Dist --workpath $Work --specpath $Work `
        (Join-Path $Root "main.py")
    if ($LASTEXITCODE -ne 0) { throw "Fallo PyInstaller" }
} finally { Pop-Location }

Step "Copiando herramientas junto al ejecutable"
Copy-Item -Path $Vendor -Destination (Join-Path $AppDist "bin") -Recurse -Force
Copy-Item (Join-Path $Root "LICENSE") $AppDist -Force

# ------------------------------------------------------------------ instalador
if ($SkipInstaller) {
    Write-Host "`nListo: $AppDist" -ForegroundColor Green
    exit 0
}

Step "Compilando el instalador con Inno Setup"
$iscc = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    throw "No se encontro Inno Setup 6. Instalalo con: winget install JRSoftware.InnoSetup  (o usa -SkipInstaller)"
}
& $iscc /Q "/DAppVersion=$Version" "/DSourceDir=$AppDist" "/O$(Join-Path $Dist 'installer')" (Join-Path $PSScriptRoot "installer.iss")
if ($LASTEXITCODE -ne 0) { throw "Fallo Inno Setup" }

$setup = Join-Path $Dist "installer\EasyTunrMusic-Setup-$Version.exe"
Write-Host ("`nListo: {0} ({1:N0} MB)" -f $setup, ((Get-Item $setup).Length / 1MB)) -ForegroundColor Green
