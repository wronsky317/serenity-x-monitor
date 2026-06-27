#!/usr/bin/env python3
"""Hermes daily entrypoint for the Serenity monitor.

This script is intentionally deterministic:
- fetches a recent UTC window from Supercycle/X,
- archives raw JSON under raw/<timestamp>/,
- writes complete parsed markdown under parsed/<timestamp>.md,
- writes a Feishu-friendly report under reports/<timestamp>_report.md and
  reports/latest_summary.md,
- updates state/memory.md.

It does not send Feishu directly. Hermes/Atlas sends the suite digest.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]


PROJECT_ROOT = Path("/Users/wronsky/Documents/codes/serenity-x-monitor")
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
STATE_FILE = PROJECT_ROOT / "state" / "memory.md"
LATEST_REPORT = PROJECT_ROOT / "reports" / "latest_summary.md"


def now_cst() -> datetime:
    if ZoneInfo is None:
        return datetime.now()
    return datetime.now(ZoneInfo("Asia/Shanghai"))


def iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def parse_key_values(stdout: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def read_manifest(raw_run: str) -> dict:
    path = Path(raw_run) / "manifest.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def append_memory(
    *,
    since: str,
    until: str,
    raw_run: str,
    outputs: dict[str, str],
    manifest: dict,
    status: str,
) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    old = STATE_FILE.read_text(encoding="utf-8", errors="replace") if STATE_FILE.exists() else ""
    entry = [
        "## Hermes daily archive run",
        f"Last run: {now_cst().strftime('%Y-%m-%d %H:%M')} CST (Asia/Shanghai)",
        "",
        f"Status: {status}",
        "Source: Supercycle `/api/feed` via `scripts/fetch_x_raw.py` with `before=<nextCursor>` pagination.",
        f"Coverage window UTC: {since} -> {until}",
        f"Raw archive: `{raw_run}`",
        f"Parsed archive: `{outputs.get('detailed', '')}`",
        f"Report: `{outputs.get('report', '')}`",
        f"Latest report: `{outputs.get('latest', '')}`",
        f"Feed rows deduped: `{manifest.get('rowCountDeduped', '')}`",
        f"Serenity rows: `{manifest.get('matchedHandleRowCount', '')}`",
        f"Stopped after since reached: `{manifest.get('stoppedAfterSinceReached', '')}`",
        "",
    ]
    STATE_FILE.write_text("\n".join(entry).rstrip() + "\n\n" + old, encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run daily Serenity archive pipeline for Hermes.")
    parser.add_argument("--window-hours", type=float, default=30.0, help="UTC lookback window. Default: 30 hours.")
    parser.add_argument("--take", type=int, default=50)
    parser.add_argument("--max-pages", type=int, default=120)
    parser.add_argument("--handle", default="aleabitoreddit")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    until_dt = datetime.now(timezone.utc)
    since_dt = until_dt - timedelta(hours=args.window_hours)
    since = iso_utc(since_dt)
    until = iso_utc(until_dt)

    command = [
        sys.executable,
        str(SCRIPTS_DIR / "run_pipeline.py"),
        "--parser",
        "archive",
        "--handle",
        args.handle,
        "--since",
        since,
        "--until",
        until,
        "--take",
        str(args.take),
        "--max-pages",
        str(args.max_pages),
    ]
    completed = run(command)
    if completed.returncode != 0:
        print(completed.stdout, end="")
        print(completed.stderr, end="", file=sys.stderr)
        append_memory(
            since=since,
            until=until,
            raw_run="",
            outputs={},
            manifest={},
            status=f"failed exit={completed.returncode}",
        )
        return completed.returncode

    values = parse_key_values(completed.stdout)
    raw_run = values.get("raw", "")
    manifest = read_manifest(raw_run) if raw_run else {}
    append_memory(
        since=since,
        until=until,
        raw_run=raw_run,
        outputs=values,
        manifest=manifest,
        status="ok",
    )

    if LATEST_REPORT.exists():
        print(LATEST_REPORT.read_text(encoding="utf-8", errors="replace"), end="")
    else:
        print(completed.stdout, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
