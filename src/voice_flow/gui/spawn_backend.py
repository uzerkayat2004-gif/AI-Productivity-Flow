import os
import subprocess
import sys

root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
python_exe = os.path.join(os.path.dirname(sys.executable), "python.exe")
if not os.path.exists(python_exe):
    python_exe = sys.executable

CREATE_NO_WINDOW = 0x08000000

subprocess.Popen(
    [python_exe, "-m", "voice_flow.main"],
    cwd=root_dir,
    creationflags=CREATE_NO_WINDOW,
)
