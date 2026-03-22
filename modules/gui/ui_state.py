"""
UI state persistence — saves/restores window geometry, table column state.
"""

import json
from pathlib import Path

from PyQt6.QtCore import Qt


class UIState:
    """Persists window geometry and table view state across sessions."""

    def __init__(self, state_file: str):
        self.state_file = Path(state_file)
        self._state = self._load()

    def _load(self) -> dict:
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump(self._state, f, indent=2)

    def get(self, key, default=None):
        return self._state.get(key, default)

    def set(self, key, value):
        self._state[key] = value

    def save_window(self, window, key='main_window'):
        g = window.geometry()
        self._state[key] = {
            'x': g.x(), 'y': g.y(),
            'width': g.width(), 'height': g.height(),
        }
        self.save()

    def restore_window(self, window, key='main_window',
                       default_w=1400, default_h=900):
        if key in self._state:
            s = self._state[key]
            window.setGeometry(
                s.get('x', 100), s.get('y', 100),
                s.get('width', default_w), s.get('height', default_h),
            )
        else:
            window.resize(default_w, default_h)

    def save_splitter(self, splitter, key):
        self._state[key] = splitter.sizes()
        self.save()

    def restore_splitter(self, splitter, key):
        if key in self._state:
            splitter.setSizes(self._state[key])

    def save_table(self, table, key):
        header = table.horizontalHeader()
        col_count = header.count()
        self._state[key] = {
            'column_widths':  [header.sectionSize(i) for i in range(col_count)],
            'column_order':   [header.logicalIndex(i) for i in range(col_count)],
            'hidden_columns': [i for i in range(col_count) if header.isSectionHidden(i)],
            'sort_column':    header.sortIndicatorSection(),
            'sort_order':     header.sortIndicatorOrder().value,
        }
        self.save()

    def restore_table(self, table, key):
        if key not in self._state:
            return
        s = self._state[key]
        header = table.horizontalHeader()
        col_count = header.count()

        widths = s.get('column_widths', [])
        for i, w in enumerate(widths):
            if i < col_count and w > 0:
                header.resizeSection(i, w)

        order = s.get('column_order', [])
        for visual_pos, logical_idx in enumerate(order):
            if visual_pos < col_count and logical_idx < col_count:
                current_visual = header.visualIndex(logical_idx)
                if current_visual != visual_pos:
                    header.moveSection(current_visual, visual_pos)

        for col in s.get('hidden_columns', []):
            if col < col_count:
                header.setSectionHidden(col, True)

        sort_col = s.get('sort_column', -1)
        sort_order_val = s.get('sort_order', 0)
        if sort_col >= 0:
            sort_order = (Qt.SortOrder.AscendingOrder
                          if sort_order_val == 0
                          else Qt.SortOrder.DescendingOrder)
            table.sortByColumn(sort_col, sort_order)
