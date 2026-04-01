from __future__ import annotations

import argparse
import logging
import os
import platform
import sys

from pyocirun.oci import load_oci_config
from pyocirun.paths import DEFAULT_UTILITY_NAME, container_paths
from pyocirun.runtime import run_container


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pyocirun",
        description="Запуск процесса по OCI config.json с overlayfs и namespaces (Linux, root).",
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Подробный лог",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Запустить контейнер")
    run_p.add_argument(
        "--config",
        metavar="PATH",
        help="Путь к config.json",
    )
    run_p.add_argument(
        "--bundle",
        metavar="DIR",
        help="Каталог bundle (используется DIR/config.json)",
    )
    run_p.add_argument(
        "--id",
        required=True,
        metavar="ID",
        help="Идентификатор контейнера (каталог под /var/lib/<имя>/<id>/)",
    )
    run_p.add_argument(
        "--utility-name",
        default=DEFAULT_UTILITY_NAME,
        metavar="NAME",
        help=f"Имя утилиты для /var/lib/<name>/ (по умолчанию: {DEFAULT_UTILITY_NAME})",
    )
    run_p.add_argument(
        "--no-proc",
        action="store_true",
        help="Не монтировать /proc внутри контейнера",
    )
    run_p.add_argument(
        "--no-cgroup",
        action="store_true",
        help="Не применять cgroups v2 (по умолчанию используется systemd-run/systemctl для лимитов)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )
    if args.cmd != "run":
        return 2

    if platform.system() != "Linux":
        print("pyocirun: поддерживается только Linux.", file=sys.stderr)
        return 1

    if os.geteuid() != 0:
        print("pyocirun: требуются права root (euid==0).", file=sys.stderr)
        return 1

    config_path: str | None = args.config
    if args.bundle:
        config_path = os.path.join(args.bundle, "config.json")
    if not config_path:
        print("pyocirun: укажите --config или --bundle.", file=sys.stderr)
        return 2

    try:
        oci = load_oci_config(config_path)
    except (OSError, ValueError, NotADirectoryError) as e:
        print(f"pyocirun: {e}", file=sys.stderr)
        return 1

    paths = container_paths(args.utility_name, args.id)
    use_cgroup = not args.no_cgroup

    return run_container(
        oci,
        paths,
        utility_name=args.utility_name,
        container_id=args.id,
        do_mount_proc=not args.no_proc,
        use_cgroup=use_cgroup,
    )


if __name__ == "__main__":
    raise SystemExit(main())
