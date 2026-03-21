"""
Log output widget — captures sys.stdout and displays in a QPlainTextEdit.
"""

import sys

from PyQt6.QtCore import QObject, pyqtSignal, Qt
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPlainTextEdit, QPushButton, QCheckBox, QLabel,
)


class _SignalStream(QObject):
    """Forwards write() calls as Qt signals (thread-safe)."""
    text_written = pyqtSignal(str)

    def write(self, text: str):
        if text:
            self.text_written.emit(text)

    def flush(self):
        pass


class LogWidget(QWidget):
    """
    Widget that shows captured stdout output.
    Use the .stream property to redirect sys.stdout inside workers.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stream = _SignalStream()
        self._stream.text_written.connect(self._append_text, Qt.ConnectionType.QueuedConnection)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        toolbar = QHBoxLayout()
        lbl = QLabel("Log Output")
        lbl.setStyleSheet("font-weight: bold;")
        toolbar.addWidget(lbl)
        toolbar.addStretch()

        self._auto_scroll = QCheckBox("Auto-scroll")
        self._auto_scroll.setChecked(True)
        toolbar.addWidget(self._auto_scroll)

        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(self.clear)
        toolbar.addWidget(btn_clear)

        layout.addLayout(toolbar)

        self._text_edit = QPlainTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setMaximumBlockCount(5000)
        font = QFont("Consolas", 9)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._text_edit.setFont(font)
        self._text_edit.setStyleSheet(
            "QPlainTextEdit { border:1px solid #aaa; border-radius:4px; padding:4px; }"
        )
        layout.addWidget(self._text_edit)

    def _append_text(self, text: str):
        stripped = text.rstrip('\n')
        if not stripped:
            return
        self._text_edit.appendPlainText(stripped)
        if self._auto_scroll.isChecked():
            cursor = self._text_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self._text_edit.setTextCursor(cursor)

    def clear(self):
        self._text_edit.clear()

    def append(self, text: str):
        self._append_text(text)

    @property
    def stream(self) -> _SignalStream:
        return self._stream
