"""
Main application window for Media Manager.
Sidebar navigation + library switcher (QComboBox).
Pages: Dashboard | Browser | Process | Log
"""

import os
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QLabel, QListWidget, QListWidgetItem, QStackedWidget,
    QPushButton, QComboBox, QGroupBox, QGridLayout, QFrame,
    QStatusBar, QScrollArea,
)

from modules.gui.log_widget import LogWidget
from modules.gui.theme_manager import THEME_NAMES, build_stylesheet
from modules.gui.ui_state import UIState

APP_VERSION = '1.0.0'


class MainWindow(QMainWindow):

    def __init__(self, global_config):
        super().__init__()
        self._global_config = global_config
        self._ui_state = UIState(str(global_config.ui_state_path()))
        self._plugin   = None
        self._lib_config = None
        self._browser_page = None   # lazy-created per library
        self._worker   = None
        self._log_widget = None

        self.setWindowTitle('Media Manager')
        self._apply_theme(global_config.theme)
        self._build_ui()
        self._ui_state.restore_window(self)
        self._load_library(global_config.active_library)

    # ──────────────────────────────────────────────────────────────────
    # Theme
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

        # Sidebar
        sidebar = QWidget()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(210)
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(0, 0, 0, 0)
        sb_layout.setSpacing(0)

        app_title = QLabel('Media Manager')
        app_title.setObjectName('app_title')
        sb_layout.addWidget(app_title)

        sub = QLabel('Multi-library tool')
        sub.setObjectName('app_subtitle')
        sb_layout.addWidget(sub)

        # Library switcher
        lib_lbl = QLabel('Library')
        lib_lbl.setStyleSheet("padding: 8px 14px 2px 14px; font-size:8pt;")
        sb_layout.addWidget(lib_lbl)

        self._lib_combo = QComboBox()
        self._lib_combo.setStyleSheet(
            "combobox-popup: 0; margin: 0 10px; padding: 4px 8px;"
        )
        self._lib_combo.view().setStyleSheet("max-height: 300px;")
        self._populate_lib_combo()
        self._lib_combo.currentTextChanged.connect(self._on_lib_changed)
        sb_layout.addWidget(self._lib_combo)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setStyleSheet("color: #333;")
        sb_layout.addWidget(sep1)

        # Nav list
        self._nav = QListWidget()
        self._nav.setObjectName('nav_list')
        for label in ['Dashboard', 'Library', 'Process', 'Log']:
            item = QListWidgetItem(label)
            self._nav.addItem(item)
        self._nav.setCurrentRow(0)
        self._nav.currentRowChanged.connect(self._on_nav_changed)
        sb_layout.addWidget(self._nav, 1)

        # Theme switcher
        theme_lbl = QLabel('Theme')
        theme_lbl.setStyleSheet("padding: 8px 14px 2px 14px; font-size:8pt;")
        sb_layout.addWidget(theme_lbl)

        self._theme_combo = QComboBox()
        self._theme_combo.setStyleSheet("combobox-popup: 0; margin: 0 10px; padding: 4px 8px;")
        self._theme_combo.view().setStyleSheet("max-height: 300px;")
        self._theme_combo.addItems(THEME_NAMES)
        saved_theme = self._global_config.theme
        idx = self._theme_combo.findText(saved_theme)
        if idx >= 0:
            self._theme_combo.setCurrentIndex(idx)
        self._theme_combo.currentTextChanged.connect(self._on_theme_changed)
        sb_layout.addWidget(self._theme_combo)

        ver = QLabel(f'v{APP_VERSION}')
        ver.setObjectName('ver_label')
        sb_layout.addWidget(ver)

        root.addWidget(sidebar)

        # Content area (stacked)
        self._stack = QStackedWidget()
        self._stack.setObjectName('content_widget')

        self._dash_page    = self._build_dashboard_page()
        self._process_page = self._build_process_page()
        self._log_page     = self._build_log_page()
        # Browser page is created dynamically per library in _load_library()
        self._browser_placeholder = QWidget()

        self._stack.addWidget(self._dash_page)          # idx 0
        self._stack.addWidget(self._browser_placeholder) # idx 1 (replaced per library)
        self._stack.addWidget(self._process_page)        # idx 2
        self._stack.addWidget(self._log_page)            # idx 3

        root.addWidget(self._stack, 1)

        # Status bar
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

        # Stats group
        self._stats_grp = QGroupBox('Library Stats')
        self._stats_grid = QGridLayout(self._stats_grp)
        layout.addWidget(self._stats_grp)

        # Quick actions group
        qa_grp = QGroupBox('Quick Actions')
        qa_layout = QHBoxLayout(qa_grp)

        self._dash_btn_new    = QPushButton('Process New Items')
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

        desc = QLabel(
            'Run individual steps for the active library.\n'
            'Use the wizards on the Dashboard for guided full-pipeline runs.'
        )
        desc.setProperty('role', 'muted')
        desc.setWordWrap(True)
        layout.addWidget(desc)

        grp = QGroupBox('Steps')
        grp_layout = QVBoxLayout(grp)

        steps = [
            ('Scan Source Folder',          self._run_scan),
            ('Fetch Metadata',              self._run_metadata),
            ('Generate Organizer Script',   self._run_organizer),
            ('Generate HTML Library Page',  self._run_html),
        ]
        for label, slot in steps:
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            grp_layout.addWidget(btn)

        layout.addWidget(grp)

        self._process_log = LogWidget()
        layout.addWidget(self._process_log, 1)

        self._log_widget = self._process_log   # alias for workers
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

        lib_path = (
            self._global_config.libraries_folder() /
            f'{media_type}.json'
        )
        self._lib_config = LibraryConfig(str(lib_path))

        # Load plugin
        plugin_map = {
            'games':  'modules.media_types.games.GamesPlugin',
            'movies': 'modules.media_types.movies.MoviesPlugin',
            'books':  'modules.media_types.books.BooksPlugin',
            'comics': 'modules.media_types.comics.ComicsPlugin',
            'music':  'modules.media_types.music.MusicPlugin',
        }
        module_path, class_name = plugin_map[media_type].rsplit('.', 1)
        import importlib
        mod = importlib.import_module(module_path)
        self._plugin = getattr(mod, class_name)()

        # Replace browser page
        self._rebuild_browser_page()
        self._refresh_dashboard()
        self._status_bar.showMessage(f'Library: {self._plugin.name}')

    def _rebuild_browser_page(self):
        from modules.gui.library_browser import LibraryBrowser
        old = self._stack.widget(1)
        # Stop any in-progress load before destroying old page
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
        page_map = {0: 0, 1: 1, 2: 2, 3: 3}
        self._stack.setCurrentIndex(page_map.get(row, 0))
        # Auto-load browser on first visit only — subsequent refreshes are manual
        if row == 1 and self._browser_page and not self._browser_page._state_loaded:
            self._browser_page.load_data()

    # ──────────────────────────────────────────────────────────────────
    # Dashboard helpers
    # ──────────────────────────────────────────────────────────────────
    def _refresh_dashboard(self):
        # Clear stats grid
        while self._stats_grid.count():
            item = self._stats_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        stats = self._collect_stats()
        row = 0
        for label, value in stats.items():
            lbl = QLabel(label + ':')
            lbl.setProperty('role', 'card_label')
            val = QLabel(str(value))
            self._stats_grid.addWidget(lbl, row, 0)
            self._stats_grid.addWidget(val, row, 1)
            row += 1

        # Show/hide HTML button
        html_file = Path(self._lib_config.html_file) if self._lib_config.html_file else None
        self._dash_btn_html.setVisible(bool(html_file and html_file.exists()))

    def _collect_stats(self) -> dict:
        from pathlib import Path
        import json

        stats = {}
        scan_file = self._lib_config.scan_list_file
        if scan_file and Path(scan_file).exists():
            with open(scan_file, 'r', encoding='utf-8') as f:
                scan = json.load(f)
            stats['Items in scan list'] = len(scan)

        meta_file = self._lib_config.metadata_file
        if meta_file and Path(meta_file).exists():
            with open(meta_file, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            items = meta.get('processed_items', meta.get('processed_games', {}))
            found = sum(1 for v in items.values() if v.get('igdb_found') or v.get('found'))
            stats['Metadata found'] = found
            stats['Metadata failed'] = len(items) - found

        return stats

    # ──────────────────────────────────────────────────────────────────
    # Process slots
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
        prefix = 'Done' if success else 'Error'
        self._status_bar.showMessage(f'{prefix}: {message}')
        self._refresh_dashboard()

    # ──────────────────────────────────────────────────────────────────
    # Dialog openers
    # ──────────────────────────────────────────────────────────────────
    def _open_new_items_wizard(self):
        from modules.gui.wizard import NewItemsWizard
        dlg = NewItemsWizard(self._lib_config, self._plugin, self)
        dlg.exec()
        self._refresh_dashboard()

    def _open_refresh_wizard(self):
        from modules.gui.wizard import RefreshDBWizard
        dlg = RefreshDBWizard(self._lib_config, self._plugin, self)
        dlg.exec()
        self._refresh_dashboard()

    def _open_failed_dialog(self):
        from modules.gui.failed_dialog import FailedItemsDialog
        dlg = FailedItemsDialog(self._lib_config, self._plugin, self)
        dlg.exec()

    def _open_html(self):
        html_file = self._lib_config.html_file
        if html_file and Path(html_file).exists():
            url = Path(html_file).resolve().as_uri()
            import webbrowser
            webbrowser.open(url)

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
