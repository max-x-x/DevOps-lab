import json
import tempfile
import unittest
from pathlib import Path

from pyocirun.oci import load_oci_config


class OciConfigTests(unittest.TestCase):
    def test_load_oci_config_parses_required_and_optional_fields(self):
        with tempfile.TemporaryDirectory() as td:
            bundle = Path(td)
            rootfs = bundle / "rootfs"
            rootfs.mkdir()
            cfg = {
                "hostname": "demo-host",
                "root": {"path": "rootfs"},
                "process": {
                    "args": ["/bin/sh", "-c", "echo ok"],
                    "cwd": "/",
                    "env": ["A=B"],
                },
                "linux": {
                    "resources": {
                        "cpu": {"quota": 50000, "period": 100000},
                        "memory": {"limit": 134217728},
                        "blockIO": {
                            "throttleReadBpsDevice": [{"major": 8, "minor": 0, "rate": 1048576}],
                            "throttleWriteBpsDevice": [{"major": 8, "minor": 0, "rate": 2097152}],
                        },
                    }
                },
            }
            config_path = bundle / "config.json"
            config_path.write_text(json.dumps(cfg), encoding="utf-8")

            oci = load_oci_config(config_path)

            self.assertEqual(oci.hostname, "demo-host")
            self.assertEqual(Path(oci.root_path), rootfs.resolve())
            self.assertEqual(oci.process.args[0], "/bin/sh")
            self.assertEqual(oci.process.cwd, "/")
            self.assertEqual(oci.process.env, ["A=B"])
            self.assertIsNotNone(oci.linux_resources)
            self.assertEqual(oci.linux_resources.cpu.quota, 50000)
            self.assertEqual(oci.linux_resources.cpu.period, 100000)
            self.assertEqual(oci.linux_resources.memory.limit, 134217728)
            self.assertEqual(oci.linux_resources.block_io_read_bps[0].rate, 1048576)
            self.assertEqual(oci.linux_resources.block_io_write_bps[0].rate, 2097152)

    def test_load_oci_config_raises_on_invalid_process_args(self):
        with tempfile.TemporaryDirectory() as td:
            bundle = Path(td)
            (bundle / "rootfs").mkdir()
            cfg = {
                "root": {"path": "rootfs"},
                "process": {"args": []},
            }
            config_path = bundle / "config.json"
            config_path.write_text(json.dumps(cfg), encoding="utf-8")

            with self.assertRaises(ValueError):
                load_oci_config(config_path)


if __name__ == "__main__":
    unittest.main()
