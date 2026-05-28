"""Application entrypoint.

Boots a local FastAPI server (``app.server``) that hosts the HTML/CSS/JS
UI under ``app/web/`` and exposes a tiny JSON API on top of the Jupyter
kernel + SQLite progress store. The user's default web browser is opened
to the loopback URL so no native UI toolkit (PyQt, Tk, …) is required.

Run with::

    uv run python -m app.main
    uv run study-python                 # equivalent (project.scripts)

Flags::

    --host 127.0.0.1   listen address (default: loopback only)
    --port 0           port (0 = pick a free one; default 8765)
    --no-browser       don't open the browser automatically
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
import socket
import sys
import threading
import time
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path

import uvicorn

from .content.loader import ContentError, load_chapters
from .content.test_schemas import load_test_sets
from .db.repo import Repository
from .kernel.manager import KernelSession
from .server import ServerContext, create_app

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = PROJECT_ROOT / "content" / "chapters"
TESTS_DIR = PROJECT_ROOT / "content" / "tests"


def _resolve_data_dir() -> Path:
    """Return the directory that holds per-user state (progress.json, logs/).

    Resolution order:

      1. ``STUDYPY_DATA_DIR`` env var (explicit override; required for
         classroom-scale deployments where many users share the project
         tree on a network drive).
      2. ``PROJECT_ROOT`` if ``progress.json`` already exists there —
         preserves the historical layout so single-user installs and
         existing checkouts keep their data without manual migration.
      3. ``%LOCALAPPDATA%\\studypy`` on Windows / ``~/.studypy`` elsewhere.
         This is the recommended default for fresh shared-drive installs:
         every user's writable state stays on their own machine, and the
         project tree itself can be mounted read-only.
    """
    env_val = os.environ.get("STUDYPY_DATA_DIR")
    if env_val:
        return Path(env_val).expanduser()
    if (PROJECT_ROOT / "progress.json").exists():
        return PROJECT_ROOT
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        return Path(base) / "studypy"
    return Path.home() / ".studypy"


DATA_DIR = _resolve_data_dir()
DB_PATH = DATA_DIR / "progress.json"
LOG_DIR = DATA_DIR / "logs"


def _configure_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    handler.setFormatter(fmt)
    logging.basicConfig(level=logging.INFO, handlers=[handler])


_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "0:0:0:0:0:0:0:1"}


def _is_loopback(host: str) -> bool:
    return host.lower() in _LOOPBACK_HOSTS


def _pick_free_port(host: str, preferred: int) -> int:
    """Return ``preferred`` if it's free on ``host``; otherwise pick any free port.

    Probes on the actual bind address so a --host 0.0.0.0 / --port 0 run picks
    a port that is free on every interface, not just on loopback.
    """
    if preferred:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, preferred))
                return preferred
            except OSError:
                pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def _display_host(bind_host: str) -> str:
    """Pick a host the browser can actually reach.

    Binding to 0.0.0.0 / :: makes the socket reachable on every interface, but
    those addresses are not valid destinations for the browser (Firefox /
    Safari refuse ``http://0.0.0.0/``). In that case we tell the user to
    connect to 127.0.0.1.
    """
    if bind_host in ("0.0.0.0", "::", ""):
        return "127.0.0.1"
    return bind_host


def _print_banner(url: str) -> None:
    bar = "─" * 60
    print()
    print(f"  ┌{bar}┐")
    print("  │  Study.Py — Finance Edition                              │")
    print(f"  │  {url:<56}│")
    print(f"  └{bar}┘")
    print()
    print("  ブラウザを閉じるか Ctrl+C で停止します。")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(prog="study-python")
    parser.add_argument("--host", default="127.0.0.1", help="listen address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="port (default: 8765; 0 = pick free port)")
    parser.add_argument("--no-browser", action="store_true", help="don't open the system browser")
    parser.add_argument(
        "--no-auto-shutdown",
        action="store_true",
        help=(
            "Keep the server running even after the last browser tab closes. "
            "By default, the server self-terminates 10s after every client disconnects "
            "so the launching cmd.exe window closes cleanly when the user closes their browser."
        ),
    )
    parser.add_argument(
        "--shutdown-grace",
        type=float,
        default=10.0,
        help="Seconds to wait after last client disconnect before shutting down (default: 10)",
    )
    parser.add_argument(
        "--insecure-lan",
        action="store_true",
        help=(
            "Allow binding to a non-loopback address (e.g. 0.0.0.0) WITHOUT authentication. "
            "The /api/run-code endpoint executes arbitrary Python — anyone on the same network "
            "can run code on this machine. Required acknowledgement flag for non-loopback hosts."
        ),
    )
    args = parser.parse_args()

    # Refuse non-loopback hosts unless the user has explicitly acknowledged the
    # consequences. The Jupyter kernel reachable through /api/run-code is a
    # trivial RCE primitive; we don't want a user to accidentally expose it on
    # a shared network by following a copy-paste from the README.
    if not _is_loopback(args.host) and not args.insecure_lan:
        print(
            f"[fatal] --host {args.host} は loopback ではありません。\n"
            "        このアプリは認証を行わず、/api/run-code 経由で任意の Python を\n"
            "        実行できるため、LAN/インターネットに公開すると同ネットワーク上の\n"
            "        誰でもこの端末でコード実行できる状態になります。\n"
            "        意図的にネットワーク公開する場合は --insecure-lan を追加してください。",
            file=sys.stderr,
        )
        return 2

    # Best-effort: pick up .env for proxy settings / OPENAI_API_KEY (used
    # in chapter 24's OpenAI SDK examples). Load this BEFORE re-resolving
    # the data dir so STUDYPY_DATA_DIR coming from .env (not just the
    # parent process env) is honoured.
    try:
        from dotenv import load_dotenv

        load_dotenv(PROJECT_ROOT / ".env")
    except ImportError:
        pass

    # Re-resolve the writable data location now that .env has been loaded.
    # The module-level DATA_DIR was computed at import time and may miss
    # values that only appear in .env when the launcher does not export
    # them up-front (the bundled run.bat / setup.bat both do, but a
    # bare `uv run python -m app.main` would not).
    data_dir = _resolve_data_dir()
    db_path = data_dir / "progress.json"
    log_dir = data_dir / "logs"

    _configure_logging(log_dir)

    # ----- Load domain data -----
    repo = Repository(db_path)
    user = repo.get_or_create_default_user()
    kernel = KernelSession()

    try:
        chapters = load_chapters(CONTENT_DIR)
    except ContentError as e:
        print(f"[fatal] 章ファイルの読み込みに失敗しました: {e}", file=sys.stderr)
        return 2
    try:
        test_sets = load_test_sets(TESTS_DIR)
    except Exception as e:  # noqa: BLE001
        logging.exception("test set load failed")
        print(f"[warn] テスト読み込み警告: {e}", file=sys.stderr)
        test_sets = {}
    if not chapters:
        print(f"[warn] {CONTENT_DIR} に章ファイル(YAML)が見つかりません。", file=sys.stderr)

    # ----- Build the FastAPI app -----
    ctx = ServerContext(chapters, repo, user.id, kernel, test_sets)
    app = create_app(ctx)

    # ----- Start the kernel in the background -----
    def _start_kernel() -> None:
        try:
            kernel.start()
            ctx.events.publish({"type": "kernel_state", "state": "ready"})
        except Exception:  # noqa: BLE001
            logging.exception("kernel start failed")
            ctx.events.publish({"type": "kernel_state", "state": "error"})

    threading.Thread(target=_start_kernel, name="kernel-bootstrap", daemon=True).start()

    # ----- Pick a port + spin up uvicorn -----
    port = _pick_free_port(args.host, args.port)

    config = uvicorn.Config(
        app,
        host=args.host,
        port=port,
        log_level="warning",
        access_log=False,
        lifespan="on",
    )
    server = uvicorn.Server(config)

    # Wire up auto-shutdown so closing the last browser tab terminates the
    # process. The grace period absorbs reloads and brief network blips.
    if not args.no_auto_shutdown:
        ctx.shutdown_grace_seconds = args.shutdown_grace

        def _request_shutdown() -> None:
            server.should_exit = True

        ctx.shutdown_callback = _request_shutdown

    display_host = _display_host(args.host)
    url = f"http://{display_host}:{port}/"
    _print_banner(url)

    # ----- Open the browser after the server is ready -----
    def _open_browser() -> None:
        # Poll for the server being up; bail out after ~5s to avoid blocking.
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                with socket.create_connection((display_host, port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
        with contextlib.suppress(Exception):
            webbrowser.open(url)

    if not args.no_browser and not os.environ.get("STUDYPY_NO_BROWSER"):
        threading.Thread(target=_open_browser, name="open-browser", daemon=True).start()

    # ----- Run server (blocks) -----
    try:
        server.run()
    except KeyboardInterrupt:
        pass
    finally:
        # Best-effort cleanup
        with contextlib.suppress(Exception):
            kernel.shutdown()
        with contextlib.suppress(Exception):
            # Streamlit subprocess (chapter 25) may have been launched
            # by chapter content; we don't import it here because that
            # module is on the deprecated PyQt path.
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
