"""Bounded, current-user Windows Task Scheduler integration.

The public functions in this module are inert on import.  Every scheduler
operation runs a short, non-elevated Windows PowerShell process with a fixed
timeout and exchanges one bounded JSON document.  Values used in the task are
passed through the environment rather than interpolated into PowerShell.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
from typing import Callable, Mapping


TASK_PREFIX = "AI Productivity Flow"
TASK_DELAY = "PT10S"
POWERSHELL_TIMEOUT_SECONDS = 10.0
MAX_OUTPUT_CHARS = 64 * 1024


@dataclass(frozen=True)
class StartupAction:
    executable: str
    arguments: str
    working_directory: str


@dataclass(frozen=True)
class TaskStatus:
    available: bool
    exists: bool = False
    enabled: bool = False
    matches: bool = False
    task_name: str = ""
    sid: str = ""
    error: str | None = None


@dataclass(frozen=True)
class TaskResult:
    success: bool
    available: bool = True
    status: TaskStatus | None = None
    error: str | None = None


PowerShellRunner = Callable[[str, Mapping[str, str]], dict[str, object]]


_INSPECT_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $OutputEncoding
function Get-HResultHex($exception) {
    while ($null -ne $exception) {
        $hex = '{0:X8}' -f ($exception.HResult -band 0xffffffffL)
        if ($hex -ne '00000000') { return $hex }
        $exception = $exception.InnerException
    }
    return ''
}
function Resolve-IdentitySid($identity) {
    if ([string]::IsNullOrWhiteSpace([string]$identity)) { return '' }
    try {
        return ([System.Security.Principal.SecurityIdentifier]::new([string]$identity)).Value
    } catch {
        try {
            $account = [System.Security.Principal.NTAccount]::new([string]$identity)
            return ($account.Translate([System.Security.Principal.SecurityIdentifier])).Value
        } catch {
            return ''
        }
    }
}
$sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$name = 'AI Productivity Flow-' + $sid
$service = New-Object -ComObject 'Schedule.Service'
$service.Connect()
$folder = $service.GetFolder('\')
try { $task = $folder.GetTask($name) } catch {
    if ((Get-HResultHex $_.Exception) -eq '80070002') { $task = $null } else { throw }
}
if ($null -eq $task) {
    @{ available = $true; exists = $false; taskName = $name; sid = $sid } | ConvertTo-Json -Compress
    exit 0
}
$definition = $task.Definition
$action = if ($definition.Actions.Count -eq 1) { $definition.Actions.Item(1) } else { $null }
$trigger = if ($definition.Triggers.Count -eq 1) { $definition.Triggers.Item(1) } else { $null }
$expected = ConvertFrom-Json $env:VOICE_FLOW_STARTUP_CONFIG
$principalSid = Resolve-IdentitySid $definition.Principal.UserId
$triggerSid = if ($null -ne $trigger) { Resolve-IdentitySid $trigger.UserId } else { '' }
$matches = (
    $principalSid -eq $sid -and
    [int]$definition.Principal.LogonType -eq 3 -and
    [int]$definition.Principal.RunLevel -eq 0 -and
    $null -ne $action -and [int]$action.Type -eq 0 -and
    $action.Path -eq $expected.executable -and
    $action.Arguments -eq $expected.arguments -and
    $action.WorkingDirectory -eq $expected.workingDirectory -and
    $null -ne $trigger -and [int]$trigger.Type -eq 9 -and
    $trigger.Enabled -and $triggerSid -eq $sid -and $trigger.Delay -eq 'PT10S' -and
    -not $definition.Settings.DisallowStartIfOnBatteries -and
    -not $definition.Settings.StopIfGoingOnBatteries -and
    -not $definition.Settings.RunOnlyIfIdle -and
    -not $definition.Settings.RunOnlyIfNetworkAvailable -and
    $definition.Settings.StartWhenAvailable -and
    $definition.Settings.ExecutionTimeLimit -eq 'PT0S' -and
    $definition.Settings.RestartInterval -eq 'PT1M' -and
    [int]$definition.Settings.RestartCount -eq 3 -and
    [int]$definition.Settings.Priority -eq 6 -and
    [int]$definition.Settings.MultipleInstances -eq 2
)
@{
    available = $true
    exists = $true
    enabled = [bool]$task.Enabled
    matches = [bool]$matches
    taskName = $name
    sid = $sid
} | ConvertTo-Json -Compress
"""


_REGISTER_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $OutputEncoding
$expected = ConvertFrom-Json $env:VOICE_FLOW_STARTUP_CONFIG
$sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$name = 'AI Productivity Flow-' + $sid
$service = New-Object -ComObject 'Schedule.Service'
$service.Connect()
$folder = $service.GetFolder('\')
$definition = $service.NewTask(0)
$definition.RegistrationInfo.Description = 'Starts AI Productivity Flow after this user signs in.'
$definition.Principal.UserId = $sid
$definition.Principal.LogonType = 3
$definition.Principal.RunLevel = 0
$trigger = $definition.Triggers.Create(9)
$trigger.UserId = $sid
$trigger.Delay = 'PT10S'
$trigger.Enabled = $true
$action = $definition.Actions.Create(0)
$action.Path = $expected.executable
$action.Arguments = $expected.arguments
$action.WorkingDirectory = $expected.workingDirectory
$settings = $definition.Settings
$settings.Enabled = $true
$settings.AllowDemandStart = $true
$settings.DisallowStartIfOnBatteries = $false
$settings.StopIfGoingOnBatteries = $false
$settings.RunOnlyIfIdle = $false
$settings.RunOnlyIfNetworkAvailable = $false
$settings.StartWhenAvailable = $true
$settings.ExecutionTimeLimit = 'PT0S'
$settings.RestartInterval = 'PT1M'
$settings.RestartCount = 3
$settings.Priority = 6
$settings.MultipleInstances = 2
$folder.RegisterTaskDefinition($name, $definition, 6, $sid, $null, 3, $null) | Out-Null
@{ success = $true; available = $true; taskName = $name; sid = $sid } | ConvertTo-Json -Compress
"""


_DELETE_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $OutputEncoding
function Get-HResultHex($exception) {
    while ($null -ne $exception) {
        $hex = '{0:X8}' -f ($exception.HResult -band 0xffffffffL)
        if ($hex -ne '00000000') { return $hex }
        $exception = $exception.InnerException
    }
    return ''
}
$sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$name = 'AI Productivity Flow-' + $sid
$service = New-Object -ComObject 'Schedule.Service'
$service.Connect()
$folder = $service.GetFolder('\')
try { $folder.DeleteTask($name, 0) } catch {
    if ((Get-HResultHex $_.Exception) -ne '80070002') { throw }
}
@{ success = $true; available = $true; taskName = $name; sid = $sid } | ConvertTo-Json -Compress
"""


def powershell_executable() -> Path:
    return (
        Path(os.environ.get("SystemRoot", r"C:\Windows"))
        / "System32"
        / "WindowsPowerShell"
        / "v1.0"
        / "powershell.exe"
    )


def _config(action: StartupAction) -> dict[str, str]:
    return {
        "executable": action.executable,
        "arguments": action.arguments,
        "workingDirectory": action.working_directory,
    }


def _run_powershell(script: str, env_values: Mapping[str, str]) -> dict[str, object]:
    if sys.platform != "win32":
        raise RuntimeError("Windows Task Scheduler is unavailable on this platform")
    powershell = powershell_executable()
    if not powershell.is_file():
        raise RuntimeError(f"Windows PowerShell was not found at {powershell}")
    env = os.environ.copy()
    env.update(env_values)
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    try:
        completed = subprocess.run(
            [
                str(powershell),
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=POWERSHELL_TIMEOUT_SECONDS,
            check=False,
            shell=False,
            creationflags=creationflags,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"Windows Task Scheduler did not respond within {POWERSHELL_TIMEOUT_SECONDS:g} seconds"
        ) from exc
    stdout = (completed.stdout or "")[:MAX_OUTPUT_CHARS].strip()
    stderr = (completed.stderr or "")[:MAX_OUTPUT_CHARS].strip()
    if completed.returncode != 0:
        detail = stderr or stdout or f"PowerShell exited with code {completed.returncode}"
        raise RuntimeError(f"Windows Task Scheduler failed: {detail}")
    if not stdout:
        raise RuntimeError("Windows Task Scheduler returned no status")
    try:
        payload = json.loads(stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Windows Task Scheduler returned malformed status") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Windows Task Scheduler returned malformed status")
    return payload


def inspect_task(action: StartupAction, *, runner: PowerShellRunner = _run_powershell) -> TaskStatus:
    env = {"VOICE_FLOW_STARTUP_CONFIG": json.dumps(_config(action), ensure_ascii=True)}
    try:
        payload = runner(_INSPECT_SCRIPT, env)
        if payload.get("available") is not True:
            return TaskStatus(False, error="Windows Task Scheduler is unavailable")
        return TaskStatus(
            available=True,
            exists=payload.get("exists") is True,
            enabled=payload.get("enabled") is True,
            matches=payload.get("matches") is True,
            task_name=str(payload.get("taskName") or ""),
            sid=str(payload.get("sid") or ""),
        )
    except Exception as exc:
        return TaskStatus(False, error=str(exc))


def register_task(action: StartupAction, *, runner: PowerShellRunner = _run_powershell) -> TaskResult:
    env = {"VOICE_FLOW_STARTUP_CONFIG": json.dumps(_config(action), ensure_ascii=True)}
    try:
        payload = runner(_REGISTER_SCRIPT, env)
        if payload.get("success") is not True:
            return TaskResult(False, payload.get("available") is True, error="Task registration failed")
        status = inspect_task(action, runner=runner)
        if not (status.available and status.exists and status.enabled and status.matches):
            return TaskResult(False, status.available, status=status, error=status.error or "Task verification failed")
        return TaskResult(True, available=status.available, status=status)
    except Exception as exc:
        return TaskResult(False, False, error=str(exc))


def unregister_task(*, runner: PowerShellRunner = _run_powershell) -> TaskResult:
    try:
        payload = runner(_DELETE_SCRIPT, {})
        if payload.get("success") is True:
            return TaskResult(True, payload.get("available") is True)
        return TaskResult(False, payload.get("available") is True, error="Task removal failed")
    except Exception as exc:
        return TaskResult(False, False, error=str(exc))


__all__ = [
    "StartupAction",
    "TaskResult",
    "TaskStatus",
    "inspect_task",
    "register_task",
    "unregister_task",
]
