"""Logging handler that emits Qt signals for UI console updates."""

from __future__ import annotations

import logging
from datetime import datetime
from PySide6.QtCore import QObject, Signal


class LogEmitter(QObject):
    """QObject helper to emit log signals across threads."""

    sig_log = Signal(str, str, str)  # timestamp, level, message


class QtSignalingLogHandler(logging.Handler):
    """Custom logging handler forwarding log events to a Qt signal."""

    def __init__(self, emitter: LogEmitter) -> None:
        super().__init__()
        self.emitter = emitter

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            level = record.levelname
            timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
            self.emitter.sig_log.emit(timestamp, level, msg)
        except Exception:
            self.handleError(record)
