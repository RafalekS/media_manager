"""
Library browser page — generic table view driven by plugin.columns.
Shows all organized items enriched with metadata.
Data loading runs in a background thread to keep the GUI responsive.
"""

from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QStandardItemModel, QStandardItem
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableView, QHeaderView, QLineEdit, QComboBox, QFrame, QCheckBox,
)


# ── Background loader ─────────────────────────────────────────────────────────

class _LoadWorker(QThread):
    done = pyqtSignal(list)   # emits flat list of item dicts

    def __init__(self, lib_config, plugin):
        super().__init__()
        self._lib_config = lib_config
        self._plugin     = plugin

    def run(self):
        import json

        meta_file = Path(self._lib_config.metadata_file)
        if not meta_file.exists():
            self.done.emit([])
            return

        try:
            with open(meta_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f'[ERROR] Failed to load metadata: {e}')
            self.done.emit([])
            return

        items = data.get('processed_items', data.get('processed_games', {}))
        flat = []
        for entry in items.values():
            e = dict(entry)
            # Table col 0 ('name') = folder/original name
            # plugin column 'display_name' = provider/matched name
            e['name']         = entry.get('original_name') or entry.get('name', '')
            e['display_name'] = entry.get('name', '')
            flat.append(e)
        self.done.emit(flat)


# ── Browser widget ────────────────────────────────────────────────────────────

class LibraryBrowser(QWidget):
    """
    Generic table browser — columns come from plugin.columns.
    First column is always 'Name' (folder name).
    """

    def __init__(self, lib_config, plugin, ui_state, parent=None):
        super().__init__(parent)
        self._lib_config   = lib_config
        self._plugin       = plugin
        self._ui_state     = ui_state
        self._state_key    = f'browser_{plugin.media_type}'
        self._data         = []          # flat list of item dicts
        self._state_loaded = False
        self._worker       = None

        # Find which column index (in plugin.columns) holds 'genre'
        self._genre_col_idx = next(
            (i for i, (key, _, _) in enumerate(plugin.columns) if key == 'genre'),
            None,
        )
        # In the table: col 0 = name, cols 1..N = plugin.columns
        self._table_genre_col = (
            self._genre_col_idx + 1 if self._genre_col_idx is not None else None
        )

        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(500)
        self._debounce.timeout.connect(self._save_table_state)

        self._setup_ui()

    # ──────────────────────────────────────────────────────────────────
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # Header row
        hdr = QHBoxLayout()
        title = QLabel(f'{self._plugin.icon} {self._plugin.name} Library')
        title.setProperty('role', 'title')
        hdr.addWidget(title)
        hdr.addStretch()

        self._lbl_status = QLabel('Click Refresh to load.')
        self._lbl_status.setProperty('role', 'muted')
        hdr.addWidget(self._lbl_status)

        self._btn_refresh = QPushButton('Refresh')
        self._btn_refresh.clicked.connect(self.load_data)
        hdr.addWidget(self._btn_refresh)

        layout.addLayout(hdr)

        # Filter row
        flt = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText('Search...')
        self._search.textChanged.connect(self._apply_filter)
        flt.addWidget(self._search, 2)

        self._genre_combo = QComboBox()
        self._genre_combo.setMinimumWidth(160)
        self._genre_combo.setStyleSheet("combobox-popup: 0;")
        self._genre_combo.view().setStyleSheet("max-height: 300px;")
        self._genre_combo.addItem('All Genres')
        self._genre_combo.currentIndexChanged.connect(self._apply_filter)
        flt.addWidget(self._genre_combo, 1)

        self._chk_wrap = QCheckBox('Wrap text')
        self._chk_wrap.setChecked(False)
        self._chk_wrap.toggled.connect(self._toggle_wrap)
        flt.addWidget(self._chk_wrap)

        layout.addLayout(flt)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        # Table
        self._model = QStandardItemModel()

        self._table = QTableView()
        self._table.setModel(self._model)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self._table.setSortingEnabled(False)

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionsMovable(True)
        header.sectionResized.connect(self._on_header_changed)
        header.sectionMoved.connect(self._on_header_changed)
        header.sortIndicatorChanged.connect(self._on_header_changed)

        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table)

        self._build_columns()

    def _build_columns(self):
        headers = ['Name'] + [col[1] for col in self._plugin.columns]
        self._model.setHorizontalHeaderLabels(headers)
        self._table.setColumnWidth(0, 220)
        for i, (_, _, width) in enumerate(self._plugin.columns, start=1):
            self._table.setColumnWidth(i, width)

    # ──────────────────────────────────────────────────────────────────
    def load_data(self):
        """Start background load — GUI stays responsive."""
        if self._worker and self._worker.isRunning():
            return

        self._btn_refresh.setEnabled(False)
        self._lbl_status.setText('Loading...')

        self._worker = _LoadWorker(self._lib_config, self._plugin)
        self._worker.done.connect(self._on_data_loaded)
        self._worker.start()

    def _on_data_loaded(self, flat_list: list):
        self._data = flat_list
        self._btn_refresh.setEnabled(True)
        self._populate_table()
        self._populate_genre_filter()

    def _populate_table(self):
        self._model.setRowCount(0)
        self._table.setSortingEnabled(False)

        # Column key order: 'name' (folder name) + plugin column keys
        col_keys = ['name'] + [col[0] for col in self._plugin.columns]

        for item in self._data:
            row = []
            for key in col_keys:
                val = item.get(key, '') or ''
                cell = QStandardItem(str(val))
                cell.setEditable(False)
                row.append(cell)
            self._model.appendRow(row)

        self._table.setSortingEnabled(True)
        self._lbl_status.setText(f'{len(self._data)} items')

        if self._chk_wrap.isChecked():
            self._table.resizeRowsToContents()

        if not self._state_loaded:
            self._ui_state.restore_table(self._table, self._state_key)
            self._state_loaded = True

        self._apply_filter()

    def _populate_genre_filter(self):
        genres = sorted({item.get('genre', '') for item in self._data if item.get('genre')})
        current = self._genre_combo.currentText()
        self._genre_combo.blockSignals(True)
        self._genre_combo.clear()
        self._genre_combo.addItem('All Genres')
        for g in genres:
            self._genre_combo.addItem(g)
        idx = self._genre_combo.findText(current)
        self._genre_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._genre_combo.blockSignals(False)

    def _toggle_wrap(self, checked: bool):
        self._table.setWordWrap(checked)
        if checked:
            self._table.resizeRowsToContents()
        else:
            self._table.verticalHeader().setDefaultSectionSize(30)
            for row in range(self._model.rowCount()):
                self._table.setRowHeight(row, 30)

    # ──────────────────────────────────────────────────────────────────
    def _apply_filter(self):
        search = self._search.text().strip().lower()
        genre  = self._genre_combo.currentText()
        if genre == 'All Genres':
            genre = ''

        for row in range(self._model.rowCount()):
            # Genre match
            if genre and self._table_genre_col is not None:
                cell = self._model.item(row, self._table_genre_col)
                genre_match = bool(cell and cell.text() == genre)
            else:
                genre_match = True

            # Search match (all columns)
            if search:
                search_match = False
                for col in range(self._model.columnCount()):
                    cell = self._model.item(row, col)
                    if cell and search in cell.text().lower():
                        search_match = True
                        break
            else:
                search_match = True

            self._table.setRowHidden(row, not (genre_match and search_match))

    # ──────────────────────────────────────────────────────────────────
    def _on_header_changed(self, *_):
        if self._state_loaded:
            self._debounce.start()

    def _save_table_state(self):
        self._ui_state.save_table(self._table, self._state_key)

    def save_state(self):
        """Explicitly save column state — call from closeEvent."""
        self._debounce.stop()
        if self._state_loaded:
            self._save_table_state()

    def stop_worker(self):
        """Abort any in-progress background load (call before replacing this page)."""
        if self._worker and self._worker.isRunning():
            self._worker.done.disconnect()
            self._worker.quit()
            self._worker.wait(2000)

    def hideEvent(self, event):
        self._debounce.stop()
        if self._state_loaded:
            self._save_table_state()
        super().hideEvent(event)
