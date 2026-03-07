"""
Settings page — per-library paths, API keys, HTML options.
Reloads when the active library changes.
"""

import json
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QSpinBox, QPushButton, QGroupBox,
    QScrollArea, QMessageBox, QFileDialog,
)


# Which API fields each library needs
_LIBRARY_API_FIELDS = {
    'games': [
        ('igdb_client_id',     'IGDB Client ID',     False),
        ('igdb_client_secret', 'IGDB Client Secret', True),
        ('rawg_api_key',       'RAWG API Key',        True),
    ],
    'movies': [
        ('tmdb_api_key',  'TMDB API Key',  True),
        ('omdb_api_key',  'OMDB API Key',  True),
    ],
    'books': [
        ('google_books_api_key', 'Google Books API Key', True),
    ],
    'comics': [
        ('comic_vine_api_key', 'Comic Vine API Key', True),
    ],
    'music': [],   # MusicBrainz needs no key
}


class SettingsPage(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lib_config   = None
        self._api_widgets  = {}   # key -> QLineEdit
        self._api_grp      = None
        self._api_form     = None
        self._setup_ui()

    # ──────────────────────────────────────────────────────────────────
    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        self._layout = QVBoxLayout(inner)
        self._layout.setContentsMargins(24, 24, 24, 24)
        self._layout.setSpacing(14)

        title = QLabel('Settings')
        title.setProperty('role', 'title')
        self._layout.addWidget(title)

        self._lib_lbl = QLabel('')
        self._lib_lbl.setProperty('role', 'subtitle')
        self._layout.addWidget(self._lib_lbl)

        # ── Paths ────────────────────────────────────────────────────
        paths_grp = QGroupBox('Paths')
        paths_form = QFormLayout(paths_grp)

        self._src = QLineEdit()
        paths_form.addRow('Source Folder:', self._path_row(self._src, folder=True))

        self._dest = QLineEdit()
        paths_form.addRow('Destination Base:', self._path_row(self._dest, folder=True))

        self._bat = QLineEdit()
        self._bat.setPlaceholderText('(leave blank = destination base)')
        paths_form.addRow('Script Output Path:', self._path_row(self._bat, folder=False))

        self._html_fname = QLineEdit()
        self._html_fname.setPlaceholderText('e.g. games_library.html')
        paths_form.addRow('HTML Filename:', self._html_fname)

        self._layout.addWidget(paths_grp)

        # ── API Keys ─────────────────────────────────────────────────
        self._api_grp = QGroupBox('API Keys')
        self._api_form = QFormLayout(self._api_grp)
        self._layout.addWidget(self._api_grp)

        # ── HTML Options ─────────────────────────────────────────────
        html_grp = QGroupBox('HTML Options')
        html_form = QFormLayout(html_grp)

        self._items_per_page = QSpinBox()
        self._items_per_page.setRange(10, 1000)
        self._items_per_page.setSingleStep(10)
        self._items_per_page.setValue(50)
        html_form.addRow('Items per page:', self._items_per_page)

        self._layout.addWidget(html_grp)

        # ── Buttons ──────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_save = QPushButton('Save Settings')
        btn_save.clicked.connect(self._save)
        btn_row.addWidget(btn_save)
        btn_row.addStretch()
        self._layout.addLayout(btn_row)
        self._layout.addStretch()

        scroll.setWidget(inner)
        outer.addWidget(scroll)

    def _path_row(self, line_edit: QLineEdit, folder: bool) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(line_edit)
        btn = QPushButton('Browse')
        btn.setObjectName('btn_secondary')
        if folder:
            btn.clicked.connect(lambda: self._browse_folder(line_edit))
        else:
            btn.clicked.connect(lambda: self._browse_file(line_edit))
        row.addWidget(btn)
        return row

    # ──────────────────────────────────────────────────────────────────
    def load_library(self, lib_config):
        """Call this whenever the active library changes."""
        self._lib_config = lib_config
        media_type = lib_config.media_type
        self._lib_lbl.setText(f'Active library: {media_type.capitalize()}')

        # Paths
        self._src.setText(str(lib_config.data.get('source_folder', '')))
        self._dest.setText(str(lib_config.data.get('destination_base', '')))
        self._bat.setText(str(lib_config.data.get('bat_output_path', '')))
        self._html_fname.setText(lib_config.data.get('html_filename', ''))
        self._items_per_page.setValue(lib_config.data.get('items_per_page', 50))

        # Rebuild API key fields for this library type
        self._rebuild_api_fields(media_type, lib_config.data.get('api', {}))

    def _rebuild_api_fields(self, media_type: str, api_data: dict):
        # Clear existing rows
        while self._api_form.rowCount():
            self._api_form.removeRow(0)
        self._api_widgets.clear()

        fields = _LIBRARY_API_FIELDS.get(media_type, [])
        if not fields:
            lbl = QLabel('No API keys required for this library.')
            lbl.setProperty('role', 'muted')
            self._api_form.addRow(lbl)
            return

        for key, label, secret in fields:
            edit = QLineEdit()
            edit.setText(api_data.get(key, ''))
            if secret:
                edit.setEchoMode(QLineEdit.EchoMode.Password)
            self._api_form.addRow(f'{label}:', edit)
            self._api_widgets[key] = edit

    # ──────────────────────────────────────────────────────────────────
    def _save(self):
        if not self._lib_config:
            return

        data = self._lib_config.data

        # Paths
        src = self._src.text().strip()
        dst = self._dest.text().strip()
        if not src or not dst:
            QMessageBox.warning(self, 'Validation', 'Source Folder and Destination Base are required.')
            return

        data['source_folder']    = src
        data['destination_base'] = dst
        data['bat_output_path']  = self._bat.text().strip()
        data['items_per_page']   = self._items_per_page.value()

        html_fname = self._html_fname.text().strip()
        if html_fname:
            data['html_filename'] = html_fname

        # API keys
        if 'api' not in data:
            data['api'] = {}
        for key, edit in self._api_widgets.items():
            data['api'][key] = edit.text().strip()

        # Map api sub-keys to top-level provider key names used by providers
        # e.g. games.json 'api' has 'client_id'/'client_secret' for IGDB
        api = data['api']
        mt  = self._lib_config.media_type
        if mt == 'games':
            api['client_id']     = api.pop('igdb_client_id',     api.get('client_id', ''))
            api['client_secret'] = api.pop('igdb_client_secret', api.get('client_secret', ''))
            api['api_key']       = api.pop('rawg_api_key',       api.get('api_key', ''))
        elif mt == 'movies':
            api['tmdb_api_key'] = api.get('tmdb_api_key', '')
            api['omdb_api_key'] = api.get('omdb_api_key', '')
        elif mt == 'books':
            api['api_key'] = api.pop('google_books_api_key', api.get('api_key', ''))
        elif mt == 'comics':
            api['api_key'] = api.pop('comic_vine_api_key', api.get('api_key', ''))

        try:
            with open(self._lib_config.path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            # Reload the config data in-memory
            self._lib_config.data = data
            QMessageBox.information(self, 'Saved', 'Settings saved.')
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Failed to save:\n{e}')

    # ──────────────────────────────────────────────────────────────────
    def _browse_folder(self, edit: QLineEdit):
        folder = QFileDialog.getExistingDirectory(self, 'Select Folder', edit.text())
        if folder:
            edit.setText(folder)

    def _browse_file(self, edit: QLineEdit):
        path, _ = QFileDialog.getSaveFileName(
            self, 'Select Output File', edit.text(), 'Batch Files (*.bat);;All Files (*)'
        )
        if path:
            edit.setText(path)
