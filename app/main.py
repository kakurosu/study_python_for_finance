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
import signal
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
from .llm.claude_client import ClaudeClient
from .server import ServerContext, create_app

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = PROJECT_ROOT / "content" / "chapters"
TESTS_DIR = PROJECT_ROOT / "content" / "tests"
DB_PATH = PROJECT_ROOT / "progress.db"
LOG_DIR = PROJECT_ROOT / "logs"


def _configure_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        LOG_DIR / "app.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    handler.setFormatter(fmt)
    logging.basicConfig(level=logging.INFO, handlers=[handler])


def _pick_free_port(preferred: int) -> int:
    """Return ``preferred`` if it's free; otherwise pick any free port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _print_banner(url: str) -> None:
    bar = "─" * 60
    print()
    print(f"  ┌{bar}┐")
    print("  │  Study.Py — Finance Edition                              │")
    print(f"  │  {url:<56}│")
    print(f"  └{bar}┘")
    print()
    print("  Ctrl+C で停止します。ブラウザでこの URL を開いてください。")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(prog="study-python")
    parser.add_argument("--host", default="127.0.0.1", help="listen address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="port (default: 8765; 0 = pick free port)")
    parser.add_argument("--no-browser", action="store_true", help="don't open the system browser")
    args = parser.parse_args()

    _configure_logging()

    # Best-effort: pick up .env so ANTHROPIC_API_KEY is set.
    try:
        from dotenv import load_dotenv

        load_dotenv(PROJECT_ROOT / ".env")
    except ImportError:
        pass

    # ----- Load domain data -----
    repo = Repository(DB_PATH)
    user = repo.get_or_create_default_user()
    kernel = KernelSession()
    _llm = ClaudeClient()  # noqa: F841 — wired through the chapter flows later

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
    port = args.port if args.port == 0 else _pick_free_port(args.port)
    if args.port == 0:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]

    config = uvicorn.Config(
        app,
        host=args.host,
        port=port,
        log_level="warning",
        access_log=False,
        lifespan="on",
    )
    server = uvicorn.Server(config)

    url = f"http://{args.host}:{port}/"
    _print_banner(url)

    # ----- Open the browser after the server is ready -----
    def _open_browser() -> None:
        # Poll for the server being up; bail out after ~5s to avoid blocking.
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                with socket.create_connection((args.host, port), timeout=0.2):
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


def _install_sigint_handler() -> None:
    # Uvicorn already installs its own signal handlers, but a clean exit
    # on a second Ctrl+C is nice in case the kernel hangs.
    def _handler(signum, frame):  # noqa: ANN001
        sys.exit(0)

    with contextlib.suppress(Exception):
        signal.signal(signal.SIGINT, _handler)


if __name__ == "__main__":
    sys.exit(main())
