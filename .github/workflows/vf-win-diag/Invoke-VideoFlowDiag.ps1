param(
    [Parameter(Mandatory = $true)][string]$InstallRoot,
    [Parameter(Mandatory = $true)][string]$Artifacts,
    [Parameter(Mandatory = $true)][string]$Label
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $Artifacts | Out-Null
$logPath = Join-Path $Artifacts "harness.log"

function Log([string]$Message) {
    $line = "{0} {1}" -f (Get-Date -Format "HH:mm:ss"), $Message
    Add-Content -Path $logPath -Value $line
    Write-Host $line
}

Add-Type -Language CSharp -ReferencedAssemblies System.Drawing, System.Windows.Forms -TypeDefinition @'
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using System.Text;

public static class ApfNative {
    public delegate bool EnumProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc lpEnumFunc, IntPtr lParam);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMax);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassName(IntPtr hWnd, StringBuilder lpString, int nMax);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int cmd);
    [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr hWnd, int x, int y, int w, int h, bool repaint);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdc, uint flags);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern bool SetWindowText(IntPtr hWnd, string text);
    [DllImport("user32.dll")] public static extern int GetSystemMetrics(int index);

    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }

    public static void Retitle(long hwndValue, string title) {
        SetWindowText(new IntPtr(hwndValue), title);
    }

    public static string ScreenSize() {
        SetProcessDPIAware();
        return GetSystemMetrics(0) + "x" + GetSystemMetrics(1);
    }

    public static string ListWindows() {
        SetProcessDPIAware();
        StringBuilder output = new StringBuilder();
        EnumWindows(delegate (IntPtr hWnd, IntPtr lParam) {
            if (!IsWindowVisible(hWnd)) return true;
            RECT rect;
            if (!GetWindowRect(hWnd, out rect)) return true;
            int width = rect.Right - rect.Left;
            int height = rect.Bottom - rect.Top;
            if (width < 40 || height < 40) return true;
            StringBuilder title = new StringBuilder(512);
            StringBuilder cls = new StringBuilder(256);
            GetWindowText(hWnd, title, title.Capacity);
            GetClassName(hWnd, cls, cls.Capacity);
            uint pid;
            GetWindowThreadProcessId(hWnd, out pid);
            string safeTitle = title.ToString().Replace("\t", " ").Replace("\r", " ").Replace("\n", " ");
            output.Append(pid).Append('\t').Append(hWnd.ToInt64()).Append('\t')
                .Append(rect.Left).Append('\t').Append(rect.Top).Append('\t')
                .Append(width).Append('\t').Append(height).Append('\t')
                .Append(cls.ToString().Replace("\t", " ")).Append('\t').Append(safeTitle).Append('\n');
            return true;
        }, IntPtr.Zero);
        return output.ToString();
    }

    public static void Focus(long hwndValue) {
        IntPtr hwnd = new IntPtr(hwndValue);
        ShowWindow(hwnd, 9);
        RECT rect;
        if (GetWindowRect(hwnd, out rect) && (rect.Left < -2000 || rect.Top < -2000)) {
            int width = Math.Max(900, rect.Right - rect.Left);
            int height = Math.Max(600, rect.Bottom - rect.Top);
            MoveWindow(hwnd, 20, 20, width, height, true);
        }
        SetForegroundWindow(hwnd);
    }

    static bool IsBlank(Bitmap bmp) {
        int width = bmp.Width;
        int height = bmp.Height;
        if (width < 4 || height < 4) return true;
        Color first = bmp.GetPixel(width / 2, height / 2);
        int same = 0;
        int samples = 0;
        for (int y = 4; y < height; y += 24) {
            for (int x = 4; x < width; x += 24) {
                Color pixel = bmp.GetPixel(x, y);
                samples++;
                if (Math.Abs(pixel.R - first.R) < 6 && Math.Abs(pixel.G - first.G) < 6 && Math.Abs(pixel.B - first.B) < 6) same++;
            }
        }
        return samples > 0 && same > (samples * 97 / 100);
    }

    public static string CaptureWindow(long hwndValue, string path) {
        try {
            IntPtr hwnd = new IntPtr(hwndValue);
            Focus(hwndValue);
            RECT rect;
            if (!GetWindowRect(hwnd, out rect)) return "no-rect";
            int width = rect.Right - rect.Left;
            int height = rect.Bottom - rect.Top;
            if (width < 40 || height < 40 || width > 4000 || height > 4000) return "bad-size";
            Bitmap bmp = new Bitmap(width, height);
            try {
                using (Graphics graphics = Graphics.FromImage(bmp)) {
                    graphics.CopyFromScreen(rect.Left, rect.Top, 0, 0, new Size(width, height));
                }
            } catch { }
            if (IsBlank(bmp)) {
                using (Graphics graphics = Graphics.FromImage(bmp)) {
                    IntPtr hdc = graphics.GetHdc();
                    PrintWindow(hwnd, hdc, 2);
                    graphics.ReleaseHdc(hdc);
                }
            }
            bmp.Save(path, ImageFormat.Png);
            bool blank = IsBlank(bmp);
            bmp.Dispose();
            return blank ? "blank" : "ok";
        } catch (Exception ex) {
            return "error:" + ex.Message;
        }
    }

    public static string CaptureScreen(string path) {
        try {
            int width = GetSystemMetrics(0);
            int height = GetSystemMetrics(1);
            if (width < 100 || height < 100) return "bad-screen";
            Bitmap bmp = new Bitmap(width, height);
            using (Graphics graphics = Graphics.FromImage(bmp)) {
                graphics.CopyFromScreen(0, 0, 0, 0, new Size(width, height));
            }
            bmp.Save(path, ImageFormat.Png);
            bool blank = IsBlank(bmp);
            bmp.Dispose();
            return blank ? "blank" : "ok";
        } catch (Exception ex) {
            return "error:" + ex.Message;
        }
    }
}
'@

function Get-WindowRows {
    $rows = @()
    $raw = [ApfNative]::ListWindows()
    foreach ($line in ($raw -split "`n")) {
        if (-not $line.Trim()) { continue }
        $parts = $line.Split("`t")
        if ($parts.Count -lt 8) { continue }
        $rows += [pscustomobject]@{
            pid = [int]$parts[0]
            hwnd = [int64]$parts[1]
            left = [int]$parts[2]
            top = [int]$parts[3]
            width = [int]$parts[4]
            height = [int]$parts[5]
            class = $parts[6]
            title = (@($parts[7..($parts.Count - 1)]) -join " ").Trim()
        }
    }
    return $rows
}

function Save-Shot([string]$Name, [int64]$Hwnd) {
    $path = Join-Path $Artifacts $Name
    $status = "no-window"
    if ($Hwnd -ne 0) { $status = [ApfNative]::CaptureWindow($Hwnd, $path) }
    if ($status -ne "ok") {
        $desktop = [ApfNative]::CaptureScreen($path)
        $status = "window=$status desktop=$desktop"
    }
    Log "shot $Name $status"
}

function Copy-Tree([string]$Source, [string]$Dest) {
    if (Test-Path -LiteralPath $Source) {
        New-Item -ItemType Directory -Force -Path $Dest | Out-Null
        Copy-Item -LiteralPath (Join-Path $Source "*") -Destination $Dest -Recurse -Force -ErrorAction SilentlyContinue
    }
}

$pythonw = Join-Path $InstallRoot "runtime\python\pythonw.exe"
$python = Join-Path $InstallRoot "runtime\python\python.exe"
$launcher = Join-Path $InstallRoot "launch_apf.pyw"
if (-not (Test-Path -LiteralPath $pythonw)) { throw "pythonw missing at $pythonw" }
if (-not (Test-Path -LiteralPath $launcher)) { throw "launcher missing at $launcher" }

$runtimeFacts = Join-Path $Artifacts "runtime-facts.txt"
$factScript = @'
import json, os
from pathlib import Path
from voice_flow import node_component, runtime_env
facts = {
    "installed": runtime_env.is_installed(),
    "install_root": str(runtime_env.install_root()),
    "runtime": str(runtime_env.runtime_root()),
    "bundled_node": node_component.bundled_node_version(),
    "needs_managed_node": node_component.needs_managed_node(),
    "managed_node": str(node_component.managed_node_executable() or ""),
    "video_node": str(node_component.video_node_executable() or ""),
    "ffmpeg": str(runtime_env.ffmpeg_executable() or ""),
    "narova": str(runtime_env.narova_tool_root() or ""),
    "browser": str(runtime_env.browser_executable() or ""),
    "render_browser": str(runtime_env.render_browser_cache() or ""),
}
print(json.dumps(facts, indent=2))
'@
$factFile = Join-Path $env:RUNNER_TEMP "apf-runtime-facts.py"
Set-Content -Path $factFile -Value $factScript -Encoding utf8
Log "runtime facts before launch"
& $python $factFile *> $runtimeFacts
if ($LASTEXITCODE -ne 0) { Log "runtime facts exit $LASTEXITCODE" }
Log (Get-Content -Raw $runtimeFacts)

Log "screen $([ApfNative]::ScreenSize()) label=$Label"
Save-Shot "00-desktop-before.png" 0

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $pythonw
$psi.Arguments = '"' + $launcher + '"'
$psi.WorkingDirectory = $InstallRoot
$psi.UseShellExecute = $false
$null = $psi.EnvironmentVariables.Remove("CI")
$psi.EnvironmentVariables["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = "--remote-debugging-port=9222 --remote-allow-origins=http://127.0.0.1:9222"
$app = [Diagnostics.Process]::Start($psi)
Log "app pid $($app.Id)"

$healthAt = $null
$mainHwnd = [int64]0
$deadline = (Get-Date).AddMinutes(6)
while ((Get-Date) -lt $deadline) {
    foreach ($row in @(Get-WindowRows)) {
        if ($row.class -eq "APFEarlySplash" -and $row.title -eq "AI Productivity Flow") {
            [ApfNative]::Retitle([int64]$row.hwnd, "APF Splash")
            if (-not (Test-Path (Join-Path $Artifacts "01-splash.png"))) {
                Save-Shot "01-splash.png" ([int64]$row.hwnd)
            }
        }
        if ($row.title -eq "AI Productivity Flow" -and $row.class -ne "APFEarlySplash" -and $row.width -ge 700 -and $mainHwnd -eq 0) {
            $mainHwnd = [int64]$row.hwnd
            Log "main window hwnd=$mainHwnd"
            Save-Shot "02-main-window.png" $mainHwnd
        }
    }
    if (-not $healthAt) {
        try {
            $health = Invoke-WebRequest -Uri "http://127.0.0.1:8991/api/runtime" -UseBasicParsing -TimeoutSec 2
            if ($health.StatusCode -eq 200) {
                $healthAt = Get-Date
                Log "api healthy"
            }
        } catch {}
    }
    if ($healthAt -and $mainHwnd -ne 0) { break }
    Start-Sleep -Milliseconds 400
}
if (-not $healthAt) { throw "API did not become healthy" }
Save-Shot "02-main-window.png" $mainHwnd

$probe = Join-Path $PSScriptRoot "render_probe.py"
$probeOut = Join-Path $Artifacts "probe-stdout.txt"
$probeErr = Join-Path $Artifacts "probe-stderr.txt"
$probePsi = New-Object System.Diagnostics.ProcessStartInfo
$probePsi.FileName = $python
$probePsi.Arguments = "`"$probe`" --artifacts `"$Artifacts`" --minutes 35"
$probePsi.WorkingDirectory = $InstallRoot
$probePsi.UseShellExecute = $false
$probePsi.RedirectStandardOutput = $true
$probePsi.RedirectStandardError = $true
$null = $probePsi.EnvironmentVariables.Remove("CI")
$probeProc = [Diagnostics.Process]::Start($probePsi)
$stdoutTask = $probeProc.StandardOutput.ReadToEndAsync()
$stderrTask = $probeProc.StandardError.ReadToEndAsync()
$shotIndex = 3
while (-not $probeProc.WaitForExit(20000)) {
    $name = "{0:D2}-during-render.png" -f $shotIndex
    Save-Shot $name $mainHwnd
    $shotIndex++
}
$probeProc.WaitForExit()
$stdoutTask.Result | Set-Content -Path $probeOut -Encoding utf8
$stderrTask.Result | Set-Content -Path $probeErr -Encoding utf8
Log "probe exit $($probeProc.ExitCode)"
Save-Shot "90-after-probe.png" $mainHwnd

Log "runtime facts after render"
& $python $factFile *> (Join-Path $Artifacts "runtime-facts-after.txt")

$data = Join-Path $env:USERPROFILE ".voice_flow"
try {
Copy-Tree (Join-Path $data "logs") (Join-Path $Artifacts "voice-flow-logs")
$projects = Join-Path $data "v3_projects"
if (Test-Path $projects) {
    Get-ChildItem $projects -Directory | ForEach-Object {
        $dest = Join-Path $Artifacts ("project-" + $_.Name)
        New-Item -ItemType Directory -Force -Path $dest | Out-Null
        foreach ($rel in @("logs", "bridge-output.json", "creative-direction.json", "source.txt")) {
            $src = Join-Path $_.FullName $rel
            if (Test-Path $src) {
                Copy-Item $src (Join-Path $dest (Split-Path $rel -Leaf)) -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
        foreach ($mp4 in @(Get-ChildItem $_.FullName -Recurse -Filter "video.mp4" -ErrorAction SilentlyContinue)) {
            $len = $mp4.Length
            Add-Content (Join-Path $dest "video-size.txt") "$($mp4.FullName) bytes=$len"
            if ($len -gt 0 -and $len -lt 80MB -and -not (Test-Path (Join-Path $dest "video.mp4"))) {
                Copy-Item $mp4.FullName (Join-Path $dest "video.mp4") -Force
            }
        }
    }
}
Get-ChildItem (Join-Path $data "components") -Recurse -Filter "component.json" -ErrorAction SilentlyContinue | ForEach-Object {
    $rel = $_.FullName.Substring($data.Length).TrimStart("\")
    $dest = Join-Path $Artifacts ("components" + $rel)
    New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
    Copy-Item $_.FullName $dest -Force
}
} catch {
    Log "artifact copy failed: $($_.Exception.Message)"
}

try { Stop-Process -Id $app.Id -Force -ErrorAction SilentlyContinue } catch {}
Get-Process python, pythonw, node, ffmpeg -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -like "*AI Productivity Flow*" -or $_.Path -like "*apf-release-build*"
} | ForEach-Object { try { Stop-Process -Id $_.Id -Force } catch {} }

exit $probeProc.ExitCode
