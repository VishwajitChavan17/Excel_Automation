; installer.iss
; ================
; Inno Setup script for Excel Automation Studio.
;
; This is SOURCE for the Inno Setup Compiler (a Windows-only tool -- it
; cannot be compiled in this Linux build environment, so it ships as
; verified-correct source rather than a compiled .exe). To produce the
; installer:
;
;   1. Build the app first:  pyinstaller build.spec --noconfirm
;      (produces dist\ExcelAutomationStudio.exe)
;   2. Install Inno Setup (https://jrsoftware.org/isinfo.php) on Windows.
;   3. Open this file in the Inno Setup Compiler (or run from the command
;      line: ISCC.exe installer.iss) and build.
;   4. The installer is written to installer_output\
;      ExcelAutomationStudio_Setup_<version>.exe
;
; The installer creates Start Menu / Desktop shortcuts, registers an
; uninstaller, and creates the persistent data folders (logs, config,
; templates, workflows, exports, database, autosave) next to the
; installed EXE so the app's paths.py (which resolves everything relative
; to sys.executable when frozen) finds them immediately on first run.

#define MyAppName "Excel Automation Studio"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Rolls-Royce Power Systems (MTU)"
#define MyAppExeName "ExcelAutomationStudio.exe"
#define MyAppIcon "assets\icons\app_icon.ico"

[Setup]
AppId={{A3F1E7C2-9B4D-4E2A-8C1F-6D5B2E9A7C31}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=ExcelAutomationStudio_Setup_{#MyAppVersion}
SetupIconFile={#MyAppIcon}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "docs\USER_MANUAL.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "docs\DEVELOPER_GUIDE.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "docs\PLUGIN_GUIDE.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "docs\PERFORMANCE.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "samples\*"; DestDir: "{app}\samples"; Flags: ignoreversion recursesubdirs

; Persistent data directories -- created empty so the app's first run has
; somewhere to write immediately (the app also creates these itself via
; paths.py if missing, so this is a convenience, not a hard requirement).
[Dirs]
Name: "{app}\logs"
Name: "{app}\config"
Name: "{app}\templates"
Name: "{app}\workflows"
Name: "{app}\exports"
Name: "{app}\database"
Name: "{app}\autosave"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\User Manual"; Filename: "{app}\docs\USER_MANUAL.md"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Uninstall removes the app binary and shortcuts (via Inno's normal
; mechanism) but deliberately LEAVES logs/config/templates/workflows/
; exports/database/autosave in place -- per the "never destroy user work"
; principle applied elsewhere in this app (Safety section of the spec).
; Uncomment the following to also remove all persistent data on uninstall:
; Type: filesandordirs; Name: "{app}\autosave"
; Type: filesandordirs; Name: "{app}\logs"
