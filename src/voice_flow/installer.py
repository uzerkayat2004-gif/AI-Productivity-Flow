"""Voice Flow Auto-Startup & Desktop Integration Installer.

Configures seamless, zero-console auto-starting for Voice Flow on Windows:
1. Windows Registry: HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\\VoiceFlow
2. Windows Startup Folder: %APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\Voice Flow.lnk
3. User Desktop: %USERPROFILE%\\Desktop\\Voice Flow.lnk
4. Start Menu Programs: %APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Voice Flow.lnk
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import sys
import winreg


def get_project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def get_vbs_launcher_path() -> Path:
    return get_project_root() / "VoiceFlowLauncher.vbs"


def get_icon_path() -> Path:
    return get_project_root() / "src" / "voice_flow" / "gui" / "assets" / "icon.ico"


def get_startup_dir() -> Path:
    """Retrieve standard Windows Startup directory path."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        p = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        if p.exists() or p.parent.exists():
            return p

    # Fallback via Win32 Shell API (CSIDL_STARTUP = 0x0007)
    buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
    ctypes.windll.shell32.SHGetFolderPathW(None, 0x0007, None, 0, buf)
    if buf.value:
        return Path(buf.value)

    return Path(os.path.expanduser(r"~\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup"))


def get_start_menu_programs_dir() -> Path:
    """Retrieve Start Menu Programs folder path."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        p = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        if p.exists():
            return p
    return Path(os.path.expanduser(r"~\AppData\Roaming\Microsoft\Windows\Start Menu\Programs"))


def get_desktop_dirs() -> list[Path]:
    """Retrieve all candidate Desktop folder paths (including OneDrive Desktop)."""
    paths: set[Path] = set()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders") as key:
            dt = winreg.QueryValueEx(key, "Desktop")[0]
            if dt:
                paths.add(Path(dt))
    except Exception:
        pass

    user_dt = Path(os.path.expanduser("~/Desktop"))
    if user_dt.exists():
        paths.add(user_dt)

    onedrive_dt = Path(os.path.expanduser("~/OneDrive/Desktop"))
    if onedrive_dt.exists():
        paths.add(onedrive_dt)

    return [p for p in paths if p.exists()]


def create_windows_shortcut(
    shortcut_path: Path,
    target_path: Path | str,
    arguments: str = "",
    working_dir: Path | str = "",
    icon_path: Path | str = "",
    description: str = "Voice Flow",
) -> bool:
    """Create a Windows .lnk shortcut file via WScript.Shell COM object."""
    import tempfile, time
    shortcut_path.parent.mkdir(parents=True, exist_ok=True)
    safe_target = str(target_path).replace('"', '""')
    safe_args = str(arguments).replace('"', '""')
    safe_workdir = str(working_dir).replace('"', '""')
    safe_icon = str(icon_path).replace('"', '""')
    safe_desc = str(description).replace('"', '""')

    vbs_helper = f"""
Set WshShell = CreateObject("WScript.Shell")
Set Shortcut = WshShell.CreateShortcut("{shortcut_path}")
Shortcut.TargetPath = "{safe_target}"
Shortcut.Arguments = "{safe_args}"
Shortcut.WorkingDirectory = "{safe_workdir}"
Shortcut.IconLocation = "{safe_icon}"
Shortcut.Description = "{safe_desc}"
Shortcut.Save
"""
    try:
        temp_vbs = Path(tempfile.gettempdir()) / f"_temp_shortcut_{os.getpid()}_{time.time_ns()}.vbs"
        temp_vbs.write_text(vbs_helper, encoding="utf-8")
        result = subprocess.run(["cscript.exe", "//Nologo", str(temp_vbs)], capture_output=True, text=True)
        try:
            temp_vbs.unlink()
        except Exception:
            pass
        return shortcut_path.exists()
    except Exception as e:
        print(f"[ERROR] Failed creating shortcut at {shortcut_path}: {e}")
        return False


def register_registry_autorun() -> bool:
    """Register Voice Flow in HKCU Run key for silent boot start."""
    vbs_path = get_vbs_launcher_path()
    if not vbs_path.exists():
        print(f"[ERROR] Launcher not found at {vbs_path}")
        return False

    cmd = f'wscript.exe "{vbs_path}"'
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE) as key:
            winreg.SetValueEx(key, "VoiceFlow", 0, winreg.REG_SZ, cmd)
            val, _ = winreg.QueryValueEx(key, "VoiceFlow")
            if val == cmd:
                print(f"[OK] Registry Auto-Run registered: HKCU\\{key_path}\\VoiceFlow -> {cmd}")
                return True
            return False
    except Exception as e:
        print(f"[ERROR] Failed to set Registry Auto-Run: {e}")
        return False


def unregister_registry_autorun() -> bool:
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE) as key:
            try:
                winreg.DeleteValue(key, "VoiceFlow")
                print(f"[OK] Registry Auto-Run removed: HKCU\\{key_path}\\VoiceFlow")
                return True
            except FileNotFoundError:
                return True
    except Exception as e:
        print(f"[ERROR] Failed to remove Registry Auto-Run: {e}")
        return False


def register_startup_folder() -> bool:
    """Register Voice Flow shortcut in Windows Startup Folder."""
    startup_dir = get_startup_dir()
    startup_dir.mkdir(parents=True, exist_ok=True)
    shortcut_path = startup_dir / "Voice Flow.lnk"

    vbs_path = get_vbs_launcher_path()
    icon_path = get_icon_path()
    root = get_project_root()
    wscript_path = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "wscript.exe")

    success = create_windows_shortcut(
        shortcut_path=shortcut_path,
        target_path=wscript_path,
        arguments=f'"{vbs_path}"',
        working_dir=str(root),
        icon_path=str(icon_path),
        description="Voice Flow - AI Speech Desktop App (Auto-Start)",
    )
    if success:
        print(f"[OK] Startup folder shortcut registered: {shortcut_path}")
    else:
        print(f"[ERROR] Could not create startup folder shortcut at {shortcut_path}")
    return success


def unregister_startup_folder() -> bool:
    startup_dir = get_startup_dir()
    shortcut_path = startup_dir / "Voice Flow.lnk"
    if shortcut_path.exists():
        try:
            shortcut_path.unlink()
            print(f"[OK] Startup folder shortcut removed: {shortcut_path}")
            return True
        except Exception as e:
            print(f"[ERROR] Could not remove shortcut at {shortcut_path}: {e}")
            return False
    return True


def register_desktop_shortcuts() -> bool:
    """Create Desktop and Start Menu programs shortcuts."""
    vbs_path = get_vbs_launcher_path()
    icon_path = get_icon_path()
    root = get_project_root()
    wscript_path = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "wscript.exe")

    success_all = True
    # Desktop shortcuts
    for dt in get_desktop_dirs():
        dt_sc = dt / "Voice Flow.lnk"
        ok = create_windows_shortcut(
            shortcut_path=dt_sc,
            target_path=wscript_path,
            arguments=f'"{vbs_path}"',
            working_dir=str(root),
            icon_path=str(icon_path),
            description="Voice Flow - AI Speech Desktop App",
        )
        if ok:
            print(f"[OK] Desktop shortcut created: {dt_sc}")
        else:
            success_all = False

    # Start Menu Programs shortcut
    sm_dir = get_start_menu_programs_dir()
    sm_sc = sm_dir / "Voice Flow.lnk"
    ok_sm = create_windows_shortcut(
        shortcut_path=sm_sc,
        target_path=wscript_path,
        arguments=f'"{vbs_path}"',
        working_dir=str(root),
        icon_path=str(icon_path),
        description="Voice Flow - AI Speech Desktop App",
    )
    if ok_sm:
        print(f"[OK] Start Menu shortcut created: {sm_sc}")
    else:
        success_all = False

    return success_all


def install_all() -> bool:
    """Execute complete installation of auto-startup and shortcuts."""
    print("========================================================")
    print("  VOICE FLOW — WINDOWS AUTO-STARTUP & APP INSTALLER")
    print("========================================================")
    print()

    # Step 1: Ensure launcher exists
    vbs_path = get_vbs_launcher_path()
    if not vbs_path.exists():
        print(f"[1/4] Generating Launcher VBS at {vbs_path}...")
        from voice_flow.watchdog import get_pythonw_executable
        pyw = get_pythonw_executable()
        vbs_content = f"""Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strPath = fso.GetParentFolderName(WScript.ScriptFullName)
strSrc = strPath & "\\src"
WshShell.CurrentDirectory = strSrc

strPythonw = "{pyw}"
If Not fso.FileExists(strPythonw) Then
    strPythonw = strPath & "\\.venv\\Scripts\\pythonw.exe"
End If
If Not fso.FileExists(strPythonw) Then
    strPythonw = "C:\\Python314\\pythonw.exe"
End If
If Not fso.FileExists(strPythonw) Then
    strPythonw = "pythonw.exe"
End If

WshShell.Run \"\"\"\" & strPythonw & \"\"\" -m voice_flow.watchdog\", 0, False
"""
        vbs_path.write_text(vbs_content, encoding="utf-8")
        print(f"  [OK] Launcher VBS written.")
    else:
        print(f"[1/4] Found Launcher VBS at {vbs_path}")

    # Step 2: Register Windows Registry Auto-Run
    print("\n[2/4] Configuring Windows Registry Auto-Run (HKCU)...")
    reg_ok = register_registry_autorun()

    # Step 3: Register Startup Directory Shortcut
    print("\n[3/4] Configuring Windows Startup Folder Shortcut...")
    su_ok = register_startup_folder()

    # Step 4: Register Desktop & Start Menu Shortcuts
    print("\n[4/4] Creating Desktop & Start Menu Program Shortcuts...")
    dt_ok = register_desktop_shortcuts()

    print("\n========================================================")
    if reg_ok and su_ok and dt_ok:
        print("  INSTALLATION SUCCESSFUL!")
        print("  Voice Flow is now configured for dual-layer auto-startup:")
        print("  1. Windows Registry (HKCU Run)")
        print("  2. Windows Startup Folder (.lnk)")
        print("  3. Background Watchdog Supervisor (Auto-Recovery)")
        print("  4. Zero Console Popup (Silent pythonw execution)")
        print("========================================================")
        return True
    else:
        print("  INSTALLATION COMPLETED WITH WARNINGS.")
        print(f"  Registry: {reg_ok}, Startup Folder: {su_ok}, Shortcuts: {dt_ok}")
        print("========================================================")
        return False


def uninstall_all() -> None:
    print("Uninstalling Voice Flow auto-start configurations...")
    unregister_registry_autorun()
    unregister_startup_folder()
    print("[OK] Uninstalled auto-startup entries.")


def status_report() -> None:
    """Check and display status of all auto-startup components."""
    print("========================================================")
    print("  VOICE FLOW AUTO-STARTUP STATUS DIAGNOSTICS")
    print("========================================================")

    # 1. Registry
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    reg_val = "NOT CONFIGURED"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
            reg_val, _ = winreg.QueryValueEx(key, "VoiceFlow")
    except Exception:
        pass
    print(f"1. Registry Auto-Run:  {reg_val}")

    # 2. Startup Folder
    startup_sc = get_startup_dir() / "Voice Flow.lnk"
    print(f"2. Startup Shortcut:   {'EXISTS (' + str(startup_sc) + ')' if startup_sc.exists() else 'MISSING'}")

    # 3. Launcher VBS
    vbs = get_vbs_launcher_path()
    print(f"3. Launcher VBS:       {'EXISTS (' + str(vbs) + ')' if vbs.exists() else 'MISSING'}")

    # 4. Desktop Shortcut
    dts = [p / "Voice Flow.lnk" for p in get_desktop_dirs()]
    found_dts = [str(p) for p in dts if p.exists()]
    print(f"4. Desktop Shortcuts:  {', '.join(found_dts) if found_dts else 'MISSING'}")

    print("========================================================")


def main() -> None:
    parser = argparse.ArgumentParser(description="Voice Flow Windows Auto-Startup Installer")
    parser.add_argument("--install", action="store_true", default=True, help="Install auto-startup and shortcuts")
    parser.add_argument("--uninstall", action="store_true", help="Remove auto-startup configurations")
    parser.add_argument("--status", action="store_true", help="Check auto-startup status")
    args = parser.parse_args()

    if args.status:
        status_report()
    elif args.uninstall:
        uninstall_all()
    else:
        install_all()


if __name__ == "__main__":
    main()
