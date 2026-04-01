from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProcessConfig:
    args: list[str]
    cwd: str | None
    env: list[str] | None


@dataclass
class CpuResources:
    quota: int | None = None
    period: int | None = None


@dataclass
class MemoryResources:
    limit: int | None = None


@dataclass
class BlockIODeviceThrottle:
    major: int
    minor: int
    rate: int


@dataclass
class LinuxResources:
    cpu: CpuResources | None = None
    memory: MemoryResources | None = None
    block_io_read_bps: list[BlockIODeviceThrottle] = field(default_factory=list)
    block_io_write_bps: list[BlockIODeviceThrottle] = field(default_factory=list)


@dataclass
class OciConfig:
    hostname: str
    root_path: str
    process: ProcessConfig
    linux_resources: LinuxResources | None


def _parse_block_throttle(entries: Any) -> list[BlockIODeviceThrottle]:
    if not isinstance(entries, list):
        return []
    out: list[BlockIODeviceThrottle] = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        try:
            major = int(e["major"])
            minor = int(e["minor"])
            rate = int(e["rate"])
        except (KeyError, TypeError, ValueError):
            continue
        out.append(BlockIODeviceThrottle(major=major, minor=minor, rate=rate))
    return out


def load_oci_config(config_path: str | os.PathLike[str]) -> OciConfig:
    path = Path(config_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"config.json не найден: {path}")
    with path.open(encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        raise ValueError("config.json должен быть JSON-объектом")

    hostname = raw.get("hostname")
    if hostname is None or not isinstance(hostname, str) or not hostname:
        hostname = "pyocirun"

    root = raw.get("root")
    if not isinstance(root, dict):
        raise ValueError("Отсутствует или неверно поле root")
    root_path_rel = root.get("path")
    if not isinstance(root_path_rel, str) or not root_path_rel:
        raise ValueError("root.path обязателен и должен быть непустой строкой")

    bundle_dir = path.parent
    root_path = (bundle_dir / root_path_rel).resolve()
    if not root_path.is_dir():
        raise NotADirectoryError(f"root.path не указывает на каталог: {root_path}")

    proc = raw.get("process")
    if not isinstance(proc, dict):
        raise ValueError("Отсутствует или неверно поле process")
    args = proc.get("args")
    if not isinstance(args, list) or not args or not all(isinstance(a, str) for a in args):
        raise ValueError("process.args обязателен: непустой массив строк")

    cwd = proc.get("cwd")
    if cwd is not None and not isinstance(cwd, str):
        raise ValueError("process.cwd должен быть строкой или отсутствовать")

    env = proc.get("env")
    if env is not None:
        if not isinstance(env, list) or not all(isinstance(x, str) for x in env):
            raise ValueError("process.env должен быть массивом строк или отсутствовать")

    linux_resources: LinuxResources | None = None
    linux = raw.get("linux")
    if isinstance(linux, dict):
        res = linux.get("resources")
        if isinstance(res, dict):
            lr = LinuxResources()
            cpu = res.get("cpu")
            if isinstance(cpu, dict):
                q = cpu.get("quota")
                p = cpu.get("period")
                if q is not None or p is not None:
                    lr.cpu = CpuResources(
                        quota=int(q) if q is not None else None,
                        period=int(p) if p is not None else None,
                    )
            mem = res.get("memory")
            if isinstance(mem, dict) and mem.get("limit") is not None:
                lr.memory = MemoryResources(limit=int(mem["limit"]))
            bio = res.get("blockIO")
            if isinstance(bio, dict):
                lr.block_io_read_bps = _parse_block_throttle(bio.get("throttleReadBpsDevice"))
                lr.block_io_write_bps = _parse_block_throttle(bio.get("throttleWriteBpsDevice"))
            if (
                lr.cpu
                or lr.memory
                or lr.block_io_read_bps
                or lr.block_io_write_bps
            ):
                linux_resources = lr

    return OciConfig(
        hostname=hostname,
        root_path=str(root_path),
        process=ProcessConfig(args=args, cwd=cwd, env=env),
        linux_resources=linux_resources,
    )
