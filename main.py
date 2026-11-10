"""CLI Entrypoint for Facebook Group Batch Poster.

Allows running initial login setup, dry runs, single group testing,
and full campaign execution in batches from a bundle path (text + images/videos).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows consoles to prevent UnicodeEncodeError with emojis
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from config import PosterConfig
from batch_manager import GroupBatchManager
from post_bundle import PostBundle, PostBundleLoader
from poster import FacebookGroupPoster, logger


def load_post_content(post_file: Path) -> str:
    """Read post text from file using utf-8 encoding."""
    if not post_file.exists():
        raise FileNotFoundError(
            f"El archivo con el contenido de la publicación no existe: {post_file}\n"
            f"Crea el archivo '{post_file.name}' con el texto que deseas publicar."
        )
    with open(post_file, "r", encoding="utf-8") as f:
        content = f.read().strip()
    if not content:
        raise ValueError(f"El archivo '{post_file.name}' está vacío.")
    return content


def resolve_post_bundle(args: argparse.Namespace, config: PosterConfig) -> PostBundle:
    """Resolve and load the PostBundle (text + media files) from a directory path."""
    # 1. Explicit directory passed via CLI
    if args.post_dir:
        loader = PostBundleLoader(args.post_dir)
        return loader.load()

    # 2. Configured directory in .env or default 'post_data' folder
    candidate_dir = config.resolved_post_dir
    if candidate_dir.exists() and candidate_dir.is_dir():
        try:
            loader = PostBundleLoader(candidate_dir)
            bundle = loader.load()
            if args.image:
                img_path = Path(args.image).resolve()
                if img_path.exists() and img_path not in bundle.media_paths:
                    return PostBundle(
                        text=bundle.text,
                        media_paths=(*bundle.media_paths, img_path),
                        source_dir=bundle.source_dir,
                    )
            return bundle
        except Exception as e:
            # If candidate_dir was explicitly FB_POST_DIR, raise error
            if os.getenv("FB_POST_DIR"):
                raise e

    # 3. Fallback: single file
    post_file = Path(args.post_file) if args.post_file else config.post_file
    text = load_post_content(post_file)
    media: list[Path] = []
    media_candidate = Path(args.image) if args.image else config.image_path
    if media_candidate and media_candidate.exists():
        media.append(media_candidate.resolve())

    return PostBundle(text=text, media_paths=tuple(media), source_dir=post_file.parent)


def parse_arguments() -> argparse.Namespace:
    """Configure and parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Publicador masivo en grupos de Facebook por tandas con Playwright."
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Abre el navegador para iniciar sesión manualmente y guardar la sesión persistente.",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Inicia la campaña de publicación por tandas.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Modo de prueba: navega, escribe el post y adjunta archivos pero NO hace clic en Publicar.",
    )
    parser.add_argument(
        "--single",
        type=str,
        default=None,
        help="URL de un único grupo para realizar una prueba individual.",
    )
    parser.add_argument(
        "--path",
        "--post-dir",
        dest="post_dir",
        type=str,
        default=None,
        help="Ruta a la carpeta que contiene 'post_content.txt' y todos los archivos de imagen/video para el post.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Tamaño de la tanda (por defecto 10 o el configurado en .env).",
    )
    parser.add_argument(
        "--groups-file",
        type=str,
        default=None,
        help="Ruta alternativa al archivo con lista de URLs de grupos.",
    )
    parser.add_argument(
        "--post-file",
        type=str,
        default=None,
        help="Ruta alternativa al archivo con el texto de la publicación.",
    )
    parser.add_argument(
        "--image",
        type=str,
        default=None,
        help="Ruta a una imagen individual para adjuntar.",
    )
    parser.add_argument(
        "--ignore-history",
        "--force",
        dest="ignore_history",
        action="store_true",
        help="Ignora el historial de publicaciones previas y procesa todos los grupos de la lista.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    config = PosterConfig()

    groups_file = Path(args.groups_file) if args.groups_file else config.groups_file
    batch_size = args.batch_size if args.batch_size else config.batch_size

    poster = FacebookGroupPoster(config)

    # 1. Login flow
    if args.login:
        poster.run_login_flow()
        sys.exit(0)

    # 2. Single group test
    if args.single:
        try:
            bundle = resolve_post_bundle(args, config)
        except Exception as e:
            logger.error(str(e))
            sys.exit(1)

        print("\n" + "=" * 60)
        print(f"Directorio de contenido: {bundle.source_dir}")
        print(f"Texto ({len(bundle.text)} caracteres): {bundle.text[:80]}...")
        print(f"Multimedia adjunta ({bundle.media_count}): {[p.name for p in bundle.media_paths]}")
        print("=" * 60 + "\n")

        poster.start_session(force_visible=True)
        try:
            res = poster.post_to_group(
                group_url=args.single,
                message=bundle.text,
                media_paths=bundle.media_paths,
                dry_run=args.dry_run,
            )
            print(f"\nResultado de la prueba individual: {res}\n")
        finally:
            poster.close_session()
        sys.exit(0)

    # 3. Batch campaign run or dry-run
    # Executes if --run or --dry-run is passed, or if --groups-file or --path are specified
    should_run_campaign = (
        args.run
        or args.dry_run
        or (args.groups_file is not None)
        or (args.post_dir is not None)
    )
    if should_run_campaign:
        try:
            bundle = resolve_post_bundle(args, config)
        except Exception as e:
            logger.error(str(e))
            sys.exit(1)

        if not groups_file.exists():
            logger.error(
                f"El archivo con las URLs de grupos no existe: {groups_file}\n"
                f"Crea un archivo '{groups_file.name}' con una URL de grupo por línea."
            )
            sys.exit(1)

        manager = GroupBatchManager(
            groups_file=groups_file,
            history_file=config.history_file,
            batch_size=batch_size,
        )

        initial_stats = manager.get_stats()
        logger.info(f"Historial previo: {initial_stats}")
        logger.info(
            f"Configuración de campaña: Tanda={batch_size} grupos, "
            f"Intervalo entre posts={config.min_post_delay}-{config.max_post_delay}s, "
            f"Pausa entre tandas={config.batch_cooldown}s"
        )
        logger.info(
            f"Contenido a publicar desde: {bundle.source_dir} | "
            f"Multimedia ({bundle.media_count}): {[p.name for p in bundle.media_paths]}"
        )

        poster.execute_campaign(
            manager=manager,
            message=bundle.text,
            media_paths=bundle.media_paths,
            dry_run=args.dry_run,
            ignore_history=args.ignore_history,
        )
        sys.exit(0)

    # If no action specified, display help
    print(
        "\nUso sugerido:\n"
        "  1. Iniciar sesión por primera vez:      python main.py --login\n"
        "  2. Probar en un grupo (modo simulación): python main.py --single <URL_GRUPO> --path <CARPETA> --dry-run\n"
        "  3. Probar en un grupo (publicación real):python main.py --single <URL_GRUPO> --path <CARPETA>\n"
        "  4. Ejecutar campaña por tandas:         python main.py --run --path <CARPETA>\n"
        "  5. Ver opciones disponibles:            python main.py --help\n"
    )


if __name__ == "__main__":
    main()
