from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "summarize_x_archive_with_codex.py"
SPEC = importlib.util.spec_from_file_location("summarize_x_archive_with_codex", MODULE_PATH)
assert SPEC and SPEC.loader
summary = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(summary)


class SummarizeXArchiveWithCodexTest(unittest.TestCase):
    def test_extract_report_requires_markers(self) -> None:
        text = """
noise
<<<SERENITY_REPORT_MD>>>
# Serenity（@aleabitoreddit）X 日报

## 今日核心总结

- ok
<<<END>>>
""".strip()

        self.assertIn("今日核心总结", summary.extract_report(text))

    def test_extract_report_rejects_missing_end_marker(self) -> None:
        with self.assertRaises(ValueError):
            summary.extract_report("<<<SERENITY_REPORT_MD>>>\n# report")

    def test_prompt_contains_causality_guardrails(self) -> None:
        prompt = summary.build_prompt(
            Path("/tmp/raw/20260701T000000Z"),
            Path("/tmp/parsed/20260701T000000Z.md"),
            "aleabitoreddit",
        )

        self.assertIn("Optimus", prompt)
        self.assertIn("Unimicron", prompt)
        self.assertIn("Samsung 签 MLCC LTA 不等于 Samsung HBM thesis", prompt)

    def test_prompt_explains_raw_status_labels(self) -> None:
        prompt = summary.build_prompt(
            Path("/tmp/raw/20260701T000000Z"),
            Path("/tmp/parsed/20260701T000000Z.md"),
            "aleabitoreddit",
        )

        self.assertIn("`thesis` 表示上游成功生成了结构化 portfolio/thesis", prompt)
        self.assertIn("`failed` 不是推文抓取失败", prompt)
        self.assertIn("`skipped` 不是推文无效", prompt)
        self.assertIn("原始 row 状态，不是报告结论等级", prompt)


if __name__ == "__main__":
    unittest.main()
