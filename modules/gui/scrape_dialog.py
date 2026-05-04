"""
Scrape dialog — re-query providers for selected library items.
Shows full metadata for every result before saving. NO auto-save.
"""

import textwrap
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QFont, QImage, QPixmap
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox, QSplitter, QWidget, QPlainTextEdit, QProgressBar,
    QDialogButtonBox, QCheckBox,
)


class ScrapeDialog(QDialog):
    """
    Review dialog for re-scraping library items.

    Layout:
      - Top: results table with columns for every key metadata field
      - Bottom: detail pane — cover thumbnail + full field dump for selected row
    Auto-starts scrape on open; Re-search Selected re-runs chosen rows.
    Nothing is saved until the user clicks Save Found.
    """

    _COL_FOLDER   = 0
    _COL_SEARCH   = 1
    _COL_FOUND    = 2
    _COL_YEAR     = 3
    _COL_GENRE    = 4
    _COL_RATING   = 5
    _COL_PROVIDER = 6
    _COL_STATUS   = 7

    def __init__(self, items: list, lib_config, plugin, parent=None):
        super().__init__(parent)
        self._lib_config       = lib_config
        self._plugin           = plugin
        self._items            = items
        self._worker           = None
        self._finished_workers = []
        self._pending_results  = {}   # key -> full result dict
        self._provider_checks  = {}   # provider_name -> QCheckBox
        self._cover_url_shown  = ''   # tracks which cover is currently in the pane
        self._current_url      = ''   # URL for "Open in Browser"
        self._nam              = QNetworkAccessManager(self)

        self.setWindowTitle(f'Scrape — {plugin.name}')
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.resize(1120, 680)
        self._setup_ui()
        self._populate_table()
        QTimer.singleShot(100, self._start_scrape)

    # ── UI ────────────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 10)
        layout.setSpacing(8)

        lbl = QLabel(f'Re-scrape {len(self._items)} item(s) — {self._plugin.name}')
        lbl.setProperty('role', 'title')
        layout.addWidget(lbl)

        info = QLabel(
            'Double-click Search Query to edit it, then click Re-search Selected. '
            'Click any row to see the full result below. Nothing is saved until you click Save Found.'
        )
        info.setWordWrap(True)
        info.setProperty('role', 'muted')
        layout.addWidget(info)

        # ── Provider checkboxes ────────────────────────────────────────
        provider_row = self._build_provider_row()
        if provider_row:
            layout.addWidget(provider_row)

        splitter = QSplitter(Qt.Orientation.Vertical)

        # ── Results table ─────────────────────────────────────────────
        self._table = QTableWidget()
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels([
            'Folder Name', 'Search Query',
            'Found Name', 'Year', 'Genre', 'Rating', 'Provider', 'St.',
        ])
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr.setSectionsMovable(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked |
            QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self._table.currentCellChanged.connect(
            lambda row, _col, _prow, _pcol: self._on_row_selected(row)
        )
        splitter.addWidget(self._table)

        # ── Detail pane ───────────────────────────────────────────────
        detail_w = QWidget()
        detail_lay = QVBoxLayout(detail_w)
        detail_lay.setContentsMargins(0, 4, 0, 0)
        detail_lay.setSpacing(4)

        det_hdr = QHBoxLayout()
        det_lbl = QLabel('Result Preview  (select a row)')
        det_lbl.setProperty('role', 'muted')
        det_hdr.addWidget(det_lbl)
        det_hdr.addStretch()
        self._btn_open = QPushButton('Open in Browser')
        self._btn_open.setObjectName('btn_secondary')
        self._btn_open.setEnabled(False)
        self._btn_open.clicked.connect(self._open_in_browser)
        det_hdr.addWidget(self._btn_open)
        detail_lay.addLayout(det_hdr)

        det_split = QSplitter(Qt.Orientation.Horizontal)

        self._cover_lbl = QLabel('No cover')
        self._cover_lbl.setFixedWidth(130)
        self._cover_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self._cover_lbl.setStyleSheet(
            'QLabel { background: #1e1e2e; border-radius: 4px; '
            'color: #555; padding: 4px; font-size: 9px; }'
        )
        self._cover_lbl.setWordWrap(True)
        det_split.addWidget(self._cover_lbl)

        self._detail_view = QPlainTextEdit()
        self._detail_view.setReadOnly(True)
        self._detail_view.setFont(QFont('Consolas', 9))
        self._detail_view.setPlaceholderText(
            'Click a row to preview the full scraped result here…'
        )
        det_split.addWidget(self._detail_view)
        det_split.setSizes([130, 860])

        detail_lay.addWidget(det_split, 1)
        splitter.addWidget(detail_w)

        splitter.setSizes([360, 240])
        layout.addWidget(splitter, 1)

        # ── Progress ──────────────────────────────────────────────────
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # ── Save Found ────────────────────────────────────────────────
        self._btn_save = QPushButton('Save Found')
        self._btn_save.setVisible(False)
        self._btn_save.clicked.connect(self._save_found)
        layout.addWidget(self._btn_save)

        # ── Action row ────────────────────────────────────────────────
        bar = QHBoxLayout()

        self._btn_start = QPushButton('Start Scrape')
        self._btn_start.clicked.connect(self._start_scrape)
        bar.addWidget(self._btn_start)

        self._btn_research = QPushButton('Re-search Selected')
        self._btn_research.setObjectName('btn_secondary')
        self._btn_research.clicked.connect(self._research_selected)
        bar.addWidget(self._btn_research)

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

    def _build_provider_row(self) -> QWidget | None:
        from modules.gui.settings_page import _LIBRARY_PROVIDERS
        media_type       = getattr(self._lib_config, 'media_type', '') or ''
        all_defs         = _LIBRARY_PROVIDERS.get(media_type, [])
        if not all_defs:
            return None

        primary_name     = getattr(self._lib_config, 'primary_provider', '') or ''
        supplement_names = set(getattr(self._lib_config, 'supplement_providers', []) or [])
        configured       = {primary_name} | supplement_names

        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel('Sources:')
        lbl.setProperty('role', 'muted')
        row.addWidget(lbl)
        for provider_id, display_name, _is_primary, _fields in all_defs:
            if not provider_id:
                continue
            is_primary = (provider_id == primary_name)
            label = f'{display_name} ★' if is_primary else display_name
            chk = QCheckBox(label)
            chk.setToolTip('Primary provider' if is_primary else provider_id)
            chk.setChecked(provider_id in configured)
            row.addWidget(chk)
            self._provider_checks[provider_id] = chk
        row.addStretch()
        return container

    def _populate_table(self):
        self._table.setRowCount(len(self._items))
        for row, item in enumerate(self._items):
            folder_name = item.get('name', item.get('_key', ''))
            search_q    = self._plugin.clean_name(folder_name) if folder_name else item.get('_key', '')
            db_key      = item.get('_key', '')

            def _ro(text=''):
                it = QTableWidgetItem(text)
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                return it

            self._table.setItem(row, self._COL_FOLDER, _ro(folder_name))

            si = QTableWidgetItem(search_q)
            si.setData(Qt.ItemDataRole.UserRole, db_key)
            si.setToolTip('Double-click to edit, then click Re-search Selected')
            self._table.setItem(row, self._COL_SEARCH, si)

            for col in (self._COL_FOUND, self._COL_YEAR, self._COL_GENRE,
                        self._COL_RATING, self._COL_PROVIDER):
                self._table.setItem(row, col, _ro())

            sti = _ro('…')
            sti.setForeground(Qt.GlobalColor.gray)
            sti.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, self._COL_STATUS, sti)

        self._table.setColumnWidth(self._COL_FOLDER,   170)
        self._table.setColumnWidth(self._COL_SEARCH,   170)
        self._table.setColumnWidth(self._COL_FOUND,    210)
        self._table.setColumnWidth(self._COL_YEAR,      52)
        self._table.setColumnWidth(self._COL_GENRE,    130)
        self._table.setColumnWidth(self._COL_RATING,    55)
        self._table.setColumnWidth(self._COL_PROVIDER,  90)
        self._table.setColumnWidth(self._COL_STATUS,    38)

    # ── Scrape ────────────────────────────────────────────────────────

    def _get_active_providers(self) -> list | None:
        if not self._provider_checks:
            return None
        active = [n for n, chk in self._provider_checks.items() if chk.isChecked()]
        return active if active else None

    def _collect_rows(self, rows=None) -> list:
        """Build retry_items and reset status cells. rows=None means all rows."""
        items = []
        row_range = rows if rows is not None else range(self._table.rowCount())
        for row in row_range:
            si = self._table.item(row, self._COL_SEARCH)
            fi = self._table.item(row, self._COL_FOLDER)
            if not si:
                continue
            db_key      = si.data(Qt.ItemDataRole.UserRole) or ''
            search_name = si.text().strip() or db_key
            orig        = fi.text() if fi else db_key
            items.append({'key': db_key, 'search_name': search_name, 'original_name': orig})
            # Reset this row
            sti = self._table.item(row, self._COL_STATUS)
            if sti:
                sti.setText('…')
                sti.setForeground(Qt.GlobalColor.gray)
            for col in (self._COL_FOUND, self._COL_YEAR, self._COL_GENRE,
                        self._COL_RATING, self._COL_PROVIDER):
                cell = self._table.item(row, col)
                if cell:
                    cell.setText('')
        return items

    def _run_worker(self, retry_items: list):
        self._pending_results = {}
        self._btn_save.setVisible(False)
        self._progress.setVisible(True)
        self._btn_start.setEnabled(False)
        self._btn_research.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._detail_view.clear()
        self._cover_lbl.setText('No cover')
        self._cover_url_shown = ''

        from modules.gui.workers import MetadataRetryWorker
        self._worker = MetadataRetryWorker(
            self._lib_config, self._plugin, self._log_stream, retry_items,
            active_providers=self._get_active_providers(),
        )
        self._worker.item_result.connect(self._on_item_result)
        self._worker.finished.connect(self._on_scrape_done)
        self._worker.start()

    def _start_scrape(self):
        selected = sorted({idx.row() for idx in self._table.selectedIndexes()})
        if selected:
            rows = [r for r in selected if not self._row_has_result(r)]
        else:
            rows = [r for r in range(self._table.rowCount()) if not self._row_has_result(r)]
        items = self._collect_rows(rows)
        if items:
            self._run_worker(items)

    def _row_has_result(self, row: int) -> bool:
        si = self._table.item(row, self._COL_SEARCH)
        if not si:
            return False
        return si.data(Qt.ItemDataRole.UserRole) in self._pending_results

    def _research_selected(self):
        rows = sorted({idx.row() for idx in self._table.selectedIndexes()})
        if not rows:
            return
        retry_items = self._collect_rows(rows)
        if retry_items:
            self._run_worker(retry_items)

    def _stop_scrape(self):
        if self._worker and self._worker.isRunning():
            self._worker.request_stop()

    def _on_item_result(self, key: str, found: bool, _display_name: str):
        for row in range(self._table.rowCount()):
            si = self._table.item(row, self._COL_SEARCH)
            if si and si.data(Qt.ItemDataRole.UserRole) == key:
                sti = self._table.item(row, self._COL_STATUS)
                if sti:
                    if found:
                        sti.setText('✓')
                        sti.setForeground(Qt.GlobalColor.darkGreen)
                    else:
                        sti.setText('✗')
                        sti.setForeground(Qt.GlobalColor.red)
                break

    def _on_scrape_done(self, success: bool, message: str,
                        auto_results: dict, multi_candidates: dict):
        self._progress.setVisible(False)
        self._btn_start.setEnabled(True)
        self._btn_research.setEnabled(True)
        self._btn_stop.setEnabled(False)

        if self._worker is not None:
            self._finished_workers.append(self._worker)
            QTimer.singleShot(0, self._drop_finished_workers)
        self._worker = None

        self._pending_results.update(auto_results)
        for key, result in auto_results.items():
            self._set_row_result(key, result)

        from modules.gui.failed_dialog import _PickResultDialog
        skip_all = False
        for key, candidates in multi_candidates.items():
            search_name = key
            for row in range(self._table.rowCount()):
                si = self._table.item(row, self._COL_SEARCH)
                if si and si.data(Qt.ItemDataRole.UserRole) == key:
                    search_name = si.text() or key
                    break

            picked = False
            if not skip_all:
                dlg = _PickResultDialog(search_name, candidates, self)
                if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_result:
                    result = dlg.selected_result
                    result['original_name'] = candidates[0].get('original_name', key)
                    result['found']         = True
                    result['igdb_found']    = True
                    result['manual']        = False
                    self._pending_results[key] = result
                    self._set_row_result(key, result)
                    picked = True
                elif dlg.skip_all:
                    skip_all = True

            if not picked:
                for row in range(self._table.rowCount()):
                    si = self._table.item(row, self._COL_SEARCH)
                    if si and si.data(Qt.ItemDataRole.UserRole) == key:
                        sti = self._table.item(row, self._COL_STATUS)
                        if sti:
                            sti.setText('–')
                            sti.setForeground(Qt.GlobalColor.darkYellow)
                        break

        if self._pending_results:
            self._btn_save.setText(f'Save Found ({len(self._pending_results)})')
            self._btn_save.setVisible(True)

    def _set_row_result(self, key: str, result: dict):
        """Fill Found Name / Year / Genre / Rating / Provider columns for this key."""
        for row in range(self._table.rowCount()):
            si = self._table.item(row, self._COL_SEARCH)
            if not si or si.data(Qt.ItemDataRole.UserRole) != key:
                continue

            def _s(col, field):
                cell = self._table.item(row, col)
                if cell:
                    cell.setText(str(result.get(field) or ''))

            _s(self._COL_FOUND,    'name')
            _s(self._COL_YEAR,     'year')
            _s(self._COL_GENRE,    'genre')
            _s(self._COL_RATING,   'rating')
            _s(self._COL_PROVIDER, 'provider_source')

            sti = self._table.item(row, self._COL_STATUS)
            if sti:
                sti.setText('✓')
                sti.setForeground(Qt.GlobalColor.darkGreen)
            break

    # ── Detail pane ───────────────────────────────────────────────────

    def _on_row_selected(self, row: int):
        if row < 0:
            return
        si = self._table.item(row, self._COL_SEARCH)
        if not si:
            return
        key    = si.data(Qt.ItemDataRole.UserRole)
        result = self._pending_results.get(key)
        self._show_detail(result)

    def _show_detail(self, result: dict | None):
        if not result:
            self._detail_view.setPlainText('')
            self._cover_lbl.setText('No cover')
            self._cover_url_shown = ''
            self._current_url = ''
            self._btn_open.setEnabled(False)
            return

        self._current_url = str(result.get('provider_url') or result.get('website_url') or '').strip()
        self._btn_open.setEnabled(bool(self._current_url))

        lines = []
        for label, field in [
            ('Name',         'name'),
            ('Year',         'year'),
            ('Genre',        'genre'),
            ('Rating',       'rating'),
            ('Provider',     'provider_source'),
            ('Slug',         'slug'),
            ('Website',      'website_url'),
            ('Provider URL', 'provider_url'),
            ('Cover URL',    'cover_url'),
        ]:
            val = str(result.get(field) or '').strip()
            if val:
                lines.append(f'{label:<14}: {val}')

        desc = str(result.get('description') or '').strip()
        if desc:
            lines.append('')
            lines.append('Description:')
            for chunk in textwrap.wrap(desc, width=90):
                lines.append(f'  {chunk}')

        self._detail_view.setPlainText('\n'.join(lines))

        cover_url = str(result.get('cover_url') or '').strip()
        if cover_url and cover_url != self._cover_url_shown:
            self._cover_url_shown = cover_url
            self._cover_lbl.setText('Loading…')
            self._fetch_cover(cover_url)
        elif not cover_url:
            self._cover_lbl.setText('No cover')
            self._cover_url_shown = ''

    def _fetch_cover(self, url: str):
        req = QNetworkRequest(QUrl(url))
        req.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader,
                      'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')
        reply = self._nam.get(req)
        reply.finished.connect(lambda: self._on_cover_reply(reply, url))

    def _on_cover_reply(self, reply, url: str):
        data = bytes(reply.readAll())
        reply.deleteLater()
        if url != self._cover_url_shown:
            return
        img = QImage()
        if img.loadFromData(data) and not img.isNull():
            self._set_cover(img)
        else:
            self._cover_lbl.setText('No cover')

    def _set_cover(self, img: QImage):
        px = QPixmap.fromImage(img)
        w  = max(self._cover_lbl.width() - 4, 200)
        scaled = px.scaled(
            w, 220,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._cover_lbl.setPixmap(scaled)

    def _open_in_browser(self):
        if self._current_url:
            import webbrowser
            webbrowser.open(self._current_url)

    # ── Save ──────────────────────────────────────────────────────────

    def _save_found(self):
        if not self._pending_results:
            return
        try:
            from modules.core.db import LibraryDB
            db = LibraryDB(Path(self._lib_config.metadata_file))
            for key, item in self._pending_results.items():
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
        return self._log_stream_obj

    def done(self, result: int):
        if self._worker is not None and self._worker.isRunning():
            self._worker.request_stop()
            self._worker.wait(5000)
        super().done(result)
