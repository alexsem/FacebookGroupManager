"""CLI Entrypoint for Facebook Group Batch Poster.

Allows running initial login setup, dry runs, single group testing,
and full campaign execution in batches.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from config import PosterConfig
from batch_manager import GroupBatchManager
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
        help="Modo de prueba: navega, escribe el post pero NO hace clic en Publicar.",
    )
    parser.add_argument(
        "--single",
        type=str,
        default=None,
        help="URL de un único grupo para realizar una prueba individual.",
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
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    config = PosterConfig()

    # Override files if passed via CLI
    groups_file = Path(args.groups_file) if args.groups_file else config.groups_file
    post_file = Path(args.post_file) if args.post_file else config.post_file
    batch_size = args.batch_size if args.batch_size else config.batch_size

    poster = FacebookGroupPoster(config)

    # 1. Login flow
    if args.login:
        poster.run_login_flow()
        sys.exit(0)

    # 2. Single group test
    if args.single:
        try:
            message = load_post_content(post_file)
        except Exception as e:
            logger.error(str(e))
            sys.exit(1)

        poster.start_session(force_visible=True)
        try:
            res = poster.post_to_group(
                group_url=args.single,
                message=message,
                image_path=config.image_path,
                dry_run=args.dry_run,
            )
            print(f"\nResultado de la prueba individual: {res}\n")
        finally:
            poster.close_session()
        sys.exit(0)

    # 3. Batch campaign run or dry-run
    if args.run or args.dry_run:
        try:
            message = load_post_content(post_file)
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

        poster.execute_campaign(
            manager=manager,
            message=message,
            image_path=config.image_path,
            dry_run=args.dry_run,
        )
        sys.exit(0)

    # If no action specified, display help
    print(
        "\nUso sugerido:\n"
        "  1. Iniciar sesión por primera vez:   python main.py --login\n"
        "  2. Probar en un grupo de prueba:     python main.py --single <URL_GRUPO> --dry-run\n"
        "  3. Ejecutar campaña por tandas:      python main.py --run\n"
        "  4. Ver opciones disponibles:         python main.py --help\n"
    )


if __name__ == "__main__":
    main()
