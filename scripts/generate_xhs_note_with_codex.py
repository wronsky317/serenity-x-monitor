#!/usr/bin/env python3
"""Generate a Xiaohongshu note from the current Serenity daily report.

The note is written by Codex CLI from the just-generated report. It never reads
old Xiaohongshu drafts, so a failed run cannot silently reuse stale content.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path("/Users/wronsky/Documents/codes/serenity-x-monitor")
REPORTS_DIR = PROJECT_ROOT / "reports"
DEFAULT_HANDLE = "aleabitoreddit"

XHS_MARKER = "<<<SERENITY_XHS_MD>>>"
END_MARKER = "<<<END>>>"


def run_id_from_report(report_path: Path) -> str:
    name = report_path.name
    if name.endswith("_report.md"):
        return name[: -len("_report.md")]
    return report_path.stem


def default_xhs_path(report_path: Path) -> Path:
    return REPORTS_DIR / f"{run_id_from_report(report_path)}_xhs.md"


def build_prompt(report_path: Path, handle: str, target_words: int) -> str:
    return f"""
你是财经小红书笔记编辑。请读取 Serenity 当日中文报告，把它改写成可直接附在飞书消息里的小红书文章。

输入文件：
- 当日 Serenity 报告：{report_path}

硬性要求：
1. 只基于输入报告，不联网，不补充外部事实，不编造链接、时间、证券代码或原帖内容。
2. 输出中文，正文控制在 {max(500, target_words - 50)}-{target_words + 100} 字，标题候选和话题标签不计入；超过上限必须删减，不要灌水。
3. 必须调用小红书笔记写法：短句、分段、适量 emoji、钩子开头、重点清晰、可读性强。
4. 必须拟 5 个短标题，标题不超过 20 个中文字符，并标出“推荐”。
5. 正文要保留 Serenity 报告里的不确定性、可验证催化和风险，不得写成荐股或确定性投资建议。
6. 如果报告明确说某主题今天没有有效主线，必须在正文中写清楚，避免误归因。
7. 不使用 Markdown 表格，不输出写作过程，不输出图片提示词。
8. 正文末尾必须包含这一条风险提示，文字保持一致：
   **风险提示**:投资有风险,入市需谨慎。以上内容仅供参考,不构成投资建议或收益承诺。关于相关权益,请以购买页面所展示的信息为准。如需了解更多详细规则,欢迎添加企业微信进行咨询。
9. 最后给 8-12 个小红书话题标签。

输出结构必须是：

# 小红书笔记

## 短标题候选

1. ...

## 正文

...

## 话题

#标签 ...

请严格按以下格式输出，不要添加其他前言或解释：

{XHS_MARKER}
# 小红书笔记
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


def extract_xhs_note(text: str) -> str:
    if XHS_MARKER not in text:
        raise ValueError(f"Missing marker: {XHS_MARKER}")
    after = text.split(XHS_MARKER, 1)[1]
    if END_MARKER not in after:
        raise ValueError(f"Missing marker after {XHS_MARKER}: {END_MARKER}")
    return after.split(END_MARKER, 1)[0].strip() + "\n"


def write_xhs_note(note: str, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(note, encoding="utf-8")
    return output_path


def append_note_to_report(report_path: Path, note: str) -> None:
    report = report_path.read_text(encoding="utf-8", errors="replace").rstrip()
    report_path.write_text(
        report + "\n\n---\n\n" + note.strip() + "\n",
        encoding="utf-8",
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a Xiaohongshu note with Codex CLI.")
    parser.add_argument("--report", required=True, help="Current-run Serenity report path.")
    parser.add_argument("--handle", default=DEFAULT_HANDLE)
    parser.add_argument("--target-words", type=int, default=800, help="Target Chinese character count for the note body.")
    parser.add_argument("--output", help="Output path. Defaults to reports/<run_id>_xhs.md.")
    parser.add_argument(
        "--append-to",
        help=(
            "Optional report file to append the Xiaohongshu note to. "
            "Use reports/latest_summary.md for Feishu/Hermes delivery."
        ),
    )
    parser.add_argument("--keep-codex-output", help="Optional path to save raw Codex output.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    report_path = Path(args.report).expanduser()
    if not report_path.exists():
        raise SystemExit(f"Report file not found: {report_path}")
    output_path = Path(args.output).expanduser() if args.output else default_xhs_path(report_path)
    prompt = build_prompt(report_path, args.handle.lower().lstrip("@"), args.target_words)

    with tempfile.NamedTemporaryFile("w+", encoding="utf-8", suffix=".md", delete=False) as handle_obj:
        codex_output = Path(handle_obj.name)
    try:
        run_codex(prompt, codex_output)
        text = codex_output.read_text(encoding="utf-8", errors="replace")
        note = extract_xhs_note(text)
        xhs_path = write_xhs_note(note, output_path)
        if args.append_to:
            append_note_to_report(Path(args.append_to).expanduser(), note)
        if args.keep_codex_output:
            shutil.copyfile(codex_output, Path(args.keep_codex_output).expanduser())
    finally:
        if not args.keep_codex_output:
            codex_output.unlink(missing_ok=True)

    print(f"xhs={xhs_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
