from __future__ import annotations

from dataclasses import dataclass
import logging
import os
import re
import shutil
import subprocess
import time

from pyocirun.oci import LinuxResources

logger = logging.getLogger(__name__)

CGROUP2_ROOT = "/sys/fs/cgroup"


@dataclass
class CgroupHandle:
    path: str
    unit_name: str | None = None


def is_cgroup_v2() -> bool:
    controllers = os.path.join(CGROUP2_ROOT, "cgroup.controllers")
    return os.path.isfile(controllers)


def _read_cgroup2_rel_path() -> str:
    try:
        with open("/proc/self/cgroup", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("0::"):
                    rel = line[3:].strip().lstrip("/")
                    return rel
    except OSError:
        pass
    return ""


def current_cgroup_path() -> str:
    rel = _read_cgroup2_rel_path()
    if not rel:
        return CGROUP2_ROOT
    return os.path.join(CGROUP2_ROOT, rel)


def sanitize_cgroup_name(s: str) -> str:
    if not s:
        return "container"
    out = re.sub(r"[^a-zA-Z0-9_.-]", "_", s)
    return out[:200] if len(out) > 200 else out


def _run_command(args: list[str]) -> str:
    proc = subprocess.run(
        args,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return proc.stdout.strip()


def _systemctl(*args: str) -> str:
    return _run_command(["systemctl", *args])


def _make_unit_name(utility_name: str, container_id: str) -> str:
    base = sanitize_cgroup_name(f"{utility_name}-{container_id}")
    return f"pyocirun-{base}.service"


def _stop_unit_best_effort(unit_name: str) -> None:
    try:
        _systemctl("stop", unit_name)
    except Exception:
        pass
    try:
        _systemctl("reset-failed", unit_name)
    except Exception:
        pass


def _create_systemd_unit(utility_name: str, container_id: str) -> CgroupHandle:
    if shutil.which("systemd-run") is None or shutil.which("systemctl") is None:
        raise RuntimeError("systemd-run/systemctl недоступны в PATH")

    unit_name = _make_unit_name(utility_name, container_id)
    _stop_unit_best_effort(unit_name)

    _run_command(
        [
            "systemd-run",
            "--quiet",
            "--unit",
            unit_name,
            "--property=Delegate=yes",
            "--property=TasksMax=infinity",
            "sleep",
            "infinity",
        ]
    )

    control_group = _systemctl("show", "--property=ControlGroup", "--value", unit_name)
    if not control_group:
        raise RuntimeError(f"systemd не вернул ControlGroup для юнита {unit_name}")

    cgroup_path = os.path.join(CGROUP2_ROOT, control_group.lstrip("/"))
    for _ in range(20):
        if os.path.isdir(cgroup_path):
            return CgroupHandle(path=cgroup_path, unit_name=unit_name)
        time.sleep(0.05)
    raise RuntimeError(f"ControlGroup не появился на файловой системе: {cgroup_path}")


def _write_file(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _apply_limits(cgroup_path: str, resources: LinuxResources) -> None:
    if resources.cpu:
        q, p = resources.cpu.quota, resources.cpu.period
        if q is not None and p is not None and p > 0:
            if q <= 0:
                _write_file(os.path.join(cgroup_path, "cpu.max"), "max\n")
            else:
                _write_file(
                    os.path.join(cgroup_path, "cpu.max"),
                    f"{q} {p}\n",
                )
    if resources.memory and resources.memory.limit is not None:
        lim = resources.memory.limit
        if lim <= 0:
            _write_file(os.path.join(cgroup_path, "memory.max"), "max\n")
        else:
            _write_file(
                os.path.join(cgroup_path, "memory.max"),
                f"{lim}\n",
            )

    dev_rates: dict[tuple[int, int], tuple[int | None, int | None]] = {}
    for t in resources.block_io_read_bps:
        key = (t.major, t.minor)
        r, w = dev_rates.get(key, (None, None))
        dev_rates[key] = (t.rate, w)
    for t in resources.block_io_write_bps:
        key = (t.major, t.minor)
        r, w = dev_rates.get(key, (None, None))
        dev_rates[key] = (r, t.rate)

    if dev_rates:
        lines: list[str] = []
        for (maj, mino), (rbps, wbps) in dev_rates.items():
            parts = [f"{maj}:{mino}"]
            if rbps is not None:
                parts.append(f"rbps={rbps}")
            if wbps is not None:
                parts.append(f"wbps={wbps}")
            lines.append(" ".join(parts))
        _write_file(os.path.join(cgroup_path, "io.max"), "\n".join(lines) + "\n")


def prepare_cgroup(
    utility_name: str,
    container_id: str,
    resources: LinuxResources,
) -> CgroupHandle | None:
    if not is_cgroup_v2():
        logger.warning("cgroups v2 не обнаружены, пропуск лимитов")
        return None

    if (
        not resources.cpu
        and not resources.memory
        and not resources.block_io_read_bps
        and not resources.block_io_write_bps
    ):
        return None

    handle: CgroupHandle | None = None
    try:
        handle = _create_systemd_unit(utility_name, container_id)
        _apply_limits(handle.path, resources)
        return handle
    except (OSError, RuntimeError, subprocess.CalledProcessError) as e:
        if handle is not None:
            cleanup_cgroup(handle)
        logger.warning(
            "Не удалось настроить cgroups через systemd, лимиты пропущены (можно использовать --no-cgroup): %s",
            e,
        )
        return None


def attach_pid(cgroup_path: str, pid: int) -> None:
    procs = os.path.join(cgroup_path, "cgroup.procs")
    try:
        _write_file(procs, f"{pid}\n")
    except OSError as e:
        logger.warning("Не удалось привязать pid %s к %s: %s", pid, cgroup_path, e)


def cleanup_cgroup(handle: CgroupHandle | None) -> None:
    if handle is None or handle.unit_name is None:
        return
    _stop_unit_best_effort(handle.unit_name)
