"""
Main application window for Media Manager.

Layout (matches game_processor):
  QSplitter (Vertical)
    ├── top: Sidebar | QStackedWidget (pages)
    └── bottom: Shared LogWidget

Nav: Dashboard | Scan | Metadata | Failed Items | Organize | Generate HTML | Library | Settings
"""

import os
import sys
import webbrowser
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QLabel, QListWidget, QListWidgetItem, QStackedWidget,
    QPushButton, QComboBox, QFrame, QScrollArea,
    QSizePolicy as QSP, QStatusBar, QApplication,
    QGroupBox, QFormLayout, QCheckBox, QRadioButton, QButtonGroup,
    QProgressBar, QMessageBox,
)

from modules.gui.log_widget import LogWidget
from modules.gui.theme_manager import THEME_NAMES, build_stylesheet, _THEMES
from modules.gui.ui_state import UIState
from modules.gui.settings_page import SettingsPage

APP_VERSION = '1.0.0'
_ROOT = Path(__file__).parent.parent.parent

_PAGE_DASHBOARD  = 0
_PAGE_EXTRACT    = 1
_PAGE_SCAN       = 2
_PAGE_METADATA   = 3
_PAGE_FAILED     = 4
_PAGE_ORGANIZE   = 5
_PAGE_HTML       = 6
_PAGE_LIBRARY    = 7
_PAGE_SETTINGS   = 8


# ── Stat card ──────────────────────────────────────────────────────────────────

class _StatCard(QFrame):
    def __init__(self, label: str, value: str = '—', accent: str = '#2563eb', parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSP.Policy.Expanding, QSP.Policy.Fixed)
        self.setMinimumHeight(72)
        self._accent = accent
        self._apply_style('#ffffff', '#e2e8f0')

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(2)

        self._val = QLabel(value)
        self._val.setStyleSheet(f'font-size:22px; font-weight:bold; color:{accent}; background:transparent;')
        lay.addWidget(self._val)

        self._lbl = QLabel(label)
        self._lbl.setProperty('role', 'card_label')
        lay.addWidget(self._lbl)

    def set_value(self, v):
        self._val.setText(str(v))

    def _apply_style(self, bg: str, border: str):
        self.setStyleSheet(
            f'QFrame {{ background:{bg}; border:1px solid {border}; border-radius:2px; }}'
        )

    def apply_theme(self, card_bg: str, card_border: str):
        self._apply_style(card_bg, card_border)


# ── Wizard card ────────────────────────────────────────────────────────────────

class _WizardCard(QFrame):
    def __init__(self, title: str, subtitle: str, btn_text: str,
                 on_click, accent: str = '#2563eb', parent=None):
        super().__init__(parent)
        self.setObjectName('wizard_card')
        self.setSizePolicy(QSP.Policy.Expanding, QSP.Policy.Fixed)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(6)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(
            f'font-size:11pt; font-weight:bold; color:{accent}; background:transparent;'
        )
        lay.addWidget(lbl_title)

        lbl_sub = QLabel(subtitle)
        lbl_sub.setWordWrap(True)
        lbl_sub.setProperty('role', 'muted')
        lay.addWidget(lbl_sub)

        self._btn = QPushButton(btn_text)
        self._btn.setSizePolicy(QSP.Policy.Fixed, QSP.Policy.Fixed)
        self._btn.clicked.connect(on_click)
        lay.addWidget(self._btn)

    def set_enabled(self, enabled: bool):
        self._btn.setEnabled(enabled)


# ── Main Window ────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):

    def __init__(self, global_config):
        super().__init__()
        self._global_config = global_config
        self._ui_state   = UIState(str(global_config.ui_state_path()))
        self._plugin     = None
        self._lib_config = None
        self._browser_page = None
        self._worker     = None
        self._stat_cards = []
        self._active_progress = None   # QProgressBar of the currently-running step
        self._active_run_btn  = None   # QPushButton to re-enable on finish
        self._active_stop_btn = None   # Stop button to disable on finish

        self.setWindowTitle('Media Manager')
        self._apply_theme(global_config.theme)
        self._set_window_icon(global_config.theme)
        self._build_ui()
        self._ui_state.restore_window(self)
        self._load_library(global_config.active_library)

    # ── Theme / icon ──────────────────────────────────────────────────
    def _apply_theme(self, name: str):
        QApplication.instance().setStyleSheet(build_stylesheet(name))
        if hasattr(self, '_stat_cards') and self._stat_cards:
            t = _THEMES.get(name, _THEMES['Light'])
            for card in self._stat_cards:
                card.apply_theme(t['card_bg'], t['card_border'])

    def _set_window_icon(self, theme: str):
        dark_themes = {'Dark', 'Midnight', 'Slate'}
        if theme in dark_themes:
            icon_name = 'light_media_mgr.png'
        elif theme == 'Light':
            icon_name = 'dark_media_mgr.png'
        else:
            icon_name = 'color_media_mgr.png'
        icon_path = _ROOT / 'assets' / icon_name
        if not icon_path.exists():
            icon_path = _ROOT / 'assets' / 'color_media_mgr.png'
        if icon_path.exists():
            icon = QIcon(str(icon_path))
            self.setWindowIcon(QIcon())
            QApplication.instance().setWindowIcon(QIcon())
            QTimer.singleShot(50, lambda: (
                self.setWindowIcon(icon),
                QApplication.instance().setWindowIcon(icon),
            ))

    # ── Build UI ──────────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Vertical splitter: content on top, shared log at bottom
        self._main_splitter = QSplitter(Qt.Orientation.Vertical)
        root.addWidget(self._main_splitter)

        top = QWidget()
        top_lay = QHBoxLayout(top)
        top_lay.setContentsMargins(0, 0, 0, 0)
        top_lay.setSpacing(0)
        self._main_splitter.addWidget(top)

        top_lay.addWidget(self._build_sidebar())

        self._stack = QStackedWidget()
        self._stack.setObjectName('content_widget')
        top_lay.addWidget(self._stack, 1)

        # Shared log panel at bottom
        self._log = LogWidget()
        self._main_splitter.addWidget(self._log)
        self._main_splitter.setSizes([700, 200])
        self._main_splitter.setCollapsible(1, True)

        # Build all pages
        self._dash_page    = self._build_dashboard_page()
        self._extract_page = self._build_extract_page()
        self._scan_page    = self._build_scan_page()
        self._meta_page   = self._build_metadata_page()
        self._failed_page = self._build_simple_page(
            'Failed Items',
            'Review and manually assign genres to items that couldn\'t be matched.',
            'Open Failed Items Dialog', self._open_failed_dialog,
        )
        self._org_page  = self._build_simple_page(
            'Organize',
            'Generate a batch script that moves items into genre folders.\n'
            'Review the script before running — no files are moved until you execute it.',
            'Generate Organize Script', self._run_organizer,
        )
        self._html_page = self._build_simple_page(
            'Generate HTML',
            'Build the dynamic HTML library page from your metadata database.',
            'Generate HTML', self._run_html,
        )
        self._browser_placeholder = QWidget()
        self._settings_page = SettingsPage()

        for page in (
            self._dash_page,           # 0
            self._extract_page,        # 1
            self._scan_page,           # 2
            self._meta_page,           # 3
            self._failed_page,         # 4
            self._org_page,            # 5
            self._html_page,           # 6
            self._browser_placeholder, # 7
            self._settings_page,       # 8
        ):
            self._stack.addWidget(page)

        self._ui_state.restore_splitter(self._main_splitter, 'main_splitter')

        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage('Ready.')

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(210)
        sb = QVBoxLayout(sidebar)
        sb.setContentsMargins(0, 0, 0, 0)
        sb.setSpacing(0)

        lbl = QLabel('Media Manager')
        lbl.setObjectName('app_title')
        sb.addWidget(lbl)

        sub = QLabel('Multi-library tool')
        sub.setObjectName('app_subtitle')
        sb.addWidget(sub)

        lib_lbl = QLabel('Library')
        lib_lbl.setStyleSheet('padding: 8px 14px 2px 14px; font-size:8pt;')
        sb.addWidget(lib_lbl)

        self._lib_combo = QComboBox()
        self._lib_combo.setStyleSheet('combobox-popup: 0; margin: 0 10px; padding: 4px 8px;')
        self._lib_combo.view().setStyleSheet('max-height: 300px;')
        self._populate_lib_combo()
        self._lib_combo.currentTextChanged.connect(self._on_lib_changed)
        sb.addWidget(self._lib_combo)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet('color: #333;')
        sb.addWidget(sep)

        self._nav = QListWidget()
        self._nav.setObjectName('nav_list')
        for label in [
            'Dashboard', 'Extract', 'Scan', 'Metadata',
            'Failed Items', 'Organize', 'Generate HTML',
            'Library', 'Settings',
        ]:
            self._nav.addItem(QListWidgetItem(label))
        self._nav.setCurrentRow(0)
        self._nav.currentRowChanged.connect(self._on_nav_changed)
        sb.addWidget(self._nav, 1)

        theme_lbl = QLabel('Theme')
        theme_lbl.setStyleSheet('padding: 8px 14px 2px 14px; font-size:8pt;')
        sb.addWidget(theme_lbl)

        self._theme_combo = QComboBox()
        self._theme_combo.setStyleSheet('combobox-popup: 0; margin: 0 10px; padding: 4px 8px;')
        self._theme_combo.view().setStyleSheet('max-height: 300px;')
        self._theme_combo.addItems(THEME_NAMES)
        idx = self._theme_combo.findText(self._global_config.theme)
        if idx >= 0:
            self._theme_combo.setCurrentIndex(idx)
        self._theme_combo.currentTextChanged.connect(self._on_theme_changed)
        sb.addWidget(self._theme_combo)

        ver = QLabel(f'v{APP_VERSION}')
        ver.setObjectName('ver_label')
        sb.addWidget(ver)

        return sidebar

    def _populate_lib_combo(self):
        self._lib_combo.blockSignals(True)
        self._lib_combo.clear()
        for lib in self._global_config.available_libraries():
            self._lib_combo.addItem(lib.capitalize(), userData=lib)
        self._lib_combo.blockSignals(False)

    # ── Dashboard page ────────────────────────────────────────────────
    def _build_dashboard_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(12)

        title = QLabel('Dashboard')
        title.setProperty('role', 'title')
        lay.addWidget(title)

        self._dash_lib_lbl = QLabel('')
        self._dash_lib_lbl.setProperty('role', 'subtitle')
        lay.addWidget(self._dash_lib_lbl)

        # Wizard cards
        wizard_row = QHBoxLayout()
        wizard_row.setSpacing(10)
        self._wiz_new = _WizardCard(
            'New Items Wizard',
            'Scan → Metadata → Organize → HTML in one guided flow.',
            'Launch', self._open_new_items_wizard, '#2563eb',
        )
        wizard_row.addWidget(self._wiz_new)
        self._wiz_refresh = _WizardCard(
            'Refresh Database Wizard',
            'Re-fetch metadata and regenerate the HTML library page.',
            'Launch', self._open_refresh_wizard, '#0891b2',
        )
        wizard_row.addWidget(self._wiz_refresh)
        self._wiz_rebuild = _WizardCard(
            'Rebuild from Scratch',
            'Wipe metadata DB and scan list, then re-fetch everything from scratch.',
            'Launch', self._open_rebuild_wizard, '#ef4444',
        )
        wizard_row.addWidget(self._wiz_rebuild)
        lay.addLayout(wizard_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        lay.addWidget(sep)

        # Stat cards
        stats_row = QHBoxLayout()
        stats_row.setSpacing(10)
        self._card_scanned   = _StatCard('Items Scanned',   '—', '#2563eb')
        self._card_found     = _StatCard('Metadata Found',  '—', '#10b981')
        self._card_failed    = _StatCard('Metadata Failed', '—', '#ef4444')
        self._card_organized = _StatCard('With Genre',      '—', '#f59e0b')
        self._stat_cards = [
            self._card_scanned, self._card_found,
            self._card_failed, self._card_organized,
        ]
        for c in self._stat_cards:
            stats_row.addWidget(c)
        lay.addLayout(stats_row)

        self._dash_paths_lbl = QLabel('')
        self._dash_paths_lbl.setProperty('role', 'muted')
        self._dash_paths_lbl.setWordWrap(True)
        lay.addWidget(self._dash_paths_lbl)

        html_row = QHBoxLayout()
        self._dash_btn_html = QPushButton('Open HTML Library')
        self._dash_btn_html.clicked.connect(self._open_html)
        self._dash_btn_html.setVisible(False)
        self._dash_btn_html.setSizePolicy(QSP.Policy.Fixed, QSP.Policy.Fixed)
        html_row.addWidget(self._dash_btn_html)
        html_row.addStretch()
        lay.addLayout(html_row)

        lay.addStretch()
        scroll.setWidget(inner)
        return scroll

    # ── Extract page ──────────────────────────────────────────────────
    def _build_extract_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(10)

        lbl = QLabel('Extract Archives')
        lbl.setProperty('role', 'title')
        lay.addWidget(lbl)

        # ── Archive list ──────────────────────────────────────────────
        list_hdr = QHBoxLayout()
        self._extract_count_lbl = QLabel('No source folder configured.')
        self._extract_count_lbl.setProperty('role', 'muted')
        list_hdr.addWidget(self._extract_count_lbl)
        list_hdr.addStretch()
        btn_refresh = QPushButton('Refresh')
        btn_refresh.setSizePolicy(QSP.Policy.Fixed, QSP.Policy.Fixed)
        btn_refresh.clicked.connect(self._refresh_extract_list)
        list_hdr.addWidget(btn_refresh)
        lay.addLayout(list_hdr)

        self._extract_list = QListWidget()
        self._extract_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self._extract_list.setMinimumHeight(120)
        self._extract_list.setMaximumHeight(240)
        lay.addWidget(self._extract_list)

        # ── Options ───────────────────────────────────────────────────
        grp = QGroupBox('Options')
        grp_lay = QVBoxLayout(grp)

        self._extract_path_lbl = QLabel('')
        self._extract_path_lbl.setProperty('role', 'muted')
        grp_lay.addWidget(self._extract_path_lbl)

        self._extract_tool_lbl = QLabel('')
        self._extract_tool_lbl.setProperty('role', 'muted')
        grp_lay.addWidget(self._extract_tool_lbl)

        self._extract_delete = QCheckBox('Delete archive after successful extraction')
        self._extract_delete.setChecked(True)
        grp_lay.addWidget(self._extract_delete)

        self._extract_ssh = QCheckBox('Extract on QNAP via SSH (recommended for large archives)')
        grp_lay.addWidget(self._extract_ssh)

        self._extract_ssh_note = QLabel('SSH settings configured in Settings page.')
        self._extract_ssh_note.setProperty('role', 'muted')
        self._extract_ssh_note.setContentsMargins(20, 0, 0, 0)
        grp_lay.addWidget(self._extract_ssh_note)

        lay.addWidget(grp)

        btn_row = QHBoxLayout()
        btn = QPushButton('Extract Now')
        btn.setSizePolicy(QSP.Policy.Fixed, QSP.Policy.Fixed)
        btn.clicked.connect(self._run_extract)
        btn_row.addWidget(btn)
        stop = QPushButton('Stop')
        stop.setSizePolicy(QSP.Policy.Fixed, QSP.Policy.Fixed)
        stop.setEnabled(False)
        stop.clicked.connect(self._stop_worker)
        btn_row.addWidget(stop)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        progress = QProgressBar()
        progress.setRange(0, 0)
        progress.setVisible(False)
        lay.addWidget(progress)

        page._run_btn  = btn
        page._stop_btn = stop
        page._progress = progress
        lay.addStretch()
        return page

    def _refresh_extract_list(self):
        """Scan source folder and populate the archive list."""
        if not hasattr(self, '_extract_list'):
            return
        from modules.core.archive_extractor import find_archives, clean_folder_name
        src = self._lib_config.data.get('source_folder', '') or ''
        self._extract_list.clear()
        if not src:
            self._extract_count_lbl.setText('No source folder configured.')
            return
        archives = find_archives(src)
        if not archives:
            self._extract_count_lbl.setText('No archives found.')
            return
        self._extract_count_lbl.setText(f'{len(archives)} archive(s) found:')
        for a in archives:
            size_mb = a.stat().st_size / (1024 * 1024)
            size_str = f'{size_mb / 1024:.1f} GB' if size_mb >= 1024 else f'{size_mb:.0f} MB'
            folder = clean_folder_name(a.name)
            dest = a.parent / folder
            status = '  [already extracted]' if dest.exists() else ''
            self._extract_list.addItem(
                f'  {a.name}  ({size_str})  →  {folder}/{status}'
            )

    def _update_extract_labels(self):
        if not hasattr(self, '_extract_path_lbl'):
            return
        from modules.core.archive_extractor import find_tool
        src = self._lib_config.data.get('source_folder', '') or ''
        if src:
            self._extract_path_lbl.setText(f'Source folder: {src}')
        else:
            self._extract_path_lbl.setText(
                'No source folder configured — set in Settings.'
            )
        configured = self._lib_config.data.get('extractor_path', '') or ''
        tool_path, tool_type = find_tool(configured)
        if tool_path:
            self._extract_tool_lbl.setText(f'Tool: {tool_path}  ({tool_type})')
        else:
            self._extract_tool_lbl.setText(
                'No extraction tool found — install 7-Zip or WinRAR, '
                'or set Extractor Path in Settings.'
            )
        self._refresh_extract_list()

    # ── Scan page ─────────────────────────────────────────────────────
    def _build_scan_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(10)

        lbl = QLabel('Scan')
        lbl.setProperty('role', 'title')
        lay.addWidget(lbl)

        desc = QLabel(
            'Scan source folder for new items and create scan_list.json.\n'
            'For libraries without a separate source, scans the destination directly.'
        )
        desc.setProperty('role', 'muted')
        desc.setWordWrap(True)
        lay.addWidget(desc)

        grp = QGroupBox('Options')
        grp_lay = QVBoxLayout(grp)
        self._scan_force = QCheckBox('Force rescan (ignore existing scan_list.json)')
        self._scan_force.setChecked(True)
        grp_lay.addWidget(self._scan_force)
        self._scan_path_lbl = QLabel('')
        self._scan_path_lbl.setProperty('role', 'muted')
        grp_lay.addWidget(self._scan_path_lbl)
        lay.addWidget(grp)

        btn_row = QHBoxLayout()
        btn = QPushButton('Scan Now')
        btn.setSizePolicy(QSP.Policy.Fixed, QSP.Policy.Fixed)
        btn.clicked.connect(self._run_scan)
        btn_row.addWidget(btn)
        stop = QPushButton('Stop')
        stop.setSizePolicy(QSP.Policy.Fixed, QSP.Policy.Fixed)
        stop.setEnabled(False)
        stop.clicked.connect(self._stop_worker)
        btn_row.addWidget(stop)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        progress = QProgressBar()
        progress.setRange(0, 0)
        progress.setVisible(False)
        lay.addWidget(progress)

        page._run_btn  = btn
        page._stop_btn = stop
        page._progress = progress
        lay.addStretch()
        return page

    # ── Metadata page ─────────────────────────────────────────────────
    def _build_metadata_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(10)

        lbl = QLabel('Metadata')
        lbl.setProperty('role', 'title')
        lay.addWidget(lbl)

        desc = QLabel('Fetch metadata from providers for scanned items.')
        desc.setProperty('role', 'muted')
        desc.setWordWrap(True)
        lay.addWidget(desc)

        grp = QGroupBox('Query Mode')
        grp_lay = QVBoxLayout(grp)

        self._meta_radio_new  = QRadioButton('New items only — process scan_list.json (skips already found)')
        self._meta_radio_full = QRadioButton('Full collection — re-query all items in destination folder')
        self._meta_radio_new.setChecked(True)

        self._meta_mode_grp = QButtonGroup(self)
        self._meta_mode_grp.addButton(self._meta_radio_new,  1)
        self._meta_mode_grp.addButton(self._meta_radio_full, 2)

        warn = QLabel(
            'Full collection queries all items found in the destination folder. '
            'Skips items already in metadata_progress.json. May take several minutes.'
        )
        warn.setProperty('role', 'muted')
        warn.setWordWrap(True)
        warn.setVisible(False)
        self._meta_radio_full.toggled.connect(warn.setVisible)

        grp_lay.addWidget(self._meta_radio_new)
        grp_lay.addWidget(self._meta_radio_full)
        grp_lay.addWidget(warn)
        lay.addWidget(grp)

        btn_row = QHBoxLayout()
        btn = QPushButton('Start Metadata Fetch')
        btn.setSizePolicy(QSP.Policy.Fixed, QSP.Policy.Fixed)
        btn.clicked.connect(self._run_metadata)
        btn_row.addWidget(btn)
        stop = QPushButton('Stop')
        stop.setSizePolicy(QSP.Policy.Fixed, QSP.Policy.Fixed)
        stop.setEnabled(False)
        stop.clicked.connect(self._stop_worker)
        btn_row.addWidget(stop)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        progress = QProgressBar()
        progress.setRange(0, 0)
        progress.setVisible(False)
        lay.addWidget(progress)

        page._run_btn  = btn
        page._stop_btn = stop
        page._progress = progress
        lay.addStretch()
        return page

    # ── Generic step page (Organize / HTML / Failed) ──────────────────
    def _build_simple_page(self, title: str, description: str,
                           btn_label: str, action_slot) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(10)

        lbl = QLabel(title)
        lbl.setProperty('role', 'title')
        lay.addWidget(lbl)

        desc = QLabel(description)
        desc.setProperty('role', 'muted')
        desc.setWordWrap(True)
        lay.addWidget(desc)

        btn_row = QHBoxLayout()
        btn = QPushButton(btn_label)
        btn.setSizePolicy(QSP.Policy.Fixed, QSP.Policy.Fixed)
        btn.clicked.connect(action_slot)
        btn_row.addWidget(btn)
        stop = QPushButton('Stop')
        stop.setSizePolicy(QSP.Policy.Fixed, QSP.Policy.Fixed)
        stop.setEnabled(False)
        stop.clicked.connect(self._stop_worker)
        btn_row.addWidget(stop)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        progress = QProgressBar()
        progress.setRange(0, 0)
        progress.setVisible(False)
        lay.addWidget(progress)

        page._run_btn  = btn
        page._stop_btn = stop
        page._progress = progress
        lay.addStretch()
        return page

    # ── Library switching ─────────────────────────────────────────────
    def _load_library(self, media_type: str):
        import importlib
        from modules.core.config_manager import LibraryConfig

        self._lib_config = LibraryConfig(media_type)

        plugin_map = {
            'games':  'modules.media_types.games.GamesPlugin',
            'movies': 'modules.media_types.movies.MoviesPlugin',
            'books':  'modules.media_types.books.BooksPlugin',
            'comics': 'modules.media_types.comics.ComicsPlugin',
            'music':  'modules.media_types.music.MusicPlugin',
        }
        module_path, class_name = plugin_map[media_type].rsplit('.', 1)
        mod = importlib.import_module(module_path)
        self._plugin = getattr(mod, class_name)()

        self._lib_combo.blockSignals(True)
        idx = self._lib_combo.findData(media_type)
        if idx >= 0:
            self._lib_combo.setCurrentIndex(idx)
        self._lib_combo.blockSignals(False)

        self._rebuild_browser_page()
        self._settings_page.load_library(self._lib_config)
        self._refresh_dashboard()
        self._update_organize_nav()
        self._update_scan_path_label()
        self._update_extract_labels()
        self._status_bar.showMessage(f'Library: {self._plugin.name}')

    def _update_scan_path_label(self):
        if not hasattr(self, '_scan_path_lbl'):
            return
        src  = str(self._lib_config.data.get('source_folder', '') or '')
        dest = str(self._lib_config.data.get('destination_base', '') or '')
        if src and src != dest:
            self._scan_path_lbl.setText(f'Source: {src}')
        elif dest:
            self._scan_path_lbl.setText(f'Scanning destination directly: {dest}')
        else:
            self._scan_path_lbl.setText('No folder configured — set paths in Settings.')

    def _update_organize_nav(self):
        enabled = self._lib_config.data.get('organize_enabled', True)
        item = self._nav.item(_PAGE_ORGANIZE)
        if enabled:
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        else:
            item.setFlags(item.flags() & ~(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable))

    def _rebuild_browser_page(self):
        from modules.gui.library_browser import LibraryBrowser
        old = self._stack.widget(_PAGE_LIBRARY)
        if hasattr(old, 'stop_worker'):
            old.stop_worker()
        if hasattr(old, 'save_state'):
            old.save_state()
        new_page = LibraryBrowser(self._lib_config, self._plugin, self._ui_state)
        self._stack.insertWidget(_PAGE_LIBRARY, new_page)
        self._stack.removeWidget(old)
        old.deleteLater()
        self._browser_page = new_page

    def _on_lib_changed(self, _):
        idx = self._lib_combo.currentIndex()
        media_type = self._lib_combo.itemData(idx)
        if media_type:
            self._load_library(media_type)
            self._global_config.set_active_library(media_type)

    # ── Navigation ────────────────────────────────────────────────────
    def _on_nav_changed(self, row: int):
        self._stack.setCurrentIndex(row)
        if row == _PAGE_DASHBOARD:
            self._refresh_dashboard()
        elif row == _PAGE_EXTRACT:
            self._refresh_extract_list()
        elif row == _PAGE_LIBRARY and self._browser_page and not self._browser_page._state_loaded:
            self._browser_page.load_data()

    # ── Dashboard refresh ─────────────────────────────────────────────
    def _refresh_dashboard(self):
        import json

        lib_name = self._plugin.name if self._plugin else ''
        src  = self._lib_config.data.get('source_folder', '') or '—'
        dest = self._lib_config.data.get('destination_base', '') or '—'
        if self._plugin:
            self._dash_lib_lbl.setText(
                f'{self._plugin.icon} {lib_name}  |  Source: {src}  |  Destination: {dest}'
            )

        scanned = found = failed = organized = 0

        scan_file = self._lib_config.scan_list_file
        if scan_file and Path(scan_file).exists():
            try:
                with open(scan_file, 'r', encoding='utf-8') as f:
                    scanned = len(json.load(f))
            except Exception:
                pass

        meta_file = self._lib_config.metadata_file
        if meta_file and Path(meta_file).exists():
            try:
                with open(meta_file, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                items = meta.get('processed_items', meta.get('processed_games', {}))
                found     = sum(1 for v in items.values() if v.get('igdb_found') or v.get('found'))
                failed    = len(items) - found
                organized = sum(
                    1 for v in items.values()
                    if (v.get('igdb_found') or v.get('found')) and v.get('genre')
                )
            except Exception:
                pass

        self._card_scanned.set_value(scanned)
        self._card_found.set_value(found)
        self._card_failed.set_value(failed)
        self._card_organized.set_value(organized)

        html_file = self._lib_config.html_file
        self._dash_btn_html.setVisible(bool(html_file and Path(html_file).exists()))

        t = _THEMES.get(self._global_config.theme, _THEMES['Light'])
        for card in self._stat_cards:
            card.apply_theme(t['card_bg'], t['card_border'])

    # ── Workers ───────────────────────────────────────────────────────
    def _run_extract(self):
        delete_after = self._extract_delete.isChecked()
        if self._extract_ssh.isChecked():
            from modules.gui.workers import ExtractSSHWorker
            w = ExtractSSHWorker(self._lib_config, self._log.stream, delete_after=delete_after)
        else:
            from modules.gui.workers import ExtractWorker
            w = ExtractWorker(self._lib_config, self._log.stream, delete_after=delete_after)
        self._start_worker(w, self._extract_page)

    def _run_scan(self):
        from modules.gui.workers import ScanWorker
        force = self._scan_force.isChecked()
        w = ScanWorker(self._lib_config, self._plugin, self._log.stream, force=force)
        self._start_worker(w, self._scan_page)

    def _run_metadata(self):
        from modules.gui.workers import MetadataWorker
        full = self._meta_radio_full.isChecked()
        if full:
            ans = QMessageBox.question(
                self, 'Full Collection Scan',
                'Re-query all items in the destination folder not yet in the database.\n\nContinue?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return
        w = MetadataWorker(self._lib_config, self._plugin, self._log.stream,
                           full_collection=full)
        self._start_worker(w, self._meta_page)

    def _run_organizer(self):
        from modules.gui.workers import OrganizerWorker
        self._start_worker(
            OrganizerWorker(self._lib_config, self._plugin, self._log.stream),
            self._org_page,
        )

    def _run_html(self):
        from modules.gui.workers import HTMLWorker
        self._start_worker(
            HTMLWorker(self._lib_config, self._plugin, self._log.stream),
            self._html_page,
        )

    def _start_worker(self, worker, page=None):
        if self._worker and self._worker.isRunning():
            self._status_bar.showMessage('A task is already running.')
            return
        self._worker = worker
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()
        self._status_bar.showMessage('Running...')

        if page and hasattr(page, '_progress'):
            self._active_progress = page._progress
            self._active_run_btn  = page._run_btn
            self._active_stop_btn = getattr(page, '_stop_btn', None)
            page._progress.setVisible(True)
            page._run_btn.setEnabled(False)
            if self._active_stop_btn:
                self._active_stop_btn.setEnabled(True)

    def _stop_worker(self):
        if self._worker and self._worker.isRunning():
            if hasattr(self._worker, 'request_stop'):
                self._worker.request_stop()
                self._status_bar.showMessage('Stopping — finishing current item...')
            if self._active_stop_btn:
                self._active_stop_btn.setEnabled(False)

    def _on_worker_finished(self, success: bool, message: str):
        self._status_bar.showMessage(('Done: ' if success else 'Error: ') + message)
        if self._active_progress:
            self._active_progress.setVisible(False)
            self._active_progress = None
        if self._active_run_btn:
            self._active_run_btn.setEnabled(True)
            self._active_run_btn = None
        if self._active_stop_btn:
            self._active_stop_btn.setEnabled(False)
            self._active_stop_btn = None
        self._refresh_dashboard()

    # ── Dialogs ───────────────────────────────────────────────────────
    def _open_new_items_wizard(self):
        from modules.gui.wizard import NewItemsWizard
        NewItemsWizard(self._lib_config, self._plugin, self).exec()
        self._refresh_dashboard()

    def _open_refresh_wizard(self):
        from modules.gui.wizard import RefreshDBWizard
        RefreshDBWizard(self._lib_config, self._plugin, self).exec()
        self._refresh_dashboard()

    def _open_rebuild_wizard(self):
        from modules.gui.wizard import RebuildWizard
        RebuildWizard(self._lib_config, self._plugin, self).exec()
        self._refresh_dashboard()

    def _open_failed_dialog(self):
        from modules.gui.failed_dialog import FailedItemsDialog
        FailedItemsDialog(self._lib_config, self._plugin, self).exec()

    def _open_html(self):
        html_file = self._lib_config.html_file
        if html_file and Path(html_file).exists():
            webbrowser.open(Path(html_file).resolve().as_uri())

    # ── Theme ─────────────────────────────────────────────────────────
    def _on_theme_changed(self, name: str):
        self._apply_theme(name)
        self._set_window_icon(name)
        self._global_config.set_theme(name)

    # ── Close ─────────────────────────────────────────────────────────
    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            ans = QMessageBox.question(
                self, 'Operation Running',
                'A task is still running. Quit anyway?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._worker.quit()
            self._worker.wait(3000)

        # Save library browser column state explicitly (matches game_processor pattern)
        if self._browser_page and hasattr(self._browser_page, 'save_state'):
            self._browser_page.save_state()

        self._ui_state.save_window(self)
        self._ui_state.save_splitter(self._main_splitter, 'main_splitter')
        super().closeEvent(event)
