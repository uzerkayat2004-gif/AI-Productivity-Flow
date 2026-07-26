"""Spawn the Voice Flow main application as a detached background process.

Called by VoiceFlowLauncher.vbs via pythonw.exe (which has no console).
We use python.exe (not pythonw) for the child process so CTranslate2 and
other C extensions get valid OS file handles. We redirect stdout/stderr
to devnull and use DETACHED_PROCESS so no console window appears.
"""
import os
import subprocess
import sys

root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

# Use python.exe (not pythonw) so C extensions get valid stdout/stderr handles
python_exe = os.path.join(os.path.dirname(sys.executable), "python.exe")
if not os.path.exists(python_exe):
    python_exe = sys.executable

# DETACHED_PROCESS: detach from parent console but DO NOT suppress GUI windows
# (CREATE_NO_WINDOW would suppress ALL windows including PyWebView and Tkinter)
DETACHED_PROCESS = 0x00000008

devnull = open(os.devnull, "w")

subprocess.Popen(
    [python_exe, "-m", "voice_flow.main"],
    cwd=root_dir,
    stdout=devnull,
    stderr=devnull,
    stdin=subprocess.DEVNULL,
    creationflags=DETACHED_PROCESS,
    close_fds=True,
)
