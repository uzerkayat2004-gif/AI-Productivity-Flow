@echo off
title Voice Flow - AI Speech Desktop App
echo Starting Voice Flow Desktop Application...
cd /d "%~dp0"
python -m voice_flow.gui.desktop_launcher
pause
