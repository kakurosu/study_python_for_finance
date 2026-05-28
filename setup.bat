@echo off
REM ============================================================
REM  Study Python for Finance - Setup / Repair script
REM
REM  Use cases:
REM    - First time installation
REM    - .venv is broken (UnicodeDecodeError on launch, etc.)
REM    - Switching Python version
REM    - Clean reinstall of all dependencies
REM
REM  Steps:
REM    1) Remove existing .venv
REM    2) Recreate .venv with Python 3.13 and install all extras
REM    3) Install Playwright browser binaries (optional)
REM
REM  For normal startup, use run.bat instead.
REM ============================================================

setlocal EnableDelayedExpansion
cd /d "%~dp0"

REM Required env vars for Japanese Windows + OneDrive
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
set "UV_LINK_MODE=copy"

REM Read .env for proxy / cache config
if exist ".env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
        set "key=%%A"
        set "val=%%B"
        if defined val (
            for /f "tokens=* delims= " %%X in ("!val!") do set "val=%%X"
            if /i "!key!"=="HTTPS_PROXY"            set "HTTPS_PROXY=!val!"
            if /i "!key!"=="HTTP_PROXY"             set "HTTP_PROXY=!val!"
            if /i "!key!"=="NO_PROXY"               set "NO_PROXY=!val!"
            if /i "!key!"=="UV_CACHE_DIR"           set "UV_CACHE_DIR=!val!"
            if /i "!key!"=="UV_PROJECT_ENVIRONMENT" set "UV_PROJECT_ENVIRONMENT=!val!"
        )
    )
)

echo.
echo ============================================================
echo  Study Python for Finance - Setup / Repair
echo ============================================================
echo.

REM Step 0: Check uv
where uv >nul 2>nul
if errorlevel 1 (
    echo [ERROR] uv command not found in PATH.
    echo   Install via PowerShell:
    echo     powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 ^| iex"
    echo   Or: winget install astral-sh.uv
    echo.
    pause
    exit /b 1
)

REM Step 1: Remove existing .venv
if exist ".venv" (
    echo [1/3] Removing existing .venv ...
    rmdir /s /q ".venv"
    if exist ".venv" (
        echo.
        echo [ERROR] Failed to remove .venv.
        echo   - Another process ^(VS Code, editor, running app^) may be locking files.
        echo   - If OneDrive is syncing, wait for it to finish and retry.
        echo.
        pause
        exit /b 1
    )
) else (
    echo [1/3] No existing .venv. Skipping removal.
)

REM Step 2: Recreate .venv with Python 3.13 and install dependencies
echo.
echo [2/3] Creating .venv with Python 3.13 and installing dependencies...
echo       First run downloads 1.5-2 GB ^(PyTorch / Playwright^).
echo       This may take 5-15 minutes.
echo.
uv sync --python 3.13 --link-mode=copy --extra deep --extra automation --extra dev
if errorlevel 1 (
    echo.
    echo [ERROR] uv sync failed.
    echo   - Check internet connection.
    echo   - For proxy environments, configure HTTPS_PROXY in .env
    echo.
    pause
    exit /b 1
)

REM Step 3: Playwright browser install (optional, used by chapter 26)
echo.
echo [3/3] Installing Playwright Chromium ^(for chapter 26, about 200MB^)...
echo       You can press Ctrl+C to skip; main features will still work.
echo.
uv run playwright install chromium
if errorlevel 1 (
    echo.
    echo [WARN] Playwright install failed, but core features are unaffected.
    echo        Run "uv run playwright install chromium" later if you need chapter 26.
    echo.
)

echo.
echo ============================================================
echo  Setup complete.
echo ============================================================
echo  To launch the app, double-click run.bat
echo ============================================================
echo.
pause

endlocal
