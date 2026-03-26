"""
Main application window for Media Manager.

Layout (matches game_processor):
  QSplitter (Vertical)
    ├── top: Sidebar | QStackedWidget (pages)
    └── bottom: Shared LogWidget

Nav: Dashboard | Scan | Metadata | Failed Items | Organize | Generate HTML | Library | Settings
"""

import math
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
    QProgressBar, QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QInputDialog,
)

from modules.gui.log_widget import LogWidget
from modules.gui.table_utils import CITableWidgetItem
from modules.gui.theme_manager import THEME_NAMES, build_stylesheet, _THEMES, get_theme_names
from modules.gui.theme_editor import ThemeEditor
from modules.gui.ui_state import UIState
from modules.gui.settings_page import SettingsPage

APP_VERSION = '1.0.0'
_ROOT = Path(__file__).parent.parent.parent

_PAGE_DASHBOARD   = 0
_PAGE_EXTRACT     = 1
_PAGE_OPERATIONS  = 2
_PAGE_LIBRARY     = 3
_PAGE_SETTINGS    = 4
_PAGE_THEMES      = 5


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
        self._val.setProperty('role', 'stat_value')
        self._val.setStyleSheet(f'color:{accent}; background:transparent;')
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
        lbl_title.setProperty('role', 'card_title')
        lbl_title.setStyleSheet(f'color:{accent}; background:transparent;')
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

        self._nav_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._nav_splitter.setChildrenCollapsible(False)
        self._main_splitter.addWidget(self._nav_splitter)

        self._nav_splitter.addWidget(self._build_sidebar())

        self._stack = QStackedWidget()
        self._stack.setObjectName('content_widget')
        self._nav_splitter.addWidget(self._stack)
        self._nav_splitter.setSizes([210, 800])
        self._nav_splitter.setStretchFactor(0, 0)
        self._nav_splitter.setStretchFactor(1, 1)

        # Shared log panel at bottom (hidden on non-operational tabs)
        self._log = LogWidget()
        self._main_splitter.addWidget(self._log)
        self._main_splitter.setSizes([700, 200])
        self._main_splitter.setCollapsible(1, True)
        self._log.setVisible(False)  # hidden until an operational tab is selected

        # Build all pages
        self._dash_page        = self._build_dashboard_page()
        self._extract_page     = self._build_extract_page()
        self._operations_page  = self._build_operations_page()
        self._browser_placeholder = QWidget()
        self._settings_page    = SettingsPage()
        self._theme_editor     = ThemeEditor()
        self._theme_editor.theme_applied.connect(self._on_theme_editor_applied)
        self._theme_editor.themes_changed.connect(self._on_themes_changed)

        for page in (
            self._dash_page,            # 0
            self._extract_page,         # 1
            self._operations_page,      # 2
            self._browser_placeholder,  # 3
            self._settings_page,        # 4
            self._theme_editor,         # 5
        ):
            self._stack.addWidget(page)

        self._ui_state.restore_splitter(self._main_splitter, 'main_splitter')
        self._ui_state.restore_splitter(self._nav_splitter, 'nav_splitter')

        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage('Ready.')

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName('sidebar')
        sidebar.setMinimumWidth(140)
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
        lib_lbl.setObjectName('sidebar_section')
        sb.addWidget(lib_lbl)

        self._lib_combo = QComboBox()
        self._lib_combo.setStyleSheet('combobox-popup: 0; margin: 0 10px; padding: 4px 8px;')
        self._lib_combo.view().setStyleSheet('max-height: 300px;')
        self._populate_lib_combo()
        self._lib_combo.currentTextChanged.connect(self._on_lib_changed)
        sb.addWidget(self._lib_combo)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet('color: palette(mid);')
        sb.addWidget(sep)

        self._nav = QListWidget()
        self._nav.setObjectName('nav_list')
        for label in [
            'Dashboard', 'Extract', 'Operations',
            'Library', 'Settings', 'Themes',
        ]:
            self._nav.addItem(QListWidgetItem(label))
        self._nav.setCurrentRow(0)
        self._nav.currentRowChanged.connect(self._on_nav_changed)
        sb.addWidget(self._nav, 1)

        theme_lbl = QLabel('Theme')
        theme_lbl.setObjectName('sidebar_section')
        sb.addWidget(theme_lbl)

        self._theme_combo = QComboBox()
        self._theme_combo.setStyleSheet('combobox-popup: 0; margin: 0 10px; padding: 4px 8px;')
        self._theme_combo.view().setStyleSheet('max-height: 300px;')
        self._theme_combo.addItems(get_theme_names())
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

        # ── Genres table ──────────────────────────────────────────────
        self._genres_grp = QGroupBox('Genres')
        genres_lay = QVBoxLayout(self._genres_grp)

        self._genres_table = QTableWidget()
        self._genres_table.setColumnCount(6)
        self._genres_table.setHorizontalHeaderLabels(
            ['Genre', '#', 'Genre', '#', 'Genre', '#']
        )
        hdr = self._genres_table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr.setSectionsMovable(False)  # fixed layout for 3-column display
        self._genres_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._genres_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._genres_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._genres_table.setAlternatingRowColors(True)
        self._genres_table.verticalHeader().setVisible(False)
        self._genres_table.setMinimumHeight(180)
        self._genres_table.doubleClicked.connect(self._genre_rename)
        genres_lay.addWidget(self._genres_table)

        genre_btns = QHBoxLayout()
        self._btn_genre_add    = QPushButton('Add')
        self._btn_genre_rename = QPushButton('Rename')
        self._btn_genre_rename.setObjectName('btn_secondary')
        self._btn_genre_del    = QPushButton('Delete')
        self._btn_genre_del.setObjectName('btn_secondary')
        self._btn_genre_add.clicked.connect(self._genre_add)
        self._btn_genre_rename.clicked.connect(self._genre_rename)
        self._btn_genre_del.clicked.connect(self._genre_delete)
        for b in (self._btn_genre_add, self._btn_genre_rename, self._btn_genre_del):
            b.setSizePolicy(QSP.Policy.Fixed, QSP.Policy.Fixed)
            genre_btns.addWidget(b)
        genre_btns.addStretch()
        genres_lay.addLayout(genre_btns)

        lay.addWidget(self._genres_grp)
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
    def _build_operations_page(self) -> QWidget:
        """Single page combining Scan, Metadata, Failed Items, Organize, Generate HTML."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(16)

        title = QLabel('Operations')
        title.setProperty('role', 'title')
        lay.addWidget(title)

        def _make_section(group_title, desc_text, btn_label, slot, has_stop=True):
            grp = QGroupBox(group_title)
            gl = QVBoxLayout(grp)
            if desc_text:
                d = QLabel(desc_text)
                d.setProperty('role', 'muted')
                d.setWordWrap(True)
                gl.addWidget(d)
            row = QHBoxLayout()
            btn = QPushButton(btn_label)
            btn.setSizePolicy(QSP.Policy.Fixed, QSP.Policy.Fixed)
            btn.clicked.connect(slot)
            row.addWidget(btn)
            stop = None
            if has_stop:
                stop = QPushButton('Stop')
                stop.setSizePolicy(QSP.Policy.Fixed, QSP.Policy.Fixed)
                stop.setEnabled(False)
                stop.clicked.connect(self._stop_worker)
                row.addWidget(stop)
            row.addStretch()
            gl.addLayout(row)
            prog = QProgressBar()
            prog.setRange(0, 0)
            prog.setVisible(False)
            gl.addWidget(prog)
            return grp, btn, stop, prog

        # ── Scan ──────────────────────────────────────────────────────
        scan_grp = QGroupBox('Scan')
        scan_lay = QVBoxLayout(scan_grp)
        scan_desc = QLabel(
            'Scan source folder for new items.\n'
            'For libraries without a separate source, scans the destination directly.'
        )
        scan_desc.setProperty('role', 'muted')
        scan_desc.setWordWrap(True)
        scan_lay.addWidget(scan_desc)
        self._scan_force = QCheckBox('Force rescan (ignore existing scan list)')
        self._scan_force.setChecked(True)
        scan_lay.addWidget(self._scan_force)
        self._scan_path_lbl = QLabel('')
        self._scan_path_lbl.setProperty('role', 'muted')
        scan_lay.addWidget(self._scan_path_lbl)
        scan_row = QHBoxLayout()
        self._scan_run_btn = QPushButton('Scan Now')
        self._scan_run_btn.setSizePolicy(QSP.Policy.Fixed, QSP.Policy.Fixed)
        self._scan_run_btn.clicked.connect(self._run_scan)
        self._scan_stop_btn = QPushButton('Stop')
        self._scan_stop_btn.setSizePolicy(QSP.Policy.Fixed, QSP.Policy.Fixed)
        self._scan_stop_btn.setEnabled(False)
        self._scan_stop_btn.clicked.connect(self._stop_worker)
        scan_row.addWidget(self._scan_run_btn)
        scan_row.addWidget(self._scan_stop_btn)
        scan_row.addStretch()
        scan_lay.addLayout(scan_row)
        self._scan_progress = QProgressBar()
        self._scan_progress.setRange(0, 0)
        self._scan_progress.setVisible(False)
        scan_lay.addWidget(self._scan_progress)
        lay.addWidget(scan_grp)

        # ── Metadata ──────────────────────────────────────────────────
        meta_grp = QGroupBox('Metadata')
        meta_lay = QVBoxLayout(meta_grp)
        meta_desc = QLabel('Fetch metadata from providers for scanned items.')
        meta_desc.setProperty('role', 'muted')
        meta_desc.setWordWrap(True)
        meta_lay.addWidget(meta_desc)
        self._meta_radio_new  = QRadioButton('New items only (skips already matched)')
        self._meta_radio_full = QRadioButton('Full collection — re-query all items in destination')
        self._meta_radio_new.setChecked(True)
        self._meta_mode_grp = QButtonGroup(self)
        self._meta_mode_grp.addButton(self._meta_radio_new,  1)
        self._meta_mode_grp.addButton(self._meta_radio_full, 2)
        meta_lay.addWidget(self._meta_radio_new)
        meta_lay.addWidget(self._meta_radio_full)
        meta_row = QHBoxLayout()
        self._meta_run_btn = QPushButton('Start Metadata Fetch')
        self._meta_run_btn.setSizePolicy(QSP.Policy.Fixed, QSP.Policy.Fixed)
        self._meta_run_btn.clicked.connect(self._run_metadata)
        self._meta_stop_btn = QPushButton('Stop')
        self._meta_stop_btn.setSizePolicy(QSP.Policy.Fixed, QSP.Policy.Fixed)
        self._meta_stop_btn.setEnabled(False)
        self._meta_stop_btn.clicked.connect(self._stop_worker)
        meta_row.addWidget(self._meta_run_btn)
        meta_row.addWidget(self._meta_stop_btn)
        meta_row.addStretch()
        meta_lay.addLayout(meta_row)
        self._meta_progress = QProgressBar()
        self._meta_progress.setRange(0, 0)
        self._meta_progress.setVisible(False)
        meta_lay.addWidget(self._meta_progress)
        lay.addWidget(meta_grp)

        # ── Failed Items ──────────────────────────────────────────────
        failed_grp, self._failed_run_btn, _, _fp = _make_section(
            'Failed Items',
            'Review items that couldn\'t be matched and manually assign genres.',
            'Open Failed Items Dialog',
            self._open_failed_dialog,
            has_stop=False,
        )
        _fp.setVisible(False)
        btn_clear_failed = QPushButton('Clear Failed Items')
        btn_clear_failed.setObjectName('btn_danger')
        btn_clear_failed.setSizePolicy(QSP.Policy.Fixed, QSP.Policy.Fixed)
        btn_clear_failed.setToolTip('Delete all failed items from the database.')
        btn_clear_failed.clicked.connect(self._clear_failed_items)
        # Insert button into the existing button row (first QHBoxLayout in failed_grp)
        for i in range(failed_grp.layout().count()):
            item = failed_grp.layout().itemAt(i)
            if item and item.layout() and isinstance(item.layout(), QHBoxLayout):
                item.layout().insertWidget(1, btn_clear_failed)
                break
        lay.addWidget(failed_grp)

        # ── Organize ──────────────────────────────────────────────────
        self._org_grp, self._org_run_btn, self._org_stop_btn, self._org_progress = _make_section(
            'Organize',
            'Generate a batch script that moves items into genre folders.\n'
            'Review the script before running — no files are moved until you execute it.',
            'Generate Organize Script',
            self._run_organizer,
        )
        lay.addWidget(self._org_grp)

        # ── Generate HTML ─────────────────────────────────────────────
        html_grp, self._html_run_btn, self._html_stop_btn, self._html_progress = _make_section(
            'Generate HTML',
            'Build the dynamic HTML library page from your metadata.',
            'Generate HTML',
            self._run_html,
        )
        lay.addWidget(html_grp)

        # ── Sanitize Folder Names ─────────────────────────────────────
        san_grp = QGroupBox('Sanitize Folder Names')
        san_lay = QVBoxLayout(san_grp)
        san_desc = QLabel(
            'Bulk-rename folders in your library: replaces dots, underscores and dashes with '
            'spaces, strips version numbers and scene-group tags (e.g. TENOKE, v1.401).\n'
            'A preview dialog lets you review and edit each name before any files are touched.'
        )
        san_desc.setProperty('role', 'muted')
        san_desc.setWordWrap(True)
        san_lay.addWidget(san_desc)
        san_row = QHBoxLayout()
        self._san_btn = QPushButton('Open Sanitizer')
        self._san_btn.setSizePolicy(QSP.Policy.Fixed, QSP.Policy.Fixed)
        self._san_btn.clicked.connect(self._open_sanitizer)
        san_row.addWidget(self._san_btn)
        san_row.addStretch()
        san_lay.addLayout(san_row)
        lay.addWidget(san_grp)

        lay.addStretch()
        scroll.setWidget(inner)
        return scroll

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
        if hasattr(self, '_org_grp'):
            self._org_grp.setVisible(enabled)

    def _rebuild_browser_page(self):
        from modules.gui.library_browser import LibraryBrowser
        old = self._stack.widget(_PAGE_LIBRARY)
        if hasattr(old, 'stop_worker'):
            old.stop_worker()
        if hasattr(old, 'save_state'):
            old.save_state()
        new_page = LibraryBrowser(self._lib_config, self._plugin, self._ui_state)
        self._stack.insertWidget(_PAGE_LIBRARY, new_page)
        # insertWidget shifts existing widgets — remove the now-displaced placeholder
        displaced = self._stack.widget(_PAGE_LIBRARY + 1)
        if displaced is old:
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
    _LOG_PAGES = {_PAGE_EXTRACT, _PAGE_OPERATIONS}  # Themes page intentionally excluded

    def _on_nav_changed(self, row: int):
        self._stack.setCurrentIndex(row)
        self._log.setVisible(row in self._LOG_PAGES)
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
        genre_counts = {}

        try:
            from modules.core.db import LibraryDB
            db = LibraryDB(Path(self._lib_config.db_file))
            scanned   = db.count_scan_list()
            found      = db.count_found()
            failed     = db.count_failed()
            organized  = db.count_organized()
            genre_counts = db.genre_counts()
        except Exception:
            pass

        self._card_scanned.set_value(scanned)
        self._card_found.set_value(found)
        self._card_failed.set_value(failed)
        self._card_organized.set_value(organized)
        self._load_genres_dash(genre_counts)

        html_file = self._lib_config.html_file
        self._dash_btn_html.setVisible(bool(html_file and Path(html_file).exists()))

        t = _THEMES.get(self._global_config.theme, _THEMES['Light'])
        for card in self._stat_cards:
            card.apply_theme(t['card_bg'], t['card_border'])

    # ── Genres (dashboard) ────────────────────────────────────────────
    def _load_genres_dash(self, genre_counts: dict):
        import json
        genre_file = self._lib_config.genre_file if self._lib_config else None
        has_file = bool(genre_file)
        self._genres_grp.setVisible(has_file)
        if not has_file:
            return

        genres = []
        if Path(genre_file).exists():
            try:
                with open(genre_file, 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                genres = sorted(raw.values() if isinstance(raw, dict) else raw)
            except Exception:
                pass

        self._populate_genres_table({g: genre_counts.get(g, 0) for g in genres})

    def _genres_from_table(self) -> dict:
        """Return {genre_name: count} from all 3 column groups."""
        result = {}
        for r in range(self._genres_table.rowCount()):
            for gc in (0, 2, 4):
                g = self._genres_table.item(r, gc)
                c = self._genres_table.item(r, gc + 1)
                if g and g.text():
                    try:
                        result[g.text()] = int(c.text()) if c else 0
                    except ValueError:
                        result[g.text()] = 0
        return result

    def _populate_genres_table(self, genre_counts: dict):
        """Fill genres table in 3-column layout (Genre/#/Genre/#/Genre/#)."""
        genres = sorted(genre_counts)
        n = len(genres)
        rows = math.ceil(n / 3) if n > 0 else 0
        self._genres_table.setSortingEnabled(False)
        self._genres_table.setRowCount(0)
        self._genres_table.setRowCount(rows)
        for i, name in enumerate(genres):
            grp = i // rows if rows > 0 else 0
            row = i % rows if rows > 0 else i
            gc = grp * 2
            g_item = CITableWidgetItem(name)
            c_item = CITableWidgetItem(str(genre_counts.get(name, 0)))
            c_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._genres_table.setItem(row, gc, g_item)
            self._genres_table.setItem(row, gc + 1, c_item)
        self._genres_table.setSortingEnabled(False)  # sorting disabled; layout is positional

    def _save_genres_to_file(self):
        import json
        genre_file = self._lib_config.genre_file if self._lib_config else None
        if not genre_file:
            return
        genres = sorted(self._genres_from_table())
        data = {g: g for g in genres}
        try:
            Path(genre_file).parent.mkdir(parents=True, exist_ok=True)
            with open(genre_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Failed to save genres:\n{e}')

    def _genre_add(self):
        name, ok = QInputDialog.getText(self, 'Add Genre', 'Genre name:')
        if not ok or not name.strip():
            return
        name = name.strip()
        counts = self._genres_from_table()
        if name in counts:
            QMessageBox.warning(self, 'Duplicate', f'"{name}" already exists.')
            return
        counts[name] = 0
        self._populate_genres_table(counts)
        self._save_genres_to_file()

    def _genre_rename(self):
        item = self._genres_table.currentItem()
        if not item or not item.text():
            QMessageBox.information(self, 'Rename', 'Select a genre first.')
            return
        col = self._genres_table.currentColumn()
        row = self._genres_table.currentRow()
        gc = (col // 2) * 2
        g_item = self._genres_table.item(row, gc)
        if not g_item or not g_item.text():
            QMessageBox.information(self, 'Rename', 'Select a genre first.')
            return
        old = g_item.text()
        name, ok = QInputDialog.getText(self, 'Rename Genre', 'New name:', text=old)
        if not ok or not name.strip() or name.strip() == old:
            return
        counts = self._genres_from_table()
        counts[name.strip()] = counts.pop(old, 0)
        self._populate_genres_table(counts)
        self._save_genres_to_file()

    def _genre_delete(self):
        item = self._genres_table.currentItem()
        if not item or not item.text():
            QMessageBox.information(self, 'Delete', 'Select a genre first.')
            return
        col = self._genres_table.currentColumn()
        row = self._genres_table.currentRow()
        gc = (col // 2) * 2
        g_item = self._genres_table.item(row, gc)
        if not g_item or not g_item.text():
            QMessageBox.information(self, 'Delete', 'Select a genre first.')
            return
        name = g_item.text()
        if QMessageBox.question(
            self, 'Delete Genre', f'Delete "{name}"?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            counts = self._genres_from_table()
            counts.pop(name, None)
            self._populate_genres_table(counts)
            self._save_genres_to_file()

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
        self._start_worker(w, self._scan_run_btn, self._scan_stop_btn, self._scan_progress)

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
        self._start_worker(w, self._meta_run_btn, self._meta_stop_btn, self._meta_progress)

    def _run_organizer(self):
        from modules.gui.workers import OrganizerWorker
        self._start_worker(
            OrganizerWorker(self._lib_config, self._plugin, self._log.stream),
            self._org_run_btn, self._org_stop_btn, self._org_progress,
        )

    def _run_html(self):
        from modules.gui.workers import HTMLWorker
        self._start_worker(
            HTMLWorker(self._lib_config, self._plugin, self._log.stream),
            self._html_run_btn, self._html_stop_btn, self._html_progress,
        )

    def _open_sanitizer(self):
        from modules.gui.folder_sanitizer import FolderSanitizerDialog
        dlg = FolderSanitizerDialog(self._lib_config, self)
        dlg.exec()

    def _start_worker(self, worker, run_btn=None, stop_btn=None, progress=None):
        if self._worker and self._worker.isRunning():
            self._status_bar.showMessage('A task is already running.')
            return
        self._worker = worker
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()
        self._status_bar.showMessage('Running...')

        self._active_progress = progress
        self._active_run_btn  = run_btn
        self._active_stop_btn = stop_btn
        if progress:
            progress.setVisible(True)
        if run_btn:
            run_btn.setEnabled(False)
        if stop_btn:
            stop_btn.setEnabled(True)

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
        FailedItemsDialog(self._lib_config, self._plugin, self, ui_state=self._ui_state).exec()

    def _clear_failed_items(self):
        if not self._lib_config:
            return
        from modules.core.db import LibraryDB
        db = LibraryDB(self._lib_config.db_file)
        count = db.count_failed()
        if count == 0:
            QMessageBox.information(self, 'Clear Failed Items', 'No failed items in the database.')
            return
        ans = QMessageBox.question(
            self, 'Clear Failed Items',
            f'Delete all {count} failed item(s) from the database?\n\nThis cannot be undone.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans == QMessageBox.StandardButton.Yes:
            deleted = db.delete_failed_items()
            QMessageBox.information(self, 'Done', f'Removed {deleted} failed item(s).')
            self._refresh_dashboard()

    def _open_html(self):
        html_file = self._lib_config.html_file
        if html_file and Path(html_file).exists():
            webbrowser.open(Path(html_file).resolve().as_uri())

    # ── Theme ─────────────────────────────────────────────────────────
    def _on_theme_changed(self, name: str):
        self._apply_theme(name)
        self._set_window_icon(name)
        self._global_config.set_theme(name)

    def _on_theme_editor_applied(self, name: str):
        self._apply_theme(name)
        self._set_window_icon(name)
        self._global_config.set_theme(name)
        idx = self._theme_combo.findText(name)
        if idx >= 0:
            self._theme_combo.blockSignals(True)
            self._theme_combo.setCurrentIndex(idx)
            self._theme_combo.blockSignals(False)

    def _on_themes_changed(self):
        current = self._theme_combo.currentText()
        self._theme_combo.blockSignals(True)
        self._theme_combo.clear()
        self._theme_combo.addItems(get_theme_names())
        idx = self._theme_combo.findText(current)
        if idx >= 0:
            self._theme_combo.setCurrentIndex(idx)
        self._theme_combo.blockSignals(False)

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
        self._ui_state.save_splitter(self._nav_splitter, 'nav_splitter')
        super().closeEvent(event)
