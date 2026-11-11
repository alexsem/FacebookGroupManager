#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Facebook Group Batch Poster - Setup & Launcher Script
# Works on Windows (Git Bash / MSYS2), WSL, Linux, and macOS.
#
# Usage:
#   ./setup_and_run.sh                 # Setup (if needed) and launch PySide6 GUI
#   ./setup_and_run.sh --setup-only    # Setup environment and dependencies only
#   ./setup_and_run.sh --reinstall     # Force reinstall Python deps & browser
#   ./setup_and_run.sh --login         # Pass CLI args directly to main.py
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

SETUP_ONLY=false
FORCE_REINSTALL=false
APP_ARGS=()

for arg in "$@"; do
    case "$arg" in
        --setup-only)
            SETUP_ONLY=true
            ;;
        --reinstall)
            FORCE_REINSTALL=true
            ;;
        *)
            APP_ARGS+=("$arg")
            ;;
    esac
done

echo "============================================================"
echo "  Facebook Group Batch Poster - Setup & Run"
echo "============================================================"

# 1. Detect base Python interpreter
find_base_python() {
    if command -v python3 >/dev/null 2>&1; then
        echo "python3"
    elif command -v python >/dev/null 2>&1; then
        echo "python"
    else
        echo ""
    fi
}

BASE_PYTHON="$(find_base_python)"
if [[ -z "$BASE_PYTHON" ]] && ! command -v uv >/dev/null 2>&1; then
    echo "[ERROR] Neither 'python' nor 'uv' was found in PATH."
    echo "Please install Python 3.10+ (https://www.python.org/) and try again."
    exit 1
fi

# 2. Create virtual environment (.venv) if missing
if [[ ! -d ".venv" ]]; then
    echo "[1/4] Creating virtual environment in .venv ..."
    if command -v uv >/dev/null 2>&1; then
        uv venv --seed .venv
    else
        "$BASE_PYTHON" -m venv .venv
    fi
else
    echo "[1/4] Virtual environment (.venv) already exists."
fi

# 3. Locate Python inside .venv (Windows Git Bash vs POSIX)
if [[ -f ".venv/Scripts/python.exe" ]]; then
    VENV_PYTHON=".venv/Scripts/python.exe"
elif [[ -f ".venv/bin/python" ]]; then
    VENV_PYTHON=".venv/bin/python"
else
    echo "[ERROR] Could not locate Python executable inside .venv."
    exit 1
fi

# 4. Install or update Python dependencies when requirements.txt changes
REQ_HASH="$("$VENV_PYTHON" -c "import hashlib, pathlib; print(hashlib.sha256(pathlib.Path('requirements.txt').read_bytes()).hexdigest())")"
HASH_FILE=".venv/.requirements.sha256"
PREV_HASH=""
if [[ -f "$HASH_FILE" ]]; then
    PREV_HASH="$(cat "$HASH_FILE")"
fi

if [[ "$FORCE_REINSTALL" == true || "$REQ_HASH" != "$PREV_HASH" ]]; then
    echo "[2/4] Installing dependencies from requirements.txt ..."
    if command -v uv >/dev/null 2>&1; then
        uv pip install --python "$VENV_PYTHON" -r requirements.txt
    else
        "$VENV_PYTHON" -m pip install --upgrade pip
        "$VENV_PYTHON" -m pip install -r requirements.txt
    fi
    echo "$REQ_HASH" > "$HASH_FILE"
else
    echo "[2/4] Dependencies are up to date."
fi

# 5. Ensure Playwright Chromium browser is installed
PW_MARKER=".venv/.playwright_chromium_ready"
if [[ "$FORCE_REINSTALL" == true || ! -f "$PW_MARKER" ]]; then
    echo "[3/4] Installing/verifying Playwright Chromium browser ..."
    "$VENV_PYTHON" -m playwright install chromium
    touch "$PW_MARKER"
else
    echo "[3/4] Playwright Chromium browser already verified."
fi

# 6. Bootstrap default configuration files if missing
echo "[4/4] Checking configuration files ..."
if [[ ! -f ".env" && -f ".env.example" ]]; then
    cp .env.example .env
    echo "  -> Created .env from .env.example"
fi
if [[ ! -f "groups.txt" && -f "groups.txt.example" ]]; then
    cp groups.txt.example groups.txt
    echo "  -> Created groups.txt from groups.txt.example"
fi
if [[ ! -d "post_data" && -f "post_content.txt.example" ]]; then
    mkdir -p post_data
    cp post_content.txt.example post_data/post_content.txt
    echo "  -> Created post_data/post_content.txt from post_content.txt.example"
fi

echo "Setup complete!"

if [[ "$SETUP_ONLY" == true ]]; then
    echo "Setup-only mode requested. Exiting without launching the application."
    exit 0
fi

echo "Launching Facebook Group Batch Poster ..."
if [[ ${#APP_ARGS[@]} -eq 0 ]]; then
    exec "$VENV_PYTHON" main.py
else
    exec "$VENV_PYTHON" main.py "${APP_ARGS[@]}"
fi
