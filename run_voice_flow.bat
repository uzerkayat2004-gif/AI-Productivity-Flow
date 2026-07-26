@echo off
title Voice Flow - AI Speech Desktop App
set PYTHONPATH=%~dp0src
cd /d "%~dp0"
echo Starting Voice Flow AI Speech Application...
python -m voice_flow.main
