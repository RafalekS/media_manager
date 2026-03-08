"""
Main application window for Media Manager.

Nav:  Dashboard | Scan | Metadata | Failed Items | Organize | Generate HTML | Library | Settings | Log
"""

import os
import sys
import webbrowser
from pathlib import Path

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QStackedWidget,
    QPushButton, QComboBox, QFrame, QScrollArea,
    QSizePolicy as QSP, QStatusBar, QApplication,
    QGroupBox, QFormLayout, QCheckBox,
)

from modules.gui.log_widget import LogWidget
from modules.gui.theme_manager import THEME_NAMES, build_stylesheet, _THEMES
from modules.gui.ui_state import UIState
from modules.gui.settings_page import SettingsPage

APP_VERSION = '1.0.0'
_ROOT = Path(__file__).parent.parent.parent

# Nav index constants
_PAGE_DASHBOARD  = 0
_PAGE_SCAN       = 1
_PAGE_METADATA   = 2
_PAGE_FAILED     = 3
_PAGE_ORGANIZE   = 4
_PAGE_HTML       = 5
_PAGE_LIBRARY    = 6
_PAGE_SETTINGS   = 7
_PAGE_LOG        = 8


# ── Stat card ─────────────────────────────────────────────────────────────────

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


# ── Wizard card ───────────────────────────────────────────────────────────────

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


# ── Main Window ───────────────────────────────────────────────────────────────

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

        self.setWindowTitle('Media Manager')
        self._apply_theme(global_config.theme)
        self._set_window_icon(global_config.theme)
        self._build_ui()
        self._ui_state.restore_window(self)
        self._load_library(global_config.active_library)

    # ──────────────────────────────────────────────────────────────────
    # Theme / icon
    # ──────────────────────────────────────────────────────────────────
    def _apply_theme(self, name: str):
        QApplication.instance().setStyleSheet(build_stylesheet(name))
        if hasattr(self, '_stat_cards') and self._stat_cards:
            t = _THEMES.get(name, _THEMES['Light'])
            for card in self._stat_cards:
                card.apply_theme(t['card_bg'], t['card_border'])

    def _set_window_icon(self, theme: str):
        from PyQt6.QtCore import QTimer
        dark_themes = {'Dark', 'Midnight', 'Slate'}
        if theme in dark_themes:
            icon_name = 'light_media_mgr.png'   # light icon on dark bg
        elif theme == 'Light':
            icon_name = 'dark_media_mgr.png'    # dark icon on light bg
        else:
            icon_name = 'color_media_mgr.png'
        icon_path = _ROOT / 'assets' / icon_name
        if not icon_path.exists():
            icon_path = _ROOT / 'assets' / 'color_media_mgr.png'
        if icon_path.exists():
            icon = QIcon(str(icon_path))
            # Clear first — Qt caches the previous icon on Windows
            self.setWindowIcon(QIcon())
            QApplication.instance().setWindowIcon(QIcon())
            # Defer the actual set so the clear is processed first
            QTimer.singleShot(50, lambda: (
                self.setWindowIcon(icon),
                QApplication.instance().setWindowIcon(icon),
            ))

    # ──────────────────────────────────────────────────────────────────
    # Build UI
    # ──────────────────────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_sidebar())

        self._stack = QStackedWidget()
        self._stack.setObjectName('content_widget')

        self._dash_page     = self._build_dashboard_page()
        self._scan_page     = self._build_step_page('Scan', 'Scan source folder for new items.', self._run_scan)
        self._meta_page     = self._build_step_page('Metadata', 'Fetch metadata from providers for all scanned items.', self._run_metadata)
        self._failed_page   = self._build_step_page('Failed Items', 'Review and manually assign genres to failed lookups.', self._open_failed_dialog, btn_label='Open Failed Items Dialog')
        self._org_page      = self._build_step_page('Organize', 'Generate the organizer batch script.', self._run_organizer)
        self._html_page     = self._build_step_page('Generate HTML', 'Build the dynamic HTML library page.', self._run_html)
        self._browser_placeholder = QWidget()
        self._settings_page = SettingsPage()
        self._log_page      = self._build_log_page()

        for page in (
            self._dash_page,           # 0
            self._scan_page,           # 1
            self._meta_page,           # 2
            self._failed_page,         # 3
            self._org_page,            # 4
            self._html_page,           # 5
            self._browser_placeholder, # 6
            self._settings_page,       # 7
            self._log_page,            # 8
        ):
            self._stack.addWidget(page)

        root.addWidget(self._stack, 1)

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
            'Dashboard', 'Scan', 'Metadata',
            'Failed Items', 'Organize', 'Generate HTML',
            'Library', 'Settings', 'Log',
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

    # ──────────────────────────────────────────────────────────────────
    # Dashboard page
    # ──────────────────────────────────────────────────────────────────
    def _build_dashboard_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
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

        # Wizard cards row
        wizard_row = QHBoxLayout()
        wizard_row.setSpacing(10)

        self._wiz_new = _WizardCard(
            'New Items Wizard',
            'Scan → Metadata → Organize → HTML in one guided flow.',
            'Launch',
            self._open_new_items_wizard,
            '#2563eb',
        )
        wizard_row.addWidget(self._wiz_new)

        self._wiz_refresh = _WizardCard(
            'Refresh Database Wizard',
            'Re-fetch metadata and regenerate the HTML library page.',
            'Launch',
            self._open_refresh_wizard,
            '#0891b2',
        )
        wizard_row.addWidget(self._wiz_refresh)

        lay.addLayout(wizard_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        lay.addWidget(sep)

        # Stat cards row
        stats_row = QHBoxLayout()
        stats_row.setSpacing(10)

        self._card_scanned  = _StatCard('Items Scanned',   '—', '#2563eb')
        self._card_found    = _StatCard('Metadata Found',  '—', '#10b981')
        self._card_failed   = _StatCard('Metadata Failed', '—', '#ef4444')
        self._card_organized = _StatCard('Organized',      '—', '#f59e0b')
        self._stat_cards = [
            self._card_scanned, self._card_found,
            self._card_failed, self._card_organized,
        ]
        for c in self._stat_cards:
            stats_row.addWidget(c)
        lay.addLayout(stats_row)

        # Config summary
        self._dash_paths_lbl = QLabel('')
        self._dash_paths_lbl.setProperty('role', 'muted')
        self._dash_paths_lbl.setWordWrap(True)
        lay.addWidget(self._dash_paths_lbl)

        # HTML button
        self._dash_btn_html = QPushButton('Open HTML Library')
        self._dash_btn_html.clicked.connect(self._open_html)
        self._dash_btn_html.setVisible(False)
        self._dash_btn_html.setSizePolicy(QSP.Policy.Fixed, QSP.Policy.Fixed)
        lay.addWidget(self._dash_btn_html)

        lay.addStretch()
        scroll.setWidget(inner)
        return scroll

    # ──────────────────────────────────────────────────────────────────
    # Generic step page (Scan / Metadata / Organize / HTML)
    # ──────────────────────────────────────────────────────────────────
    def _build_step_page(self, title: str, description: str,
                         action_slot, btn_label: str = 'Run') -> QWidget:
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

        btn = QPushButton(btn_label)
        btn.setSizePolicy(QSP.Policy.Fixed, QSP.Policy.Fixed)
        btn.clicked.connect(action_slot)
        lay.addWidget(btn)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        lay.addWidget(sep)

        log = LogWidget()
        lay.addWidget(log, 1)

        # Store log widget ref on page for worker use
        page._log = log
        return page

    # ──────────────────────────────────────────────────────────────────
    # Log page
    # ──────────────────────────────────────────────────────────────────
    def _build_log_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 24, 24, 24)
        lbl = QLabel('Log')
        lbl.setProperty('role', 'title')
        lay.addWidget(lbl)
        self._main_log = LogWidget()
        lay.addWidget(self._main_log, 1)
        return page

    # ──────────────────────────────────────────────────────────────────
    # Library switching
    # ──────────────────────────────────────────────────────────────────
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
        self._status_bar.showMessage(f'Library: {self._plugin.name}')

    def _update_organize_nav(self):
        """Enable/disable the Organize nav item based on the current library's organize_enabled flag."""
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

    # ──────────────────────────────────────────────────────────────────
    # Navigation
    # ──────────────────────────────────────────────────────────────────
    def _on_nav_changed(self, row: int):
        self._stack.setCurrentIndex(row)
        if row == _PAGE_LIBRARY and self._browser_page and not self._browser_page._state_loaded:
            self._browser_page.load_data()

    # ──────────────────────────────────────────────────────────────────
    # Dashboard refresh
    # ──────────────────────────────────────────────────────────────────
    def _refresh_dashboard(self):
        import json

        lib_name = self._plugin.name if self._plugin else ''
        src  = self._lib_config.data.get('source_folder', '') or '—'
        dest = self._lib_config.data.get('destination_base', '') or '—'
        if self._plugin:
            self._dash_lib_lbl.setText(
                f'{self._plugin.icon} {lib_name}  |  Source: {src}  Destination: {dest}'
            )

        # Read stats from JSON only — never scan the filesystem here (would freeze on large libraries)
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
                organized = sum(1 for v in items.values() if (v.get('igdb_found') or v.get('found')) and v.get('genre'))
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

    # ──────────────────────────────────────────────────────────────────
    # Workers
    # ──────────────────────────────────────────────────────────────────
    def _current_log(self) -> LogWidget:
        page = self._stack.currentWidget()
        return getattr(page, '_log', self._main_log)

    def _run_scan(self):
        from modules.gui.workers import ScanWorker
        self._start_worker(ScanWorker(self._lib_config, self._plugin, self._current_log().stream))

    def _run_metadata(self):
        from modules.gui.workers import MetadataWorker
        self._start_worker(MetadataWorker(self._lib_config, self._plugin, self._current_log().stream))

    def _run_organizer(self):
        from modules.gui.workers import OrganizerWorker
        self._start_worker(OrganizerWorker(self._lib_config, self._plugin, self._current_log().stream))

    def _run_html(self):
        from modules.gui.workers import HTMLWorker
        self._start_worker(HTMLWorker(self._lib_config, self._plugin, self._current_log().stream))

    def _start_worker(self, worker):
        if self._worker and self._worker.isRunning():
            self._status_bar.showMessage('A task is already running.')
            return
        self._worker = worker
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()
        self._status_bar.showMessage('Running...')

    def _on_worker_finished(self, success: bool, message: str):
        self._status_bar.showMessage(('Done: ' if success else 'Error: ') + message)
        self._refresh_dashboard()

    # ──────────────────────────────────────────────────────────────────
    # Dialogs
    # ──────────────────────────────────────────────────────────────────
    def _open_new_items_wizard(self):
        from modules.gui.wizard import NewItemsWizard
        NewItemsWizard(self._lib_config, self._plugin, self).exec()
        self._refresh_dashboard()

    def _open_refresh_wizard(self):
        from modules.gui.wizard import RefreshDBWizard
        RefreshDBWizard(self._lib_config, self._plugin, self).exec()
        self._refresh_dashboard()

    def _open_failed_dialog(self):
        from modules.gui.failed_dialog import FailedItemsDialog
        FailedItemsDialog(self._lib_config, self._plugin, self).exec()

    def _open_html(self):
        html_file = self._lib_config.html_file
        if html_file and Path(html_file).exists():
            webbrowser.open(Path(html_file).resolve().as_uri())

    # ──────────────────────────────────────────────────────────────────
    # Theme
    # ──────────────────────────────────────────────────────────────────
    def _on_theme_changed(self, name: str):
        self._apply_theme(name)
        self._set_window_icon(name)
        self._global_config.set_theme(name)

    # ──────────────────────────────────────────────────────────────────
    # Close
    # ──────────────────────────────────────────────────────────────────
    def closeEvent(self, event):
        self._ui_state.save_window(self)
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(3000)
        super().closeEvent(event)
