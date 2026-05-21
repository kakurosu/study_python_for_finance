@echo off
REM ============================================================
REM  Study Python for Finance — Windows startup wrapper
REM
REM  事前要件:
REM    - Python 3.11 以上
REM    - uv (https://docs.astral.sh/uv/)
REM
REM  Proxy 環境の場合は .env に下記のいずれかを書き、行頭の # を外す:
REM    HTTPS_PROXY=http://proxy.example.com:8080
REM    HTTP_PROXY=http://proxy.example.com:8080
REM    NO_PROXY=localhost,127.0.0.1
REM  不要になったら # を戻すか、行ごと削除すれば通常モードに戻ります。
REM ============================================================

setlocal EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"

REM --- 1) .env から起動に必要な変数だけ先行読込 -----------------
REM     eol=# でコメント行をスキップ、key=value 形式をパース。
REM     対応キー:
REM       HTTPS_PROXY / HTTP_PROXY / NO_PROXY     ... proxy 設定
REM       UV_CACHE_DIR                              ... uv のキャッシュ場所
REM                                                     (共有フォルダを指せば「誰かが
REM                                                      取得済みのパッケージを再利用」可能)
REM       UV_PROJECT_ENVIRONMENT                    ... .venv の場所（個別ユーザーで分けたい時）
if exist ".env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
        set "key=%%A"
        set "val=%%B"
        if defined val (
            REM 末尾の CR / 空白を除去（Windows 行末対策）
            for /f "tokens=* delims= " %%X in ("!val!") do set "val=%%X"
            if /i "!key!"=="HTTPS_PROXY"            set "HTTPS_PROXY=!val!"
            if /i "!key!"=="HTTP_PROXY"             set "HTTP_PROXY=!val!"
            if /i "!key!"=="NO_PROXY"               set "NO_PROXY=!val!"
            if /i "!key!"=="UV_CACHE_DIR"           set "UV_CACHE_DIR=!val!"
            if /i "!key!"=="UV_PROJECT_ENVIRONMENT" set "UV_PROJECT_ENVIRONMENT=!val!"
        )
    )
)

if defined HTTPS_PROXY            echo [proxy] HTTPS_PROXY=!HTTPS_PROXY!
if defined HTTP_PROXY             echo [proxy] HTTP_PROXY=!HTTP_PROXY!
if defined NO_PROXY               echo [proxy] NO_PROXY=!NO_PROXY!
if defined UV_CACHE_DIR           echo [uv]    cache  = !UV_CACHE_DIR!
if defined UV_PROJECT_ENVIRONMENT echo [uv]    .venv  = !UV_PROJECT_ENVIRONMENT!

REM --- 2) uv が PATH 上にあるか確認 ---------------------------
where uv >nul 2>nul
if errorlevel 1 (
    echo.
    echo [エラー] uv コマンドが見つかりません。
    echo   公式インストール手順: https://docs.astral.sh/uv/
    echo   PowerShell で次を実行してください:
    echo     powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 ^| iex"
    echo.
    pause
    exit /b 1
)

REM --- 3) 依存同期 (全 extras) --------------------------------
echo.
echo [1/2] 依存関係を確認しています...
echo       初回起動時は数分〜十数分かかります（PyTorch / Playwright を含む 1.5-2 GB）。
echo.
uv sync --extra deep --extra automation
if errorlevel 1 (
    echo.
    echo [エラー] uv sync に失敗しました。
    echo   - インターネット接続を確認してください。
    echo   - Proxy 経由の環境では .env に HTTPS_PROXY を設定してください
    echo     ^(.env.example を .env にコピーして編集^)。
    echo.
    pause
    exit /b 1
)

REM --- 4) アプリ起動 ------------------------------------------
echo.
echo [2/2] Study Python for Finance を起動します...
echo.
uv run python -m app.main
if errorlevel 1 (
    echo.
    echo [エラー] アプリの起動に失敗しました。logs\app.log を確認してください。
    pause
    exit /b 1
)

endlocal
