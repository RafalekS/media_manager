"""
Theme manager — 5 built-in themes.
build_stylesheet(name) returns a complete QSS string.
Themes are persisted as JSON files in config/themes/.
"""

import json
from pathlib import Path

_THEMES_DIR = Path(__file__).parent.parent.parent / 'config' / 'themes'

_BUILTIN = {
    'Light': dict(
        sidebar_bg      = '#1e293b',
        sidebar_text    = '#94a3b8',
        sidebar_sel_bg  = '#2563eb',
        sidebar_sel_fg  = '#ffffff',
        sidebar_hover   = '#273549',
        sidebar_hover_fg= '#e2e8f0',
        content_bg      = '#f8fafc',
        card_bg         = '#ffffff',
        card_border     = '#e2e8f0',
        accent          = '#2563eb',
        accent_hover    = '#1d4ed8',
        accent_pressed  = '#1e40af',
        accent_disabled = '#93c5fd',
        accent_text     = '#ffffff',
        text_primary    = '#0f172a',
        text_muted      = '#64748b',
        input_bg        = '#ffffff',
        input_border    = '#cbd5e1',
        input_fg        = '#0f172a',
        input_focus     = '#2563eb',
        check_bg        = '#ffffff',
        check_border    = '#cbd5e1',
        check_checked   = '#2563eb',
        check_mark      = '#ffffff',
        grp_border      = '#e2e8f0',
        grp_title       = '#475569',
        progress_bg     = '#e2e8f0',
        statusbar_bg    = '#1e293b',
        statusbar_fg    = '#94a3b8',
        sec_bg          = '#ffffff',
        sec_fg          = '#374151',
        sec_border      = '#d1d5db',
        danger          = '#dc2626',
        danger_hover    = '#b91c1c',
        sep             = '#e2e8f0',
        table_bg        = '#ffffff',
        table_alt       = '#f8fafc',
        table_sel       = '#dbeafe',
        table_sel_fg    = '#1e40af',
        header_bg       = '#f1f5f9',
        header_fg       = '#475569',
    ),
    'Dark': dict(
        sidebar_bg      = '#1c1e26',
        sidebar_text    = '#9ca3af',
        sidebar_sel_bg  = '#4f46e5',
        sidebar_sel_fg  = '#ffffff',
        sidebar_hover   = '#2d303d',
        sidebar_hover_fg= '#e5e7eb',
        content_bg      = '#252830',
        card_bg         = '#2d303d',
        card_border     = '#383c4a',
        accent          = '#4f46e5',
        accent_hover    = '#4338ca',
        accent_pressed  = '#3730a3',
        accent_disabled = '#6366f1',
        accent_text     = '#ffffff',
        text_primary    = '#e5e7eb',
        text_muted      = '#6b7280',
        input_bg        = '#1c1e26',
        input_border    = '#383c4a',
        input_fg        = '#e5e7eb',
        input_focus     = '#4f46e5',
        check_bg        = '#1c1e26',
        check_border    = '#383c4a',
        check_checked   = '#4f46e5',
        check_mark      = '#ffffff',
        grp_border      = '#383c4a',
        grp_title       = '#9ca3af',
        progress_bg     = '#383c4a',
        statusbar_bg    = '#1c1e26',
        statusbar_fg    = '#6b7280',
        sec_bg          = '#2d303d',
        sec_fg          = '#e5e7eb',
        sec_border      = '#383c4a',
        danger          = '#ef4444',
        danger_hover    = '#dc2626',
        sep             = '#383c4a',
        table_bg        = '#2d303d',
        table_alt       = '#343849',
        table_sel       = '#4f46e5',
        table_sel_fg    = '#ffffff',
        header_bg       = '#1c1e26',
        header_fg       = '#9ca3af',
    ),
    'Slate': dict(
        sidebar_bg      = '#0f172a',
        sidebar_text    = '#64748b',
        sidebar_sel_bg  = '#0ea5e9',
        sidebar_sel_fg  = '#ffffff',
        sidebar_hover   = '#1e293b',
        sidebar_hover_fg= '#cbd5e1',
        content_bg      = '#f1f5f9',
        card_bg         = '#ffffff',
        card_border     = '#e2e8f0',
        accent          = '#0ea5e9',
        accent_hover    = '#0284c7',
        accent_pressed  = '#0369a1',
        accent_disabled = '#7dd3fc',
        accent_text     = '#ffffff',
        text_primary    = '#0f172a',
        text_muted      = '#64748b',
        input_bg        = '#ffffff',
        input_border    = '#cbd5e1',
        input_fg        = '#0f172a',
        input_focus     = '#0ea5e9',
        check_bg        = '#ffffff',
        check_border    = '#cbd5e1',
        check_checked   = '#0ea5e9',
        check_mark      = '#ffffff',
        grp_border      = '#e2e8f0',
        grp_title       = '#475569',
        progress_bg     = '#e2e8f0',
        statusbar_bg    = '#0f172a',
        statusbar_fg    = '#64748b',
        sec_bg          = '#ffffff',
        sec_fg          = '#374151',
        sec_border      = '#d1d5db',
        danger          = '#dc2626',
        danger_hover    = '#b91c1c',
        sep             = '#e2e8f0',
        table_bg        = '#ffffff',
        table_alt       = '#f1f5f9',
        table_sel       = '#e0f2fe',
        table_sel_fg    = '#0369a1',
        header_bg       = '#f1f5f9',
        header_fg       = '#475569',
    ),
    'Midnight': dict(
        sidebar_bg      = '#0d1117',
        sidebar_text    = '#8b949e',
        sidebar_sel_bg  = '#7c3aed',
        sidebar_sel_fg  = '#ffffff',
        sidebar_hover   = '#161b22',
        sidebar_hover_fg= '#c9d1d9',
        content_bg      = '#161b22',
        card_bg         = '#21262d',
        card_border     = '#30363d',
        accent          = '#7c3aed',
        accent_hover    = '#6d28d9',
        accent_pressed  = '#5b21b6',
        accent_disabled = '#a78bfa',
        accent_text     = '#ffffff',
        text_primary    = '#c9d1d9',
        text_muted      = '#8b949e',
        input_bg        = '#0d1117',
        input_border    = '#30363d',
        input_fg        = '#c9d1d9',
        input_focus     = '#7c3aed',
        check_bg        = '#0d1117',
        check_border    = '#30363d',
        check_checked   = '#7c3aed',
        check_mark      = '#ffffff',
        grp_border      = '#30363d',
        grp_title       = '#8b949e',
        progress_bg     = '#30363d',
        statusbar_bg    = '#0d1117',
        statusbar_fg    = '#8b949e',
        sec_bg          = '#21262d',
        sec_fg          = '#c9d1d9',
        sec_border      = '#30363d',
        danger          = '#f85149',
        danger_hover    = '#da3633',
        sep             = '#30363d',
        table_bg        = '#21262d',
        table_alt       = '#262c35',
        table_sel       = '#7c3aed',
        table_sel_fg    = '#ffffff',
        header_bg       = '#0d1117',
        header_fg       = '#8b949e',
    ),
    'Pastel': dict(
        sidebar_bg      = '#e8eaf6',
        sidebar_text    = '#7986cb',
        sidebar_sel_bg  = '#7c4dff',
        sidebar_sel_fg  = '#ffffff',
        sidebar_hover   = '#dde2f5',
        sidebar_hover_fg= '#3949ab',
        content_bg      = '#fafafa',
        card_bg         = '#ffffff',
        card_border     = '#e8eaf6',
        accent          = '#7c4dff',
        accent_hover    = '#651fff',
        accent_pressed  = '#6200ea',
        accent_disabled = '#b39ddb',
        accent_text     = '#ffffff',
        text_primary    = '#37474f',
        text_muted      = '#90a4ae',
        input_bg        = '#ffffff',
        input_border    = '#ce93d8',
        input_fg        = '#37474f',
        input_focus     = '#7c4dff',
        check_bg        = '#ffffff',
        check_border    = '#ce93d8',
        check_checked   = '#7c4dff',
        check_mark      = '#ffffff',
        grp_border      = '#e1bee7',
        grp_title       = '#7e57c2',
        progress_bg     = '#e8eaf6',
        statusbar_bg    = '#e8eaf6',
        statusbar_fg    = '#7986cb',
        sec_bg          = '#f3e5f5',
        sec_fg          = '#37474f',
        sec_border      = '#ce93d8',
        danger          = '#e57373',
        danger_hover    = '#ef5350',
        sep             = '#e8eaf6',
        table_bg        = '#ffffff',
        table_alt       = '#f3e5f5',
        table_sel       = '#ede7f6',
        table_sel_fg    = '#4527a0',
        header_bg       = '#ede7f6',
        header_fg       = '#7e57c2',
    ),
}

# Backward compat — used by main_window for card colors
_THEMES = _BUILTIN

# Backward compat list
THEME_NAMES = list(_BUILTIN.keys())

COLOR_LABELS = {
    'sidebar_bg': 'Sidebar Background', 'sidebar_text': 'Sidebar Text',
    'sidebar_sel_bg': 'Sidebar Selected Bg', 'sidebar_sel_fg': 'Sidebar Selected Text',
    'sidebar_hover': 'Sidebar Hover Bg', 'sidebar_hover_fg': 'Sidebar Hover Text',
    'content_bg': 'Content Background', 'card_bg': 'Card Background',
    'card_border': 'Card Border', 'accent': 'Accent',
    'accent_hover': 'Accent Hover', 'accent_pressed': 'Accent Pressed',
    'accent_disabled': 'Accent Disabled', 'accent_text': 'Accent Text',
    'text_primary': 'Primary Text', 'text_muted': 'Muted Text',
    'input_bg': 'Input Background', 'input_border': 'Input Border',
    'input_fg': 'Input Text', 'input_focus': 'Input Focus Border',
    'check_bg': 'Checkbox Background', 'check_border': 'Checkbox Border',
    'check_checked': 'Checkbox Checked Fill', 'check_mark': 'Checkbox Tick Color',
    'grp_border': 'Group Border', 'grp_title': 'Group Title',
    'progress_bg': 'Progress Background', 'statusbar_bg': 'Status Bar Bg',
    'statusbar_fg': 'Status Bar Text', 'sec_bg': 'Secondary Btn Bg',
    'sec_fg': 'Secondary Btn Text', 'sec_border': 'Secondary Btn Border',
    'danger': 'Danger', 'danger_hover': 'Danger Hover', 'sep': 'Separator',
    'table_bg': 'Table Background', 'table_alt': 'Table Alt Row',
    'table_sel': 'Table Selection', 'table_sel_fg': 'Table Selection Text',
    'header_bg': 'Header Background', 'header_fg': 'Header Text',
}

COLOR_GROUPS = {
    'Sidebar':  ['sidebar_bg', 'sidebar_text', 'sidebar_sel_bg', 'sidebar_sel_fg', 'sidebar_hover', 'sidebar_hover_fg'],
    'Content':  ['content_bg', 'card_bg', 'card_border', 'sep'],
    'Text':     ['text_primary', 'text_muted'],
    'Accent':   ['accent', 'accent_hover', 'accent_pressed', 'accent_disabled', 'accent_text'],
    'Buttons':  ['sec_bg', 'sec_fg', 'sec_border', 'danger', 'danger_hover'],
    'Input':    ['input_bg', 'input_border', 'input_fg', 'input_focus'],
    'Checkbox': ['check_bg', 'check_border', 'check_checked', 'check_mark'],
    'Table':    ['table_bg', 'table_alt', 'table_sel', 'table_sel_fg', 'header_bg', 'header_fg'],
    'Misc':     ['grp_border', 'grp_title', 'progress_bg', 'statusbar_bg', 'statusbar_fg'],
}


def load_themes() -> dict:
    """Load all themes from config/themes/*.json. Seeds from built-ins if empty."""
    _THEMES_DIR.mkdir(parents=True, exist_ok=True)
    json_files = list(_THEMES_DIR.glob('*.json'))
    if not json_files:
        # Seed built-ins to disk
        for name, data in _BUILTIN.items():
            _write_theme_file(name, data)
        return {name: dict(data) for name, data in _BUILTIN.items()}

    themes = {}
    for f in sorted(json_files):
        try:
            with open(f, 'r', encoding='utf-8') as fh:
                themes[f.stem] = json.load(fh)
        except Exception:
            pass
    return themes


def _write_theme_file(name: str, data: dict):
    _THEMES_DIR.mkdir(parents=True, exist_ok=True)
    path = _THEMES_DIR / f'{name}.json'
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def save_theme(name: str, data: dict):
    """Write theme to config/themes/<name>.json"""
    _write_theme_file(name, data)


def delete_theme(name: str):
    """Delete config/themes/<name>.json"""
    path = _THEMES_DIR / f'{name}.json'
    if path.exists():
        path.unlink()


def get_theme_names() -> list:
    """Return sorted list of theme names."""
    themes = load_themes()
    return sorted(themes.keys())


def build_stylesheet(theme_name: str) -> str:
    themes = load_themes()
    t = themes.get(theme_name, themes.get('Light', _BUILTIN['Light']))
    return f"""
/* ── Base ─────────────────────────────────────────────────────────── */
QMainWindow, QDialog, QWidget {{
    background-color: {t['content_bg']};
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 10pt;
    color: {t['text_primary']};
}}
QLabel {{ background: transparent; color: {t['text_primary']}; }}

/* ── Sidebar ──────────────────────────────────────────────────────── */
#sidebar {{ background-color: {t['sidebar_bg']}; }}
#sidebar QLabel {{
    color: {t['sidebar_text']};
    background: transparent;
}}
#sidebar QLabel#app_title {{
    color: {t['sidebar_sel_fg']};
    font-size: 12pt;
    font-weight: bold;
    padding: 16px 14px 2px 14px;
}}
#sidebar QLabel#app_subtitle {{
    color: {t['sidebar_text']};
    font-size: 8pt;
    padding: 0 14px 12px 14px;
}}
#sidebar QLabel#ver_label {{
    color: {t['sidebar_text']};
    font-size: 8pt;
    padding: 8px 14px;
}}
#nav_list {{
    background: transparent;
    border: none;
    outline: none;
    color: {t['sidebar_text']};
    font-size: 9.5pt;
}}
#nav_list::item {{
    padding: 8px 14px;
    border-radius: 2px;
    margin: 1px 8px;
}}
#nav_list::item:selected {{
    background-color: {t['sidebar_sel_bg']};
    color: {t['sidebar_sel_fg']};
}}
#nav_list::item:hover:!selected {{
    background-color: {t['sidebar_hover']};
    color: {t['sidebar_hover_fg']};
}}

/* ── Content ──────────────────────────────────────────────────────── */
#content_widget {{ background: {t['content_bg']}; }}
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollArea > QWidget > QWidget {{ background: transparent; }}

/* ── Label roles ──────────────────────────────────────────────────── */
QLabel[role='title'] {{
    font-size: 17px;
    font-weight: bold;
    color: {t['text_primary']};
}}
QLabel[role='subtitle'] {{
    font-size: 9pt;
    color: {t['text_muted']};
    margin-bottom: 4px;
}}
QLabel[role='muted'] {{
    font-size: 9.5pt;
    color: {t['text_muted']};
}}
QLabel[role='card_label'] {{
    font-size: 8.5pt;
    color: {t['text_muted']};
}}
QLabel[role='status_ok']   {{ color: #10b981; }}
QLabel[role='status_err']  {{ color: #ef4444; }}
QLabel[role='status_warn'] {{ color: #f59e0b; }}
QLabel[role='stat_value']  {{ font-size: 22px; font-weight: bold; background: transparent; }}
QLabel[role='card_title']  {{ font-size: 11pt; font-weight: bold; background: transparent; }}
QLabel#sidebar_section     {{ font-size: 8pt; padding: 8px 14px 2px 14px; color: {t['text_muted']}; }}

/* ── Cards / panels ───────────────────────────────────────────────── */
#wizard_card {{
    background: {t['card_bg']};
    border: 1px solid {t['card_border']};
    border-radius: 2px;
}}
#wizard_card QLabel {{ background: transparent; }}

/* ── GroupBox ─────────────────────────────────────────────────────── */
QGroupBox {{
    background: {t['card_bg']};
    border: 1px solid {t['grp_border']};
    border-radius: 2px;
    margin-top: 10px;
    padding-top: 10px;
    font-weight: 600;
    font-size: 9.5pt;
    color: {t['grp_title']};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    left: 10px;
    color: {t['grp_title']};
}}
QGroupBox QLabel {{ background: transparent; }}

/* ── Buttons — primary ────────────────────────────────────────────── */
QPushButton {{
    background-color: {t['accent']};
    color: {t['accent_text']};
    border: none;
    border-radius: 2px;
    padding: 6px 16px;
    font-weight: 600;
    font-size: 9.5pt;
}}
QPushButton:hover    {{ background-color: {t['accent_hover']}; }}
QPushButton:pressed  {{ background-color: {t['accent_pressed']}; }}
QPushButton:disabled {{ background-color: {t['accent_disabled']}; color: {t['accent_text']}; }}

/* secondary */
QPushButton#btn_secondary {{
    background: {t['sec_bg']};
    color: {t['sec_fg']};
    border: 1px solid {t['sec_border']};
}}
QPushButton#btn_secondary:hover {{ background: {t['card_bg']}; }}

/* provider badges */
QLabel#badge_primary    {{ background: {t['accent']}; color: {t['accent_text']}; padding: 1px 6px; border-radius: 2px; }}
QLabel#badge_supplement {{ background: {t['sec_bg']}; color: {t['sec_fg']}; border: 1px solid {t['sec_border']}; padding: 1px 6px; border-radius: 2px; }}

/* danger */
QPushButton#btn_danger {{
    background-color: {t['danger']};
    color: white;
}}
QPushButton#btn_danger:hover {{ background-color: {t['danger_hover']}; }}

/* ── Inputs ───────────────────────────────────────────────────────── */
QLineEdit, QComboBox {{
    background: {t['input_bg']};
    border: 1px solid {t['input_border']};
    border-radius: 2px;
    padding: 5px 9px;
    color: {t['input_fg']};
}}
QLineEdit:focus, QComboBox:focus {{
    border-color: {t['input_focus']};
}}
QComboBox::drop-down {{ border: none; padding-right: 6px; }}
QComboBox QAbstractItemView {{
    background: {t['card_bg']};
    border: 1px solid {t['card_border']};
    color: {t['text_primary']};
    selection-background-color: {t['accent']};
    selection-color: {t['accent_text']};
}}

/* ── SpinBox — separate so up/down buttons stay visible ───────────── */
QSpinBox, QDoubleSpinBox {{
    background: {t['input_bg']};
    border: 1px solid {t['input_border']};
    border-radius: 2px;
    padding: 4px 4px 4px 9px;
    color: {t['input_fg']};
}}
QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {t['input_focus']};
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 22px;
    border-left: 1px solid {t['input_border']};
    border-bottom: 1px solid {t['input_border']};
    background: {t['input_bg']};
    border-top-right-radius: 2px;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 22px;
    border-left: 1px solid {t['input_border']};
    background: {t['input_bg']};
    border-bottom-right-radius: 2px;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background: {t['input_focus']};
}}
QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed,
QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed {{
    background: {t['accent_pressed']};
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    width: 8px; height: 8px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    width: 8px; height: 8px;
}}

/* ── Tables ───────────────────────────────────────────────────────── */
QTableWidget {{
    background: {t['table_bg']};
    alternate-background-color: {t['table_alt']};
    border: 1px solid {t['card_border']};
    border-radius: 0px;
    color: {t['text_primary']};
    gridline-color: {t['card_border']};
}}
QTableWidget::item:selected {{
    background: {t['table_sel']};
    color: {t['table_sel_fg']};
}}
QHeaderView::section {{
    background: {t['header_bg']};
    color: {t['header_fg']};
    border: none;
    border-bottom: 1px solid {t['card_border']};
    border-right: 1px solid {t['card_border']};
    padding: 5px 8px;
    font-weight: 600;
    font-size: 9pt;
}}
QHeaderView {{ background: transparent; }}

/* ── Progress bar ─────────────────────────────────────────────────── */
QProgressBar {{
    border: none;
    border-radius: 2px;
    background: {t['progress_bg']};
    text-align: center;
    font-size: 9pt;
    min-height: 14px;
    max-height: 14px;
}}
QProgressBar::chunk {{
    background-color: {t['accent']};
    border-radius: 2px;
}}

/* ── Status bar ───────────────────────────────────────────────────── */
QStatusBar {{
    background: {t['statusbar_bg']};
    color: {t['statusbar_fg']};
    font-size: 8.5pt;
}}

/* ── Splitter ─────────────────────────────────────────────────────── */
QSplitter::handle {{
    background: {t['sep']};
}}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical   {{ height: 1px; }}

/* ── Checkbox / Radio ─────────────────────────────────────────────── */
QRadioButton, QCheckBox {{
    spacing: 6px;
    color: {t['text_primary']};
    background: transparent;
}}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {t['check_border']};
    border-radius: 2px;
    background: {t['check_bg']};
}}
QCheckBox::indicator:checked {{
    background: {t['check_checked']};
    border-color: {t['check_checked']};
    image: none;
}}
QCheckBox::indicator:checked::after {{
    color: {t['check_mark']};
}}
QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {t['check_border']};
    border-radius: 7px;
    background: {t['check_bg']};
}}
QRadioButton::indicator:checked {{
    background: {t['check_checked']};
    border-color: {t['check_checked']};
}}

/* ── Frame separators ─────────────────────────────────────────────── */
QFrame[frameShape='4'] {{ color: {t['sep']}; }}
QFrame[frameShape='5'] {{ color: {t['sep']}; }}
"""
