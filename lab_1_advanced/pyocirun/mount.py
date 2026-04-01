from __future__ import annotations

import subprocess


def mount_make_rprivate(target: str = "/") -> None:
    subprocess.run(
        ["mount", "--make-rprivate", target],
        check=True,
    )


def mount_overlay(lowerdir: str, upperdir: str, workdir: str, merged: str) -> None:
    opts = f"lowerdir={lowerdir},upperdir={upperdir},workdir={workdir}"
    subprocess.run(
        ["mount", "-t", "overlay", "overlay", "-o", opts, merged],
        check=True,
    )


def mount_proc(at: str = "/proc") -> None:
    subprocess.run(
        ["mount", "-t", "proc", "proc", at],
        check=True,
    )


def umount_lazy(target: str) -> None:
    subprocess.run(["umount", "-l", target], check=False)
