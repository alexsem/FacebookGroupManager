"""Reusable KPI metric card widget."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class MetricCard(QFrame):
    """Dark-themed KPI card displaying a title and numeric/text value."""

    def __init__(
        self, title: str, initial_value: str = "0", color: str = "#4DA2FF", parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            "background-color: #181B20; border: 1px solid #262B33; border-radius: 8px; padding: 10px;"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        self.lbl_title = QLabel(title)
        self.lbl_title.setStyleSheet("color: #7D8B9B; font-size: 11px; font-weight: 600;")

        self.lbl_value = QLabel(initial_value)
        self.lbl_value.setStyleSheet(f"color: {color}; font-size: 24px; font-weight: bold;")

        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_value)

    def set_value(self, value: int | str) -> None:
        """Update the displayed KPI value."""
        self.lbl_value.setText(str(value))

