import os
import sys
from pathlib import Path

root = Path(os.getcwd()).resolve()
vbs_path = root / "VoiceFlowLauncher.vbs"

# Get the directory of the current python executable and find python.exe
python_dir = os.path.dirname(sys.executable)
python_exe = os.path.join(python_dir, "python.exe")

if not os.path.exists(python_exe):
    python_exe = "python" # fallback to PATH

vbs_content = f"""Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strPath = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = strPath
WshShell.Run \"\"\"{python_exe}\"\" -m voice_flow.gui.desktop_launcher\", 0, False
"""

with open(vbs_path, "w", encoding="utf-8") as f:
    f.write(vbs_content)

print(f"[OK] VoiceFlowLauncher.vbs generated with explicit python path: {python_exe}")
