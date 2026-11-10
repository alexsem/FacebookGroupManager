"""Background workers for running Playwright automation inside QThread."""

from __future__ import annotations

import logging
import random
import time
from pathlib import Path
from threading import Event
from typing import List, Optional

from PySide6.QtCore import QThread, Signal

from batch_manager import GroupBatchManager
from config import PosterConfig
from post_bundle import PostBundle
from poster import FacebookGroupPoster, logger


class LoginWorker(QThread):
    """Worker to launch visible Chrome for manual Facebook login."""

    sig_finished = Signal(bool, str)

    def __init__(self, config: PosterConfig, parent=None) -> None:
        super().__init__(parent)
        self.config = config

    def run(self) -> None:
        poster = FacebookGroupPoster(self.config)
        try:
            logger.info("Iniciando ventana para inicio de sesión en Facebook...")
            poster.run_login_flow()
            self.sig_finished.emit(True, "Inicio de sesión completado o verificado.")
        except Exception as e:
            logger.error(f"Error en flujo de login: {e}")
            self.sig_finished.emit(False, str(e))


class CampaignWorker(QThread):
    """Worker executing batch posting campaign with pause/resume/stop controls."""

    sig_log = Signal(str, str)  # level, message
    sig_status = Signal(str)
    sig_group_started = Signal(str, int, int)  # url, current_1_based, total
    sig_group_finished = Signal(str, str, str)  # url, status, details
    sig_batch_completed = Signal(int, int)  # batch_num, total_batches
    sig_countdown = Signal(str, int)  # label, seconds_left
    sig_finished = Signal(dict)  # final stats
    sig_error = Signal(str)

    def __init__(
        self,
        config: PosterConfig,
        manager: GroupBatchManager,
        bundle: PostBundle,
        groups: List[str],
        batch_size: int,
        min_delay: int,
        max_delay: int,
        cooldown: int,
        dry_run: bool,
        ignore_history: bool,
        headless: bool,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.manager = manager
        self.bundle = bundle
        self.groups = groups
        self.batch_size = max(1, batch_size)
        self.min_delay = max(5, min_delay)
        self.max_delay = max(self.min_delay, max_delay)
        self.cooldown = max(5, cooldown)
        self.dry_run = dry_run
        self.ignore_history = ignore_history
        self.headless = headless

        self._stop_event = Event()
        self._pause_event = Event()
        self._pause_event.set()  # Not paused initially

    def pause(self) -> None:
        """Pause campaign execution."""
        self._pause_event.clear()
        self.sig_status.emit("Campaña pausada por el usuario.")

    def resume(self) -> None:
        """Resume campaign execution."""
        self._pause_event.set()
        self.sig_status.emit("Campaña reanudada.")

    def stop(self) -> None:
        """Request cooperative stop."""
        self._stop_event.set()
        self._pause_event.set()  # Unpause so loop can exit immediately
        self.sig_status.emit("Detención solicitada...")

    @property
    def is_paused(self) -> bool:
        return not self._pause_event.is_set()

    def _sleep_interruptible(self, seconds: float, label: str) -> bool:
        """Sleep in small steps while reporting countdown and checking stop/pause.
        
        Returns True if sleep completed normally, False if interrupted by stop.
        """
        remaining = int(seconds)
        while remaining > 0:
            if self._stop_event.is_set():
                return False

            # Wait if paused
            while not self._pause_event.is_set():
                if self._stop_event.is_set():
                    return False
                time.sleep(0.5)

            self.sig_countdown.emit(label, remaining)
            sleep_step = min(1.0, float(remaining))
            time.sleep(sleep_step)
            remaining -= 1

        self.sig_countdown.emit(label, 0)
        return True

    def run(self) -> None:
        """Execute the campaign workflow."""
        # Filter groups to process
        groups_to_process: List[str] = []
        for g in self.groups:
            cleaned = g.strip()
            if not cleaned or cleaned.startswith("#"):
                continue
            if self.ignore_history or self.dry_run or not self.manager.is_processed(cleaned):
                groups_to_process.append(cleaned)

        total_groups = len(groups_to_process)
        if total_groups == 0:
            self.sig_status.emit("No hay grupos pendientes para procesar.")
            self.sig_finished.emit(self.manager.get_stats())
            return

        # Prepare customized config with worker runtime parameters
        custom_config = PosterConfig(
            user_data_dir=self.config.user_data_dir,
            groups_file=self.config.groups_file,
            post_dir=self.config.post_dir,
            post_file=self.config.post_file,
            history_file=self.config.history_file,
            image_path=self.config.image_path,
            batch_size=self.batch_size,
            min_post_delay=self.min_delay,
            max_post_delay=self.max_delay,
            batch_cooldown=self.cooldown,
            headless=self.headless,
            viewport_width=self.config.viewport_width,
            viewport_height=self.config.viewport_height,
            human_typing=self.config.human_typing,
        )

        poster = FacebookGroupPoster(custom_config)

        try:
            self.sig_status.emit("Iniciando navegador Playwright...")
            poster.start_session()
            assert poster.page is not None

            # Verify login status
            self.sig_status.emit("Verificando autenticación en Facebook...")
            poster.page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
            time.sleep(3.0)

            if not poster.is_logged_in():
                err_msg = "No hay sesión activa de Facebook. Usa el botón 'Iniciar Sesión' primero."
                self.sig_error.emit(err_msg)
                self.sig_status.emit(err_msg)
                return

            # Partition into batches
            batches: List[List[str]] = [
                groups_to_process[i : i + self.batch_size]
                for i in range(0, total_groups, self.batch_size)
            ]
            total_batches = len(batches)

            processed_count = 0

            for batch_idx, batch in enumerate(batches, start=1):
                if self._stop_event.is_set():
                    break

                self.sig_status.emit(
                    f"Iniciando Tanda {batch_idx}/{total_batches} ({len(batch)} grupos)"
                )

                for item_idx, group_url in enumerate(batch, start=1):
                    # Check pause
                    while not self._pause_event.is_set():
                        if self._stop_event.is_set():
                            break
                        time.sleep(0.5)

                    if self._stop_event.is_set():
                        break

                    processed_count += 1
                    self.sig_group_started.emit(group_url, processed_count, total_groups)
                    self.sig_status.emit(f"Publicando en grupo ({processed_count}/{total_groups}): {group_url}")

                    result = poster.post_to_group(
                        group_url=group_url,
                        message=self.bundle.text,
                        media_paths=self.bundle.media_paths,
                        dry_run=self.dry_run,
                    )

                    # Persist in manager
                    self.manager.record_result(
                        group_url=group_url,
                        status=result.status,
                        details=result.details,
                    )

                    self.sig_group_finished.emit(group_url, result.status, result.details)

                    # Emergency stop if Facebook triggered an anti-spam block
                    if result.status == "BLOCKED":
                        msg = "BLOQUEO DETECTADO: Facebook suspendió la acción temporalmente. Deteniendo campaña."
                        self.sig_error.emit(msg)
                        self.sig_status.emit(msg)
                        return

                    # Human jitter delay between posts inside the batch
                    if item_idx < len(batch) and not self._stop_event.is_set():
                        delay = random.uniform(self.min_delay, self.max_delay)
                        label = f"Pausa humana anti-bot ({delay:.0f}s)"
                        if not self._sleep_interruptible(delay, label):
                            break

                self.sig_batch_completed.emit(batch_idx, total_batches)

                # Cooldown between batches if there is a next batch
                if batch_idx < total_batches and not self._stop_event.is_set():
                    cooldown_label = f"Cooldown entre tandas ({self.cooldown}s)"
                    if not self._sleep_interruptible(self.cooldown, cooldown_label):
                        break

            if self._stop_event.is_set():
                self.sig_status.emit("Campaña detenida por el usuario.")
            else:
                self.sig_status.emit("¡Campaña finalizada exitosamente!")

        except Exception as e:
            logger.error(f"Error inesperado en campaña: {e}")
            self.sig_error.emit(str(e))
            self.sig_status.emit(f"Error: {e}")
        finally:
            poster.close_session()
            self.sig_finished.emit(self.manager.get_stats())
