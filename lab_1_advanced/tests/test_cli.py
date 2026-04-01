import unittest
from unittest import mock

from pyocirun import cli


class CliTests(unittest.TestCase):
    @mock.patch("pyocirun.cli.platform.system", return_value="Darwin")
    def test_main_rejects_non_linux(self, _):
        code = cli.main(["run", "--config", "/tmp/config.json", "--id", "x"])
        self.assertEqual(code, 1)

    @mock.patch("pyocirun.cli.platform.system", return_value="Linux")
    @mock.patch("pyocirun.cli.os.geteuid", return_value=1000)
    def test_main_rejects_non_root(self, *_):
        code = cli.main(["run", "--config", "/tmp/config.json", "--id", "x"])
        self.assertEqual(code, 1)

    @mock.patch("pyocirun.cli.run_container", return_value=7)
    @mock.patch("pyocirun.cli.container_paths", return_value="P")
    @mock.patch("pyocirun.cli.load_oci_config", return_value="OCI")
    @mock.patch("pyocirun.cli.os.geteuid", return_value=0)
    @mock.patch("pyocirun.cli.platform.system", return_value="Linux")
    def test_main_run_success_path(self, *_):
        code = cli.main(["run", "--bundle", "/bundle", "--id", "abc"])
        self.assertEqual(code, 7)


if __name__ == "__main__":
    unittest.main()
