"""
Main application window for Media Manager.
Sidebar navigation + library switcher (QComboBox).
Pages: Dashboard | Library | Process | Settings | Log
"""

import os
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QStackedWidget,
    QPushButton, QComboBox, QGroupBox, QGridLayout, QFrame,
    QStatusBar, QScrollArea,
)

from modules.gui.log_widget import LogWidget
from modules.gui.theme_manager import THEME_NAMES, build_stylesheet
from modules.gui.ui_state import UIState
from modules.gui.settings_page import SettingsPage

APP_VERSION = '1.0.0'

# Nav row → stack index
_NAV_MAP = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4}


class MainWindow(QMainWindow):

    def __init__(self, global_config):
        super().__init__()
        self._global_config = global_config
        self._ui_state   = UIState(str(global_config.ui_state_path()))
        self._plugin     = None
        self._lib_config = None
        self._browser_page = None
        self._worker     = None

        self.setWindowTitle('Media Manager')
        self._apply_theme(global_config.theme)
        self._build_ui()
        self._ui_state.restore_window(self)
        self._load_library(global_config.active_library)

    # ──────────────────────────────────────────────────────────────────
    def _apply_theme(self, name: str):
        self.setStyleSheet(build_stylesheet(name))

    # ──────────────────────────────────────────────────────────────────
    # UI Construction
    # ──────────────────────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Sidebar ───────────────────────────────────────────────────
        sidebar = QWidget()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(210)
        sb = QVBoxLayout(sidebar)
        sb.setContentsMargins(0, 0, 0, 0)
        sb.setSpacing(0)

        lbl_title = QLabel('Media Manager')
        lbl_title.setObjectName('app_title')
        sb.addWidget(lbl_title)

        lbl_sub = QLabel('Multi-library tool')
        lbl_sub.setObjectName('app_subtitle')
        sb.addWidget(lbl_sub)

        lbl_lib = QLabel('Library')
        lbl_lib.setStyleSheet("padding: 8px 14px 2px 14px; font-size:8pt;")
        sb.addWidget(lbl_lib)

        self._lib_combo = QComboBox()
        self._lib_combo.setStyleSheet("combobox-popup: 0; margin: 0 10px; padding: 4px 8px;")
        self._lib_combo.view().setStyleSheet("max-height: 300px;")
        self._populate_lib_combo()
        self._lib_combo.currentTextChanged.connect(self._on_lib_changed)
        sb.addWidget(self._lib_combo)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #333;")
        sb.addWidget(sep)

        self._nav = QListWidget()
        self._nav.setObjectName('nav_list')
        for label in ['Dashboard', 'Library', 'Process', 'Settings', 'Log']:
            self._nav.addItem(QListWidgetItem(label))
        self._nav.setCurrentRow(0)
        self._nav.currentRowChanged.connect(self._on_nav_changed)
        sb.addWidget(self._nav, 1)

        lbl_theme = QLabel('Theme')
        lbl_theme.setStyleSheet("padding: 8px 14px 2px 14px; font-size:8pt;")
        sb.addWidget(lbl_theme)

        self._theme_combo = QComboBox()
        self._theme_combo.setStyleSheet("combobox-popup: 0; margin: 0 10px; padding: 4px 8px;")
        self._theme_combo.view().setStyleSheet("max-height: 300px;")
        self._theme_combo.addItems(THEME_NAMES)
        idx = self._theme_combo.findText(self._global_config.theme)
        if idx >= 0:
            self._theme_combo.setCurrentIndex(idx)
        self._theme_combo.currentTextChanged.connect(self._on_theme_changed)
        sb.addWidget(self._theme_combo)

        lbl_ver = QLabel(f'v{APP_VERSION}')
        lbl_ver.setObjectName('ver_label')
        sb.addWidget(lbl_ver)

        root.addWidget(sidebar)

        # ── Content stack ─────────────────────────────────────────────
        self._stack = QStackedWidget()
        self._stack.setObjectName('content_widget')

        self._dash_page     = self._build_dashboard_page()   # 0
        self._browser_placeholder = QWidget()                 # 1 — replaced per library
        self._process_page  = self._build_process_page()     # 2
        self._settings_page = SettingsPage()                  # 3
        self._log_page      = self._build_log_page()          # 4

        self._stack.addWidget(self._dash_page)
        self._stack.addWidget(self._browser_placeholder)
        self._stack.addWidget(self._process_page)
        self._stack.addWidget(self._settings_page)
        self._stack.addWidget(self._log_page)

        root.addWidget(self._stack, 1)

        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage('Ready.')

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
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel('Dashboard')
        title.setProperty('role', 'title')
        layout.addWidget(title)

        self._stats_grp = QGroupBox('Library Stats')
        self._stats_grid = QGridLayout(self._stats_grp)
        layout.addWidget(self._stats_grp)

        qa_grp = QGroupBox('Quick Actions')
        qa_layout = QHBoxLayout(qa_grp)

        self._dash_btn_new = QPushButton('Process New Items')
        self._dash_btn_new.clicked.connect(self._open_new_items_wizard)
        qa_layout.addWidget(self._dash_btn_new)

        self._dash_btn_refresh = QPushButton('Refresh Database')
        self._dash_btn_refresh.clicked.connect(self._open_refresh_wizard)
        qa_layout.addWidget(self._dash_btn_refresh)

        self._dash_btn_failed = QPushButton('Manage Failed Items')
        self._dash_btn_failed.clicked.connect(self._open_failed_dialog)
        qa_layout.addWidget(self._dash_btn_failed)

        self._dash_btn_html = QPushButton('Open HTML Library')
        self._dash_btn_html.clicked.connect(self._open_html)
        self._dash_btn_html.setVisible(False)
        qa_layout.addWidget(self._dash_btn_html)

        layout.addWidget(qa_grp)
        layout.addStretch()
        scroll.setWidget(inner)
        return scroll

    # ──────────────────────────────────────────────────────────────────
    # Process page
    # ──────────────────────────────────────────────────────────────────
    def _build_process_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel('Process')
        title.setProperty('role', 'title')
        layout.addWidget(title)

        self._process_lib_lbl = QLabel('')
        self._process_lib_lbl.setProperty('role', 'subtitle')
        layout.addWidget(self._process_lib_lbl)

        desc = QLabel(
            'Run individual steps for the active library.\n'
            'Use the wizards on the Dashboard for a guided full-pipeline run.'
        )
        desc.setProperty('role', 'muted')
        desc.setWordWrap(True)
        layout.addWidget(desc)

        grp = QGroupBox('Steps')
        grp_layout = QVBoxLayout(grp)
        for label, slot in [
            ('1. Scan Source Folder',         self._run_scan),
            ('2. Fetch Metadata',             self._run_metadata),
            ('3. Generate Organizer Script',  self._run_organizer),
            ('4. Generate HTML Library Page', self._run_html),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            grp_layout.addWidget(btn)
        layout.addWidget(grp)

        self._process_log = LogWidget()
        layout.addWidget(self._process_log, 1)
        return page

    # ──────────────────────────────────────────────────────────────────
    # Log page
    # ──────────────────────────────────────────────────────────────────
    def _build_log_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        title = QLabel('Log')
        title.setProperty('role', 'title')
        layout.addWidget(title)
        self._main_log = LogWidget()
        layout.addWidget(self._main_log, 1)
        return page

    # ──────────────────────────────────────────────────────────────────
    # Library switching
    # ──────────────────────────────────────────────────────────────────
    def _load_library(self, media_type: str):
        from modules.core.config_manager import LibraryConfig
        import importlib

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

        # Sync combo (blocked to prevent re-trigger)
        self._lib_combo.blockSignals(True)
        idx = self._lib_combo.findData(media_type)
        if idx >= 0:
            self._lib_combo.setCurrentIndex(idx)
        self._lib_combo.blockSignals(False)

        self._rebuild_browser_page()
        self._refresh_dashboard()
        self._settings_page.load_library(self._lib_config)
        self._process_lib_lbl.setText(f'Active: {self._plugin.name}')
        self._status_bar.showMessage(f'Library: {self._plugin.name}')

    def _rebuild_browser_page(self):
        from modules.gui.library_browser import LibraryBrowser
        old = self._stack.widget(1)
        if hasattr(old, 'stop_worker'):
            old.stop_worker()
        new_page = LibraryBrowser(self._lib_config, self._plugin, self._ui_state)
        self._stack.insertWidget(1, new_page)
        self._stack.removeWidget(old)
        old.deleteLater()
        self._browser_page = new_page

    def _on_lib_changed(self, display_name: str):
        idx = self._lib_combo.currentIndex()
        media_type = self._lib_combo.itemData(idx)
        if media_type:
            self._load_library(media_type)
            self._global_config.set_active_library(media_type)

    # ──────────────────────────────────────────────────────────────────
    # Navigation
    # ──────────────────────────────────────────────────────────────────
    def _on_nav_changed(self, row: int):
        self._stack.setCurrentIndex(_NAV_MAP.get(row, 0))
        if row == 1 and self._browser_page and not self._browser_page._state_loaded:
            self._browser_page.load_data()

    # ──────────────────────────────────────────────────────────────────
    # Dashboard
    # ──────────────────────────────────────────────────────────────────
    def _refresh_dashboard(self):
        while self._stats_grid.count():
            item = self._stats_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        lib_name = self._plugin.name if self._plugin else 'Unknown'
        self._stats_grp.setTitle(f'{lib_name} Library Stats')

        stats = self._collect_stats()
        for row, (label, value) in enumerate(stats.items()):
            lbl = QLabel(label + ':')
            lbl.setProperty('role', 'card_label')
            val = QLabel(str(value))
            self._stats_grid.addWidget(lbl, row, 0)
            self._stats_grid.addWidget(val, row, 1)

        html_file = self._lib_config.html_file if self._lib_config else None
        self._dash_btn_html.setVisible(bool(html_file and Path(html_file).exists()))

    def _collect_stats(self) -> dict:
        import json
        stats = {}

        scan_file = self._lib_config.scan_list_file
        if scan_file and Path(scan_file).exists():
            with open(scan_file, 'r', encoding='utf-8') as f:
                stats['Items in scan list'] = len(json.load(f))

        meta_file = self._lib_config.metadata_file
        if meta_file and Path(meta_file).exists():
            with open(meta_file, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            items = meta.get('processed_items', meta.get('processed_games', {}))
            found = sum(1 for v in items.values() if v.get('igdb_found') or v.get('found'))
            stats['Metadata found']  = found
            stats['Metadata failed'] = len(items) - found

        return stats

    # ──────────────────────────────────────────────────────────────────
    # Process workers
    # ──────────────────────────────────────────────────────────────────
    def _run_scan(self):
        from modules.gui.workers import ScanWorker
        self._start_worker(ScanWorker(self._lib_config, self._plugin, self._process_log.stream))

    def _run_metadata(self):
        from modules.gui.workers import MetadataWorker
        self._start_worker(MetadataWorker(self._lib_config, self._plugin, self._process_log.stream))

    def _run_organizer(self):
        from modules.gui.workers import OrganizerWorker
        self._start_worker(OrganizerWorker(self._lib_config, self._plugin, self._process_log.stream))

    def _run_html(self):
        from modules.gui.workers import HTMLWorker
        self._start_worker(HTMLWorker(self._lib_config, self._plugin, self._process_log.stream))

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
            import webbrowser
            webbrowser.open(Path(html_file).resolve().as_uri())

    # ──────────────────────────────────────────────────────────────────
    # Theme
    # ──────────────────────────────────────────────────────────────────
    def _on_theme_changed(self, name: str):
        self._apply_theme(name)
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
