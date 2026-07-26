@echo off
title Voice Flow - AI Speech System ^& Desktop Application
set PYTHONPATH=%~dp0src
cd /d "%~dp0"
echo Starting Voice Flow AI Speech System Engine ^& Desktop UI...
start "Voice Flow Engine" python -m voice_flow.main
start "Voice Flow Desktop UI" python -m voice_flow.gui.desktop_launcher
echo Voice Flow is running! Hold Middle Mouse Click or Ctrl+Win to dictate anywhere.
