"""Modern dark styling and CSS definitions for PySide6 interface."""

DARK_THEME_QSS = """
QMainWindow {
    background-color: #121417;
    color: #E1E7EC;
    font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
    font-size: 13px;
}

QWidget {
    background-color: transparent;
    color: #E1E7EC;
    selection-background-color: #2D68C4;
    selection-color: #FFFFFF;
}

/* Menu Bar */
QMenuBar {
    background-color: #181B20;
    color: #E1E7EC;
    border-bottom: 1px solid #262B33;
    padding: 4px 8px;
}

QMenuBar::item {
    background-color: transparent;
    padding: 6px 12px;
    border-radius: 4px;
}

QMenuBar::item:selected {
    background-color: #242932;
    color: #4DA2FF;
}

QMenu {
    background-color: #181B20;
    border: 1px solid #2B313B;
    border-radius: 6px;
    padding: 4px;
    color: #E1E7EC;
}

QMenu::item {
    padding: 7px 24px 7px 14px;
    border-radius: 4px;
}

QMenu::item:selected {
    background-color: #2D68C4;
    color: #FFFFFF;
}

QMenu::separator {
    height: 1px;
    background-color: #262B33;
    margin: 4px 8px;
}

/* Tab Bar */
QTabWidget::pane {
    border: 1px solid #262B33;
    background-color: #181B20;
    border-radius: 8px;
    top: -1px;
}

QTabBar::tab {
    background-color: #1B1E24;
    color: #9AA7B5;
    padding: 10px 24px;
    margin-right: 4px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: 600;
}

QTabBar::tab:selected {
    background-color: #181B20;
    color: #4DA2FF;
    border-bottom: 2px solid #4DA2FF;
}

QTabBar::tab:hover:!selected {
    background-color: #242932;
    color: #E1E7EC;
}

/* Group Boxes / Cards */
QGroupBox {
    background-color: #181B20;
    border: 1px solid #262B33;
    border-radius: 8px;
    margin-top: 24px;
    padding-top: 18px;
    padding-left: 14px;
    padding-right: 14px;
    padding-bottom: 14px;
    font-weight: 600;
    color: #88B7FF;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    padding: 0 6px;
    background-color: #181B20;
}

/* Input Fields & Spinners */
QLineEdit, QSpinBox, QComboBox, QTextEdit, QPlainTextEdit {
    background-color: #0E1013;
    border: 1px solid #2B313B;
    border-radius: 6px;
    padding: 6px 10px;
    color: #F0F4F8;
    selection-background-color: #2D68C4;
}

QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #4DA2FF;
}

QSpinBox::up-button, QSpinBox::down-button {
    background-color: #1E232B;
    border-radius: 3px;
    width: 18px;
}

QSpinBox::up-button:hover, QSpinBox::down-button:hover {
    background-color: #2B323D;
}

/* Push Buttons */
QPushButton {
    background-color: #232832;
    border: 1px solid #323A48;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 600;
    color: #E1E7EC;
}

QPushButton:hover {
    background-color: #2E3543;
    border-color: #4B566B;
}

QPushButton:pressed {
    background-color: #1C2028;
}

QPushButton:disabled {
    background-color: #16181D;
    border-color: #22262E;
    color: #555E6B;
}

/* Primary Action Buttons */
QPushButton#btn_start {
    background-color: #107C41;
    border: 1px solid #169E53;
    color: #FFFFFF;
    font-size: 14px;
    padding: 10px 18px;
}

QPushButton#btn_start:hover {
    background-color: #169E53;
}

QPushButton#btn_pause {
    background-color: #B26A00;
    border: 1px solid #D68100;
    color: #FFFFFF;
}

QPushButton#btn_pause:hover {
    background-color: #D68100;
}

QPushButton#btn_stop {
    background-color: #A31C1C;
    border: 1px solid #C42B2B;
    color: #FFFFFF;
}

QPushButton#btn_stop:hover {
    background-color: #C42B2B;
}

QPushButton#btn_login {
    background-color: #1877F2;
    border: 1px solid #3B8AF5;
    color: #FFFFFF;
    font-weight: bold;
}

QPushButton#btn_login:hover {
    background-color: #3B8AF5;
}

/* Tables */
QTableWidget {
    background-color: #0E1013;
    border: 1px solid #262B33;
    border-radius: 6px;
    gridline-color: #1E232B;
    color: #E1E7EC;
}

QHeaderView::section {
    background-color: #1B1E24;
    color: #9AA7B5;
    padding: 8px 10px;
    border: none;
    border-right: 1px solid #262B33;
    border-bottom: 1px solid #262B33;
    font-weight: 600;
}

QTableWidget::item {
    padding: 6px;
    border-bottom: 1px solid #16191E;
}

QTableWidget::item:selected {
    background-color: #1E2E48;
}

/* Progress Bars */
QProgressBar {
    background-color: #0E1013;
    border: 1px solid #262B33;
    border-radius: 6px;
    text-align: center;
    color: #FFFFFF;
    font-weight: bold;
    height: 20px;
}

QProgressBar::chunk {
    background-color: #1A73E8;
    border-radius: 5px;
}

QProgressBar#progress_cooldown::chunk {
    background-color: #F2994A;
}

/* Checkboxes */
QCheckBox {
    spacing: 8px;
    color: #E1E7EC;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 1px solid #3A4352;
    border-radius: 4px;
    background-color: #0E1013;
}

QCheckBox::indicator:checked {
    background-color: #1877F2;
    border-color: #4DA2FF;
}

/* Scrollbars */
QScrollBar:vertical {
    background: #121417;
    width: 10px;
    margin: 0px;
    border-radius: 5px;
}

QScrollBar::handle:vertical {
    background: #2B313B;
    min-height: 20px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background: #3E4654;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""

