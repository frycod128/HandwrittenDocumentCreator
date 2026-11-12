from __future__ import annotations

import random
import unittest
from pathlib import Path

from handwriting_doc.gfont import GFont
from handwriting_doc.layout import build_layout, build_metrics


ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "字体素材"


class LayoutTests(unittest.TestCase):
    def test_metrics_leave_space_for_rotation(self) -> None:
        metrics = build_metrics(20)
        self.assertGreater(metrics.row_pitch, metrics.font_size)
        self.assertAlmostEqual(metrics.column_x[1] - metrics.column_x[0] - metrics.column_width, metrics.column_gap)

    def test_layout_has_two_columns_of_requested_height(self) -> None:
        paths = (
            FONT_DIR / "常用_kvenjoy_美文.gfont",
            FONT_DIR / "超连笔快写-3500字_kvenjoy_gantry.gfont",
        )
        with GFont(paths[0]) as first, GFont(paths[1]) as second:
            layout = build_layout(
                "中英文 mixed 文本。" * 260,
                [first, second],
                lines_per_column=8,
                rng=random.Random(20261112),
            )
        self.assertGreater(len(layout.pages), 1)
        for page in layout.pages:
            self.assertLessEqual(len(page.left_lines), 8)
            self.assertLessEqual(len(page.right_lines), 8)
        self.assertTrue(all(-10 <= item.angle <= 10 for item in layout.lines[0].items))

    def test_seed_reproduces_font_and_transform_choices(self) -> None:
        paths = (
            FONT_DIR / "常用_kvenjoy_美文.gfont",
            FONT_DIR / "乐行书_kvenjoy_乐乐.gfont",
        )
        with GFont(paths[0]) as first, GFont(paths[1]) as second:
            one = build_layout("你好，handwriting。", [first, second], 5, random.Random(99))
            two = build_layout("你好，handwriting。", [first, second], 5, random.Random(99))
        fingerprint_one = [
            (item.char, item.font.name if item.font else None, round(item.angle, 6))
            for line in one.lines
            for item in line.items
        ]
        fingerprint_two = [
            (item.char, item.font.name if item.font else None, round(item.angle, 6))
            for line in two.lines
            for item in line.items
        ]
        self.assertEqual(fingerprint_one, fingerprint_two)


if __name__ == "__main__":
    unittest.main()
