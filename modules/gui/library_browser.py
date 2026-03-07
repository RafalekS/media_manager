"""
Library browser page — generic table view driven by plugin.columns.
Shows all organized items enriched with metadata.
"""

import os
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QSortFilterProxyModel
from PyQt6.QtGui import QStandardItemModel, QStandardItem
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableView, QHeaderView, QLineEdit, QComboBox, QFrame,
)


class LibraryBrowser(QWidget):
    """
    Generic table browser — columns come from plugin.columns.
    Extra columns prepended: Folder Name (always present).
    """

    def __init__(self, lib_config, plugin, ui_state, parent=None):
        super().__init__(parent)
        self._lib_config = lib_config
        self._plugin     = plugin
        self._ui_state   = ui_state
        self._state_key  = f'browser_{plugin.media_type}'
        self._data       = []
        self._state_loaded = False

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

        self._lbl_count = QLabel('')
        self._lbl_count.setProperty('role', 'muted')
        hdr.addWidget(self._lbl_count)

        btn_refresh = QPushButton('Refresh')
        btn_refresh.clicked.connect(self.load_data)
        hdr.addWidget(btn_refresh)

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

        layout.addLayout(flt)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        # Table
        self._model = QStandardItemModel()
        self._proxy = QSortFilterProxyModel()
        self._proxy.setSourceModel(self._model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._proxy.setFilterKeyColumn(-1)  # search all columns

        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self._table.setSortingEnabled(False)  # enabled after load

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
        """Set up column headers from plugin.columns + Folder column."""
        headers = ['Folder'] + [col[1] for col in self._plugin.columns]
        self._model.setHorizontalHeaderLabels(headers)
        # Default widths
        self._table.setColumnWidth(0, 200)
        for i, (_, _, width) in enumerate(self._plugin.columns, start=1):
            self._table.setColumnWidth(i, width)

    # ──────────────────────────────────────────────────────────────────
    def load_data(self):
        from modules.core.utils import scan_organized_items, load_metadata_progress

        dest = self._lib_config.destination_base
        skip = getattr(self._lib_config, 'skip_folders', [])
        organized = scan_organized_items(dest, skip)

        meta_file = self._lib_config.metadata_file
        if Path(meta_file).exists():
            from modules.core.utils import enrich_with_metadata
            enrich_with_metadata(organized, meta_file)

        self._data = organized
        self._populate_table()
        self._populate_genre_filter()

    def _populate_table(self):
        self._model.setRowCount(0)
        self._table.setSortingEnabled(False)

        col_keys = ['folder_name'] + [col[0] for col in self._plugin.columns]

        for item in self._data:
            row = []
            for key in col_keys:
                val = item.get(key, '') or ''
                cell = QStandardItem(str(val))
                cell.setEditable(False)
                row.append(cell)
            self._model.appendRow(row)

        self._table.setSortingEnabled(True)
        self._lbl_count.setText(f'{len(self._data)} items')

        if not self._state_loaded:
            self._ui_state.restore_table(self._table, self._state_key)
            self._state_loaded = True

    def _populate_genre_filter(self):
        genres = sorted({item.get('genre', '') for item in self._data if item.get('genre')})
        self._genre_combo.blockSignals(True)
        current = self._genre_combo.currentText()
        self._genre_combo.clear()
        self._genre_combo.addItem('All Genres')
        for g in genres:
            self._genre_combo.addItem(g)
        idx = self._genre_combo.findText(current)
        if idx >= 0:
            self._genre_combo.setCurrentIndex(idx)
        self._genre_combo.blockSignals(False)

    # ──────────────────────────────────────────────────────────────────
    def _apply_filter(self):
        search = self._search.text().strip()
        genre  = self._genre_combo.currentText()
        if genre == 'All Genres':
            genre = ''

        if not genre:
            self._proxy.setFilterWildcard(f'*{search}*' if search else '')
        else:
            # Filter manually via row hiding when genre filter active
            self._proxy.setFilterFixedString('')
            for row in range(self._model.rowCount()):
                item_genre = self._model.item(row, 1)  # genre col after folder
                genre_match = (not genre) or (item_genre and item_genre.text() == genre)
                # search across all columns
                search_match = not search
                if not search_match:
                    for col in range(self._model.columnCount()):
                        cell = self._model.item(row, col)
                        if cell and search.lower() in cell.text().lower():
                            search_match = True
                            break
                # proxy row = source row when no proxy filter active
                self._table.setRowHidden(row, not (genre_match and search_match))
            return

        visible = sum(
            1 for row in range(self._proxy.rowCount())
            if not self._table.isRowHidden(row)
        )
        self._lbl_count.setText(f'{self._proxy.rowCount()} items')

    # ──────────────────────────────────────────────────────────────────
    def _on_header_changed(self, *_):
        if self._state_loaded:
            self._debounce.start()

    def _save_table_state(self):
        self._ui_state.save_table(self._table, self._state_key)

    def hideEvent(self, event):
        self._debounce.stop()
        if self._state_loaded:
            self._save_table_state()
        super().hideEvent(event)
