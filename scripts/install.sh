#!/usr/bin/env bash
# ==============================================================================
# 🌊 AI PRODUCTIVITY FLOW — ONE-LINER macOS TERMINAL INSTALLER
#
# Usage (macOS Terminal):
#   curl -fsSL https://raw.githubusercontent.com/uzerkayat2004-gif/AI-Productivity-Flow/main/scripts/install.sh | bash
#
# Or with options:
#   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/uzerkayat2004-gif/AI-Productivity-Flow/main/scripts/install.sh)" -- --launch
# ==============================================================================

set -eo pipefail

INSTALL_DIR="${HOME}/AI-Productivity-Flow"
BRANCH="main"
SHOULD_LAUNCH=0

for arg in "$@"; do
    case "$arg" in
        --dir=*)
            INSTALL_DIR="${arg#*=}"
            ;;
        --branch=*)
            BRANCH="${arg#*=}"
            ;;
        --launch)
            SHOULD_LAUNCH=1
            ;;
        --help|-h)
            echo "AI Productivity Flow — macOS Terminal Installer"
            echo ""
            echo "Options:"
            echo "  --dir=<path>    Destination directory (default: ~/AI-Productivity-Flow)"
            echo "  --branch=<name> Git branch (default: main)"
            echo "  --launch        Launch app immediately after installation"
            echo "  --help, -h      Show this message"
            exit 0
            ;;
    esac
done

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

echo ""
echo -e "${CYAN}========================================================================${NC}"
echo -e "${BOLD}${CYAN}   🌊 AI PRODUCTIVITY FLOW — macOS INSTALLER${NC}"
echo -e "   Zero-friction Speech, Audio, and Video Transformation"
echo -e "${CYAN}========================================================================${NC}"
echo ""

# ==============================================================================
# ⚠️ PROMINENT EXPERIMENTAL DISCLAIMER FOR macOS
# ==============================================================================
echo -e "${YELLOW}╔══════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${YELLOW}║  ${BOLD}⚠️  NOTE: macOS SUPPORT IS EXPERIMENTAL / COMMUNITY PREVIEW${NC}${YELLOW}        ║${NC}"
echo -e "${YELLOW}╠══════════════════════════════════════════════════════════════════════╣${NC}"
echo -e "${YELLOW}║${NC}  The macOS build has ${BOLD}not yet undergone full physical hardware testing${NC}.  ${YELLOW}║${NC}"
echo -e "${YELLOW}║${NC}  You may experience permissions prompts, audio input latency, or     ${YELLOW}║${NC}"
echo -e "${YELLOW}║${NC}  minor hotkey quirks depending on your macOS version and hardware.    ${YELLOW}║${NC}"
echo -e "${YELLOW}║${NC}                                                                      ${YELLOW}║${NC}"
echo -e "${YELLOW}║${NC}  • Windows 10/11 x64 is the primary, production-verified platform.    ${YELLOW}║${NC}"
echo -e "${YELLOW}║${NC}  • macOS Apple Silicon (M1/M2/M3/M4) and Intel are supported in       ${YELLOW}║${NC}"
echo -e "${YELLOW}║${NC}    active development mode.                                           ${YELLOW}║${NC}"
echo -e "${YELLOW}║${NC}                                                                      ${YELLOW}║${NC}"
echo -e "${YELLOW}║${NC}  Please report any macOS bugs or feedback to:                        ${YELLOW}║${NC}"
echo -e "${YELLOW}║${NC}  ${CYAN}https://github.com/uzerkayat2004-gif/AI-Productivity-Flow/issues${NC}     ${YELLOW}║${NC}"
echo -e "${YELLOW}╚══════════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ------------------------------------------------------------------------------
# 1. OS Check
# ------------------------------------------------------------------------------
OS_NAME="$(uname -s)"
if [ "$OS_NAME" != "Darwin" ]; then
    echo -e "${RED}[X] Error: This script is intended for macOS (Darwin). Detected: $OS_NAME${NC}"
    echo "For Windows, run in PowerShell:"
    echo "  irm https://raw.githubusercontent.com/uzerkayat2004-gif/AI-Productivity-Flow/main/scripts/install.ps1 | iex"
    exit 1
fi

ARCH="$(uname -m)"
echo -e "${GREEN}==>${NC} Detected macOS on ${BOLD}${ARCH}${NC}"

# ------------------------------------------------------------------------------
# 2. Python 3.10+ Detection
# ------------------------------------------------------------------------------
echo -e "${GREEN}==>${NC} Checking Python 3 environment..."
PYTHON_BIN=""

for cand in python3 /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
    if command -v "$cand" >/dev/null 2>&1; then
        if "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
            PYTHON_BIN="$cand"
            PY_VER="$("$cand" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')"
            echo -e "  ${GREEN}[OK]${NC} Found Python ${PY_VER} at: ${PYTHON_BIN}"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo -e "${RED}[X] Python 3.10+ is required but was not found.${NC}"
    echo -e "Please install Python 3.10+ using Homebrew:"
    echo -e "  ${CYAN}brew install python${NC}"
    echo -e "Or download from: https://www.python.org/downloads/"
    exit 1
fi

# ------------------------------------------------------------------------------
# 3. Source Acquisition
# ------------------------------------------------------------------------------
# Check if running from inside an existing cloned repo
if [ -f "./src/voice_flow/main.py" ] && [ -f "./pyproject.toml" ]; then
    INSTALL_DIR="$(pwd)"
    echo -e "${GREEN}==>${NC} Running inside existing AI-Productivity-Flow directory: ${INSTALL_DIR}"
else
    echo -e "${GREEN}==>${NC} Target directory: ${INSTALL_DIR}"
    mkdir -p "${INSTALL_DIR}"

    if command -v git >/dev/null 2>&1; then
        if [ -d "${INSTALL_DIR}/.git" ]; then
            echo -e "${GREEN}==>${NC} Updating existing Git repository in ${INSTALL_DIR}..."
            (cd "${INSTALL_DIR}" && git fetch origin "${BRANCH}" && git checkout "${BRANCH}" && git pull origin "${BRANCH}")
        else
            echo -e "${GREEN}==>${NC} Cloning AI-Productivity-Flow via Git..."
            git clone -b "${BRANCH}" https://github.com/uzerkayat2004-gif/AI-Productivity-Flow.git "${INSTALL_DIR}"
        fi
    else
        echo -e "${YELLOW}  [!] Git not detected. Downloading source archive via curl...${NC}"
        ZIP_URL="https://github.com/uzerkayat2004-gif/AI-Productivity-Flow/archive/refs/heads/${BRANCH}.zip"
        TEMP_ZIP="/tmp/ai-productivity-flow-${BRANCH}.zip"
        TEMP_EXTRACT="/tmp/ai-flow-mac-extract-$$"
        
        curl -fsSL "${ZIP_URL}" -o "${TEMP_ZIP}"
        mkdir -p "${TEMP_EXTRACT}"
        unzip -q "${TEMP_ZIP}" -d "${TEMP_EXTRACT}"
        cp -R "${TEMP_EXTRACT}/AI-Productivity-Flow-${BRANCH}/"* "${INSTALL_DIR}/"
        rm -rf "${TEMP_EXTRACT}" "${TEMP_ZIP}"
        echo -e "  ${GREEN}[OK]${NC} Extracted source code."
    fi
fi

# ------------------------------------------------------------------------------
# 4. Virtual Environment & Dependencies
# ------------------------------------------------------------------------------
cd "${INSTALL_DIR}"

VENV_DIR="${INSTALL_DIR}/.venv"
if [ ! -d "${VENV_DIR}" ]; then
    echo -e "${GREEN}==>${NC} Creating Python virtual environment (.venv)..."
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

VENV_PYTHON="${VENV_DIR}/bin/python"
VENV_PIP="${VENV_DIR}/bin/pip"

echo -e "${GREEN}==>${NC} Installing AI Productivity Flow and dependencies..."
"${VENV_PIP}" install --upgrade pip --quiet
"${VENV_PIP}" install -e .

# ------------------------------------------------------------------------------
# 5. Video Flow Renderer Dependencies (Optional Node.js)
# ------------------------------------------------------------------------------
if [ -d "video_flow_renderer" ] && [ -f "video_flow_renderer/package.json" ]; then
    if command -v npm >/dev/null 2>&1; then
        echo -e "${GREEN}==>${NC} Installing Video Flow renderer dependencies (npm)..."
        (cd video_flow_renderer && npm install --silent) || echo -e "${YELLOW}  [!] npm install finished with warnings.${NC}"
    else
        echo -e "${YELLOW}  [!] Node.js/npm not found. Video Flow will use browser/canvas fallbacks.${NC}"
    fi
fi

# ------------------------------------------------------------------------------
# 6. Build macOS Application Bundle (.app)
# ------------------------------------------------------------------------------
echo -e "${GREEN}==>${NC} Building native macOS Application Bundle..."
if [ -f "scripts/build_macos_app.py" ]; then
    "${VENV_PYTHON}" scripts/build_macos_app.py || true
fi

# If Voice Flow.app was created, offer to link or copy to /Applications
if [ -d "dist/Voice Flow.app" ]; then
    if [ -w "/Applications" ]; then
        echo -e "${GREEN}==>${NC} Installing Voice Flow.app into /Applications..."
        rm -rf "/Applications/Voice Flow.app" 2>/dev/null || true
        cp -R "dist/Voice Flow.app" "/Applications/"
        xattr -cr "/Applications/Voice Flow.app" 2>/dev/null || true
        APP_PATH="/Applications/Voice Flow.app"
    else
        mkdir -p "${HOME}/Applications"
        echo -e "${GREEN}==>${NC} Installing Voice Flow.app into ~/Applications..."
        rm -rf "${HOME}/Applications/Voice Flow.app" 2>/dev/null || true
        cp -R "dist/Voice Flow.app" "${HOME}/Applications/"
        xattr -cr "${HOME}/Applications/Voice Flow.app" 2>/dev/null || true
        APP_PATH="${HOME}/Applications/Voice Flow.app"
    fi
    echo -e "  ${GREEN}[OK]${NC} Installed: ${APP_PATH}"
fi

# ------------------------------------------------------------------------------
# 7. Permissions Instructions & Summary
# ------------------------------------------------------------------------------
echo ""
echo -e "${GREEN}========================================================================${NC}"
echo -e "${BOLD}${GREEN}   🎉 AI PRODUCTIVITY FLOW INSTALLED ON macOS!${NC}"
echo -e "${GREEN}========================================================================${NC}"
echo ""
echo -e "${BOLD}Required macOS Permissions:${NC}"
echo -e "To allow global dictation and text paste across applications, macOS requires"
echo -e "the following three permissions in ${CYAN}System Settings > Privacy & Security${NC}:"
echo -e "  1. ${BOLD}Microphone${NC}        — for Voice Flow speech recognition"
echo -e "  2. ${BOLD}Accessibility${NC}     — to paste polished text into your active app"
echo -e "  3. ${BOLD}Input Monitoring${NC}  — to detect the global push-to-talk triggers"
echo ""
echo -e "${BOLD}Running AI Productivity Flow:${NC}"
echo -e "  • ${BOLD}From Finder / Spotlight:${NC} Open ${CYAN}Voice Flow.app${NC}"
echo -e "  • ${BOLD}From Terminal:${NC}          ${CYAN}${VENV_PYTHON} -m voice_flow.main${NC}"
echo -e "  • ${BOLD}Web Dashboard:${NC}          ${CYAN}http://127.0.0.1:8991${NC}"
echo ""
echo -e "${YELLOW}Reminder: macOS support is in Community Preview. If you hit any issues,${NC}"
echo -e "${YELLOW}please open an issue at: https://github.com/uzerkayat2004-gif/AI-Productivity-Flow/issues${NC}"
echo ""

if [ "$SHOULD_LAUNCH" -eq 1 ]; then
    if [ -n "$APP_PATH" ] && [ -d "$APP_PATH" ]; then
        echo -e "${GREEN}==>${NC} Launching Voice Flow.app..."
        open "$APP_PATH"
    else
        echo -e "${GREEN}==>${NC} Launching from terminal..."
        "${VENV_PYTHON}" -m voice_flow.main &
    fi
fi
