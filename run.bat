@echo off
REM ============================================================
REM  Study Python for Finance - Windows startup wrapper
REM
REM  Prerequisites:
REM    - Python 3.13+ (managed by uv)
REM    - uv 0.11.6+ (https://docs.astral.sh/uv/)
REM
REM  For proxy environments, add the following to .env (uncomment):
REM    HTTPS_PROXY=http://proxy.example.com:8080
REM    HTTP_PROXY=http://proxy.example.com:8080
REM    NO_PROXY=localhost,127.0.0.1
REM
REM  For first time / repair: run setup.bat instead.
REM ============================================================

setlocal EnableDelayedExpansion

REM UTF-8 console + UNC-safe directory change. See setup.bat for details.
chcp 65001 >nul
pushd "%~dp0" 2>nul
if errorlevel 1 (
    echo [ERROR] Could not enter the script directory:
    echo   %~dp0
    echo Make sure the share is accessible and you have read permission.
    pause
    exit /b 1
)

REM Required env vars for Japanese Windows + OneDrive
REM   PYTHONIOENCODING / PYTHONUTF8: avoid UnicodeEncodeError when
REM     the startup banner em-dash is emitted to a cp932 console.
REM   UV_LINK_MODE=copy: OneDrive paths do not support hardlinks.
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
set "UV_LINK_MODE=copy"

REM Security: only use Python interpreters already installed on this
REM machine; never let uv download CPython from python-build-standalone
REM (Astral's GitHub-hosted prebuilt binaries). See setup.bat for the
REM matching pre-flight check that fails fast if Python 3.13+ is missing.
set "UV_PYTHON_DOWNLOADS=never"
set "UV_PYTHON_PREFERENCE=only-system"

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
            if /i "!key!"=="STUDYPY_DATA_DIR"       set "STUDYPY_DATA_DIR=!val!"
        )
    )
)

REM Auto-fallback: put the per-user .venv on local disk by default.
REM See setup.bat for the rationale. Must run AFTER the .env read so the
REM user-supplied value takes precedence.
if not defined UV_PROJECT_ENVIRONMENT (
    set "UV_PROJECT_ENVIRONMENT=%LOCALAPPDATA%\studypy\venv"
)
for %%P in ("!UV_PROJECT_ENVIRONMENT!") do set "_VENV_PARENT=%%~dpP"
if not exist "!_VENV_PARENT!" mkdir "!_VENV_PARENT!" 2>nul

REM Per-user data dir (progress.json, logs). For a single-user install
REM with an existing progress.json in the project tree, Python's
REM _resolve_data_dir() keeps that location for back-compat; otherwise
REM it falls back to %LOCALAPPDATA%\studypy. Set explicitly here only if
REM you need every instance on this machine to share or split state.
REM (Empty default - let Python pick the right path.)

if defined HTTPS_PROXY            echo [proxy] HTTPS_PROXY=!HTTPS_PROXY!
if defined HTTP_PROXY             echo [proxy] HTTP_PROXY=!HTTP_PROXY!
if defined NO_PROXY               echo [proxy] NO_PROXY=!NO_PROXY!
if defined UV_CACHE_DIR           echo [uv]    cache  = !UV_CACHE_DIR!
if defined STUDYPY_DATA_DIR       echo [data]  dir    = !STUDYPY_DATA_DIR!
echo [uv]    venv   = !UV_PROJECT_ENVIRONMENT!

REM Check uv
where uv >nul 2>nul
if errorlevel 1 (
    echo.
    echo [ERROR] uv command not found in PATH.
    echo   Install via PowerShell:
    echo     powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 ^| iex"
    echo   Or: winget install astral-sh.uv
    echo.
    pause
    exit /b 1
)

REM Check Python 3.13+ is installed (we disabled uv's automatic downloads).
set "_PY313_OK="
py -3.13 --version >nul 2>nul && set "_PY313_OK=1"
if not defined _PY313_OK (
    where python >nul 2>nul && (
        python --version 2>nul | findstr /b /r "Python 3\.1[3-9]" >nul && set "_PY313_OK=1"
    )
)
if not defined _PY313_OK (
    echo.
    echo [ERROR] Python 3.13+ not detected on this system.
    echo   uv's automatic Python downloads are disabled for security.
    echo   Install with one of:
    echo     winget install Python.Python.3.13
    echo     https://www.python.org/downloads/
    echo   Then run setup.bat ^(first time^) or this script again.
    echo.
    pause
    exit /b 1
)

REM Dependency sync (fast no-op if already up to date)
REM   --python 3.13 forces uv to use Python 3.13; required because earlier
REM   versions fail to read .pth files containing non-ASCII paths on
REM   Japanese Windows (locale encoding fallback to cp932).
echo.
echo [1/2] Checking dependencies...
echo       First run downloads 1.5-2 GB (PyTorch / Playwright).
echo.
uv sync --python 3.13 --link-mode=copy --extra deep --extra automation
if errorlevel 1 (
    echo.
    echo [ERROR] uv sync failed.
    echo   - Check internet connection.
    echo   - For proxy environments, configure HTTPS_PROXY in .env
    echo   - If .venv is corrupted, run setup.bat to rebuild clean.
    echo.
    pause
    exit /b 1
)

REM Launch the app
echo.
echo [2/2] Starting Study Python for Finance...
echo.
uv run python -m app.main
if errorlevel 1 (
    echo.
    echo [ERROR] App startup failed. Check logs\app.log for details.
    pause
    exit /b 1
)

popd
endlocal
