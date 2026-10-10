"""Voice Flow Auto-Startup & Desktop Integration Installer.

Configures seamless, zero-console auto-starting for Voice Flow on Windows:
1. A current-user Task Scheduler logon task (preferred), or one HKCU Run
   value when Task Scheduler is unavailable.
2. User Desktop: %USERPROFILE%\\Desktop\\Voice Flow.lnk (manual launch only)
3. Start Menu Programs: %APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Voice Flow.lnk
   (manual launch only)

Legacy Run values and Startup-folder .lnk autostart shortcuts are removed only
after the preferred task has been registered and verified.  Failed migration
rolls the new task back so an upgrade cannot leave two boot mechanisms behind.
"""

from __future__ import annotations

import argparse
import ctypes
from voice_flow.platform.wincompat import wintypes, windll, IS_WINDOWS
import os
from pathlib import Path
import subprocess
import sys

from voice_flow import windows_startup

try:
    import winreg
except ImportError:
    winreg = None  # type: ignore[assignment]


def get_project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _installed_watchdog_command() -> tuple[str, str, str] | None:
    """(pythonw, arguments, working_dir) for the installed app, else None."""
    try:
        from voice_flow import runtime_env
        from voice_flow.paths import data_dir

        pyw = runtime_env.pythonw_executable()
        if pyw:
            return pyw, "-m voice_flow.watchdog", str(data_dir())
    except Exception:
        pass
    return None


def get_vbs_launcher_path() -> Path:
    """Return the VoiceFlowLauncher.vbs path for the active project/installation root."""
    return get_project_root() / "VoiceFlowLauncher.vbs"


def _windows_system_executable(name: str) -> Path:
    return Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / name


def get_startup_action() -> windows_startup.StartupAction | None:
    """Return the verified, absolute action used by Task Scheduler."""
    installed = _installed_watchdog_command()
    if installed is not None:
        pyw, args, working_dir = installed
        executable = Path(pyw)
        if not executable.is_absolute() or not executable.is_file():
            return None
        return windows_startup.StartupAction(str(executable), args, str(Path(working_dir).resolve()))

    vbs_path = get_vbs_launcher_path().resolve()
    wscript = _windows_system_executable("wscript.exe").resolve()
    if not vbs_path.is_file() or not wscript.is_file():
        return None
    return windows_startup.StartupAction(
        executable=str(wscript),
        arguments=f'"{vbs_path}"',
        working_directory=str(get_project_root().resolve()),
    )


def _expected_registry_command() -> str | None:
    action = get_startup_action()
    if action is None:
        return None
    return f'"{action.executable}" {action.arguments}'.strip()



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
    """Register the one HKCU Run fallback when Task Scheduler is unavailable."""
    cmd = _expected_registry_command()
    if cmd is None:
        print("[ERROR] A verified startup command could not be built")
        return False
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
            for val_name in ("VoiceFlow", "Voice Flow", "AI Productivity Flow"):
                try:
                    winreg.DeleteValue(key, val_name)
                    print(f"[OK] Registry Auto-Run removed: HKCU\\{key_path}\\{val_name}")
                except FileNotFoundError:
                    pass
            return True
    except FileNotFoundError:
        return True
    except Exception as e:
        print(f"[ERROR] Failed to remove Registry Auto-Run: {e}")
        return False


def is_registry_autorun_enabled() -> bool:
    """Check whether the current HKCU Run value exactly matches this install."""
    expected = _expected_registry_command()
    if expected is None:
        return False
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
            for val_name in ("VoiceFlow", "Voice Flow", "AI Productivity Flow"):
                try:
                    val, _ = winreg.QueryValueEx(key, val_name)
                    if val_name == "VoiceFlow" and str(val).strip() == expected:
                        return True
                except (FileNotFoundError, OSError):
                    pass
        return False
    except Exception:
        return False


def has_own_registry_autorun() -> bool:
    """Return whether any current or legacy app-owned Run value exists."""
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
            for val_name in ("VoiceFlow", "Voice Flow", "AI Productivity Flow"):
                try:
                    winreg.QueryValueEx(key, val_name)
                    return True
                except (FileNotFoundError, OSError):
                    pass
    except Exception:
        pass
    return False


def is_startup_folder_enabled() -> bool:
    """Check if Voice Flow shortcut exists in Startup folder."""
    try:
        startup_dir = get_startup_dir()
        for name in ("Voice Flow.lnk", "VoiceFlow.lnk", "AI Productivity Flow.lnk"):
            if (startup_dir / name).exists():
                return True
        return False
    except Exception:
        return False


def is_autostart_enabled() -> bool:
    """Return the actual, valid registration state for the current user."""
    return get_autostart_status()[0]


def get_autostart_status() -> tuple[bool, str | None]:
    """Return actual state plus an error when no mechanism can be verified."""
    action = get_startup_action()
    if action is None:
        return False, "A verified Windows startup action could not be built"
    task = windows_startup.inspect_task(action)
    if task.available and task.exists:
        # A disabled or externally changed task is deliberately reported off.
        return task.enabled and task.matches, None
    fallback = is_registry_autorun_enabled() or is_startup_folder_enabled()
    if fallback:
        return True, None
    if not task.available:
        return False, task.error or "Windows Task Scheduler is unavailable"
    return False, None


def _remove_legacy_autostart() -> bool:
    registry_ok = unregister_registry_autorun()
    startup_ok = unregister_startup_folder()
    return registry_ok and startup_ok


def _enable_registry_fallback() -> bool:
    """Create one safe fallback without leaving a Startup shortcut duplicate."""
    if not register_registry_autorun():
        return False
    if unregister_startup_folder():
        return True
    # The old shortcut is still a launch path. Roll back the new Run value.
    unregister_registry_autorun()
    return False


def _finish_task_migration() -> bool:
    """Remove legacy paths, rolling the task back only if one still remains."""
    if _remove_legacy_autostart():
        return True
    if has_own_registry_autorun() or is_startup_folder_enabled():
        # A legacy launch path is still active. Removing the new task avoids a
        # duplicate while retaining the older path as the last mechanism.
        windows_startup.unregister_task()
    # If cleanup reported an error but no legacy path remains, keep the verified
    # task so startup is not accidentally removed altogether.
    return False


def set_autostart(enabled: bool) -> bool:
    """Explicitly enable or disable current-user startup registration."""
    if enabled:
        action = get_startup_action()
        if action is None:
            return False
        current = windows_startup.inspect_task(action)
        if not current.available:
            # A query timeout cannot prove an older task is absent. Preserve an
            # already-verified fallback, but never create a possible duplicate.
            return is_registry_autorun_enabled()
        if current.exists and current.enabled and current.matches:
            # Idempotent: do not rewrite an already-correct task on every GUI open.
            return _finish_task_migration()
        task_result = windows_startup.register_task(action)
        if task_result.success:
            return _finish_task_migration()

        # Registration may have failed after Windows accepted the definition
        # (for example, verification timed out). Never add a fallback until a
        # follow-up inspection proves there is no task.
        after = windows_startup.inspect_task(action)
        if not after.available:
            return False
        if after.exists:
            removed = windows_startup.unregister_task()
            if not removed.success:
                return False
            verified_removed = windows_startup.inspect_task(action)
            if not verified_removed.available or verified_removed.exists:
                return False
        return _enable_registry_fallback()

    task_ok = windows_startup.unregister_task().success
    reg_ok = unregister_registry_autorun()
    su_ok = unregister_startup_folder()
    return task_ok and reg_ok and su_ok


def reconcile_autostart(enabled: bool) -> bool:
    """Reconcile a saved preference without overriding Task Scheduler UI edits.

    An existing disabled task is treated as an explicit external choice. An
    enabled stale task is repaired for this installation. A missing task may
    be created for a saved-on preference; an unavailable scheduler keeps a
    valid Run fallback.
    """
    if not enabled:
        if set_autostart(False):
            return False
        return is_autostart_enabled()
    action = get_startup_action()
    if action is None:
        return False
    current = windows_startup.inspect_task(action)
    if current.available and current.exists:
        if not current.enabled:
            # Remove old secondary paths so the disabled task is the
            # authoritative off state. Do not rewrite the task itself.
            _remove_legacy_autostart()
            return False
        if not current.matches:
            # An enabled stale definition is an upgrade/move failure, so repair
            # it. A disabled definition above remains an explicit user choice.
            return set_autostart(True)
        return _finish_task_migration()
    if not current.available and is_registry_autorun_enabled():
        return not is_startup_folder_enabled() or unregister_startup_folder()
    return set_autostart(True)


def ensure_single_autostart_mechanism() -> bool:
    """Guarantee one verified task, or one Run fallback if unavailable."""
    return set_autostart(True)


def register_startup_folder() -> bool:
    """Register Voice Flow shortcut in Windows Startup Folder."""
    startup_dir = get_startup_dir()
    startup_dir.mkdir(parents=True, exist_ok=True)
    for legacy in ("Voice Flow.lnk", "VoiceFlow.lnk", "voiceFlow.lnk"):
        legacy_sc = startup_dir / legacy
        if legacy_sc.exists():
            try:
                legacy_sc.unlink()
            except Exception:
                pass
    shortcut_path = startup_dir / "AI Productivity Flow.lnk"

    icon_path = get_icon_path()
    installed = _installed_watchdog_command()
    if installed is not None:
        pyw, args, working_dir = installed
        success = create_windows_shortcut(
            shortcut_path=shortcut_path,
            target_path=pyw,
            arguments=args,
            working_dir=working_dir,
            icon_path=str(icon_path),
            description="AI Productivity Flow (Auto-Start)",
        )
        if success:
            print(f"[OK] Startup shortcut created (installed app): {shortcut_path}")
        return success

    vbs_path = get_vbs_launcher_path()
    root = get_project_root()
    wscript_path = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "wscript.exe")

    success = create_windows_shortcut(
        shortcut_path=shortcut_path,
        target_path=wscript_path,
        arguments=f'"{vbs_path}"',
        working_dir=str(root),
        icon_path=str(icon_path),
        description="AI Productivity Flow (Auto-Start)",
    )
    if success:
        print(f"[OK] Startup folder shortcut registered: {shortcut_path}")
    else:
        print(f"[ERROR] Could not create startup folder shortcut at {shortcut_path}")
    return success


def unregister_startup_folder() -> bool:
    startup_dir = get_startup_dir()
    success = True
    for name in ("Voice Flow.lnk", "VoiceFlow.lnk", "voiceFlow.lnk", "AI Productivity Flow.lnk"):
        shortcut_path = startup_dir / name
        if shortcut_path.exists():
            try:
                shortcut_path.unlink()
                print(f"[OK] Startup folder shortcut removed: {shortcut_path}")
            except Exception as e:
                print(f"[ERROR] Could not remove shortcut at {shortcut_path}: {e}")
                success = False
    return success


def register_desktop_shortcuts() -> bool:
    """Create Desktop and Start Menu programs shortcuts."""
    vbs_path = get_vbs_launcher_path()
    icon_path = get_icon_path()
    root = get_project_root()
    wscript_path = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "wscript.exe")

    success_all = True
    # Desktop shortcuts
    for dt in get_desktop_dirs():
        # Remove legacy shortcuts to prevent duplicate desktop icons
        for legacy in ("Voice Flow.lnk", "VoiceFlow.lnk", "voiceFlow.lnk"):
            legacy_dt = dt / legacy
            if legacy_dt.exists():
                try:
                    legacy_dt.unlink()
                    print(f"[OK] Cleaned up legacy shortcut: {legacy_dt}")
                except Exception as e:
                    print(f"[WARNING] Could not remove legacy shortcut at {legacy_dt}: {e}")

        dt_sc = dt / "AI Productivity Flow.lnk"
        ok = create_windows_shortcut(
            shortcut_path=dt_sc,
            target_path=wscript_path,
            arguments=f'"{vbs_path}"',
            working_dir=str(root),
            icon_path=str(icon_path),
            description="AI Productivity Flow",
        )
        if ok:
            print(f"[OK] Desktop shortcut created: {dt_sc}")
        else:
            success_all = False

    # Start Menu Programs shortcut
    sm_dir = get_start_menu_programs_dir()
    for legacy in ("Voice Flow.lnk", "VoiceFlow.lnk", "voiceFlow.lnk"):
        legacy_sm = sm_dir / legacy
        if legacy_sm.exists():
            try:
                legacy_sm.unlink()
                print(f"[OK] Cleaned up legacy Start Menu shortcut: {legacy_sm}")
            except Exception as e:
                print(f"[WARNING] Could not remove legacy Start Menu shortcut at {legacy_sm}: {e}")

    sm_sc = sm_dir / "AI Productivity Flow.lnk"
    ok_sm = create_windows_shortcut(
        shortcut_path=sm_sc,
        target_path=wscript_path,
        arguments=f'"{vbs_path}"',
        working_dir=str(root),
        icon_path=str(icon_path),
        description="AI Productivity Flow",
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

WshShell.Run \"\"\"\" & strPythonw & \"\"\" -m voice_flow.gui.desktop_launcher\", 0, False
"""
        vbs_path.write_text(vbs_content, encoding="utf-8")
        print(f"  [OK] Launcher VBS written.")
    else:
        print(f"[1/4] Found Launcher VBS at {vbs_path}")

    # Steps 2-3 are transactional: verify the preferred logon task first,
    # then remove legacy launch paths. set_autostart rolls back on cleanup
    # failure and uses one Run fallback when Task Scheduler is unavailable.
    print("\n[2/4] Configuring current-user Windows logon startup...")
    startup_ok = ensure_single_autostart_mechanism()

    print("\n[3/4] Verifying a single startup mechanism...")
    single_ok = startup_ok and is_autostart_enabled()

    # Step 4: Register Desktop & Start Menu Shortcuts
    print("\n[4/4] Creating Desktop & Start Menu Program Shortcuts...")
    dt_ok = register_desktop_shortcuts()

    print("\n========================================================")
    if startup_ok and single_ok and dt_ok:
        print("  INSTALLATION SUCCESSFUL!")
        print("  Voice Flow is now configured for single-mechanism auto-startup:")
        print("  1. Current-user logon task (or one HKCU Run fallback)")
        print("  2. Legacy startup entries removed (no duplicate instances at logon)")
        print("  3. Background Watchdog Supervisor (Auto-Recovery)")
        print("  4. Zero Console Popup (Silent pythonw execution)")
        print("========================================================")
        return True
    else:
        print("  INSTALLATION COMPLETED WITH WARNINGS.")
        print(f"  Startup: {startup_ok}, Verified: {single_ok}, Shortcuts: {dt_ok}")
        print("========================================================")
        return False


def uninstall_all() -> bool:
    print("Uninstalling Voice Flow auto-start configurations...")
    task_ok = windows_startup.unregister_task().success
    registry_ok = unregister_registry_autorun()
    startup_ok = unregister_startup_folder()
    success = task_ok and registry_ok and startup_ok
    if success:
        print("[OK] Uninstalled auto-startup entries.")
    else:
        print(
            "[ERROR] Could not remove every auto-startup entry "
            f"(task={task_ok}, registry={registry_ok}, startup={startup_ok})."
        )
    return success


def status_report() -> None:
    """Check and display status of all auto-startup components."""
    print("========================================================")
    print("  VOICE FLOW AUTO-STARTUP STATUS DIAGNOSTICS")
    print("========================================================")

    # 1. Preferred current-user logon task
    action = get_startup_action()
    task = windows_startup.inspect_task(action) if action is not None else None
    if task is None:
        task_text = "INVALID ACTION"
    elif not task.available:
        task_text = f"UNAVAILABLE ({task.error or 'unknown error'})"
    elif not task.exists:
        task_text = "NOT CONFIGURED"
    else:
        task_text = f"{'ENABLED' if task.enabled else 'DISABLED'}, {'CURRENT' if task.matches else 'CHANGED'} ({task.task_name})"
    print(f"1. Logon task:         {task_text}")

    # 2. Registry fallback
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    reg_val = "NOT CONFIGURED"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
            reg_val, _ = winreg.QueryValueEx(key, "VoiceFlow")
    except Exception:
        pass
    print(f"2. Registry fallback:  {reg_val}")

    # 3. Startup Folder
    startup_sc = get_startup_dir() / "AI Productivity Flow.lnk"
    if not startup_sc.exists():
        startup_sc = get_startup_dir() / "Voice Flow.lnk"
    print(f"3. Startup Shortcut:   {'EXISTS (' + str(startup_sc) + ')' if startup_sc.exists() else 'MISSING'}")

    # 4. Launcher VBS
    vbs = get_vbs_launcher_path()
    print(f"4. Launcher VBS:       {'EXISTS (' + str(vbs) + ')' if vbs.exists() else 'MISSING'}")

    # 5. Desktop Shortcut
    dts = [p / "AI Productivity Flow.lnk" for p in get_desktop_dirs()]
    found_dts = [str(p) for p in dts if p.exists()]
    if not found_dts:
        legacy_dts = [p / "Voice Flow.lnk" for p in get_desktop_dirs()]
        found_dts = [str(p) for p in legacy_dts if p.exists()]
    print(f"5. Desktop Shortcuts:  {', '.join(found_dts) if found_dts else 'MISSING'}")

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
