"""
Bulk Folder Name Sanitizer dialog.

Scans the library destination folder, proposes cleaned names,
lets the user review/edit, then renames folders on disk and
updates the metadata DB.
"""

import os
import re
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
    QAbstractItemView, QSizePolicy as QSP, QProgressBar,
    QMessageBox, QFrame,
)

from modules.gui.ui_state import UIState
from modules.core.config_manager import GlobalConfig

# ── Release-tag / noise words to strip ────────────────────────────────────────
_NOISE_WORDS = {
    # Scene groups
    'TENOKE', 'CODEX', 'DODI', 'FLT', 'SKIDROW', 'PLAZA', 'CPY', 'RELOADED',
    'HOODLUM', 'PROPHET', 'SIMPLEX', 'TiNYiSO', 'TINYI SO', 'RAZOR1911',
    'DEVIANCE', 'EMPRESS', 'RUNE', 'DARKSIDERS', 'POSTMORTEM', 'CHRONOS',
    'ORIGINS', 'FCKDRM', 'KAOS', 'REVOLT', 'ANOMALY', 'ALIAS', 'NOFEAR',
    'DARKSiDERS', 'DOGE', 'FIGA', 'GOLDBERG', 'STEAM', 'CRACK',
    # Common noise keywords
    'Update', 'Repack', 'Build', 'GOG', 'DLC', 'MULTI', 'MULTi',
    'Proper', 'PROPER', 'RETAIL', 'FINAL', 'FULL',
}

# Compiled pattern: whole-word match for each noise word (case-insensitive)
_NOISE_RE = re.compile(
    r'\b(?:' + '|'.join(re.escape(w) for w in _NOISE_WORDS) + r')\b',
    re.IGNORECASE,
)

# Version numbers: v1.401, v2, 1.33.0, 1.0.0.1, Build 12345
_VERSION_RE = re.compile(
    r'\bv?\d+(?:\.\d+){1,4}\b'        # v1.2.3 / 1.2.3
    r'|\bv\d+\b'                       # v2
    r'|\bBuild\s*\d+\b',               # Build 1234
    re.IGNORECASE,
)


def clean_folder_name(name: str) -> str:
    """Replace separators, strip version numbers and noise tags, collapse whitespace."""
    s = name.replace('.', ' ').replace('_', ' ').replace('-', ' ')
    s = _VERSION_RE.sub('', s)
    s = _NOISE_RE.sub('', s)
    s = ' '.join(s.split())   # collapse whitespace
    return s.strip()


# ── Column indices ─────────────────────────────────────────────────────────────
_COL_CHECK   = 0
_COL_GENRE   = 1
_COL_PATH    = 2
_COL_ORIG    = 3
_COL_CLEANED = 4


_STATE_KEY = 'folder_sanitizer_table'


class FolderSanitizerDialog(QDialog):
    def __init__(self, lib_config, parent=None):
        super().__init__(parent)
        self._lib_config = lib_config
        self._rows: list[dict] = []   # {genre, orig, folder_path, cleaned}
        self._ui_state = UIState(GlobalConfig().ui_state_path())

        self._save_timer = QTimer()
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(500)
        self._save_timer.timeout.connect(self._save_table_state)

        self.setWindowTitle('Sanitize Folder Names')
        self.resize(1100, 680)
        self._build_ui()
        self._scan()

    def closeEvent(self, event):
        self._save_timer.stop()
        self._save_table_state()
        super().closeEvent(event)

    def _save_table_state(self):
        self._ui_state.save_table(self._table, _STATE_KEY)

    def _schedule_save(self):
        self._save_timer.start()

    # ── UI ─────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        # Header
        title = QLabel('Sanitize Folder Names')
        title.setProperty('role', 'title')
        lay.addWidget(title)

        desc = QLabel(
            'Dots, underscores and dashes are converted to spaces; version numbers and '
            'scene-group tags are removed. Edit the Cleaned Name column before renaming.'
        )
        desc.setWordWrap(True)
        desc.setProperty('role', 'muted')
        lay.addWidget(desc)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        lay.addWidget(sep)

        # Filter bar
        filter_row = QHBoxLayout()
        self._chk_changed_only = QCheckBox('Show changed only')
        self._chk_changed_only.setChecked(True)
        self._chk_changed_only.toggled.connect(self._apply_filter)
        filter_row.addWidget(self._chk_changed_only)

        filter_row.addStretch()

        self._status_lbl = QLabel('')
        self._status_lbl.setProperty('role', 'muted')
        filter_row.addWidget(self._status_lbl)

        lay.addLayout(filter_row)

        # Table
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(['', 'Genre', 'Full Path', 'Original Name', 'Cleaned Name'])
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked |
                                    QAbstractItemView.EditTrigger.SelectedClicked)

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr.setSectionsMovable(True)
        self._table.setColumnWidth(_COL_CHECK,    30)
        self._table.setColumnWidth(_COL_GENRE,   110)
        self._table.setColumnWidth(_COL_PATH,    300)
        self._table.setColumnWidth(_COL_ORIG,    280)
        self._table.setColumnWidth(_COL_CLEANED, 280)
        hdr.setStretchLastSection(False)
        hdr.sectionResized.connect(lambda *_: self._schedule_save())
        hdr.sectionMoved.connect(lambda *_: self._schedule_save())
        hdr.sortIndicatorChanged.connect(lambda *_: self._schedule_save())

        self._table.verticalHeader().setVisible(False)
        self._table.itemChanged.connect(self._on_item_changed)
        self._table.itemClicked.connect(self._on_item_clicked)

        lay.addWidget(self._table, 1)

        # Bottom bar
        bot = QHBoxLayout()
        bot.setSpacing(8)

        self._btn_all  = QPushButton('Select All')
        self._btn_all.clicked.connect(self._select_all)
        bot.addWidget(self._btn_all)

        self._btn_none = QPushButton('Select None')
        self._btn_none.setObjectName('btn_secondary')
        self._btn_none.clicked.connect(self._select_none)
        bot.addWidget(self._btn_none)

        self._btn_reset = QPushButton('Reset Cleaned Names')
        self._btn_reset.setObjectName('btn_secondary')
        self._btn_reset.clicked.connect(self._reset_cleaned)
        bot.addWidget(self._btn_reset)

        bot.addStretch()

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setFixedWidth(200)
        bot.addWidget(self._progress)

        self._btn_rename = QPushButton('Rename Selected')
        self._btn_rename.clicked.connect(self._do_rename)
        bot.addWidget(self._btn_rename)

        self._btn_close = QPushButton('Close')
        self._btn_close.setObjectName('btn_secondary')
        self._btn_close.clicked.connect(self.reject)
        bot.addWidget(self._btn_close)

        lay.addLayout(bot)

    # ── Scanning ───────────────────────────────────────────────────────────────

    def _scan(self):
        dest = self._lib_config.destination_base
        skip = {s.lower() for s in self._lib_config.skip_folders + ['new']}
        self._rows.clear()

        if not dest.exists():
            QMessageBox.warning(self, 'Not Found', f'Destination folder not found:\n{dest}')
            return

        for genre_dir in sorted(dest.iterdir()):
            if not genre_dir.is_dir() or genre_dir.name.lower() in skip:
                continue
            try:
                for item_dir in sorted(genre_dir.iterdir()):
                    if not item_dir.is_dir():
                        continue
                    orig    = item_dir.name
                    cleaned = clean_folder_name(orig)
                    self._rows.append({
                        'genre':       genre_dir.name,
                        'orig':        orig,
                        'folder_path': str(item_dir),
                        'cleaned':     cleaned,
                    })
            except PermissionError:
                continue

        self._populate_table()

    # ── Table population ───────────────────────────────────────────────────────

    def _populate_table(self):
        self._table.setSortingEnabled(False)
        self._table.blockSignals(True)
        self._table.setRowCount(0)

        show_changed_only = self._chk_changed_only.isChecked()
        visible_rows = 0

        for row_data in self._rows:
            is_changed = row_data['orig'] != row_data['cleaned']
            if show_changed_only and not is_changed:
                continue

            r = self._table.rowCount()
            self._table.insertRow(r)

            # Checkbox col
            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk_item.setCheckState(
                Qt.CheckState.Checked if is_changed else Qt.CheckState.Unchecked
            )
            self._table.setItem(r, _COL_CHECK, chk_item)

            # Genre (read-only)
            genre_item = QTableWidgetItem(row_data['genre'])
            genre_item.setFlags(genre_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(r, _COL_GENRE, genre_item)

            # Full path of parent directory (read-only)
            parent_path = str(Path(row_data['folder_path']).parent)
            path_item = QTableWidgetItem(parent_path)
            path_item.setFlags(path_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(r, _COL_PATH, path_item)

            # Original (read-only)
            orig_item = QTableWidgetItem(row_data['orig'])
            orig_item.setFlags(orig_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            # Store index into self._rows for later lookup
            orig_item.setData(Qt.ItemDataRole.UserRole, self._rows.index(row_data))
            self._table.setItem(r, _COL_ORIG, orig_item)

            # Cleaned (editable)
            cleaned_item = QTableWidgetItem(row_data['cleaned'])
            self._table.setItem(r, _COL_CLEANED, cleaned_item)

            visible_rows += 1

        self._table.blockSignals(False)
        self._table.setSortingEnabled(True)
        self._ui_state.restore_table(self._table, _STATE_KEY)
        self._update_status()

    def _apply_filter(self):
        self._populate_table()

    # ── Item changed / clicked ─────────────────────────────────────────────────

    def _on_item_changed(self, item: QTableWidgetItem):
        if item.column() != _COL_CLEANED:
            self._update_status()
            return
        r = item.row()
        orig_item = self._table.item(r, _COL_ORIG)
        if orig_item is None:
            return
        row_idx = orig_item.data(Qt.ItemDataRole.UserRole)
        if row_idx is not None:
            self._rows[row_idx]['cleaned'] = item.text()
        self._update_status()

    def _on_item_clicked(self, item: QTableWidgetItem):
        """Propagate checkbox state to all selected rows when col 0 is clicked."""
        if item.column() != _COL_CHECK:
            return
        state = item.checkState()
        selected_rows = {idx.row() for idx in self._table.selectionModel().selectedRows()}
        selected_rows.add(item.row())
        self._table.blockSignals(True)
        for r in selected_rows:
            chk = self._table.item(r, _COL_CHECK)
            if chk:
                chk.setCheckState(state)
        self._table.blockSignals(False)
        self._update_status()

    # ── Select helpers ─────────────────────────────────────────────────────────

    def _select_all(self):
        self._table.blockSignals(True)
        for r in range(self._table.rowCount()):
            item = self._table.item(r, _COL_CHECK)
            if item:
                item.setCheckState(Qt.CheckState.Checked)
        self._table.blockSignals(False)
        self._update_status()

    def _select_none(self):
        self._table.blockSignals(True)
        for r in range(self._table.rowCount()):
            item = self._table.item(r, _COL_CHECK)
            if item:
                item.setCheckState(Qt.CheckState.Unchecked)
        self._table.blockSignals(False)
        self._update_status()

    def _reset_cleaned(self):
        """Re-run auto-clean on all visible rows."""
        self._table.blockSignals(True)
        for r in range(self._table.rowCount()):
            orig_item = self._table.item(r, _COL_ORIG)
            if not orig_item:
                continue
            row_idx = orig_item.data(Qt.ItemDataRole.UserRole)
            if row_idx is None:
                continue
            orig = self._rows[row_idx]['orig']
            cleaned = clean_folder_name(orig)
            self._rows[row_idx]['cleaned'] = cleaned
            cleaned_item = self._table.item(r, _COL_CLEANED)
            if cleaned_item:
                cleaned_item.setText(cleaned)
        self._table.blockSignals(False)
        self._update_status()

    # ── Status label ───────────────────────────────────────────────────────────

    def _update_status(self):
        total    = self._table.rowCount()
        selected = sum(
            1 for r in range(total)
            if (item := self._table.item(r, _COL_CHECK)) and
               item.checkState() == Qt.CheckState.Checked
        )
        changed = sum(
            1 for rd in self._rows if rd['orig'] != rd['cleaned']
        )
        self._status_lbl.setText(
            f'{selected} selected  ·  {total} shown  ·  {changed} total changed'
        )
        self._btn_rename.setText(f'Rename Selected ({selected})')
        self._btn_rename.setEnabled(selected > 0)

    # ── Rename ─────────────────────────────────────────────────────────────────

    def _do_rename(self):
        # Collect checked rows
        to_rename = []
        for r in range(self._table.rowCount()):
            chk = self._table.item(r, _COL_CHECK)
            if not chk or chk.checkState() != Qt.CheckState.Checked:
                continue
            orig_item    = self._table.item(r, _COL_ORIG)
            cleaned_item = self._table.item(r, _COL_CLEANED)
            if not orig_item or not cleaned_item:
                continue
            row_idx  = orig_item.data(Qt.ItemDataRole.UserRole)
            row_data = self._rows[row_idx]
            new_name = cleaned_item.text().strip()
            if not new_name or new_name == row_data['orig']:
                continue
            to_rename.append((row_data, new_name, r))

        if not to_rename:
            QMessageBox.information(self, 'Nothing to do',
                                    'No folders selected or cleaned names are unchanged.')
            return

        ans = QMessageBox.question(
            self, 'Confirm Rename',
            f'Rename {len(to_rename)} folder(s) on disk?\nThis cannot be undone.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return

        # Load DB
        from modules.core.db import LibraryDB
        db = LibraryDB(self._lib_config.db_file)

        self._progress.setVisible(True)
        self._progress.setMaximum(len(to_rename))
        self._progress.setValue(0)
        self._btn_rename.setEnabled(False)

        ok_count = 0
        fail_msgs = []

        for row_data, new_name, table_row in to_rename:
            old_path = Path(row_data['folder_path'])
            new_path = old_path.parent / new_name

            # Guard against collision
            if new_path.exists():
                fail_msgs.append(f'{row_data["orig"]!r} → already exists: {new_name!r}')
                self._progress.setValue(self._progress.value() + 1)
                continue

            try:
                os.rename(old_path, new_path)
            except OSError as e:
                fail_msgs.append(f'{row_data["orig"]!r}: {e}')
                self._progress.setValue(self._progress.value() + 1)
                continue

            # Update DB if the item exists there
            if db.item_exists(row_data['orig']):
                try:
                    db.rename_item(row_data['orig'], new_name)
                except Exception as e:
                    # Disk rename done — DB failed; try to undo
                    try:
                        os.rename(new_path, old_path)
                        fail_msgs.append(f'{row_data["orig"]!r}: DB update failed, rename rolled back. ({e})')
                    except OSError:
                        fail_msgs.append(
                            f'{row_data["orig"]!r}: DB update failed AND rollback failed! '
                            f'Folder is now {new_name!r} but DB still has old name.'
                        )
                    self._progress.setValue(self._progress.value() + 1)
                    continue

            # Update in-memory row
            row_data['folder_path'] = str(new_path)
            row_data['cleaned']     = new_name
            old_orig                = row_data['orig']
            row_data['orig']        = new_name

            # Update table cells
            orig_item = self._table.item(table_row, _COL_ORIG)
            if orig_item:
                orig_item.setText(new_name)

            # Uncheck — done
            chk = self._table.item(table_row, _COL_CHECK)
            if chk:
                self._table.blockSignals(True)
                chk.setCheckState(Qt.CheckState.Unchecked)
                self._table.blockSignals(False)

            ok_count += 1
            self._progress.setValue(self._progress.value() + 1)

        self._progress.setVisible(False)
        self._update_status()

        if fail_msgs:
            msg = f'Renamed {ok_count} folder(s).\n\nErrors ({len(fail_msgs)}):\n' + '\n'.join(fail_msgs)
            QMessageBox.warning(self, 'Rename Complete (with errors)', msg)
        else:
            QMessageBox.information(self, 'Done', f'Successfully renamed {ok_count} folder(s).')
