"""Campaign execution tab widget."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from batch_manager import GroupBatchManager
from config import BASE_DIR, PosterConfig
from gui.components import status_display
from gui.tabs.config_tab import RunOptions
from gui.worker import CampaignWorker
from post_bundle import PostBundle, PostBundleLoader
from poster import logger
from storage import (
    CampaignRepository,
    DatabaseManager,
    GroupRepository,
    PostRepository,
    compute_content_hash,
)


class CampaignTab(QWidget):
    """Tab 1: Post bundle preview, target groups, live monitor, and console."""

    sig_edit_config_requested = Signal()
    sig_data_changed = Signal()
    sig_campaign_finished = Signal()

    def __init__(
        self,
        config: PosterConfig,
        db_manager: DatabaseManager,
        run_options_provider: Callable[[], RunOptions],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.db_manager = db_manager
        self._get_run_options = run_options_provider

        self.current_bundle: Optional[PostBundle] = None
        self.current_manager: Optional[GroupBatchManager] = None
        self.campaign_worker: Optional[CampaignWorker] = None

        self._init_ui()
        self.load_bundle_directories()
        self.load_groups_from_db()
        self.update_config_summary(self._get_run_options())

    def _init_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 10, 6, 6)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._create_left_panel())
        splitter.addWidget(self._create_right_panel())
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 6)
        layout.addWidget(splitter)

    def _create_left_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(8)

        # 1. Content Bundle Card
        grp_content = QGroupBox("📁 Contenido de Publicación (Post Bundle)")
        content_layout = QVBoxLayout(grp_content)
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(6)

        folder_row = QHBoxLayout()
        self.combo_bundles = QComboBox()
        self.combo_bundles.currentIndexChanged.connect(self._on_bundle_selected)
        folder_row.addWidget(self.combo_bundles, stretch=1)

        btn_browse_bundle = QPushButton("Examinar...")
        btn_browse_bundle.clicked.connect(self._on_browse_bundle)
        folder_row.addWidget(btn_browse_bundle)
        content_layout.addLayout(folder_row)

        content_layout.addWidget(QLabel("Texto del mensaje (post_content.txt):"))
        self.txt_content_preview = QTextEdit()
        self.txt_content_preview.setPlaceholderText("El texto cargado del bundle aparecerá aquí...")
        self.txt_content_preview.setMinimumHeight(60)
        self.txt_content_preview.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        content_layout.addWidget(self.txt_content_preview, stretch=1)

        self.lbl_media_summary = QLabel("Archivos multimedia: Ninguno")
        self.lbl_media_summary.setStyleSheet("color: #4DA2FF; font-weight: 500; padding-top: 2px;")
        self.lbl_media_summary.setWordWrap(True)
        self.lbl_media_summary.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        content_layout.addWidget(self.lbl_media_summary, stretch=0)
        layout.addWidget(grp_content, stretch=1)

        # 2. Compact Config Summary Strip
        summary_card = QFrame()
        summary_card.setStyleSheet(
            "background-color: #181B20; border: 1px solid #262B33; border-radius: 8px; padding: 4px;"
        )
        summary_row = QHBoxLayout(summary_card)
        summary_row.setContentsMargins(10, 4, 10, 4)

        self.lbl_config_summary = QLabel("⚙️ Tanda: 10 | Delays: 45-90s | Cooldown: 30s")
        self.lbl_config_summary.setStyleSheet("color: #9AA7B5; font-size: 12px;")
        self.lbl_config_summary.setWordWrap(True)
        summary_row.addWidget(self.lbl_config_summary, stretch=1)

        btn_edit_config = QPushButton("⚙️ Ajustar")
        btn_edit_config.setToolTip("Ir a la pestaña Configuración")
        btn_edit_config.clicked.connect(self.sig_edit_config_requested.emit)
        summary_row.addWidget(btn_edit_config)
        layout.addWidget(summary_card)

        # 3. Action Buttons
        grp_actions = QGroupBox("🎮 Controles de Ejecución")
        actions_layout = QVBoxLayout(grp_actions)
        actions_layout.setContentsMargins(10, 10, 10, 10)
        actions_layout.setSpacing(6)

        self.chk_force_new_campaign = QCheckBox(
            "✨ Crear nueva campaña al iniciar (no reanudar anterior)"
        )
        self.chk_force_new_campaign.setStyleSheet("color: #9AA7B5; font-size: 12px;")
        actions_layout.addWidget(self.chk_force_new_campaign)

        self.btn_start = QPushButton("▶ Iniciar Campaña")
        self.btn_start.setObjectName("btn_start")
        self.btn_start.clicked.connect(self.start_campaign)
        actions_layout.addWidget(self.btn_start)

        row_ctrl = QHBoxLayout()
        self.btn_pause = QPushButton("⏸ Pausar")
        self.btn_pause.setObjectName("btn_pause")
        self.btn_pause.setEnabled(False)
        self.btn_pause.clicked.connect(self._on_pause_campaign)
        row_ctrl.addWidget(self.btn_pause)

        self.btn_stop = QPushButton("⏹ Detener")
        self.btn_stop.setObjectName("btn_stop")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._on_stop_campaign)
        row_ctrl.addWidget(self.btn_stop)
        actions_layout.addLayout(row_ctrl)

        self.btn_single_test = QPushButton("🧪 Probar en grupo seleccionado (Dry-Run)")
        self.btn_single_test.clicked.connect(self._on_test_single_group)
        actions_layout.addWidget(self.btn_single_test)
        layout.addWidget(grp_actions)

        scroll.setWidget(panel)
        return scroll

    def _create_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 0, 0, 0)
        layout.setSpacing(10)

        # 1. Target Groups Section
        grp_groups = QGroupBox("👥 Grupos de Facebook")
        groups_layout = QVBoxLayout(grp_groups)
        groups_layout.setSpacing(8)

        top_row = QHBoxLayout()
        self.lbl_groups_file = QLabel(f"BD: {self.config.db_path.name}")
        self.lbl_groups_file.setStyleSheet("color: #88B7FF; font-weight: bold;")
        top_row.addWidget(self.lbl_groups_file)

        btn_browse_groups = QPushButton("Importar .txt...")
        btn_browse_groups.clicked.connect(self.import_groups_dialog)
        top_row.addWidget(btn_browse_groups)
        top_row.addStretch()

        btn_select_all = QPushButton("Seleccionar Todos")
        btn_select_all.clicked.connect(lambda: self.set_all_groups_checked(True))
        top_row.addWidget(btn_select_all)

        btn_deselect_all = QPushButton("Deseleccionar")
        btn_deselect_all.clicked.connect(lambda: self.set_all_groups_checked(False))
        top_row.addWidget(btn_deselect_all)
        groups_layout.addLayout(top_row)

        self.table_groups = QTableWidget()
        self.table_groups.setColumnCount(4)
        self.table_groups.setHorizontalHeaderLabels(["Activar", "URL del Grupo", "Estado", "Detalles"])
        self.table_groups.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table_groups.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_groups.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table_groups.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table_groups.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        groups_layout.addWidget(self.table_groups)
        layout.addWidget(grp_groups, stretch=5)

        # 2. Live Progress Section
        grp_monitor = QGroupBox("📊 Monitor de Progreso en Vivo")
        monitor_layout = QVBoxLayout(grp_monitor)
        monitor_layout.setSpacing(6)

        self.lbl_status_message = QLabel("Listo para comenzar.")
        self.lbl_status_message.setStyleSheet("font-size: 13px; font-weight: bold; color: #FFFFFF;")
        monitor_layout.addWidget(self.lbl_status_message)

        self.progress_groups = QProgressBar()
        self.progress_groups.setValue(0)
        self.progress_groups.setFormat("Grupos: %v / %m (%p%)")
        monitor_layout.addWidget(self.progress_groups)

        self.lbl_countdown = QLabel("Pausa: En espera...")
        self.lbl_countdown.setStyleSheet("color: #F2994A; font-weight: 500;")
        monitor_layout.addWidget(self.lbl_countdown)
        layout.addWidget(grp_monitor, stretch=2)

        # 3. Live Console Section
        grp_console = QGroupBox("📜 Consola de Registro en Vivo")
        console_layout = QVBoxLayout(grp_console)
        console_layout.setSpacing(6)

        self.txt_console = QPlainTextEdit()
        self.txt_console.setReadOnly(True)
        self.txt_console.setMaximumBlockCount(1000)
        self.txt_console.setFont(QFont("Consolas", 10))
        console_layout.addWidget(self.txt_console)

        btn_clear_console = QPushButton("Limpiar Consola")
        btn_clear_console.clicked.connect(self.txt_console.clear)
        console_layout.addWidget(btn_clear_console, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addWidget(grp_console, stretch=3)

        return panel

    # -------------------------------------------------------------------------
    # Configuration Summary
    # -------------------------------------------------------------------------
    def update_config_summary(self, options: RunOptions) -> None:
        """Refresh the compact parameter strip using current RunOptions."""
        mode_text = "Simulación (Dry-Run)" if options.dry_run else "Publicación Real"
        mode_color = "#F2C94C" if options.dry_run else "#27AE60"
        summary_html = (
            f"<b>Tanda:</b> {options.batch_size} | "
            f"<b>Pausas:</b> {options.min_delay}-{options.max_delay}s | "
            f"<b>Cooldown:</b> {options.cooldown}s<br>"
            f"<b>Modo:</b> <span style='color: {mode_color};'>{mode_text}</span>"
        )
        if options.headless:
            summary_html += " | Headless"
        if options.ignore_history:
            summary_html += " | Ignorar historial"
        self.lbl_config_summary.setText(summary_html)

    # -------------------------------------------------------------------------
    # Bundle Management
    # -------------------------------------------------------------------------
    def load_bundle_directories(self) -> None:
        """Scan project directory for folders containing post_content.txt."""
        self.combo_bundles.clear()
        found_dirs: List[Path] = []

        for item in sorted(BASE_DIR.iterdir()):
            if item.is_dir() and not item.name.startswith(".") and item.name != "gui":
                if (item / "post_content.txt").exists():
                    found_dirs.append(item)

        if (BASE_DIR / "post_content.txt").exists() and BASE_DIR not in found_dirs:
            found_dirs.append(BASE_DIR)

        for d in found_dirs:
            label = d.name if d != BASE_DIR else "(Carpeta Raíz)"
            self.combo_bundles.addItem(label, userData=str(d))

        default_dir = self.config.resolved_post_dir
        for idx in range(self.combo_bundles.count()):
            if self.combo_bundles.itemData(idx) == str(default_dir):
                self.combo_bundles.setCurrentIndex(idx)
                return

        if self.combo_bundles.count() > 0:
            self.combo_bundles.setCurrentIndex(0)

    def _on_bundle_selected(self, index: int) -> None:
        if index < 0:
            return
        path_str = self.combo_bundles.itemData(index)
        if path_str:
            self._load_bundle_from_path(Path(path_str))

    def _on_browse_bundle(self) -> None:
        selected_dir = QFileDialog.getExistingDirectory(
            self, "Seleccionar carpeta con post_content.txt", str(BASE_DIR)
        )
        if selected_dir:
            bundle_path = Path(selected_dir)
            self.combo_bundles.addItem(bundle_path.name, userData=str(bundle_path))
            self.combo_bundles.setCurrentIndex(self.combo_bundles.count() - 1)
            self._load_bundle_from_path(bundle_path)

    def _load_bundle_from_path(self, bundle_dir: Path) -> None:
        try:
            loader = PostBundleLoader(bundle_dir)
            self.current_bundle = loader.load()
            self.txt_content_preview.setPlainText(self.current_bundle.text)

            images = [
                p.name
                for p in self.current_bundle.media_paths
                if p.suffix.lower() in loader.SUPPORTED_IMAGE_EXTENSIONS
            ]
            videos = [
                p.name
                for p in self.current_bundle.media_paths
                if p.suffix.lower() in loader.SUPPORTED_VIDEO_EXTENSIONS
            ]
            summary_parts = []
            if images:
                summary_parts.append(f"📷 {len(images)} foto(s)")
            if videos:
                summary_parts.append(f"🎥 {len(videos)} video(s)")

            if summary_parts:
                self.lbl_media_summary.setText(
                    "Multimedia adjunta: " + " | ".join(summary_parts)
                )
            else:
                self.lbl_media_summary.setText(
                    "Multimedia adjunta: Solo texto (sin imágenes/videos)"
                )
        except Exception as e:
            self.txt_content_preview.setPlainText("")
            self.lbl_media_summary.setText(f"❌ Error al cargar bundle: {e}")

    # -------------------------------------------------------------------------
    # Groups Table Management
    # -------------------------------------------------------------------------
    def import_groups_dialog(self) -> None:
        """Open file dialog to import group URLs from a .txt file into SQLite."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Importar archivo de grupos (.txt)",
            str(BASE_DIR),
            "Archivos de Texto (*.txt);;Todos (*.*)",
        )
        if file_path:
            self.import_groups_file(Path(file_path))

    def import_groups_file(self, path: Path) -> None:
        """Import a .txt file into SQLite and reload the groups table."""
        if not path.exists():
            return
        imported = GroupRepository(self.db_manager).import_from_txt(path)
        logger.info(f"Grupos importados desde {path.name} hacia SQLite: {imported} nuevos.")
        self.load_groups_from_db()

    def load_groups_from_db(self, campaign_id: Optional[int] = None) -> None:
        """Populate the groups table from SQLite and show statuses for the given campaign."""
        options = self._get_run_options()
        self.current_manager = GroupBatchManager(
            groups_file=None,
            batch_size=options.batch_size,
            db=self.db_manager,
            campaign_id=campaign_id,
        )
        groups = list(GroupRepository(self.db_manager).stream_groups())
        status_map = PostRepository(self.db_manager).get_status_map(
            self.current_manager.campaign_id
        )
        self.lbl_groups_file.setText(
            f"BD: {self.config.db_path.name} ({len(groups)} grupos)"
        )

        self.table_groups.setRowCount(len(groups))
        for row_idx, group in enumerate(groups):
            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk_item.setCheckState(Qt.CheckState.Checked)
            self.table_groups.setItem(row_idx, 0, chk_item)
            self.table_groups.setItem(row_idx, 1, QTableWidgetItem(group.url))

            status_item = QTableWidgetItem()
            post_rec = status_map.get(group.url)
            if post_rec:
                label, color = status_display(post_rec.status)
                status_item.setText(label)
                status_item.setForeground(QColor(color))
                details_text = post_rec.post_url or post_rec.details
            else:
                status_item.setText("⏳ Pendiente")
                status_item.setForeground(QColor("#9AA7B5"))
                details_text = ""

            self.table_groups.setItem(row_idx, 2, status_item)
            self.table_groups.setItem(row_idx, 3, QTableWidgetItem(details_text))

        self.progress_groups.setMaximum(max(1, len(groups)))
        self.progress_groups.setValue(0)

    def set_all_groups_checked(self, checked: bool) -> None:
        """Check or uncheck all group rows."""
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for row in range(self.table_groups.rowCount()):
            item = self.table_groups.item(row, 0)
            if item:
                item.setCheckState(state)

    def get_selected_group_urls(self) -> List[str]:
        """Return list of checked group URLs."""
        urls: List[str] = []
        for row in range(self.table_groups.rowCount()):
            chk = self.table_groups.item(row, 0)
            url_item = self.table_groups.item(row, 1)
            if chk and chk.checkState() == Qt.CheckState.Checked and url_item:
                urls.append(url_item.text())
        return urls

    # -------------------------------------------------------------------------
    # Campaign Execution Controls
    # -------------------------------------------------------------------------
    def start_campaign(self) -> None:
        """Validate selection, resolve/create campaign in SQLite, and start CampaignWorker."""
        selected_urls = self.get_selected_group_urls()
        if not selected_urls:
            QMessageBox.warning(
                self,
                "Sin grupos seleccionados",
                "Por favor marca al menos un grupo de la tabla para iniciar.",
            )
            return

        if not self.current_bundle:
            QMessageBox.warning(
                self,
                "Sin contenido",
                "Carga o selecciona una carpeta válida con 'post_content.txt'.",
            )
            return

        options = self._get_run_options()
        content_hash = compute_content_hash(
            self.current_bundle.text, [p.name for p in self.current_bundle.media_paths]
        )
        campaign = CampaignRepository(self.db_manager).get_or_create_for_bundle(
            name=self.current_bundle.source_dir.name,
            post_text=self.current_bundle.text,
            bundle_dir=str(self.current_bundle.source_dir),
            content_hash=content_hash,
            force_new=self.chk_force_new_campaign.isChecked(),
        )
        self.chk_force_new_campaign.setChecked(False)
        self.current_manager = GroupBatchManager(
            groups_file=None,
            batch_size=options.batch_size,
            db=self.db_manager,
            campaign_id=campaign.id,
        )
        self.sig_data_changed.emit()

        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_pause.setText("⏸ Pausar")
        self.btn_stop.setEnabled(True)
        self.btn_single_test.setEnabled(False)

        self.progress_groups.setMaximum(len(selected_urls))
        self.progress_groups.setValue(0)
        self.lbl_status_message.setText(
            f"Iniciando campaña #{campaign.id} ({campaign.name})..."
        )

        self.campaign_worker = CampaignWorker(
            config=self.config,
            manager=self.current_manager,
            bundle=self.current_bundle,
            groups=selected_urls,
            batch_size=options.batch_size,
            min_delay=options.min_delay,
            max_delay=options.max_delay,
            cooldown=options.cooldown,
            dry_run=options.dry_run,
            ignore_history=options.ignore_history,
            headless=options.headless,
        )
        self._connect_worker_signals(self.campaign_worker)
        self.campaign_worker.start()

    def _on_pause_campaign(self) -> None:
        if not self.campaign_worker:
            return
        if self.campaign_worker.is_paused:
            self.campaign_worker.resume()
            self.btn_pause.setText("⏸ Pausar")
        else:
            self.campaign_worker.pause()
            self.btn_pause.setText("▶ Reanudar")

    def _on_stop_campaign(self) -> None:
        if self.campaign_worker:
            self.campaign_worker.stop()
            self.btn_stop.setEnabled(False)

    def _on_test_single_group(self) -> None:
        selected_row = self.table_groups.currentRow()
        if selected_row < 0:
            QMessageBox.information(
                self,
                "Seleccionar fila",
                "Haz clic en una fila de la tabla para probar en ese grupo específico.",
            )
            return

        url = self.table_groups.item(selected_row, 1).text()
        if not self.current_bundle:
            QMessageBox.warning(
                self, "Sin contenido", "Carga una carpeta de contenido válida primero."
            )
            return

        assert self.current_manager is not None
        self.btn_start.setEnabled(False)
        self.btn_single_test.setEnabled(False)
        self.lbl_status_message.setText(f"Probando publicación en grupo: {url}")

        self.campaign_worker = CampaignWorker(
            config=self.config,
            manager=self.current_manager,
            bundle=self.current_bundle,
            groups=[url],
            batch_size=1,
            min_delay=5,
            max_delay=5,
            cooldown=5,
            dry_run=True,
            ignore_history=True,
            headless=False,
        )
        self._connect_worker_signals(self.campaign_worker)
        self.campaign_worker.start()

    def _connect_worker_signals(self, worker: CampaignWorker) -> None:
        worker.sig_status.connect(self.set_status_message)
        worker.sig_group_started.connect(self._on_group_started)
        worker.sig_group_finished.connect(self._on_group_finished)
        worker.sig_countdown.connect(self._on_countdown_tick)
        worker.sig_finished.connect(self._on_campaign_finished)
        worker.sig_error.connect(self._on_worker_error)

    # -------------------------------------------------------------------------
    # Worker Signal Handlers & Console
    # -------------------------------------------------------------------------
    def set_status_message(self, status_msg: str) -> None:
        """Update the live status label."""
        self.lbl_status_message.setText(status_msg)

    def _on_group_started(self, url: str, current: int, _total: int) -> None:
        self.progress_groups.setValue(current)
        self._update_table_row_status(url, "🚀 Publicando...", "#4DA2FF")

    def _on_group_finished(
        self, url: str, status: str, details: str, post_url: str = ""
    ) -> None:
        label, color = status_display(status)
        self._update_table_row_status(url, label, color, post_url or details)
        self.sig_data_changed.emit()

    def _on_countdown_tick(self, label: str, seconds_left: int) -> None:
        if seconds_left > 0:
            mins, secs = divmod(seconds_left, 60)
            time_str = f"{mins:02d}:{secs:02d}" if mins > 0 else f"{secs}s"
            self.lbl_countdown.setText(f"⏳ {label}: {time_str} restantes...")
        else:
            self.lbl_countdown.setText("Pausa: Reanudando...")

    def _on_campaign_finished(self, _stats: dict) -> None:
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_pause.setText("⏸ Pausar")
        self.btn_stop.setEnabled(False)
        self.btn_single_test.setEnabled(True)
        self.lbl_countdown.setText("Pausa: En espera...")
        self.sig_campaign_finished.emit()

    def _on_worker_error(self, err_msg: str) -> None:
        QMessageBox.critical(self, "Aviso de Campaña", err_msg)

    def _update_table_row_status(
        self, url: str, status_text: str, color_hex: str, details: str = ""
    ) -> None:
        for row in range(self.table_groups.rowCount()):
            item_url = self.table_groups.item(row, 1)
            if item_url and item_url.text() == url:
                status_item = self.table_groups.item(row, 2)
                if status_item:
                    status_item.setText(status_text)
                    status_item.setForeground(QColor(color_hex))
                if details:
                    self.table_groups.setItem(row, 3, QTableWidgetItem(details))
                break

    def append_log(self, timestamp: str, level: str, msg: str) -> None:
        """Append a formatted HTML log entry to the live console."""
        color = "#E1E7EC"
        if level == "WARNING":
            color = "#F2C94C"
        elif level in ("ERROR", "CRITICAL"):
            color = "#EB5757"
        elif "exitos" in msg.lower() or "success" in msg.lower():
            color = "#27AE60"

        html_line = (
            f"<span style='color: #7D8B9B;'>[{timestamp}]</span> "
            f"<span style='color: {color};'><b>[{level}]</b> {msg}</span>"
        )
        self.txt_console.appendHtml(html_line)
        self.txt_console.moveCursor(QTextCursor.MoveOperation.End)

    def stop_worker_on_close(self) -> None:
        """Cooperatively stop running worker thread before window shutdown."""
        if self.campaign_worker and self.campaign_worker.isRunning():
            self.campaign_worker.stop()
            self.campaign_worker.wait(3000)

