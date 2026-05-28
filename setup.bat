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

REM Switch the console to UTF-8 so any non-ASCII path the user runs us
REM under (e.g. a shared folder named in Japanese) renders correctly in
REM both our own echo lines and in subprocess output from uv / Python.
REM This file itself is pure ASCII, so changing the codepage cannot
REM break batch parsing.
chcp 65001 >nul

REM `pushd` (not `cd /d`) so the script also works when launched from a
REM UNC path such as \\fileserver\share\study_python_finance. cmd refuses
REM to set the cwd to a UNC string with `cd`; pushd transparently maps it
REM to a temporary drive letter.
pushd "%~dp0" 2>nul
if errorlevel 1 (
    echo [ERROR] Could not enter the script directory:
    echo   %~dp0
    echo Make sure the share is accessible and you have read permission.
    pause
    exit /b 1
)

REM Required env vars for Japanese Windows + OneDrive
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
set "UV_LINK_MODE=copy"

REM Security: do NOT let uv download CPython from python-build-standalone
REM (Astral's GitHub-hosted prebuilt interpreters). Restrict to Python
REM installations already present on this system (PATH / py launcher /
REM Windows registry under PEP 514). The user must install Python 3.13
REM themselves via winget / the official python.org installer.
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
            if /i "!key!"=="UV_CACHE_SEED_DIR"      set "UV_CACHE_SEED_DIR=!val!"
            if /i "!key!"=="UV_PROJECT_ENVIRONMENT" set "UV_PROJECT_ENVIRONMENT=!val!"
            if /i "!key!"=="STUDYPY_DATA_DIR"       set "STUDYPY_DATA_DIR=!val!"
        )
    )
)

REM ---- Shared-cache bootstrap ---------------------------------------
REM Setting UV_CACHE_DIR to a shared / read-only drive does NOT work:
REM uv still needs to write build artefacts there (e.g. building
REM pytweening from sdist), and the second user gets PermissionError.
REM
REM Instead, the *admin* runs setup.bat normally on a writable machine,
REM then copies their %LOCALAPPDATA%\uv\cache to a shared location.
REM Each subsequent user sets UV_CACHE_SEED_DIR in .env pointing at that
REM copy. On first run we mirror the seed -> the user's LOCAL cache once
REM with robocopy and run uv sync entirely against that local copy.
REM After bootstrap, no further reads or writes against the shared seed.
if defined UV_CACHE_SEED_DIR (
    REM Resolve the per-user uv cache. If the user pinned UV_CACHE_DIR
    REM in .env, honour it; otherwise use uv's documented default.
    if defined UV_CACHE_DIR (
        set "_LOCAL_CACHE=!UV_CACHE_DIR!"
    ) else (
        set "_LOCAL_CACHE=%LOCALAPPDATA%\uv\cache"
    )
    if exist "!UV_CACHE_SEED_DIR!\archive-v0" (
        if not exist "!_LOCAL_CACHE!\archive-v0" (
            echo.
            echo [seed] Bootstrapping local uv cache from shared seed:
            echo        src ^= !UV_CACHE_SEED_DIR!
            echo        dst ^= !_LOCAL_CACHE!
            echo        This one-time copy is ~1.5-2 GB and may take 5-15 minutes.
            if not exist "!_LOCAL_CACHE!" mkdir "!_LOCAL_CACHE!" >nul 2>&1
            REM /E    : include empty subdirectories
            REM /XD   : skip per-machine state (environments-v2) and in-progress
            REM         build temps (builds-v0) which are not portable.
            REM /R:1 /W:1 : retry once with 1s wait on transient I/O hiccups.
            REM /NFL /NDL /NJH /NJS /NC /NS /NP : quiet output.
            robocopy "!UV_CACHE_SEED_DIR!" "!_LOCAL_CACHE!" /E /XD environments-v2 builds-v0 /R:1 /W:1 /NFL /NDL /NJH /NJS /NC /NS /NP
            REM robocopy exit codes 0-7 are success ^(0 = no copy, 1 = copies,
            REM 2 = extras, up to 7 combinations^); 8+ are real errors.
            if errorlevel 8 (
                echo [WARN] Seed copy reported errors. uv sync may need to
                echo        fall back to PyPI for some packages.
            ) else (
                echo [seed] Local cache populated. Subsequent runs are offline-ready.
            )
        ) else (
            echo [seed] Local uv cache already present at !_LOCAL_CACHE! - skipping copy.
        )
    ) else (
        echo [seed] UV_CACHE_SEED_DIR is set but ^"!UV_CACHE_SEED_DIR!\archive-v0^" was not found.
        echo        Skipping bootstrap; uv will fetch from PyPI as usual.
    )
)

REM Auto-fallback: put the per-user .venv on local disk by default.
REM This is critical when the project tree itself lives on OneDrive or a
REM shared/network drive: a .venv co-located with the project breaks for
REM three reasons - hardlink unsupported (slow copy), cross-user
REM hardcoded paths (cannot be shared), and per-Python-version native
REM extensions (every user needs their own anyway).
if not defined UV_PROJECT_ENVIRONMENT (
    set "UV_PROJECT_ENVIRONMENT=%LOCALAPPDATA%\studypy\venv"
)
REM Ensure the parent directory exists so uv can create the venv leaf.
for %%P in ("!UV_PROJECT_ENVIRONMENT!") do set "_VENV_PARENT=%%~dpP"
if not exist "!_VENV_PARENT!" mkdir "!_VENV_PARENT!" 2>nul

echo.
echo ============================================================
echo  Study Python for Finance - Setup / Repair
echo ============================================================
echo  venv  : !UV_PROJECT_ENVIRONMENT!
if defined UV_CACHE_DIR (echo  cache : !UV_CACHE_DIR!) else (echo  cache : ^(uv default: %%LOCALAPPDATA%%\uv\cache^))
if defined STUDYPY_DATA_DIR (echo  data  : !STUDYPY_DATA_DIR!) else (echo  data  : ^(auto: project root or %%LOCALAPPDATA%%\studypy^))
echo ============================================================
echo.

REM Step 0a: Check uv
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

REM Step 0b: Check Python 3.11+ is installed. We disabled uv's automatic
REM Python downloads above, so we must verify the interpreter is on disk
REM ourselves and give the user a precise error if not.
REM
REM Python 3.11 is the minimum because pyproject.toml's requires-python.
REM Older Python (3.11 / 3.12) used to fail when the project lived on a
REM Japanese path because site.py read .pth files with the cp932 locale
REM codec; we sidestep that by passing --no-install-project to uv (no
REM project-specific .pth is created), so 3.11 is back on the menu.
set "_PY_OK="
for %%V in (3.11 3.12 3.13 3.14) do (
    if not defined _PY_OK (
        py -%%V --version >nul 2>nul && set "_PY_OK=1"
    )
)
if not defined _PY_OK (
    where python >nul 2>nul && (
        python --version 2>nul | findstr /b /r "Python 3\.1[1-9]" >nul && set "_PY_OK=1"
    )
)
if not defined _PY_OK (
    echo [ERROR] Python 3.11+ not detected on this system.
    echo   uv's automatic Python downloads are intentionally disabled for
    echo   security ^(UV_PYTHON_DOWNLOADS=never^), so Python must be
    echo   installed locally first.
    echo.
    echo   Install via one of:
    echo     winget install Python.Python.3.11
    echo     winget install Python.Python.3.13   ^(latest^)
    echo     https://www.python.org/downloads/   ^(official installer^)
    echo.
    echo   After installing, re-run this script.
    pause
    exit /b 1
)

REM Step 1: Remove existing venv (both the per-user path and any legacy
REM in-project .venv left over from older setups).
if exist "!UV_PROJECT_ENVIRONMENT!" (
    echo [1/3] Removing existing venv at !UV_PROJECT_ENVIRONMENT! ...
    rmdir /s /q "!UV_PROJECT_ENVIRONMENT!"
    if exist "!UV_PROJECT_ENVIRONMENT!" (
        echo.
        echo [ERROR] Failed to remove venv.
        echo   - Another process ^(VS Code, editor, running app^) may be locking files.
        echo   - If on shared / cloud storage, wait for sync and retry.
        echo.
        pause
        exit /b 1
    )
) else (
    echo [1/3] No existing venv at the target path. Skipping removal.
)
REM Also clean up a stray in-project .venv from previous installs.
if exist ".venv" (
    echo       Removing legacy in-project .venv ...
    rmdir /s /q ".venv" 2>nul
)

REM Step 2: Recreate .venv (using any available Python 3.11+) and install
REM dependencies.
REM
REM --no-install-project: do NOT install the project itself into the
REM   venv as an editable install. Without this, uv creates a
REM   _editable_impl_*.pth file that records the project path; when that
REM   path contains Japanese characters (shared drive, etc.) Python
REM   3.11 / 3.12's site.py blows up trying to decode it as cp932.
REM   Skipping the editable install makes Python 3.11 work everywhere.
REM   We invoke the app via `uv run python -m app.main` from the project
REM   dir (run.bat does `pushd %~dp0`), so cwd is on sys.path and the
REM   `app` package imports fine without an explicit install.
echo.
echo [2/3] Creating venv and installing dependencies...
echo       First run downloads 1.5-2 GB ^(PyTorch / Playwright^).
echo       This may take 5-15 minutes.
echo.
uv sync --link-mode=copy --no-install-project --extra deep --extra automation --extra dev
if errorlevel 1 (
    echo.
    echo [ERROR] uv sync failed.
    echo   - Check internet connection.
    echo   - For proxy environments, configure HTTPS_PROXY in .env
    echo.
    pause
    exit /b 1
)

REM Belt-and-suspenders: even with --no-install-project, an older uv
REM version or a lingering install from a previous setup pattern may
REM leave a project-specific .pth in the venv. Python 3.11 / 3.12's
REM frozen site.py reads .pth files with the cp932 locale codec
REM REGARDLESS of -X utf8 / PYTHONUTF8 (the encoding="locale" call in
REM site.py runs from C before the UTF-8-mode plumbing is fully wired
REM up for frozen modules), so a single .pth carrying a Japanese path
REM stops the interpreter from starting at all.
REM
REM Force-remove all known editable-install .pth file names for this
REM project. uv re-installs only what's in the lockfile on the next
REM sync, so this is purely a cleanup against stale state.
set "_SITE_PACKAGES=!UV_PROJECT_ENVIRONMENT!\Lib\site-packages"
if exist "!_SITE_PACKAGES!" (
    for %%P in (
        "_editable_impl_study_python_finance.pth"
        "__editable__.study_python_finance.pth"
        "__editable___study_python_finance_0_1_0_finder.py"
        "study-python-finance.pth"
        "study_python_finance.pth"
        "easy-install.pth"
    ) do (
        if exist "!_SITE_PACKAGES!\%%~P" (
            echo       Removing stale install artefact: %%~P
            del /q "!_SITE_PACKAGES!\%%~P" 2>nul
        )
    )
)

REM Step 3: Playwright browser detection (chapters 31 / 32).
REM Chapter samples now use `chromium.launch(channel="chrome")` so they
REM drive the system-installed Google Chrome directly. No download is
REM needed when Chrome is already on the machine. If Chrome is missing
REM we just warn -- the rest of the curriculum is fully usable, and
REM students who want to run the Playwright demos can install Chrome
REM from https://www.google.com/chrome/ afterwards.
echo.
echo [3/3] Checking for Google Chrome ^(used by chapter 31 / 32 examples^)...
set "_CHROME_FOUND="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "_CHROME_FOUND=1"
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "_CHROME_FOUND=1"
if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" set "_CHROME_FOUND=1"
if defined _CHROME_FOUND (
    echo       OK: system Chrome detected. Playwright will use it via
    echo           channel="chrome" -- no extra download required.
) else (
    echo       INFO: Google Chrome was not found in the usual locations.
    echo             Chapters 31 / 32 ^(Playwright examples^) will not run
    echo             until Chrome is installed. The rest of the app works
    echo             without it.
    echo             Install from: https://www.google.com/chrome/
    echo             Or: winget install Google.Chrome
)

echo.
echo ============================================================
echo  Setup complete.
echo ============================================================
echo  To launch the app, double-click run.bat
echo ============================================================
echo.
pause

popd
endlocal
