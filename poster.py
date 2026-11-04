"""Facebook Group Poster using Playwright and persistent browser context.

Handles browser automation, anti-detection pacing, dynamic Facebook UI elements,
and batch posting across Facebook groups.
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List

from playwright.sync_api import sync_playwright, BrowserContext, Page, TimeoutError as PlaywrightTimeoutError

from config import PosterConfig
from batch_manager import GroupBatchManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("FacebookPoster")


@dataclass
class PostResult:
    """Outcome of attempting to post in a single Facebook group."""

    group_url: str
    success: bool
    status: str
    details: str = ""


class FacebookGroupPoster:
    """Automates posting to Facebook groups with human-like behavior."""

    def __init__(self, config: PosterConfig) -> None:
        self.config = config
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.playwright = None

    def start_session(self, force_visible: bool = False) -> None:
        """Launch browser using persistent context to preserve login session."""
        self.config.user_data_dir.mkdir(parents=True, exist_ok=True)
        self.playwright = sync_playwright().start()

        # Headless mode should be False for initial login or debugging
        is_headless = False if force_visible else self.config.headless

        logger.info(
            f"Launching Chromium with profile at: {self.config.user_data_dir} (headless={is_headless})"
        )

        args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
        ]

        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.config.user_data_dir),
            headless=is_headless,
            viewport={"width": self.config.viewport_width, "height": self.config.viewport_height},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            args=args,
            locale="es-ES",
        )

        # Apply basic navigator override to avoid simple bot detection
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

    def close_session(self) -> None:
        """Gracefully close browser context and Playwright runtime."""
        if self.context:
            self.context.close()
            self.context = None
        if self.playwright:
            self.playwright.stop()
            self.playwright = None
        logger.info("Browser session closed.")

    def run_login_flow(self) -> bool:
        """Open browser to Facebook and pause so the user can log in manually."""
        logger.info("Opening Facebook for manual login...")
        self.start_session(force_visible=True)
        assert self.page is not None

        self.page.goto("https://www.facebook.com/", wait_until="domcontentloaded")

        print("\n" + "=" * 60)
        print("POR FAVOR INICIA SESIÓN EN LA VENTANA DEL NAVEGADOR QUE SE ABRIÓ.")
        print("Ingresa tu correo, contraseña y resuelve 2FA si aplica.")
        print("Una vez que estés dentro de Facebook (en el feed principal),")
        print("regresa a esta terminal y presiona ENTER para guardar la sesión.")
        print("=" * 60 + "\n")

        input("Presiona [ENTER] cuando hayas iniciado sesión completamente en Facebook... ")

        # Quick check if logged in
        is_logged = self.is_logged_in()
        if is_logged:
            logger.info("¡Sesión guardada exitosamente en el perfil!")
        else:
            logger.warning(
                "No se pudo verificar el inicio de sesión. Si iniciaste sesión, el perfil ya se guardó."
            )

        self.close_session()
        return is_logged

    def is_logged_in(self) -> bool:
        """Verify whether the current session is logged into Facebook."""
        if not self.page:
            return False
        try:
            # Check for common post-login elements
            logged_in_selectors = [
                'div[aria-label="Your profile"]',
                'div[aria-label="Tu perfil"]',
                'div[aria-label="Cuenta"]',
                'div[aria-label="Account"]',
                'div[role="navigation"]',
                'a[href*="/me/"]',
            ]
            for sel in logged_in_selectors:
                if self.page.locator(sel).first.is_visible(timeout=3000):
                    return True

            # If login inputs exist, user is NOT logged in
            login_inputs = ['input[name="email"]', 'input[id="email"]', 'button[name="login"]']
            for sel in login_inputs:
                if self.page.locator(sel).first.is_visible(timeout=2000):
                    return False

            return True
        except Exception:
            return False

    def _type_human_like(self, text: str) -> None:
        """Type message text into focused input with randomized delays."""
        assert self.page is not None
        if not self.config.human_typing:
            self.page.keyboard.insert_text(text)
            return

        lines = text.split("\n")
        for i, line in enumerate(lines):
            for char in line:
                self.page.keyboard.type(char, delay=random.randint(15, 60))
                if random.random() < 0.05:
                    time.sleep(random.uniform(0.1, 0.4))
            if i < len(lines) - 1:
                # Type Enter or Shift+Enter for newlines
                self.page.keyboard.press("Shift+Enter")
                time.sleep(random.uniform(0.1, 0.3))

    def _check_rate_limit(self) -> bool:
        """Detect Facebook rate limiting or temporary block banners."""
        if not self.page:
            return False
        rate_limit_texts = [
            "Se te ha bloqueado temporalmente",
            "You're temporarily blocked",
            "Has alcanzado el límite",
            "You've reached a limit",
            "No puedes usar esta función",
            "Action blocked",
        ]
        for text in rate_limit_texts:
            if self.page.locator(f"text='{text}'").first.is_visible(timeout=1000):
                return True
        return False

    def post_to_group(
        self,
        group_url: str,
        message: str,
        image_path: Optional[Path] = None,
        dry_run: bool = False,
    ) -> PostResult:
        """Post a message and optional image to a specific Facebook group URL."""
        assert self.page is not None
        logger.info(f"Navigating to group: {group_url}")

        try:
            self.page.goto(group_url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(random.uniform(3.0, 5.0))

            # Detect rate limits
            if self._check_rate_limit():
                logger.error("Rate limit or block detected on Facebook!")
                return PostResult(
                    group_url=group_url,
                    success=False,
                    status="BLOCKED",
                    details="Facebook rate limit or temporary block detected.",
                )

            # Check if user is not a member
            join_selectors = [
                'div[aria-label="Unirte al grupo"]',
                'div[aria-label="Join group"]',
                'span:has-text("Unirte al grupo")',
                'span:has-text("Join group")',
            ]
            for sel in join_selectors:
                if self.page.locator(sel).first.is_visible(timeout=2000):
                    logger.warning(f"Not a member of group: {group_url}")
                    return PostResult(
                        group_url=group_url,
                        success=False,
                        status="NOT_A_MEMBER",
                        details="User is not a member of this group.",
                    )

            # Find the "Write something..." / "Escribe algo..." box
            composer_triggers = [
                'div[role="button"]:has-text("Escribe algo...")',
                'div[role="button"]:has-text("Write something...")',
                'div[role="button"]:has-text("Crear publicación")',
                'div[role="button"]:has-text("Create post")',
                'div[role="button"]:has-text("Create a public post...")',
                'span:has-text("Escribe algo...")',
                'span:has-text("Write something...")',
                'div[data-pagelet="GroupInlineComposer"] div[role="button"]',
            ]

            trigger_elem = None
            for sel in composer_triggers:
                loc = self.page.locator(sel).first
                if loc.is_visible(timeout=2000):
                    trigger_elem = loc
                    break

            if not trigger_elem:
                logger.warning(
                    f"Could not find post creation box in: {group_url}. Group may require admin approval or have posting restricted."
                )
                return PostResult(
                    group_url=group_url,
                    success=False,
                    status="CANNOT_POST",
                    details="Post creation button not found or posting restricted.",
                )

            # Click composer trigger
            trigger_elem.click()
            time.sleep(random.uniform(2.0, 3.5))

            # Wait for modal dialog
            dialog = self.page.locator('div[role="dialog"]').first
            dialog.wait_for(state="visible", timeout=15000)

            # Find text editor inside modal
            editor_selectors = [
                'div[role="dialog"] div[role="textbox"]',
                'div[role="dialog"] div[contenteditable="true"]',
                'div[role="dialog"] div[aria-label*="Escribe algo" i]',
                'div[role="dialog"] div[aria-label*="Write something" i]',
                'div[role="dialog"] div[aria-label*="¿Qué estás pensando" i]',
            ]

            editor_elem = None
            for sel in editor_selectors:
                loc = self.page.locator(sel).first
                if loc.is_visible(timeout=3000):
                    editor_elem = loc
                    break

            if not editor_elem:
                logger.error("Could not find text input area inside modal dialog.")
                return PostResult(
                    group_url=group_url,
                    success=False,
                    status="FAILED",
                    details="Text input area not found in modal.",
                )

            editor_elem.click()
            time.sleep(0.5)

            # Type the message
            logger.info("Typing message into post editor...")
            self._type_human_like(message)
            time.sleep(random.uniform(1.5, 3.0))

            # Handle optional image attachment
            if image_path and image_path.exists():
                logger.info(f"Attaching image from {image_path}...")
                try:
                    file_input = self.page.locator('div[role="dialog"] input[type="file"]').first
                    if file_input.count() > 0:
                        file_input.set_input_files(str(image_path))
                        time.sleep(3.0)
                    else:
                        photo_btn = self.page.locator(
                            'div[role="dialog"] div[aria-label*="Foto" i], div[role="dialog"] div[aria-label*="Photo" i]'
                        ).first
                        if photo_btn.is_visible(timeout=3000):
                            with self.page.expect_file_chooser(timeout=5000) as fc_info:
                                photo_btn.click()
                            file_chooser = fc_info.value
                            file_chooser.set_files(str(image_path))
                            time.sleep(3.0)
                except Exception as img_err:
                    logger.warning(f"Could not attach image: {img_err}")

            if dry_run:
                logger.info("[DRY RUN] Simulating post submission (not clicking Post).")
                # Close dialog by pressing Escape
                self.page.keyboard.press("Escape")
                time.sleep(1.0)
                return PostResult(
                    group_url=group_url,
                    success=True,
                    status="DRY_RUN",
                    details="Simulated successfully without publishing.",
                )

            # Find Post / Publicar button inside modal
            post_btn_selectors = [
                'div[role="dialog"] div[aria-label="Publicar"][role="button"]',
                'div[role="dialog"] div[aria-label="Post"][role="button"]',
                'div[role="dialog"] div[role="button"]:has-text("Publicar")',
                'div[role="dialog"] div[role="button"]:has-text("Post")',
            ]

            post_btn = None
            for sel in post_btn_selectors:
                loc = self.page.locator(sel).first
                if loc.is_visible(timeout=3000):
                    post_btn = loc
                    break

            if not post_btn:
                logger.error("Could not find 'Post' button.")
                return PostResult(
                    group_url=group_url,
                    success=False,
                    status="FAILED",
                    details="Submit button not found.",
                )

            # Wait until post button is enabled
            time.sleep(1.0)
            post_btn.click()
            logger.info("Clicked 'Post'. Waiting for confirmation...")

            # Wait for modal to dismiss
            try:
                dialog.wait_for(state="hidden", timeout=25000)
                status = "SUCCESS"
                details = "Post published successfully."
            except PlaywrightTimeoutError:
                # Check if it was submitted for admin approval
                approval_note = self.page.locator(
                    'text="Enviado para aprobación del administrador", text="Submitted for admin approval"'
                ).first
                if approval_note.is_visible(timeout=2000):
                    status = "PENDING_APPROVAL"
                    details = "Post submitted and pending admin approval."
                else:
                    status = "POSSIBLE_SUCCESS"
                    details = "Dialog did not close in time, but post was submitted."

            logger.info(f"Result for {group_url}: {status}")
            return PostResult(group_url=group_url, success=True, status=status, details=details)

        except PlaywrightTimeoutError as te:
            logger.error(f"Timeout while interacting with {group_url}: {te}")
            return PostResult(
                group_url=group_url,
                success=False,
                status="FAILED",
                details=f"Timeout: {te}",
            )
        except Exception as e:
            logger.error(f"Unexpected error in {group_url}: {e}")
            return PostResult(
                group_url=group_url,
                success=False,
                status="FAILED",
                details=f"Error: {e}",
            )

    def execute_campaign(
        self,
        manager: GroupBatchManager,
        message: str,
        image_path: Optional[Path] = None,
        dry_run: bool = False,
    ) -> None:
        """Run campaign through batches with anti-detection pacing and cooldown."""
        self.start_session()
        assert self.page is not None

        # Verify session is authenticated
        self.page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
        time.sleep(3.0)
        if not self.is_logged_in():
            logger.error(
                "No hay una sesión activa de Facebook. Ejecuta primero: python main.py --login"
            )
            self.close_session()
            return

        batch_number = 1
        try:
            for batch in manager.stream_batches():
                logger.info(
                    f"\n{'=' * 20} INICIANDO TANDA {batch_number} ({len(batch)} grupos) {'=' * 20}"
                )

                for index, group_url in enumerate(batch, start=1):
                    logger.info(
                        f"Procesando grupo {index}/{len(batch)} de la tanda {batch_number}: {group_url}"
                    )
                    result = self.post_to_group(
                        group_url=group_url,
                        message=message,
                        image_path=image_path,
                        dry_run=dry_run,
                    )

                    # Persist state
                    manager.record_result(
                        group_url=group_url,
                        status=result.status,
                        details=result.details,
                    )

                    # If Facebook blocked the action, stop to protect the account
                    if result.status == "BLOCKED":
                        logger.critical(
                            "DETENCIÓN DE EMERGENCIA: Facebook detectó límites o bloqueo temporal. "
                            "Se suspende la ejecución para proteger tu cuenta."
                        )
                        return

                    # Human jitter delay between posts in the batch
                    if index < len(batch):
                        delay = random.uniform(
                            self.config.min_post_delay, self.config.max_post_delay
                        )
                        logger.info(
                            f"Esperando {delay:.1f} segundos antes del siguiente grupo (anti-bot)..."
                        )
                        time.sleep(delay)

                stats = manager.get_stats()
                logger.info(
                    f"Tanda {batch_number} completada. Estadísticas acumuladas: {stats}"
                )

                # Cooldown delay between batches
                logger.info(
                    f"Pausa entre tandas (cooldown): {self.config.batch_cooldown} segundos (~{self.config.batch_cooldown / 60:.1f} minutos)..."
                )
                time.sleep(self.config.batch_cooldown)
                batch_number += 1

            logger.info("¡Todas las tandas pendientes han sido procesadas!")

        finally:
            self.close_session()
