"""Theme tokens — Dark Sharp Modern (Linear / Vercel inspired).

Design rules:
- Near-black surfaces with subtle elevation tiers
- A single vivid red as the only saturated accent
- Sharp corners (radius 0; never rounded)
- Hairline borders (1px) using a low-contrast LINE color
- No emoji, no soft drop shadows
- Strong typographic hierarchy via weight + size, never decoration
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Color tokens — Dark mode
# ---------------------------------------------------------------------------

# Accent (the only saturated color in the UI)
ACCENT         = "#EF4444"   # red-500 — slightly brighter than light-mode so it pops on dark
ACCENT_HOVER   = "#F87171"   # red-400 — even brighter on hover (dark mode quirk)
ACCENT_PRESSED = "#DC2626"   # red-600
ACCENT_SOFT    = "#1F0A0A"   # ultra-dark red tint, used for hover backgrounds
ACCENT_TINT    = "#2A0E0E"   # mid-dark red tint, for selected rows/cards

# Ink (text) — light on dark
INK       = "#F5F5F5"        # primary text
INK_2     = "#D4D4D4"        # secondary
INK_3     = "#A3A3A3"        # tertiary / sub
INK_4     = "#737373"        # muted / placeholder
INK_5     = "#525252"        # very muted

# Surfaces
BG          = "#0A0A0A"      # window background
SURFACE     = "#141414"      # cards / panels (slight elevation)
SURFACE_ALT = "#1C1C1C"      # code blocks, deeper containers
SURFACE_TINT = "#1A1A1A"     # subtle hover background
BG_ALT      = SURFACE        # legacy alias kept for compat

# Lines
LINE        = "#262626"      # hairline border
LINE_STRONG = "#404040"      # stronger dividers (e.g. between header and body)
LINE_TINT   = "#1F1F1F"      # ultra-subtle line
LINE_SUBTLE = "#1A1A1A"      # nearly-invisible split (used inside cards)
LINE_FOCUS  = "#5B5B5B"      # neutral inner outline (Arc-style elevation)

# Subtle blue — focus ring & link state only (Arc/Raycast accent restraint)
INK_BLUE      = "#7DA9FF"
INK_BLUE_SOFT = "#0E141F"
FOCUS_RING    = INK_BLUE     # 1px outline on :focus targets

# Elevation tiers (no shadows; we tone borders instead)
SURFACE_HI    = "#181818"    # CommandPalette / hover-rich panels
SURFACE_GLASS = "rgba(20, 20, 20, 0.92)"  # overlay layer
OVERLAY_SCRIM = "rgba(0, 0, 0, 0.55)"     # modal backdrop

# Status
SUCCESS = "#10B981"          # emerald-500
WARN    = "#F59E0B"          # amber-500
DANGER  = ACCENT

# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------

# Font stacks. The first families are loaded from app/resources/fonts/ if
# the user has placed the corresponding .ttf there (see fonts/README.md);
# otherwise the OS defaults kick in transparently.
FONT_SANS = (
    '"Inter Variable", "Inter", "Geist", "SF Pro Text", '
    '"Segoe UI Variable Text", "Segoe UI", "Yu Gothic UI", "Hiragino Sans", '
    'system-ui, -apple-system, sans-serif'
)
FONT_SANS_DISPLAY = (
    '"Inter Display", "Inter Variable", "Inter", "Geist", '
    '"SF Pro Display", "Segoe UI Variable Display", "Segoe UI", '
    '"Yu Gothic UI", "Hiragino Sans", system-ui, sans-serif'
)
FONT_MONO = (
    '"JetBrains Mono", "Cascadia Code", "Cascadia Mono", "Consolas", '
    '"SF Mono", "Menlo", monospace'
)

PHASE_LABELS = {
    "A": "Phase A",
    "B": "Phase B",
    "C": "Phase C",
    "D": "Phase D",
    "E": "Phase E",
    "F": "Phase F",
}


# ---------------------------------------------------------------------------
# Global stylesheet
# ---------------------------------------------------------------------------

GLOBAL_STYLESHEET = f"""
/* ========================================================================
   Study Python Finance — Dark Sharp Modern
   ======================================================================== */

QMainWindow, QWidget {{
    background: {BG};
    color: {INK};
    font-family: {FONT_SANS};
    font-size: 13px;
}}

QLabel {{
    color: {INK};
    letter-spacing: -0.1px;
}}

QLabel[role="muted"] {{ color: {INK_3}; }}
QLabel[role="caption"] {{
    color: {INK_3};
    font-size: 11px;
    letter-spacing: 0.4px;
    text-transform: none;
}}

/* Buttons --------------------------------------------------------------- */

QPushButton {{
    background: {ACCENT};
    color: white;
    border: 1px solid {ACCENT};
    border-radius: 0px;
    padding: 8px 22px;
    font-family: {FONT_SANS};
    font-size: 11px;
    font-weight: 700;
    min-width: 96px;
    min-height: 22px;
}}
QPushButton:hover     {{ background: {ACCENT_HOVER};   border-color: {ACCENT_HOVER}; }}
QPushButton:pressed   {{ background: {ACCENT_PRESSED}; border-color: {ACCENT_PRESSED}; }}
QPushButton:disabled  {{ background: {SURFACE}; color: {INK_4}; border-color: {LINE}; }}

QPushButton[variant="secondary"] {{
    background: {SURFACE};
    color: {INK};
    border: 1px solid {LINE_STRONG};
}}
QPushButton[variant="secondary"]:hover {{
    background: {INK};
    color: {BG};
    border-color: {INK};
}}
QPushButton[variant="secondary"]:disabled {{
    background: {SURFACE}; color: {INK_4}; border-color: {LINE};
}}

QPushButton[variant="ghost"] {{
    background: transparent;
    color: {INK_3};
    border: none;
    padding: 6px 10px;
    font-weight: 600;
    min-width: 0;
}}
QPushButton[variant="ghost"]:hover {{ color: {ACCENT}; }}

/* Inputs ---------------------------------------------------------------- */

QLineEdit, QPlainTextEdit, QTextBrowser, QTextEdit {{
    background: {SURFACE};
    color: {INK};
    border: 1px solid {LINE};
    border-radius: 0px;
    padding: 6px 10px;
    selection-background-color: {ACCENT};
    selection-color: white;
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextBrowser:focus {{
    border-color: {ACCENT};
}}

/* Progress bar ---------------------------------------------------------- */

QProgressBar {{
    background: {LINE};
    border: none;
    border-radius: 0px;
    height: 2px;
    text-align: center;
    color: {INK_3};
    font-size: 11px;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 0px;
}}

/* Group box ------------------------------------------------------------- */

QGroupBox {{
    background: {SURFACE};
    border: 1px solid {LINE};
    border-radius: 0px;
    margin-top: 14px;
    padding: 14px;
    font-weight: 700;
    color: {INK};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px; top: -8px; padding: 0 6px;
    background: {BG};
    color: {INK};
}}

/* List widgets ---------------------------------------------------------- */

QListWidget {{
    background: transparent;
    border: none;
    outline: 0;
}}
QListWidget::item {{
    background: {SURFACE};
    border: 1px solid {LINE};
    border-radius: 0px;
    padding: 10px 12px;
    margin-bottom: 4px;
    color: {INK};
}}
QListWidget::item:hover {{
    border-color: {ACCENT};
    color: {ACCENT};
}}
QListWidget::item:selected {{
    background: {ACCENT_TINT};
    border-color: {ACCENT};
    color: {ACCENT};
}}

/* Combo box ------------------------------------------------------------- */

QComboBox {{
    background: {SURFACE};
    color: {INK};
    border: 1px solid {LINE};
    border-radius: 0px;
    padding: 6px 10px;
    selection-background-color: {ACCENT};
}}
QComboBox:hover {{ border-color: {LINE_STRONG}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE};
    color: {INK};
    border: 1px solid {LINE_STRONG};
    selection-background-color: {ACCENT};
    selection-color: white;
    outline: 0;
}}

/* Status bar ------------------------------------------------------------ */

QStatusBar {{
    background: {BG};
    color: {INK_3};
    border-top: 1px solid {LINE};
}}
QStatusBar::item {{ border: none; }}

/* Tooltip --------------------------------------------------------------- */

QToolTip {{
    background: {INK};
    color: {BG};
    border: none;
    padding: 6px 10px;
    border-radius: 0px;
    font-size: 11px;
    font-weight: 600;
}}

/* Scrollbars ------------------------------------------------------------ */

QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {LINE_STRONG}; min-height: 30px; border-radius: 0px;
}}
QScrollBar::handle:vertical:hover {{ background: {INK_4}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

QScrollBar:horizontal {{
    background: transparent; height: 10px; margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {LINE_STRONG}; min-width: 30px; border-radius: 0px;
}}
QScrollBar::handle:horizontal:hover {{ background: {INK_4}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ height: 0; width: 0; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}

/* Splitter ------------------------------------------------------------ */
QSplitter::handle {{ background: {LINE}; }}
QSplitter::handle:hover {{ background: {ACCENT}; }}

/* Frames as message boxes ----------------------------------------------- */
QMessageBox {{ background: {SURFACE}; }}
QMessageBox QLabel {{ color: {INK}; }}

/* Headings via objectName ---------------------------------------------- */

QLabel#hero {{
    font-family: {FONT_SANS_DISPLAY};
    font-size: 40px; font-weight: 800; color: {INK};
    letter-spacing: -1.0px;
}}
QLabel#h1 {{
    font-family: {FONT_SANS_DISPLAY};
    font-size: 26px; font-weight: 800; color: {INK};
    letter-spacing: -0.4px;
}}
QLabel#h2 {{
    font-size: 16px; font-weight: 700; color: {INK};
}}
QLabel#h3 {{
    font-size: 12px; font-weight: 700; color: {INK};
}}
QLabel#kicker {{
    font-size: 10px; font-weight: 800;
    color: {ACCENT}; letter-spacing: 0.4px;
}}
QLabel#muted {{ color: {INK_3}; }}

/* Section divider helper class via dynamic property -------------------- */
QFrame[variant="rule"] {{
    background: {LINE};
    max-height: 1px; min-height: 1px; border: none;
}}
QFrame[variant="rule-strong"] {{
    background: {LINE_STRONG};
    max-height: 2px; min-height: 2px; border: none;
}}
QFrame[variant="rule-accent"] {{
    background: {ACCENT};
    max-height: 2px; min-height: 2px; border: none;
}}
QFrame[variant="rule-subtle"] {{
    background: {LINE_SUBTLE};
    max-height: 1px; min-height: 1px; border: none;
}}

/* Keyboard cap ---------------------------------------------------------- */

QLabel[kbd="true"] {{
    background: {SURFACE_ALT};
    color: {INK_2};
    border: 1px solid {LINE_STRONG};
    border-bottom: 2px solid {LINE_STRONG};
    border-radius: 0px;
    font-family: {FONT_MONO};
    font-size: 10px;
    font-weight: 700;
    padding: 1px 5px 0 5px;
    min-width: 12px;
    letter-spacing: 0;
}}

QLabel[kbd="true"][kbdMuted="true"] {{
    color: {INK_4};
    border-color: {LINE};
    border-bottom-color: {LINE};
}}

/* Hoverable rows / cards (Raycast row feel) ----------------------------- */

QFrame[hoverable="true"] {{
    background: transparent;
}}
QFrame[hoverable="true"]:hover {{
    background: {SURFACE_TINT};
}}

/* Inner-glow panel (Arc-style elevation; nested 1px frame, radius 0) ---- */

QFrame[panel="glass"] {{
    background: {SURFACE_HI};
    border: 1px solid {LINE_STRONG};
    border-radius: 0px;
}}

QFrame[panel="raised"] {{
    background: {SURFACE};
    border: 1px solid {LINE};
    border-radius: 0px;
}}

QFrame[panel="raised-accent"] {{
    background: {SURFACE};
    border: 1px solid {LINE_SUBTLE};
    border-left: 2px solid {ACCENT};
    border-radius: 0px;
}}

/* Tag / pill (Arc-style metadata chip) ---------------------------------- */

QLabel[tag="true"] {{
    background: {SURFACE_ALT};
    border: 1px solid {LINE};
    color: {INK_3};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.2px;
    padding: 2px 7px;
    border-radius: 0px;
}}
QLabel[tag="accent"] {{
    background: {ACCENT_TINT};
    border: 1px solid {ACCENT};
    color: {ACCENT_HOVER};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.2px;
    padding: 2px 7px;
    border-radius: 0px;
}}

/* Focus rings (subtle blue, only when focused) -------------------------- */

QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
QTextBrowser:focus, QComboBox:focus {{
    border: 1px solid {FOCUS_RING};
}}
"""
