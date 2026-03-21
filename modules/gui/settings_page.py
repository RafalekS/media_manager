"""
Settings page — per-library paths, providers (enable/disable + API keys), rate limit, HTML options.
"""

import json
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QSpinBox, QDoubleSpinBox,
    QPushButton, QGroupBox, QScrollArea, QMessageBox,
    QFileDialog, QCheckBox, QFrame, QComboBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal


class _TestWorker(QThread):
    result = pyqtSignal(bool, str)  # success, message

    def __init__(self, provider_id: str, api_config: dict):
        super().__init__()
        self._provider_id = provider_id
        self._api_config  = api_config

    def run(self):
        try:
            from modules.providers import get_provider_class
            cls      = get_provider_class(self._provider_id)
            provider = cls(self._api_config)
            success, message = provider.test_connection()
            self.result.emit(success, message)
        except Exception as e:
            self.result.emit(False, str(e))


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
        ('itchio',     'itch.io',     False, [
            ('itch_api_key',      'API Key',    True),
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

        self._organize_enabled = QCheckBox('Enable Organize step (requires separate Source folder)')
        paths_form.addRow('', self._organize_enabled)

        self._scan_mode = QComboBox()
        self._scan_mode.addItems(['folders', 'files'])
        self._scan_mode.currentTextChanged.connect(self._on_scan_mode_changed)
        paths_form.addRow('Scan mode:', self._scan_mode)

        self._scan_depth = QSpinBox()
        self._scan_depth.setRange(1, 5)
        self._scan_depth.setValue(1)
        self._scan_depth.setToolTip(
            '1 = immediate subfolders (games, movies)\n'
            '2 = Genre\\Artist level (music)\n'
            '3 = Genre\\Artist\\Album level'
        )
        self._scan_depth_label = QLabel('Scan depth:')
        paths_form.addRow(self._scan_depth_label, self._scan_depth)

        self._file_extensions = QLineEdit()
        self._file_extensions.setPlaceholderText('e.g. .mp3, .flac, .m4a  (comma-separated, only for Files mode)')
        self._ext_row_label = QLabel('File extensions:')
        paths_form.addRow(self._ext_row_label, self._file_extensions)

        self._extractor_path = QLineEdit()
        self._extractor_path.setPlaceholderText(
            'Leave blank to auto-detect  (e.g. C:\\Program Files\\WinRAR\\UnRAR.exe)'
        )
        paths_form.addRow('Extractor Path:', self._path_row(self._extractor_path, folder=False, open_file=True))

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

        # ── QNAP SSH Extraction ──────────────────────────────────────
        ssh_grp = QGroupBox('QNAP SSH Extraction (for large archives)')
        ssh_form = QFormLayout(ssh_grp)

        self._ssh_host = QLineEdit()
        self._ssh_host.setPlaceholderText('e.g. 192.168.0.166')
        ssh_form.addRow('SSH Host:', self._ssh_host)

        self._ssh_user = QLineEdit()
        self._ssh_user.setPlaceholderText('e.g. rls1203')
        ssh_form.addRow('SSH User:', self._ssh_user)

        self._ssh_key_path = QLineEdit()
        self._ssh_key_path.setPlaceholderText(
            r'e.g. C:\Users\r_sta\.ssh\P16_id_rsa  (leave blank for default key)'
        )
        ssh_form.addRow('SSH Key Path:', self._path_row(self._ssh_key_path, folder=False, open_file=True))

        self._ssh_source_path = QLineEdit()
        self._ssh_source_path.setPlaceholderText('e.g. /share/CACHEDEV1_DATA/FULL/Gry/New')
        ssh_form.addRow('Remote Source Path:', self._ssh_source_path)

        self._ssh_script_path = QLineEdit()
        self._ssh_script_path.setPlaceholderText(
            'e.g. /share/homes/rls1203/scripts/extractor_silent.sh'
        )
        ssh_form.addRow('Script Path on NAS:', self._ssh_script_path)

        self._layout.addWidget(ssh_grp)

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

    def _path_row(self, line_edit: QLineEdit, folder: bool, open_file: bool = False) -> QWidget:
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(line_edit)
        btn = QPushButton('Browse')
        btn.setObjectName('btn_secondary')
        if folder:
            btn.clicked.connect(lambda: self._browse_folder(line_edit))
        elif open_file:
            btn.clicked.connect(lambda: self._browse_open_file(line_edit))
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
        self._organize_enabled.setChecked(lib_config.data.get('organize_enabled', True))

        scan_mode = lib_config.data.get('scan_mode', 'folders')
        self._scan_mode.blockSignals(True)
        self._scan_mode.setCurrentText(scan_mode)
        self._scan_mode.blockSignals(False)
        self._scan_depth.setValue(lib_config.data.get('scan_depth', 1))
        exts = lib_config.data.get('file_extensions', [])
        self._file_extensions.setText(', '.join(exts))
        self._on_scan_mode_changed(scan_mode)

        self._extractor_path.setText(lib_config.data.get('extractor_path', '') or '')
        self._ssh_host.setText(lib_config.data.get('ssh_host', '') or '')
        self._ssh_user.setText(lib_config.data.get('ssh_user', '') or '')
        self._ssh_key_path.setText(lib_config.data.get('ssh_key_path', '') or '')
        self._ssh_source_path.setText(lib_config.data.get('ssh_source_path', '') or '')
        self._ssh_script_path.setText(lib_config.data.get('ssh_script_path', '') or '')
        self._bat.setText(str(lib_config.data.get('bat_output_path', '')))
        self._html_fname.setText(lib_config.data.get('html_filename', ''))
        self._items_per_page.setValue(lib_config.data.get('items_per_page', 50))
        self._rate_limit.setValue(lib_config.data.get('rate_limit', 0.25))

        self._rebuild_providers(mt, lib_config)

    def _on_scan_mode_changed(self, mode: str):
        files_mode = (mode == 'files')
        self._file_extensions.setVisible(files_mode)
        self._ext_row_label.setVisible(files_mode)

    def _rebuild_providers(self, media_type: str, lib_config):
        # Abort any in-progress test workers before destroying their label widgets
        for w in getattr(self, '_test_workers', []):
            try:
                w.result.disconnect()
            except Exception:
                pass
            w.quit()
            w.wait(500)
        self._test_workers = []

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

            # API key fields + Test button
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

                # Test button row
                test_row = QHBoxLayout()
                test_row.setContentsMargins(16, 2, 0, 0)
                btn_test   = QPushButton('Test Connection')
                btn_test.setSizePolicy(btn_test.sizePolicy().horizontalPolicy(),
                                       btn_test.sizePolicy().verticalPolicy())
                test_lbl   = QLabel('')
                test_lbl.setProperty('role', 'muted')
                test_row.addWidget(btn_test)
                test_row.addWidget(test_lbl)
                test_row.addStretch()
                frame_lay.addLayout(test_row)

                # Capture loop vars for the lambda
                btn_test.clicked.connect(
                    lambda _checked, pid=provider_id, fw=field_widgets,
                           lbl=test_lbl, btn=btn_test:
                    self._test_provider(pid, fw, lbl, btn)
                )
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
    def _test_provider(self, provider_id: str, field_widgets: dict,
                       status_lbl: QLabel, btn: QPushButton):
        # Build api_config from current (unsaved) field values
        api_config = {k: w.text().strip() for k, w in field_widgets.items()}

        status_lbl.setText('Testing...')
        status_lbl.setStyleSheet('')
        btn.setEnabled(False)

        worker = _TestWorker(provider_id, api_config)
        # Keep a reference so it isn't GC'd before it finishes
        self._test_workers = getattr(self, '_test_workers', [])
        self._test_workers.append(worker)

        def on_result(success: bool, message: str):
            try:
                status_lbl.setText(('✓ ' if success else '✗ ') + message)
                status_lbl.setStyleSheet(
                    'color: #10b981;' if success else 'color: #ef4444;'
                )
                btn.setEnabled(True)
            except RuntimeError:
                pass  # Widget deleted (library switched) while test was running
            if worker in self._test_workers:
                self._test_workers.remove(worker)

        worker.result.connect(on_result)
        worker.start()

    # ──────────────────────────────────────────────────────────────────
    def _save(self):
        if not self._lib_config:
            return

        data = self._lib_config.data

        src = self._src.text().strip()
        dst = self._dest.text().strip()
        if not dst:
            QMessageBox.warning(self, 'Validation', 'Destination Base is required.')
            return

        data['source_folder']    = src
        data['destination_base'] = dst
        data['organize_enabled'] = self._organize_enabled.isChecked()
        data['scan_mode']        = self._scan_mode.currentText()
        data['scan_depth']       = self._scan_depth.value()
        raw_exts = self._file_extensions.text()
        data['file_extensions']  = [
            e.strip() for e in raw_exts.split(',') if e.strip()
        ]
        data['extractor_path']   = self._extractor_path.text().strip()
        data['ssh_host']         = self._ssh_host.text().strip()
        data['ssh_user']         = self._ssh_user.text().strip()
        data['ssh_key_path']     = self._ssh_key_path.text().strip()
        data['ssh_source_path']  = self._ssh_source_path.text().strip()
        data['ssh_script_path']  = self._ssh_script_path.text().strip()
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

    def _browse_open_file(self, edit: QLineEdit):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select File', edit.text(),
            'All Files (*)'
        )
        if path:
            edit.setText(path)
