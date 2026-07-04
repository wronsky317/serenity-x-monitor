#!/usr/bin/env python3
"""Run the Serenity monitor pipeline.

Pipeline:
1. Fetch raw X/Supercycle data into raw/<timestamp>/.
2. Archive the raw run into parsed/<timestamp>.md.
3. Write the report-ready file into reports/<timestamp>_report.md and latest_summary.md.
4. Optionally send latest_summary.md to Feishu.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


PROJECT_ROOT = Path("/Users/wronsky/Documents/codes/serenity-x-monitor")
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
DEFAULT_CHAT_ID = os.environ.get("FEISHU_CHAT_ID", "")
DEFAULT_FETCH_RETRY_SCHEDULE = "20:3,60:3,120:3"


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def write_failure_notice(stage: str, details: str) -> Path:
    REPORTS_DIR = PROJECT_ROOT / "reports"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    latest_path = REPORTS_DIR / "latest_summary.md"
    latest_path.write_text(
        "\n".join(
            [
                "# Serenity X 日报生成失败",
                "",
                f"- 时间：{timestamp}",
                f"- 阶段：{stage}",
                "- 状态：本次抓取/解析未成功生成新报告。",
                "- 处理：为避免误用旧报告，`latest_summary.md` 已写入失败占位，不作为 Serenity 内容报告。",
                "",
                "## 错误摘要",
                "",
                details.strip()[-4000:] or "未捕获到详细错误输出。",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return latest_path


def run_fetch_with_retries(
    command: list[str],
    *,
    retry_schedule: list[tuple[float, int]],
    runner: Callable[[list[str]], subprocess.CompletedProcess[str]] = run,
    sleeper: Callable[[float], None] = time.sleep,
) -> subprocess.CompletedProcess[str]:
    last = runner(command)
    if last.returncode == 0:
        return last
    total_retries = sum(max(0, retries) for _, retries in retry_schedule)
    retry_index = 0
    for level_index, (sleep_seconds, retries) in enumerate(retry_schedule, start=1):
        for level_retry in range(1, max(0, retries) + 1):
            retry_index += 1
            print(
                (
                    f"Fetch failed with exit={last.returncode}; retry "
                    f"{retry_index}/{total_retries} "
                    f"(level {level_index}, {level_retry}/{retries}) "
                    f"after {sleep_seconds:g}s..."
                ),
                file=sys.stderr,
            )
            if sleep_seconds > 0:
                sleeper(sleep_seconds)
            last = runner(command)
            if last.returncode == 0:
                return last
    return last


def parse_retry_schedule(value: str) -> list[tuple[float, int]]:
    schedule: list[tuple[float, int]] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" not in item:
            raise argparse.ArgumentTypeError(
                "retry schedule items must use '<seconds>:<retries>', e.g. 20:3,60:3,120:3"
            )
        seconds_text, retries_text = item.split(":", 1)
        try:
            seconds = float(seconds_text)
            retries = int(retries_text)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                "retry schedule seconds must be numeric and retries must be integer"
            ) from exc
        if seconds < 0 or retries < 0:
            raise argparse.ArgumentTypeError("retry schedule values must be non-negative")
        schedule.append((seconds, retries))
    if not schedule:
        raise argparse.ArgumentTypeError("retry schedule cannot be empty")
    return schedule


def parse_key_value_lines(stdout: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def run_archive_builder(raw_run: str, handle: str) -> subprocess.CompletedProcess[str]:
    return run(
        [
            sys.executable,
            "-B",
            str(SCRIPTS_DIR / "build_x_archive_report.py"),
            "--raw-run",
            raw_run,
            "--handle",
            handle,
        ]
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch, parse, report, and optionally send Serenity update.")
    parser.add_argument(
        "--take",
        type=int,
        default=50,
        help="Rows requested per Supercycle API page. Passed through to fetch_x_raw.py.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=5,
        help=(
            "Safety cap on cursor pages to fetch. Rough scan limit is "
            "take * max-pages; stops earlier after reaching --since."
        ),
    )
    parser.add_argument("--cursor", help="Optional Supercycle cursor.")
    parser.add_argument("--since", help="Inclusive UTC lower bound, e.g. 2026-06-20T00:00:00Z.")
    parser.add_argument("--until", help="Inclusive UTC upper bound, e.g. 2026-06-27T00:00:00Z.")
    parser.add_argument("--handle", default="aleabitoreddit")
    parser.add_argument(
        "--parser",
        choices=("archive", "codex"),
        default="codex",
        help=(
            "codex = deterministic full row archive plus Codex CLI opinion summary; "
            "archive = deterministic full row archive and rule-based report."
        ),
    )
    parser.add_argument("--send", action="store_true", help="Send the generated report to Feishu.")
    parser.add_argument("--chat-id", default=DEFAULT_CHAT_ID)
    parser.add_argument("--title", default="Serenity 日报")
    parser.add_argument(
        "--fetch-retry-schedule",
        default=DEFAULT_FETCH_RETRY_SCHEDULE,
        help=(
            "Fetch retry schedule as '<seconds>:<retries>' levels. "
            "Default: 20:3,60:3,120:3."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])

    fetch_command = [
        sys.executable,
        str(SCRIPTS_DIR / "fetch_x_raw.py"),
        "--handle",
        args.handle,
        "--take",
        str(args.take),
        "--max-pages",
        str(args.max_pages),
    ]
    if args.cursor:
        fetch_command.extend(["--cursor", args.cursor])
    if args.since:
        fetch_command.extend(["--since", args.since])
    if args.until:
        fetch_command.extend(["--until", args.until])
    fetched = run_fetch_with_retries(
        fetch_command,
        retry_schedule=parse_retry_schedule(args.fetch_retry_schedule),
    )
    if fetched.returncode != 0:
        print(fetched.stdout, end="")
        print(fetched.stderr, end="", file=sys.stderr)
        write_failure_notice("fetch", fetched.stderr or fetched.stdout)
        return fetched.returncode
    raw_run = next((line.strip() for line in fetched.stdout.splitlines() if line.startswith(str(PROJECT_ROOT / "raw"))), "")
    if not raw_run:
        print(f"Could not determine raw run directory from fetch output:\n{fetched.stdout}", file=sys.stderr)
        write_failure_notice("fetch-output", fetched.stdout)
        return 1

    parsed = run_archive_builder(raw_run, args.handle)
    if parsed.returncode != 0:
        print(parsed.stdout, end="")
        print(parsed.stderr, end="", file=sys.stderr)
        write_failure_notice("archive", parsed.stderr or parsed.stdout)
        return parsed.returncode
    if args.parser == "codex":
        archive_outputs = parse_key_value_lines(parsed.stdout)
        detail_path = archive_outputs.get("detailed")
        if not detail_path:
            print(f"Could not determine detailed archive path from archive output:\n{parsed.stdout}", file=sys.stderr)
            write_failure_notice("archive-output", parsed.stdout)
            return 1
        codex_command = [
            sys.executable,
            str(SCRIPTS_DIR / "summarize_x_archive_with_codex.py"),
            "--raw-run",
            raw_run,
            "--detail",
            detail_path,
            "--handle",
            args.handle,
        ]
        parsed = run(codex_command)
        if parsed.returncode != 0:
            print(parsed.stdout, end="")
            print(parsed.stderr, end="", file=sys.stderr)
            write_failure_notice("codex-summary", parsed.stderr or parsed.stdout)
            return parsed.returncode
    outputs = parse_key_value_lines(parsed.stdout)
    report_path = outputs.get("latest") or outputs.get("report")
    if not report_path:
        print(f"Could not determine report path from parse output:\n{parsed.stdout}", file=sys.stderr)
        write_failure_notice("report-output", parsed.stdout)
        return 1

    if args.send:
        if not args.chat_id:
            print("Missing --chat-id or FEISHU_CHAT_ID for --send.", file=sys.stderr)
            return 1
        send_command = [
            sys.executable,
            str(SCRIPTS_DIR / "send_feishu_text.py"),
            "--chat-id",
            args.chat_id,
            "--title",
            args.title,
            "--file",
            report_path,
        ]
        sent = run(send_command)
        print(sent.stdout, end="")
        print(sent.stderr, end="", file=sys.stderr)
        if sent.returncode != 0:
            return sent.returncode

    print(f"raw={raw_run}")
    print(parsed.stdout, end="")
    if args.send:
        print(f"sent={report_path}")
    else:
        print("sent=skipped (pass --send to deliver to Feishu)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
