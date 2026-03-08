"""
Settings page — per-library paths, providers (enable/disable + API keys), rate limit, HTML options.
"""

import json
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QSpinBox, QDoubleSpinBox,
    QPushButton, QGroupBox, QScrollArea, QMessageBox,
    QFileDialog, QCheckBox, QFrame,
)
from PyQt6.QtCore import Qt


# All providers per library:
# (provider_id, display_name, is_primary, [(api_key, label, is_secret), ...])
_LIBRARY_PROVIDERS = {
    'games': [
        ('igdb',       'IGDB',        True,  [
            ('client_id',     'Client ID',     False),
            ('client_secret', 'Client Secret', True),
        ]),
        ('rawg',       'RAWG',        False, [
            ('api_key',       'API Key',        True),
        ]),
        ('giantbomb',  'Giant Bomb',  False, [
            ('giantbomb_api_key', 'API Key',    True),
        ]),
    ],
    'movies': [
        ('tmdb',   'TMDB',   True,  [('tmdb_api_key',   'API Key',   True)]),
        ('omdb',   'OMDB',   False, [('omdb_api_key',   'API Key',   True)]),
        ('trakt',  'Trakt',  False, [('trakt_client_id','Client ID', True)]),
    ],
    'books': [
        ('google_books',     'Google Books',     True,  [('google_books_api_key', 'API Key', True)]),
        ('open_library',     'Open Library',     False, []),
        ('internet_archive', 'Internet Archive', False, []),
    ],
    'comics': [
        ('comic_vine', 'Comic Vine', True,  [('comic_vine_api_key',  'API Key',      True)]),
        ('mangadex',   'MangaDex',   False, []),
        ('marvel',     'Marvel',     False, [
            ('marvel_public_key',  'Public Key',  False),
            ('marvel_private_key', 'Private Key', True),
        ]),
    ],
    'music': [
        ('musicbrainz', 'MusicBrainz', True,  []),
        ('lastfm',      'Last.fm',     False, [('lastfm_api_key', 'API Key', True)]),
        ('discogs',     'Discogs',     False, [('discogs_token',  'Token',   True)]),
    ],
}


class SettingsPage(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lib_config       = None
        self._provider_widgets = {}   # provider_id -> {'chk': QCheckBox, 'fields': {key: QLineEdit}}
        self._providers_grp    = None
        self._providers_layout = None
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

        # ── Providers (rebuilt per library) ──────────────────────────
        self._providers_grp = QGroupBox('Metadata Providers')
        self._providers_layout = QVBoxLayout(self._providers_grp)
        self._layout.addWidget(self._providers_grp)

        # ── Rate limit ───────────────────────────────────────────────
        rl_grp = QGroupBox('Rate Limiting')
        rl_form = QFormLayout(rl_grp)

        self._rate_limit = QDoubleSpinBox()
        self._rate_limit.setRange(0.1, 10.0)
        self._rate_limit.setSingleStep(0.1)
        self._rate_limit.setDecimals(1)
        self._rate_limit.setValue(0.25)
        self._rate_limit.setSuffix(' s between requests')
        rl_form.addRow('Rate limit:', self._rate_limit)

        self._layout.addWidget(rl_grp)

        # ── HTML Options ─────────────────────────────────────────────
        html_grp = QGroupBox('HTML Options')
        html_form = QFormLayout(html_grp)

        self._items_per_page = QSpinBox()
        self._items_per_page.setRange(10, 1000)
        self._items_per_page.setSingleStep(10)
        self._items_per_page.setValue(50)
        html_form.addRow('Items per page:', self._items_per_page)

        self._layout.addWidget(html_grp)

        # ── Save button ──────────────────────────────────────────────
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
        self._lib_lbl.setText(f'Active library: {mt.capitalize()}')

        self._src.setText(str(lib_config.data.get('source_folder', '')))
        self._dest.setText(str(lib_config.data.get('destination_base', '')))
        self._bat.setText(str(lib_config.data.get('bat_output_path', '')))
        self._html_fname.setText(lib_config.data.get('html_filename', ''))
        self._items_per_page.setValue(lib_config.data.get('items_per_page', 50))
        self._rate_limit.setValue(lib_config.data.get('rate_limit', 0.25))

        self._rebuild_providers(mt, lib_config)

    def _rebuild_providers(self, media_type: str, lib_config):
        # Clear existing provider widgets
        while self._providers_layout.count():
            item = self._providers_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._provider_widgets.clear()

        api_data     = lib_config.data.get('api', {})
        supplements  = lib_config.data.get('supplement_providers', [])
        primary_id   = lib_config.data.get('primary_provider', '')

        providers = _LIBRARY_PROVIDERS.get(media_type, [])

        for provider_id, display_name, is_primary, api_fields in providers:
            frame = QFrame()
            frame.setFrameShape(QFrame.Shape.StyledPanel)
            frame_lay = QVBoxLayout(frame)
            frame_lay.setContentsMargins(8, 6, 8, 6)
            frame_lay.setSpacing(4)

            # Header row: checkbox + name + badge
            hdr = QHBoxLayout()

            chk = QCheckBox(display_name)
            chk.setStyleSheet('font-weight: bold;')
            if is_primary:
                chk.setChecked(True)
                chk.setEnabled(False)   # primary always on
            else:
                chk.setChecked(provider_id in supplements)
            hdr.addWidget(chk)

            badge = QLabel('Primary' if is_primary else 'Supplement')
            badge.setStyleSheet(
                'color: white; background: #2563eb; padding: 1px 6px; border-radius: 2px; font-size: 8pt;'
                if is_primary else
                'color: white; background: #64748b; padding: 1px 6px; border-radius: 2px; font-size: 8pt;'
            )
            hdr.addWidget(badge)
            hdr.addStretch()
            frame_lay.addLayout(hdr)

            # API key fields
            field_widgets = {}
            if api_fields:
                form = QFormLayout()
                form.setContentsMargins(16, 0, 0, 0)
                for key, label, secret in api_fields:
                    edit = QLineEdit()
                    edit.setText(api_data.get(key, ''))
                    if secret:
                        edit.setEchoMode(QLineEdit.EchoMode.Password)
                    form.addRow(f'{label}:', edit)
                    field_widgets[key] = edit
                frame_lay.addLayout(form)
            else:
                no_key = QLabel('No API key required')
                no_key.setProperty('role', 'muted')
                no_key.setContentsMargins(16, 0, 0, 0)
                frame_lay.addWidget(no_key)

            self._providers_layout.addWidget(frame)
            self._provider_widgets[provider_id] = {
                'chk':    chk,
                'fields': field_widgets,
            }

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
        data['rate_limit']       = self._rate_limit.value()

        html_fname = self._html_fname.text().strip()
        if html_fname:
            data['html_filename'] = html_fname

        # Rebuild supplement_providers from checkboxes
        supplements = []
        if 'api' not in data:
            data['api'] = {}

        for provider_id, pw in self._provider_widgets.items():
            chk = pw['chk']
            # primary is always enabled (checkbox disabled), supplements by checkbox
            is_primary = not chk.isEnabled()
            if not is_primary and chk.isChecked():
                supplements.append(provider_id)
            # Save API key values regardless
            for key, edit in pw['fields'].items():
                data['api'][key] = edit.text().strip()

        data['supplement_providers'] = supplements

        try:
            with open(self._lib_config.path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
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
            self, 'Select Output File', edit.text(),
            'Batch Files (*.bat);;All Files (*)'
        )
        if path:
            edit.setText(path)
