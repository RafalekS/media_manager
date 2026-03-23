"""Shared table utilities."""

from PyQt6.QtWidgets import QTableWidgetItem


class CITableWidgetItem(QTableWidgetItem):
    """QTableWidgetItem with case-insensitive sorting."""

    def __lt__(self, other: QTableWidgetItem) -> bool:
        return self.text().lower() < other.text().lower()
