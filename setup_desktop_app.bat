@echo off
title Voice Flow - Desktop Application Setup
echo ========================================================
echo   VOICE FLOW — STANDALONE DESKTOP INSTALLER
echo ========================================================
echo.

cd /d "%~dp0"
set PYTHONPATH=%~dp0src

echo [1/3] Verifying Python environment and dependencies...
python -c "import scipy, faster_whisper, sounddevice; print('  [OK] Core dependencies verified!')"
if %ERRORLEVEL% NEQ 0 (
    echo   [ERROR] Missing dependencies. Installing...
    pip install -e .
)

echo.
echo [2/3] Generating Silent Background Launcher and Watchdog Supervisor...
python scratch/generate_launcher.py

echo.
echo [3/3] Registering Dual-Layer Windows Auto-Startup ^& Shortcuts...
python -m voice_flow.installer --install

echo.
echo ========================================================
echo   INSTALLATION COMPLETE!
echo   Voice Flow is now configured with resilient auto-startup:
echo   - Registry: HKCU\Software\Microsoft\Windows\CurrentVersion\Run\VoiceFlow
echo   - Startup Folder: %%APPDATA%%\Microsoft\Windows\Start Menu\Programs\Startup\Voice Flow.lnk
echo   - Auto-Recovery: Background Watchdog Supervisor
echo   - Zero Console Popup: Enabled (Silent pythonw execution)
echo ========================================================
echo.
