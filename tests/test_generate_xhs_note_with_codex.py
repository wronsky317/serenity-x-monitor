from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "generate_xhs_note_with_codex.py"
SPEC = importlib.util.spec_from_file_location("generate_xhs_note_with_codex", MODULE_PATH)
assert SPEC and SPEC.loader
xhs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(xhs)


class GenerateXhsNoteWithCodexTest(unittest.TestCase):
    def test_extract_xhs_note_requires_markers(self) -> None:
        text = """
noise
<<<SERENITY_XHS_MD>>>
# 小红书笔记

## 短标题候选

1. AI下一站
<<<END>>>
""".strip()

        self.assertIn("短标题候选", xhs.extract_xhs_note(text))

    def test_extract_xhs_note_rejects_missing_end_marker(self) -> None:
        with self.assertRaises(ValueError):
            xhs.extract_xhs_note("<<<SERENITY_XHS_MD>>>\n# 小红书笔记")

    def test_prompt_requires_codex_xhs_shape(self) -> None:
        prompt = xhs.build_prompt(
            Path("/tmp/reports/20260705T131515Z_report.md"),
            "aleabitoreddit",
            800,
        )

        self.assertIn("正文控制在 750-900 字", prompt)
        self.assertIn("必须拟 5 个短标题", prompt)
        self.assertIn("不得写成荐股", prompt)
        self.assertIn("如果报告明确说某主题今天没有有效主线", prompt)
        self.assertIn("<<<SERENITY_XHS_MD>>>", prompt)

    def test_append_note_to_report_appends_current_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "latest_summary.md"
            report.write_text("# Serenity 日报\n\n日报正文\n", encoding="utf-8")

            xhs.append_note_to_report(report, "# 小红书笔记\n\n新稿")

            text = report.read_text(encoding="utf-8")
            self.assertIn("# Serenity 日报", text)
            self.assertIn("# 小红书笔记", text)
            self.assertIn("新稿", text)


if __name__ == "__main__":
    unittest.main()
