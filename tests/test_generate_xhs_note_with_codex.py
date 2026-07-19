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
2. 巨头迎来挑战
3. 生态竞争升级
4. AI格局生变
5. 谁在挑战巨头（推荐）

## 正文

正文内容。

本文由AI辅助生成，基于公开数据整理，不构成投资建议

## 话题

#财经 #AI #科技 #半导体 #产业 #研究 #市场 #投资
<<<END>>>
""".strip()

        self.assertIn("短标题候选", xhs.extract_xhs_note(text))

    def test_extract_xhs_note_rejects_missing_end_marker(self) -> None:
        with self.assertRaises(ValueError):
            xhs.extract_xhs_note("<<<SERENITY_XHS_MD>>>\n# 小红书笔记")

    def test_extract_xhs_note_rejects_internal_status_labels(self) -> None:
        text = """
<<<SERENITY_XHS_MD>>>
# 小红书笔记

正文解释 skipped 状态。

本文由AI辅助生成，基于公开数据整理，不构成投资建议
<<<END>>>
""".strip()

        with self.assertRaisesRegex(ValueError, "forbidden internal processing status"):
            xhs.extract_xhs_note(text)

    def test_extract_xhs_note_rejects_marketing_cta(self) -> None:
        text = """
<<<SERENITY_XHS_MD>>>
# 小红书笔记

欢迎添加企业微信进行咨询。

本文由AI辅助生成，基于公开数据整理，不构成投资建议
<<<END>>>
""".strip()

        with self.assertRaisesRegex(ValueError, "forbidden marketing or contact CTA"):
            xhs.extract_xhs_note(text)

    def test_extract_xhs_note_requires_short_disclaimer(self) -> None:
        text = """
<<<SERENITY_XHS_MD>>>
# 小红书笔记

正文内容。
<<<END>>>
""".strip()

        with self.assertRaisesRegex(ValueError, "missing the required investment-advice disclaimer"):
            xhs.extract_xhs_note(text)

    def test_extract_xhs_note_rejects_legacy_disclaimer(self) -> None:
        text = """
<<<SERENITY_XHS_MD>>>
# 小红书笔记

## 短标题候选

1. 第一标题（推荐）
2. 第二标题
3. 第三标题
4. 第四标题
5. 第五标题

## 正文

正文内容。

风险提示：以上内容仅供参考，不构成投资建议。

## 话题

#财经 #AI #科技 #半导体 #产业 #研究 #市场 #投资
<<<END>>>
""".strip()

        with self.assertRaisesRegex(ValueError, "missing the required investment-advice disclaimer"):
            xhs.extract_xhs_note(text)

    def test_extract_xhs_note_rejects_overlong_generated_title(self) -> None:
        text = """
<<<SERENITY_XHS_MD>>>
# 小红书笔记

## 短标题候选

1. 这是一个明显超过十一字符限制的标题（推荐）
2. 第二标题
3. 第三标题
4. 第四标题
5. 第五标题

## 正文

正文内容。

本文由AI辅助生成，基于公开数据整理，不构成投资建议
<<<END>>>
""".strip()

        with self.assertRaisesRegex(ValueError, "title candidate exceeds 11"):
            xhs.extract_xhs_note(text)

    def test_prompt_requires_codex_xhs_shape(self) -> None:
        prompt = xhs.build_prompt(
            Path("/tmp/reports/20260705T131515Z_report.md"),
            "aleabitoreddit",
            800,
        )

        self.assertIn("正文控制在 750-900 字", prompt)
        self.assertIn("正文绝对不得超过 1000 个字符", prompt)
        self.assertIn("必须拟 5 个语义完整的短标题", prompt)
        self.assertIn("每个标题不得超过 11 个字符", prompt)
        self.assertIn("禁止依赖截断凑长度", prompt)
        self.assertIn("不得写成荐股", prompt)
        self.assertIn("如果报告明确说某主题今天没有有效主线", prompt)
        self.assertIn("不要在标题、正文或话题中出现 `thesis`、`skipped`、`failed`", prompt)
        self.assertIn("不要解释这些状态的含义", prompt)
        self.assertIn("本文由AI辅助生成，基于公开数据整理，不构成投资建议", prompt)
        self.assertIn("不要追加购买页面、企业微信、咨询、合作、开户链接", prompt)
        self.assertIn("最后严格给 10 个小红书话题标签", prompt)
        self.assertIn("#白毛女神 #长期主义", prompt)
        self.assertIn("<<<SERENITY_XHS_MD>>>", prompt)

    def test_extract_normalizes_fixed_final_topics(self) -> None:
        text = """
<<<SERENITY_XHS_MD>>>
# 小红书笔记

## 短标题候选

1. 第一标题（推荐）
2. 第二标题
3. 第三标题
4. 第四标题
5. 第五标题

## 正文

正文内容。

本文由AI辅助生成，基于公开数据整理，不构成投资建议

## 话题

#财经 #白毛女神 #AI #科技 #半导体 #产业 #研究 #市场 #投资 #观察 #长期主义 #财经
<<<END>>>
""".strip()

        note = xhs.extract_xhs_note(text)

        topic_line = note.split("## 话题", 1)[1].strip()
        self.assertEqual(
            topic_line,
            "#财经 #AI #科技 #半导体 #产业 #研究 #市场 #投资 #白毛女神 #长期主义",
        )

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
