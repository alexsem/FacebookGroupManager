"""Configuration module for Facebook Group Poster.

Reads environment variables from .env.local or .env.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

# Prioritize .env.local over .env
BASE_DIR = Path(__file__).resolve().parent
local_env = BASE_DIR / ".env.local"
default_env = BASE_DIR / ".env"

if local_env.exists():
    load_dotenv(dotenv_path=local_env)
else:
    load_dotenv(dotenv_path=default_env)


@dataclass(frozen=True)
class PosterConfig:
    """Immutable application configuration."""

    # Paths
    user_data_dir: Path = BASE_DIR / os.getenv("FB_USER_DATA_DIR", "fb_user_data")
    groups_file: Path = BASE_DIR / os.getenv("FB_GROUPS_FILE", "groups.txt")
    post_dir: Path = BASE_DIR / os.getenv("FB_POST_DIR", "post_data")
    post_file: Path = BASE_DIR / os.getenv("FB_POST_FILE", "post_content.txt")
    history_file: Path = BASE_DIR / os.getenv("FB_HISTORY_FILE", "post_history.json")
    image_path: Path | None = (
        BASE_DIR / os.getenv("FB_IMAGE_PATH") if os.getenv("FB_IMAGE_PATH") else None
    )

    # Batch and delay settings
    batch_size: int = int(os.getenv("FB_BATCH_SIZE", "10"))
    min_post_delay: int = int(os.getenv("FB_MIN_POST_DELAY", "45"))
    max_post_delay: int = int(os.getenv("FB_MAX_POST_DELAY", "90"))
    batch_cooldown: int = int(os.getenv("FB_BATCH_COOLDOWN", "30"))  # 30 seconds default

    # Browser options
    headless: bool = os.getenv("FB_HEADLESS", "false").lower() in ("true", "1", "yes")
    viewport_width: int = int(os.getenv("FB_VIEWPORT_WIDTH", "1280"))
    viewport_height: int = int(os.getenv("FB_VIEWPORT_HEIGHT", "800"))

    # Anti-bot options
    human_typing: bool = os.getenv("FB_HUMAN_TYPING", "true").lower() in ("true", "1", "yes")

    @property
    def resolved_post_dir(self) -> Path:
        """Resolve post bundle directory, falling back to BASE_DIR if post_data does not exist."""
        if self.post_dir.exists() and self.post_dir.is_dir():
            return self.post_dir
        if (BASE_DIR / "post_content.txt").exists():
            return BASE_DIR
        return self.post_dir
