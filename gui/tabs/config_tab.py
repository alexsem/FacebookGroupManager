"""Configuration tab widget and RunOptions dataclass."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from config import PosterConfig


@dataclass(frozen=True)
class RunOptions:
    """Snapshot of campaign execution parameters configured in the UI."""

    batch_size: int
    min_delay: int
    max_delay: int
    cooldown: int
    dry_run: bool
    headless: bool
    ignore_history: bool


class ConfigTab(QWidget):
    """Tab 3: Sending cadence, batch size, and browser behavior settings."""

    sig_options_changed = Signal(object)  # RunOptions
    sig_done_requested = Signal()

    def __init__(self, config: PosterConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        grp_params = QGroupBox("⚙️ Parámetros de Envío y Comportamiento")
        grp_params.setMaximumWidth(700)
        params_layout = QVBoxLayout(grp_params)
        params_layout.setSpacing(16)

        form_layout = QFormLayout()
        form_layout.setSpacing(12)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.spin_batch_size = QSpinBox()
        self.spin_batch_size.setRange(1, 100)
        self.spin_batch_size.setValue(self.config.batch_size)
        self.spin_batch_size.setMinimumWidth(140)
        self.spin_batch_size.valueChanged.connect(self._emit_options_changed)
        form_layout.addRow("Tamaño de tanda (grupos por lote):", self.spin_batch_size)

        self.spin_cooldown = QSpinBox()
        self.spin_cooldown.setRange(5, 7200)
        self.spin_cooldown.setValue(self.config.batch_cooldown)
        self.spin_cooldown.setMinimumWidth(140)
        self.spin_cooldown.setToolTip("Pausa anti-bloqueo entre cada tanda de grupos")
        self.spin_cooldown.valueChanged.connect(self._emit_options_changed)
        form_layout.addRow("Cooldown entre tandas (segundos):", self.spin_cooldown)

        self.spin_min_delay = QSpinBox()
        self.spin_min_delay.setRange(5, 300)
        self.spin_min_delay.setValue(self.config.min_post_delay)
        self.spin_min_delay.setMinimumWidth(140)
        self.spin_min_delay.valueChanged.connect(self._emit_options_changed)
        form_layout.addRow("Pausa mínima entre grupos (segundos):", self.spin_min_delay)

        self.spin_max_delay = QSpinBox()
        self.spin_max_delay.setRange(5, 600)
        self.spin_max_delay.setValue(self.config.max_post_delay)
        self.spin_max_delay.setMinimumWidth(140)
        self.spin_max_delay.valueChanged.connect(self._emit_options_changed)
        form_layout.addRow("Pausa máxima entre grupos (segundos):", self.spin_max_delay)

        params_layout.addLayout(form_layout)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #262B33; max-height: 1px;")
        params_layout.addWidget(line)

        self.chk_dry_run = QCheckBox(
            "Modo Simulación (Dry-Run: llena el post pero no presiona Publicar)"
        )
        self.chk_dry_run.setStyleSheet("color: #F2C94C; font-weight: 500;")
        self.chk_dry_run.toggled.connect(self._emit_options_changed)
        params_layout.addWidget(self.chk_dry_run)

        self.chk_headless = QCheckBox(
            "Ocultar navegador (Ejecutar Chrome en segundo plano / Headless)"
        )
        self.chk_headless.setChecked(self.config.headless)
        self.chk_headless.toggled.connect(self._emit_options_changed)
        params_layout.addWidget(self.chk_headless)

        self.chk_ignore_history = QCheckBox(
            "Ignorar historial previo (Volver a publicar en todos los grupos marcados)"
        )
        self.chk_ignore_history.toggled.connect(self._emit_options_changed)
        params_layout.addWidget(self.chk_ignore_history)

        btn_row = QHBoxLayout()
        btn_reset = QPushButton("↺ Restaurar Valores por Defecto")
        btn_reset.clicked.connect(self.reset_defaults)
        btn_row.addWidget(btn_reset)
        btn_row.addStretch()

        btn_back = QPushButton("✔ Listo (Volver a Campaña)")
        btn_back.setObjectName("btn_login")
        btn_back.clicked.connect(self.sig_done_requested.emit)
        btn_row.addWidget(btn_back)
        params_layout.addLayout(btn_row)

        layout.addWidget(grp_params)
        layout.addStretch()

    def get_run_options(self) -> RunOptions:
        """Return current execution parameters as an immutable snapshot."""
        return RunOptions(
            batch_size=self.spin_batch_size.value(),
            min_delay=self.spin_min_delay.value(),
            max_delay=self.spin_max_delay.value(),
            cooldown=self.spin_cooldown.value(),
            dry_run=self.chk_dry_run.isChecked(),
            headless=self.chk_headless.isChecked(),
            ignore_history=self.chk_ignore_history.isChecked(),
        )

    def reset_defaults(self) -> None:
        """Restore all parameter widgets to PosterConfig defaults."""
        self.spin_batch_size.setValue(self.config.batch_size)
        self.spin_cooldown.setValue(self.config.batch_cooldown)
        self.spin_min_delay.setValue(self.config.min_post_delay)
        self.spin_max_delay.setValue(self.config.max_post_delay)
        self.chk_dry_run.setChecked(False)
        self.chk_headless.setChecked(self.config.headless)
        self.chk_ignore_history.setChecked(False)
        self._emit_options_changed()

    def _emit_options_changed(self) -> None:
        self.sig_options_changed.emit(self.get_run_options())

