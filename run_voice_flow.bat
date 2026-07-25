@echo off
title Voice Flow - AI Speech System & Desktop Application
echo Starting Voice Flow AI Speech System Engine & Interface...
cd /d "%~dp0"
start "" python -m voice_flow.main
start "" python -m voice_flow.gui.desktop_launcher
echo Voice Flow is running! Hold Middle Mouse Click or Ctrl+Win to dictate anywhere.
