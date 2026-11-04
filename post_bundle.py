"""Module for managing post bundles (text, images, and videos in a single directory).

Encapsulates reading the post text and discovering all attached media files
from a given folder path.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

logger = logging.getLogger("FacebookGroupPoster")


@dataclass(frozen=True)
class PostBundle:
    """Encapsulates all content to be published together in a Facebook post."""

    text: str
    media_paths: tuple[Path, ...]
    source_dir: Path

    @property
    def has_media(self) -> bool:
        """Check if bundle contains any image or video attachments."""
        return len(self.media_paths) > 0

    @property
    def media_count(self) -> int:
        """Total number of attached media files."""
        return len(self.media_paths)


class PostBundleLoader:
    """Loads post content (text, images, and videos) from a directory path.
    
    The directory must contain:
      - 'post_content.txt': The message text to publish.
      - Any image files (.jpg, .jpeg, .png, .webp, .gif, .bmp).
      - Any video files (.mp4, .mov, .avi, .mkv, .webm, .m4v).
    """

    SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
    SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
    SUPPORTED_MEDIA_EXTENSIONS = SUPPORTED_IMAGE_EXTENSIONS | SUPPORTED_VIDEO_EXTENSIONS

    def __init__(self, directory_path: str | Path) -> None:
        self.directory_path = Path(directory_path).resolve()

    def load(self) -> PostBundle:
        """Validate directory, load text, and discover all media files."""
        if not self.directory_path.exists():
            raise FileNotFoundError(
                f"El directorio especificado no existe: {self.directory_path}"
            )
        if not self.directory_path.is_dir():
            raise NotADirectoryError(
                f"La ruta especificada no es una carpeta: {self.directory_path}"
            )

        content_file = self.directory_path / "post_content.txt"
        if not content_file.exists():
            # Fallback to any single .txt file if post_content.txt is missing
            txt_files = [f for f in self.directory_path.glob("*.txt") if not f.name.startswith(".")]
            if txt_files:
                content_file = txt_files[0]
            else:
                raise FileNotFoundError(
                    f"No se encontró 'post_content.txt' dentro de: {self.directory_path}\n"
                    f"Crea un archivo 'post_content.txt' con el texto del mensaje dentro de esa carpeta."
                )

        with open(content_file, "r", encoding="utf-8") as f:
            text = f.read().strip()

        if not text:
            raise ValueError(
                f"El archivo '{content_file.name}' está vacío. Debe contener el texto del post."
            )

        # Discover all valid media files in directory (non-recursive, non-hidden)
        media_files: list[Path] = []
        for item in sorted(self.directory_path.iterdir(), key=lambda p: p.name.lower()):
            if item.is_file() and not item.name.startswith("."):
                if item.suffix.lower() in self.SUPPORTED_MEDIA_EXTENSIONS:
                    media_files.append(item)

        bundle = PostBundle(
            text=text,
            media_paths=tuple(media_files),
            source_dir=self.directory_path,
        )

        logger.info(
            f"PostBundle cargado desde: {bundle.source_dir} | "
            f"Texto: {len(bundle.text)} caracteres | "
            f"Archivos multimedia ({bundle.media_count}): {[p.name for p in bundle.media_paths]}"
        )
        return bundle
