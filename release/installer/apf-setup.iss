; Inno Setup script — AI Productivity Flow single-file Windows installer.
; Two wizard screens: branded progress, then branded Finish.
; Per-user install, no admin, no mode / license / folder / tasks / ready pages.
; Staging paths are injected by release/build_windows_release.py
; (#define STAGING_ROOT / DIST_ROOT).

#define MyAppName "AI Productivity Flow"
#define MyAppVersion "1.0.14"
#define MyAppDisplayVersion "1.0"
#define MyAppPublisher "Uzer Kayat"
#define MyAppURL "https://aiproductivityflow.site/"
#define MyAppExeName "pythonw.exe"
; Same id the app sets at runtime (desktop_launcher / early_splash), so the
; taskbar ties the running window to these shortcuts and shows the logo.
#define MyAppUserModelID "antigravity.voiceflow.desktop.1.0"

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
AppVerName={#MyAppName} {#MyAppDisplayVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL=https://github.com/uzerkayat2004-gif/AI-Productivity-Flow/issues
AppUpdatesURL=https://github.com/uzerkayat2004-gif/AI-Productivity-Flow/releases
DefaultDirName={localappdata}\Programs\{#MyAppName}
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
; Without this, DisableProgramGroupPage stores the shortcut in Programs\(Default).
DefaultGroupName={#MyAppName}
; An upgrade would otherwise reuse the group saved by the older installer,
; which is "(Default)" for builds that had no DefaultGroupName.
UsePreviousGroup=no
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
FinishedLabel=Version 1.0 is on this PC. Launch is selected below. You can open the app any time from the desktop shortcut.%n%nCopyright 2026 Uzer Kayat. License and third-party notices are installed with the app.
ClickFinish=Finish
; Inno still opens this page when it would be the first one, and ignores
; DisableReadyPage. The labels below match the Installing page until Next fires.
WizardReady=Installing AI Productivity Flow
ReadyLabel1=Installing AI Productivity Flow...
ReadyLabel2a=Installing AI Productivity Flow...
ReadyLabel2b=Installing AI Productivity Flow...
StatusExtractFiles=Installing AI Productivity Flow...
StatusCreatingIcons=Adding the desktop shortcut...

[CustomMessages]
; Embedded in the built installer so CI can confirm the page flow.
PageFlow=APF_WIZARD_PAGES:installing,finished

[Files]
; runtime\* is the whole private runtime. That includes runtime\code2video.
; pip and the C headers stay in staging for later build steps but are never
; used by the installed app; leaving them out saves ~1,070 files for Defender.
Source: "{#STAGING_ROOT}\runtime\*"; DestDir: "{app}\runtime"; Excludes: "\python\Lib\site-packages\pip,\python\Lib\site-packages\pip\*,\python\Lib\site-packages\pip-*.dist-info,\python\Lib\site-packages\pip-*.dist-info\*,\python\include,\python\include\*"; Flags: recursesubdirs ignoreversion
Source: "{#STAGING_ROOT}\THIRD_PARTY_NOTICES.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#STAGING_ROOT}\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#LaunchScriptPath}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\runtime\python\{#MyAppExeName}"; Parameters: """{app}\launch_apf.pyw"""; WorkingDir: "{app}"; IconFilename: "{app}\runtime\python\Lib\site-packages\voice_flow\gui\assets\icon.ico"; AppUserModelID: "{#MyAppUserModelID}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\runtime\python\{#MyAppExeName}"; Parameters: """{app}\launch_apf.pyw"""; WorkingDir: "{app}"; IconFilename: "{app}\runtime\python\Lib\site-packages\voice_flow\gui\assets\icon.ico"; AppUserModelID: "{#MyAppUserModelID}"

[Run]
Filename: "{app}\runtime\vcredist\vc_redist.x64.exe"; Parameters: "/install /quiet /norestart"; Flags: runhidden; Check: NeedsVcRedist
Filename: "{app}\runtime\webview2\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; Flags: runhidden; Check: NeedsWebView2
; No render-browser download here any more. `hyperframes browser ensure` used
; to start (nowait) right before the app's first launch and competed with it
; for CPU, disk and network. The app now prepares it in the background at
; idle priority after it is up (runtime_env.schedule_render_browser_prefetch),
; or on demand before the first Video Flow render.
Filename: "{app}\runtime\python\{#MyAppExeName}"; Parameters: """{app}\launch_apf.pyw"""; WorkingDir: "{app}"; Description: "Launch AI Productivity Flow"; Flags: shellexec nowait postinstall skipifsilent runasoriginaluser
; /SILENT and /VERYSILENT skip the Finish checkbox above. Launch anyway so a
; one-click update opens the app again when the installer is done.
Filename: "{app}\runtime\python\{#MyAppExeName}"; Parameters: """{app}\launch_apf.pyw"""; WorkingDir: "{app}"; Flags: nowait runasoriginaluser; Check: IsSilentSetup

[UninstallDelete]
; Installed files, the bundled runtime, and the shortcut group.
; Personal files stay unless uninstall asks and the user agrees.
Type: filesandordirs; Name: "{app}\runtime"
Type: filesandordirs; Name: "{app}"
Type: filesandordirs; Name: "{group}"

[UninstallRun]
Filename: "{app}\runtime\python\python.exe"; Parameters: "-m voice_flow.release_cleanup_autorun"; Flags: runhidden; RunOnceId: "remove_autorun"

[Code]
const
  PBM_SETBARCOLOR = $0409;
  BM_CLICK = $00F5;

var
  ReadyPageAdvanced: Boolean;

procedure SetWindowTheme(Wnd: HWND; SubAppName, SubIdList: String);
  external 'SetWindowTheme@uxtheme.dll stdcall';
function SendMessageW(hWnd: HWND; Msg: Cardinal; wParam, lParam: Longint): Longint;
  external 'SendMessageW@user32.dll stdcall';
function PostMessageW(hWnd: HWND; Msg: Cardinal; wParam, lParam: Longint): Longint;
  external 'PostMessageW@user32.dll stdcall';

procedure StyleProgressBar;
begin
  try
    SetWindowTheme(WizardForm.ProgressGauge.Handle, '', '');
    SendMessageW(WizardForm.ProgressGauge.Handle, PBM_SETBARCOLOR, 0, $001A6AFF);
  except
  end;
end;

procedure StyleWizard;
begin
  { Brand colours: ink #1c140f, paper #fff8f3, accent #ff6a1a. }
  WizardForm.Color := $00F3F8FF;
  WizardForm.MainPanel.Color := $00F3F8FF;
  WizardForm.Bevel.Visible := False;
  WizardForm.FinishedHeadingLabel.Font.Color := $000F141C;
  WizardForm.FinishedHeadingLabel.Font.Style := [fsBold];
  WizardForm.FinishedHeadingLabel.Font.Size := 14;
  WizardForm.FinishedLabel.Font.Color := $004F565C;
  WizardForm.FinishedLabel.Font.Size := 10;
  WizardForm.StatusLabel.Font.Color := $000F141C;
end;

procedure DeleteStaleShortcut(const ShortcutPath: String);
begin
  if FileExists(ShortcutPath) then
    DeleteFile(ShortcutPath);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    { Replace any older desktop or Start-menu shortcut, including ones that
      still launch wscript.exe and a development VoiceFlowLauncher.vbs. }
    DeleteStaleShortcut(ExpandConstant('{autodesktop}\{#MyAppName}.lnk'));
    DeleteStaleShortcut(ExpandConstant('{userdesktop}\{#MyAppName}.lnk'));
    DeleteStaleShortcut(ExpandConstant('{commondesktop}\{#MyAppName}.lnk'));
    DeleteStaleShortcut(ExpandConstant('{autoprograms}\{#MyAppName}.lnk'));
    DeleteStaleShortcut(ExpandConstant('{userprograms}\{#MyAppName}.lnk'));
    DeleteStaleShortcut(ExpandConstant('{commonprograms}\{#MyAppName}.lnk'));
    DeleteStaleShortcut(ExpandConstant('{group}\{#MyAppName}.lnk'));
    { Upgrades from a build that had no DefaultGroupName. }
    DeleteStaleShortcut(ExpandConstant('{userprograms}\(Default)\{#MyAppName}.lnk'));
    DeleteStaleShortcut(ExpandConstant('{autoprograms}\(Default)\{#MyAppName}.lnk'));
    DeleteStaleShortcut(ExpandConstant('{commonprograms}\(Default)\{#MyAppName}.lnk'));
    RemoveDir(ExpandConstant('{userprograms}\(Default)'));
    RemoveDir(ExpandConstant('{autoprograms}\(Default)'));
    RemoveDir(ExpandConstant('{commonprograms}\(Default)'));
  end;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = wpWelcome) or (PageID = wpLicense) or (PageID = wpSelectDir)
    or (PageID = wpSelectProgramGroup) or (PageID = wpReady);
end;

procedure InitializeWizard;
begin
  StyleWizard;
  StyleProgressBar;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  StyleWizard;
  { DisableReadyPage is ignored when Ready would be the first wizard page.
    Advance immediately so the only screens are Installing and Finish.
    shellexec nowait on the Finish launch keeps that click from waiting. }
  if (CurPageID = wpReady) and (not ReadyPageAdvanced) then
  begin
    ReadyPageAdvanced := True;
    WizardForm.PageNameLabel.Caption := 'Installing AI Productivity Flow';
    WizardForm.PageDescriptionLabel.Caption := 'Please wait while Setup installs AI Productivity Flow on your computer.';
    WizardForm.ReadyLabel.Caption := 'Installing AI Productivity Flow...';
    WizardForm.ReadyMemo.Visible := False;
    WizardForm.BackButton.Visible := False;
    PostMessageW(WizardForm.NextButton.Handle, BM_CLICK, 0, 0);
  end;
  if CurPageID = wpInstalling then
  begin
    WizardForm.StatusLabel.Visible := True;
    WizardForm.StatusLabel.Caption := 'Installing AI Productivity Flow...';
    StyleProgressBar;
  end;
  if CurPageID = wpFinished then
  begin
    WizardForm.StatusLabel.Visible := False;
    WizardForm.StatusLabel.Caption := '';
    WizardForm.FilenameLabel.Visible := False;
    WizardForm.FilenameLabel.Caption := '';
  end;
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

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    DataDir := ExpandConstant('{userprofile}\.voice_flow');
    if DirExists(DataDir) then
    begin
      { No is the default, so a silent uninstall keeps personal files. }
      if MsgBox('Remove my data (dictionary, history, and settings)?' + #13#10 + #13#10 +
        'Choose No to keep them on this PC.',
        mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
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
