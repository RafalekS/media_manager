"""
Theme Editor page — lets the user view and edit individual theme colors,
create new themes based on built-ins, and delete custom themes.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QScrollArea, QFrame, QInputDialog,
    QMessageBox, QSizePolicy as QSP, QColorDialog, QGridLayout,
)

from modules.gui.theme_manager import (
    COLOR_LABELS, COLOR_GROUPS, _BUILTIN,
    load_themes, save_theme, delete_theme, get_theme_names,
)


class ThemeEditor(QWidget):
    theme_applied = pyqtSignal(str)
    themes_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dirty = False
        self._current_data = {}
        # Widgets keyed by color key: (swatch_btn, hex_edit)
        self._color_widgets: dict[str, tuple[QPushButton, QLineEdit]] = {}

        self._build_ui()
        self._refresh_combo()

    # ── UI Construction ───────────────────────────────────────────────

    def _build_ui(self):
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(24, 24, 24, 24)
        main_lay.setSpacing(10)

        # Title
        title = QLabel('Theme Editor')
        title.setProperty('role', 'title')
        main_lay.addWidget(title)

        # Top bar
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        theme_lbl = QLabel('Theme:')
        theme_lbl.setSizePolicy(QSP.Policy.Fixed, QSP.Policy.Fixed)
        top_bar.addWidget(theme_lbl)

        self._combo = QComboBox()
        self._combo.setMinimumWidth(160)
        self._combo.setSizePolicy(QSP.Policy.Fixed, QSP.Policy.Fixed)
        self._combo.currentTextChanged.connect(self._on_theme_selected)
        top_bar.addWidget(self._combo)

        self._btn_new = QPushButton('New Theme')
        self._btn_new.setSizePolicy(QSP.Policy.Fixed, QSP.Policy.Fixed)
        self._btn_new.clicked.connect(self._new_theme)
        top_bar.addWidget(self._btn_new)

        self._btn_delete = QPushButton('Delete')
        self._btn_delete.setObjectName('btn_danger')
        self._btn_delete.setSizePolicy(QSP.Policy.Fixed, QSP.Policy.Fixed)
        self._btn_delete.clicked.connect(self._delete_theme)
        top_bar.addWidget(self._btn_delete)

        top_bar.addStretch()

        self._btn_save = QPushButton('Save & Apply')
        self._btn_save.setSizePolicy(QSP.Policy.Fixed, QSP.Policy.Fixed)
        self._btn_save.clicked.connect(self._save_and_apply)
        top_bar.addWidget(self._btn_save)

        main_lay.addLayout(top_bar)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        main_lay.addWidget(sep)

        # Scrollable color grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        self._grid_lay = QVBoxLayout(inner)
        self._grid_lay.setContentsMargins(0, 0, 0, 0)
        self._grid_lay.setSpacing(0)
        self._build_color_grid()
        self._grid_lay.addStretch()
        scroll.setWidget(inner)
        main_lay.addWidget(scroll, 1)

    def _build_color_grid(self):
        for group_name, keys in COLOR_GROUPS.items():
            # Group header
            hdr = QLabel(group_name)
            hdr.setStyleSheet('font-weight: bold; font-size: 10pt; padding: 8px 0 4px 0;')
            self._grid_lay.addWidget(hdr)

            # Grid for this group
            grid_widget = QWidget()
            grid = QGridLayout(grid_widget)
            grid.setContentsMargins(0, 0, 0, 4)
            grid.setHorizontalSpacing(8)
            grid.setVerticalSpacing(4)

            for row_idx, key in enumerate(keys):
                label_text = COLOR_LABELS.get(key, key)

                lbl = QLabel(label_text)
                lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                lbl.setMinimumWidth(160)
                grid.addWidget(lbl, row_idx, 0)

                swatch = QPushButton()
                swatch.setFixedSize(40, 22)
                swatch.setObjectName(f'swatch_{key}')
                swatch.clicked.connect(lambda checked, k=key: self._pick_color(k))
                grid.addWidget(swatch, row_idx, 1)

                hex_edit = QLineEdit()
                hex_edit.setMaximumWidth(90)
                hex_edit.setPlaceholderText('#rrggbb')
                hex_edit.editingFinished.connect(lambda k=key: self._on_hex_edited(k))
                grid.addWidget(hex_edit, row_idx, 2)

                grid.setColumnStretch(3, 1)
                self._color_widgets[key] = (swatch, hex_edit)

            self._grid_lay.addWidget(grid_widget)

    # ── Combo management ──────────────────────────────────────────────

    def _refresh_combo(self, select: str = None):
        current = select or self._combo.currentText()
        self._combo.blockSignals(True)
        self._combo.clear()
        for name in get_theme_names():
            self._combo.addItem(name)
        self._combo.blockSignals(False)

        idx = self._combo.findText(current)
        if idx >= 0:
            self._combo.setCurrentIndex(idx)
        elif self._combo.count() > 0:
            self._combo.setCurrentIndex(0)

        self._on_theme_selected(self._combo.currentText())

    # ── Theme loading ─────────────────────────────────────────────────

    def _on_theme_selected(self, name: str):
        if not name:
            return
        themes = load_themes()
        data = themes.get(name, {})
        self._current_data = dict(data)
        self._dirty = False
        self._populate_rows(data)
        # Delete button: only enabled for non-built-in themes
        is_builtin = name in _BUILTIN
        self._btn_delete.setEnabled(not is_builtin)

    def _populate_rows(self, data: dict):
        for key, (swatch, hex_edit) in self._color_widgets.items():
            color = data.get(key, '#000000')
            self._apply_swatch(swatch, color)
            hex_edit.blockSignals(True)
            hex_edit.setText(color)
            hex_edit.blockSignals(False)

    def _apply_swatch(self, btn: QPushButton, color: str):
        btn.setStyleSheet(
            f'QPushButton {{ background-color: {color}; border: 1px solid #888; border-radius: 2px; }}'
        )

    # ── Color editing ─────────────────────────────────────────────────

    def _pick_color(self, key: str):
        current = self._current_data.get(key, '#000000')
        initial = QColor(current)
        color = QColorDialog.getColor(initial, self, f'Pick color — {COLOR_LABELS.get(key, key)}')
        if color.isValid():
            hex_val = color.name()
            self._current_data[key] = hex_val
            swatch, hex_edit = self._color_widgets[key]
            self._apply_swatch(swatch, hex_val)
            hex_edit.blockSignals(True)
            hex_edit.setText(hex_val)
            hex_edit.blockSignals(False)
            self._dirty = True

    def _on_hex_edited(self, key: str):
        swatch, hex_edit = self._color_widgets[key]
        text = hex_edit.text().strip()
        color = QColor(text)
        if color.isValid():
            self._current_data[key] = text
            self._apply_swatch(swatch, text)
            self._dirty = True
        else:
            # Restore previous value
            prev = self._current_data.get(key, '#000000')
            hex_edit.blockSignals(True)
            hex_edit.setText(prev)
            hex_edit.blockSignals(False)

    # ── Actions ───────────────────────────────────────────────────────

    def _save_and_apply(self):
        name = self._combo.currentText()
        if not name:
            return
        save_theme(name, self._current_data)
        self._dirty = False
        self.theme_applied.emit(name)

    def _new_theme(self):
        builtin_names = sorted(_BUILTIN.keys())
        base_name, ok = QInputDialog.getItem(
            self, 'New Theme', 'Base theme:', builtin_names, 0, False
        )
        if not ok or not base_name:
            return
        new_name, ok2 = QInputDialog.getText(
            self, 'New Theme', 'New theme name:'
        )
        if not ok2 or not new_name.strip():
            return
        new_name = new_name.strip()
        existing = get_theme_names()
        if new_name in existing:
            QMessageBox.warning(self, 'Duplicate', f'Theme "{new_name}" already exists.')
            return
        base_data = dict(_BUILTIN.get(base_name, _BUILTIN['Light']))
        save_theme(new_name, base_data)
        self._refresh_combo(select=new_name)
        self.themes_changed.emit()

    def _delete_theme(self):
        name = self._combo.currentText()
        if not name or name in _BUILTIN:
            return
        ans = QMessageBox.question(
            self, 'Delete Theme',
            f'Delete theme "{name}"?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        delete_theme(name)
        self._refresh_combo()
        self.themes_changed.emit()
