@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ==============================================================================
REM Facebook Group Batch Poster - Windows CMD Setup & Launcher Script
REM
REM Usage:
REM   setup_and_run.bat                 (Setup if needed and launch PySide6 GUI)
REM   setup_and_run.bat --setup-only    (Setup environment and dependencies only)
REM   setup_and_run.bat --reinstall     (Force reinstall Python deps & browser)
REM   setup_and_run.bat --login         (Forward CLI args directly to main.py)
REM ==============================================================================

cd /d "%~dp0"

set "SETUP_ONLY=0"
set "FORCE_REINSTALL=0"
set "APP_ARGS="

:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--setup-only" (
    set "SETUP_ONLY=1"
) else if /I "%~1"=="--reinstall" (
    set "FORCE_REINSTALL=1"
) else (
    if defined APP_ARGS (
        set "APP_ARGS=!APP_ARGS! %1"
    ) else (
        set "APP_ARGS=%1"
    )
)
shift
goto parse_args
:args_done

echo ============================================================
echo   Facebook Group Batch Poster - Setup ^& Run (Windows)
echo ============================================================

REM 1. Detect uv and base Python
set "HAS_UV=0"
where uv >nul 2>&1
if %ERRORLEVEL%==0 set "HAS_UV=1"

set "BASE_PYTHON="
where python >nul 2>&1
if %ERRORLEVEL%==0 (
    set "BASE_PYTHON=python"
) else (
    where py >nul 2>&1
    if %ERRORLEVEL%==0 set "BASE_PYTHON=py -3"
)

if "%HAS_UV%"=="0" if "%BASE_PYTHON%"=="" (
    echo [ERROR] Neither 'python', 'py', nor 'uv' was found in PATH.
    echo Please install Python 3.10+ ^(https://www.python.org/^) and try again.
    exit /b 1
)

REM 2. Create virtual environment (.venv) if missing
if not exist ".venv" (
    echo [1/4] Creating virtual environment in .venv ...
    if "%HAS_UV%"=="1" (
        uv venv --seed .venv
    ) else (
        %BASE_PYTHON% -m venv .venv
    )
    if errorlevel 1 (
        echo [ERROR] Failed to create .venv.
        exit /b 1
    )
) else (
    echo [1/4] Virtual environment ^(.venv^) already exists.
)

set "VENV_PYTHON=.venv\Scripts\python.exe"
if not exist "%VENV_PYTHON%" (
    echo [ERROR] Could not locate %VENV_PYTHON%.
    exit /b 1
)

REM 3. Install or update Python dependencies when requirements.txt changes
set "HASH_FILE=.venv\.requirements.sha256"
set "NEED_INSTALL=0"
if "%FORCE_REINSTALL%"=="1" (
    set "NEED_INSTALL=1"
) else (
    "%VENV_PYTHON%" -c "import hashlib, pathlib; req=hashlib.sha256(pathlib.Path('requirements.txt').read_bytes()).hexdigest(); hf=pathlib.Path('.venv/.requirements.sha256'); raise SystemExit(0 if hf.exists() and hf.read_text(encoding='utf-8').strip()==req else 1)"
    if errorlevel 1 set "NEED_INSTALL=1"
)

if "%NEED_INSTALL%"=="1" (
    echo [2/4] Installing dependencies from requirements.txt ...
    if "%HAS_UV%"=="1" (
        uv pip install --python "%VENV_PYTHON%" -r requirements.txt
    ) else (
        "%VENV_PYTHON%" -m pip install --upgrade pip
        "%VENV_PYTHON%" -m pip install -r requirements.txt
    )
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies.
        exit /b 1
    )
    "%VENV_PYTHON%" -c "import hashlib, pathlib; pathlib.Path('.venv/.requirements.sha256').write_text(hashlib.sha256(pathlib.Path('requirements.txt').read_bytes()).hexdigest() + '\n', encoding='utf-8')"
) else (
    echo [2/4] Dependencies are up to date.
)

REM 4. Ensure Playwright Chromium browser is installed
set "PW_MARKER=.venv\.playwright_chromium_ready"
set "NEED_PW=0"
if "%FORCE_REINSTALL%"=="1" set "NEED_PW=1"
if not exist "%PW_MARKER%" set "NEED_PW=1"

if "%NEED_PW%"=="1" (
    echo [3/4] Installing/verifying Playwright Chromium browser ...
    "%VENV_PYTHON%" -m playwright install chromium
    if errorlevel 1 (
        echo [ERROR] Failed to install Playwright Chromium.
        exit /b 1
    )
    type nul > "%PW_MARKER%"
) else (
    echo [3/4] Playwright Chromium browser already verified.
)

REM 5. Bootstrap default configuration files if missing
echo [4/4] Checking configuration files ...
if not exist ".env" if exist ".env.example" (
    copy /Y ".env.example" ".env" >nul
    echo   -^> Created .env from .env.example
)
if not exist "groups.txt" if exist "groups.txt.example" (
    copy /Y "groups.txt.example" "groups.txt" >nul
    echo   -^> Created groups.txt from groups.txt.example
)
if not exist "post_data" if exist "post_content.txt.example" (
    mkdir "post_data"
    copy /Y "post_content.txt.example" "post_data\post_content.txt" >nul
    echo   -^> Created post_data\post_content.txt from post_content.txt.example
)

echo Setup complete.

if "%SETUP_ONLY%"=="1" (
    echo Setup-only mode requested. Exiting without launching the application.
    exit /b 0
)

echo Launching Facebook Group Batch Poster ...
if defined APP_ARGS (
    "%VENV_PYTHON%" main.py %APP_ARGS%
) else (
    "%VENV_PYTHON%" main.py
)

exit /b %ERRORLEVEL%
