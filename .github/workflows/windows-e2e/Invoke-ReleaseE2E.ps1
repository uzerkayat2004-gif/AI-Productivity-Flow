param(
    [Parameter(Mandatory = $true)][string]$Tag,
    [Parameter(Mandatory = $true)][string]$Artifacts
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"
if ($Tag -notmatch '^v\d+\.\d+\.\d+$') { throw "Refusing tag '$Tag'" }

New-Item -ItemType Directory -Force -Path $Artifacts | Out-Null
$script:LogFile = Join-Path $Artifacts "e2e.log"
$script:ShotNotes = New-Object System.Collections.Generic.List[object]
$script:Steps = New-Object System.Collections.Generic.List[object]
$script:Bugs = New-Object System.Collections.Generic.List[object]
$script:Timings = @{}
$script:CdpWs = $null
$script:CdpSeq = 0
$script:MainHwnd = [int64]0
$script:HungFails = 0
$script:HungSamples = 0
$script:HungStarted = $null
$script:InstallRoot = Join-Path $env:LOCALAPPDATA "Programs\AI Productivity Flow"
$script:Python = Join-Path $script:InstallRoot "runtime\python\python.exe"
$script:Pythonw = Join-Path $script:InstallRoot "runtime\python\pythonw.exe"
$script:Launcher = Join-Path $script:InstallRoot "launch_apf.pyw"

function Log([string]$Message) {
    $line = "{0} {1}" -f (Get-Date -Format "HH:mm:ss"), $Message
    Add-Content -Path $script:LogFile -Value $line -Encoding UTF8
    Write-Host $line
}

function Add-JsonString([System.Text.StringBuilder]$Sb, [string]$Text) {
    [void]$Sb.Append('"')
    if ($Text) {
        foreach ($ch in $Text.ToCharArray()) {
            $code = [int]$ch
            if ($ch -eq '"') { [void]$Sb.Append('\"') }
            elseif ($ch -eq '\') { [void]$Sb.Append('\\') }
            elseif ($ch -eq "`n") { [void]$Sb.Append('\n') }
            elseif ($ch -eq "`r") { [void]$Sb.Append('\r') }
            elseif ($ch -eq "`t") { [void]$Sb.Append('\t') }
            elseif ($code -lt 32) {
                [void]$Sb.Append('\u')
                [void]$Sb.Append($code.ToString("x4"))
            } else { [void]$Sb.Append([string]$ch) }
        }
    }
    [void]$Sb.Append('"')
}

function Add-Json([System.Text.StringBuilder]$Sb, $Value, [int]$Depth) {
    if ($null -eq $Value -or $Depth -lt 0) { [void]$Sb.Append('null'); return }
    if ($Value -is [bool]) {
        if ($Value) { [void]$Sb.Append('true') } else { [void]$Sb.Append('false') }
        return
    }
    if ($Value -is [string]) { Add-JsonString $Sb $Value; return }
    $typeName = $Value.GetType().FullName
    if ($typeName -eq 'System.Byte' -or $typeName -eq 'System.Int16' -or $typeName -eq 'System.Int32' -or $typeName -eq 'System.Int64' -or $typeName -eq 'System.UInt32' -or $typeName -eq 'System.UInt64' -or $typeName -eq 'System.Single' -or $typeName -eq 'System.Double' -or $typeName -eq 'System.Decimal') {
        [void]$Sb.Append($Value.ToString([System.Globalization.CultureInfo]::InvariantCulture))
        return
    }
    if ($Value -is [System.Collections.IDictionary]) {
        [void]$Sb.Append('{')
        $first = $true
        foreach ($key in $Value.Keys) {
            if (-not $first) { [void]$Sb.Append(',') }
            $first = $false
            Add-JsonString $Sb ([string]$key)
            [void]$Sb.Append(':')
            Add-Json $Sb $Value[$key] ($Depth - 1)
        }
        [void]$Sb.Append('}')
        return
    }
    if ($Value -is [System.Collections.IEnumerable]) {
        [void]$Sb.Append('[')
        $first = $true
        foreach ($item in $Value) {
            if (-not $first) { [void]$Sb.Append(',') }
            $first = $false
            Add-Json $Sb $item ($Depth - 1)
        }
        [void]$Sb.Append(']')
        return
    }
    Add-JsonString $Sb ([string]$Value)
}

function Save-State {
    try {
        $doc = @{
            tag = [string]$Tag
            steps = $script:Steps.ToArray()
            timings = $script:Timings
            screenshots = $script:ShotNotes.ToArray()
            bugs = $script:Bugs.ToArray()
        }
        $sb = New-Object System.Text.StringBuilder
        Add-Json $sb $doc 8
        $utf8 = New-Object System.Text.UTF8Encoding $false
        [System.IO.File]::WriteAllText((Join-Path $Artifacts "results.json"), $sb.ToString(), $utf8)
    } catch {
        Log ("results.json write failed: " + $_.Exception.ToString())
    }
}

function Add-Step([string]$Id, [bool]$Pass, [string]$Detail, [string]$Kind) {
    $script:Steps.Add(@{ id = $Id; pass = $Pass; detail = $Detail; kind = $Kind })
    Log ("STEP {0} {1} {2}" -f $(if ($Pass) { "PASS" } else { "FAIL" }), $Id, $Detail)
    if (-not $Pass -and $Kind -eq "app") {
        $script:Bugs.Add(@{ step = $Id; detail = $Detail })
    }
    Save-State
}

function Add-Shot([string]$Name, [string]$Note) {
    $script:ShotNotes.Add(@{ file = $Name; note = $Note })
    Log ("SHOT {0} {1}" -f $Name, $Note)
    Save-State
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
    [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr hWnd, EnumProc lpEnumFunc, IntPtr lParam);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMax);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassName(IntPtr hWnd, StringBuilder lpString, int nMax);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int cmd);
    [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr hWnd, int x, int y, int w, int h, bool repaint);
    [DllImport("user32.dll")] public static extern bool IsHungAppWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdc, uint flags);
    [DllImport("user32.dll")] public static extern IntPtr SendMessageTimeout(IntPtr hWnd, uint msg, UIntPtr wParam, IntPtr lParam, uint flags, uint timeout, out UIntPtr result);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll", CharSet = CharSet.Auto)] public static extern bool EnumDisplaySettings(string device, int mode, ref DEVMODE devMode);
    [DllImport("user32.dll", CharSet = CharSet.Auto)] public static extern int ChangeDisplaySettings(ref DEVMODE devMode, int flags);
    [DllImport("user32.dll")] public static extern int GetSystemMetrics(int index);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern bool SetWindowText(IntPtr hWnd, string text);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern IntPtr FindWindow(string className, string windowName);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint flags, uint dx, uint dy, uint data, System.UIntPtr extra);
    [DllImport("user32.dll")] public static extern void keybd_event(byte key, byte scan, uint flags, System.UIntPtr extra);

    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Auto)]
    public struct DEVMODE {
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string dmDeviceName;
        public short dmSpecVersion;
        public short dmDriverVersion;
        public short dmSize;
        public short dmDriverExtra;
        public int dmFields;
        public int dmPositionX;
        public int dmPositionY;
        public int dmDisplayOrientation;
        public int dmDisplayFixedOutput;
        public short dmColor;
        public short dmDuplex;
        public short dmYResolution;
        public short dmTTOption;
        public short dmCollate;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string dmFormName;
        public short dmLogPixels;
        public int dmBitsPerPel;
        public int dmPelsWidth;
        public int dmPelsHeight;
        public int dmDisplayFlags;
        public int dmDisplayFrequency;
        public int dmICMMethod;
        public int dmICMIntent;
        public int dmMediaType;
        public int dmDitherType;
        public int dmReserved1;
        public int dmReserved2;
        public int dmPanningWidth;
        public int dmPanningHeight;
    }

    public static long FindByClass(string className) {
        return FindWindow(className, null).ToInt64();
    }

    public static void Retitle(long hwndValue, string title) {
        SetWindowText(new IntPtr(hwndValue), title);
    }

    public static void ClickScreen(int x, int y) {
        SetCursorPos(x, y);
        mouse_event(0x0002, 0, 0, 0, System.UIntPtr.Zero);
        mouse_event(0x0004, 0, 0, 0, System.UIntPtr.Zero);
    }

    public static void PressEnter(long hwndValue) {
        IntPtr hwnd = new IntPtr(hwndValue);
        ShowWindow(hwnd, 9);
        SetForegroundWindow(hwnd);
        keybd_event(0x0D, 0, 0, System.UIntPtr.Zero);
        keybd_event(0x0D, 0, 2, System.UIntPtr.Zero);
    }

    public static string WindowTitle(long hwndValue) {
        StringBuilder title = new StringBuilder(512);
        GetWindowText(new IntPtr(hwndValue), title, title.Capacity);
        return title.ToString();
    }

    public static string ScreenSize() {
        SetProcessDPIAware();
        return GetSystemMetrics(0) + "x" + GetSystemMetrics(1);
    }

    public static string TryResolution(int width, int height) {
        try {
            DEVMODE mode = new DEVMODE();
            mode.dmSize = (short)Marshal.SizeOf(typeof(DEVMODE));
            if (!EnumDisplaySettings(null, -1, ref mode)) return "enum-failed";
            mode.dmPelsWidth = width;
            mode.dmPelsHeight = height;
            mode.dmFields = 0x80000 | 0x100000;
            int code = ChangeDisplaySettings(ref mode, 0);
            return "code=" + code + " now=" + ScreenSize();
        } catch (Exception ex) {
            return ex.Message;
        }
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
            string safeClass = cls.ToString().Replace("\t", " ");
            output.Append(pid).Append('\t').Append(hWnd.ToInt64()).Append('\t')
                .Append(rect.Left).Append('\t').Append(rect.Top).Append('\t')
                .Append(width).Append('\t').Append(height).Append('\t')
                .Append(safeClass).Append('\t').Append(safeTitle).Append('\n');
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

    public static string Responds(long hwndValue) {
        IntPtr hwnd = new IntPtr(hwndValue);
        if (IsHungAppWindow(hwnd)) return "hung";
        UIntPtr result;
        IntPtr code = SendMessageTimeout(hwnd, 0, UIntPtr.Zero, IntPtr.Zero, 0x0002, 1000, out result);
        return code == IntPtr.Zero ? "timeout" : "ok";
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
            } catch {
                /* PrintWindow below covers a failed screen copy. */
            }
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

if (-not ([System.Management.Automation.PSTypeName]"ApfNative").Type) {
    throw "Native helper did not compile"
}

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

function Stop-ApfProcesses {
    $procs = Get-CimInstance Win32_Process | Where-Object {
        ($_.ExecutablePath -and $_.ExecutablePath -like "*\AI Productivity Flow\*") -or
        ($_.CommandLine -and ($_.CommandLine -like "*launch_apf.pyw*" -or $_.CommandLine -like "*\voice_flow*"))
    }
    foreach ($proc in @($procs)) {
        try { Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue } catch {}
    }
    Start-Sleep -Seconds 2
}

function Copy-Tree([string]$Source, [string]$Dest) {
    if (Test-Path $Source) {
        New-Item -ItemType Directory -Force -Path $Dest | Out-Null
        Copy-Item -Path (Join-Path $Source "*") -Destination $Dest -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Reset-UserData {
    $data = Join-Path $env:USERPROFILE ".voice_flow"
    if (Test-Path $data) {
        Copy-Tree (Join-Path $data "logs") (Join-Path $Artifacts "autolaunch-logs")
        Remove-Item -LiteralPath $data -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Measure-FolderBytes([string]$Path) {
    if (-not (Test-Path $Path)) { return 0 }
    $sum = (Get-ChildItem -LiteralPath $Path -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
    if (-not $sum) { return 0 }
    return [int64]$sum
}

function Get-UiElements([int]$ProcessId) {
    $found = @()
    try {
        Add-Type -AssemblyName UIAutomationClient | Out-Null
        Add-Type -AssemblyName UIAutomationTypes | Out-Null
        $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty, $ProcessId)
        $windows = [System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children, $cond)
        foreach ($window in $windows) {
            $found += $window
            $desc = $window.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
            foreach ($el in $desc) { $found += $el }
        }
    } catch {
        Log "ui automation failed: $($_.Exception.Message)"
    }
    return @($found)
}

function Invoke-UiClick([int]$ProcessId, [string]$ExactName) {
    foreach ($el in @(Get-UiElements $ProcessId)) {
        $name = ""
        try { $name = [string]$el.Current.Name } catch { continue }
        if ($name -ne $ExactName) { continue }
        try {
            $invoke = $el.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
            $invoke.Invoke()
            return $true
        } catch {}
        try {
            $rect = $el.Current.BoundingRectangle
            if ($rect.Width -gt 4 -and $rect.Height -gt 4) {
                [ApfNative]::ClickScreen([int]($rect.X + ($rect.Width / 2)), [int]($rect.Y + ($rect.Height / 2)))
                return $true
            }
        } catch {}
    }
    return $false
}

function Get-UiNames([int]$ProcessId) {
    $names = New-Object System.Collections.Generic.List[string]
    try {
        Add-Type -AssemblyName UIAutomationClient | Out-Null
        Add-Type -AssemblyName UIAutomationTypes | Out-Null
        $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty, $ProcessId)
        $windows = [System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children, $cond)
        foreach ($window in $windows) {
            if ($window.Current.Name) { $names.Add([string]$window.Current.Name) }
            $desc = $window.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
            foreach ($el in $desc) {
                $name = [string]$el.Current.Name
                if ($name) { $names.Add($name) }
            }
        }
    } catch {
        $names.Add("automation-error: $($_.Exception.Message)")
    }
    return @($names)
}

function Invoke-Cdp([string]$Method, $Params, [int]$TimeoutMs) {
    if (-not $script:CdpWs) { throw "CDP is not connected" }
    $ws = New-Object System.Net.WebSockets.ClientWebSocket
    $wait = $ws.ConnectAsync([Uri]$script:CdpWs, [Threading.CancellationToken]::None)
    if (-not $wait.Wait(10000)) { throw "CDP connect timeout" }
    if ($wait.IsFaulted) { throw $wait.Exception.InnerException }
    $script:CdpSeq++
    $id = $script:CdpSeq
    $body = @{ id = $id; method = $Method; params = $Params } | ConvertTo-Json -Compress -Depth 8
    $bytes = [Text.Encoding]::UTF8.GetBytes($body)
    $segment = [System.ArraySegment[byte]]::new($bytes)
    $send = $ws.SendAsync($segment, [System.Net.WebSockets.WebSocketMessageType]::Text, $true, [Threading.CancellationToken]::None)
    if (-not $send.Wait(10000)) { throw "CDP send timeout" }
    $stream = New-Object System.IO.MemoryStream
    $buffer = New-Object byte[] 262144
    $deadline = [DateTime]::UtcNow.AddMilliseconds($TimeoutMs)
    while ($true) {
        $stream.SetLength(0)
        do {
            if ([DateTime]::UtcNow -gt $deadline) { throw "CDP recv timeout for $Method" }
            $chunk = [System.ArraySegment[byte]]::new($buffer)
            $recv = $ws.ReceiveAsync($chunk, [Threading.CancellationToken]::None)
            if (-not $recv.Wait(8000)) { throw "CDP socket stalled during $Method" }
            $result = $recv.Result
            $stream.Write($buffer, 0, $result.Count)
            $ended = $result.EndOfMessage
        } while (-not $ended)
        $text = [Text.Encoding]::UTF8.GetString($stream.ToArray())
        $message = $text | ConvertFrom-Json
        if ($message.id -eq $id) {
            $ws.Dispose()
            return $message
        }
    }
}

function Invoke-Page([string]$Expression) {
    $js = @"
(async () => {
  try {
    const value = await ($Expression);
    return JSON.stringify({ok:true, value:value});
  } catch (e) {
    return JSON.stringify({ok:false, error:String(e && (e.stack || e.message) || e)});
  }
})()
"@
    $response = Invoke-Cdp "Runtime.evaluate" @{ expression = $js; awaitPromise = $true; returnByValue = $true } 40000
    if ($response.result.exceptionDetails) {
        throw ("CDP exception " + ($response.result.exceptionDetails | ConvertTo-Json -Compress -Depth 4))
    }
    $raw = [string]$response.result.result.value
    if (-not $raw) { throw "empty page result for $Expression" }
    $parsed = $raw | ConvertFrom-Json
    if (-not $parsed.ok) { throw $parsed.error }
    return $parsed.value
}

function Connect-Cdp {
    $deadline = (Get-Date).AddSeconds(75)
    while ((Get-Date) -lt $deadline) {
        try {
            $list = @(Invoke-RestMethod -Uri "http://127.0.0.1:9222/json" -TimeoutSec 3)
            $page = $list | Where-Object { $_.type -eq "page" -and $_.webSocketDebuggerUrl -and ($_.url -match "8991|index.html") } | Select-Object -First 1
            if (-not $page) {
                $page = $list | Where-Object { $_.type -eq "page" -and $_.webSocketDebuggerUrl } | Select-Object -First 1
            }
            if ($page) {
                $script:CdpWs = [string]$page.webSocketDebuggerUrl
                $helperPath = Join-Path $PSScriptRoot "page_helpers.js"
                $helper = [IO.File]::ReadAllText($helperPath)
                $loaded = Invoke-Cdp "Runtime.evaluate" @{ expression = $helper; returnByValue = $true } 20000
                if ($loaded.result.exceptionDetails) { throw "helper inject failed" }
                Log "CDP connected $($page.url)"
                return $true
            }
        } catch {
            Log "CDP wait: $($_.Exception.Message)"
        }
        Start-Sleep -Milliseconds 700
    }
    return $false
}

function Save-CdpShot([string]$Path) {
    try {
        $null = Invoke-Cdp "Page.enable" @{} 10000
    } catch {}
    $shot = Invoke-Cdp "Page.captureScreenshot" @{ format = "png" } 30000
    $data = [string]$shot.result.data
    if (-not $data) { return "no-data" }
    [IO.File]::WriteAllBytes($Path, [Convert]::FromBase64String($data))
    return "cdp"
}

function Save-WindowShot([string]$Name, [int64]$Hwnd, [string]$Note) {
    $path = Join-Path $Artifacts $Name
    $status = "no-window"
    if ($Hwnd -ne 0) { $status = [ApfNative]::CaptureWindow($Hwnd, $path) }
    if ($status -ne "ok" -and $script:CdpWs -and $Name -notlike "*installer*" -and $Name -notlike "*splash*" -and $Name -notlike "*browser*") {
        try { $status = Save-CdpShot $path } catch { $status = "cdp-error: $($_.Exception.Message)" }
    }
    if ($status -ne "ok" -and $status -ne "cdp") {
        $desktopStatus = [ApfNative]::CaptureScreen($path)
        $status = "window=$status desktop=$desktopStatus"
    }
    Add-Shot $Name ("{0} capture={1}" -f $Note, $status)
    return $status
}

function Sample-Hung {
    if ($script:MainHwnd -eq 0) { return }
    if (-not $script:HungStarted) { $script:HungStarted = Get-Date }
    $state = [ApfNative]::Responds($script:MainHwnd)
    $script:HungSamples++
    if ($state -ne "ok") { $script:HungFails++ }
}

function Wait-HungWindow {
    $deadline = $script:HungStarted.AddSeconds(90)
    while ((Get-Date) -lt $deadline) {
        Sample-Hung
        Start-Sleep -Seconds 3
    }
}

function Start-InstalledApp {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $script:Pythonw
    $psi.Arguments = '"' + $script:Launcher + '"'
    $psi.WorkingDirectory = $script:InstallRoot
    $psi.UseShellExecute = $false
    $null = $psi.EnvironmentVariables.Remove("CI")
    $psi.EnvironmentVariables["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = "--remote-debugging-port=9222 --remote-allow-origins=http://127.0.0.1:9222"
    return [Diagnostics.Process]::Start($psi)
}

function Get-MainWindows {
    return @(Get-WindowRows | Where-Object {
        $_.title -eq "AI Productivity Flow" -and $_.class -ne "APFEarlySplash" -and $_.width -ge 700 -and $_.left -gt -2000
    })
}

try {
    Log "screen $([ApfNative]::ScreenSize())"
    $resolution = [ApfNative]::TryResolution(1920, 1080)
    Log "resolution $resolution"
    $desktopStatus = [ApfNative]::CaptureScreen((Join-Path $Artifacts "00-session-desktop.png"))
    Add-Shot "00-session-desktop.png" "Runner desktop before install. capture=$desktopStatus"

    $work = Join-Path $env:RUNNER_TEMP "apf-e2e"
    New-Item -ItemType Directory -Force -Path $work | Out-Null
    $installer = Join-Path $work "AI-Productivity-Flow-Setup-x64.exe"
    $checksum = Join-Path $work "AI-Productivity-Flow-Setup-x64.exe.sha256"
    $base = "https://github.com/uzerkayat2004-gif/AI-Productivity-Flow/releases/download/$Tag"
    $curl = Join-Path $env:SystemRoot "System32\curl.exe"
    Log "downloading $base"
    & $curl -L --retry 5 --retry-delay 2 --fail -o $checksum "$base/AI-Productivity-Flow-Setup-x64.exe.sha256"
    $shaExit = $LASTEXITCODE
    & $curl -L --retry 5 --retry-delay 2 --fail -o $installer "$base/AI-Productivity-Flow-Setup-x64.exe"
    $exeExit = $LASTEXITCODE
    if ($shaExit -ne 0 -or $exeExit -ne 0 -or -not (Test-Path $installer)) {
        Add-Step "1-download-sha256" $false "download failed sha=$shaExit exe=$exeExit" "harness"
        throw "download failed"
    }
    $shaText = Get-Content -Raw -Path $checksum
    $expected = ""
    if ($shaText -match "([A-Fa-f0-9]{64})") { $expected = $Matches[1].ToLower() }
    $actual = (Get-FileHash -Algorithm SHA256 -Path $installer).Hash.ToLower()
    $shaOk = ($expected -eq $actual -and $expected.Length -eq 64)
    Add-Step "1-download-sha256" $shaOk ("expected={0} actual={1} bytes={2}" -f $expected, $actual, (Get-Item $installer).Length) $(if ($shaOk) { "ok" } else { "app" })
    if (-not $shaOk) { throw "checksum mismatch" }

    $wizardTrace = Join-Path $Artifacts "wizard-trace.txt"
    $wizardLog = Join-Path $Artifacts "wizard-install.log"
    $wizard = Start-Process -FilePath $installer -ArgumentList ('/LOG=' + $wizardLog) -PassThru
    Log "wizard pid $($wizard.Id)"
    $wizardDeadline = (Get-Date).AddMinutes(8)
    $sawInstalling = $false
    $shotInstalling = $false
    $shotFinish = $false
    $installingAt = $null
    $pages = New-Object System.Collections.Generic.List[string]
    $titles = New-Object System.Collections.Generic.List[string]
    $wizardHwnd = [int64]0
    $lastBlob = ""
    $lastCensus = ""
    $shotReady = $false
    $installAttempts = 0
    $nextInstallTry = Get-Date
    while ((Get-Date) -lt $wizardDeadline -and -not $wizard.HasExited) {
        $rows = @(Get-WindowRows)
        $censusLines = New-Object System.Collections.Generic.List[string]
        foreach ($row in $rows) { $censusLines.Add(("{0}`t{1}`t{2}x{3}`t{4}`t{5}" -f $row.pid, $row.hwnd, $row.width, $row.height, $row.class, $row.title)) }
        $census = [string]::Join("`n", $censusLines.ToArray())
        if ($census -ne $lastCensus) {
            $lastCensus = $census
            Add-Content -Path $wizardTrace -Value ("{0} WINDOWS`n{1}" -f (Get-Date -Format "HH:mm:ss"), $census) -Encoding UTF8
        }
        $setupHwnd = [ApfNative]::FindByClass("TWizardForm")
        $top = $null
        if ($setupHwnd -ne 0) {
            $top = $rows | Where-Object { $_.hwnd -eq $setupHwnd } | Select-Object -First 1
            if (-not $top) {
                $top = [pscustomobject]@{ pid = $wizard.Id; hwnd = $setupHwnd; left = 0; top = 0; width = 640; height = 480; class = "TWizardForm"; title = [ApfNative]::WindowTitle($setupHwnd) }
            }
        }
        if (-not $top) {
            $owned = @($rows | Where-Object { $_.pid -eq $wizard.Id -and $_.width -ge 300 })
            if ($owned.Count -gt 0) { $top = $owned | Sort-Object { $_.width * $_.height } -Descending | Select-Object -First 1 }
        }
        if (-not $top) {
            $titled = @($rows | Where-Object { $_.title -like "Setup -*" })
            if ($titled.Count -gt 0) { $top = $titled | Select-Object -First 1 }
        }
        if ($top) {
            $wizardHwnd = $top.hwnd
            if ($titles -notcontains $top.title) { $titles.Add($top.title) }
            $names = Get-UiNames ([int]$top.pid)
            $blob = (($names + @($top.title)) -join " | ")
            if ($blob -ne $lastBlob) {
                $lastBlob = $blob
                Add-Content -Path $wizardTrace -Value ("{0} TITLE={1} TEXT={2}" -f (Get-Date -Format "HH:mm:ss"), $top.title, $blob) -Encoding UTF8
            }
            $lower = $blob.ToLower()
            $page = "unknown"
            foreach ($forbidden in @("select destination", "select start menu", "license agreement", "ready to install", "select additional tasks", "welcome to the")) {
                if ($lower.Contains($forbidden)) { $page = "forbidden:$forbidden" }
            }
            if ($lower.Contains("if you exit now") -or $lower.Contains("setup is not complete")) {
                $page = "exit-confirm"
            } elseif ($page -eq "unknown" -and ($lower.Contains("ai productivity flow is installed") -or ($lower.Contains("version 1.0") -and $lower.Contains("finish")))) {
                $page = "finish"
            } elseif ($page -eq "unknown" -and $lower.Contains("installing ai productivity flow")) {
                $page = "installing"
            }
            if ($pages -notcontains $page) { $pages.Add($page); Log "wizard page $page" }
            if ($page -like "forbidden:*" -and -not $shotReady) {
                Save-WindowShot "01-installer-ready.png" $wizardHwnd ("Unexpected wizard page. title='$($top.title)'") | Out-Null
                $shotReady = $true
            }
            if ($page -eq "exit-confirm") {
                $dismissed = Invoke-UiClick ([int]$top.pid) "No"
                Log "wizard exit prompt dismissed=$dismissed"
                Start-Sleep -Seconds 1
                continue
            }
            if ($page -like "forbidden:*" -and $installAttempts -lt 4 -and (Get-Date) -ge $nextInstallTry) {
                $installAttempts++
                $nextInstallTry = (Get-Date).AddSeconds(4)
                $clickedInstall = Invoke-UiClick ([int]$top.pid) "Install"
                Log "wizard Install attempt=$installAttempts click=$clickedInstall"
            }
            if ($page -eq "installing" -and -not $sawInstalling) {
                $sawInstalling = $true
                $installingAt = Get-Date
            }
            if ($page -eq "installing" -and -not $shotInstalling -and $installingAt -and ((Get-Date) - $installingAt).TotalSeconds -ge 5) {
                Save-WindowShot "01-installer-installing.png" $wizardHwnd ("Installing page. title='$($top.title)'") | Out-Null
                $shotInstalling = $true
            }
            if ($page -eq "finish" -and -not $shotFinish) {
                if (-not $shotInstalling) {
                    Save-WindowShot "01-installer-installing.png" $wizardHwnd "Installing page was not held; this frame was the first stable wizard image." | Out-Null
                    $shotInstalling = $true
                }
                Start-Sleep -Seconds 1
                Save-WindowShot "02-installer-finish.png" $wizardHwnd ("Finish page. title='$($top.title)'") | Out-Null
                $shotFinish = $true
                try {
                    $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty, ([int]$top.pid))
                    $roots = [System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children, $cond)
                    foreach ($root in $roots) {
                        $desc = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
                        foreach ($el in $desc) {
                            $nm = [string]$el.Current.Name
                            if ($nm -eq "Finish") {
                                $invoke = $el.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
                                $invoke.Invoke()
                            }
                        }
                    }
                } catch {
                    Log "finish click failed: $($_.Exception.Message)"
                }
                break
            }
        }
        Start-Sleep -Milliseconds 800
    }
    if (-not $wizard.HasExited) {
        $null = $wizard.WaitForExit(120000)
    }
    if (-not $wizard.HasExited) {
        try { Stop-Process -Id $wizard.Id -Force -ErrorAction SilentlyContinue } catch {}
        Log "wizard was still open; stopped it"
    }
    $forbiddenPages = @($pages | Where-Object { $_ -like "forbidden:*" })
    $titleOk = @($titles | Where-Object { $_ -like "*AI Productivity Flow 1.0*" }).Count -gt 0
    $pageOk = $shotInstalling -and $shotFinish -and $forbiddenPages.Count -eq 0 -and $titleOk -and @($pages | Where-Object { $_ -eq "installing" }).Count -gt 0 -and @($pages | Where-Object { $_ -eq "finish" }).Count -gt 0
    Add-Step "2-wizard-pages" $pageOk ("pages=$($pages -join ',') titles=$($titles -join ' || ') exit=$($wizard.ExitCode)") $(if ($pageOk) { "ok" } else { "app" })

    Stop-ApfProcesses
    $unins = Join-Path $script:InstallRoot "unins000.exe"
    if (Test-Path $unins) {
        $un = Start-Process -FilePath $unins -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -PassThru
        $null = $un.WaitForExit(300000)
        Log "uninstall exit $($un.ExitCode)"
    }
    Start-Sleep -Seconds 2

    $silentLog = Join-Path $Artifacts "silent-install.log"
    $silent = Start-Process -FilePath $installer -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", ('/LOG="' + $silentLog + '"') -PassThru
    $silentWatch = [Diagnostics.Stopwatch]::StartNew()
    while (-not $silent.HasExited -and $silentWatch.Elapsed.TotalMinutes -lt 40) { Start-Sleep -Seconds 2 }
    $silentWatch.Stop()
    $script:Timings.silent_install_seconds = [math]::Round($silentWatch.Elapsed.TotalSeconds, 1)
    $silentOk = $silent.HasExited -and $silent.ExitCode -eq 0 -and (Test-Path $script:Pythonw)
    $bytes = Measure-FolderBytes $script:InstallRoot
    $script:Timings.install_folder_bytes = $bytes
    $script:Timings.install_folder_mb = [math]::Round($bytes / 1MB, 1)
    Add-Step "2-silent-install" $silentOk ("seconds=$($script:Timings.silent_install_seconds) exit=$($silent.ExitCode) folder_mb=$($script:Timings.install_folder_mb)") $(if ($silentOk) { "ok" } else { "app" })
    Stop-ApfProcesses
    foreach ($proc in @(Get-Process msedgewebview2 -ErrorAction SilentlyContinue)) {
        try { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } catch {}
    }
    Reset-UserData

    $shell = New-Object -ComObject WScript.Shell
    $desktop = Join-Path ([Environment]::GetFolderPath("Desktop")) "AI Productivity Flow.lnk"
    $programsRoot = [Environment]::GetFolderPath("Programs")
    $startLinks = @()
    if ($programsRoot -and (Test-Path -LiteralPath $programsRoot)) {
        $startLinks = @(Get-ChildItem -LiteralPath $programsRoot -Recurse -Filter "AI Productivity Flow.lnk" -ErrorAction SilentlyContinue)
    }
    $shortcutNotes = New-Object System.Collections.Generic.List[string]
    $shortcutOk = $true
    $links = New-Object System.Collections.Generic.List[string]
    $links.Add($desktop)
    foreach ($link in $startLinks) { $links.Add($link.FullName) }
    if ($startLinks.Count -eq 0) {
        $shortcutOk = $false
        $shortcutNotes.Add("missing Start Menu shortcut under $programsRoot")
    }
    foreach ($lnk in $links) {
        if (-not (Test-Path -LiteralPath $lnk)) {
            $shortcutOk = $false
            $shortcutNotes.Add("missing $lnk")
            continue
        }
        $sc = $shell.CreateShortcut($lnk)
        $targetOk = $sc.TargetPath -like "*\pythonw.exe"
        $argOk = $sc.Arguments -like "*launch_apf.pyw*"
        if (-not $targetOk -or -not $argOk) { $shortcutOk = $false }
        $shortcutNotes.Add(("{0} target={1} args={2}" -f $lnk, $sc.TargetPath, $sc.Arguments))
    }
    Add-Step "3-shortcuts" $shortcutOk ([string]::Join(" || ", $shortcutNotes.ToArray())) $(if ($shortcutOk) { "ok" } else { "app" })
    $defaultFolder = @($startLinks | Where-Object { $_.Directory.Name -eq "(Default)" })
    $folderOk = ($startLinks.Count -gt 0 -and $defaultFolder.Count -eq 0)
    $folderDetail = $(if ($folderOk) { "Start Menu shortcut is outside a (Default) folder" } else { "Start Menu shortcut landed in '(Default)' instead of 'AI Productivity Flow': " + $(if ($defaultFolder.Count -gt 0) { $defaultFolder[0].FullName } else { $programsRoot }) })
    Add-Step "3-start-menu-folder" $folderOk $folderDetail $(if ($folderOk) { "ok" } else { "app" })

    if (-not (Test-Path $script:Pythonw)) { throw "installed pythonw missing" }
    $launchWatch = [Diagnostics.Stopwatch]::StartNew()
    $app = Start-InstalledApp
    Log "app pid $($app.Id)"
    $splashHwnd = [int64]0
    $splashAt = $null
    $mainAt = $null
    $healthAt = $null
    $launchDeadline = (Get-Date).AddMinutes(4)
    while ((Get-Date) -lt $launchDeadline) {
        $rows = @(Get-WindowRows)
        foreach ($row in $rows) {
            if ($row.class -eq "APFEarlySplash" -and $row.title -eq "AI Productivity Flow") {
                [ApfNative]::Retitle([int64]$row.hwnd, "APF Splash")
                $row.title = "APF Splash"
            }
        }
        $splash = $rows | Where-Object { $_.class -eq "APFEarlySplash" } | Select-Object -First 1
        if ($splash -and $splashHwnd -eq 0) {
            $splashHwnd = $splash.hwnd
            $splashAt = $launchWatch.Elapsed.TotalSeconds
            Save-WindowShot "03-splash.png" $splashHwnd ("Splash class=$($splash.class) $($splash.width)x$($splash.height) at $([math]::Round($splashAt, 2))s") | Out-Null
        }
        $main = Get-MainWindows | Select-Object -First 1
        if ($main -and -not $mainAt) {
            $script:MainHwnd = $main.hwnd
            $script:MainPid = [int]$main.pid
            $mainAt = $launchWatch.Elapsed.TotalSeconds
            $script:HungStarted = Get-Date
            Log "main window at $mainAt hwnd $($main.hwnd)"
        }
        if (-not $healthAt) {
            try {
                $health = Invoke-WebRequest -Uri "http://127.0.0.1:8991/api/runtime" -UseBasicParsing -TimeoutSec 2
                if ($health.StatusCode -eq 200) { $healthAt = $launchWatch.Elapsed.TotalSeconds }
            } catch {}
        }
        Sample-Hung
        if ($splashAt -and $mainAt -and $healthAt) { break }
        Start-Sleep -Milliseconds 200
    }
    $script:Timings.splash_seconds = $(if ($splashAt) { [math]::Round($splashAt, 2) } else { $null })
    $script:Timings.main_window_seconds = $(if ($mainAt) { [math]::Round($mainAt, 2) } else { $null })
    $script:Timings.backend_health_seconds = $(if ($healthAt) { [math]::Round($healthAt, 2) } else { $null })
    $launchOk = ($null -ne $splashAt -and $null -ne $mainAt -and $null -ne $healthAt)
    Add-Step "4-launch" $launchOk ("splash_s=$($script:Timings.splash_seconds) main_s=$($script:Timings.main_window_seconds) health_s=$($script:Timings.backend_health_seconds)") $(if ($launchOk) { "ok" } else { "app" })

    $beforeSecond = @(Get-MainWindows).Count
    $second = Start-InstalledApp
    $secondDeadline = (Get-Date).AddSeconds(20)
    while ((Get-Date) -lt $secondDeadline -and -not $second.HasExited) {
        Sample-Hung
        Start-Sleep -Milliseconds 400
    }
    Start-Sleep -Seconds 2
    $afterSecond = @(Get-MainWindows).Count
    $singleOk = ($beforeSecond -eq 1 -and $afterSecond -eq 1)
    if (-not $second.HasExited) {
        try { Stop-Process -Id $second.Id -Force -ErrorAction SilentlyContinue } catch {}
    }
    Add-Step "4-single-window" $singleOk ("before=$beforeSecond after=$afterSecond second_exited=$($second.HasExited) second_exit=$($second.ExitCode)") $(if ($singleOk) { "ok" } else { "app" })

    $cdpOk = Connect-Cdp
    if (-not $cdpOk) {
        $browserLines = New-Object System.Collections.Generic.List[string]
        foreach ($proc in @(Get-CimInstance Win32_Process | Where-Object { $_.Name -match "msedgewebview2|msedge" })) {
            $browserLines.Add(("{0} {1}" -f $proc.ProcessId, $proc.CommandLine))
        }
        Log ("browser processes: " + [string]::Join(" || ", $browserLines.ToArray()))
        $uiPid = $(if ($script:MainPid) { [int]$script:MainPid } else { [int]$app.Id })
        $uiNames = @(Get-UiNames $uiPid)
        $uiPath = Join-Path $Artifacts "main-window-ui.txt"
        [System.IO.File]::WriteAllText($uiPath, ([string]::Join("`r`n", @($uiNames))))
        Log ("main window ui names=" + $uiNames.Count)
        Start-Sleep -Seconds 6
        Save-WindowShot "04-onboarding-scene-1.png" $script:MainHwnd ("Scene 1 from the live window. UI sample: " + ([string]::Join(" | ", @($uiNames | Select-Object -First 12)))) | Out-Null
        $null = Invoke-UiClick $uiPid "Auto"
        $sceneShots = @(
            @{ file = "05-onboarding-scene-2.png"; button = "Next" },
            @{ file = "06-onboarding-scene-3.png"; button = "Next" },
            @{ file = "07-onboarding-scene-4.png"; button = "Next" },
            @{ file = "08-onboarding-scene-5.png"; button = "Next" }
        )
        foreach ($scene in $sceneShots) {
            $advanced = Invoke-UiClick $uiPid $scene.button
            if (-not $advanced) { $advanced = Invoke-UiClick $uiPid "Get Started" }
            Start-Sleep -Seconds 5
            Save-WindowShot $scene.file $script:MainHwnd ("Advanced=$advanced via UIA") | Out-Null
        }
        $pageShots = @(
            @{ name = "Audio Flow"; file = "21-page-audio-flow-dark.png" },
            @{ name = "Video Flow"; file = "22-page-video-flow-dark.png" },
            @{ name = "Home"; file = "23-page-voice-home-dark.png" },
            @{ name = "Insights"; file = "24-page-insights-dark.png" },
            @{ name = "Dictionary"; file = "25-page-dictionary-dark.png" },
            @{ name = "Style"; file = "26-page-style-dark.png" },
            @{ name = "Providers"; file = "27-page-providers-dark.png" },
            @{ name = "Settings"; file = "30-settings-general-dark.png" }
        )
        foreach ($pageShot in $pageShots) {
            $opened = Invoke-UiClick $uiPid $pageShot.name
            Start-Sleep -Seconds 2
            Save-WindowShot $pageShot.file $script:MainHwnd ("UIA click '$($pageShot.name)' opened=$opened") | Out-Null
        }
        $tourDriven = @($uiNames | Where-Object { $_ -match "Skip Tour|Next|Get Started" }).Count -gt 0
        Add-Step "ui-tour" $tourDriven ("CDP port 9222 was closed. UIA names=$($uiNames.Count) tour_controls=$tourDriven") $(if ($tourDriven) { "ok" } else { "harness" })
    } else {
        $tourProblems = @()
        foreach ($index in 0..4) {
            Sample-Hung
            try {
                $state = Invoke-Page "window.__e2e.prepScene($index)"
                $visual = Invoke-Page "window.__e2e.visual()"
                $file = "{0:D2}-onboarding-scene-{1}.png" -f ($index + 4), ($index + 1)
                $bar = "skip=$($state.hasSkip) auto=$($state.hasAuto) back=$($state.hasBack) next=$($state.hasNext) buttons=$($state.buttons -join ' / ')"
                $note = "Scene $($index + 1) caption='$($state.caption)'. $bar. $($visual.summary)"
                Save-WindowShot $file $script:MainHwnd $note | Out-Null
                if (-not $state.ok -or -not $state.hasSkip -or -not $state.hasAuto -or -not $state.hasBack -or -not $state.hasNext -or -not $state.caption) {
                    $tourProblems += "scene $($index + 1) incomplete ($bar)"
                }
            } catch {
                $tourProblems += "scene $($index + 1) error: $($_.Exception.Message)"
            }
        }
        $guidePlan = @(
            @{ kind = "audio"; step = 1; file = "09-guide-audio-flow-1.png" },
            @{ kind = "audio"; step = 2; file = "10-guide-audio-flow-2.png" },
            @{ kind = "audio"; step = 3; file = "11-guide-audio-flow-3.png" },
            @{ kind = "audio"; step = 4; file = "12-guide-audio-flow-4.png" },
            @{ kind = "video"; step = 1; file = "13-guide-video-flow-1.png" },
            @{ kind = "video"; step = 2; file = "14-guide-video-flow-2.png" },
            @{ kind = "video"; step = 3; file = "15-guide-video-flow-3.png" },
            @{ kind = "video"; step = 4; file = "16-guide-video-flow-4.png" },
            @{ kind = "voice"; step = 1; file = "17-guide-voice-flow-1.png" },
            @{ kind = "voice"; step = 2; file = "18-guide-voice-flow-2.png" },
            @{ kind = "voice"; step = 3; file = "19-guide-voice-flow-3.png" },
            @{ kind = "voice"; step = 4; file = "20-guide-voice-flow-4.png" }
        )
        foreach ($item in $guidePlan) {
            Sample-Hung
            try {
                $state = Invoke-Page ("window.__e2e.prepGuide('{0}', {1})" -f $item.kind, $item.step)
                $visual = Invoke-Page "window.__e2e.visual()"
                $note = ("{0} guide step {1} caption='{2}'. {3}" -f $item.kind, $item.step, $state.caption, $visual.summary)
                Save-WindowShot $item.file $script:MainHwnd $note | Out-Null
                if (-not $state.ok) { $tourProblems += "$($item.file) guide not visible" }
            } catch {
                $tourProblems += "$($item.file) error: $($_.Exception.Message)"
            }
        }
        $pages = @(
            @{ id = "audioflow"; dark = "21-page-audio-flow-dark.png"; light = "34-page-audio-flow-light.png" },
            @{ id = "videoflow"; dark = "22-page-video-flow-dark.png"; light = "35-page-video-flow-light.png" },
            @{ id = "home"; dark = "23-page-voice-home-dark.png"; light = "36-page-voice-home-light.png" },
            @{ id = "insights"; dark = "24-page-insights-dark.png"; light = "37-page-insights-light.png" },
            @{ id = "dictionary"; dark = "25-page-dictionary-dark.png"; light = "38-page-dictionary-light.png" },
            @{ id = "style"; dark = "26-page-style-dark.png"; light = "39-page-style-light.png" },
            @{ id = "providers"; dark = "27-page-providers-dark.png"; light = "40-page-providers-light.png" }
        )
        foreach ($theme in @("dark", "light")) {
            foreach ($page in $pages) {
                Sample-Hung
                $file = $(if ($theme -eq "dark") { $page.dark } else { $page.light })
                try {
                    $state = Invoke-Page ("window.__e2e.prepPage('{0}', '{1}')" -f $page.id, $theme)
                    $visual = Invoke-Page "window.__e2e.visual()"
                    $themeNote = $(if ($state.theme -eq $theme) { "theme=$($state.theme)" } else { "theme requested $theme but page reports $($state.theme)" })
                    Save-WindowShot $file $script:MainHwnd ("{0} {1}. {2}. {3}" -f $page.id, $theme, $themeNote, $visual.summary) | Out-Null
                    if ($state.theme -ne $theme) { $tourProblems += "$file theme mismatch" }
                } catch {
                    $tourProblems += "$file error: $($_.Exception.Message)"
                }
            }
            try {
                $notice = Invoke-Page ("window.__e2e.prepNotice('{0}')" -f $theme)
                $visual = Invoke-Page "window.__e2e.visual()"
                $noticeFile = $(if ($theme -eq "dark") { "28-notice-model-dark.png" } else { "41-notice-model-light.png" })
                $natural = $(if ($notice.natural) { "banner was already visible" } else { "banner was hidden until the test unhid it" })
                Save-WindowShot $noticeFile $script:MainHwnd ("Model notice ($theme). $natural. text='$($notice.text)'. $($visual.summary)") | Out-Null
                if (-not $notice.natural) { $tourProblems += "$noticeFile model notice was not shown on its own" }
            } catch {
                $tourProblems += "notice $theme error: $($_.Exception.Message)"
            }
            try {
                $card = Invoke-Page ("window.__e2e.prepNotebookCard('{0}')" -f $theme)
                $visual = Invoke-Page "window.__e2e.visual()"
                $cardFile = $(if ($theme -eq "dark") { "29-card-notebooklm-signin-dark.png" } else { "42-card-notebooklm-signin-light.png" })
                Save-WindowShot $cardFile $script:MainHwnd ("NotebookLM card ($theme) text='$($card.text)'. $($visual.summary)") | Out-Null
                if (-not $card.ok -or $card.text -notmatch "Sign in") { $tourProblems += "$cardFile sign-in card missing" }
            } catch {
                $tourProblems += "notebook card $theme error: $($_.Exception.Message)"
            }
            foreach ($tab in @(
                @{ id = "general"; about = $false; dark = "30-settings-general-dark.png"; light = "43-settings-general-light.png" },
                @{ id = "system"; about = $false; dark = "31-settings-system-dark.png"; light = "44-settings-system-light.png" },
                @{ id = "system"; about = $true; dark = "32-settings-about-updates-privacy-dark.png"; light = "45-settings-about-updates-privacy-light.png" },
                @{ id = "account"; about = $false; dark = "33-settings-account-dark.png"; light = "46-settings-account-light.png" }
            )) {
                Sample-Hung
                $file = $(if ($theme -eq "dark") { $tab.dark } else { $tab.light })
                $aboutJs = $(if ($tab.about) { "true" } else { "false" })
                try {
                    $state = Invoke-Page ("window.__e2e.prepSettings('{0}', '{1}', {2})" -f $tab.id, $theme, $aboutJs)
                    $visual = Invoke-Page "window.__e2e.visual()"
                    $versionNote = ""
                    if ($tab.about) {
                        $versionNote = " version='$($state.version)' build='$($state.build)'."
                        if ($state.version -notmatch "1\.0" -or $state.build -notmatch "1\.0\.4") {
                            $tourProblems += "$file version text '$($state.version)' '$($state.build)'"
                        }
                    }
                    Save-WindowShot $file $script:MainHwnd ("Settings $($tab.id) about=$($tab.about) $theme.$versionNote $($visual.summary)") | Out-Null
                    if (-not $state.ok) { $tourProblems += "$file settings modal hidden" }
                } catch {
                    $tourProblems += "$file error: $($_.Exception.Message)"
                }
            }
        }
        $tourOk = $tourProblems.Count -eq 0
        Add-Step "ui-screenshots" $tourOk ($(if ($tourOk) { "tour, guides, pages, settings captured" } else { $tourProblems -join " || " })) $(if ($tourOk) { "ok" } else { "app" })
    }

    if ($script:HungStarted) { Wait-HungWindow }
    $hungElapsed = 0
    if ($script:HungStarted) { $hungElapsed = ((Get-Date) - $script:HungStarted).TotalSeconds }
    $hungOk = ($script:HungSamples -gt 0 -and $script:HungFails -eq 0 -and $hungElapsed -ge 90)
    $script:Timings.hung_samples = $script:HungSamples
    $script:Timings.hung_failures = $script:HungFails
    Add-Step "4-not-hung-90s" $hungOk ("samples=$($script:HungSamples) failures=$($script:HungFails) elapsed_s=$([math]::Round($hungElapsed, 1))") $(if ($hungOk) { "ok" } else { "app" })

    $knownBrowsers = @(Get-Process chrome, msedge, chromium -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
    $knownWindows = @(Get-WindowRows | Select-Object -ExpandProperty hwnd)
    $probePy = Join-Path $PSScriptRoot "notebooklm_probe.py"
    $probeStatus = Join-Path $Artifacts "notebooklm-status.json"
    $probePsi = New-Object System.Diagnostics.ProcessStartInfo
    $probePsi.FileName = $script:Pythonw
    $probePsi.Arguments = '"' + $probePy + '" "' + $probeStatus + '"'
    $probePsi.WorkingDirectory = $script:InstallRoot
    $probePsi.UseShellExecute = $false
    $probe = [Diagnostics.Process]::Start($probePsi)
    $browserHwnd = [int64]0
    $browserNote = ""
    $nlmDeadline = (Get-Date).AddSeconds(30)
    $instantExit = $false
    while ((Get-Date) -lt $nlmDeadline) {
        if (Test-Path $probeStatus) {
            try {
                $status = Get-Content -Raw -Path $probeStatus | ConvertFrom-Json
                if ($status.stage -eq "spawned" -and $null -ne $status.exit_code -and [double]$status.elapsed -lt 2) {
                    $instantExit = $true
                    $browserNote = "child exited in $($status.elapsed)s code=$($status.exit_code) argv=$($status.argv -join ' ')"
                    break
                }
            } catch {}
        }
        $fresh = @(Get-WindowRows | Where-Object {
            $knownWindows -notcontains $_.hwnd -and $_.width -ge 400 -and $_.height -ge 300 -and (
                $_.class -like "*Chrome*" -or $_.title -match "Google|Sign in|Edge|Chrome|NotebookLM|accounts")
        })
        if ($fresh.Count -gt 0) {
            $browserHwnd = $fresh[0].hwnd
            $browserNote = "window '$($fresh[0].title)' class=$($fresh[0].class)"
            Start-Sleep -Seconds 2
            Save-WindowShot "47-notebooklm-browser.png" $browserHwnd $browserNote | Out-Null
            break
        }
        Start-Sleep -Milliseconds 500
    }
    $statusText = ""
    if (Test-Path $probeStatus) { $statusText = Get-Content -Raw -Path $probeStatus }
    $nlmOk = (-not $instantExit -and $browserHwnd -ne 0)
    Add-Step "5-notebooklm-login-spawn" $nlmOk ("$browserNote status=$statusText") $(if ($nlmOk) { "ok" } else { "app" })
    try { Stop-Process -Id $probe.Id -Force -ErrorAction SilentlyContinue } catch {}
    $newBrowsers = @(Get-Process chrome, msedge, chromium -ErrorAction SilentlyContinue | Where-Object { $knownBrowsers -notcontains $_.Id })
    foreach ($proc in $newBrowsers) { try { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } catch {} }
    Stop-ApfProcesses

    $wav = Join-Path $Artifacts "speech-fixture.wav"
    $speechOk = $false
    try {
        Add-Type -AssemblyName System.Speech
        $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
        $synth.Rate = -2
        $synth.SetOutputToWaveFile($wav)
        $synth.Speak("Please ship the notes today before noon.")
        $synth.Dispose()
        $speechOk = (Test-Path $wav) -and ((Get-Item $wav).Length -gt 1000)
    } catch {
        Log "SAPI failed: $($_.Exception.Message)"
    }
    $transcribeResult = Join-Path $Artifacts "transcribe-result.json"
    $transcribeOk = $false
    $transcribeDetail = "speech fixture was not created"
    if ($speechOk) {
        $probe = Join-Path $PSScriptRoot "transcribe_probe.py"
        $watch = [Diagnostics.Stopwatch]::StartNew()
        & $script:Python $probe $wav $transcribeResult
        $watch.Stop()
        $script:Timings.transcribe_wall_seconds = [math]::Round($watch.Elapsed.TotalSeconds, 1)
        if (Test-Path $transcribeResult) {
            $tr = Get-Content -Raw -Path $transcribeResult | ConvertFrom-Json
            $transcribeOk = [bool]$tr.pass
            $script:Timings.whisper_load_seconds = $tr.load_seconds
            $script:Timings.whisper_decode_seconds = $tr.decode_seconds
            $transcribeDetail = "text='$($tr.text)' repeated=$($tr.repeated_sentence) load_s=$($tr.load_seconds) decode_s=$($tr.decode_seconds) error=$($tr.error)"
        } else {
            $transcribeDetail = "transcribe probe produced no result"
        }
    }
    $transcribeKind = $(if ($transcribeOk) { "ok" } elseif (-not $speechOk) { "harness" } else { "app" })
    Add-Step "6-whisper-no-hallucination" $transcribeOk $transcribeDetail $transcribeKind

    $modelUrl = ""
    try {
        $modelUrl = (& $script:Python -c "from voice_flow.downloadable_models import get_model_spec; print(get_model_spec('nvidia/nemotron-speech-streaming-en-0.6b')['download_url'])").Trim()
    } catch {
        $modelUrl = "https://huggingface.co/nvidia/nemotron-speech-streaming-en-0.6b/resolve/main/nemotron-speech-streaming-en-0.6b.q8_0.gguf"
    }
    $headFile = Join-Path $Artifacts "nemotron-head.txt"
    & $curl -sS -I -L --max-redirs 5 -A "AI-Productivity-Flow-e2e" -D $headFile -o NUL $modelUrl
    $headText = ""
    if (Test-Path $headFile) { $headText = Get-Content -Raw -Path $headFile }
    $lastStatus = 0
    $length = 0
    foreach ($line in ($headText -split "`n")) {
        if ($line -match "^HTTP/\S+\s+(\d+)") { $lastStatus = [int]$Matches[1] }
        if ($line -match "(?i)^content-length:\s+(\d+)") { $length = [int64]$Matches[1] }
    }
    $headOk = ($lastStatus -eq 200 -and $length -gt 50000000)
    $script:Timings.nemotron_head_status = $lastStatus
    $script:Timings.nemotron_content_length = $length
    Add-Step "6-nemotron-head" $headOk ("url=$modelUrl status=$lastStatus content_length=$length") $(if ($headOk) { "ok" } else { "app" })

    $assetsFile = Join-Path $Artifacts "release-assets.json"
    $token = $env:GITHUB_TOKEN
    $headers = @{ "User-Agent" = "AI-Productivity-Flow-e2e"; "Accept" = "application/vnd.github+json" }
    if ($token) { $headers["Authorization"] = "Bearer $token" }
    try {
        $release = Invoke-RestMethod -Headers $headers -Uri "https://api.github.com/repos/uzerkayat2004-gif/AI-Productivity-Flow/releases/tags/$Tag" -TimeoutSec 30
        $assetJson = @($release.assets) | ConvertTo-Json -Depth 6
        $utf8 = New-Object System.Text.UTF8Encoding $false
        [System.IO.File]::WriteAllText($assetsFile, $assetJson, $utf8)
    } catch {
        Log "release asset list failed: $($_.Exception.Message)"
    }
    $updateResult = Join-Path $Artifacts "update-result.json"
    $updateProbe = Join-Path $PSScriptRoot "update_probe.py"
    & $script:Python $updateProbe $Tag.TrimStart("v") $updateResult $assetsFile
    $updateOk = $false
    $updateDetail = "update probe produced no result"
    if (Test-Path $updateResult) {
        $ur = Get-Content -Raw -Path $updateResult | ConvertFrom-Json
        $updateOk = [bool]$ur.pass
        $checkJson = ""
        try { $checkJson = ($ur.check | ConvertTo-Json -Compress -Depth 4) } catch { $checkJson = "unserializable" }
        $updateDetail = "up_to_date=$($ur.up_to_date) dry_run=$($ur.dry_run_ok) plan=$($ur.plan.kind) asset=$($ur.plan.asset_name) reason=$($ur.plan.reason) error=$($ur.error) check=$checkJson"
    }
    Add-Step "7-updater" $updateOk $updateDetail $(if ($updateOk) { "ok" } else { "app" })

    $logDir = Join-Path $env:USERPROFILE ".voice_flow\logs"
    Copy-Tree $logDir (Join-Path $Artifacts "voice-flow-logs")
    $launchLog = Join-Path $logDir "launch.log"
    $debugLogs = @(Get-ChildItem -Path $logDir -Filter "*debug*.log" -ErrorAction SilentlyContinue)
    $traceback = @()
    $logFiles = @()
    if (Test-Path $logDir) { $logFiles = @(Get-ChildItem -Path $logDir -Filter "*.log" -ErrorAction SilentlyContinue) }
    foreach ($file in $logFiles) {
        $text = Get-Content -Raw -Path $file.FullName -ErrorAction SilentlyContinue
        if ($text -and $text -match "Traceback \(most recent call last\)") { $traceback += $file.Name }
    }
    $logsOk = (Test-Path $launchLog) -and $debugLogs.Count -gt 0 -and $traceback.Count -eq 0
    $debugNames = @($debugLogs | ForEach-Object { $_.Name })
    $tracebackNames = @($traceback | ForEach-Object { $_ })
    Add-Step "4-logs" $logsOk ("launch_log=$(Test-Path $launchLog) debug=$($debugNames -join ',') tracebacks=$($tracebackNames -join ',')") $(if ($logsOk) { "ok" } else { "app" })

    $pngCount = @(Get-ChildItem -Path $Artifacts -Filter "*.png" -ErrorAction SilentlyContinue).Count
    Add-Step "8-artifacts" ($pngCount -ge 10) "png_count=$pngCount dir=$Artifacts" $(if ($pngCount -ge 10) { "ok" } else { "harness" })
} catch {
    Add-Step "harness" $false $_.Exception.Message "harness"
    Log $_.ScriptStackTrace
} finally {
    Save-State
    Copy-Tree (Join-Path $env:USERPROFILE ".voice_flow\logs") (Join-Path $Artifacts "voice-flow-logs")
    try { Stop-ApfProcesses } catch {}
}

$failed = @($script:Steps | Where-Object { -not $_.pass })
Log ("done pass={0} fail={1}" -f (@($script:Steps | Where-Object { $_.pass }).Count), $failed.Count)
if ($failed.Count -gt 0) { exit 1 }
exit 0
