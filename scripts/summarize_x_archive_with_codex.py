#!/usr/bin/env python3
"""Use Codex CLI to summarize Serenity views from a deterministic archive.

This script does not fetch data and does not write the detailed archive. It
reads an existing parsed/<run_id>.md archive plus raw metadata, then asks Codex
CLI to generate the report-level opinion summary. The goal is to keep raw/parsed
coverage deterministic while making thesis synthesis contextual instead of
keyword-template based.
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

REPORT_MARKER = "<<<SERENITY_REPORT_MD>>>"
END_MARKER = "<<<END>>>"


def latest_raw_run(raw_dir: Path) -> Path:
    runs = sorted(path for path in raw_dir.iterdir() if path.is_dir())
    if not runs:
        raise FileNotFoundError(f"No raw run directories found under {raw_dir}")
    return runs[-1]


def default_detail_path(raw_run: Path) -> Path:
    return PARSED_DIR / f"{raw_run.name}.md"


def build_prompt(raw_run: Path, detail_path: Path, handle: str) -> str:
    rows_path = raw_run / f"{handle}.rows.json"
    manifest_path = raw_run / "manifest.json"
    return f"""
你是 Serenity X 监控项目的观点归纳审阅器。请读取本地抓取与逐条归档，然后生成一份可直接发送到飞书、也可被 long_term_views/pending_updates 继续抽取的中文报告。

输入文件：
- 完整逐条归档：{detail_path}
- Serenity 原始行 JSON：{rows_path}
- 抓取元数据：{manifest_path}

硬性要求：
1. 只基于上述本地文件，不联网，不补充外部事实，不编造链接、时间、证券代码或原帖内容。
2. 完整逐条归档由 deterministic parser 生成，用它保证覆盖；你的职责是做观点归纳、因果审阅、主题合并与风险拆分。
3. 逐条核对证据后再下结论。不能因为单词子串或宽泛提及就套用既有主题。例如：
   - `Optimus` 里的 `mu` 不是 `$MU`。
   - `Unimicron` 不是 Micron。
   - Samsung 签 MLCC LTA 不等于 Samsung HBM thesis。
   - 机器人/汽车零部件/执行器内容不要归纳成 Memory/HBM，除非原文明确提到 HBM/DRAM/NAND 供需与相关公司。
4. 对 failed/skipped 行也要阅读；它们可能包含有效观点。
   - `thesis` 表示上游成功生成了结构化 portfolio/thesis，不等于“观点一定正确”或“可直接合并长期观点”；仍需核对原文因果、ticker 和风险。
   - `failed` 不是推文抓取失败，通常表示上游 portfolio/thesis 结构化生成失败、图片下载失败或 ticker 校验失败；如果原文已在 archive 中出现，应写作“原始状态：failed（结构化生成失败，文本已抓取）”，并列出 failureReason。
   - `skipped` 不是推文无效，通常表示上游没有生成方向性组合；如果文本有主题观察，应写作“原始状态：skipped（未生成方向性组合）”，并列出 skipReason。
   - 不要只写“状态：thesis/failed/skipped”，必须解释这些是原始 row 状态，不是报告结论等级。
5. 对每条重点内容给出：时间、来源链接、原始状态说明、涉及证券/公司、Serenity 的观点、可验证催化、风险或待验证事项。
6. 长期观点部分只写“新增/强化/削弱/待观察”的 thesis，不要把一次性市场评论升级成长期主线。
7. 不给投资买卖建议，不使用 Markdown 表格，不输出 raw JSON，不贴长篇原文。

报告结构必须使用这些二级标题，便于后续脚本抽取：

# Serenity（@{handle}）X 日报

## 今日核心总结

## 重点内容解读

## 对长期观点的影响

## 风险与待验证事项

## 抓取与归档状态

## 最新条目索引

请严格按以下格式输出，不要添加其他前言或解释：

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


def extract_report(text: str) -> str:
    if REPORT_MARKER not in text:
        raise ValueError(f"Missing marker: {REPORT_MARKER}")
    after = text.split(REPORT_MARKER, 1)[1]
    if END_MARKER not in after:
        raise ValueError(f"Missing marker after {REPORT_MARKER}: {END_MARKER}")
    return after.split(END_MARKER, 1)[0].strip() + "\n"


def write_outputs(raw_run: Path, detail_path: Path, report: str) -> dict[str, Path]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    run_id = raw_run.name
    report_path = REPORTS_DIR / f"{run_id}_report.md"
    latest_path = REPORTS_DIR / "latest_summary.md"
    report_path.write_text(report, encoding="utf-8")
    latest_path.write_text(report, encoding="utf-8")
    return {
        "detailed": detail_path,
        "report": report_path,
        "latest": latest_path,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a Serenity report summary with Codex CLI.")
    parser.add_argument("--raw-run", help="Timestamped raw run directory. Defaults to latest raw/* dir.")
    parser.add_argument("--detail", help="Deterministic parsed archive path. Defaults to parsed/<run_id>.md.")
    parser.add_argument("--handle", default=DEFAULT_HANDLE)
    parser.add_argument("--keep-codex-output", help="Optional path to save raw Codex output.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    raw_run = Path(args.raw_run).expanduser() if args.raw_run else latest_raw_run(RAW_DIR)
    handle = args.handle.lower().lstrip("@")
    detail_path = Path(args.detail).expanduser() if args.detail else default_detail_path(raw_run)
    if not raw_run.exists() or not raw_run.is_dir():
        raise SystemExit(f"Raw run directory not found: {raw_run}")
    if not detail_path.exists():
        raise SystemExit(f"Detailed archive not found: {detail_path}")
    rows_path = raw_run / f"{handle}.rows.json"
    manifest_path = raw_run / "manifest.json"
    if not rows_path.exists():
        raise SystemExit(f"Rows file not found: {rows_path}")
    if not manifest_path.exists():
        raise SystemExit(f"Manifest file not found: {manifest_path}")

    prompt = build_prompt(raw_run, detail_path, handle)
    with tempfile.NamedTemporaryFile("w+", encoding="utf-8", suffix=".md", delete=False) as handle_obj:
        codex_output = Path(handle_obj.name)
    try:
        run_codex(prompt, codex_output)
        text = codex_output.read_text(encoding="utf-8", errors="replace")
        report = extract_report(text)
        outputs = write_outputs(raw_run, detail_path, report)
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
