"""End-to-end test: simulates exactly what happens when user double-clicks the Desktop shortcut.
Chain: pythonw.exe -m voice_flow.gui.spawn_backend → python.exe -m voice_flow.main
"""
import os
import sys
import subprocess
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")

print(f"[E2E] Simulating double-click: {pythonw} -m voice_flow.gui.spawn_backend")
print(f"[E2E] Working directory: {ROOT}")

# This is exactly what VoiceFlowLauncher.vbs does
proc = subprocess.Popen(
    [pythonw, "-m", "voice_flow.gui.spawn_backend"],
    cwd=ROOT,
)
proc.wait()
print(f"[E2E] spawn_backend exited with code: {proc.returncode}")

# Wait for main.py to start up
time.sleep(3)

# Check if python.exe is running (main.py)
result = subprocess.run(
    ["tasklist", "/fi", "imagename eq python.exe"],
    capture_output=True, text=True
)
print(f"[E2E] Running python processes:\n{result.stdout}")

# Check if the API server is listening
import urllib.request
try:
    resp = urllib.request.urlopen("http://127.0.0.1:8991/api/history", timeout=3)
    print(f"[E2E] API server responding: HTTP {resp.status}")
except Exception as e:
    print(f"[E2E] API server NOT responding: {e}")

print("\n[E2E] If you see 'VOICE FLOW READY' in a python.exe process and API responding,")
print("[E2E] then the desktop shortcut chain is working correctly.")
print("[E2E] Check your screen for the Floating Bar and Desktop Window.")
