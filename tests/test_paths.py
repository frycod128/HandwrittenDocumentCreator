from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from handwriting_doc import paths


class DownloadFolderTests(unittest.TestCase):
    def test_candidates_are_absolute_and_unique(self) -> None:
        candidates = paths.downloads_candidates()
        self.assertTrue(candidates)
        self.assertTrue(all(path.is_absolute() for path in candidates))
        keys = [str(path).casefold() for path in candidates]
        self.assertEqual(len(keys), len(set(keys)))

    def test_candidates_always_end_with_home_downloads(self) -> None:
        candidates = paths.downloads_candidates()
        self.assertEqual(candidates[-1], Path.home() / "Downloads")

    def test_default_downloads_dir_is_one_of_the_candidates(self) -> None:
        directory = paths.default_downloads_dir()
        self.assertTrue(directory.is_absolute())
        self.assertIn(directory, paths.downloads_candidates())

    def test_default_output_dir_is_writable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            resolved = paths.default_output_dir(directory)
            self.assertTrue(resolved.is_dir())
            self.assertTrue(os.access(resolved, os.W_OK))

    def test_falls_back_to_project_output_when_downloads_is_unusable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            blocker = project / "blocker"
            blocker.write_text("not a directory", encoding="utf-8")
            with mock.patch.object(paths, "downloads_candidates", return_value=[blocker / "Downloads"]):
                resolved = paths.default_output_dir(project)
            self.assertEqual(resolved, project / "output")
            self.assertTrue(resolved.is_dir())

    def test_xdg_user_dirs_are_honoured(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "home"
            home.mkdir()
            config = Path(directory) / "config"
            (config / "user-dirs.dirs").parent.mkdir(parents=True)
            (config / "user-dirs.dirs").write_text(
                'XDG_DOWNLOAD_DIR="$HOME/下载"\n', encoding="utf-8"
            )
            with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(config)}, clear=False):
                with mock.patch.object(paths.Path, "home", return_value=home):
                    resolved = paths._posix_folder()
            self.assertEqual(resolved, home / "下载")


if __name__ == "__main__":
    unittest.main()
