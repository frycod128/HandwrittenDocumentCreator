from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

from tools import bootstrap


ROOT = Path(__file__).resolve().parent.parent


class BootstrapTests(unittest.TestCase):
    def test_project_root_points_to_the_repository(self) -> None:
        self.assertEqual(bootstrap.PROJECT_ROOT, ROOT)
        self.assertTrue((ROOT / "main.py").is_file())
        self.assertTrue((ROOT / "requirements.txt").is_file())

    def test_venv_python_uses_platform_layout(self) -> None:
        python = bootstrap.venv_python(ROOT / ".venv")
        self.assertEqual(python.name, "python.exe" if bootstrap.IS_WINDOWS else "python")
        self.assertIn(python.parent.name, {"Scripts", "bin"})

    def test_probe_reads_the_running_interpreter(self) -> None:
        interpreter = bootstrap.probe_interpreter([sys.executable])
        self.assertIsNotNone(interpreter)
        assert interpreter is not None
        self.assertGreaterEqual(interpreter.version[:2], bootstrap.MIN_PYTHON)
        self.assertTrue(interpreter.executable.is_file())

    def test_probe_rejects_a_missing_interpreter(self) -> None:
        self.assertIsNone(bootstrap.probe_interpreter([str(ROOT / "no-such-python.exe")]))

    def test_requirements_digest_tracks_the_file(self) -> None:
        expected = hashlib.sha256((ROOT / "requirements.txt").read_bytes()).hexdigest()
        self.assertEqual(bootstrap.requirements_digest(), expected)

    def test_remove_tree_refuses_paths_outside_the_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            outsider = Path(directory) / "outside"
            outsider.mkdir()
            with self.assertRaises(bootstrap.BootstrapError):
                bootstrap._remove_tree(outsider)
            self.assertTrue(outsider.is_dir())

    def test_project_venv_is_detected_as_a_virtual_environment(self) -> None:
        venv = ROOT / ".venv"
        if not (venv / "pyvenv.cfg").is_file():
            self.skipTest("项目内还没有 .venv")
        python = bootstrap.venv_python(venv)
        self.assertTrue(bootstrap._looks_like_venv(python))

    def test_existing_project_venv_passes_health_check(self) -> None:
        venv = ROOT / ".venv"
        if not (venv / "pyvenv.cfg").is_file():
            self.skipTest("项目内还没有 .venv")
        health = bootstrap.check_environment(venv, need_tk=False)
        self.assertTrue(health.ok, health.reason)
        if bootstrap.IS_WINDOWS and health.tkinter:
            self.assertTrue(bootstrap.check_environment(venv, need_tk=True).ok)

    def test_check_mode_never_creates_a_venv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            venv = Path(directory) / "venv"
            self.assertEqual(bootstrap.main(["--venv-dir", str(venv), "--check"]), 1)
            self.assertFalse(venv.exists())


if __name__ == "__main__":
    unittest.main()
