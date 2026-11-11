"""Campaigns and associated created posts master-detail tab widget."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gui.components import (
    copy_url_to_clipboard,
    create_url_item,
    open_url_in_browser,
    status_display,
)
from storage import CampaignRepository, DatabaseManager, PostRepository


class CampaignsPostsTab(QWidget):
    """Tab 4: Master-detail view of campaigns and their created posts/URLs."""

    sig_campaign_activated = Signal(int)
    sig_status_message = Signal(str)

    def __init__(
        self, db_manager: DatabaseManager, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.db_manager = db_manager
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        splitter = QSplitter(Qt.Orientation.Vertical)

        # Top pane: Campaigns Master Table
        grp_campaigns = QGroupBox("📂 Campañas Registradas")
        campaigns_layout = QVBoxLayout(grp_campaigns)
        campaigns_layout.setSpacing(8)

        camp_toolbar = QHBoxLayout()
        lbl_camp_hint = QLabel("Selecciona una campaña para ver los posts creados asociados:")
        lbl_camp_hint.setStyleSheet("color: #7D8B9B; font-weight: 500;")
        camp_toolbar.addWidget(lbl_camp_hint)
        camp_toolbar.addStretch()

        self.btn_activate_campaign = QPushButton("★ Marcar como Activa")
        self.btn_activate_campaign.clicked.connect(self._on_activate_selected_campaign)
        camp_toolbar.addWidget(self.btn_activate_campaign)

        btn_refresh = QPushButton("🔄 Actualizar")
        btn_refresh.clicked.connect(self.refresh)
        camp_toolbar.addWidget(btn_refresh)
        campaigns_layout.addLayout(camp_toolbar)

        self.table_campaigns = QTableWidget()
        self.table_campaigns.setColumnCount(7)
        self.table_campaigns.setHorizontalHeaderLabels(
            ["ID", "Campaña", "Estado", "Publicados", "Con URL", "Pend. Aprob.", "Creada"]
        )
        self.table_campaigns.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_campaigns.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_campaigns.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_campaigns.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table_campaigns.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_campaigns.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table_campaigns.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table_campaigns.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table_campaigns.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table_campaigns.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.table_campaigns.itemSelectionChanged.connect(self._on_campaign_row_selected)
        campaigns_layout.addWidget(self.table_campaigns)

        splitter.addWidget(grp_campaigns)

        # Bottom pane: Created Posts Detail Table
        grp_posts = QGroupBox("📌 Posts Creados de la Campaña Seleccionada")
        posts_layout = QVBoxLayout(grp_posts)
        posts_layout.setSpacing(8)

        posts_toolbar = QHBoxLayout()
        self.lbl_selected_campaign_detail = QLabel("Sin campaña seleccionada")
        self.lbl_selected_campaign_detail.setStyleSheet("color: #E1E7EC; font-weight: 500;")
        self.lbl_selected_campaign_detail.setWordWrap(True)
        posts_toolbar.addWidget(self.lbl_selected_campaign_detail, stretch=1)

        posts_toolbar.addWidget(QLabel("Mostrar:"))
        self.combo_campaign_post_filter = QComboBox()
        self.combo_campaign_post_filter.addItem("Publicados y Pendientes", userData="CREATED")
        self.combo_campaign_post_filter.addItem("Solo con URL capturada", userData="WITH_URL")
        self.combo_campaign_post_filter.addItem("Todos los estados", userData="ALL")
        self.combo_campaign_post_filter.currentIndexChanged.connect(self._on_campaign_row_selected)
        posts_toolbar.addWidget(self.combo_campaign_post_filter)

        btn_copy_url = QPushButton("📋 Copiar URL")
        btn_copy_url.clicked.connect(self._on_copy_post_url)
        posts_toolbar.addWidget(btn_copy_url)

        btn_open_url = QPushButton("🌐 Abrir Post")
        btn_open_url.clicked.connect(self._on_open_post_url)
        posts_toolbar.addWidget(btn_open_url)
        posts_layout.addLayout(posts_toolbar)

        self.table_campaign_posts = QTableWidget()
        self.table_campaign_posts.setColumnCount(6)
        self.table_campaign_posts.setHorizontalHeaderLabels(
            ["Grupo (URL)", "Estado", "URL del Post", "ID Post FB", "Fecha / Hora", "Detalles"]
        )
        self.table_campaign_posts.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_campaign_posts.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_campaign_posts.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_campaign_posts.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_campaign_posts.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table_campaign_posts.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table_campaign_posts.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table_campaign_posts.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table_campaign_posts.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.table_campaign_posts.cellDoubleClicked.connect(lambda _r, _c: self._on_open_post_url())
        posts_layout.addWidget(self.table_campaign_posts)

        splitter.addWidget(grp_posts)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 6)
        layout.addWidget(splitter)

    def refresh(self) -> None:
        """Reload campaigns summary table and associated posts."""
        selected_id = self.get_selected_campaign_id()
        summaries = CampaignRepository(self.db_manager).list_campaigns_with_stats()

        self.table_campaigns.blockSignals(True)
        self.table_campaigns.setRowCount(len(summaries))
        target_row = 0 if summaries else -1

        for row_idx, summary in enumerate(summaries):
            camp = summary.campaign
            id_item = QTableWidgetItem(f"#{camp.id}")
            id_item.setData(Qt.ItemDataRole.UserRole, camp.id)
            self.table_campaigns.setItem(row_idx, 0, id_item)

            self.table_campaigns.setItem(row_idx, 1, QTableWidgetItem(camp.name))

            state_item = QTableWidgetItem("★ Activa" if camp.is_active else "Inactiva")
            state_item.setForeground(QColor("#27AE60" if camp.is_active else "#7D8B9B"))
            self.table_campaigns.setItem(row_idx, 2, state_item)

            self.table_campaigns.setItem(row_idx, 3, QTableWidgetItem(str(summary.published_count)))
            self.table_campaigns.setItem(row_idx, 4, QTableWidgetItem(str(summary.with_url_count)))
            self.table_campaigns.setItem(row_idx, 5, QTableWidgetItem(str(summary.pending_approval_count)))
            self.table_campaigns.setItem(
                row_idx, 6, QTableWidgetItem(camp.created_at[:19].replace("T", " "))
            )

            if selected_id is not None and camp.id == selected_id:
                target_row = row_idx

        self.table_campaigns.blockSignals(False)

        if target_row >= 0:
            self.table_campaigns.selectRow(target_row)
        self._on_campaign_row_selected()

    def get_selected_campaign_id(self) -> Optional[int]:
        """Return currently selected campaign ID, or None."""
        row = self.table_campaigns.currentRow()
        if row < 0:
            return None
        id_item = self.table_campaigns.item(row, 0)
        if not id_item:
            return None
        val = id_item.data(Qt.ItemDataRole.UserRole)
        return int(val) if val is not None else None

    def _on_campaign_row_selected(self) -> None:
        campaign_id = self.get_selected_campaign_id()
        if campaign_id is None:
            self.lbl_selected_campaign_detail.setText("Sin campaña seleccionada")
            self.table_campaign_posts.setRowCount(0)
            return

        campaign = CampaignRepository(self.db_manager).get_by_id(campaign_id)
        if not campaign:
            self.lbl_selected_campaign_detail.setText("Campaña no encontrada")
            self.table_campaign_posts.setRowCount(0)
            return

        snippet = campaign.post_text.replace("\n", " ").strip()
        if len(snippet) > 90:
            snippet = snippet[:87] + "..."
        bundle_info = Path(campaign.bundle_dir).name if campaign.bundle_dir else "Sin bundle"
        self.lbl_selected_campaign_detail.setText(
            f"<b>#{campaign.id} {campaign.name}</b> ({bundle_info}) — {snippet or '(Sin texto)'}"
        )

        filter_mode = self.combo_campaign_post_filter.currentData()
        statuses = (
            ("SUCCESS", "PENDING_APPROVAL", "POSSIBLE_SUCCESS")
            if filter_mode == "CREATED"
            else None
        )
        only_with_url = filter_mode == "WITH_URL"

        posts = list(
            PostRepository(self.db_manager).stream_posts(
                campaign_id=campaign_id,
                statuses=statuses,
                only_with_url=only_with_url,
            )
        )
        self.table_campaign_posts.setRowCount(len(posts))
        for row_idx, post in enumerate(posts):
            self.table_campaign_posts.setItem(row_idx, 0, QTableWidgetItem(post.group_url))

            label, color = status_display(post.status)
            st_item = QTableWidgetItem(label)
            st_item.setForeground(QColor(color))
            self.table_campaign_posts.setItem(row_idx, 1, st_item)

            self.table_campaign_posts.setItem(row_idx, 2, create_url_item(post.post_url))
            self.table_campaign_posts.setItem(row_idx, 3, QTableWidgetItem(post.fb_post_id or "-"))
            ts = post.published_at or post.updated_at
            self.table_campaign_posts.setItem(row_idx, 4, QTableWidgetItem(ts[:19].replace("T", " ")))
            self.table_campaign_posts.setItem(row_idx, 5, QTableWidgetItem(post.details))

    def _on_activate_selected_campaign(self) -> None:
        campaign_id = self.get_selected_campaign_id()
        if campaign_id is None:
            return
        CampaignRepository(self.db_manager).set_active_campaign(campaign_id)
        self.refresh()
        self.sig_campaign_activated.emit(campaign_id)

    def _get_selected_post_url(self) -> Optional[str]:
        row = self.table_campaign_posts.currentRow()
        if row < 0:
            return None
        url_item = self.table_campaign_posts.item(row, 2)
        if not url_item:
            return None
        val = url_item.data(Qt.ItemDataRole.UserRole)
        return str(val) if val else None

    def _on_copy_post_url(self) -> None:
        url = self._get_selected_post_url()
        if copy_url_to_clipboard(self, url) and url:
            self.sig_status_message.emit(f"URL copiada al portapapeles: {url}")

    def _on_open_post_url(self) -> None:
        open_url_in_browser(self, self._get_selected_post_url())

