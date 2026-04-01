from __future__ import annotations

import ctypes
import ctypes.util
import logging
import os
import platform
import sys

from pyocirun import cgroups_v2
from pyocirun.mount import mount_make_rprivate, mount_overlay, mount_proc, umount_lazy
from pyocirun.oci import OciConfig
from pyocirun.paths import ContainerPaths, ensure_container_dirs

logger = logging.getLogger(__name__)

CLONE_NEWNS = 0x00020000
CLONE_NEWUTS = 0x04000000
CLONE_NEWPID = 0x20000000


def _unshare(flags: int) -> None:
    if platform.system() != "Linux":
        raise OSError("Поддерживается только Linux")
    if hasattr(os, "unshare"):
        os.unshare(flags)
        return
    libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    libc.unshare.argtypes = [ctypes.c_int]
    libc.unshare.restype = ctypes.c_int
    if libc.unshare(flags) != 0:
        errno = ctypes.get_errno()
        raise OSError(errno, os.strerror(errno))


def _env_dict_from_oci(envlist: list[str] | None) -> dict[str, str]:
    if not envlist:
        return dict(os.environ)
    out: dict[str, str] = {}
    for e in envlist:
        if "=" in e:
            k, _, v = e.partition("=")
            out[k] = v
        else:
            out[e] = ""
    return out


def _set_hostname(name: str) -> None:
    if hasattr(os, "sethostname"):
        os.sethostname(name)
        return
    libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    buf = name.encode("utf-8")
    if libc.sethostname(buf, len(buf)) != 0:
        errno = ctypes.get_errno()
        raise OSError(errno, os.strerror(errno))


def _child_main(
    oci: OciConfig,
    paths: ContainerPaths,
    *,
    do_mount_proc: bool,
) -> None:
    _set_hostname(oci.hostname)
    mount_make_rprivate("/")
    mount_overlay(oci.root_path, paths.upper, paths.work, paths.merged)
    os.chroot(paths.merged)
    os.chdir("/")
    if oci.process.cwd:
        os.chdir(oci.process.cwd)
    if do_mount_proc:
        os.makedirs("/proc", mode=0o555, exist_ok=True)
        mount_proc("/proc")
    env = _env_dict_from_oci(oci.process.env)
    args = oci.process.args
    os.execvpe(args[0], args, env)


def _wait_status_to_code(status: int) -> int:
    if os.WIFEXITED(status):
        return os.WEXITSTATUS(status)
    if os.WIFSIGNALED(status):
        return 128 + os.WTERMSIG(status)
    return 1


def run_container(
    oci: OciConfig,
    paths: ContainerPaths,
    *,
    utility_name: str,
    container_id: str,
    do_mount_proc: bool,
    use_cgroup: bool,
) -> int:
    ensure_container_dirs(paths)

    cgroup_handle: cgroups_v2.CgroupHandle | None = None
    if use_cgroup and oci.linux_resources is not None:
        cgroup_handle = cgroups_v2.prepare_cgroup(
            utility_name, container_id, oci.linux_resources
        )

    flags = CLONE_NEWNS | CLONE_NEWUTS | CLONE_NEWPID
    _unshare(flags)

    pid = os.fork()
    if pid == 0:
        try:
            _child_main(oci, paths, do_mount_proc=do_mount_proc)
        except Exception as e:
            print(f"pyocirun (child): {e}", file=sys.stderr)
            os._exit(127)
        os._exit(127)

    if cgroup_handle:
        cgroups_v2.attach_pid(cgroup_handle.path, pid)

    _, status = os.waitpid(pid, 0)
    code = _wait_status_to_code(status)
    try:
        if do_mount_proc:
            umount_lazy(os.path.join(paths.merged, "proc"))
        umount_lazy(paths.merged)
    except OSError as e:
        logger.debug("umount: %s", e)
    finally:
        cgroups_v2.cleanup_cgroup(cgroup_handle)

    return code
