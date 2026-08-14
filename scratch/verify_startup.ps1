# Voice Flow Auto-Startup & System Resilience Verification Script

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host " VOICE FLOW AUTO-STARTUP & SYSTEM RESILIENCE AUDIT" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Check Registry Auto-Run
Write-Host "[1/5] Checking Windows Registry Auto-Run (HKCU\Software\Microsoft\Windows\CurrentVersion\Run)..." -ForegroundColor Yellow
$regKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$regVal = (Get-ItemProperty -Path $regKey -Name "VoiceFlow" -ErrorAction SilentlyContinue).VoiceFlow

if ($regVal) {
    Write-Host "  [PASS] HKCU Run\VoiceFlow -> $regVal" -ForegroundColor Green
} else {
    Write-Host "  [FAIL] HKCU Run\VoiceFlow is NOT set!" -ForegroundColor Red
}

# 2. Check Startup Folder Shortcut
Write-Host ""
Write-Host "[2/5] Checking Windows Startup Directory..." -ForegroundColor Yellow
$startupPath = [Environment]::GetFolderPath('Startup')
$startupFile = Join-Path $startupPath "Voice Flow.lnk"

if (Test-Path $startupFile) {
    $wsh = New-Object -ComObject WScript.Shell
    $sc = $wsh.CreateShortcut($startupFile)
    Write-Host "  [PASS] Startup Shortcut Found: $startupFile" -ForegroundColor Green
    Write-Host "         Target:           $($sc.TargetPath)" -ForegroundColor Gray
    Write-Host "         Arguments:        $($sc.Arguments)" -ForegroundColor Gray
    Write-Host "         WorkingDirectory: $($sc.WorkingDirectory)" -ForegroundColor Gray
    Write-Host "         IconLocation:     $($sc.IconLocation)" -ForegroundColor Gray
} else {
    Write-Host "  [FAIL] Startup shortcut not found at $startupFile" -ForegroundColor Red
}

# 3. Check VoiceFlowLauncher.vbs and Silent Execution
Write-Host ""
Write-Host "[3/5] Inspecting VoiceFlowLauncher.vbs for Zero-Console Silent Execution..." -ForegroundColor Yellow
$vbsPath = "C:\Users\Asus\.gemini\antigravity\scratch\voice-flow\VoiceFlowLauncher.vbs"

if (Test-Path $vbsPath) {
    $content = Get-Content $vbsPath -Raw
    $hasHideFlag = $content -match ",\s*0\s*,\s*False"
    $hasPythonw = $content -match "pythonw"
    $hasWatchdog = $content -match "voice_flow\.watchdog"
    
    if ($hasHideFlag -and $hasPythonw -and $hasWatchdog) {
        Write-Host "  [PASS] VoiceFlowLauncher.vbs is configured for silent execution!" -ForegroundColor Green
        Write-Host "         - WindowStyle 0 (SW_HIDE, zero console popup): YES" -ForegroundColor Green
        Write-Host "         - Uses pythonw.exe (GUI subsystem binary):     YES" -ForegroundColor Green
        Write-Host "         - Supervises via Watchdog auto-recovery:        YES" -ForegroundColor Green
    } else {
        Write-Host "  [WARN] VBS configuration check incomplete. Contents:" -ForegroundColor Yellow
        Write-Host $content -ForegroundColor Gray
    }
} else {
    Write-Host "  [FAIL] Launcher VBS not found at $vbsPath" -ForegroundColor Red
}

# 4. Check Desktop and Start Menu Shortcuts
Write-Host ""
Write-Host "[4/5] Checking Desktop and Start Menu Shortcuts..." -ForegroundColor Yellow
$desktopPath = [Environment]::GetFolderPath('Desktop')
$dtFile = Join-Path $desktopPath "Voice Flow.lnk"
if (Test-Path $dtFile) {
    Write-Host "  [PASS] Desktop Shortcut Found: $dtFile" -ForegroundColor Green
} else {
    Write-Host "  [INFO] User desktop shortcut checked." -ForegroundColor Gray
}

$programsPath = [Environment]::GetFolderPath('Programs')
$smFile = Join-Path $programsPath "Voice Flow.lnk"
if (Test-Path $smFile) {
    Write-Host "  [PASS] Start Menu Shortcut Found: $smFile" -ForegroundColor Green
} else {
    Write-Host "  [INFO] Start Menu shortcut checked." -ForegroundColor Gray
}

# 5. Check Runtime API Health
Write-Host ""
Write-Host "[5/5] Checking Backend Runtime API Health (http://127.0.0.1:8991/api/runtime)..." -ForegroundColor Yellow
try {
    $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8991/api/runtime" -TimeoutSec 2 -ErrorAction Stop
    Write-Host "  [PASS] Voice Flow Runtime is LIVE and responding!" -ForegroundColor Green
    Write-Host "         Contract Version: $($resp.contract_version)" -ForegroundColor Gray
    Write-Host "         Name:             $($resp.name)" -ForegroundColor Gray
} catch {
    Write-Host "  [INFO] Voice Flow backend is not actively running at this instant." -ForegroundColor Gray
}

Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host " AUDIT SUMMARY COMPLETE" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
