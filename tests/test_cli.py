from __future__ import annotations

import unittest

from handwriting_doc.cli import _parser


class CliParserTests(unittest.TestCase):
    def test_restore_text_is_accepted_together_with_gui(self) -> None:
        args = _parser().parse_args(["--gui", "--restore-text", "restore.txt"])
        self.assertTrue(args.gui)
        self.assertEqual(args.restore_text, "restore.txt")

    def test_restore_text_is_internal_and_hidden_from_help(self) -> None:
        help_text = _parser().format_help()
        self.assertNotIn("--restore-text", help_text)


if __name__ == "__main__":
    unittest.main()
