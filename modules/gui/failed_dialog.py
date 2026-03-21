"""
Failed items dialog — manage metadata lookup failures.

Shows a table of items that didn't match and allows:
- Mark as Manual Genre (pick from genre list)
- Skip Selected
- Retry lookup for selected (with editable clean name and inline log)
"""

import json
from pathlib import Path

from PyQt6.QtCore import Qt, QEvent, QTimer
from PyQt6.QtGui import QTextCursor, QFont, QAction
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QInputDialog, QMessageBox, QDialogButtonBox, QProgressBar,
    QPlainTextEdit, QSplitter, QWidget, QApplication, QMenu,
    QListWidget, QListWidgetItem,
)


class _PickResultDialog(QDialog):
    """Show all provider search results and let the user pick one."""

    def __init__(self, query: str, results: list, provider, parent=None):
        super().__init__(parent)
        self.selected_result = None
        self._provider = provider
        self.setWindowTitle(f'Pick match — {query}')
        self.resize(520, 320)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        lay = QVBoxLayout(self)

        lay.addWidget(QLabel(f'Search query: <b>{query}</b>'))
        lay.addWidget(QLabel('Double-click or select and click Pick:'))

        self._list = QListWidget()
        for r in results:
            name = r.get('name', '?')
            year = ''
            ts = r.get('first_release_date')
            if ts:
                try:
                    from datetime import datetime, timezone
                    year = str(datetime.fromtimestamp(ts, tz=timezone.utc).year)
                except Exception:
                    pass
            text = f'{name}  ({year})' if year else name
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, r)
            self._list.addItem(item)
        self._list.doubleClicked.connect(self._pick)
        lay.addWidget(self._list, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_pick = QPushButton('Pick')
        btn_pick.clicked.connect(self._pick)
        btn_row.addWidget(btn_pick)
        btn_skip = QPushButton('Skip')
        btn_skip.setObjectName('btn_secondary')
        btn_skip.clicked.connect(self.reject)
        btn_row.addWidget(btn_skip)
        lay.addLayout(btn_row)

    def _pick(self):
        item = self._list.currentItem()
        if not item:
            return
        raw = item.data(Qt.ItemDataRole.UserRole)
        self.selected_result = self._provider.extract(raw)
        self.accept()


class FailedItemsDialog(QDialog):

    _COL_SEL      = 0
    _COL_FOLDER   = 1
    _COL_CLEAN    = 2
    _COL_LOCATION = 3
    _COL_STATUS   = 4

    def __init__(self, lib_config, plugin, parent=None, ui_state=None):
        super().__init__(parent)
        self._lib_config      = lib_config
        self._plugin          = plugin
        self._worker          = None
        self._pending_results = {}
        self._genres          = self._load_genres()
        self._ui_state        = ui_state
        self._state_key       = f'failed_dialog_{plugin.media_type}'
        self._debounce        = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(400)
        self._debounce.timeout.connect(self._save_state)

        self.setWindowTitle(f'Failed Items — {plugin.name}')
        self.resize(960, 640)
        self._setup_ui()
        self._load_data()

    # ── Genres ────────────────────────────────────────────────────────
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

    # ── UI ────────────────────────────────────────────────────────────
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 10)
        layout.setSpacing(8)

        lbl = QLabel(f'Items that could not be matched — {self._plugin.name}')
        lbl.setProperty('role', 'title')
        layout.addWidget(lbl)

        self._info_label = QLabel('Loading...')
        self._info_label.setProperty('role', 'muted')
        layout.addWidget(self._info_label)

        # Splitter: table top, retry log bottom
        splitter = QSplitter(Qt.Orientation.Vertical)
        self._splitter = splitter

        # ── Table ─────────────────────────────────────────────────────
        table_w = QWidget()
        table_lay = QVBoxLayout(table_w)
        table_lay.setContentsMargins(0, 0, 0, 0)

        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(['', 'Folder Name', 'Clean Name', 'Location', 'Status'])
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr.setSectionsMovable(True)
        hdr.sectionResized.connect(lambda *_: self._debounce.start())
        hdr.sectionMoved.connect(lambda *_: self._debounce.start())
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(False)
        self._table.verticalHeader().setVisible(False)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        self._table.installEventFilter(self)
        self._table.itemChanged.connect(self._on_item_changed)

        table_lay.addWidget(self._table)
        splitter.addWidget(table_w)

        # ── Retry log ─────────────────────────────────────────────────
        log_w = QWidget()
        log_lay = QVBoxLayout(log_w)
        log_lay.setContentsMargins(0, 0, 0, 0)
        log_lay.setSpacing(4)

        log_hdr = QHBoxLayout()
        log_lbl = QLabel('Retry Log')
        log_lbl.setStyleSheet('font-size:8.5pt; font-weight:600;')
        log_hdr.addWidget(log_lbl)
        btn_clear_log = QPushButton('Clear')
        btn_clear_log.setObjectName('btn_secondary')
        btn_clear_log.clicked.connect(lambda: self._retry_log.clear())
        log_hdr.addWidget(btn_clear_log)
        log_hdr.addStretch()
        log_lay.addLayout(log_hdr)

        self._retry_log = QPlainTextEdit()
        self._retry_log.setReadOnly(True)
        self._retry_log.setFont(QFont('Consolas', 8))
        self._retry_log.setMaximumHeight(150)
        self._retry_log.setStyleSheet(
            'background:#1c1e26; color:#a8b2d8; border:none; padding:4px;'
        )
        log_lay.addWidget(self._retry_log)
        splitter.addWidget(log_w)

        splitter.setSizes([420, 130])
        layout.addWidget(splitter, 1)

        # ── Action bar ────────────────────────────────────────────────
        bar = QHBoxLayout()

        self._btn_manual = QPushButton('Mark as Manual Genre')
        self._btn_manual.clicked.connect(self._mark_manual)
        bar.addWidget(self._btn_manual)

        self._btn_skip = QPushButton('Skip Selected')
        self._btn_skip.setObjectName('btn_secondary')
        self._btn_skip.clicked.connect(self._skip_selected)
        bar.addWidget(self._btn_skip)

        self._btn_retry = QPushButton('Retry for Selected')
        self._btn_retry.clicked.connect(self._retry_selected)
        bar.addWidget(self._btn_retry)

        self._btn_pick = QPushButton('Pick Match')
        self._btn_pick.setObjectName('btn_secondary')
        self._btn_pick.setToolTip('Search and manually pick from all results for each selected item')
        self._btn_pick.clicked.connect(self._pick_match)
        bar.addWidget(self._btn_pick)

        bar.addStretch()

        self._btn_select_all = QPushButton('Select All')
        self._btn_select_all.setObjectName('btn_secondary')
        self._btn_select_all.clicked.connect(self._select_all)
        bar.addWidget(self._btn_select_all)

        self._btn_clear_sel = QPushButton('Clear Selection')
        self._btn_clear_sel.setObjectName('btn_secondary')
        self._btn_clear_sel.clicked.connect(self._clear_selection)
        bar.addWidget(self._btn_clear_sel)

        layout.addLayout(bar)

        # ── Progress ──────────────────────────────────────────────────
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # Save Found — only visible after a successful retry
        self._btn_save_found = QPushButton('Save Found')
        self._btn_save_found.setVisible(False)
        self._btn_save_found.clicked.connect(self._save_found)
        layout.addWidget(self._btn_save_found)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(self.accept)
        layout.addWidget(btn_box)

    # ── Load data ─────────────────────────────────────────────────────
    def _load_data(self):
        meta_file = self._lib_config.metadata_file
        if not meta_file or not Path(meta_file).exists():
            self._info_label.setText('No metadata file found — run Metadata step first.')
            return

        with open(meta_file, 'r', encoding='utf-8') as f:
            raw = json.load(f)

        items = raw.get('processed_items', raw.get('processed_games', {}))
        failed = {
            k: v for k, v in items.items()
            if not (v.get('igdb_found') or v.get('found'))
        }

        self._populate_table(failed)
        self._restore_state()
        self._info_label.setText(
            f'{len(failed)} failed item(s). '
            'Edit Clean Name before retrying. Double-click to edit.'
        )

    def _populate_table(self, failed: dict):
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        self._table.setRowCount(len(failed))

        for row, (clean_name, info) in enumerate(failed.items()):
            # Checkbox col
            chk = QTableWidgetItem()
            chk.setCheckState(Qt.CheckState.Unchecked)
            chk.setData(Qt.ItemDataRole.UserRole, {'key': clean_name, **info})
            chk.setFlags(chk.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, self._COL_SEL, chk)

            # Folder name (read-only)
            folder = info.get('original_name', clean_name)
            fi = QTableWidgetItem(folder)
            fi.setFlags(fi.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, self._COL_FOLDER, fi)

            # Clean name (editable — user can change before retrying)
            fresh_clean = self._plugin.clean_name(folder) if folder else clean_name
            ci = QTableWidgetItem(fresh_clean)
            ci.setToolTip('Double-click to edit the search name before retrying')
            self._table.setItem(row, self._COL_CLEAN, ci)

            # Location — full_path if stored, else blank
            full_path = info.get('full_path', '')
            li = QTableWidgetItem(full_path)
            li.setFlags(li.flags() & ~Qt.ItemFlag.ItemIsEditable)
            li.setToolTip(full_path)
            self._table.setItem(row, self._COL_LOCATION, li)

            # Status
            si = QTableWidgetItem('Pending')
            si.setFlags(si.flags() & ~Qt.ItemFlag.ItemIsEditable)
            si.setForeground(Qt.GlobalColor.gray)
            self._table.setItem(row, self._COL_STATUS, si)

        self._table.setColumnWidth(self._COL_SEL,      28)
        self._table.setColumnWidth(self._COL_FOLDER,  240)
        self._table.setColumnWidth(self._COL_CLEAN,   200)
        self._table.setColumnWidth(self._COL_LOCATION, 220)
        self._table.setColumnWidth(self._COL_STATUS,   140)
        self._table.setSortingEnabled(True)

    def _on_item_changed(self, item):
        if item.column() == self._COL_CLEAN:
            chk = self._table.item(item.row(), self._COL_SEL)
            if chk:
                chk.setCheckState(Qt.CheckState.Checked)

    # ── State persistence ─────────────────────────────────────────────
    def _save_state(self):
        if self._ui_state:
            self._ui_state.save_table(self._table, self._state_key)
            self._ui_state.save_splitter(self._splitter, self._state_key + '_splitter')

    def _restore_state(self):
        if self._ui_state:
            self._ui_state.restore_table(self._table, self._state_key)
            self._ui_state.restore_splitter(self._splitter, self._state_key + '_splitter')

    def closeEvent(self, event):
        self._debounce.stop()
        self._save_state()
        super().closeEvent(event)

    # ── Context menu / copy ───────────────────────────────────────────
    def eventFilter(self, obj, event):
        if obj is self._table and event.type() == QEvent.Type.KeyPress:
            if (event.key() == Qt.Key.Key_C
                    and event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                self._copy_selection()
                return True
        return super().eventFilter(obj, event)

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        act_row  = QAction('Copy Row', self)
        act_cell = QAction('Copy Cell', self)
        act_row.triggered.connect(self._copy_selection)
        act_cell.triggered.connect(self._copy_cell_at(pos))
        menu.addAction(act_row)
        menu.addAction(act_cell)
        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _copy_cell_at(self, pos):
        def do_copy():
            idx = self._table.indexAt(pos)
            if idx.isValid():
                item = self._table.item(idx.row(), idx.column())
                if item:
                    QApplication.clipboard().setText(item.text())
        return do_copy

    def _copy_selection(self):
        rows = sorted(set(idx.row() for idx in self._table.selectedIndexes()))
        lines = []
        for row in rows:
            parts = []
            for col in range(1, self._table.columnCount()):
                item = self._table.item(row, col)
                parts.append(item.text() if item else '')
            lines.append('\t'.join(parts))
        QApplication.clipboard().setText('\n'.join(lines))

    # ── Selection helpers ─────────────────────────────────────────────
    def _get_checked_rows(self):
        result = []
        for row in range(self._table.rowCount()):
            chk = self._table.item(row, self._COL_SEL)
            if chk and chk.checkState() == Qt.CheckState.Checked:
                result.append((row, chk.data(Qt.ItemDataRole.UserRole)))
        return result

    def _select_all(self):
        for row in range(self._table.rowCount()):
            item = self._table.item(row, self._COL_SEL)
            if item:
                item.setCheckState(Qt.CheckState.Checked)

    def _clear_selection(self):
        for row in range(self._table.rowCount()):
            item = self._table.item(row, self._COL_SEL)
            if item:
                item.setCheckState(Qt.CheckState.Unchecked)

    # ── Actions ───────────────────────────────────────────────────────
    def _mark_manual(self):
        selected = self._get_checked_rows()
        if not selected:
            QMessageBox.information(self, 'No selection', 'Check at least one item.')
            return
        if not self._genres:
            QMessageBox.warning(self, 'No genres',
                                'No genre file configured. Set genre_file in Settings.')
            return

        genre, ok = QInputDialog.getItem(
            self, 'Select Genre',
            f'Assign genre for {len(selected)} selected item(s):',
            self._genres, 0, False,
        )
        if not ok or not genre:
            return

        meta_file = Path(self._lib_config.metadata_file)
        try:
            with open(meta_file, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            key_name = 'processed_items' if 'processed_items' in raw else 'processed_games'
            items = raw.get(key_name, {})

            for row, info in selected:
                k = info['key']
                entry = items.get(k, {})
                entry.update({
                    'found':        True,
                    'igdb_found':   True,
                    'manual':       True,
                    'genre':        genre,
                    'original_name': info.get('original_name', k),
                    'display_name': info.get('original_name', k),
                })
                items[k] = entry

                si = self._table.item(row, self._COL_STATUS)
                if si:
                    si.setText(f'Manual: {genre}')
                    si.setForeground(Qt.GlobalColor.darkGreen)

            raw[key_name] = items
            with open(meta_file, 'w', encoding='utf-8') as f:
                json.dump(raw, f, indent=2, ensure_ascii=False)

            QMessageBox.information(
                self, 'Done',
                f"Marked {len(selected)} item(s) as '{genre}'.\nRun Organize to move them.",
            )
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Failed to save:\n{e}')

    def _skip_selected(self):
        for row, _ in self._get_checked_rows():
            si = self._table.item(row, self._COL_STATUS)
            if si:
                si.setText('Skipped')
                si.setForeground(Qt.GlobalColor.gray)
            chk = self._table.item(row, self._COL_SEL)
            if chk:
                chk.setCheckState(Qt.CheckState.Unchecked)

    def _retry_selected(self):
        selected = self._get_checked_rows()
        if not selected:
            QMessageBox.information(self, 'No selection', 'Check at least one item.')
            return

        retry_items = []
        for row, info in selected:
            clean_item = self._table.item(row, self._COL_CLEAN)
            search_name = clean_item.text().strip() if clean_item else info['key']
            retry_items.append({
                'key':           info['key'],
                'search_name':   search_name,
                'original_name': info.get('original_name', info['key']),
            })

        if QMessageBox.question(
            self, 'Retry Lookup',
            f'Query metadata providers for {len(retry_items)} item(s)?\n\n'
            'Progress will appear in the log below.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        self._retry_log.clear()
        self._pending_results = {}   # key -> result dict, populated by worker
        self._btn_save_found.setVisible(False)
        self._progress.setVisible(True)
        self._set_buttons_enabled(False)

        from modules.gui.workers import MetadataRetryWorker
        self._worker = MetadataRetryWorker(
            self._lib_config, self._plugin, self._retry_stream, retry_items
        )
        self._worker.item_result.connect(self._on_item_result)
        self._worker.finished.connect(self._on_retry_done)
        self._worker.start()

    def _on_item_result(self, key: str, found: bool, display_name: str):
        for row in range(self._table.rowCount()):
            chk = self._table.item(row, self._COL_SEL)
            if not chk:
                continue
            info = chk.data(Qt.ItemDataRole.UserRole)
            if info and info.get('key') == key:
                si = self._table.item(row, self._COL_STATUS)
                if si:
                    if found:
                        si.setText(f'Found: {display_name}')
                        si.setForeground(Qt.GlobalColor.darkGreen)
                    else:
                        si.setText('Still not found')
                        si.setForeground(Qt.GlobalColor.red)
                break

    def _on_retry_done(self, success: bool, message: str, found_results: dict):
        self._progress.setVisible(False)
        self._set_buttons_enabled(True)
        self._worker = None
        self._pending_results = found_results
        self._append_retry_log(f'\n[DONE] {message}\n')
        if found_results:
            self._btn_save_found.setText(f'Save Found ({len(found_results)})')
            self._btn_save_found.setVisible(True)

    def _save_found(self):
        if not self._pending_results:
            return
        meta_file = Path(self._lib_config.metadata_file)
        try:
            with open(meta_file, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            key_name = 'processed_items' if 'processed_items' in raw else 'processed_games'
            items = raw.get(key_name, {})
            items.update(self._pending_results)
            raw[key_name] = items
            with open(meta_file, 'w', encoding='utf-8') as f:
                json.dump(raw, f, indent=2, ensure_ascii=False)
            count = len(self._pending_results)
            self._pending_results = {}
            self._btn_save_found.setVisible(False)
            QMessageBox.information(
                self, 'Saved', f'{count} item(s) saved to DB.\nRun Organize to move them.'
            )
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Failed to save:\n{e}')

    def _pick_match(self):
        selected = self._get_checked_rows()
        if not selected:
            QMessageBox.information(self, 'No selection', 'Check at least one item.')
            return

        try:
            from modules.providers import get_provider_class
            cls      = get_provider_class(self._lib_config.primary_provider)
            provider = cls(self._lib_config.api)
            provider.authenticate()
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Could not connect to provider:\n{e}')
            return

        for row, info in selected:
            clean_item  = self._table.item(row, self._COL_CLEAN)
            search_name = clean_item.text().strip() if clean_item else info['key']

            try:
                results = provider.search(search_name)
            except Exception as e:
                QMessageBox.warning(self, 'Search failed', f'{search_name}:\n{e}')
                continue

            if not results:
                QMessageBox.information(
                    self, 'No results', f'No results found for: {search_name}'
                )
                continue

            dlg = _PickResultDialog(search_name, results, provider, self)
            if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.selected_result:
                continue  # user skipped this item

            key    = info['key']
            result = dlg.selected_result
            result['original_name'] = info.get('original_name', key)
            result['found']         = True
            result['igdb_found']    = True
            result['manual']        = False
            self._pending_results[key] = result

            si = self._table.item(row, self._COL_STATUS)
            if si:
                si.setText(f'Picked: {result.get("name", "")}')
                si.setForeground(Qt.GlobalColor.darkGreen)

        if self._pending_results:
            self._btn_save_found.setText(f'Save Found ({len(self._pending_results)})')
            self._btn_save_found.setVisible(True)

    def _set_buttons_enabled(self, enabled: bool):
        for btn in (self._btn_manual, self._btn_skip, self._btn_retry,
                    self._btn_pick, self._btn_select_all, self._btn_clear_sel):
            btn.setEnabled(enabled)

    # ── Retry log ─────────────────────────────────────────────────────
    @property
    def _retry_stream(self):
        if not hasattr(self, '_retry_stream_obj'):
            from modules.gui.log_widget import _SignalStream
            self._retry_stream_obj = _SignalStream()
            self._retry_stream_obj.text_written.connect(self._append_retry_log)
        return self._retry_stream_obj

    def _append_retry_log(self, text: str):
        self._retry_log.moveCursor(QTextCursor.MoveOperation.End)
        self._retry_log.insertPlainText(text)
        self._retry_log.ensureCursorVisible()
