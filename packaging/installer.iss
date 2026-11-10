; Instalador de EasyTunrMusic (Inno Setup 6).
; Se compila desde packaging\build.ps1, que pasa AppVersion y SourceDir.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\EasyTunrMusic"
#endif

#define AppName "EasyTunrMusic"
#define AppExe  "EasyTunrMusic.exe"

[Setup]
AppId={{6F1C2A57-9D3E-4B8A-A1F2-EA57C0DE7A11}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Veneiro
AppPublisherURL=https://github.com/Veneiro/EasyTunrMusic
AppSupportURL=https://github.com/Veneiro/EasyTunrMusic/issues
; Sin permisos de administrador por defecto: se instala para el usuario actual
; (%LOCALAPPDATA%\Programs). El usuario puede elegir "para todos" en el asistente.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
LicenseFile={#SourceDir}\LICENSE
SetupIconFile=..\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
OutputBaseFilename={#AppName}-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
; Actualizacion lanzada desde la propia app (/SILENT /UPDATE=1): volver a abrirla al terminar.
; Una instalacion silenciosa normal (p. ej. desatendida) no abre la app.
Filename: "{app}\{#AppExe}"; Flags: nowait skipifnotsilent; Check: IsAppUpdate

[UninstallDelete]
; Herramientas descargadas/actualizadas por la app (no toca la musica ni la configuracion)
Type: filesandordirs; Name: "{localappdata}\{#AppName}\bin"

[Code]
function IsAppUpdate: Boolean;
begin
  Result := ExpandConstant('{param:UPDATE|0}') = '1';
end;
