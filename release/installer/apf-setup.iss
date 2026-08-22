; Inno Setup script — AI Productivity Flow single-file Windows installer.
; Per-user install, no admin required. Staging paths are injected by
; release/build_windows_release.py (#define STAGING_ROOT / DIST_ROOT).

#define MyAppName "AI Productivity Flow"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "AI Productivity Flow"
#define MyAppExeName "pythonw.exe"

[Setup]
AppId={{8E7B6C4A-52D1-4F3B-9A2E-6C4A52D12026}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#DIST_ROOT}
OutputBaseFilename=AI-Productivity-Flow-Setup-x64
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayName={#MyAppName}
Uninstallable=not IsPortableMode

[Files]
Source: "{#STAGING_ROOT}\runtime\*"; DestDir: "{app}\runtime"; Flags: recursesubdirs ignoreversion
Source: "{#STAGING_ROOT}\THIRD_PARTY_NOTICES.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#STAGING_ROOT}\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\runtime\python\{#MyAppExeName}"; Parameters: "-m voice_flow.watchdog"; WorkingDir: "{userdocs}"; IconFilename: "{app}\runtime\python\Lib\site-packages\voice_flow\gui\assets\icon.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\runtime\python\{#MyAppExeName}"; Parameters: "-m voice_flow.watchdog"; WorkingDir: "{userdocs}"; IconFilename: "{app}\runtime\python\Lib\site-packages\voice_flow\gui\assets\icon.ico"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Run]
; VC++ redistributable (silent, idempotent) — required by native wheels on
; clean machines; skipped if the machine-level install is missing.
Filename: "{app}\runtime\vcredist\vc_redist.x64.exe"; Parameters: "/install /quiet /norestart"; Flags: runhidden; Check: NeedsVcRedist
; WebView2 Evergreen (silent) only when no WebView2 runtime is present.
Filename: "{app}\runtime\webview2\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; Flags: runhidden; Check: NeedsWebView2
; Provision the pinned chrome-headless-shell render browser through
; HyperFrames' official command (Google Chrome for Testing endpoints; the
; binary is not redistributed in this installer). Failure is non-fatal: the
; application retries provisioning before the first render.
Filename: "{app}\runtime\node\node.exe"; Parameters: """{app}\runtime\hyperframes\node_modules\hyperframes\bin\hyperframes.mjs"" browser ensure"; Flags: runhidden
; Launch (user checkbox at the end of the wizard).
Filename: "{app}\runtime\python\{#MyAppExeName}"; Parameters: "-m voice_flow.watchdog"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\runtime"
Type: filesandordirs; Name: "{group}"

[UninstallRun]
; Remove the app's own autostart registration if present (user data under
; ~/.voice_flow is intentionally preserved).
Filename: "{app}\runtime\python\python.exe"; Parameters: "-m voice_flow.release_cleanup_autorun"; Flags: runhidden; RunOnceId: "remove_autorun"

[Code]
function IsPortableMode: Boolean;
begin
  Result := ExpandConstant('{param:portable|0}') = '1';
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
