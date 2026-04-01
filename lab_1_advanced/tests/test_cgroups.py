import os
import tempfile
import unittest
from unittest import mock

from pyocirun import cgroups_v2
from pyocirun.oci import BlockIODeviceThrottle, CpuResources, LinuxResources, MemoryResources


class CgroupsTests(unittest.TestCase):
    def test_sanitize_cgroup_name(self):
        self.assertEqual(cgroups_v2.sanitize_cgroup_name("a/b:c"), "a_b_c")

    def test_prepare_cgroup_writes_limits(self):
        with tempfile.TemporaryDirectory() as td:
            root = td
            rel = "system.slice/pyocirun-id1.service"
            cgroup_path = os.path.join(root, rel)
            os.makedirs(cgroup_path, exist_ok=True)
            with open(os.path.join(root, "cgroup.controllers"), "w", encoding="utf-8") as f:
                f.write("cpu memory io\n")

            resources = LinuxResources(
                cpu=CpuResources(quota=50000, period=100000),
                memory=MemoryResources(limit=104857600),
                block_io_read_bps=[BlockIODeviceThrottle(major=8, minor=0, rate=1000)],
                block_io_write_bps=[BlockIODeviceThrottle(major=8, minor=0, rate=2000)],
            )

            def _run_command_side_effect(args):
                if args[0] == "systemd-run":
                    return ""
                if args[:3] == ["systemctl", "show", "--property=ControlGroup"]:
                    return f"/{rel}"
                if args[0] == "systemctl":
                    return ""
                raise AssertionError(f"unexpected command: {args}")

            with (
                mock.patch.object(cgroups_v2, "CGROUP2_ROOT", root),
                mock.patch.object(cgroups_v2, "_run_command", side_effect=_run_command_side_effect),
                mock.patch("pyocirun.cgroups_v2.shutil.which", return_value="/bin/systemctl"),
            ):
                cg = cgroups_v2.prepare_cgroup("pyocirun", "id1", resources)

            self.assertIsNotNone(cg)
            self.assertEqual(cg.path, cgroup_path)
            self.assertEqual(cg.unit_name, "pyocirun-pyocirun-id1.service")
            with open(os.path.join(cgroup_path, "cpu.max"), encoding="utf-8") as f:
                self.assertEqual(f.read().strip(), "50000 100000")
            with open(os.path.join(cgroup_path, "memory.max"), encoding="utf-8") as f:
                self.assertEqual(f.read().strip(), "104857600")
            with open(os.path.join(cgroup_path, "io.max"), encoding="utf-8") as f:
                data = f.read().strip()
                self.assertIn("8:0", data)
                self.assertIn("rbps=1000", data)
                self.assertIn("wbps=2000", data)

    def test_prepare_cgroup_returns_none_when_systemd_is_unavailable(self):
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "cgroup.controllers"), "w", encoding="utf-8") as f:
                f.write("cpu memory io\n")

            resources = LinuxResources(cpu=CpuResources(quota=10000, period=100000))
            with (
                mock.patch.object(cgroups_v2, "CGROUP2_ROOT", td),
                mock.patch("pyocirun.cgroups_v2.shutil.which", return_value=None),
            ):
                cg = cgroups_v2.prepare_cgroup("pyocirun", "id2", resources)
            self.assertIsNone(cg)


if __name__ == "__main__":
    unittest.main()
