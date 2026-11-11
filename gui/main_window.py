"""Main window implementation for Facebook Group Batch Poster in PySide6."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent, QColor, QFont, QIcon, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from batch_manager import GroupBatchManager
from config import BASE_DIR, PosterConfig
from gui.log_handler import LogEmitter, QtSignalingLogHandler
from gui.styles import DARK_THEME_QSS
from gui.worker import CampaignWorker, LoginWorker
from post_bundle import PostBundle, PostBundleLoader
from poster import FacebookGroupPoster, logger


class MainWindow(QMainWindow):
    """Primary application window."""

    def __init__(self, config: Optional[PosterConfig] = None) -> None:
        super().__init__()
        self.config = config or PosterConfig()
        self.current_bundle: Optional[PostBundle] = None
        self.current_manager: Optional[GroupBatchManager] = None
        self.campaign_worker: Optional[CampaignWorker] = None
        self.login_worker: Optional[LoginWorker] = None

        self.setWindowTitle("Facebook Group Batch Poster - Control Panel")
        self.resize(1300, 850)
        self.setMinimumSize(1050, 700)
        self.setStyleSheet(DARK_THEME_QSS)

        # Setup logging interceptor
        self.log_emitter = LogEmitter(self)
        self.log_emitter.sig_log.connect(self._on_log_received)
        self.log_handler = QtSignalingLogHandler(self.log_emitter)
        self.log_handler.setLevel(logging.INFO)
        logging.getLogger().addHandler(self.log_handler)

        self._init_ui()
        self._load_bundle_directories()
        self._load_groups_file(self.config.groups_file)
        self._check_session_status()
        self._reload_history_table()

    def _init_ui(self) -> None:
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(16, 12, 16, 12)
        main_layout.setSpacing(10)

        # Top Header Bar
        main_layout.addWidget(self._create_header_bar())

        # Main Tab Widget
        self.tabs = QTabWidget()
        self.tab_campaign = QWidget()
        self.tab_history = QWidget()

        self._build_campaign_tab()
        self._build_history_tab()

        self.tabs.addTab(self.tab_campaign, "🚀 Campaña de Publicación")
        self.tabs.addTab(self.tab_history, "📜 Historial y Auditoría")

        main_layout.addWidget(self.tabs, stretch=1)

    # -------------------------------------------------------------------------
    # Header Bar
    # -------------------------------------------------------------------------
    def _create_header_bar(self) -> QWidget:
        header = QFrame()
        header.setStyleSheet("background-color: #181B20; border-radius: 8px; padding: 4px;")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(12, 8, 12, 8)

        # Title & subtitle
        title_box = QVBoxLayout()
        title_label = QLabel("Facebook Group Batch Poster")
        title_label.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #FFFFFF;")
        subtitle_label = QLabel("Publicación automatizada por tandas con cadencia humana y control de sesión")
        subtitle_label.setStyleSheet("color: #7D8B9B; font-size: 11px;")
        title_box.addWidget(title_label)
        title_box.addWidget(subtitle_label)
        layout.addLayout(title_box)

        layout.addStretch()

        # Session Status Badge
        self.lbl_session_status = QLabel("● Verificando sesión...")
        self.lbl_session_status.setStyleSheet("color: #F2C94C; font-weight: bold; padding: 6px 12px;")
        layout.addWidget(self.lbl_session_status)

        # Login button
        self.btn_login = QPushButton("🔑 Iniciar Sesión en Facebook")
        self.btn_login.setObjectName("btn_login")
        self.btn_login.clicked.connect(self._on_login_clicked)
        layout.addWidget(self.btn_login)

        return header

    # -------------------------------------------------------------------------
    # Tab 1: Campaign View
    # -------------------------------------------------------------------------
    def _build_campaign_tab(self) -> None:
        layout = QHBoxLayout(self.tab_campaign)
        layout.setContentsMargins(6, 10, 6, 6)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._create_left_panel())
        splitter.addWidget(self._create_right_panel())
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 6)

        layout.addWidget(splitter)

    def _create_left_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(12)

        # --- 1. Content Bundle Card ---
        grp_content = QGroupBox("📁 Contenido de Publicación (Post Bundle)")
        content_layout = QVBoxLayout(grp_content)
        content_layout.setSpacing(8)

        # Folder selector row
        folder_row = QHBoxLayout()
        self.combo_bundles = QComboBox()
        self.combo_bundles.currentIndexChanged.connect(self._on_bundle_selected)
        folder_row.addWidget(self.combo_bundles, stretch=1)

        btn_browse_bundle = QPushButton("Examinar...")
        btn_browse_bundle.clicked.connect(self._on_browse_bundle)
        folder_row.addWidget(btn_browse_bundle)
        content_layout.addLayout(folder_row)

        # Post text preview
        content_layout.addWidget(QLabel("Texto del mensaje (post_content.txt):"))
        self.txt_content_preview = QTextEdit()
        self.txt_content_preview.setPlaceholderText("El texto cargado del bundle aparecerá aquí...")
        self.txt_content_preview.setMaximumHeight(130)
        content_layout.addWidget(self.txt_content_preview)

        # Attached Media summary label
        self.lbl_media_summary = QLabel("Archivos multimedia: Ninguno")
        self.lbl_media_summary.setStyleSheet("color: #4DA2FF; font-weight: 500;")
        content_layout.addWidget(self.lbl_media_summary)

        layout.addWidget(grp_content)

        # --- 2. Campaign Parameters Card ---
        grp_params = QGroupBox("⚙️ Parámetros de Envío")
        params_layout = QVBoxLayout(grp_params)
        params_layout.setSpacing(8)

        # Batch Size and Cooldown
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Tamaño de tanda:"))
        self.spin_batch_size = QSpinBox()
        self.spin_batch_size.setRange(1, 100)
        self.spin_batch_size.setValue(self.config.batch_size)
        row1.addWidget(self.spin_batch_size)

        row1.addWidget(QLabel("Cooldown (segundos):"))
        self.spin_cooldown = QSpinBox()
        self.spin_cooldown.setRange(5, 7200)
        self.spin_cooldown.setValue(self.config.batch_cooldown)
        self.spin_cooldown.setToolTip("Pausa anti-bloqueo entre cada tanda de grupos")
        row1.addWidget(self.spin_cooldown)
        params_layout.addLayout(row1)

        # Delays
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Pausa mín (s):"))
        self.spin_min_delay = QSpinBox()
        self.spin_min_delay.setRange(5, 300)
        self.spin_min_delay.setValue(self.config.min_post_delay)
        row2.addWidget(self.spin_min_delay)

        row2.addWidget(QLabel("Pausa máx (s):"))
        self.spin_max_delay = QSpinBox()
        self.spin_max_delay.setRange(5, 600)
        self.spin_max_delay.setValue(self.config.max_post_delay)
        row2.addWidget(self.spin_max_delay)
        params_layout.addLayout(row2)

        # Checkboxes
        self.chk_dry_run = QCheckBox("Modo Simulación (Dry-Run: no presiona Publicar)")
        self.chk_dry_run.setStyleSheet("color: #F2C94C; font-weight: 500;")
        params_layout.addWidget(self.chk_dry_run)

        self.chk_headless = QCheckBox("Ocultar navegador (Headless background)")
        self.chk_headless.setChecked(self.config.headless)
        params_layout.addWidget(self.chk_headless)

        self.chk_ignore_history = QCheckBox("Ignorar historial (Volver a publicar en todos)")
        params_layout.addWidget(self.chk_ignore_history)

        layout.addWidget(grp_params)

        # --- 3. Action Buttons ---
        grp_actions = QGroupBox("🎮 Controles de Ejecución")
        actions_layout = QVBoxLayout(grp_actions)
        actions_layout.setSpacing(10)

        self.btn_start = QPushButton("▶ Iniciar Campaña")
        self.btn_start.setObjectName("btn_start")
        self.btn_start.clicked.connect(self._on_start_campaign)
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
        layout.addStretch()

        return panel

    def _create_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 0, 0, 0)
        layout.setSpacing(10)

        # --- 1. Target Groups Section ---
        grp_groups = QGroupBox("👥 Grupos de Facebook")
        groups_layout = QVBoxLayout(grp_groups)
        groups_layout.setSpacing(8)

        # File selector and mass-selection buttons
        top_row = QHBoxLayout()
        self.lbl_groups_file = QLabel(f"Archivo: {self.config.groups_file.name}")
        self.lbl_groups_file.setStyleSheet("color: #88B7FF; font-weight: bold;")
        top_row.addWidget(self.lbl_groups_file)

        btn_browse_groups = QPushButton("Cambiar Archivo...")
        btn_browse_groups.clicked.connect(self._on_browse_groups_file)
        top_row.addWidget(btn_browse_groups)

        top_row.addStretch()

        btn_select_all = QPushButton("Seleccionar Todos")
        btn_select_all.clicked.connect(lambda: self._set_all_groups_checked(True))
        top_row.addWidget(btn_select_all)

        btn_deselect_all = QPushButton("Deseleccionar")
        btn_deselect_all.clicked.connect(lambda: self._set_all_groups_checked(False))
        top_row.addWidget(btn_deselect_all)

        groups_layout.addLayout(top_row)

        # Table of groups
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

        # --- 2. Live Progress Section ---
        grp_monitor = QGroupBox("📊 Monitor de Progreso en Vivo")
        monitor_layout = QVBoxLayout(grp_monitor)
        monitor_layout.setSpacing(6)

        self.lbl_status_message = QLabel("Listo para comenzar.")
        self.lbl_status_message.setStyleSheet("font-size: 13px; font-weight: bold; color: #FFFFFF;")
        monitor_layout.addWidget(self.lbl_status_message)

        # Progress bar for groups
        self.progress_groups = QProgressBar()
        self.progress_groups.setValue(0)
        self.progress_groups.setFormat("Grupos: %v / %m (%p%)")
        monitor_layout.addWidget(self.progress_groups)

        # Progress bar / Countdown for anti-bot & cooldown
        self.lbl_countdown = QLabel("Pausa: En espera...")
        self.lbl_countdown.setStyleSheet("color: #F2994A; font-weight: 500;")
        monitor_layout.addWidget(self.lbl_countdown)

        layout.addWidget(grp_monitor, stretch=2)

        # --- 3. Live Console Section ---
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
    # Tab 2: History View
    # -------------------------------------------------------------------------
    def _build_history_tab(self) -> None:
        layout = QVBoxLayout(self.tab_history)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        # Summary Metrics Row
        cards_layout = QHBoxLayout()
        self.card_total = self._create_metric_card("Total Procesados", "0", "#4DA2FF")
        self.card_success = self._create_metric_card("Exitosos", "0", "#27AE60")
        self.card_pending = self._create_metric_card("Aprobación Pendiente", "0", "#F2C94C")
        self.card_failed = self._create_metric_card("Fallidos / Bloqueados", "0", "#EB5757")

        cards_layout.addWidget(self.card_total)
        cards_layout.addWidget(self.card_success)
        cards_layout.addWidget(self.card_pending)
        cards_layout.addWidget(self.card_failed)
        layout.addLayout(cards_layout)

        # History Table Toolbar
        toolbar = QHBoxLayout()
        lbl_info = QLabel("Registro detallado de publicaciones guardadas en post_history.json")
        lbl_info.setStyleSheet("color: #7D8B9B; font-weight: 500;")
        toolbar.addWidget(lbl_info)
        toolbar.addStretch()

        btn_reload_history = QPushButton("🔄 Actualizar Historial")
        btn_reload_history.clicked.connect(self._reload_history_table)
        toolbar.addWidget(btn_reload_history)

        layout.addLayout(toolbar)

        # Table
        self.table_history = QTableWidget()
        self.table_history.setColumnCount(4)
        self.table_history.setHorizontalHeaderLabels(["URL del Grupo", "Estado", "Fecha / Hora", "Detalles"])
        self.table_history.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_history.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table_history.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table_history.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table_history, stretch=1)

    def _create_metric_card(self, title: str, value: str, color: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            f"background-color: #181B20; border: 1px solid #262B33; border-radius: 8px; padding: 10px;"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("color: #7D8B9B; font-size: 11px; font-weight: 600;")
        lbl_val = QLabel(value)
        lbl_val.setStyleSheet(f"color: {color}; font-size: 24px; font-weight: bold;")
        lbl_val.setObjectName(f"val_{title.lower().replace(' ', '_')}")
        layout.addWidget(lbl_title)
        layout.addWidget(lbl_val)
        return card

    # -------------------------------------------------------------------------
    # Content & Directory Management
    # -------------------------------------------------------------------------
    def _load_bundle_directories(self) -> None:
        """Scan project directory for folders containing post_content.txt."""
        self.combo_bundles.clear()
        found_dirs = []

        # Check BASE_DIR subdirectories
        for item in sorted(BASE_DIR.iterdir()):
            if item.is_dir() and not item.name.startswith(".") and item.name != "gui":
                if (item / "post_content.txt").exists():
                    found_dirs.append(item)

        # If base directory has post_content.txt directly
        if (BASE_DIR / "post_content.txt").exists() and BASE_DIR not in found_dirs:
            found_dirs.append(BASE_DIR)

        for d in found_dirs:
            label = d.name if d != BASE_DIR else "(Carpeta Raíz)"
            self.combo_bundles.addItem(label, userData=str(d))

        # Select configured default if present
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
        if not path_str:
            return
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

            # Summarize media
            images = [p.name for p in self.current_bundle.media_paths if p.suffix.lower() in loader.SUPPORTED_IMAGE_EXTENSIONS]
            videos = [p.name for p in self.current_bundle.media_paths if p.suffix.lower() in loader.SUPPORTED_VIDEO_EXTENSIONS]
            summary_parts = []
            if images:
                summary_parts.append(f"📷 {len(images)} foto(s)")
            if videos:
                summary_parts.append(f"🎥 {len(videos)} video(s)")
            
            if summary_parts:
                self.lbl_media_summary.setText("Multimedia adjunta: " + " | ".join(summary_parts))
            else:
                self.lbl_media_summary.setText("Multimedia adjunta: Solo texto (sin imágenes/videos)")
        except Exception as e:
            self.txt_content_preview.setPlainText("")
            self.lbl_media_summary.setText(f"❌ Error al cargar bundle: {e}")

    # -------------------------------------------------------------------------
    # Groups Table Management
    # -------------------------------------------------------------------------
    def _on_browse_groups_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar archivo de grupos", str(BASE_DIR), "Archivos de Texto (*.txt);;Todos (*.*)"
        )
        if file_path:
            self._load_groups_file(Path(file_path))

    def _load_groups_file(self, path: Path) -> None:
        if not path.exists():
            return

        self.current_groups_file = path
        self.lbl_groups_file.setText(f"Archivo: {path.name}")
        self.current_manager = GroupBatchManager(
            groups_file=path,
            history_file=self.config.history_file,
            batch_size=self.spin_batch_size.value(),
        )

        with open(path, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]

        self.table_groups.setRowCount(len(lines))
        for row_idx, url in enumerate(lines):
            # Checkbox item
            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk_item.setCheckState(Qt.CheckState.Checked)
            self.table_groups.setItem(row_idx, 0, chk_item)

            # URL item
            url_item = QTableWidgetItem(url)
            self.table_groups.setItem(row_idx, 1, url_item)

            # Initial status from history
            status_item = QTableWidgetItem()
            hist_entry = self.current_manager.history.get(url)
            if hist_entry:
                st = hist_entry.get("status", "")
                if st == "SUCCESS":
                    status_item.setText("✅ Publicado")
                    status_item.setForeground(QColor("#27AE60"))
                elif st == "PENDING_APPROVAL":
                    status_item.setText("🟡 Aprobación")
                    status_item.setForeground(QColor("#F2C94C"))
                elif st == "FAILED":
                    status_item.setText("❌ Falló")
                    status_item.setForeground(QColor("#EB5757"))
                else:
                    status_item.setText(st)
                details_text = hist_entry.get("details", "")
            else:
                status_item.setText("⏳ Pendiente")
                status_item.setForeground(QColor("#9AA7B5"))
                details_text = ""

            self.table_groups.setItem(row_idx, 2, status_item)
            self.table_groups.setItem(row_idx, 3, QTableWidgetItem(details_text))

        self.progress_groups.setMaximum(len(lines))
        self.progress_groups.setValue(0)

    def _set_all_groups_checked(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for row in range(self.table_groups.rowCount()):
            item = self.table_groups.item(row, 0)
            if item:
                item.setCheckState(state)

    def _get_selected_group_urls(self) -> List[str]:
        urls = []
        for row in range(self.table_groups.rowCount()):
            chk = self.table_groups.item(row, 0)
            url_item = self.table_groups.item(row, 1)
            if chk and chk.checkState() == Qt.CheckState.Checked and url_item:
                urls.append(url_item.text())
        return urls

    # -------------------------------------------------------------------------
    # Campaign Execution Controls
    # -------------------------------------------------------------------------
    def _on_start_campaign(self) -> None:
        selected_urls = self._get_selected_group_urls()
        if not selected_urls:
            QMessageBox.warning(
                self, "Sin grupos seleccionados", "Por favor marca al menos un grupo de la tabla para iniciar."
            )
            return

        if not self.current_bundle:
            QMessageBox.warning(
                self, "Sin contenido", "Carga o selecciona una carpeta válida con 'post_content.txt'."
            )
            return

        # Prepare UI states
        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_pause.setText("⏸ Pausar")
        self.btn_stop.setEnabled(True)
        self.btn_single_test.setEnabled(False)

        self.progress_groups.setMaximum(len(selected_urls))
        self.progress_groups.setValue(0)
        self.lbl_status_message.setText("Iniciando campaña...")

        # Worker initialization
        self.campaign_worker = CampaignWorker(
            config=self.config,
            manager=self.current_manager,
            bundle=self.current_bundle,
            groups=selected_urls,
            batch_size=self.spin_batch_size.value(),
            min_delay=self.spin_min_delay.value(),
            max_delay=self.spin_max_delay.value(),
            cooldown=self.spin_cooldown.value(),
            dry_run=self.chk_dry_run.isChecked(),
            ignore_history=self.chk_ignore_history.isChecked(),
            headless=self.chk_headless.isChecked(),
        )

        self.campaign_worker.sig_status.connect(self._on_worker_status)
        self.campaign_worker.sig_group_started.connect(self._on_group_started)
        self.campaign_worker.sig_group_finished.connect(self._on_group_finished)
        self.campaign_worker.sig_countdown.connect(self._on_countdown_tick)
        self.campaign_worker.sig_finished.connect(self._on_campaign_finished)
        self.campaign_worker.sig_error.connect(self._on_worker_error)

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
        """Run single group test on currently focused row."""
        selected_row = self.table_groups.currentRow()
        if selected_row < 0:
            QMessageBox.information(
                self, "Seleccionar fila", "Haz clic en una fila de la tabla para probar en ese grupo específico."
            )
            return

        url = self.table_groups.item(selected_row, 1).text()
        if not self.current_bundle:
            QMessageBox.warning(self, "Sin contenido", "Carga una carpeta de contenido válida primero.")
            return

        # Run single test using 1-element campaign worker
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
            dry_run=True,  # Safety default for single test button
            ignore_history=True,
            headless=False,  # Always visible for manual observation
        )
        self.campaign_worker.sig_status.connect(self._on_worker_status)
        self.campaign_worker.sig_group_finished.connect(self._on_group_finished)
        self.campaign_worker.sig_finished.connect(self._on_campaign_finished)
        self.campaign_worker.start()

    # -------------------------------------------------------------------------
    # Worker Signal Handlers
    # -------------------------------------------------------------------------
    def _on_worker_status(self, status_msg: str) -> None:
        self.lbl_status_message.setText(status_msg)

    def _on_group_started(self, url: str, current: int, total: int) -> None:
        self.progress_groups.setValue(current)
        self._update_table_row_status(url, "🚀 Publicando...", "#4DA2FF")

    def _on_group_finished(self, url: str, status: str, details: str) -> None:
        if status == "SUCCESS":
            self._update_table_row_status(url, "✅ Publicado", "#27AE60", details)
        elif status == "PENDING_APPROVAL":
            self._update_table_row_status(url, "🟡 Aprobación", "#F2C94C", details)
        elif status == "DRY_RUN":
            self._update_table_row_status(url, "🔍 Simulado", "#56CCF2", details)
        else:
            self._update_table_row_status(url, "❌ Falló", "#EB5757", details)
        self._reload_history_table()

    def _on_countdown_tick(self, label: str, seconds_left: int) -> None:
        if seconds_left > 0:
            mins, secs = divmod(seconds_left, 60)
            time_str = f"{mins:02d}:{secs:02d}" if mins > 0 else f"{secs}s"
            self.lbl_countdown.setText(f"⏳ {label}: {time_str} restantes...")
        else:
            self.lbl_countdown.setText("Pausa: Reanudando...")

    def _on_campaign_finished(self, stats: dict) -> None:
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_pause.setText("⏸ Pausar")
        self.btn_stop.setEnabled(False)
        self.btn_single_test.setEnabled(True)
        self.lbl_countdown.setText("Pausa: En espera...")
        self._reload_history_table()

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

    # -------------------------------------------------------------------------
    # Session & Authentication Handling
    # -------------------------------------------------------------------------
    def _check_session_status(self) -> None:
        """Check if user profile folder exists and contains Chrome data."""
        user_dir = self.config.user_data_dir
        if user_dir.exists() and any(user_dir.iterdir()):
            self.lbl_session_status.setText("● Perfil de Chrome Detectado")
            self.lbl_session_status.setStyleSheet("color: #27AE60; font-weight: bold; padding: 6px 12px;")
        else:
            self.lbl_session_status.setText("● Sesión no detectada")
            self.lbl_session_status.setStyleSheet("color: #EB5757; font-weight: bold; padding: 6px 12px;")

    def _on_login_clicked(self) -> None:
        reply = QMessageBox.question(
            self,
            "Iniciar Sesión",
            "Se abrirá una ventana de Google Chrome nativa.\n"
            "Inicia sesión en tu cuenta de Facebook y, cuando termines de entrar a tu muro, cierra el navegador.\n\n"
            "¿Deseas abrir la ventana ahora?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.btn_login.setEnabled(False)
        self.lbl_session_status.setText("● Abriendo navegador...")
        self.lbl_session_status.setStyleSheet("color: #4DA2FF; font-weight: bold; padding: 6px 12px;")

        self.login_worker = LoginWorker(self.config)
        self.login_worker.sig_finished.connect(self._on_login_worker_finished)
        self.login_worker.start()

    def _on_login_worker_finished(self, success: bool, message: str) -> None:
        self.btn_login.setEnabled(True)
        self._check_session_status()
        if success:
            QMessageBox.information(self, "Sesión", message)
        else:
            QMessageBox.warning(self, "Error de Sesión", message)

    # -------------------------------------------------------------------------
    # History Tab Management
    # -------------------------------------------------------------------------
    def _reload_history_table(self) -> None:
        history_file = self.config.history_file
        if not history_file.exists():
            return

        try:
            with open(history_file, "r", encoding="utf-8") as f:
                history_data: Dict[str, dict] = json.load(f)
        except Exception:
            return

        # Update cards
        total = len(history_data)
        success = sum(1 for v in history_data.values() if v.get("status") == "SUCCESS")
        pending = sum(1 for v in history_data.values() if v.get("status") == "PENDING_APPROVAL")
        failed = sum(1 for v in history_data.values() if v.get("status") in ("FAILED", "BLOCKED"))

        card_total_lbl = self.card_total.findChild(QLabel, "val_total_procesados")
        if card_total_lbl:
            card_total_lbl.setText(str(total))

        card_succ_lbl = self.card_success.findChild(QLabel, "val_exitosos")
        if card_succ_lbl:
            card_succ_lbl.setText(str(success))

        card_pend_lbl = self.card_pending.findChild(QLabel, "val_aprobación_pendiente")
        if card_pend_lbl:
            card_pend_lbl.setText(str(pending))

        card_fail_lbl = self.card_failed.findChild(QLabel, "val_fallidos_/_bloqueados")
        if card_fail_lbl:
            card_fail_lbl.setText(str(failed))

        # Fill table
        self.table_history.setRowCount(total)
        for row_idx, (url, info) in enumerate(sorted(history_data.items(), key=lambda x: x[1].get("timestamp", ""), reverse=True)):
            self.table_history.setItem(row_idx, 0, QTableWidgetItem(url))

            status_str = info.get("status", "")
            st_item = QTableWidgetItem(status_str)
            if status_str == "SUCCESS":
                st_item.setForeground(QColor("#27AE60"))
            elif status_str == "PENDING_APPROVAL":
                st_item.setForeground(QColor("#F2C94C"))
            elif status_str in ("FAILED", "BLOCKED"):
                st_item.setForeground(QColor("#EB5757"))
            self.table_history.setItem(row_idx, 1, st_item)

            ts = info.get("timestamp", "")
            self.table_history.setItem(row_idx, 2, QTableWidgetItem(ts[:19].replace("T", " ")))
            self.table_history.setItem(row_idx, 3, QTableWidgetItem(info.get("details", "")))

    # -------------------------------------------------------------------------
    # Logging Console
    # -------------------------------------------------------------------------
    def _on_log_received(self, timestamp: str, level: str, msg: str) -> None:
        color = "#E1E7EC"
        if level == "WARNING":
            color = "#F2C94C"
        elif level in ("ERROR", "CRITICAL"):
            color = "#EB5757"
        elif "exitos" in msg.lower() or "success" in msg.lower():
            color = "#27AE60"

        html_line = f"<span style='color: #7D8B9B;'>[{timestamp}]</span> <span style='color: {color};'><b>[{level}]</b> {msg}</span>"
        self.txt_console.appendHtml(html_line)
        self.txt_console.moveCursor(QTextCursor.MoveOperation.End)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Detach log handler and stop active workers cleanly on window close."""
        logging.getLogger().removeHandler(self.log_handler)
        self.log_handler.close()
        if self.campaign_worker and self.campaign_worker.isRunning():
            self.campaign_worker.stop()
            self.campaign_worker.wait(3000)
        super().closeEvent(event)

