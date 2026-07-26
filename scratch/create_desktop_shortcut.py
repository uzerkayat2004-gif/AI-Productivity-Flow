import os
import sys
import subprocess
from pathlib import Path

root = Path(os.getcwd()).resolve()
ico = root / "src" / "voice_flow" / "gui" / "assets" / "icon.ico"
vbs = root / "VoiceFlowLauncher.vbs"
import winreg

def get_desktop_paths():
    paths = set()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders") as key:
            paths.add(Path(winreg.QueryValueEx(key, "Desktop")[0]))
    except Exception:
        pass
    paths.add(Path(os.path.expanduser("~/Desktop")))
    paths.add(Path(os.path.expanduser("~/OneDrive/Desktop")))
    return [p for p in paths if p.parent.exists()]

desktop_paths = get_desktop_paths()
start_menu = Path(os.path.expanduser("~/AppData/Roaming/Microsoft/Windows/Start Menu/Programs"))
sm_shortcut = start_menu / "Voice Flow.lnk"
dt_commands = []
for dp in desktop_paths:
    sc = dp / "Voice Flow.lnk"
    dt_commands.append(f"""
$Shortcut = $WshShell.CreateShortcut('{sc}')
$Shortcut.TargetPath = '{vbs}'
$Shortcut.WorkingDirectory = '{root}'
$Shortcut.IconLocation = '{ico}'
$Shortcut.Description = 'Voice Flow - AI Speech Desktop App'
$Shortcut.Save()
""")

dt_script_str = "\n".join(dt_commands)

ps_script = f"""
$WshShell = New-Object -ComObject WScript.Shell
{dt_script_str}
$Shortcut2 = $WshShell.CreateShortcut('{sm_shortcut}')
$Shortcut2.TargetPath = '{vbs}'
$Shortcut2.WorkingDirectory = '{root}'
$Shortcut2.IconLocation = '{ico}'
$Shortcut2.Description = 'Voice Flow - AI Speech Desktop App'
$Shortcut2.Save()
"""

subprocess.run(["powershell", "-Command", ps_script], check=True)
print("[OK] Desktop and Start Menu shortcuts created with orange/white icon.ico!")
