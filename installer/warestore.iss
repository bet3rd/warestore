; Inno Setup script for WareStore.
;
; Packages the PyInstaller onedir build (dist\WareStore\) into a single
; WareStoreSetup.exe that installs to Program Files, adds a Start Menu shortcut
; and uninstaller, and upgrades in place (closing a running instance first).
; The app itself writes all user data to %APPDATA%\SteamLoginTool_CLI, so the
; Program Files install dir stays read-only at runtime.
;
; Version is passed in by the build: ISCC /DMyAppVersion=<x> (see scripts\build.bat).

#ifndef MyAppVersion
  #define MyAppVersion "0.0"
#endif

#define MyAppName "WareStore - Account Manager"
#define MyAppPublisher "WareStore"
#define MyAppExeName "WareStore.exe"

[Setup]
; Stable AppId — keeps upgrades/uninstall tied to one entry. Do NOT change it.
AppId={{8F2A5C10-4E3B-4D9A-9C21-7B6E0F1A2D34}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
; Display name is "WareStore - Account Manager"; keep the install path short.
DefaultDirName={autopf}\WareStore
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
OutputDir=..\dist
OutputBaseFilename=WareStoreSetup
SetupIconFile=..\assets\warestore.ico
; Branded wizard graphics (dark WareStore theme), matched to the app.
WizardImageFile=wizard_large.png
WizardSmallImageFile=wizard_small.png
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Modern style hides the welcome page by default; show it so the branded
; WizardImageFile leads the install.
DisableWelcomePage=no
; Admin: needed for Program Files and the app's HWID spoofer / Steam manipulation.
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Close a running WareStore before upgrading, so files aren't locked.
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\WareStore\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[Code]
// On uninstall, offer to also delete user data (accounts, tokens, settings,
// HWID profiles, backups). Defaults to No so a reinstall keeps everything.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\SteamLoginTool_CLI');
    if DirExists(DataDir) then
    begin
      if MsgBox('Also delete your saved WareStore data?' + #13#10#13#10 +
                'This permanently removes your accounts, tokens, settings, HWID ' +
                'profiles and backups.' + #13#10 +
                'Choose No to keep them for a future reinstall.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;
