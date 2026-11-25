from __future__ import annotations

import datetime as dt
import unittest

from handwriting_doc import naming


WHEN = dt.datetime(2026, 11, 25, 19, 13, 1)


def build(template: str | None, *, seed: int = 42, lines: int = 52, fonts: int = 5) -> str:
    return naming.build_base_name(
        template,
        time=WHEN,
        seed=seed,
        line_count=lines,
        fonts_count=fonts,
    )


class BaseNameTemplateTests(unittest.TestCase):
    def test_default_template_uses_generation_time(self) -> None:
        self.assertEqual(build(None), "手写文档_20261125191301")
        self.assertEqual(build(""), "手写文档_20261125191301")
        self.assertEqual(build("   "), "手写文档_20261125191301")

    def test_time_uses_compact_fourteen_digit_format(self) -> None:
        self.assertEqual(naming.render_base_name("{Time}", time=WHEN, seed=1, line_count=1, fonts_count=1), "20261125191301")

    def test_every_placeholder_is_replaced(self) -> None:
        self.assertEqual(build("{Time}_{Seed}_{LineCount}_{FontsCount}"), "20261125191301_42_52_5")

    def test_placeholders_can_be_combined_with_spaces(self) -> None:
        self.assertEqual(build("手写文档_ {Time}  {LineCount}"), "手写文档_ 20261125191301  52")

    def test_plain_text_without_placeholder_is_kept(self) -> None:
        self.assertEqual(build("教案备份"), "教案备份")

    def test_unknown_placeholder_is_left_untouched(self) -> None:
        self.assertEqual(build("报告_{Version}"), "报告_{Version}")

    def test_lowercase_placeholder_is_not_replaced(self) -> None:
        self.assertEqual(build("报告_{time}"), "报告_{time}")

    def test_duplicate_placeholders_are_all_replaced(self) -> None:
        self.assertEqual(build("{LineCount}行_{LineCount}行"), "52行_52行")

    def test_document_suffix_is_not_duplicated(self) -> None:
        self.assertEqual(build("报告.pdf"), "报告")
        self.assertEqual(build("报告.DOCX"), "报告")

    def test_illegal_characters_are_replaced(self) -> None:
        self.assertEqual(build('a/b:c*?"<>|'), "a_b_c______")

    def test_trailing_dots_and_spaces_are_removed(self) -> None:
        self.assertEqual(build("报告.  "), "报告")

    def test_empty_result_falls_back_to_default(self) -> None:
        self.assertEqual(build("..."), "手写文档_20261125191301")

    def test_length_is_bounded(self) -> None:
        name = build("长" * 400)
        self.assertEqual(len(name), naming.MAX_BASE_NAME_LENGTH)

    def test_seed_is_used_verbatim(self) -> None:
        self.assertEqual(build("{Seed}", seed=0), "0")


if __name__ == "__main__":
    unittest.main()
