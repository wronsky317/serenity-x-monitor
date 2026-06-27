#!/usr/bin/env python3
"""Parse a Serenity raw run with Codex CLI.

Input: a timestamped directory under raw/ containing Supercycle/X JSON.
Output:
- parsed/<run_id>.md: detailed parsed content.
- reports/<run_id>_report.md: report-ready summary.
- reports/latest_summary.md: copy of the report-ready summary.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path("/Users/wronsky/Documents/codes/serenity-x-monitor")
RAW_DIR = PROJECT_ROOT / "raw"
PARSED_DIR = PROJECT_ROOT / "parsed"
REPORTS_DIR = PROJECT_ROOT / "reports"
DEFAULT_HANDLE = "aleabitoreddit"

DETAIL_MARKER = "<<<SERENITY_DETAILED_MD>>>"
REPORT_MARKER = "<<<SERENITY_REPORT_MD>>>"
END_MARKER = "<<<END>>>"


def latest_raw_run(raw_dir: Path) -> Path:
    runs = sorted(path for path in raw_dir.iterdir() if path.is_dir())
    if not runs:
        raise FileNotFoundError(f"No raw run directories found under {raw_dir}")
    return runs[-1]


def build_prompt(raw_run: Path, handle: str) -> str:
    raw_rows = raw_run / f"{handle}.rows.json"
    all_rows = raw_run / "all_rows.deduped.json"
    manifest = raw_run / "manifest.json"
    return f"""
你是一个只做解析整理的研究助手。请读取 Serenity X 原始抓取结果，并输出两个 Markdown 文档。

输入文件：
- Serenity 原始行：{raw_rows}
- 全量去重原始行：{all_rows}
- 抓取元数据：{manifest}

要求：
1. 只基于上述本地 JSON 文件，不联网，不补充外部事实，不编造链接、时间、证券代码或原帖内容。
2. 目标账号是 `@{handle}` / Serenity。优先解析 `{raw_rows.name}`；如果为空，说明没有新增 Serenity 行。
3. 详细文档要尽量完整：逐条列出原始帖子/行的 id、xPostId、postedAt/sortAt、canonicalUrl、kind、skipReason/failureReason、原文、涉及证券/公司/主题、观点方向、催化、风险、是否只是政策/身份/非投资性内容。
4. 报告文档要适合直接发飞书：中文、紧凑、无 Markdown 表格、无代码块、无 raw JSON；保留关键链接和风险提示。
5. 不给投资买卖建议。

请严格按以下格式输出，不要添加其他前言或解释：

{DETAIL_MARKER}
# Serenity X 详细解析
...

{REPORT_MARKER}
# Serenity（@{handle}）X 日报
...

{END_MARKER}
""".strip()


def run_codex(prompt: str, output_file: Path) -> None:
    command = [
        "codex",
        "exec",
        "--cd",
        str(PROJECT_ROOT),
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "--output-last-message",
        str(output_file),
        prompt,
    ]
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        message = (
            f"codex exec failed with exit code {completed.returncode}\n"
            f"stdout:\n{completed.stdout[-4000:]}\n"
            f"stderr:\n{completed.stderr[-4000:]}"
        )
        raise RuntimeError(message)


def extract_between(text: str, start: str, end: str) -> str:
    if start not in text:
        raise ValueError(f"Missing marker: {start}")
    after = text.split(start, 1)[1]
    if end not in after:
        raise ValueError(f"Missing marker after {start}: {end}")
    return after.split(end, 1)[0].strip() + "\n"


def parse_codex_output(text: str) -> tuple[str, str]:
    detailed = extract_between(text, DETAIL_MARKER, REPORT_MARKER)
    report = extract_between(text, REPORT_MARKER, END_MARKER)
    return detailed, report


def write_outputs(raw_run: Path, detailed: str, report: str) -> dict[str, Path]:
    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    run_id = raw_run.name
    detail_path = PARSED_DIR / f"{run_id}.md"
    report_path = REPORTS_DIR / f"{run_id}_report.md"
    latest_path = REPORTS_DIR / "latest_summary.md"
    detail_path.write_text(detailed, encoding="utf-8")
    report_path.write_text(report, encoding="utf-8")
    latest_path.write_text(report, encoding="utf-8")
    return {
        "detailed": detail_path,
        "report": report_path,
        "latest": latest_path,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse raw Serenity X JSON with Codex CLI.")
    parser.add_argument("--raw-run", help="Timestamped raw run directory. Defaults to latest raw/* dir.")
    parser.add_argument("--handle", default=DEFAULT_HANDLE)
    parser.add_argument("--keep-codex-output", help="Optional path to save raw Codex output.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    raw_run = Path(args.raw_run).expanduser() if args.raw_run else latest_raw_run(RAW_DIR)
    if not raw_run.exists() or not raw_run.is_dir():
        raise SystemExit(f"Raw run directory not found: {raw_run}")

    prompt = build_prompt(raw_run, args.handle.lower().lstrip("@"))
    with tempfile.NamedTemporaryFile("w+", encoding="utf-8", suffix=".md", delete=False) as handle:
        codex_output = Path(handle.name)
    try:
        run_codex(prompt, codex_output)
        text = codex_output.read_text(encoding="utf-8", errors="replace")
        detailed, report = parse_codex_output(text)
        outputs = write_outputs(raw_run, detailed, report)
        if args.keep_codex_output:
            shutil.copyfile(codex_output, Path(args.keep_codex_output).expanduser())
    finally:
        if not args.keep_codex_output:
            codex_output.unlink(missing_ok=True)

    print(f"detailed={outputs['detailed']}")
    print(f"report={outputs['report']}")
    print(f"latest={outputs['latest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
