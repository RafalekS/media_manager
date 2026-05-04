"""
Scrape dialog — re-query providers for selected library items.
Shows results for review before saving. NO auto-save.
"""

from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QTextCursor, QFont
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox, QSplitter, QWidget, QPlainTextEdit, QProgressBar,
    QDialogButtonBox,
)


class ScrapeDialog(QDialog):
    """
    Review dialog for re-scraping library items.
    Populates from selection, lets you edit the search query per row,
    runs MetadataRetryWorker, shows _PickResultDialog for multi-candidates,
    and only saves on explicit "Save Found" click.
    """

    _COL_FOLDER  = 0
    _COL_SEARCH  = 1
    _COL_CURRENT = 2
    _COL_STATUS  = 3

    def __init__(self, items: list, lib_config, plugin, parent=None):
        """
        items: list of dicts from LibraryBrowser._data.
               Each dict has: _key, name, display_name, full_path, ...
        """
        super().__init__(parent)
        self._lib_config       = lib_config
        self._plugin           = plugin
        self._items            = items
        self._worker           = None
        self._finished_workers = []
        self._pending_results  = {}   # key -> result dict

        self.setWindowTitle(f'Scrape — {plugin.name}')
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.resize(880, 560)
        self._setup_ui()
        self._populate_table()

    # ── UI ────────────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 10)
        layout.setSpacing(8)

        lbl = QLabel(f'Re-scrape {len(self._items)} item(s) — {self._plugin.name}')
        lbl.setProperty('role', 'title')
        layout.addWidget(lbl)

        info = QLabel(
            'Edit the Search Query column if needed, then click Start Scrape. '
            'Nothing is saved until you click Save Found.'
        )
        info.setWordWrap(True)
        info.setProperty('role', 'muted')
        layout.addWidget(info)

        splitter = QSplitter(Qt.Orientation.Vertical)

        # ── Table ─────────────────────────────────────────────────────
        table_w = QWidget()
        table_lay = QVBoxLayout(table_w)
        table_lay.setContentsMargins(0, 0, 0, 0)

        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(
            ['Folder Name', 'Search Query', 'Current Match', 'Status']
        )
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr.setSectionsMovable(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(False)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked |
            QAbstractItemView.EditTrigger.EditKeyPressed
        )

        table_lay.addWidget(self._table)
        splitter.addWidget(table_w)

        # ── Log ───────────────────────────────────────────────────────
        log_w = QWidget()
        log_lay = QVBoxLayout(log_w)
        log_lay.setContentsMargins(0, 0, 0, 0)
        log_lay.setSpacing(4)

        log_hdr = QHBoxLayout()
        log_lbl = QLabel('Scrape Log')
        log_lbl.setProperty('role', 'muted')
        log_hdr.addWidget(log_lbl)
        btn_clear = QPushButton('Clear')
        btn_clear.setObjectName('btn_secondary')
        btn_clear.clicked.connect(lambda: self._log.clear())
        log_hdr.addWidget(btn_clear)
        log_hdr.addStretch()
        log_lay.addLayout(log_hdr)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(QFont('Consolas', 9))
        log_lay.addWidget(self._log)
        splitter.addWidget(log_w)

        splitter.setSizes([370, 150])
        layout.addWidget(splitter, 1)

        # ── Progress ──────────────────────────────────────────────────
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # ── Save Found — hidden until results arrive ───────────────────
        self._btn_save = QPushButton('Save Found')
        self._btn_save.setVisible(False)
        self._btn_save.clicked.connect(self._save_found)
        layout.addWidget(self._btn_save)

        # ── Action row ────────────────────────────────────────────────
        bar = QHBoxLayout()

        self._btn_start = QPushButton('Start Scrape')
        self._btn_start.clicked.connect(self._start_scrape)
        bar.addWidget(self._btn_start)

        self._btn_stop = QPushButton('Stop')
        self._btn_stop.setObjectName('btn_secondary')
        self._btn_stop.setEnabled(False)
        self._btn_stop.clicked.connect(self._stop_scrape)
        bar.addWidget(self._btn_stop)

        bar.addStretch()

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(self.reject)
        bar.addWidget(btn_box)
        layout.addLayout(bar)

    def _populate_table(self):
        self._table.setRowCount(len(self._items))
        for row, item in enumerate(self._items):
            folder_name = item.get('name', item.get('_key', ''))
            search_q    = self._plugin.clean_name(folder_name) if folder_name else item.get('_key', '')
            current     = item.get('display_name', '')
            db_key      = item.get('_key', '')

            # Folder (read-only)
            fi = QTableWidgetItem(folder_name)
            fi.setFlags(fi.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, self._COL_FOLDER, fi)

            # Search query (editable) — stores DB key in UserRole
            si = QTableWidgetItem(search_q)
            si.setData(Qt.ItemDataRole.UserRole, db_key)
            si.setToolTip('Double-click to edit before scraping')
            self._table.setItem(row, self._COL_SEARCH, si)

            # Current match (read-only)
            ci = QTableWidgetItem(current)
            ci.setFlags(ci.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, self._COL_CURRENT, ci)

            # Status (read-only)
            sti = QTableWidgetItem('Pending')
            sti.setFlags(sti.flags() & ~Qt.ItemFlag.ItemIsEditable)
            sti.setForeground(Qt.GlobalColor.gray)
            self._table.setItem(row, self._COL_STATUS, sti)

        self._table.setColumnWidth(self._COL_FOLDER,  210)
        self._table.setColumnWidth(self._COL_SEARCH,  200)
        self._table.setColumnWidth(self._COL_CURRENT, 200)
        self._table.setColumnWidth(self._COL_STATUS,  220)

    # ── Scrape ────────────────────────────────────────────────────────

    def _start_scrape(self):
        retry_items = []
        for row in range(self._table.rowCount()):
            search_item = self._table.item(row, self._COL_SEARCH)
            folder_item = self._table.item(row, self._COL_FOLDER)
            if not search_item:
                continue
            db_key      = search_item.data(Qt.ItemDataRole.UserRole) or ''
            search_name = search_item.text().strip() or db_key
            orig        = folder_item.text() if folder_item else db_key
            retry_items.append({
                'key':           db_key,
                'search_name':   search_name,
                'original_name': orig,
            })
            sti = self._table.item(row, self._COL_STATUS)
            if sti:
                sti.setText('...')
                sti.setForeground(Qt.GlobalColor.gray)

        if not retry_items:
            return

        self._log.clear()
        self._pending_results = {}
        self._btn_save.setVisible(False)
        self._progress.setVisible(True)
        self._btn_start.setEnabled(False)
        self._btn_stop.setEnabled(True)

        from modules.gui.workers import MetadataRetryWorker
        self._worker = MetadataRetryWorker(
            self._lib_config, self._plugin, self._log_stream, retry_items
        )
        self._worker.item_result.connect(self._on_item_result)
        self._worker.finished.connect(self._on_scrape_done)
        self._worker.start()

    def _stop_scrape(self):
        if self._worker and self._worker.isRunning():
            self._worker.request_stop()

    def _on_item_result(self, key: str, found: bool, display_name: str):
        for row in range(self._table.rowCount()):
            search_item = self._table.item(row, self._COL_SEARCH)
            if not search_item:
                continue
            if search_item.data(Qt.ItemDataRole.UserRole) == key:
                sti = self._table.item(row, self._COL_STATUS)
                if sti:
                    if found:
                        sti.setText(f'Found: {display_name}')
                        sti.setForeground(Qt.GlobalColor.darkGreen)
                    else:
                        sti.setText('Not found')
                        sti.setForeground(Qt.GlobalColor.red)
                break

    def _on_scrape_done(self, success: bool, message: str,
                        auto_results: dict, multi_candidates: dict):
        self._progress.setVisible(False)
        self._btn_start.setEnabled(True)
        self._btn_stop.setEnabled(False)

        if self._worker is not None:
            self._finished_workers.append(self._worker)
            QTimer.singleShot(0, self._drop_finished_workers)
        self._worker = None

        self._pending_results.update(auto_results)
        self._append_log(f'\n[DONE] {message}\n')

        # Show pick dialog for each item with multiple candidates
        for key, candidates in multi_candidates.items():
            search_name = key
            for row in range(self._table.rowCount()):
                search_item = self._table.item(row, self._COL_SEARCH)
                if search_item and search_item.data(Qt.ItemDataRole.UserRole) == key:
                    search_name = search_item.text() or key
                    break

            from modules.gui.failed_dialog import _PickResultDialog
            dlg = _PickResultDialog(search_name, candidates, self)
            if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_result:
                result = dlg.selected_result
                result['original_name'] = candidates[0].get('original_name', key)
                result['found']         = True
                result['igdb_found']    = True
                result['manual']        = False
                self._pending_results[key] = result
                self._append_log(f'  Picked: {result.get("name", "")}\n')
                for row in range(self._table.rowCount()):
                    search_item = self._table.item(row, self._COL_SEARCH)
                    if search_item and search_item.data(Qt.ItemDataRole.UserRole) == key:
                        sti = self._table.item(row, self._COL_STATUS)
                        if sti:
                            sti.setText(f'Picked: {result.get("name", "")}')
                            sti.setForeground(Qt.GlobalColor.darkGreen)
                        break
            else:
                self._append_log(f'  Skipped pick for: {search_name}\n')

        if self._pending_results:
            self._btn_save.setText(f'Save Found ({len(self._pending_results)})')
            self._btn_save.setVisible(True)

    # ── Save ──────────────────────────────────────────────────────────

    def _save_found(self):
        if not self._pending_results:
            return
        try:
            from modules.core.db import LibraryDB
            db = LibraryDB(Path(self._lib_config.metadata_file))
            for key, item in self._pending_results.items():
                # Preserve full_path from DB if the new result doesn't have it
                if not item.get('full_path'):
                    existing = db.get_item(key) or {}
                    if existing.get('full_path'):
                        item['full_path'] = existing['full_path']
                db.set_item(key, item)
            count = len(self._pending_results)
            self._pending_results = {}
            self._btn_save.setVisible(False)
            QMessageBox.information(
                self, 'Saved',
                f'{count} item(s) saved.\n'
                'Click Refresh in the library browser to see changes.',
            )
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Could not save:\n{e}')

    # ── Helpers ───────────────────────────────────────────────────────

    def _drop_finished_workers(self):
        self._finished_workers.clear()

    @property
    def _log_stream(self):
        if not hasattr(self, '_log_stream_obj'):
            from modules.gui.log_widget import _SignalStream
            self._log_stream_obj = _SignalStream()
            self._log_stream_obj.text_written.connect(self._append_log)
        return self._log_stream_obj

    def _append_log(self, text: str):
        self._log.moveCursor(QTextCursor.MoveOperation.End)
        self._log.insertPlainText(text)
        self._log.ensureCursorVisible()

    def done(self, result: int):
        if self._worker is not None and self._worker.isRunning():
            self._worker.request_stop()
            self._worker.wait(5000)
        super().done(result)
