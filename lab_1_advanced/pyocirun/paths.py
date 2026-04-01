from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_UTILITY_NAME = "pyocirun"
STATE_ROOT = "/var/lib"


@dataclass(frozen=True)
class ContainerPaths:
    """Каталоги overlay и состояния для одного контейнера."""

    base: str
    upper: str
    work: str
    merged: str


def state_base(utility_name: str, container_id: str) -> str:
    return os.path.join(STATE_ROOT, utility_name, container_id)


def container_paths(utility_name: str, container_id: str) -> ContainerPaths:
    base = state_base(utility_name, container_id)
    return ContainerPaths(
        base=base,
        upper=os.path.join(base, "upper"),
        work=os.path.join(base, "work"),
        merged=os.path.join(base, "merged"),
    )


def ensure_container_dirs(paths: ContainerPaths) -> None:
    os.makedirs(paths.upper, mode=0o755, exist_ok=True)
    os.makedirs(paths.work, mode=0o755, exist_ok=True)
    os.makedirs(paths.merged, mode=0o755, exist_ok=True)
