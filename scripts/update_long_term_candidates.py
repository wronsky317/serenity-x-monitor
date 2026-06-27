#!/usr/bin/env python3
"""Create a reviewable long-term-view candidate update.

This script intentionally stops before editing the maintained thesis document.
It reads a generated Serenity report and writes a commit-safe Markdown draft to:

    long_term_views/pending_updates/<date>.md

The draft is meant for a human or another agent to review and later merge into
long_term_views/serenity_core_asset_map.md.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]


PROJECT_ROOT = Path("/Users/wronsky/Documents/codes/serenity-x-monitor")
DEFAULT_REPORT = PROJECT_ROOT / "reports" / "latest_summary.md"
PENDING_DIR = PROJECT_ROOT / "long_term_views" / "pending_updates"


def now_cst() -> datetime:
    if ZoneInfo is None:
        return datetime.now()
    return datetime.now(ZoneInfo("Asia/Shanghai"))


def rel_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return path.name


def section_map(markdown: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current = "__intro__"
    sections[current] = []
    for line in markdown.splitlines():
        match = re.match(r"^##\s+(.+?)\s*$", line)
        if match:
            current = match.group(1).strip()
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return {key: "\n".join(value).strip() for key, value in sections.items()}


def extract_coverage(intro: str) -> str:
    for line in intro.splitlines():
        if "覆盖 `" in line and "命中 Serenity" in line:
            return line.strip()
    return "未在报告中识别到覆盖窗口。"


def normalize_section(text: str, fallback: str) -> str:
    text = text.strip()
    return text if text else fallback


def has_durable_signal(report: str, sections: dict[str, str]) -> bool:
    core = sections.get("今日核心总结", "")
    impact = sections.get("对长期观点的影响", "")
    no_signal_markers = [
        "今日未抓到 Serenity 新内容",
        "未识别到明确投资主题、证券代码或长期观点变化",
        "今日没有新的 portfolio theme",
    ]
    if no_signal_markers[0] in report:
        return False
    if any(marker in core for marker in no_signal_markers):
        return False
    return bool(impact.strip() and "今日没有新的 portfolio theme" not in impact)


def build_candidate(
    *,
    date_text: str,
    report_path: Path,
    report_markdown: str,
    raw_run: str,
    detailed: str,
) -> str:
    sections = section_map(report_markdown)
    intro = sections.get("__intro__", "")
    durable_signal = has_durable_signal(report_markdown, sections)
    status = "需要人工复核后合并" if durable_signal else "暂无明确长期观点变更"

    core = normalize_section(sections.get("今日核心总结", ""), "- 无可提取内容。")
    key = normalize_section(sections.get("重点内容解读", ""), "- 无可提取内容。")
    impact = normalize_section(sections.get("对长期观点的影响", ""), "- 无明确长期观点影响。")
    risks = normalize_section(sections.get("风险与待验证事项", ""), "- 无新增风险。")

    raw_id = Path(raw_run).name if raw_run else "未提供"
    detailed_id = Path(detailed).name if detailed else "未提供"

    lines = [
        f"# Serenity 长期观点候选更新 - {date_text}",
        "",
        "> 自动生成的待合并草案。请先复核来源、去重和主文档上下文，再手动合并到 `serenity_core_asset_map.md`。",
        "",
        "## 状态",
        "",
        f"- 合并建议：{status}",
        f"- 生成时间：{now_cst().strftime('%Y-%m-%d %H:%M')} CST",
        f"- 来源报告：`{rel_path(report_path)}`",
        f"- raw_run_id：`{raw_id}`",
        f"- parsed_archive：`{detailed_id}`",
        f"- 覆盖口径：{extract_coverage(intro)}",
        "",
        "## 建议合并动作",
        "",
    ]
    if durable_signal:
        lines.extend(
            [
                "- [ ] 检查是否强化、削弱或新增了主文档已有主题。",
                "- [ ] 把可验证的公司、周期、催化剂、风险补入对应主题。",
                "- [ ] 对一次性市场评论保持观察，不直接升级为长期主线。",
            ]
        )
    else:
        lines.extend(
            [
                "- [ ] 通常无需合并；只在复核后发现隐藏的长期主题变化时处理。",
                "- [ ] 保留本文件作为当日长期观点审计记录。",
            ]
        )

    lines.extend(
        [
            "",
            "## 候选核心变化",
            "",
            core,
            "",
            "## 可合并主题影响",
            "",
            impact,
            "",
            "## 证据摘要",
            "",
            key,
            "",
            "## 风险与待验证",
            "",
            risks,
            "",
            "## 合并备注",
            "",
            "- 本文件只包含报告级摘要，不归档 raw JSON 或完整原文。",
            "- 合并时需要保留不确定性，不把社媒观点改写成投资建议。",
            "- 如涉及新 ticker、中文别名、供应链映射或时间点，需要在主文档中标明验证条件。",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a pending long-term-view update from a Serenity report.")
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="Report Markdown path. Default: reports/latest_summary.md.")
    parser.add_argument("--date", help="Output date, YYYY-MM-DD. Default: current Asia/Shanghai date.")
    parser.add_argument("--raw-run", default="", help="Optional raw run path for source citation.")
    parser.add_argument("--detailed", default="", help="Optional parsed archive path for source citation.")
    parser.add_argument("--output-dir", default=str(PENDING_DIR), help="Pending update output directory.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    report_path = Path(args.report).expanduser()
    if not report_path.exists():
        raise SystemExit(f"Report not found: {report_path}")

    date_text = args.date or now_cst().strftime("%Y-%m-%d")
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{date_text}.md"

    report_markdown = report_path.read_text(encoding="utf-8", errors="replace")
    output_path.write_text(
        build_candidate(
            date_text=date_text,
            report_path=report_path,
            report_markdown=report_markdown,
            raw_run=args.raw_run,
            detailed=args.detailed,
        ),
        encoding="utf-8",
    )
    print(f"pending_update={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
