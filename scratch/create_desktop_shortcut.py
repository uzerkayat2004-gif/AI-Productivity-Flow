import os
import sys
import subprocess
from pathlib import Path

root = Path(os.getcwd()).resolve()
ico = root / "src" / "voice_flow" / "gui" / "assets" / "icon.ico"
vbs = root / "VoiceFlowLauncher.vbs"
import winreg

def get_desktop_path():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders") as key:
            return Path(winreg.QueryValueEx(key, "Desktop")[0])
    except Exception:
        return Path(os.path.expanduser("~/Desktop"))

desktop = get_desktop_path()
start_menu = Path(os.path.expanduser("~/AppData/Roaming/Microsoft/Windows/Start Menu/Programs"))

dt_shortcut = desktop / "Voice Flow.lnk"
sm_shortcut = start_menu / "Voice Flow.lnk"

ps_script = f"""
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut('{dt_shortcut}')
$Shortcut.TargetPath = '{vbs}'
$Shortcut.WorkingDirectory = '{root}'
$Shortcut.IconLocation = '{ico}'
$Shortcut.Description = 'Voice Flow - AI Speech Desktop App'
$Shortcut.Save()

$Shortcut2 = $WshShell.CreateShortcut('{sm_shortcut}')
$Shortcut2.TargetPath = '{vbs}'
$Shortcut2.WorkingDirectory = '{root}'
$Shortcut2.IconLocation = '{ico}'
$Shortcut2.Description = 'Voice Flow - AI Speech Desktop App'
$Shortcut2.Save()
"""

subprocess.run(["powershell", "-Command", ps_script], check=True)
print("[OK] Desktop and Start Menu shortcuts created with orange/white icon.ico!")
