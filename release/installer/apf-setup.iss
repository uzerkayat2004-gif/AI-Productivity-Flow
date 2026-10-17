; Inno Setup script — AI Productivity Flow single-file Windows installer.
; Two wizard screens: branded progress, then branded Finish.
; Per-user install, no admin, no mode / license / folder / tasks / ready pages.
; Staging paths are injected by release/build_windows_release.py
; (#define STAGING_ROOT / DIST_ROOT).

#define MyAppName "AI Productivity Flow"
#define MyAppVersion "1.0.4"
#define MyAppPublisher "Uzer Kayat"
#define MyAppURL "https://aiproductivityflow.site/"
#define MyAppExeName "pythonw.exe"

#ifndef REPO_ROOT
  #define REPO_ROOT "..\.."
#endif
#define SetupIconPath REPO_ROOT + "\src\voice_flow\gui\assets\icon.ico"
#define WizardLargePath REPO_ROOT + "\release\installer\wizard-large.png"
#define WizardSmallPath REPO_ROOT + "\release\installer\wizard-small.png"
#define LaunchScriptPath REPO_ROOT + "\release\installer\launch_apf.pyw"

[Setup]
AppId={{8E7B6C4A-52D1-4F3B-9A2E-6C4A52D12026}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL=https://github.com/uzerkayat2004-gif/AI-Productivity-Flow/issues
AppUpdatesURL=https://github.com/uzerkayat2004-gif/AI-Productivity-Flow/releases
DefaultDirName={localappdata}\Programs\{#MyAppName}
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
DisableWelcomePage=yes
DisableFinishedPage=no
PrivilegesRequired=lowest
OutputDir={#DIST_ROOT}
OutputBaseFilename=AI-Productivity-Flow-Setup-x64
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile={#SetupIconPath}
WizardImageFile={#WizardLargePath}
WizardSmallImageFile={#WizardSmallPath}
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\runtime\python\Lib\site-packages\voice_flow\gui\assets\icon.ico
Uninstallable=not IsPortableMode
VersionInfoVersion={#MyAppVersion}.0
VersionInfoTextVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=AI Productivity Flow Setup
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}.0
VersionInfoProductTextVersion={#MyAppVersion}
VersionInfoCopyright=Copyright (C) 2026 Uzer Kayat

[Messages]
FinishedHeadingLabel=AI Productivity Flow is installed
FinishedLabel=Launch is selected below. You can open the app any time from the desktop shortcut.%n%nCopyright 2026 Uzer Kayat. License and third-party notices are installed with the app.
ClickFinish=Finish
StatusExtractFiles=Installing AI Productivity Flow...
StatusCreatingIcons=Adding the desktop shortcut...

[CustomMessages]
; Embedded in the built installer so CI can confirm the page flow.
PageFlow=APF_WIZARD_PAGES:installing,finished

[Files]
; runtime\* is the whole private runtime. That includes runtime\code2video.
Source: "{#STAGING_ROOT}\runtime\*"; DestDir: "{app}\runtime"; Flags: recursesubdirs ignoreversion
Source: "{#STAGING_ROOT}\THIRD_PARTY_NOTICES.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#STAGING_ROOT}\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#LaunchScriptPath}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\runtime\python\{#MyAppExeName}"; Parameters: """{app}\launch_apf.pyw"""; WorkingDir: "{userdocs}"; IconFilename: "{app}\runtime\python\Lib\site-packages\voice_flow\gui\assets\icon.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\runtime\python\{#MyAppExeName}"; Parameters: """{app}\launch_apf.pyw"""; WorkingDir: "{userdocs}"; IconFilename: "{app}\runtime\python\Lib\site-packages\voice_flow\gui\assets\icon.ico"

[Run]
Filename: "{app}\runtime\vcredist\vc_redist.x64.exe"; Parameters: "/install /quiet /norestart"; Flags: runhidden; Check: NeedsVcRedist
Filename: "{app}\runtime\webview2\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; Flags: runhidden; Check: NeedsWebView2
Filename: "{app}\runtime\node\node.exe"; Parameters: """{app}\runtime\hyperframes\node_modules\hyperframes\bin\hyperframes.mjs"" browser ensure"; Flags: runhidden
Filename: "{app}\runtime\python\{#MyAppExeName}"; Parameters: """{app}\launch_apf.pyw"""; Description: "Launch AI Productivity Flow"; Flags: nowait postinstall skipifsilent
; /SILENT and /VERYSILENT skip the Finish checkbox above. Launch anyway so a
; one-click update opens the app again when the installer is done.
Filename: "{app}\runtime\python\{#MyAppExeName}"; Parameters: """{app}\launch_apf.pyw"""; Flags: nowait; Check: IsSilentSetup

[UninstallDelete]
Type: filesandordirs; Name: "{app}\runtime"
Type: filesandordirs; Name: "{group}"

[UninstallRun]
Filename: "{app}\runtime\python\python.exe"; Parameters: "-m voice_flow.release_cleanup_autorun"; Flags: runhidden; RunOnceId: "remove_autorun"

[Code]
procedure StyleWizard;
begin
  { Brand colours: ink #1c140f, paper #f7f4f1, accent #ff6020. }
  WizardForm.Color := $00F1F4F7;
  WizardForm.MainPanel.Color := $00F1F4F7;
  WizardForm.Bevel.Visible := False;
  WizardForm.FinishedHeadingLabel.Font.Color := $000F141C;
  WizardForm.FinishedLabel.Font.Color := $00404040;
  { TNewProgressBar has no ForeColor in Inno's script classes. The accent
    is carried by the wizard images and the paper background. }
  WizardForm.StatusLabel.Font.Color := $000F141C;
end;

procedure InitializeWizard;
begin
  StyleWizard;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  StyleWizard;
  if CurPageID = wpInstalling then
    WizardForm.StatusLabel.Caption := 'Installing AI Productivity Flow...';
end;

function IsPortableMode: Boolean;
begin
  Result := ExpandConstant('{param:portable|0}') = '1';
end;

function IsSilentSetup: Boolean;
begin
  Result := WizardSilent;
end;

function NeedsVcRedist: Boolean;
var
  version: string;
begin
  Result := not RegQueryStringValue(HKLM,
    'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64',
    'Version', version);
end;

function NeedsWebView2: Boolean;
var
  version: string;
begin
  Result := not (RegQueryStringValue(HKLM,
      'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
      'pv', version) or
    RegQueryStringValue(HKCU,
      'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
      'pv', version));
  if Result then
    Result := not RegQueryStringValue(HKLM,
      'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
      'pv', version);
end;
