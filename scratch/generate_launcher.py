import os
import sys
from pathlib import Path

root = Path(os.getcwd()).resolve()
vbs_path = root / "VoiceFlowLauncher.vbs"

# Get the directory of the current python executable and find pythonw.exe
python_dir = os.path.dirname(sys.executable)
pythonw_exe = os.path.join(python_dir, "pythonw.exe")

if not os.path.exists(pythonw_exe):
    pythonw_exe = "pythonw" # fallback to PATH

vbs_content = f"""Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strPath = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = strPath
WshShell.Run \"\"\"{pythonw_exe}\"\" -m voice_flow.gui.spawn_backend\", 1, False
"""

with open(vbs_path, "w", encoding="utf-8") as f:
    f.write(vbs_content)

print(f"[OK] VoiceFlowLauncher.vbs generated with explicit pythonw path: {pythonw_exe}")
