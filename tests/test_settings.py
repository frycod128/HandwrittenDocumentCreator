from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from handwriting_doc import settings


class SettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = settings.settings_path(self.root)
        self.defaults = settings.default_config(self.root / "Downloads")

    def test_missing_file_is_created_with_defaults(self) -> None:
        self.assertFalse(self.path.exists())
        loaded = settings.load_or_create(self.path, self.defaults)
        self.assertEqual(loaded.status, "created")
        self.assertTrue(self.path.is_file())
        on_disk = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(on_disk, self.defaults)
        self.assertEqual(loaded.config, self.defaults)

    def test_invalid_json_is_replaced(self) -> None:
        self.path.write_text("{not json", encoding="utf-8")
        loaded = settings.load_or_create(self.path, self.defaults)
        self.assertEqual(loaded.status, "repaired")
        self.assertEqual(loaded.config, self.defaults)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), self.defaults)

    def test_out_of_range_values_are_replaced(self) -> None:
        broken = dict(self.defaults, line_count="0")
        self.path.write_text(json.dumps(broken), encoding="utf-8")
        loaded = settings.load_or_create(self.path, self.defaults)
        self.assertEqual(loaded.status, "repaired")
        self.assertEqual(loaded.config["line_count"], "52")

    def test_wrong_types_are_replaced(self) -> None:
        for mutation in (
            {"pdf": "yes"},
            {"selected_fonts": "a.gfont"},
            {"seed": "abc"},
            {"output_dir": ""},
            {"version": 99},
        ):
            with self.subTest(mutation=mutation):
                self.path.write_text(json.dumps(dict(self.defaults, **mutation)), encoding="utf-8")
                loaded = settings.load_or_create(self.path, self.defaults)
                self.assertEqual(loaded.status, "repaired")
                self.assertEqual(loaded.config, self.defaults)

    def test_round_trip_keeps_every_ui_field(self) -> None:
        config = {
            "version": settings.CURRENT_VERSION,
            "line_count": "46",
            "seed": "-2026",
            "output_dir": r"D:\Users\Admin\Downloads",
            "base_name": "我的文档",
            "pdf": False,
            "docx": True,
            "search": "楷体",
            "preview_char": "字",
            "selected_fonts": ["字体素材/楷体_kvenjoy_大孔龙.gfont", "字体素材/熊仔.gfont"],
        }
        settings.save_settings(self.path, config)
        loaded = settings.load_or_create(self.path, self.defaults)
        self.assertEqual(loaded.status, "loaded")
        self.assertEqual(loaded.config, config)

    def test_unknown_keys_are_dropped_and_rewritten(self) -> None:
        payload = dict(self.defaults, legacy="x")
        self.path.write_text(json.dumps(payload), encoding="utf-8")
        loaded = settings.load_or_create(self.path, self.defaults)
        self.assertEqual(loaded.status, "repaired")
        self.assertNotIn("legacy", json.loads(self.path.read_text(encoding="utf-8")))

    def test_save_rejects_invalid_values_without_touching_file(self) -> None:
        settings.save_settings(self.path, self.defaults)
        before = self.path.read_text(encoding="utf-8")
        with self.assertRaises(ValueError):
            settings.save_settings(self.path, dict(self.defaults, line_count="abc"))
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)

    def test_save_is_atomic_and_leaves_no_temporary_file(self) -> None:
        settings.save_settings(self.path, self.defaults)
        leftovers = [item.name for item in self.root.iterdir() if item.name.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_document_text_is_not_part_of_the_schema(self) -> None:
        settings.save_settings(self.path, self.defaults)
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        for forbidden in ("text", "content", "document", "body"):
            self.assertNotIn(forbidden, payload)

    def test_tolerates_numeric_strings_and_truncates_preview_char(self) -> None:
        payload = dict(self.defaults, line_count=52, preview_char="汉字")
        self.path.write_text(json.dumps(payload), encoding="utf-8")
        loaded = settings.load_or_create(self.path, self.defaults)
        self.assertEqual(loaded.status, "repaired")
        self.assertEqual(loaded.config["line_count"], "52")
        self.assertEqual(loaded.config["preview_char"], "汉")


if __name__ == "__main__":
    unittest.main()
