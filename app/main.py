"""Application entrypoint.

By default boots the **Web shell** (`QWebEngineView` hosting `app/web/`)
which renders a Figma-quality HTML/CSS UI. Set the environment variable
``STUDYPY_LEGACY_UI=1`` to fall back to the legacy PyQt6/QSS shell.
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PyQt6.QtCore import Qt, QCoreApplication
# QtWebEngine must be imported before QApplication construction so its
# OpenGL contexts share correctly with the rest of the UI.
QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
import PyQt6.QtWebEngineWidgets  # noqa: F401  (side-effect: registers QtWebEngine)

from PyQt6.QtGui import QFontDatabase, QGuiApplication, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
    QWidget,
)

from .content.loader import ContentError, load_chapters
from .content.test_schemas import load_test_sets
from .db.models import ChapterStatus
from .db.repo import Repository
from .kernel.manager import KernelSession
from .llm.claude_client import ClaudeClient
from .resources.theme import GLOBAL_STYLESHEET
from .ui.chapter_view import ChapterView
from .ui.command_actions import Action, CommandRegistry
from .ui.command_palette import CommandPalette
from .ui.help_overlay import HelpOverlay
from .ui.history_view import HistoryView
from .ui.shell import AppShell
from .ui.test_view import TestView
from .ui.views.chapter_picker import ChapterPickerView
from .ui.views.dashboard import DashboardView
from .ui.views.placeholder import PlaceholderView

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = PROJECT_ROOT / "content" / "chapters"
TESTS_DIR = PROJECT_ROOT / "content" / "tests"
DB_PATH = PROJECT_ROOT / "progress.db"
LOG_DIR = PROJECT_ROOT / "logs"


def _configure_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(LOG_DIR / "app.log", maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    handler.setFormatter(fmt)
    logging.basicConfig(level=logging.INFO, handlers=[handler])


def _load_bundled_fonts() -> list[str]:
    """Register all .ttf / .otf files under app/resources/fonts/ with Qt.

    Returns the list of families that were successfully loaded. The QSS in
    ``theme.py`` references these families by name (Inter, JetBrains Mono,
    etc.); when the font isn't bundled the stack silently falls back to the
    OS default — no error.
    """
    fonts_dir = PROJECT_ROOT / "app" / "resources" / "fonts"
    if not fonts_dir.exists():
        return []
    loaded: list[str] = []
    for path in fonts_dir.iterdir():
        if path.suffix.lower() not in (".ttf", ".otf"):
            continue
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id < 0:
            logging.warning("could not load font: %s", path.name)
            continue
        families = QFontDatabase.applicationFontFamilies(font_id)
        loaded.extend(families)
        logging.info("loaded font %s → %s", path.name, families)
    return loaded


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Study Python for Finance")
        self.setMinimumSize(1200, 780)

        # Best-effort: load .env so ANTHROPIC_API_KEY is picked up if user set it.
        try:
            from dotenv import load_dotenv
            load_dotenv(PROJECT_ROOT / ".env")
        except ImportError:
            pass

        self.repo = Repository(DB_PATH)
        self.user = self.repo.get_or_create_default_user()
        self.kernel = KernelSession()
        self.llm = ClaudeClient()

        # Load chapters
        try:
            self.chapters = load_chapters(CONTENT_DIR)
        except ContentError as e:
            QMessageBox.critical(self, "章ファイルの読み込みに失敗しました", str(e))
            self.chapters = []

        # Load tests
        try:
            self.test_sets = load_test_sets(TESTS_DIR)
        except Exception as e:  # noqa: BLE001
            logging.exception("test set load failed")
            QMessageBox.warning(self, "テスト読み込みエラー", str(e))
            self.test_sets = {}

        if not self.chapters:
            QMessageBox.warning(
                self,
                "章がありません",
                f"{CONTENT_DIR} に章ファイル(YAML)が見つかりません。",
            )

        # ----- Build the shell -----
        self.shell = AppShell(self)
        self.setCentralWidget(self.shell)

        # Register sidebar nav items (icons are simple text glyphs)
        self.shell.sidebar.add_item("dashboard", "ダッシュボード", icon="▣", group="学習")
        self.shell.sidebar.add_item("chapters",   "章を学ぶ",      icon="□", group="学習")
        self.shell.sidebar.add_item("practice",   "練習問題",       icon="◇", group="学習")
        self.shell.sidebar.add_item("tests",      "実力テスト",     icon="✓", group="学習")
        self.shell.sidebar.add_item("history",    "学習履歴",       icon="≡", group="学習")
        self.shell.sidebar.add_item("references", "リファレンス",   icon="✎", group="補助")
        self.shell.sidebar.add_item("settings",   "設定",           icon="⚙", group="補助")
        self.shell.sidebar.add_stretch()
        self.shell.sidebar.activated.connect(self._on_nav)

        # Build views
        self.dashboard = DashboardView(self.chapters, self.repo, self.user.id)
        self.dashboard.resume_requested.connect(self._on_resume)
        self.dashboard.browse_chapters_requested.connect(
            lambda: self._navigate_to("chapters")
        )
        self.dashboard.test_requested.connect(self._open_test)
        self.dashboard.history_requested.connect(lambda: self._navigate_to("history"))
        self.shell.add_view("dashboard", self.dashboard)

        self.picker = ChapterPickerView(self.chapters, self.repo, self.user.id)
        self.picker.chapter_selected.connect(self._open_chapter)
        self.shell.add_view("chapters", self.picker)

        self.shell.add_view(
            "practice",
            PlaceholderView("練習問題", "Phase 横断の総合練習をまとめた画面。"),
        )

        # Tests entry view is also a placeholder list (legacy LauncherScreen
        # had no dedicated picker UI yet) — wrap the test set picker as a
        # minimal placeholder for now.
        tests_view = _TestPickerStub(
            list(self.test_sets.values()),
            on_pick=self._open_test,
        )
        self.shell.add_view("tests", tests_view)

        self.history_view = HistoryView(self.repo, self.user.id)
        self.history_view.back_to_launcher.connect(
            lambda: self._navigate_to("dashboard")
        )
        self.shell.add_view("history", self.history_view)

        self.shell.add_view(
            "references",
            PlaceholderView("リファレンス", "標準ライブラリと主要パッケージの早見表。"),
        )
        self.shell.add_view(
            "settings",
            PlaceholderView("設定", "テーマ・ショートカット・API キーなどを変更できます。"),
        )

        # Chapter view is created on demand
        self._chapter_view: ChapterView | None = None
        self._test_view: TestView | None = None

        # Default to dashboard
        self.shell.show_view("dashboard")
        self.shell.topbar.set_breadcrumb("Dashboard")

        # Update sidebar mini progress card
        self._refresh_mini_progress()

        # Command palette + help overlay (Ctrl+K / Ctrl+B / ?)
        self._cmd_registry = CommandRegistry()
        self._palette: CommandPalette | None = None
        self._help_overlay: HelpOverlay | None = None
        self._register_default_actions()
        self._install_shortcuts()

        # Hook the topbar "search" button (added in shell.py) to open palette
        if hasattr(self.shell.topbar, "set_palette_handler"):
            self.shell.topbar.set_palette_handler(self._open_command_palette)
        if hasattr(self.shell.sidebar, "set_palette_handler"):
            self.shell.sidebar.set_palette_handler(self._open_command_palette)

        # Start kernel asynchronously-ish (blocking but quick).
        try:
            self.kernel.start()
            self.shell.statusbar.set_kernel_state("ready")
            self.shell.topbar.set_kernel_state("ready")
        except Exception as e:  # noqa: BLE001
            logging.exception("kernel start failed")
            QMessageBox.critical(
                self,
                "カーネル起動エラー",
                f"Jupyter kernel を起動できませんでした:\n{e}",
            )
            self.shell.statusbar.set_kernel_state("error", str(e)[:40])
            self.shell.topbar.set_kernel_state("error")

    # ------------------------------------------------------------------
    def _navigate_to(self, slug: str) -> None:
        """Switch sidebar to ``slug`` and refresh breadcrumb."""
        crumbs = {
            "dashboard":  ("Dashboard",),
            "chapters":   ("Chapters",),
            "practice":   ("Practice",),
            "tests":      ("Tests",),
            "history":    ("History",),
            "references": ("References",),
            "settings":   ("Settings",),
        }
        self.shell.show_view(slug)
        self.shell.topbar.set_breadcrumb(*crumbs.get(slug, ("Dashboard",)))
        if slug == "chapters":
            self.picker.refresh()
        if slug == "history":
            # Rebuild so the latest test scores appear.
            # HistoryView is cheap; replace in place.
            new = HistoryView(self.repo, self.user.id)
            new.back_to_launcher.connect(lambda: self._navigate_to("dashboard"))
            self.shell.replace_view("history", new)
            self.history_view = new

    def _on_nav(self, slug: str) -> None:
        # If we're inside a chapter, leaving via sidebar should tear it down
        # and bring the TopBar back (it was hidden while the chapter was open).
        if self._chapter_view is not None:
            self._tear_down_chapter()
            self.shell.topbar.setVisible(True)
        self._navigate_to(slug)

    def _on_resume(self) -> None:
        prog = self.repo.latest_in_progress(self.user.id)
        if prog is None:
            done = {p.chapter_id for p in self.repo.all_progress(self.user.id)
                    if p.status == ChapterStatus.completed}
            for ch in self.chapters:
                if ch.id not in done:
                    self._open_chapter(ch.id, 0)
                    return
            QMessageBox.information(self, "つづきから", "全章クリア済みです。")
            return
        self._open_chapter(prog.chapter_id, prog.last_page_index)

    def _open_chapter(self, chapter_id: int, start_page_index: int) -> None:
        ch = next((c for c in self.chapters if c.id == chapter_id), None)
        if ch is None:
            QMessageBox.warning(self, "章が見つかりません", f"chapter id={chapter_id}")
            return
        self.kernel.restart()
        view = ChapterView(
            ch,
            self.repo,
            self.user.id,
            self.kernel,
            start_page_index=start_page_index,
            llm=self.llm,
        )
        view.back_to_launcher.connect(self._return_from_chapter)
        # Replace the "chapter" slot in the shell with this ChapterView so the
        # sidebar / statusbar stay visible. The TopBar is hidden because the
        # chapter view's own header already carries Phase / Ch / Title — no
        # need to repeat it as a breadcrumb above.
        self.shell.replace_view("chapters", view)
        self._chapter_view = view
        self.shell.show_view("chapters")
        self.shell.topbar.setVisible(False)
        self.shell.sidebar.set_active("chapters")
        self._refresh_mini_progress(active_chapter=ch, page=start_page_index)

    def _tear_down_chapter(self) -> None:
        if self._chapter_view is None:
            return
        # Restore the chapter-picker view in the slot
        new_picker = ChapterPickerView(self.chapters, self.repo, self.user.id)
        new_picker.chapter_selected.connect(self._open_chapter)
        self.shell.replace_view("chapters", new_picker)
        self.picker = new_picker
        self._chapter_view = None

    def _return_from_chapter(self) -> None:
        self._tear_down_chapter()
        # Restore the TopBar that the chapter view had hidden.
        self.shell.topbar.setVisible(True)
        self._refresh_dashboard()
        self._navigate_to("dashboard")
        self._refresh_mini_progress()

    def _open_test(self, test_id: str) -> None:
        ts = self.test_sets.get(test_id)
        if ts is None:
            QMessageBox.information(
                self,
                "テストが見つかりません",
                f"`{test_id}` のテストはまだ用意されていません。",
            )
            return
        self.kernel.restart()
        view = TestView(ts, self.repo, self.user.id, self.kernel)
        view.back_to_launcher.connect(lambda: self._navigate_to("dashboard"))
        self.shell.replace_view("tests", view)
        self._test_view = view
        self.shell.show_view("tests")
        self.shell.topbar.set_breadcrumb("Tests", ts.title)
        self.shell.sidebar.set_active("tests")

    # ------------------------------------------------------------------
    def _refresh_dashboard(self) -> None:
        """Rebuild dashboard so progress / stats reflect the latest DB state."""
        new = DashboardView(self.chapters, self.repo, self.user.id)
        new.resume_requested.connect(self._on_resume)
        new.browse_chapters_requested.connect(lambda: self._navigate_to("chapters"))
        new.test_requested.connect(self._open_test)
        new.history_requested.connect(lambda: self._navigate_to("history"))
        self.shell.replace_view("dashboard", new)
        self.dashboard = new

    def _refresh_mini_progress(self, *, active_chapter=None, page: int | None = None) -> None:
        # Compute Phase A progress as the default mini bar
        all_progress = self.repo.all_progress(self.user.id)
        completed_ids = {p.chapter_id for p in all_progress if p.status == ChapterStatus.completed}
        phase = "A"
        if active_chapter is not None:
            phase = active_chapter.phase
        chs = [c for c in self.chapters if c.phase == phase]
        total = max(len(chs), 1)
        done = sum(1 for c in chs if c.id in completed_ids)
        pct = int(done / total * 100)
        label = f"Phase {phase} の進捗"
        if active_chapter is not None and page is not None:
            chap = f"Ch {active_chapter.id:02d} · p{page + 1}/{len(active_chapter.pages)}"
        else:
            latest = self.repo.latest_in_progress(self.user.id)
            if latest is not None:
                c = next((c for c in self.chapters if c.id == latest.chapter_id), None)
                chap = f"Ch {c.id:02d} 「{c.title[:14]}」" if c else "—"
            else:
                chap = "新しい章から始めよう"
        self.shell.sidebar.set_mini_progress(label, pct, chap)

    # ------------------------------------------------------------------
    # Command palette / shortcuts
    # ------------------------------------------------------------------
    def _install_shortcuts(self) -> None:
        self._sc_palette = QShortcut(QKeySequence("Ctrl+K"), self)
        self._sc_palette.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._sc_palette.activated.connect(self._open_command_palette)

        self._sc_sidebar = QShortcut(QKeySequence("Ctrl+B"), self)
        self._sc_sidebar.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._sc_sidebar.activated.connect(self._toggle_sidebar)

        self._sc_help = QShortcut(QKeySequence("?"), self)
        self._sc_help.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._sc_help.activated.connect(self._show_help_overlay)

        # Numeric quick-nav (Ctrl+1〜5)
        nav_keys = [
            ("Ctrl+1", "dashboard"),
            ("Ctrl+2", "chapters"),
            ("Ctrl+3", "practice"),
            ("Ctrl+4", "tests"),
            ("Ctrl+5", "history"),
        ]
        self._sc_nav: list[QShortcut] = []
        for seq, slug in nav_keys:
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(lambda _slug=slug: self._on_nav(_slug))
            self._sc_nav.append(sc)

    def _toggle_sidebar(self) -> None:
        sb = self.shell.sidebar
        sb.setVisible(not sb.isVisible())

    def _open_command_palette(self) -> None:
        # Rebuild dynamic chapter actions each time the palette opens so the
        # progress flags stay accurate.
        self._refresh_chapter_actions()
        if self._palette is None:
            self._palette = CommandPalette(self._cmd_registry, self)
        self._palette.show()
        self._palette.raise_()
        self._palette.activateWindow()

    def _show_help_overlay(self) -> None:
        if self._help_overlay is None:
            self._help_overlay = HelpOverlay(self)
        self._help_overlay.show()
        self._help_overlay.raise_()
        self._help_overlay.activateWindow()

    def _register_default_actions(self) -> None:
        nav = [
            ("nav.dashboard", "ダッシュボードを開く", "▣", "Continue & 進捗",
             ("Ctrl", "1"), ("dashboard","ホーム","home")),
            ("nav.chapters",  "章一覧を開く",          "□", "Phase A〜F",
             ("Ctrl", "2"), ("chapters","章","browse")),
            ("nav.practice",  "練習問題を開く",        "◇", "Phase 横断",
             ("Ctrl", "3"), ("practice","練習")),
            ("nav.tests",     "実力テストを受ける",    "✓", "Phase 別 10 問",
             ("Ctrl", "4"), ("tests","テスト","quiz")),
            ("nav.history",   "学習履歴を見る",        "≡", "過去のスコア",
             ("Ctrl", "5"), ("history","履歴","log")),
            ("nav.references","リファレンスを開く",    "✎", "標準ライブラリ早見",
             None, ("references","ref","help")),
            ("nav.settings",  "設定を開く",            "⚙", "テーマ・API",
             None, ("settings","preferences")),
        ]
        for slug_id, title, icon, sub, sc, kws in nav:
            target = slug_id.removeprefix("nav.")
            self._cmd_registry.register(Action(
                id=slug_id,
                title=title,
                group="ナビゲート",
                icon=icon,
                subtitle=sub,
                shortcut=sc,
                keywords=kws,
                run=lambda s=target: self._on_nav(s),
            ))

        self._cmd_registry.register(Action(
            id="resume",
            title="つづきから再開",
            group="ナビゲート",
            icon="▶",
            subtitle="最後の章/ページから",
            shortcut=("Ctrl", "R"),
            keywords=("resume","continue","再開"),
            run=self._on_resume,
        ))

        # Help
        self._cmd_registry.register(Action(
            id="help.shortcuts",
            title="ショートカット一覧",
            group="ヘルプ",
            icon="?",
            subtitle="キーボード操作",
            shortcut=("?",),
            keywords=("help","shortcuts","ヘルプ"),
            run=self._show_help_overlay,
        ))
        self._cmd_registry.register(Action(
            id="ui.toggle_sidebar",
            title="サイドバーを切替",
            group="ヘルプ",
            icon="◧",
            subtitle="表示/非表示",
            shortcut=("Ctrl", "B"),
            keywords=("sidebar","toggle"),
            run=self._toggle_sidebar,
        ))

        # Tests (one action per available test set)
        for ts in self.test_sets.values():
            self._cmd_registry.register(Action(
                id=f"test.{ts.id}",
                title=f"テスト: {ts.title}",
                group="テスト",
                icon="✓",
                subtitle=f"Phase {ts.phase} · {len(ts.questions)} 問 · {ts.time_limit_minutes} 分",
                shortcut=None,
                keywords=(f"phase {ts.phase}", ts.id, "test"),
                run=lambda tid=ts.id: self._open_test(tid),
            ))

        # Chapters (dynamic)
        self._refresh_chapter_actions()

    def _refresh_chapter_actions(self) -> None:
        for ch in self.chapters:
            kws: tuple[str, ...] = (
                f"phase {ch.phase}",
                f"ch{ch.id:02d}",
                str(ch.id),
                ch.title,
            )
            self._cmd_registry.register(Action(
                id=f"chapter.{ch.id}",
                title=f"第 {ch.id:02d} 章 {ch.title}",
                group="章",
                icon="❯",
                subtitle=f"Phase {ch.phase}",
                shortcut=None,
                keywords=kws,
                run=lambda cid=ch.id: self._open_chapter(cid, 0),
            ))

    def closeEvent(self, e) -> None:  # noqa: N802
        try:
            self.kernel.shutdown()
        except Exception:  # noqa: BLE001
            logging.exception("kernel shutdown failed")
        # Make sure any Streamlit subprocess launched from chapter 25 dies
        # with the main app — otherwise it keeps listening on port 8501.
        try:
            from .ui.pages.sample_page import StreamlitLauncher
            StreamlitLauncher.terminate()
        except Exception:  # noqa: BLE001
            logging.exception("streamlit shutdown failed")
        super().closeEvent(e)


# ---------------------------------------------------------------------------
# Lightweight test picker placeholder (real picker is the legacy LauncherScreen)
# ---------------------------------------------------------------------------


class _TestPickerStub(QWidget):
    """Minimal Tests sidebar view — a list of available test sets."""

    def __init__(self, test_sets, on_pick, parent=None):
        from PyQt6.QtWidgets import QFrame, QLabel, QPushButton, QScrollArea, QVBoxLayout
        from .resources.theme import (
            ACCENT, FONT_MONO, FONT_SANS_DISPLAY, INK, INK_3, INK_4, LINE, SURFACE,
        )
        super().__init__(parent)
        self._on_pick = on_pick

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        l = QVBoxLayout(inner)
        l.setContentsMargins(40, 28, 40, 40)
        l.setSpacing(0)

        kicker = QLabel("Tests", inner)
        kicker.setStyleSheet(
            f"color: {ACCENT}; font-size: 10px; font-weight: 800;"
            f" letter-spacing: 0.6px; font-family: {FONT_MONO};"
        )
        l.addWidget(kicker)
        l.addSpacing(6)
        t = QLabel("実力テスト", inner)
        t.setStyleSheet(
            f"color: {INK}; font-size: 32px; font-weight: 800; letter-spacing: -1px;"
            f" font-family: {FONT_SANS_DISPLAY};"
        )
        l.addWidget(t)
        sub = QLabel("Phase ごとに 10 問。制限時間 30 分、合格基準 60%。", inner)
        sub.setStyleSheet(f"color: {INK_3}; font-size: 13px; letter-spacing: -0.1px;")
        l.addWidget(sub)
        l.addSpacing(20)

        if not test_sets:
            empty = QLabel("実力テストはまだ用意されていません。", inner)
            empty.setStyleSheet(f"color: {INK_4}; font-size: 12px;")
            l.addWidget(empty)
        for ts in test_sets:
            card = QFrame(inner)
            card.setObjectName("TestCard")
            card.setStyleSheet(
                f"""
                #TestCard {{ background: transparent; border: 1px solid {LINE};
                    border-left: 2px solid transparent; border-radius: 0; }}
                #TestCard:hover {{ border-left-color: {ACCENT}; }}
                """
            )
            cl = QVBoxLayout(card)
            cl.setContentsMargins(20, 16, 20, 16)
            row = QFrame(card)
            rl = QVBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            ttl = QLabel(ts.title, row)
            ttl.setStyleSheet(
                f"color: {INK}; font-size: 16px; font-weight: 700; letter-spacing: -0.2px;"
            )
            rl.addWidget(ttl)
            meta = QLabel(
                f"Phase {ts.phase} · {len(ts.questions)} 問 · {ts.time_limit_minutes} 分", row,
            )
            meta.setStyleSheet(
                f"color: {INK_4}; font-size: 11px; font-weight: 700;"
                f" font-family: {FONT_MONO}; letter-spacing: 0.3px;"
            )
            rl.addWidget(meta)
            cl.addWidget(row)
            start = QPushButton("テストを開始 →", card)
            start.setCursor(Qt.CursorShape.PointingHandCursor)
            start.setStyleSheet(
                f"QPushButton {{ background: {ACCENT}; color: white; border: 1px solid {ACCENT};"
                f" border-radius: 0; padding: 7px 18px; font-size: 11px; font-weight: 700;"
                f" min-width: 0; min-height: 0; }}"
                f"QPushButton:hover {{ background: #F87171; border-color: #F87171; }}"
            )
            start.clicked.connect(lambda _checked=False, tid=ts.id: self._on_pick(tid))
            cl.addWidget(start, 0, Qt.AlignmentFlag.AlignLeft)
            l.addWidget(card)
            l.addSpacing(10)
        l.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll)


def _is_legacy() -> bool:
    """Return True if the user opted into the old QSS shell."""
    flag = os.environ.get("STUDYPY_LEGACY_UI", "").strip().lower()
    return flag in ("1", "true", "yes", "on")


class WebMainWindow(QMainWindow):
    """Frameless host window that mounts a `WebShell` (HTML/CSS/JS UI)."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Study Python for Finance")
        self.setMinimumSize(1200, 780)
        self.resize(1360, 860)

        # .env best-effort
        try:
            from dotenv import load_dotenv
            load_dotenv(PROJECT_ROOT / ".env")
        except ImportError:
            pass

        self.repo = Repository(DB_PATH)
        self.user = self.repo.get_or_create_default_user()
        self.kernel = KernelSession()
        self.llm = ClaudeClient()

        try:
            self.chapters = load_chapters(CONTENT_DIR)
        except ContentError as e:
            QMessageBox.critical(self, "章ファイルの読み込みに失敗しました", str(e))
            self.chapters = []
        try:
            self.test_sets = load_test_sets(TESTS_DIR)
        except Exception as e:  # noqa: BLE001
            logging.exception("test set load failed")
            self.test_sets = {}

        # Lazy import so legacy-only environments aren't forced to install
        # pyqt6-webengine.
        from .ui.web_shell import WebShell

        self.web = WebShell(
            self.chapters, self.repo, self.user.id, self.kernel, self.test_sets,
        )
        self.setCentralWidget(self.web)

        # Start kernel; relay state to the web layer.
        try:
            self.kernel.start()
            self.web.notify_kernel_state("ready")
        except Exception as e:  # noqa: BLE001
            logging.exception("kernel start failed")
            self.web.notify_kernel_state("error")

    def closeEvent(self, e) -> None:  # noqa: N802
        try:
            self.kernel.shutdown()
        except Exception:  # noqa: BLE001
            logging.exception("kernel shutdown failed")
        super().closeEvent(e)


def main() -> int:
    _configure_logging()
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    families = _load_bundled_fonts()
    if families:
        logging.info("bundled fonts active: %s", ", ".join(families))

    if _is_legacy():
        # Legacy QSS shell
        app.setStyleSheet(GLOBAL_STYLESHEET)
        win = MainWindow()
    else:
        win = WebMainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
