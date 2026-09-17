# ==============================================================================
# 🌊 AI PRODUCTIVITY FLOW — ONE-LINER WINDOWS TERMINAL INSTALLER
#
# Usage (PowerShell):
#   irm https://raw.githubusercontent.com/uzerkayat2004-gif/AI-Productivity-Flow/main/scripts/install.ps1 | iex
#
# Or with options:
#   & ([scriptblock]::Create((irm https://raw.githubusercontent.com/uzerkayat2004-gif/AI-Productivity-Flow/main/scripts/install.ps1))) -Launch
# ==============================================================================

[CmdletBinding()]
param(
    [string]$InstallDir = "$env:LOCALAPPDATA\Programs\AI-Productivity-Flow",
    [string]$Branch = "main",
    [switch]$Launch,
    [switch]$Help
)

if ($Help) {
    Write-Host @"
AI Productivity Flow — Windows Terminal Installer

Parameters:
  -InstallDir <path>   Destination directory (default: %LOCALAPPDATA%\Programs\AI-Productivity-Flow)
  -Branch <name>       Git branch to install from (default: main)
  -Launch              Launch AI Productivity Flow immediately after installation
  -Help                Display this help message

One-Liner Execution:
  irm https://raw.githubusercontent.com/uzerkayat2004-gif/AI-Productivity-Flow/main/scripts/install.ps1 | iex
"@
    exit 0
}

$ErrorActionPreference = "Stop"

function Write-Banner {
    Write-Host ""
    Write-Host "========================================================================" -ForegroundColor Cyan
    Write-Host "   🌊 AI PRODUCTIVITY FLOW — WINDOWS INSTALLER" -ForegroundColor Cyan
    Write-Host "   Zero-friction Speech, Audio, and Video Desktop Transformation" -ForegroundColor Gray
    Write-Host "========================================================================" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Step {
    param([string]$Msg)
    Write-Host "==> $Msg" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Msg)
    Write-Host "  [!] $Msg" -ForegroundColor Yellow
}

function Write-Err {
    param([string]$Msg)
    Write-Host "  [X] $Msg" -ForegroundColor Red
}

function Write-Success {
    param([string]$Msg)
    Write-Host "  [OK] $Msg" -ForegroundColor Green
}

Write-Banner

# ------------------------------------------------------------------------------
# 1. Platform Verification
# ------------------------------------------------------------------------------
if (-not $IsWindows -and $env:OS -notmatch "Windows") {
    Write-Err "This installer is designed for Windows 10/11 (64-bit). For macOS, run:"
    Write-Host '  curl -fsSL https://raw.githubusercontent.com/uzerkayat2004-gif/AI-Productivity-Flow/main/scripts/install.sh | bash' -ForegroundColor Cyan
    exit 1
}

# ------------------------------------------------------------------------------
# 2. Python 3.10+ Detection (Prefer 3.11 / 3.12 for ML wheels)
# ------------------------------------------------------------------------------
Write-Step "Checking Python environment..."

$pythonExe = $null
$candidates = @(
    "C:\Python312\python.exe",
    "C:\Python311\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
    "python.exe",
    "py.exe",
    "C:\Python313\python.exe",
    "C:\Python310\python.exe",
    "C:\Python314\python.exe"
)

foreach ($cand in $candidates) {
    try {
        $cmd = Get-Command $cand -ErrorAction SilentlyContinue
        $target = if ($cmd) { $cmd.Source } else { $cand }
        if (Test-Path $target) {
            $verOut = & $target -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}'); sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) {
                $pythonExe = $target
                Write-Success "Found Python $verOut at: $pythonExe"
                break
            }
        }
    } catch {}
}

if (-not $pythonExe) {
    Write-Err "Python 3.10+ was not found on your system."
    Write-Host ""
    Write-Host "Please install Python 3.10 or newer (Python 3.11/3.12 recommended):" -ForegroundColor Yellow
    Write-Host "  Option A (winget): winget install Python.Python.3.12" -ForegroundColor Cyan
    Write-Host "  Option B (official): https://www.python.org/downloads/" -ForegroundColor Cyan
    Write-Host "Make sure to check 'Add python.exe to PATH' during installation." -ForegroundColor Yellow
    exit 1
}

# ------------------------------------------------------------------------------
# 3. Source Acquisition (Git Clone or Archive Download)
# ------------------------------------------------------------------------------
# Check if already running from inside an existing cloned repo
$isInsideRepo = $false
if ((Test-Path ".\src\voice_flow\main.py") -and (Test-Path ".\pyproject.toml")) {
    $InstallDir = (Get-Item ".").FullName
    $isInsideRepo = $true
    Write-Step "Running directly inside existing AI-Productivity-Flow directory: $InstallDir"
}

if (-not $isInsideRepo) {
    Write-Step "Preparing installation directory: $InstallDir"
    if (-not (Test-Path $InstallDir)) {
        New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    }

    $hasGit = (Get-Command git -ErrorAction SilentlyContinue) -ne $null
    if ($hasGit) {
        if (Test-Path (Join-Path $InstallDir ".git")) {
            Write-Step "Updating existing Git repository in $InstallDir..."
            Push-Location $InstallDir
            try {
                git fetch origin $Branch
                git checkout $Branch
                git pull origin $Branch
                Write-Success "Repository updated successfully."
            } finally {
                Pop-Location
            }
        } else {
            $isDirEmpty = (-not (Test-Path $InstallDir)) -or ((Get-ChildItem -Force $InstallDir).Count -eq 0)
            if ($isDirEmpty) {
                Write-Step "Cloning AI-Productivity-Flow via Git..."
                git clone -b $Branch https://github.com/uzerkayat2004-gif/AI-Productivity-Flow.git $InstallDir
                Write-Success "Cloned into $InstallDir"
            } else {
                Write-Step "Re-syncing AI-Productivity-Flow repository in $InstallDir..."
                git -C $InstallDir init | Out-Null
                git -C $InstallDir remote add origin https://github.com/uzerkayat2004-gif/AI-Productivity-Flow.git 2>$null
                git -C $InstallDir fetch origin $Branch
                git -C $InstallDir checkout -f -B $Branch "origin/$Branch"
                Write-Success "Synchronized repository in $InstallDir"
            }
        }
    } else {
        Write-Warn "Git command not detected. Downloading source archive from GitHub..."
        $zipUrl = "https://github.com/uzerkayat2004-gif/AI-Productivity-Flow/archive/refs/heads/$Branch.zip"
        $zipDest = Join-Path $env:TEMP "AI-Productivity-Flow-$Branch.zip"
        Write-Host "  Downloading: $zipUrl" -ForegroundColor Gray
        Invoke-RestMethod -Uri $zipUrl -OutFile $zipDest
        
        Write-Step "Extracting archive to $InstallDir..."
        $extractTemp = Join-Path $env:TEMP "AI-Productivity-Flow-extract-$([Guid]::NewGuid().ToString('N'))"
        Expand-Archive -Path $zipDest -DestinationPath $extractTemp -Force
        
        $innerDir = Join-Path $extractTemp "AI-Productivity-Flow-$Branch"
        Get-ChildItem -Force -Path $innerDir | Copy-Item -Destination $InstallDir -Recurse -Force
        Remove-Item -Path $extractTemp -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item -Path $zipDest -Force -ErrorAction SilentlyContinue
        Write-Success "Extracted source to $InstallDir"
    }
}

# ------------------------------------------------------------------------------
# 4. Virtual Environment & Core Python Package Setup
# ------------------------------------------------------------------------------
Push-Location $InstallDir
try {
    $venvDir = Join-Path $InstallDir ".venv"
    $venvPython = Join-Path $venvDir "Scripts\python.exe"

    if (-not (Test-Path $venvPython)) {
        Write-Step "Creating isolated Python virtual environment (.venv)..."
        & $pythonExe -m venv $venvDir
        Write-Success "Virtual environment created."
    }

    # Ensure pip is available inside virtual environment
    $hasPip = (& $venvPython -m pip --version 2>$null) -ne $null
    if (-not $hasPip) {
        Write-Step "Bootstrapping pip into virtual environment..."
        & $venvPython -m ensurepip --default-pip 2>$null
    }

    Write-Step "Installing AI-Productivity-Flow and core dependencies (editable)..."
    $hasUv = (Get-Command uv -ErrorAction SilentlyContinue) -ne $null
    if ($hasUv) {
        Write-Step "Accelerating package installation using uv..."
        & uv pip install -e . --python $venvPython
    } else {
        & $venvPython -m pip install --upgrade pip --quiet
        & $venvPython -m pip install -e .
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to install Python dependencies. Please review error messages above."
        exit $LASTEXITCODE
    }
    Write-Success "Python packages installed successfully."

    # --------------------------------------------------------------------------
    # 5. Video Flow Renderer Dependencies (Node.js/npm)
    # --------------------------------------------------------------------------
    $rendererDir = Join-Path $InstallDir "video_flow_renderer"
    if (Test-Path (Join-Path $rendererDir "package.json")) {
        $hasNpm = (Get-Command npm -ErrorAction SilentlyContinue) -ne $null
        if ($hasNpm) {
            Write-Step "Configuring Video Flow deterministic renderer dependencies (npm)..."
            Push-Location $rendererDir
            try {
                npm install --silent
                Write-Success "Video Flow renderer dependencies installed."
            } catch {
                Write-Warn "npm install completed with warnings; Video Flow procedural fallback remains active."
            } finally {
                Pop-Location
            }
        } else {
            Write-Warn "Node.js/npm not detected. (Video Flow procedural/browser fallbacks work; install Node.js 18+ for Remotion renderer)."
        }
    }

    # --------------------------------------------------------------------------
    # 6. Desktop Setup & Auto-Startup Registration
    # --------------------------------------------------------------------------
    Write-Step "Registering resilient Windows auto-startup and Start Menu shortcuts..."
    try {
        & $venvPython -m voice_flow.installer --install
        Write-Success "Startup entries and shortcuts registered."
    } catch {
        Write-Warn "Could not register startup entry automatically. You can run .\setup_desktop_app.bat manually."
    }

    # --------------------------------------------------------------------------
    # 7. Installation Summary
    # --------------------------------------------------------------------------
    Write-Host ""
    Write-Host "========================================================================" -ForegroundColor Green
    Write-Host "   🎉 AI PRODUCTIVITY FLOW INSTALLED SUCCESSFULLY!" -ForegroundColor Green
    Write-Host "========================================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Installed Location: $InstallDir" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "How to Run Flow:" -ForegroundColor Yellow
    Write-Host "  1. Silent Background Mode (Recommended):"
    Write-Host "     Double-click VoiceFlowLauncher.vbs in the installation directory, or run:"
    Write-Host "     wscript.exe `"$InstallDir\VoiceFlowLauncher.vbs`"" -ForegroundColor Cyan
    Write-Host "  2. Interactive Console Mode:"
    Write-Host "     & `"$InstallDir\run_voice_flow.bat`" --console" -ForegroundColor Cyan
    Write-Host "  3. Open Web Dashboard:"
    Write-Host "     http://127.0.0.1:8991" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Core Desktop Triggers:" -ForegroundColor Yellow
    Write-Host "  • Voice Flow Dictation: Hold Middle Mouse Button or press [Ctrl + Win]" -ForegroundColor Gray
    Write-Host "  • Audio Flow Reader:    Select text anywhere -> click Audio Flow" -ForegroundColor Gray
    Write-Host "  • Video Flow Explainer: Select text anywhere -> click Video Flow" -ForegroundColor Gray
    Write-Host ""

    if ($Launch) {
        Write-Step "Launching AI Productivity Flow in silent background mode..."
        $vbsTarget = Join-Path $InstallDir "VoiceFlowLauncher.vbs"
        $batTarget = Join-Path $InstallDir "run_voice_flow.bat"
        if (Test-Path $vbsTarget) {
            Start-Process "wscript.exe" -ArgumentList "`"$vbsTarget`""
        } elseif (Test-Path $batTarget) {
            Start-Process $batTarget
        }
        Write-Success "AI Productivity Flow launched!"
    }

} finally {
    Pop-Location
}
