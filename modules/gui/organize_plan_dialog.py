"""
Organize Plan Review Dialog.

Shows the planned moves from BaseOrganizer in an editable table.
User can deselect items, change the genre/destination, then generate
the .bat file when satisfied.
"""

import os
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QHeaderView, QAbstractItemView,
    QSizePolicy as QSP, QMessageBox, QFrame, QApplication,
    QComboBox,
)

from modules.gui.table_utils import CITableWidgetItem
from modules.gui.ui_state import UIState
from modules.core.config_manager import GlobalConfig
from modules.core.utils import sanitize_folder_name, _DEFAULT_NOISE_WORDS, build_noise_re

_STATE_KEY = 'organize_plan_table'

_COL_CHECK   = 0
_COL_ACTION  = 1
_COL_ORIG    = 2
_COL_NAME    = 3
_COL_GENRE   = 4
_COL_TARGET  = 5


class OrganizePlanDialog(QDialog):
    """Review and edit the organizer move plan before generating the .bat file."""

    def __init__(self, items: list, lib_config, plugin, parent=None):
        super().__init__(parent)
        self._lib_config = lib_config
        self._plugin     = plugin
        self._items      = [dict(i) for i in items]   # deep-copy so we can edit freely
        self._base_path  = lib_config.destination_base
        self._ui_state   = UIState(GlobalConfig().ui_state_path())

        noise_words = lib_config.data.get('sanitize_noise_words', _DEFAULT_NOISE_WORDS)
        self._noise_re = build_noise_re(noise_words)

        # Load genre map for the dropdown
        self._genre_map: dict = {}   # raw_genre -> folder_name
        self._load_genre_map()

        self._save_timer = QTimer()
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(500)
        self._save_timer.timeout.connect(self._save_table_state)

        self.setWindowTitle('Review Organize Plan')
        self.resize(1200, 700)
        self._build_ui()
        self._populate()
        QTimer.singleShot(0, self._restore_state)

    # ── Genre map ──────────────────────────────────────────────────────────────

    def _load_genre_map(self):
        gf = self._lib_config.genre_file
        if gf.exists():
            import json
            try:
                with open(gf, 'r', encoding='utf-8') as f:
                    self._genre_map = json.load(f)
            except Exception:
                pass

    def _folder_name_for_genre(self, genre: str) -> str:
        """Return the destination folder name for a raw genre string."""
        if genre in self._genre_map:
            return self._genre_map[genre]
        # Clean the genre string for use as folder name (keep unsafe-char strip only)
        safe = genre
        for ch in r':*?"<>|':
            safe = safe.replace(ch, '')
        for ch in r'/\\|':
            safe = safe.replace(ch, '-')
        return ' '.join(safe.split()).strip()

    def _known_genres(self) -> list[str]:
        """Sorted list of known raw genre names."""
        return sorted(self._genre_map.keys())

    # ── UI ─────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        title = QLabel('Review Organize Plan')
        title.setProperty('role', 'title')
        lay.addWidget(title)

        desc = QLabel(
            'Review the planned moves below. Edit the Genre column to change the destination '
            'folder; Target Path updates automatically. Uncheck items to skip them.'
        )
        desc.setWordWrap(True)
        desc.setProperty('role', 'muted')
        lay.addWidget(desc)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        lay.addWidget(sep)

        # Status
        self._status_lbl = QLabel('')
        self._status_lbl.setProperty('role', 'muted')
        lay.addWidget(self._status_lbl)

        # Table
        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ['', 'Action', 'Original Name', 'Display Name', 'Genre', 'Target Path']
        )
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        hdr = self._table.horizontalHeader()
        for i in range(self._table.columnCount()):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionsMovable(True)
        hdr.setStretchLastSection(False)
        hdr.sectionResized.connect(lambda *_: self._schedule_save())
        hdr.sectionMoved.connect(lambda *_: self._schedule_save())
        hdr.sortIndicatorChanged.connect(lambda *_: self._schedule_save())

        self._table.setColumnWidth(_COL_CHECK,  30)
        self._table.setColumnWidth(_COL_ACTION, 70)
        self._table.setColumnWidth(_COL_ORIG,  200)
        self._table.setColumnWidth(_COL_NAME,  200)
        self._table.setColumnWidth(_COL_GENRE, 160)
        self._table.setColumnWidth(_COL_TARGET, 380)

        self._table.verticalHeader().setVisible(False)
        self._table.itemChanged.connect(self._on_item_changed)
        self._table.itemClicked.connect(self._on_item_clicked)

        lay.addWidget(self._table, 1)

        # Bottom bar
        bot = QHBoxLayout()
        bot.setSpacing(8)

        self._btn_all = QPushButton('Select All')
        self._btn_all.clicked.connect(self._select_all)
        bot.addWidget(self._btn_all)

        self._btn_none = QPushButton('Select None')
        self._btn_none.setObjectName('btn_secondary')
        self._btn_none.clicked.connect(self._select_none)
        bot.addWidget(self._btn_none)

        bot.addStretch()

        self._btn_generate = QPushButton('Generate .bat')
        self._btn_generate.clicked.connect(self._do_generate)
        bot.addWidget(self._btn_generate)

        self._btn_close = QPushButton('Close')
        self._btn_close.setObjectName('btn_secondary')
        self._btn_close.clicked.connect(self.reject)
        bot.addWidget(self._btn_close)

        lay.addLayout(bot)

    # ── Population ─────────────────────────────────────────────────────────────

    def _populate(self):
        self._table.setSortingEnabled(False)
        self._table.blockSignals(True)
        self._table.setRowCount(0)

        for row_idx, item in enumerate(self._items):
            r = self._table.rowCount()
            self._table.insertRow(r)

            # Checkbox
            chk = CITableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Checked)
            chk.setData(Qt.ItemDataRole.UserRole, row_idx)
            self._table.setItem(r, _COL_CHECK, chk)

            # Action (read-only)
            action = 'RENAME' if item.get('is_rename') else 'MOVE'
            action_item = CITableWidgetItem(action)
            action_item.setFlags(action_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(r, _COL_ACTION, action_item)

            # Original Name (read-only)
            orig_item = CITableWidgetItem(item.get('original_name', ''))
            orig_item.setFlags(orig_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(r, _COL_ORIG, orig_item)

            # Display Name (read-only)
            name_item = CITableWidgetItem(item.get('display_name', ''))
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(r, _COL_NAME, name_item)

            # Genre (editable — drives target path)
            genre_item = CITableWidgetItem(item.get('genre', ''))
            self._table.setItem(r, _COL_GENRE, genre_item)

            # Target Path (read-only, auto-updated)
            target_item = CITableWidgetItem(str(item.get('target_path', '')))
            target_item.setFlags(target_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(r, _COL_TARGET, target_item)

        self._table.blockSignals(False)
        self._table.setSortingEnabled(True)
        self._update_status()

    # ── Item changed / clicked ─────────────────────────────────────────────────

    def _on_item_changed(self, item: CITableWidgetItem):
        col = item.column()
        if col == _COL_GENRE:
            self._recompute_target(item.row())
            self._update_status()
        elif col == _COL_CHECK:
            self._update_status()

    def _on_item_clicked(self, item):
        if item.column() == _COL_CHECK:
            row = item.row()
            state = item.checkState()
            if (self._last_checked_row is not None
                    and QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier):
                lo = min(self._last_checked_row, row)
                hi = max(self._last_checked_row, row)
                self._table.itemChanged.disconnect(self._on_item_changed)
                for r in range(lo, hi + 1):
                    chk = self._table.item(r, _COL_CHECK)
                    if chk:
                        chk.setCheckState(state)
                self._table.itemChanged.connect(self._on_item_changed)
                self._update_status()
            self._last_checked_row = row

    _last_checked_row = None

    def _recompute_target(self, row: int):
        """Recalculate the target path when genre changes."""
        chk_item = self._table.item(row, _COL_CHECK)
        if chk_item is None:
            return
        row_idx = chk_item.data(Qt.ItemDataRole.UserRole)
        if row_idx is None:
            return

        genre_item = self._table.item(row, _COL_GENRE)
        if not genre_item:
            return
        new_genre = genre_item.text().strip()

        item = self._items[row_idx]
        folder_name = self._folder_name_for_genre(new_genre) if new_genre else item.get('folder_name', '')

        # Recompute target path
        orig_name = item.get('original_name', '')
        if item.get('is_rename'):
            # Rename: keep same parent, just update folder_name
            current = item.get('current_path')
            new_target = Path(current).parent / folder_name if current else Path(folder_name)
        elif item.get('is_update'):
            safe_name = sanitize_folder_name(orig_name, self._noise_re) or orig_name
            update_name = self._plugin.clean_update_name(orig_name) if orig_name else ''
            update_safe = sanitize_folder_name(update_name, self._noise_re) or update_name
            new_target = self._base_path / folder_name / safe_name / 'Updates' / update_safe
        else:
            safe_name = sanitize_folder_name(orig_name, self._noise_re) or orig_name
            new_target = self._base_path / folder_name / safe_name

        # Update in-memory item
        item['genre'] = new_genre
        item['folder_name'] = folder_name
        item['target_path'] = new_target

        # Update table cell
        target_item = self._table.item(row, _COL_TARGET)
        if target_item:
            self._table.blockSignals(True)
            target_item.setText(str(new_target))
            self._table.blockSignals(False)

    # ── Select helpers ─────────────────────────────────────────────────────────

    def _select_all(self):
        self._table.blockSignals(True)
        for r in range(self._table.rowCount()):
            chk = self._table.item(r, _COL_CHECK)
            if chk:
                chk.setCheckState(Qt.CheckState.Checked)
        self._table.blockSignals(False)
        self._update_status()

    def _select_none(self):
        self._table.blockSignals(True)
        for r in range(self._table.rowCount()):
            chk = self._table.item(r, _COL_CHECK)
            if chk:
                chk.setCheckState(Qt.CheckState.Unchecked)
        self._table.blockSignals(False)
        self._update_status()

    # ── Status ─────────────────────────────────────────────────────────────────

    def _update_status(self):
        total    = self._table.rowCount()
        selected = sum(
            1 for r in range(total)
            if (chk := self._table.item(r, _COL_CHECK)) and
               chk.checkState() == Qt.CheckState.Checked
        )
        self._status_lbl.setText(f'{selected} of {total} selected')
        self._btn_generate.setText(f'Generate .bat ({selected})')
        self._btn_generate.setEnabled(selected > 0)

    # ── Generate ───────────────────────────────────────────────────────────────

    def _collect_selected(self) -> list:
        """Return in-memory item dicts for all checked rows."""
        selected = []
        for r in range(self._table.rowCount()):
            chk = self._table.item(r, _COL_CHECK)
            if chk and chk.checkState() == Qt.CheckState.Checked:
                row_idx = chk.data(Qt.ItemDataRole.UserRole)
                if row_idx is not None:
                    selected.append(self._items[row_idx])
        return selected

    def _do_generate(self):
        items = self._collect_selected()
        if not items:
            QMessageBox.information(self, 'Nothing selected', 'Select at least one item.')
            return
        try:
            from modules.core.base_organizer import BaseOrganizer
            org = BaseOrganizer(self._lib_config, self._plugin)
            ok = org.generate_bat(items)
            if ok:
                bat_path = self._lib_config.bat_output_path or str(
                    self._lib_config.destination_base / 'organize_items.bat'
                )
                QMessageBox.information(
                    self, 'Done',
                    f'.bat file generated with {len(items)} move(s).\n\n{bat_path}'
                )
        except Exception as e:
            QMessageBox.critical(self, 'Error', str(e))

    # ── State persistence ──────────────────────────────────────────────────────

    def _schedule_save(self):
        self._save_timer.start()

    def _save_table_state(self):
        self._ui_state.save_table(self._table, _STATE_KEY)

    def _restore_state(self):
        self._ui_state.restore_table(self._table, _STATE_KEY)

    def done(self, result):
        self._save_timer.stop()
        self._save_table_state()
        super().done(result)
