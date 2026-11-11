"""History and audit log tab widget."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config import PosterConfig
from gui.components import (
    MetricCard,
    create_url_item,
    open_url_in_browser,
    raw_status_color,
)
from storage import CampaignRepository, DatabaseManager, PostRepository


class HistoryTab(QWidget):
    """Tab 2: Persistent SQLite publication audit log across campaigns."""

    def __init__(
        self,
        config: PosterConfig,
        db_manager: DatabaseManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.db_manager = db_manager
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        cards_layout = QHBoxLayout()
        self.card_total = MetricCard("Total Procesados", "0", "#4DA2FF")
        self.card_success = MetricCard("Exitosos", "0", "#27AE60")
        self.card_pending = MetricCard("Aprobación Pendiente", "0", "#F2C94C")
        self.card_failed = MetricCard("Fallidos / Bloqueados", "0", "#EB5757")

        cards_layout.addWidget(self.card_total)
        cards_layout.addWidget(self.card_success)
        cards_layout.addWidget(self.card_pending)
        cards_layout.addWidget(self.card_failed)
        layout.addLayout(cards_layout)

        toolbar = QHBoxLayout()
        lbl_info = QLabel(f"Registro persistente en SQLite ({self.config.db_path.name})")
        lbl_info.setStyleSheet("color: #7D8B9B; font-weight: 500;")
        toolbar.addWidget(lbl_info)
        toolbar.addStretch()

        toolbar.addWidget(QLabel("Campaña:"))
        self.combo_history_campaign = QComboBox()
        self.combo_history_campaign.setMinimumWidth(220)
        self.combo_history_campaign.currentIndexChanged.connect(self.reload_table)
        toolbar.addWidget(self.combo_history_campaign)

        btn_reload = QPushButton("🔄 Actualizar Historial")
        btn_reload.clicked.connect(self.refresh)
        toolbar.addWidget(btn_reload)

        layout.addLayout(toolbar)

        self.table_history = QTableWidget()
        self.table_history.setColumnCount(6)
        self.table_history.setHorizontalHeaderLabels(
            ["Campaña", "URL del Grupo", "Estado", "URL del Post", "Fecha / Hora", "Detalles"]
        )
        self.table_history.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_history.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_history.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table_history.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_history.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table_history.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table_history.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table_history.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.table_history.cellDoubleClicked.connect(self._on_row_double_clicked)
        layout.addWidget(self.table_history, stretch=1)

    def refresh(self) -> None:
        """Reload campaign filter choices and history rows from SQLite."""
        self.refresh_campaigns()
        self.reload_table()

    def refresh_campaigns(self) -> None:
        """Refresh the campaign dropdown preserving the current selection if possible."""
        current_selection = self.combo_history_campaign.currentData()
        self.combo_history_campaign.blockSignals(True)
        self.combo_history_campaign.clear()
        self.combo_history_campaign.addItem("Todas las campañas", userData=None)
        for camp in CampaignRepository(self.db_manager).list_campaigns():
            prefix = "★ " if camp.is_active else ""
            self.combo_history_campaign.addItem(
                f"{prefix}#{camp.id} {camp.name}", userData=camp.id
            )
        if current_selection is not None:
            idx = self.combo_history_campaign.findData(current_selection)
            if idx >= 0:
                self.combo_history_campaign.setCurrentIndex(idx)
        self.combo_history_campaign.blockSignals(False)

    def reload_table(self) -> None:
        """Update KPI cards and audit table rows for the selected campaign."""
        selected_campaign_id = self.combo_history_campaign.currentData()
        post_repo = PostRepository(self.db_manager)
        stats = post_repo.get_campaign_stats(campaign_id=selected_campaign_id)
        posts = list(post_repo.stream_posts(campaign_id=selected_campaign_id))

        self.card_total.set_value(stats["total_recorded"])
        self.card_success.set_value(stats["success_direct"])
        self.card_pending.set_value(stats["pending_approval"])
        self.card_failed.set_value(stats["failed"] + stats["blocked"])

        self.table_history.setRowCount(len(posts))
        for row_idx, post in enumerate(posts):
            camp_label = post.campaign_name or f"#{post.campaign_id}"
            self.table_history.setItem(row_idx, 0, QTableWidgetItem(camp_label))
            self.table_history.setItem(row_idx, 1, QTableWidgetItem(post.group_url))

            st_item = QTableWidgetItem(post.status)
            st_item.setForeground(QColor(raw_status_color(post.status)))
            self.table_history.setItem(row_idx, 2, st_item)

            self.table_history.setItem(row_idx, 3, create_url_item(post.post_url))
            ts = post.updated_at or post.published_at
            self.table_history.setItem(row_idx, 4, QTableWidgetItem(ts[:19].replace("T", " ")))
            self.table_history.setItem(row_idx, 5, QTableWidgetItem(post.details))

    def _on_row_double_clicked(self, row: int, _col: int) -> None:
        item = self.table_history.item(row, 3)
        if not item:
            return
        url = item.data(Qt.ItemDataRole.UserRole)
        if url:
            open_url_in_browser(self, str(url))

