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

# API fields per library: (json_key, display_label, is_secret)
_LIBRARY_API_FIELDS = {
    'games': [
        ('client_id',        'IGDB Client ID',      False),
        ('client_secret',    'IGDB Client Secret',  True),
        ('api_key',          'RAWG API Key',         True),
        ('giantbomb_api_key','Giant Bomb API Key',   True),
    ],
    'movies': [
        ('tmdb_api_key',    'TMDB API Key',         True),
        ('omdb_api_key',    'OMDB API Key',          True),
        ('trakt_client_id', 'Trakt Client ID',       True),
    ],
    'books': [
        ('google_books_api_key', 'Google Books API Key', True),
        # Open Library + Internet Archive need no keys
    ],
    'comics': [
        ('comic_vine_api_key',  'Comic Vine API Key',    True),
        ('marvel_public_key',   'Marvel Public Key',     False),
        ('marvel_private_key',  'Marvel Private Key',    True),
    ],
    'music': [
        ('lastfm_api_key',  'Last.fm API Key',   True),
        ('discogs_token',   'Discogs Token',      True),
        # MusicBrainz needs no key
    ],
}

_LIBRARY_API_NOTES = {
    'books':  'Open Library and Internet Archive require no API keys.',
    'music':  'MusicBrainz requires no API key.',
    'comics': 'MangaDex requires no API key.',
}


class SettingsPage(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lib_config  = None
        self._api_widgets = {}
        self._api_grp     = None
        self._api_form    = None
        self._setup_ui()

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

        # ── API Keys (rebuilt per library) ───────────────────────────
        self._api_grp  = QGroupBox('API Keys')
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

    def _path_row(self, line_edit: QLineEdit, folder: bool) -> QWidget:
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(line_edit)
        btn = QPushButton('Browse')
        btn.setObjectName('btn_secondary')
        if folder:
            btn.clicked.connect(lambda: self._browse_folder(line_edit))
        else:
            btn.clicked.connect(lambda: self._browse_file(line_edit))
        row.addWidget(btn)
        return container

    # ──────────────────────────────────────────────────────────────────
    def load_library(self, lib_config):
        self._lib_config = lib_config
        mt = lib_config.media_type
        self._lib_lbl.setText(
            f'Active library: {mt.capitalize()}  —  '
            f'Providers: {lib_config.primary_provider} + {", ".join(lib_config.supplement_providers)}'
        )

        self._src.setText(str(lib_config.data.get('source_folder', '')))
        self._dest.setText(str(lib_config.data.get('destination_base', '')))
        self._bat.setText(str(lib_config.data.get('bat_output_path', '')))
        self._html_fname.setText(lib_config.data.get('html_filename', ''))
        self._items_per_page.setValue(lib_config.data.get('items_per_page', 50))

        self._rebuild_api_fields(mt, lib_config.data.get('api', {}))

    def _rebuild_api_fields(self, media_type: str, api_data: dict):
        while self._api_form.rowCount():
            self._api_form.removeRow(0)
        self._api_widgets.clear()

        note = _LIBRARY_API_NOTES.get(media_type, '')
        if note:
            lbl = QLabel(note)
            lbl.setProperty('role', 'muted')
            self._api_form.addRow(lbl)

        fields = _LIBRARY_API_FIELDS.get(media_type, [])
        if not fields:
            if not note:
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

        if 'api' not in data:
            data['api'] = {}
        for key, edit in self._api_widgets.items():
            data['api'][key] = edit.text().strip()

        try:
            with open(self._lib_config.path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self._lib_config.data = data
            QMessageBox.information(self, 'Saved', 'Settings saved.')
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Failed to save:\n{e}')

    def _browse_folder(self, edit: QLineEdit):
        folder = QFileDialog.getExistingDirectory(self, 'Select Folder', edit.text())
        if folder:
            edit.setText(folder)

    def _browse_file(self, edit: QLineEdit):
        path, _ = QFileDialog.getSaveFileName(
            self, 'Select Output File', edit.text(),
            'Batch Files (*.bat);;All Files (*)'
        )
        if path:
            edit.setText(path)
