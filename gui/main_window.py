"""Main window shell for Facebook Group Batch Poster in PySide6."""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtGui import QAction, QCloseEvent, QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from config import PosterConfig
from gui.log_handler import LogEmitter, QtSignalingLogHandler
from gui.styles import DARK_THEME_QSS
from gui.tabs import CampaignTab, CampaignsPostsTab, ConfigTab, HistoryTab
from gui.worker import LoginWorker
from storage import DatabaseManager, GroupRepository, LegacyMigrator


class MainWindow(QMainWindow):
    """Lightweight application shell coordinating menus, session status, and tabs."""

    def __init__(self, config: Optional[PosterConfig] = None) -> None:
        super().__init__()
        self.config = config or PosterConfig()
        self.db_manager = DatabaseManager(self.config.db_path)
        LegacyMigrator.migrate_if_needed(
            self.db_manager,
            groups_file=self.config.groups_file,
            history_file=self.config.history_file,
        )
        if self.config.groups_file.exists():
            GroupRepository(self.db_manager).import_from_txt(self.config.groups_file)

        self.login_worker: Optional[LoginWorker] = None

        self.setWindowTitle("Facebook Group Batch Poster - Control Panel")
        self.resize(1300, 850)
        self.setMinimumSize(1050, 700)
        self.setStyleSheet(DARK_THEME_QSS)

        self._init_ui()
        self._setup_logging()
        self._check_session_status()
        self.tab_history.refresh()
        self.tab_campaigns_posts.refresh()

    def _setup_logging(self) -> None:
        self.log_emitter = LogEmitter(self)
        self.log_emitter.sig_log.connect(self.tab_campaign.append_log)
        self.log_handler = QtSignalingLogHandler(self.log_emitter)
        self.log_handler.setLevel(logging.INFO)
        logging.getLogger().addHandler(self.log_handler)

    def _init_ui(self) -> None:
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(16, 12, 16, 12)
        main_layout.setSpacing(10)

        main_layout.addWidget(self._create_header_bar())

        self.tabs = QTabWidget()
        self.tab_config = ConfigTab(self.config)
        self.tab_campaign = CampaignTab(
            config=self.config,
            db_manager=self.db_manager,
            run_options_provider=self.tab_config.get_run_options,
        )
        self.tab_history = HistoryTab(config=self.config, db_manager=self.db_manager)
        self.tab_campaigns_posts = CampaignsPostsTab(db_manager=self.db_manager)

        self.tabs.addTab(self.tab_campaign, "🚀 Campaña de Publicación")
        self.tabs.addTab(self.tab_history, "📜 Historial y Auditoría")
        self.tabs.addTab(self.tab_config, "⚙️ Configuración")
        self.tabs.addTab(self.tab_campaigns_posts, "📌 Posts por Campaña")

        main_layout.addWidget(self.tabs, stretch=1)

        self._connect_tab_signals()
        self._create_menu_bar()

    def _connect_tab_signals(self) -> None:
        self.tab_config.sig_options_changed.connect(self.tab_campaign.update_config_summary)
        self.tab_config.sig_done_requested.connect(
            lambda: self.tabs.setCurrentWidget(self.tab_campaign)
        )
        self.tab_campaign.sig_edit_config_requested.connect(
            lambda: self.tabs.setCurrentWidget(self.tab_config)
        )
        self.tab_campaign.sig_data_changed.connect(self._on_campaign_data_changed)
        self.tab_campaign.sig_campaign_finished.connect(self._on_campaign_data_changed)
        self.tab_campaigns_posts.sig_campaign_activated.connect(self._on_campaign_activated)
        self.tab_campaigns_posts.sig_status_message.connect(self.tab_campaign.set_status_message)

    def _on_campaign_data_changed(self) -> None:
        self.tab_history.refresh()
        self.tab_campaigns_posts.refresh()

    def _on_campaign_activated(self, campaign_id: int) -> None:
        self.tab_campaign.load_groups_from_db(campaign_id=campaign_id)
        self.tab_history.refresh()

    def _create_menu_bar(self) -> None:
        menubar = self.menuBar()

        menu_file = menubar.addMenu("Archivo")
        act_reload_bundles = QAction("🔄 Recargar Carpetas de Contenido", self)
        act_reload_bundles.triggered.connect(self.tab_campaign.load_bundle_directories)
        menu_file.addAction(act_reload_bundles)

        act_change_groups = QAction("📂 Importar Archivo de Grupos (.txt)...", self)
        act_change_groups.triggered.connect(self.tab_campaign.import_groups_dialog)
        menu_file.addAction(act_change_groups)

        menu_file.addSeparator()
        act_exit = QAction("Salir", self)
        act_exit.triggered.connect(self.close)
        menu_file.addAction(act_exit)

        menu_config = menubar.addMenu("Configuración")
        act_params = QAction("⚙️ Parámetros de Envío", self)
        act_params.triggered.connect(lambda: self.tabs.setCurrentWidget(self.tab_config))
        menu_config.addAction(act_params)

        act_reset = QAction("↺ Restaurar Valores por Defecto", self)
        act_reset.triggered.connect(self.tab_config.reset_defaults)
        menu_config.addAction(act_reset)

        menu_session = menubar.addMenu("Sesión")
        act_login = QAction("🔑 Iniciar Sesión en Facebook", self)
        act_login.triggered.connect(self._on_login_clicked)
        menu_session.addAction(act_login)

    def _create_header_bar(self) -> QWidget:
        header = QFrame()
        header.setStyleSheet("background-color: #181B20; border-radius: 8px; padding: 4px;")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(12, 8, 12, 8)

        title_box = QVBoxLayout()
        title_label = QLabel("Facebook Group Batch Poster")
        title_label.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #FFFFFF;")
        subtitle_label = QLabel(
            "Publicación automatizada por tandas con cadencia humana y control de sesión"
        )
        subtitle_label.setStyleSheet("color: #7D8B9B; font-size: 11px;")
        title_box.addWidget(title_label)
        title_box.addWidget(subtitle_label)
        layout.addLayout(title_box)
        layout.addStretch()

        self.lbl_session_status = QLabel("● Verificando sesión...")
        self.lbl_session_status.setStyleSheet(
            "color: #F2C94C; font-weight: bold; padding: 6px 12px;"
        )
        layout.addWidget(self.lbl_session_status)

        self.btn_login = QPushButton("🔑 Iniciar Sesión en Facebook")
        self.btn_login.setObjectName("btn_login")
        self.btn_login.clicked.connect(self._on_login_clicked)
        layout.addWidget(self.btn_login)

        return header

    def _check_session_status(self) -> None:
        user_dir = self.config.user_data_dir
        if user_dir.exists() and any(user_dir.iterdir()):
            self.lbl_session_status.setText("● Perfil de Chrome Detectado")
            self.lbl_session_status.setStyleSheet(
                "color: #27AE60; font-weight: bold; padding: 6px 12px;"
            )
        else:
            self.lbl_session_status.setText("● Sesión no detectada")
            self.lbl_session_status.setStyleSheet(
                "color: #EB5757; font-weight: bold; padding: 6px 12px;"
            )

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
        self.lbl_session_status.setStyleSheet(
            "color: #4DA2FF; font-weight: bold; padding: 6px 12px;"
        )

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

    def closeEvent(self, event: QCloseEvent) -> None:
        """Detach log handler, stop active workers, and close SQLite cleanly."""
        logging.getLogger().removeHandler(self.log_handler)
        self.log_handler.close()
        self.tab_campaign.stop_worker_on_close()
        self.db_manager.close()
        super().closeEvent(event)
