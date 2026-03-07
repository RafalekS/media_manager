"""
Failed items dialog — shows items where metadata lookup failed.
Allows manual genre assignment or marking as skipped.
"""

import json
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QMessageBox, QDialogButtonBox,
)


class FailedItemsDialog(QDialog):
    """Shows failed metadata items with manual genre assignment."""

    def __init__(self, lib_config, plugin, parent=None):
        super().__init__(parent)
        self._lib_config = lib_config
        self._plugin     = plugin
        self._data       = {}
        self._genres     = self._load_genres()

        self.setWindowTitle(f'Failed Items — {plugin.name}')
        self.resize(900, 600)
        self._setup_ui()
        self._load_data()

    def _load_genres(self) -> list:
        genre_file = self._lib_config.genre_file
        if genre_file and Path(genre_file).exists():
            with open(genre_file, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                return sorted(raw.values())
            if isinstance(raw, list):
                return sorted(raw)
        return []

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        lbl = QLabel('Items where metadata lookup failed. Assign a genre manually or mark as skipped.')
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(['Folder Name', 'Clean Name', 'Genre'])
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionsMovable(True)
        self._table.setColumnWidth(0, 280)
        self._table.setColumnWidth(1, 280)
        self._table.setColumnWidth(2, 200)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_save = QPushButton('Save Changes')
        btn_save.clicked.connect(self._save)
        btn_row.addWidget(btn_save)
        btn_close = QPushButton('Close')
        btn_close.setObjectName('btn_secondary')
        btn_close.clicked.connect(self.reject)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _load_data(self):
        meta_file = Path(self._lib_config.metadata_file)
        if not meta_file.exists():
            return

        with open(meta_file, 'r', encoding='utf-8') as f:
            raw = json.load(f)

        items = raw.get('processed_items', raw.get('processed_games', {}))

        self._table.setRowCount(0)
        for clean_name, info in items.items():
            if info.get('igdb_found', info.get('found', False)):
                continue  # skip successful ones

            row = self._table.rowCount()
            self._table.insertRow(row)

            folder = info.get('original_name', clean_name)
            self._table.setItem(row, 0, QTableWidgetItem(folder))
            self._table.setItem(row, 1, QTableWidgetItem(clean_name))

            combo = QComboBox()
            combo.setStyleSheet("combobox-popup: 0;")
            combo.view().setStyleSheet("max-height: 300px;")
            combo.addItem('-- Skip --')
            combo.addItems(self._genres)
            existing_genre = info.get('genre', '')
            if existing_genre:
                idx = combo.findText(existing_genre)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            self._table.setCellWidget(row, 2, combo)
            self._data[clean_name] = info

    def _save(self):
        meta_file = Path(self._lib_config.metadata_file)
        if not meta_file.exists():
            QMessageBox.warning(self, 'Error', 'Metadata file not found.')
            return

        with open(meta_file, 'r', encoding='utf-8') as f:
            raw = json.load(f)

        key = 'processed_items' if 'processed_items' in raw else 'processed_games'
        items = raw.get(key, {})

        for row in range(self._table.rowCount()):
            clean_name = self._table.item(row, 1).text()
            combo = self._table.cellWidget(row, 2)
            genre = combo.currentText()
            if genre == '-- Skip --':
                continue
            if clean_name in items:
                items[clean_name]['genre']      = genre
                items[clean_name]['found']      = True
                items[clean_name]['igdb_found'] = True
                items[clean_name]['manual']     = True
                items[clean_name]['display_name'] = items[clean_name].get(
                    'original_name', clean_name
                )

        raw[key] = items
        with open(meta_file, 'w', encoding='utf-8') as f:
            json.dump(raw, f, indent=2, ensure_ascii=False)

        QMessageBox.information(self, 'Saved', 'Manual assignments saved.')
        self.accept()
