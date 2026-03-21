"""
Library browser page — generic table view driven by plugin.columns.
Shows all organized items enriched with metadata.
Data loading runs in a background thread to keep the GUI responsive.
"""

import json
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QStandardItemModel, QStandardItem
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableView, QHeaderView, QLineEdit, QComboBox, QFrame,
    QCheckBox, QMessageBox,
)

_KEY_ROLE = Qt.ItemDataRole.UserRole  # stores metadata dict key on col-0 cell


# ── Background loader ─────────────────────────────────────────────────────────

class _LoadWorker(QThread):
    done = pyqtSignal(list)   # emits flat list of item dicts

    def __init__(self, lib_config, plugin):
        super().__init__()
        self._lib_config = lib_config
        self._plugin     = plugin

    def run(self):
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
        for key, entry in items.items():
            e = dict(entry)
            e['_key']         = key
            e['name']         = entry.get('original_name') or entry.get('name', '')
            e['display_name'] = entry.get('name', '')
            flat.append(e)
        self.done.emit(flat)


# ── Browser widget ────────────────────────────────────────────────────────────

class LibraryBrowser(QWidget):
    """
    Generic table browser — columns come from plugin.columns.
    First column is always 'Name' (folder name), read-only.
    Plugin columns are editable via double-click (except 'full_path').
    """

    # Column keys that must never be inline-edited
    _READONLY_KEYS = frozenset({'full_path'})

    def __init__(self, lib_config, plugin, ui_state, parent=None):
        super().__init__(parent)
        self._lib_config   = lib_config
        self._plugin       = plugin
        self._ui_state     = ui_state
        self._state_key    = f'browser_{plugin.media_type}'
        self._data         = []
        self._state_loaded = False
        self._worker       = None
        self._loading      = False   # suppress itemChanged during populate
        self._deleted_keys = set()   # keys removed from table, pending save

        # Find genre column index in the table (col 0 = name, then plugin cols)
        self._genre_col_idx = next(
            (i for i, (key, _, _) in enumerate(plugin.columns) if key == 'genre'),
            None,
        )
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
        self._model.itemChanged.connect(self._on_item_changed)

        self._table = QTableView()
        self._table.setModel(self._model)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableView.EditTrigger.DoubleClicked)
        self._table.setSortingEnabled(False)

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionsMovable(True)
        header.sectionResized.connect(self._on_header_changed)
        header.sectionMoved.connect(self._on_header_changed)
        header.sortIndicatorChanged.connect(self._on_header_changed)

        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table)

        # Action row
        act = QHBoxLayout()
        act.addStretch()

        self._btn_delete = QPushButton('Delete Selected')
        self._btn_delete.setEnabled(False)
        self._btn_delete.clicked.connect(self._delete_selected)
        act.addWidget(self._btn_delete)

        self._btn_save = QPushButton('Save Changes')
        self._btn_save.setEnabled(False)
        self._btn_save.clicked.connect(self._save_changes)
        act.addWidget(self._btn_save)

        layout.addLayout(act)

        self._table.selectionModel().selectionChanged.connect(self._on_selection_changed)

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
        self._btn_save.setEnabled(False)
        self._btn_delete.setEnabled(False)
        self._deleted_keys.clear()

        self._worker = _LoadWorker(self._lib_config, self._plugin)
        self._worker.done.connect(self._on_data_loaded)
        self._worker.start()

    def _on_data_loaded(self, flat_list: list):
        self._data = flat_list
        self._btn_refresh.setEnabled(True)
        self._populate_table()
        self._populate_genre_filter()

    def _populate_table(self):
        self._loading = True
        self._model.setRowCount(0)
        self._table.setSortingEnabled(False)

        col_keys = ['name'] + [col[0] for col in self._plugin.columns]

        # Determine which table column indices are read-only
        readonly_cols = {0}  # folder name — never editable
        for i, (key, _, _) in enumerate(self._plugin.columns, start=1):
            if key in self._READONLY_KEYS:
                readonly_cols.add(i)

        for item in self._data:
            meta_key = item.get('_key', '')
            row = []
            for col_idx, key in enumerate(col_keys):
                val  = item.get(key, '') or ''
                cell = QStandardItem(str(val))
                if col_idx in readonly_cols:
                    cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col_idx == 0:
                    cell.setData(meta_key, _KEY_ROLE)
                row.append(cell)
            self._model.appendRow(row)

        self._table.setSortingEnabled(True)
        self._lbl_status.setText(f'{len(self._data)} items')

        if self._chk_wrap.isChecked():
            self._table.resizeRowsToContents()

        if not self._state_loaded:
            self._state_loaded = True
            QTimer.singleShot(0, lambda: self._ui_state.restore_table(self._table, self._state_key))

        self._loading = False
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

    # ──────────────────────────────────────────────────────────────────
    def _on_item_changed(self, _item):
        if not self._loading:
            self._btn_save.setEnabled(True)

    def _on_selection_changed(self, selected, _deselected):
        self._btn_delete.setEnabled(bool(self._table.selectionModel().selectedRows()))

    def _toggle_wrap(self, checked: bool):
        self._table.setWordWrap(checked)
        if checked:
            self._table.resizeRowsToContents()
        else:
            self._table.verticalHeader().setDefaultSectionSize(30)
            for row in range(self._model.rowCount()):
                self._table.setRowHeight(row, 30)

    # ──────────────────────────────────────────────────────────────────
    def _delete_selected(self):
        rows = sorted(
            {idx.row() for idx in self._table.selectionModel().selectedRows()},
            reverse=True,
        )
        if not rows:
            return

        ans = QMessageBox.question(
            self, 'Delete entries',
            f'Remove {len(rows)} entr{"y" if len(rows) == 1 else "ies"} from the database?\n'
            'This cannot be undone without re-running metadata.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return

        for row in rows:
            key_item = self._model.item(row, 0)
            if key_item:
                key = key_item.data(_KEY_ROLE)
                if key:
                    self._deleted_keys.add(key)
            self._model.removeRow(row)

        total = self._model.rowCount()
        self._lbl_status.setText(f'{total} items')
        self._btn_save.setEnabled(True)
        self._btn_delete.setEnabled(False)

    # ──────────────────────────────────────────────────────────────────
    def _save_changes(self):
        meta_file = Path(self._lib_config.metadata_file)
        try:
            with open(meta_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Could not read metadata file:\n{e}')
            return

        items_key = 'processed_items' if 'processed_items' in data else 'processed_games'
        items = data.get(items_key, {})

        # Remove deleted entries
        for key in self._deleted_keys:
            items.pop(key, None)

        # Apply in-table edits
        col_keys = ['name'] + [col[0] for col in self._plugin.columns]
        editable_keys = {
            col[0] for col in self._plugin.columns
            if col[0] not in self._READONLY_KEYS
        }

        for row in range(self._model.rowCount()):
            key_item = self._model.item(row, 0)
            if not key_item:
                continue
            meta_key = key_item.data(_KEY_ROLE)
            if not meta_key or meta_key not in items:
                continue
            for col_idx, col_key in enumerate(col_keys):
                if col_key not in editable_keys:
                    continue
                cell = self._model.item(row, col_idx)
                if cell:
                    items[meta_key][col_key] = cell.text()
                    # display_name is stored as 'name' in the raw entry
                    if col_key == 'display_name':
                        items[meta_key]['name'] = cell.text()

        data[items_key] = items
        try:
            with open(meta_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Could not save metadata file:\n{e}')
            return

        self._deleted_keys.clear()
        self._btn_save.setEnabled(False)
        self._lbl_status.setText(f'{self._model.rowCount()} items  (saved)')

    # ──────────────────────────────────────────────────────────────────
    def _apply_filter(self):
        search = self._search.text().strip().lower()
        genre  = self._genre_combo.currentText()
        if genre == 'All Genres':
            genre = ''

        for row in range(self._model.rowCount()):
            if genre and self._table_genre_col is not None:
                cell = self._model.item(row, self._table_genre_col)
                genre_match = bool(cell and cell.text() == genre)
            else:
                genre_match = True

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
        """Abort any in-progress background load."""
        if self._worker and self._worker.isRunning():
            self._worker.done.disconnect()
            self._worker.quit()
            self._worker.wait(2000)

    def hideEvent(self, event):
        self._debounce.stop()
        if self._state_loaded:
            self._save_table_state()
        super().hideEvent(event)
