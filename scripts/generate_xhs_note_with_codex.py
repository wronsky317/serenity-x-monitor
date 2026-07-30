#!/usr/bin/env python3
"""Generate a Xiaohongshu note from the current Serenity daily report.

The note is written by Codex CLI from the just-generated report. It never reads
old Xiaohongshu drafts, so a failed run cannot silently reuse stale content.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from codex_cli import resolve_codex_cli


PROJECT_ROOT = Path("/Users/wronsky/Documents/codes/serenity-x-monitor")
REPORTS_DIR = PROJECT_ROOT / "reports"
DEFAULT_HANDLE = "aleabitoreddit"

XHS_MARKER = "<<<SERENITY_XHS_MD>>>"
END_MARKER = "<<<END>>>"
INTERNAL_STATUS_PATTERN = re.compile(r"\b(?:thesis|skipped|failed)\b", re.IGNORECASE)
MARKETING_CTA_PATTERN = re.compile(r"(?:企业微信|购买页面|添加微信|欢迎咨询|合作联系|开户链接)")
RISK_NOTICE = "本文由AI辅助生成，基于公开数据整理，不构成投资建议"
MAX_SHORT_TITLE_LENGTH = 11
MAX_BODY_LENGTH = 1000
MAX_TAGS = 10
FIXED_TAGS = ("白毛女神", "长期主义")


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
2. 输出中文，正文控制在 {max(500, target_words - 50)}-{min(MAX_BODY_LENGTH, target_words + 100)} 字，标题候选和话题标签不计入；正文绝对不得超过 {MAX_BODY_LENGTH} 个字符，超过上限必须重写删减，不要灌水。
3. 必须调用小红书笔记写法：短句、分段、适量 emoji、钩子开头、重点清晰、可读性强。
4. 必须拟 5 个语义完整的短标题，每个标题不得超过 {MAX_SHORT_TITLE_LENGTH} 个字符，并标出“推荐”。发布时会自动加 `【财经】MMDD ` 前缀，禁止依赖截断凑长度。
5. 正文要保留 Serenity 报告里的不确定性、可验证催化和风险，不得写成荐股或确定性投资建议。
6. 如果报告明确说某主题今天没有有效主线，必须在正文中写清楚，避免误归因。
7. 重要性不以是否含证券代码为前提。Serenity 帖子中的人物/基金动态、FOMC 利率决议、监管政策、重大宏观事件和产业拐点必须保留；不能为了篇幅只留下具体标的和产业链，也不能把 Leopold 等人物信息压缩成一句无主体的“去杠杆”。
8. 不要在标题、正文或话题中出现 `thesis`、`skipped`、`failed` 等内部处理状态，也不要解释这些状态的含义；只保留对应内容本身的观点、证据、催化、不确定性和风险。
9. 不使用 Markdown 表格，不输出写作过程，不输出图片提示词。
10. 正文最后只能使用这一条风险提示，文字保持一致，不要追加购买页面、企业微信、咨询、合作、开户链接等营销或导流信息：
   {RISK_NOTICE}
11. 最后严格给 {MAX_TAGS} 个小红书话题标签；最后两个必须依次为 `#白毛女神 #长期主义`，前八个不得与这两个重复。

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
        str(resolve_codex_cli()),
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
    note = after.split(END_MARKER, 1)[0].strip() + "\n"
    if INTERNAL_STATUS_PATTERN.search(note):
        raise ValueError("Xiaohongshu note contains forbidden internal processing status labels.")
    if MARKETING_CTA_PATTERN.search(note):
        raise ValueError("Xiaohongshu note contains forbidden marketing or contact CTA text.")
    if RISK_NOTICE not in note:
        raise ValueError("Xiaohongshu note is missing the required investment-advice disclaimer.")
    title_block = re.search(r"^##\s+短标题候选\s*$\n(.*?)(?=^##\s+|\Z)", note, re.MULTILINE | re.DOTALL)
    titles = re.findall(r"^\s*\d+[.)、]\s*(.+?)\s*$", title_block.group(1), re.MULTILINE) if title_block else []
    cleaned_titles = [re.sub(r"[（(]\s*推荐\s*[）)]", "", title).strip() for title in titles]
    if len(cleaned_titles) != 5:
        raise ValueError("Xiaohongshu note must contain exactly 5 short title candidates.")
    if any(len(title) > MAX_SHORT_TITLE_LENGTH for title in cleaned_titles):
        raise ValueError(f"Xiaohongshu title candidate exceeds {MAX_SHORT_TITLE_LENGTH} characters.")
    body_match = re.search(r"^##\s+正文\s*$\n(.*?)(?=^##\s+|\Z)", note, re.MULTILINE | re.DOTALL)
    body = body_match.group(1).strip() if body_match else ""
    if not body:
        raise ValueError("Xiaohongshu note is missing the body section.")
    if len(body) > MAX_BODY_LENGTH:
        raise ValueError(f"Xiaohongshu body exceeds {MAX_BODY_LENGTH} characters.")
    if not body.endswith(RISK_NOTICE) or body.count("不构成投资建议") != 1:
        raise ValueError("Xiaohongshu body must end with the exact required AI disclaimer.")
    return normalize_topic_section(note)


def normalize_topic_section(note: str) -> str:
    topic_match = re.search(r"^##\s+话题\s*$\n(.*?)(?=^##\s+|\Z)", note, re.MULTILINE | re.DOTALL)
    if not topic_match:
        raise ValueError("Xiaohongshu note is missing the topic section.")
    source = re.findall(r"#([^#\s]+)", topic_match.group(1))
    topics: list[str] = []
    for topic in source:
        if topic in FIXED_TAGS or topic in topics:
            continue
        topics.append(topic)
        if len(topics) == MAX_TAGS - len(FIXED_TAGS):
            break
    if len(topics) < MAX_TAGS - len(FIXED_TAGS):
        raise ValueError("Xiaohongshu note does not contain enough distinct topic tags.")
    normalized = topics + list(FIXED_TAGS)
    replacement = " ".join(f"#{topic}" for topic in normalized) + "\n"
    return note[: topic_match.start(1)] + "\n" + replacement + note[topic_match.end(1) :].lstrip("\n")


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
