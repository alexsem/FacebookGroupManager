"""Facebook Group Poster using Playwright and persistent browser context.

Handles browser automation, anti-detection pacing, dynamic Facebook UI elements,
and batch posting across Facebook groups.
"""

from __future__ import annotations

import logging
import os
import random
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from playwright.sync_api import sync_playwright, BrowserContext, Page, TimeoutError as PlaywrightTimeoutError

from config import PosterConfig
from batch_manager import GroupBatchManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("FacebookPoster")

_POST_ID_PATTERNS = (
    re.compile(r"/groups/[^/]+/posts/(\d+)"),
    re.compile(r"/groups/[^/]+/permalink/(\d+)"),
    re.compile(r"/posts/(\d+)"),
    re.compile(r"[?&]multi_permalinks=(\d+)"),
    re.compile(r"[?&]story_fbid=(\d+)"),
)
_IGNORED_QUERY_PREFIXES = ("__cft__", "__tn__", "notif_", "ref")


def extract_fb_post_id(url: str) -> Optional[str]:
    """Extract numeric Facebook post ID from a permalink URL."""
    if not url:
        return None
    for pattern in _POST_ID_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)
    return None


def normalize_fb_post_url(raw_href: str, group_url: str = "") -> Optional[str]:
    """Normalize a candidate Facebook link into a clean post permalink if valid."""
    if not raw_href:
        return None
    candidate = raw_href.strip()
    if candidate.startswith("#") or candidate.startswith("javascript:"):
        return None

    full_url = urljoin("https://www.facebook.com", candidate)
    parsed = urlparse(full_url)
    if "facebook.com" not in parsed.netloc.lower():
        return None

    # Ignore comment-specific anchors when looking for the parent post permalink
    qs = parse_qs(parsed.query)
    if "comment_id" in qs or "reply_comment_id" in qs:
        return None

    post_id = extract_fb_post_id(full_url)
    if not post_id:
        return None

    # Keep only essential query params (e.g., multi_permalinks / story_fbid)
    kept_params = {
        k: v
        for k, v in qs.items()
        if k in ("multi_permalinks", "story_fbid", "id")
        and not any(k.startswith(prefix) for prefix in _IGNORED_QUERY_PREFIXES)
    }
    clean_query = urlencode(kept_params, doseq=True)
    clean_path = parsed.path.rstrip("/") + "/" if parsed.path else "/"
    normalized = urlunparse(("https", "www.facebook.com", clean_path, "", clean_query, ""))

    # If group_url is given and candidate is a generic group link with multi_permalinks, keep it
    if group_url and "/groups/" not in normalized and "multi_permalinks=" not in normalized:
        return normalized
    return normalized


@dataclass
class PostResult:
    """Outcome of attempting to post in a single Facebook group."""

    group_url: str
    success: bool
    status: str
    details: str = ""
    post_url: Optional[str] = None
    fb_post_id: Optional[str] = None


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
            f"Launching browser with profile at: {self.config.user_data_dir} (headless={is_headless})"
        )

        # Clean flags without --no-sandbox to avoid Chrome security and WebAuthn warnings
        args = [
            "--disable-blink-features=AutomationControlled",
        ]

        launch_kwargs = {
            "user_data_dir": str(self.config.user_data_dir),
            "headless": is_headless,
            "viewport": {"width": self.config.viewport_width, "height": self.config.viewport_height},
            "ignore_default_args": ["--enable-automation"],
            "args": args,
            "locale": "es-ES",
        }

        try:
            # Use real installed Google Chrome for full WebAuthn/2FA and genuine browser fingerprint
            self.context = self.playwright.chromium.launch_persistent_context(
                channel="chrome",
                **launch_kwargs,
            )
            logger.info("Using native Google Chrome browser.")
        except Exception as e:
            logger.warning(f"Could not launch native Chrome ({e}), falling back to bundled Chromium.")
            self.context = self.playwright.chromium.launch_persistent_context(
                **launch_kwargs,
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

    @staticmethod
    def _find_chrome_executable() -> Optional[Path]:
        """Find local Google Chrome executable on Windows."""
        local_app = os.environ.get("LOCALAPPDATA", "")
        candidates = [
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
            Path(local_app) / "Google" / "Chrome" / "Application" / "chrome.exe" if local_app else None,
        ]
        for c in candidates:
            if c and c.exists():
                return c
        return None

    def run_login_flow(self) -> bool:
        """Open browser for initial manual Facebook login with full 2FA support."""
        profile_dir = self.config.user_data_dir.resolve()
        profile_dir.mkdir(parents=True, exist_ok=True)
        chrome_exe = self._find_chrome_executable()

        print("\n" + "=" * 65)
        print("INICIO DE SESIÓN MANUAL EN FACEBOOK (2FA / SEGURO)")
        print("Se abrirá una ventana de Google Chrome con tu perfil.")
        print("1. Ingresa tu correo y contraseña.")
        print("2. Resuelve el 2FA (código, SMS o aprobación en celular).")
        print("3. Una vez que veas tu muro o feed principal de Facebook:")
        print("   -> Cierra la ventana de Chrome.")
        print("   -> Regresa a esta terminal y presiona [ENTER].")
        print("=" * 65 + "\n")

        if chrome_exe:
            logger.info(f"Iniciando Google Chrome nativo: {chrome_exe}")
            proc = subprocess.Popen([
                str(chrome_exe),
                f"--user-data-dir={profile_dir}",
                "https://www.facebook.com/",
            ])
            input("Presiona [ENTER] después de iniciar sesión y cerrar la ventana de Chrome... ")
            try:
                proc.terminate()
            except Exception:
                pass
        else:
            logger.info("Chrome nativo no encontrado, iniciando sesión con Playwright...")
            self.start_session(force_visible=True)
            assert self.page is not None
            self.page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
            input("Presiona [ENTER] cuando hayas iniciado sesión en Facebook... ")
            self.close_session()

        time.sleep(2.0)
        logger.info("Verificando sesión guardada en perfil...")
        self.start_session(force_visible=False)
        assert self.page is not None
        self.page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
        time.sleep(3.0)
        is_logged = self.is_logged_in()
        self.close_session()

        if is_logged:
            logger.info("¡Sesión verificada y guardada exitosamente en el perfil!")
        else:
            logger.warning(
                "No se pudo verificar el inicio de sesión. Si viste tu muro antes de cerrar, la sesión ya quedó guardada."
            )
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
        """Type message text into focused input with randomized delays and emoji support."""
        assert self.page is not None
        if not self.config.human_typing:
            self.page.keyboard.insert_text(text)
            return

        lines = text.split("\n")
        for i, line in enumerate(lines):
            for char in line:
                # Use insert_text to reliably handle emojis and unicode surrogate pairs
                self.page.keyboard.insert_text(char)
                time.sleep(random.uniform(0.012, 0.035))
                if random.random() < 0.04:
                    time.sleep(random.uniform(0.08, 0.25))
            if i < len(lines) - 1:
                # Shift+Enter creates a new line in Facebook composer without submitting
                self.page.keyboard.press("Shift+Enter")
                time.sleep(random.uniform(0.1, 0.25))

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

    def _wait_for_media_upload(self, container: Optional[Any] = None, max_wait_sec: int = 180) -> None:
        """Wait for Facebook to process media upload (photos/videos)."""
        if not self.page:
            return
        logger.info("Waiting for media files to finish uploading (photos/video)...")
        time.sleep(3.0)
        start_time = time.time()
        target = container if container is not None else self.page

        post_btn_selectors = [
            'div[aria-label="Publicar"][role="button"]',
            'div[aria-label="Post"][role="button"]',
            'div[role="button"]:has-text("Publicar")',
            'div[role="button"]:has-text("Post")',
        ]

        while time.time() - start_time < max_wait_sec:
            try:
                progressbar = target.locator('[role="progressbar"]').first
                if progressbar.is_visible(timeout=500):
                    time.sleep(2.0)
                    continue
            except Exception:
                pass

            for sel in post_btn_selectors:
                try:
                    btn = target.locator(sel).first
                    if btn.is_visible(timeout=500):
                        disabled = btn.get_attribute("aria-disabled")
                        if disabled not in ("true", "1"):
                            logger.info("Media upload completed and submit button is enabled.")
                            time.sleep(1.0)
                            return
                except Exception:
                    pass
            time.sleep(1.5)

    def _find_first_post_link(self, scope: Any, group_url: str) -> Tuple[Optional[str], Optional[str]]:
        """Inspect candidate permalink anchors inside a Playwright Locator/Page scope."""
        link_selectors = (
            'a[href*="/posts/"]',
            'a[href*="/permalink/"]',
            'a[href*="multi_permalinks="]',
        )
        for sel in link_selectors:
            try:
                loc = scope.locator(sel)
                count = min(loc.count(), 5)
                for idx in range(count):
                    href = loc.nth(idx).get_attribute("href")
                    normalized = normalize_fb_post_url(href or "", group_url=group_url)
                    if normalized:
                        return normalized, extract_fb_post_id(normalized)
            except Exception:
                continue
        return None, None

    def _extract_published_post_url(self, group_url: str) -> Tuple[Optional[str], Optional[str]]:
        """Attempt to capture the permalink URL of the newly published post."""
        if not self.page:
            return None, None
        try:
            time.sleep(2.0)

            # Strategy 1: Toast / snackbar ("Ver publicación" / "View post")
            toast_selectors = (
                'div[role="alert"]',
                'div[role="status"]',
                'a:has-text("Ver publicación")',
                'a:has-text("View post")',
            )
            for sel in toast_selectors:
                try:
                    elem = self.page.locator(sel).first
                    if elem.is_visible(timeout=1000):
                        href = elem.get_attribute("href")
                        if href:
                            normalized = normalize_fb_post_url(href, group_url=group_url)
                            if normalized:
                                logger.info(f"Captured post URL from toast: {normalized}")
                                return normalized, extract_fb_post_id(normalized)
                        url, pid = self._find_first_post_link(elem, group_url)
                        if url:
                            logger.info(f"Captured post URL from toast container: {url}")
                            return url, pid
                except Exception:
                    continue

            # Strategy 2: Top articles in the group feed
            articles = self.page.locator('div[role="feed"] div[role="article"]')
            for idx in range(min(articles.count(), 2)):
                url, pid = self._find_first_post_link(articles.nth(idx), group_url)
                if url:
                    logger.info(f"Captured post URL from top group feed: {url}")
                    return url, pid

            # Strategy 3: Fallback to /my_posted_content for the current group
            my_content_url = group_url.rstrip("/") + "/my_posted_content"
            self.page.goto(my_content_url, wait_until="domcontentloaded", timeout=20000)
            time.sleep(2.5)
            url, pid = self._find_first_post_link(self.page, group_url)
            if url:
                logger.info(f"Captured post URL from my_posted_content: {url}")
                return url, pid
        except Exception as err:
            logger.warning(f"Could not capture published post URL for {group_url}: {err}")

        return None, None

    def post_to_group(
        self,
        group_url: str,
        message: str,
        media_paths: Optional[Sequence[Path]] = None,
        image_path: Optional[Path] = None,
        dry_run: bool = False,
    ) -> PostResult:
        """Post a message and optional media (images and/or videos) to a specific Facebook group."""
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
            time.sleep(random.uniform(2.5, 4.0))

            # Wait for specific composer modal dialog (avoiding notifications or background dialogs)
            composer_dialog = self.page.locator(
                'div[role="dialog"]:has-text("Crear publicación"), '
                'div[role="dialog"]:has-text("Create post"), '
                'div[role="dialog"]:has-text("Crea una publicación")'
            ).first
            composer_dialog.wait_for(state="visible", timeout=15000)

            # Find text editor inside composer dialog
            editor_selectors = [
                'div[role="textbox"][contenteditable="true"]',
                '[data-lexical-editor="true"]',
                '[aria-label*="pública" i][role="textbox"]',
                '[aria-label*="public" i][role="textbox"]',
                '[aria-label*="Escribe algo" i][role="textbox"]',
                '[contenteditable="true"]',
            ]

            editor_elem = None
            for sel in editor_selectors:
                loc = composer_dialog.locator(sel).first
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

            # Handle optional media attachment (photos and/or videos)
            all_media: list[Path] = []
            if media_paths:
                all_media.extend([p for p in media_paths if p and p.exists()])
            elif image_path and image_path.exists():
                all_media.append(image_path)

            if all_media:
                media_file_paths = [str(p.resolve()) for p in all_media]
                logger.info(
                    f"Attaching {len(media_file_paths)} media file(s) to post: {[p.name for p in all_media]}..."
                )
                try:
                    # File input is already present inside the composer dialog
                    file_input = composer_dialog.locator('input[type="file"]').first
                    if file_input.count() > 0:
                        file_input.set_input_files(media_file_paths)
                    else:
                        photo_btn = composer_dialog.locator(
                            'div[aria-label*="Foto" i], '
                            'div[aria-label*="Photo" i], '
                            'div[aria-label*="video" i], '
                            'div[aria-label*="vídeo" i]'
                        ).first
                        if photo_btn.is_visible(timeout=3000):
                            try:
                                with self.page.expect_file_chooser(timeout=3000) as fc_info:
                                    photo_btn.click()
                                file_chooser = fc_info.value
                                file_chooser.set_files(media_file_paths)
                            except Exception:
                                time.sleep(1.0)
                                composer_dialog.locator('input[type="file"]').first.set_input_files(media_file_paths)

                    # Wait for media files to complete upload before continuing
                    self._wait_for_media_upload(composer_dialog)
                except Exception as media_err:
                    logger.warning(f"Could not attach media files: {media_err}")

            if dry_run:
                logger.info("[DRY RUN] Simulating post submission (not clicking Post).")
                print("\n" + "=" * 60)
                print("[MODO SIMULACIÓN - DRY RUN]")
                print("El mensaje y los archivos multimedia han sido cargados con éxito.")
                print("Esperando 12 segundos para que puedas inspeccionar visualmente la ventana...")
                print("=" * 60 + "\n")
                time.sleep(12.0)
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
                'div[aria-label="Publicar"][role="button"]',
                'div[aria-label="Post"][role="button"]',
                'div[role="button"]:has-text("Publicar")',
                'div[role="button"]:has-text("Post")',
            ]

            post_btn = None
            for sel in post_btn_selectors:
                loc = composer_dialog.locator(sel).first
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
            post_url: Optional[str] = None
            fb_post_id: Optional[str] = None
            try:
                composer_dialog.wait_for(state="hidden", timeout=25000)
                status = "SUCCESS"
                details = "Post published successfully."
                if self.config.capture_post_url:
                    post_url, fb_post_id = self._extract_published_post_url(group_url)
                    if post_url:
                        details = f"Post published successfully. URL: {post_url}"
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
            return PostResult(
                group_url=group_url,
                success=True,
                status=status,
                details=details,
                post_url=post_url,
                fb_post_id=fb_post_id,
            )

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
        media_paths: Optional[Sequence[Path]] = None,
        image_path: Optional[Path] = None,
        dry_run: bool = False,
        ignore_history: bool = False,
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
        skip_history = ignore_history or dry_run
        try:
            for batch in manager.stream_batches(ignore_history=skip_history):
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
                        media_paths=media_paths,
                        image_path=image_path,
                        dry_run=dry_run,
                    )

                    # Persist state
                    manager.record_result(
                        group_url=group_url,
                        status=result.status,
                        details=result.details,
                        post_url=result.post_url,
                        fb_post_id=result.fb_post_id,
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
