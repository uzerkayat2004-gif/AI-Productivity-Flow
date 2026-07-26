@echo off
title Voice Flow - Desktop Application Setup
echo ========================================================
echo   VOICE FLOW — STANDALONE DESKTOP INSTALLER
echo ========================================================
echo.

cd /d "%~dp0"

echo [1/3] Verifying Python environment and dependencies...
python -c "import scipy, faster_whisper, sounddevice; print('  [OK] Core dependencies verified!')"
if %ERRORLEVEL% NEQ 0 (
    echo   [ERROR] Missing dependencies. Installing...
    pip install -e .
)

echo.
echo [2/3] Generating Desktop Shortcut & Start Menu Icons...
python scratch/create_desktop_shortcut.py

echo.
echo [3/3] Configuring Silent Windows Boot Startup Registry...
python -c "import winreg, sys, os; key_path = r'Software\Microsoft\Windows\CurrentVersion\Run'; vbs = os.path.abspath('VoiceFlowLauncher.vbs'); cmd = f'wscript.exe \"{vbs}\"'; key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS); winreg.SetValueEx(key, 'VoiceFlow', 0, winreg.REG_SZ, cmd); winreg.CloseKey(key); print('  [OK] Windows Auto-Boot Registry configured!')"

echo.
echo ========================================================
echo   INSTALLATION COMPLETE!
echo   Voice Flow is now installed as a Standalone Desktop App.
echo   - Desktop Shortcut: Voice Flow (Orange and White Icon)
echo   - Windows Auto-Start: Enabled (Silent Background)
echo ========================================================
echo.
