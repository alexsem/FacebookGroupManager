"""Shared status formatting and URL action helpers across GUI tabs."""

from __future__ import annotations

from typing import Optional, Tuple

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import QApplication, QMessageBox, QTableWidgetItem, QWidget

_STATUS_MAP = {
    "SUCCESS": ("✅ Publicado", "#27AE60"),
    "PENDING_APPROVAL": ("🟡 Aprobación", "#F2C94C"),
    "POSSIBLE_SUCCESS": ("🟢 Enviado", "#27AE60"),
    "DRY_RUN": ("🔍 Simulado", "#56CCF2"),
    "FAILED": ("❌ Falló", "#EB5757"),
    "BLOCKED": ("⛔ Bloqueado", "#EB5757"),
    "NOT_A_MEMBER": ("🚫 No es miembro", "#9AA7B5"),
    "CANNOT_POST": ("🔒 Restringido", "#F2994A"),
}

_RAW_STATUS_COLORS = {
    "SUCCESS": "#27AE60",
    "PENDING_APPROVAL": "#F2C94C",
    "DRY_RUN": "#56CCF2",
    "FAILED": "#EB5757",
    "BLOCKED": "#EB5757",
}


def status_display(status_str: str) -> Tuple[str, str]:
    """Return (display_label, hex_color) for a publication status."""
    return _STATUS_MAP.get(status_str, (status_str, "#9AA7B5"))


def raw_status_color(status_str: str) -> str:
    """Return hex color for raw status codes."""
    return _RAW_STATUS_COLORS.get(status_str, "#E1E7EC")


def create_url_item(url: Optional[str]) -> QTableWidgetItem:
    """Create a styled table cell storing a post URL in UserRole."""
    item = QTableWidgetItem(url or "-")
    if url:
        item.setForeground(QColor("#4DA2FF"))
        item.setData(Qt.ItemDataRole.UserRole, url)
    return item


def copy_url_to_clipboard(parent: QWidget, url: Optional[str]) -> bool:
    """Copy URL to system clipboard, notifying if missing."""
    if not url:
        QMessageBox.information(
            parent,
            "Sin URL de post",
            "La fila seleccionada no tiene una URL de post capturada.",
        )
        return False
    clipboard = QApplication.clipboard()
    if clipboard:
        clipboard.setText(url)
    return True


def open_url_in_browser(parent: QWidget, url: Optional[str]) -> bool:
    """Open URL in the default browser, notifying if missing."""
    if not url:
        QMessageBox.information(
            parent,
            "Sin URL de post",
            "La fila seleccionada no tiene una URL de post capturada.",
        )
        return False
    return QDesktopServices.openUrl(QUrl(url))

