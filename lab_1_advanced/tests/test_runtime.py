import unittest
from unittest import mock

from pyocirun import cgroups_v2, runtime
from pyocirun.oci import OciConfig, ProcessConfig
from pyocirun.paths import ContainerPaths


class RuntimeTests(unittest.TestCase):
    def _oci(self):
        return OciConfig(
            hostname="host1",
            root_path="/lower",
            process=ProcessConfig(args=["/bin/sh", "-c", "echo hi"], cwd="/", env=["A=B"]),
            linux_resources=None,
        )

    def _paths(self):
        return ContainerPaths(
            base="/var/lib/pyocirun/demo",
            upper="/var/lib/pyocirun/demo/upper",
            work="/var/lib/pyocirun/demo/work",
            merged="/var/lib/pyocirun/demo/merged",
        )

    @mock.patch("pyocirun.runtime.os.execvpe")
    @mock.patch("pyocirun.runtime.mount_proc")
    @mock.patch("pyocirun.runtime.os.makedirs")
    @mock.patch("pyocirun.runtime.os.chdir")
    @mock.patch("pyocirun.runtime.os.chroot")
    @mock.patch("pyocirun.runtime.mount_overlay")
    @mock.patch("pyocirun.runtime.mount_make_rprivate")
    @mock.patch("pyocirun.runtime._set_hostname")
    def test_child_main_configures_namespace_and_exec(
        self,
        set_hostname,
        make_rprivate,
        mount_overlay,
        chroot,
        chdir,
        makedirs,
        mount_proc,
        execvpe,
    ):
        runtime._child_main(self._oci(), self._paths(), do_mount_proc=True)

        set_hostname.assert_called_once_with("host1")
        make_rprivate.assert_called_once_with("/")
        mount_overlay.assert_called_once_with(
            "/lower",
            "/var/lib/pyocirun/demo/upper",
            "/var/lib/pyocirun/demo/work",
            "/var/lib/pyocirun/demo/merged",
        )
        chroot.assert_called_once_with("/var/lib/pyocirun/demo/merged")
        self.assertGreaterEqual(chdir.call_count, 2)
        makedirs.assert_called_once_with("/proc", mode=0o555, exist_ok=True)
        mount_proc.assert_called_once_with("/proc")
        execvpe.assert_called_once()

    @mock.patch("pyocirun.runtime.umount_lazy")
    @mock.patch("pyocirun.runtime.cgroups_v2.cleanup_cgroup")
    @mock.patch("pyocirun.runtime.os.waitpid", return_value=(3456, 0))
    @mock.patch("pyocirun.runtime.cgroups_v2.attach_pid")
    @mock.patch("pyocirun.runtime.os.fork", return_value=3456)
    @mock.patch("pyocirun.runtime._unshare")
    @mock.patch(
        "pyocirun.runtime.cgroups_v2.prepare_cgroup",
        return_value=cgroups_v2.CgroupHandle(path="/cg/demo", unit_name="u.service"),
    )
    @mock.patch("pyocirun.runtime.ensure_container_dirs")
    def test_run_container_parent_flow(
        self,
        ensure_dirs,
        prepare_cgroup,
        unshare,
        fork,
        attach_pid,
        waitpid,
        cleanup_cgroup,
        umount_lazy,
    ):
        oci = self._oci()
        oci.linux_resources = object()
        code = runtime.run_container(
            oci,
            self._paths(),
            utility_name="pyocirun",
            container_id="demo",
            do_mount_proc=True,
            use_cgroup=True,
        )

        ensure_dirs.assert_called_once()
        prepare_cgroup.assert_called_once()
        unshare.assert_called_once_with(runtime.CLONE_NEWNS | runtime.CLONE_NEWUTS | runtime.CLONE_NEWPID)
        fork.assert_called_once()
        attach_pid.assert_called_once_with("/cg/demo", 3456)
        waitpid.assert_called_once_with(3456, 0)
        self.assertEqual(code, 0)
        self.assertEqual(umount_lazy.call_args_list[0].args[0], "/var/lib/pyocirun/demo/merged/proc")
        self.assertEqual(umount_lazy.call_args_list[1].args[0], "/var/lib/pyocirun/demo/merged")
        cleanup_cgroup.assert_called_once()

    @mock.patch("pyocirun.runtime.platform.system", return_value="Darwin")
    def test_unshare_rejects_non_linux(self, _):
        with self.assertRaises(OSError):
            runtime._unshare(0)


if __name__ == "__main__":
    unittest.main()
