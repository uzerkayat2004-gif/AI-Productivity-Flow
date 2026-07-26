"""Diagnostic script to test the exact desktop launch chain.
Run this with: python scratch/test_launch_chain.py
"""
import os
import sys
import subprocess

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

print(f"[DIAG] Python: {sys.executable}")
print(f"[DIAG] Root: {ROOT}")

# Check 1: Does pythonw.exe exist?
pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
print(f"[DIAG] pythonw.exe exists: {os.path.exists(pythonw)} at {pythonw}")

# Check 2: Can we import voice_flow.main without crashing?
print("[DIAG] Testing import voice_flow.main...")
result = subprocess.run(
    [sys.executable, "-c", "import voice_flow.main; print('IMPORT OK')"],
    cwd=ROOT, capture_output=True, text=True, timeout=15
)
print(f"[DIAG] import stdout: {result.stdout.strip()}")
print(f"[DIAG] import stderr: {result.stderr.strip()[:500]}")
print(f"[DIAG] import returncode: {result.returncode}")

# Check 3: Can pythonw run spawn_backend.py?
print("[DIAG] Testing pythonw spawn_backend...")
result2 = subprocess.run(
    [pythonw, "-c", "import sys, os; f=open('scratch/pythonw_test.txt','w'); f.write(f'stdout={sys.stdout}\\nstderr={sys.stderr}\\nexe={sys.executable}\\n'); f.close()"],
    cwd=ROOT, timeout=5
)
if os.path.exists(os.path.join(ROOT, "scratch", "pythonw_test.txt")):
    with open(os.path.join(ROOT, "scratch", "pythonw_test.txt")) as f:
        print(f"[DIAG] pythonw output: {f.read().strip()}")
else:
    print("[DIAG] pythonw FAILED - no output file created")

# Check 4: Can pythonw actually run spawn_backend module?
print("[DIAG] Testing pythonw -m voice_flow.gui.spawn_backend...")
log_file = os.path.join(ROOT, "scratch", "spawn_test.txt")
result3 = subprocess.run(
    [pythonw, "-c", f"""
import sys, os, traceback
try:
    with open(r'{log_file}', 'w') as log:
        log.write('spawn_backend starting\\n')
        root_dir = r'{ROOT}'
        python_exe = os.path.join(os.path.dirname(sys.executable), 'python.exe')
        if not os.path.exists(python_exe):
            log.write(f'python.exe NOT FOUND at {{python_exe}}\\n')
        else:
            log.write(f'python.exe found at {{python_exe}}\\n')
        
        import subprocess as sp
        CREATE_NO_WINDOW = 0x08000000
        proc = sp.Popen(
            [python_exe, '-m', 'voice_flow.main'],
            cwd=root_dir,
            creationflags=CREATE_NO_WINDOW,
        )
        log.write(f'Started PID {{proc.pid}}\\n')
except Exception as e:
    with open(r'{log_file}', 'w') as log:
        log.write(f'ERROR: {{e}}\\n')
        traceback.print_exc(file=log)
"""],
    cwd=ROOT, timeout=10
)
import time
time.sleep(2)
if os.path.exists(log_file):
    with open(log_file) as f:
        print(f"[DIAG] spawn_backend test: {f.read().strip()}")
else:
    print("[DIAG] spawn_backend test FAILED - no log file")

# Check 5: Is voice_flow.main actually running after spawn?
result4 = subprocess.run(
    ["tasklist", "/fi", "imagename eq python.exe"],
    capture_output=True, text=True
)
print(f"[DIAG] Running python.exe processes:\n{result4.stdout.strip()}")

print("\n[DIAG] === DONE ===")
