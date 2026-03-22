"""
Library browser page — generic table view driven by plugin.columns.
Shows all organized items enriched with metadata.
Data loading runs in a background thread to keep the GUI responsive.
Cover images are loaded asynchronously and cached in memory.
"""

import os
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QImage, QPixmap
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton,
    QTableView, QHeaderView, QLineEdit, QComboBox, QFrame,
    QCheckBox, QMessageBox, QDialog, QPlainTextEdit, QScrollArea,
    QMenu, QStyledItemDelegate, QApplication,
)

_KEY_ROLE   = Qt.ItemDataRole.UserRole       # stores metadata dict key on col-0 cell
_URL_ROLE   = Qt.ItemDataRole.UserRole + 1   # stores raw URL on cover cells

# Keys that are always read-only in the edit dialog
_DIALOG_READONLY = frozenset({'provider_source'})

_COVER_ROW_HEIGHT  = 90   # px — used when cover column is visible
_DEFAULT_ROW_HEIGHT = 30  # px


# ── Cover image loader ─────────────────────────────────────────────────────────

class _CoverLoader(QThread):
    """Fetches cover images in background; emits batches of (url, QImage).
    QImage is thread-safe; QPixmap conversion happens in the main thread."""

    batch_ready = pyqtSignal(list)   # list of (url: str, img: QImage)

    def __init__(self, urls: list):
        super().__init__()
        self._urls = urls
        self._stop = False

    def request_stop(self):
        self._stop = True

    def run(self):
        import requests
        batch = []
        for url in self._urls:
            if self._stop or not url:
                continue
            try:
                r = requests.get(url, timeout=8)
                if r.ok:
                    img = QImage()
                    img.loadFromData(r.content)
                    if not img.isNull():
                        batch.append((url, img))
                        if len(batch) >= 8:
                            self.batch_ready.emit(batch)
                            batch = []
            except Exception:
                pass
        if batch:
            self.batch_ready.emit(batch)


# ── Cover delegate ─────────────────────────────────────────────────────────────

class _CoverDelegate(QStyledItemDelegate):
    """Renders a cover image from the shared cache; falls back to URL text."""

    def __init__(self, cache: dict, parent=None):
        super().__init__(parent)
        self._cache = cache   # {url: QPixmap}

    def paint(self, painter, option, index):
        url = index.data(_URL_ROLE)
        if url:
            px = self._cache.get(url)
            if px and not px.isNull():
                scaled = px.scaled(
                    option.rect.width() - 4,
                    option.rect.height() - 4,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                x = option.rect.x() + (option.rect.width()  - scaled.width())  // 2
                y = option.rect.y() + (option.rect.height() - scaled.height()) // 2
                painter.drawPixmap(x, y, scaled)
                return
        # No image yet — show plain text URL
        super().paint(painter, option, index)

    def sizeHint(self, option, index):
        return QSize(120, _COVER_ROW_HEIGHT)


# ── Item edit dialog ───────────────────────────────────────────────────────────

class _ItemEditDialog(QDialog):
    """Full-form editor for a single metadata item."""

    def __init__(self, meta_key: str, item_data: dict, plugin, lib_config,
                 ui_state=None, parent=None):
        super().__init__(parent)
        self._meta_key   = meta_key
        self._item_data  = dict(item_data)
        self._plugin     = plugin
        self._lib_config = lib_config
        self._ui_state   = ui_state
        self._fields     = {}

        title = item_data.get('original_name') or item_data.get('name', meta_key)
        self.setWindowTitle(f'Edit — {title}')
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        if ui_state:
            ui_state.restore_window(self, key='item_edit_dialog', default_w=640, default_h=520)
        else:
            self.resize(640, 520)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(8)

        title_lbl = QLabel(self._item_data.get('original_name') or
                           self._item_data.get('name', self._meta_key))
        title_lbl.setProperty('role', 'title')
        layout.addWidget(title_lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.setContentsMargins(0, 4, 0, 4)
        form.setSpacing(6)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        shown = set()

        for key, label, _ in self._plugin.columns:
            if key in shown:
                continue
            shown.add(key)
            value = str(self._item_data.get(key, '') or '')
            if key in _DIALOG_READONLY:
                w = QLineEdit(value)
                w.setReadOnly(True)
                w.setProperty('role', 'muted')
            elif key == 'description':
                w = QPlainTextEdit(value)
                w.setFixedHeight(90)
            else:
                w = QLineEdit(value)
            form.addRow(label + ':', w)
            self._fields[key] = w

        for key, label in [
            ('cover_url',       'Cover URL'),
            ('website_url',     'Website URL'),
            ('provider_url',    'Provider URL'),
            ('provider_source', 'Source'),
        ]:
            if key in shown:
                continue
            value = str(self._item_data.get(key, '') or '')
            if not value:
                continue
            shown.add(key)
            w = QLineEdit(value)
            if key in _DIALOG_READONLY:
                w.setReadOnly(True)
                w.setProperty('role', 'muted')
            form.addRow(label + ':', w)
            self._fields[key] = w

        scroll.setWidget(form_widget)
        layout.addWidget(scroll, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_save = QPushButton('Save')
        btn_save.clicked.connect(self._save)
        btn_cancel = QPushButton('Cancel')
        btn_cancel.setObjectName('btn_secondary')
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

    def _save(self):
        updates = {}
        for key, widget in self._fields.items():
            if key in _DIALOG_READONLY:
                continue
            if isinstance(widget, QPlainTextEdit):
                updates[key] = widget.toPlainText()
            else:
                updates[key] = widget.text()

        old_path = str(self._item_data.get('full_path', '') or '').strip()
        new_path = str(updates.get('full_path', old_path) or '').strip()

        # ── Rename folder on disk if path changed ──────────────────────
        renamed = False
        if new_path and old_path and new_path != old_path:
            if not Path(old_path).exists():
                reply = QMessageBox.question(
                    self, 'Folder Not Found',
                    f'Original folder not found at:\n{old_path}\n\n'
                    'Save the new path to the database anyway?',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return
            else:
                try:
                    os.rename(old_path, new_path)
                    renamed = True
                except OSError as e:
                    QMessageBox.critical(self, 'Rename Failed',
                        f'Could not rename folder:\n{old_path}\n→ {new_path}\n\n{e}')
                    return

        # ── Update metadata ────────────────────────────────────────────
        try:
            from modules.core.db import LibraryDB
            db = LibraryDB(Path(self._lib_config.metadata_file))
        except Exception as e:
            if renamed:
                try:
                    os.rename(new_path, old_path)
                except OSError:
                    pass
            QMessageBox.critical(self, 'Error', f'Could not open metadata DB:\n{e}')
            return

        if not db.item_exists(self._meta_key):
            if renamed:
                try:
                    os.rename(new_path, old_path)
                except OSError:
                    pass
            QMessageBox.warning(self, 'Not found',
                                f'Entry {self._meta_key!r} no longer exists in metadata.')
            return

        try:
            if new_path != old_path:
                new_key = Path(new_path).name
                field_updates = dict(updates)
                field_updates['original_name'] = new_key
                field_updates['full_path']      = new_path
                if 'display_name' in field_updates:
                    field_updates['name'] = field_updates['display_name']
                db.rename_item(self._meta_key, new_key, field_updates)
            else:
                item = db.get_item(self._meta_key) or {}
                item.update(updates)
                if 'display_name' in updates:
                    item['name'] = updates['display_name']
                db.set_item(self._meta_key, item)
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Could not save metadata:\n{e}')
            return

        self.accept()

    def done(self, result: int):
        if self._ui_state:
            self._ui_state.save_window(self, key='item_edit_dialog')
        super().done(result)


# ── Background loader ─────────────────────────────────────────────────────────

class _LoadWorker(QThread):
    done = pyqtSignal(list)

    def __init__(self, lib_config, plugin):
        super().__init__()
        self._lib_config = lib_config
        self._plugin     = plugin

    def run(self):
        try:
            from modules.core.db import LibraryDB
            items = LibraryDB(Path(self._lib_config.metadata_file)).get_all_items()
        except Exception as e:
            print(f'[ERROR] Failed to load metadata: {e}')
            self.done.emit([])
            return

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

    _READONLY_KEYS = frozenset({'provider_source'})

    def __init__(self, lib_config, plugin, ui_state, parent=None):
        super().__init__(parent)
        self._lib_config   = lib_config
        self._plugin       = plugin
        self._ui_state     = ui_state
        self._state_key    = f'browser_{plugin.media_type}'
        self._data         = []
        self._state_loaded = False
        self._worker       = None
        self._cover_loader = None
        self._loading      = False
        self._deleted_keys = set()
        self._img_cache    = {}   # {url: QPixmap}

        # Logical column index of the cover_url column (None if not present)
        self._cover_col_logical = next(
            (i + 1 for i, (key, _, _) in enumerate(plugin.columns) if key == 'cover_url'),
            None,
        )

        # Genre column index for filter
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

        # Wrap text — restore saved state
        wrap_saved = self._ui_state.get(f'{self._state_key}_wrap', False)
        self._chk_wrap = QCheckBox('Wrap text')
        self._chk_wrap.setChecked(wrap_saved)
        self._chk_wrap.toggled.connect(self._on_wrap_toggled)
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
        self._table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self._table.setSortingEnabled(False)
        self._table.doubleClicked.connect(self._open_edit_dialog)
        self._table.setWordWrap(wrap_saved)

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionsMovable(True)
        header.sectionResized.connect(self._on_header_changed)
        header.sectionMoved.connect(self._on_header_changed)
        header.sortIndicatorChanged.connect(self._on_header_changed)
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._show_column_menu)

        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table)

        # Cover delegate (applied once; cover col may not exist for all media types)
        if self._cover_col_logical is not None:
            self._cover_delegate = _CoverDelegate(self._img_cache, self._table)
            self._table.setItemDelegateForColumn(self._cover_col_logical, self._cover_delegate)

        # Action row
        act = QHBoxLayout()

        self._btn_edit = QPushButton('Edit')
        self._btn_edit.setEnabled(False)
        self._btn_edit.clicked.connect(self._edit_selected)
        act.addWidget(self._btn_edit)

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
        self._start_cover_load()

    def _populate_table(self):
        self._loading = True
        self._model.setRowCount(0)
        self._table.setSortingEnabled(False)

        col_keys = ['name'] + [col[0] for col in self._plugin.columns]

        readonly_cols = {0}
        for i, (key, _, _) in enumerate(self._plugin.columns, start=1):
            if key in self._READONLY_KEYS:
                readonly_cols.add(i)

        cover_col = self._cover_col_logical

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
                if col_idx == cover_col:
                    cell.setData(str(val), _URL_ROLE)
                    cell.setText('')   # hide raw URL — delegate draws image
                row.append(cell)
            self._model.appendRow(row)

        self._table.setSortingEnabled(True)
        self._lbl_status.setText(f'{len(self._data)} items')

        # Restore state once; also applies wrap + hidden columns
        if not self._state_loaded:
            self._state_loaded = True
            QTimer.singleShot(0, self._restore_state)
        else:
            self._apply_row_heights()

        self._loading = False
        self._apply_filter()

    def _restore_state(self):
        self._ui_state.restore_table(self._table, self._state_key)
        self._apply_row_heights()

    def _apply_row_heights(self):
        """Set row height: cover row height if cover column visible, else default/wrap."""
        cover_visible = (
            self._cover_col_logical is not None and
            not self._table.horizontalHeader().isSectionHidden(self._cover_col_logical)
        )
        vh = self._table.verticalHeader()
        if cover_visible:
            vh.setDefaultSectionSize(_COVER_ROW_HEIGHT)
            vh.setMinimumSectionSize(_COVER_ROW_HEIGHT)
        elif self._chk_wrap.isChecked():
            self._table.resizeRowsToContents()
        else:
            vh.setDefaultSectionSize(_DEFAULT_ROW_HEIGHT)
            vh.setMinimumSectionSize(_DEFAULT_ROW_HEIGHT)

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

    # ── Cover image loading ────────────────────────────────────────────
    def _start_cover_load(self):
        if self._cover_col_logical is None:
            return
        if self._cover_loader and self._cover_loader.isRunning():
            self._cover_loader.request_stop()
            self._cover_loader.wait(2000)

        urls = [
            item.get('cover_url', '')
            for item in self._data
            if item.get('cover_url') and item['cover_url'] not in self._img_cache
        ]
        if not urls:
            return

        self._cover_loader = _CoverLoader(urls)
        self._cover_loader.batch_ready.connect(self._on_covers_loaded)
        self._cover_loader.start()

    def _on_covers_loaded(self, batch: list):
        for url, img in batch:
            self._img_cache[url] = QPixmap.fromImage(img)
        self._table.viewport().update()

    # ── Column visibility ──────────────────────────────────────────────
    def _show_column_menu(self, pos):
        header = self._table.horizontalHeader()
        menu = QMenu(self)
        for logical in range(self._model.columnCount()):
            label = self._model.headerData(logical, Qt.Orientation.Horizontal) or str(logical)
            act = menu.addAction(str(label))
            act.setCheckable(True)
            act.setChecked(not header.isSectionHidden(logical))
            act.triggered.connect(
                lambda checked, col=logical: self._set_column_visible(col, checked)
            )
        menu.exec(header.mapToGlobal(pos))

    def _set_column_visible(self, logical: int, visible: bool):
        self._table.horizontalHeader().setSectionHidden(logical, not visible)
        self._apply_row_heights()
        self._on_header_changed()

    # ──────────────────────────────────────────────────────────────────
    def _on_item_changed(self, _item):
        if not self._loading:
            self._btn_save.setEnabled(True)

    def _on_selection_changed(self, selected, _deselected):
        has_sel = bool(self._table.selectionModel().selectedRows())
        self._btn_delete.setEnabled(has_sel)
        self._btn_edit.setEnabled(has_sel)

    def _edit_selected(self):
        rows = self._table.selectionModel().selectedRows()
        if rows:
            self._open_edit_dialog(rows[0])

    def _open_edit_dialog(self, index):
        key_item = self._model.item(index.row(), 0)
        if not key_item:
            return
        meta_key = key_item.data(_KEY_ROLE)
        if not meta_key:
            return

        item_data = next((d for d in self._data if d.get('_key') == meta_key), None)
        if item_data is None:
            return

        dlg = _ItemEditDialog(
            meta_key, item_data, self._plugin, self._lib_config,
            ui_state=self._ui_state, parent=self.window(),
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.load_data()

    def _on_wrap_toggled(self, checked: bool):
        self._table.setWordWrap(checked)
        self._ui_state.set(f'{self._state_key}_wrap', checked)
        self._ui_state.save()
        self._apply_row_heights()

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

        self._lbl_status.setText(f'{self._model.rowCount()} items')
        self._btn_save.setEnabled(True)
        self._btn_delete.setEnabled(False)

    # ──────────────────────────────────────────────────────────────────
    def _save_changes(self):
        try:
            from modules.core.db import LibraryDB
            db = LibraryDB(Path(self._lib_config.metadata_file))
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Could not open metadata DB:\n{e}')
            return

        for key in self._deleted_keys:
            db.delete_item(key)

        col_keys = ['name'] + [col[0] for col in self._plugin.columns]
        editable_keys = {
            col[0] for col in self._plugin.columns
            if col[0] not in self._READONLY_KEYS
        }

        all_items = db.get_all_items()

        for row in range(self._model.rowCount()):
            key_item = self._model.item(row, 0)
            if not key_item:
                continue
            meta_key = key_item.data(_KEY_ROLE)
            if not meta_key or meta_key not in all_items:
                continue
            item = dict(all_items[meta_key])
            for col_idx, col_key in enumerate(col_keys):
                if col_key not in editable_keys:
                    continue
                cell = self._model.item(row, col_idx)
                if cell:
                    if col_idx == self._cover_col_logical:
                        val = cell.data(_URL_ROLE) or ''
                    else:
                        val = cell.text()
                    item[col_key] = val
                    if col_key == 'display_name':
                        item['name'] = val
            db.set_item(meta_key, item)

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
                    if cell:
                        text = cell.data(_URL_ROLE) if col == self._cover_col_logical else cell.text()
                        if text and search in str(text).lower():
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
        self._debounce.stop()
        if self._state_loaded:
            self._save_table_state()

    def stop_worker(self):
        if self._worker and self._worker.isRunning():
            self._worker.done.disconnect()
            self._worker.quit()
            self._worker.wait(2000)
        if self._cover_loader and self._cover_loader.isRunning():
            self._cover_loader.request_stop()
            self._cover_loader.wait(2000)

    def hideEvent(self, event):
        self._debounce.stop()
        if self._state_loaded:
            self._save_table_state()
        super().hideEvent(event)
