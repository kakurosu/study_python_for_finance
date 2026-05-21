"""AppShell — Linear-style chrome around the active content.

Layout (window-wide):

    +--------+----------------------------------+
    | Side   |  TopBar (breadcrumb · search · Y) |
    | Nav    +----------------------------------+
    |        |                                  |
    |  Dash  |                                  |
    |  Chap  |   Content stack (view swapper)   |
    |  Pract |                                  |
    |  ...   |                                  |
    |        |                                  |
    |[mini]  |                                  |
    +--------+----------------------------------+
    |  StatusBar  Python 3.12 · kernel: ready    |
    +---------------------------------------------+

The shell owns:
- SidebarNav     (left, fixed 220px)
- TopBar         (top of content area, 56px)
- ContentStack   (the swap region — Dashboard, Chapters, ...)
- StatusBar      (bottom-of-window, 28px)

It exposes a small API used by ``MainWindow`` and by the launcher:

    shell.add_view(slug, widget, label, icon)   # register a view
    shell.show_view(slug)                       # switch focus
    shell.set_breadcrumb(*parts)                # update breadcrumb
    shell.set_kernel_state(state, detail="")    # status bar update
"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from ..resources.theme import (
    ACCENT,
    ACCENT_TINT,
    BG,
    FONT_MONO,
    FONT_SANS,
    INK,
    INK_2,
    INK_3,
    INK_4,
    INK_5,
    LINE,
    LINE_FOCUS,
    LINE_STRONG,
    LINE_SUBTLE,
    SUCCESS,
    SURFACE,
    SURFACE_ALT,
    SURFACE_TINT,
)
from .widgets.kbd import KbdCombo


# ---------------------------------------------------------------------------
# SidebarNav
# ---------------------------------------------------------------------------


@dataclass
class _NavItem:
    slug: str
    label: str
    icon: str           # text glyph (single char or 2 chars), used like a bullet
    group: str          # group header label
    button: QPushButton | None = None
    badge: QLabel | None = None


class SidebarNav(QFrame):
    """Vertical nav with grouped items and a mini progress card at the bottom."""

    activated = pyqtSignal(str)  # emits the slug of the clicked nav item

    WIDTH = 232

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(self.WIDTH)
        self.setObjectName("SidebarNav")
        self.setStyleSheet(
            f"""
            #SidebarNav {{
                background: {SURFACE_ALT};
                border: none;
                border-right: 1px solid {LINE};
            }}
            """
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # --- wordmark row -----------------------------------------------
        mark = QFrame(self)
        mark.setFixedHeight(58)
        mark.setStyleSheet(f"QFrame {{ background: transparent; border-bottom: 1px solid {LINE}; }}")
        mark_l = QHBoxLayout(mark)
        mark_l.setContentsMargins(18, 0, 18, 0)
        mark_l.setSpacing(10)
        # Square red badge as "logo"
        badge = QFrame(mark)
        badge.setFixedSize(22, 22)
        badge.setStyleSheet(f"background: {ACCENT}; border: none;")
        mark_l.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)
        wm_text = QLabel(
            "Study Python<br/>"
            "<span style='color:#A3A3A3; font-weight:600;'>for Finance</span>",
            mark,
        )
        wm_text.setTextFormat(Qt.TextFormat.RichText)
        wm_text.setStyleSheet(
            f"color: {INK}; font-size: 12px; font-weight: 800; letter-spacing: -0.2px;"
            f" line-height: 1.0;"
        )
        mark_l.addWidget(wm_text, 1, Qt.AlignmentFlag.AlignVCenter)
        ver = QLabel("v0.4", mark)
        ver.setStyleSheet(
            f"color: {INK_4}; font-size: 10px; font-weight: 700;"
            f" letter-spacing: 0.2px;"
        )
        mark_l.addWidget(ver, 0, Qt.AlignmentFlag.AlignVCenter)
        outer.addWidget(mark)

        # --- nav items --------------------------------------------------
        nav_wrap = QWidget(self)
        nav_layout = QVBoxLayout(nav_wrap)
        nav_layout.setContentsMargins(12, 14, 12, 14)
        nav_layout.setSpacing(2)
        self._nav_layout = nav_layout
        self._items: dict[str, _NavItem] = {}
        outer.addWidget(nav_wrap, 1)

        # --- Cmd+K palette hint pill (Arc/Raycast affordance) -----------
        pill_wrap = QFrame(self)
        pill_wrap.setFixedHeight(46)
        pill_wrap.setStyleSheet(
            f"QFrame {{ background: transparent;"
            f" border-top: 1px solid {LINE_SUBTLE}; }}"
        )
        pill_l = QHBoxLayout(pill_wrap)
        pill_l.setContentsMargins(14, 6, 14, 8)
        pill_l.setSpacing(8)
        self._palette_btn = QPushButton("  ⌕   検索…", pill_wrap)
        self._palette_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._palette_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {INK_3};"
            f" border: 1px solid {LINE}; border-radius: 0;"
            f" padding: 6px 8px; text-align: left;"
            f" font-family: {FONT_SANS}; font-size: 11px; font-weight: 600;"
            f" min-width: 0; min-height: 0; }}"
            f"QPushButton:hover {{ color: {INK_2}; border-color: {LINE_FOCUS}; }}"
        )
        self._palette_btn.clicked.connect(self._on_palette_clicked)
        pill_l.addWidget(self._palette_btn, 1)
        kbd = KbdCombo(["Ctrl", "K"], pill_wrap, muted=True)
        pill_l.addWidget(kbd, 0, Qt.AlignmentFlag.AlignVCenter)
        outer.addWidget(pill_wrap)

        self._active_slug: str | None = None
        self._palette_handler = None

    # ------------------------------------------------------------------
    def add_item(self, slug: str, label: str, *, icon: str = "·", group: str = "学習",
                 badge: str | None = None) -> None:
        # Render a group header lazily if it's the first item with that group label.
        existing_groups = {item.group for item in self._items.values()}
        if group not in existing_groups:
            head = QLabel(group, self)
            head.setStyleSheet(
                f"color: {INK_4}; font-size: 9px; font-weight: 800; letter-spacing: 0.6px;"
                f" padding: 14px 8px 6px 8px;"
            )
            self._nav_layout.addWidget(head)

        btn = QPushButton(self)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setProperty("nav_active", False)
        btn.setProperty("slug", slug)
        # We render the icon + label as rich label inside the button via setText
        # and a stylesheet that left-aligns the text.
        btn.setText(f"  {icon}   {label}")
        btn.setStyleSheet(self._btn_qss(active=False))
        btn.setMinimumHeight(34)
        btn.clicked.connect(lambda _checked=False, s=slug: self._on_clicked(s))
        self._nav_layout.addWidget(btn)

        badge_lbl: QLabel | None = None
        if badge:
            # Stack a small numeric badge in the right side of the button row.
            badge_lbl = QLabel(badge, self)
            badge_lbl.setStyleSheet(
                f"color: {INK_3}; background: {SURFACE_ALT};"
                f" border: 1px solid {LINE}; padding: 1px 6px;"
                f" font-size: 10px; font-weight: 700; font-family: {FONT_MONO};"
            )
            # Re-pack the button with a sibling layout: we instead use plain
            # text "Label    7" so we don't need to overlay.
            btn.setText(f"  {icon}   {label}     {badge}")

        self._items[slug] = _NavItem(
            slug=slug, label=label, icon=icon, group=group, button=btn, badge=badge_lbl
        )

    def add_stretch(self) -> None:
        self._nav_layout.addStretch(1)

    def set_active(self, slug: str) -> None:
        for s, it in self._items.items():
            assert it.button is not None
            is_active = (s == slug)
            it.button.setProperty("nav_active", is_active)
            it.button.setStyleSheet(self._btn_qss(active=is_active))
        self._active_slug = slug

    def _btn_qss(self, *, active: bool) -> str:
        if active:
            return (
                f"QPushButton {{"
                f" background: {SURFACE_TINT};"
                f" color: {INK};"
                f" border: none;"
                f" border-left: 1px solid {LINE_FOCUS};"
                f" border-radius: 0;"
                f" padding: 7px 14px 7px 17px;"
                f" font-family: 'Inter Variable', 'Inter', sans-serif;"
                f" font-size: 12.5px; font-weight: 700;"
                f" text-align: left; min-width: 0; min-height: 0;"
                f" letter-spacing: -0.1px;"
                f" }}"
            )
        return (
            f"QPushButton {{"
            f" background: transparent;"
            f" color: {INK_2};"
            f" border: none;"
            f" border-left: 1px solid transparent;"
            f" border-radius: 0;"
            f" padding: 7px 14px 7px 17px;"
            f" font-family: 'Inter Variable', 'Inter', sans-serif;"
            f" font-size: 12.5px; font-weight: 600;"
            f" text-align: left; min-width: 0; min-height: 0;"
            f" letter-spacing: -0.1px;"
            f" }}"
            f"QPushButton:hover {{ background: {SURFACE_TINT};"
            f" color: {INK};"
            f" border-left: 1px solid {LINE_FOCUS}; }}"
        )

    def _on_clicked(self, slug: str) -> None:
        self.activated.emit(slug)

    def _on_palette_clicked(self) -> None:
        if self._palette_handler is not None:
            self._palette_handler()

    def set_palette_handler(self, fn) -> None:
        self._palette_handler = fn

    # ------------------------------------------------------------------
    # Mini progress API kept as a no-op so existing callers (main.py) still
    # work after the card was removed.
    def set_mini_progress(self, *_args, **_kwargs) -> None:
        return None


# ---------------------------------------------------------------------------
# TopBar
# ---------------------------------------------------------------------------


class TopBar(QFrame):
    """Window-wide top bar with breadcrumb on the left, search + kernel pill on the right."""

    HEIGHT = 56

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(self.HEIGHT)
        self.setObjectName("AppTopBar")
        self.setStyleSheet(
            f"""
            #AppTopBar {{ background: {BG}; border: none;
                border-bottom: 1px solid {LINE}; }}
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(28, 0, 18, 0)
        layout.setSpacing(14)

        # Breadcrumb area — multiple QLabels, separators are dim chevrons
        self._crumb_holder = QWidget(self)
        self._crumb_layout = QHBoxLayout(self._crumb_holder)
        self._crumb_layout.setContentsMargins(0, 0, 0, 0)
        self._crumb_layout.setSpacing(8)
        layout.addWidget(self._crumb_holder, 1, Qt.AlignmentFlag.AlignVCenter)

        # Right: Raycast-style command search button + kernel pill
        self._palette_btn = QPushButton("  ⌕   検索 / コマンド", self)
        self._palette_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._palette_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {INK_3};"
            f" border: 1px solid {LINE}; border-radius: 0;"
            f" padding: 6px 10px; text-align: left;"
            f" font-family: {FONT_SANS}; font-size: 11px; font-weight: 600;"
            f" min-width: 200px; min-height: 26px; }}"
            f"QPushButton:hover {{ color: {INK_2}; border-color: {LINE_FOCUS}; }}"
        )
        self._palette_btn.clicked.connect(self._on_palette_clicked)
        layout.addWidget(self._palette_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        kbd = KbdCombo(["Ctrl", "K"], self, muted=True)
        layout.addWidget(kbd, 0, Qt.AlignmentFlag.AlignVCenter)

        # Kernel state pill (mirrors status bar; visible at-a-glance)
        self._kernel_pill = QFrame(self)
        self._kernel_pill.setFixedHeight(26)
        self._kernel_pill.setStyleSheet(
            f"QFrame {{ background: transparent;"
            f" border: 1px solid {LINE}; border-radius: 0; }}"
        )
        kp_l = QHBoxLayout(self._kernel_pill)
        kp_l.setContentsMargins(8, 0, 10, 0)
        kp_l.setSpacing(6)
        self._kernel_dot = QFrame(self._kernel_pill)
        self._kernel_dot.setFixedSize(6, 6)
        self._kernel_dot.setStyleSheet(f"background: {SUCCESS}; border: none;")
        kp_l.addWidget(self._kernel_dot, 0, Qt.AlignmentFlag.AlignVCenter)
        self._kernel_lbl = QLabel("ready", self._kernel_pill)
        self._kernel_lbl.setStyleSheet(
            f"color: {INK_3}; font-size: 10px; font-weight: 700;"
            f" font-family: {FONT_MONO}; letter-spacing: 0.3px;"
        )
        kp_l.addWidget(self._kernel_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._kernel_pill, 0, Qt.AlignmentFlag.AlignVCenter)

        self._palette_handler = None

        # Default breadcrumb — the brand is already in the sidebar, so the
        # crumb starts with the section name only.
        self.set_breadcrumb("Dashboard")

    def _on_palette_clicked(self) -> None:
        if self._palette_handler is not None:
            self._palette_handler()

    def set_palette_handler(self, fn) -> None:
        self._palette_handler = fn

    def set_kernel_state(self, state: str) -> None:
        colors = {
            "ready": SUCCESS,
            "busy":  "#F59E0B",
            "error": ACCENT,
            "idle":  INK_4,
        }
        c = colors.get(state, INK_4)
        self._kernel_dot.setStyleSheet(f"background: {c}; border: none;")
        self._kernel_lbl.setText(state)

    # ------------------------------------------------------------------
    def set_breadcrumb(self, *parts: str) -> None:
        # Wipe and re-render
        while self._crumb_layout.count():
            it = self._crumb_layout.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        last_idx = len(parts) - 1
        for i, p in enumerate(parts):
            lbl = QLabel(p, self._crumb_holder)
            if i == last_idx:
                lbl.setStyleSheet(
                    f"color: {INK}; font-size: 13px; font-weight: 700; letter-spacing: -0.1px;"
                )
            else:
                lbl.setStyleSheet(
                    f"color: {INK_3}; font-size: 12px; font-weight: 600;"
                )
            self._crumb_layout.addWidget(lbl, 0, Qt.AlignmentFlag.AlignVCenter)
            if i < last_idx:
                sep = QLabel("›", self._crumb_holder)
                sep.setStyleSheet(
                    f"color: {INK_5}; font-size: 13px; font-weight: 600;"
                )
                self._crumb_layout.addWidget(sep, 0, Qt.AlignmentFlag.AlignVCenter)
        self._crumb_layout.addStretch(1)


# ---------------------------------------------------------------------------
# StatusBar
# ---------------------------------------------------------------------------


class StatusBar(QFrame):
    """Window-wide bottom status bar (IDE feel: kernel, encoding, etc.)."""

    HEIGHT = 28

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(self.HEIGHT)
        self.setObjectName("AppStatusBar")
        self.setStyleSheet(
            f"""
            #AppStatusBar {{ background: {BG}; border: none;
                border-top: 1px solid {LINE}; }}
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(18)

        self._dot = QFrame(self)
        self._dot.setFixedSize(6, 6)
        self._dot.setStyleSheet(f"background: {SUCCESS}; border: none;")
        layout.addWidget(self._dot, 0, Qt.AlignmentFlag.AlignVCenter)

        self._kernel = QLabel("kernel: ready", self)
        self._kernel.setStyleSheet(
            f"color: {INK_3}; font-size: 10px; font-weight: 700;"
            f" letter-spacing: 0.3px; font-family: {FONT_MONO};"
        )
        layout.addWidget(self._kernel, 0, Qt.AlignmentFlag.AlignVCenter)

        layout.addWidget(self._dim_label("Python 3.12"))
        layout.addWidget(self._dim_label("UTF-8"))
        layout.addWidget(self._dim_label("LF"))

        layout.addStretch(1)
        layout.addWidget(self._dim_label("Study.py Finance Edition"))
        layout.addWidget(self._dim_label("v0.4"))

    def _dim_label(self, text: str) -> QLabel:
        lbl = QLabel(text, self)
        lbl.setStyleSheet(
            f"color: {INK_4}; font-size: 10px; font-weight: 600;"
            f" letter-spacing: 0.3px; font-family: {FONT_MONO};"
        )
        return lbl

    # ------------------------------------------------------------------
    def set_kernel_state(self, state: str, detail: str = "") -> None:
        # state: "ready" (green) / "busy" (amber) / "error" (red) / "idle" (gray)
        colors = {
            "ready": SUCCESS,
            "busy": "#F59E0B",
            "error": ACCENT,
            "idle": INK_4,
        }
        c = colors.get(state, INK_4)
        self._dot.setStyleSheet(f"background: {c}; border: none;")
        text = f"kernel: {state}"
        if detail:
            text = f"{text} · {detail}"
        self._kernel.setText(text)


# ---------------------------------------------------------------------------
# AppShell
# ---------------------------------------------------------------------------


class AppShell(QWidget):
    """Top-level shell: sidebar + topbar + content stack + status bar."""

    nav_activated = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # --- left sidebar ----------------------------------------------
        self.sidebar = SidebarNav(self)
        self.sidebar.activated.connect(self._on_sidebar)

        # --- right content area ----------------------------------------
        right = QWidget(self)
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(0, 0, 0, 0)
        right_l.setSpacing(0)

        self.topbar = TopBar(right)
        right_l.addWidget(self.topbar)

        # Content swap area
        self._stack_holder = QWidget(right)
        self._stack = QStackedLayout(self._stack_holder)
        self._stack.setContentsMargins(0, 0, 0, 0)
        right_l.addWidget(self._stack_holder, 1)

        # --- root layout: sidebar + right ------------------------------
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self.sidebar)
        body.addWidget(right, 1)

        # --- status bar at the very bottom -----------------------------
        self.statusbar = StatusBar(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addLayout(body, 1)
        root.addWidget(self.statusbar)

        self._views: dict[str, QWidget] = {}

    # ------------------------------------------------------------------
    def add_view(self, slug: str, widget: QWidget) -> None:
        self._views[slug] = widget
        self._stack.addWidget(widget)

    def show_view(self, slug: str) -> None:
        widget = self._views.get(slug)
        if widget is None:
            return
        self._stack.setCurrentWidget(widget)
        self.sidebar.set_active(slug)

    def replace_view(self, slug: str, widget: QWidget) -> None:
        old = self._views.get(slug)
        if old is not None:
            self._stack.removeWidget(old)
            old.deleteLater()
        self._views[slug] = widget
        self._stack.addWidget(widget)
        self._stack.setCurrentWidget(widget)

    def current_slug(self) -> str | None:
        cur = self._stack.currentWidget()
        for slug, w in self._views.items():
            if w is cur:
                return slug
        return None

    # ------------------------------------------------------------------
    def _on_sidebar(self, slug: str) -> None:
        self.show_view(slug)
        self.nav_activated.emit(slug)
