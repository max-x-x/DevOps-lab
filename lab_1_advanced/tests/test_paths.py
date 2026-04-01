import os
import tempfile
import unittest

from pyocirun.paths import ContainerPaths, container_paths, ensure_container_dirs


class PathsTests(unittest.TestCase):
    def test_container_paths_shape(self):
        p = container_paths("myrun", "abc123")
        self.assertTrue(p.base.endswith("/var/lib/myrun/abc123"))
        self.assertEqual(p.upper, os.path.join(p.base, "upper"))
        self.assertEqual(p.work, os.path.join(p.base, "work"))
        self.assertEqual(p.merged, os.path.join(p.base, "merged"))

    def test_ensure_container_dirs_creates_overlay_dirs(self):
        with tempfile.TemporaryDirectory() as td:
            base = os.path.join(td, "state", "id1")
            p = ContainerPaths(
                base=base,
                upper=os.path.join(base, "upper"),
                work=os.path.join(base, "work"),
                merged=os.path.join(base, "merged"),
            )
            ensure_container_dirs(p)
            self.assertTrue(os.path.isdir(p.upper))
            self.assertTrue(os.path.isdir(p.work))
            self.assertTrue(os.path.isdir(p.merged))


if __name__ == "__main__":
    unittest.main()
