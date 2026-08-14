@echo off
setlocal
set PYTHONPATH=%~dp0src
cd /d "%~dp0"

if "%1"=="--console" (
    echo Starting Voice Flow in Interactive Console Mode...
    if exist "%~dp0.venv\Scripts\python.exe" (
        "%~dp0.venv\Scripts\python.exe" -m voice_flow.main --show-console
    ) else if exist "C:\Python314\python.exe" (
        "C:\Python314\python.exe" -m voice_flow.main --show-console
    ) else (
        python -m voice_flow.main --show-console
    )
    goto :eof
)

if "%1"=="--watchdog-console" (
    echo Starting Voice Flow Watchdog Supervisor in Console Mode...
    if exist "%~dp0.venv\Scripts\python.exe" (
        "%~dp0.venv\Scripts\python.exe" -m voice_flow.watchdog --show-console
    ) else if exist "C:\Python314\python.exe" (
        "C:\Python314\python.exe" -m voice_flow.watchdog --show-console
    ) else (
        python -m voice_flow.watchdog --show-console
    )
    goto :eof
)

if "%1"=="--status" (
    if exist "%~dp0.venv\Scripts\python.exe" (
        "%~dp0.venv\Scripts\python.exe" -m voice_flow.watchdog --status
    ) else if exist "C:\Python314\python.exe" (
        "C:\Python314\python.exe" -m voice_flow.watchdog --status
    ) else (
        python -m voice_flow.watchdog --status
    )
    goto :eof
)

if "%1"=="--stop" (
    if exist "%~dp0.venv\Scripts\python.exe" (
        "%~dp0.venv\Scripts\python.exe" -m voice_flow.watchdog --stop
    ) else if exist "C:\Python314\python.exe" (
        "C:\Python314\python.exe" -m voice_flow.watchdog --stop
    ) else (
        python -m voice_flow.watchdog --stop
    )
    goto :eof
)

:: Default: Launch silently via VoiceFlowLauncher.vbs with zero console popup
if exist "%~dp0VoiceFlowLauncher.vbs" (
    wscript.exe "%~dp0VoiceFlowLauncher.vbs"
) else (
    if exist "%~dp0.venv\Scripts\pythonw.exe" (
        start "" "%~dp0.venv\Scripts\pythonw.exe" -m voice_flow.watchdog
    ) else if exist "C:\Python314\pythonw.exe" (
        start "" "C:\Python314\pythonw.exe" -m voice_flow.watchdog
    ) else (
        start "" pythonw -m voice_flow.watchdog
    )
)
