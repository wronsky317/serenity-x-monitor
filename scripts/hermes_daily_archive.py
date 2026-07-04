#!/usr/bin/env python3
"""Hermes daily entrypoint for the Serenity monitor.

This script is intentionally deterministic:
- fetches a recent UTC window from Supercycle/X,
- archives raw JSON under raw/<timestamp>/,
- writes complete parsed markdown under parsed/<timestamp>.md,
- writes a Codex CLI synthesized report under reports/<timestamp>_report.md and
  reports/latest_summary.md,
- writes a reviewable long-term-view candidate under
  long_term_views/pending_updates/<date>.md,
- commits and pushes the pending candidate when it changed,
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
DEFAULT_FETCH_RETRY_SCHEDULE = "20:3,60:3,120:3"


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


def report_path_for_run(outputs: dict[str, str], raw_run: str) -> str:
    """Return the report path only when it clearly belongs to this raw run."""
    if not raw_run:
        return ""
    run_id = Path(raw_run).name
    report_path = outputs.get("report", "").strip()
    latest_path = outputs.get("latest", "").strip()
    if not report_path or not latest_path:
        return ""
    if Path(report_path).name != f"{run_id}_report.md":
        return ""
    if Path(latest_path).name != "latest_summary.md":
        return ""
    return report_path


def generate_pending_update(outputs: dict[str, str], raw_run: str) -> dict[str, str]:
    report_path = report_path_for_run(outputs, raw_run)
    if not report_path:
        return {
            "pending_update_status": "failed missing-current-report",
            "pending_update_error": (
                "Pipeline did not return a report path matching the current raw run; "
                "refusing to use reports/latest_summary.md fallback."
            ),
        }
    if not Path(report_path).exists():
        return {
            "pending_update_status": "failed missing-report-file",
            "pending_update_error": f"Current run report file not found: {report_path}",
        }
    command = [
        sys.executable,
        "-B",
        str(SCRIPTS_DIR / "update_long_term_candidates.py"),
        "--report",
        report_path,
        "--raw-run",
        raw_run,
        "--detailed",
        outputs.get("detailed", ""),
        "--date",
        now_cst().strftime("%Y-%m-%d"),
    ]
    completed = run(command)
    if completed.returncode != 0:
        return {
            "pending_update_status": f"failed exit={completed.returncode}",
            "pending_update_error": (completed.stderr or completed.stdout).strip(),
        }
    values = parse_key_values(completed.stdout)
    values["pending_update_status"] = "ok"
    return values


def git_commit_pending_update(path_text: str) -> str:
    if not path_text:
        return "skipped (no pending update path)"
    path = Path(path_text).expanduser()
    if not path.exists():
        return f"skipped (missing {path})"
    try:
        relative = path.resolve().relative_to(PROJECT_ROOT)
    except ValueError:
        return "skipped (pending update outside project)"

    add = run(["git", "add", "--", str(relative)])
    if add.returncode != 0:
        return f"add_failed: {(add.stderr or add.stdout).strip()}"

    diff = run(["git", "diff", "--cached", "--quiet", "--", str(relative)])
    if diff.returncode == 0:
        return "skipped (no staged change)"

    commit = run(
        [
            "git",
            "commit",
            "-m",
            f"Add Serenity pending long-term update {path.stem}",
            "--",
            str(relative),
        ]
    )
    if commit.returncode != 0:
        return f"commit_failed: {(commit.stderr or commit.stdout).strip()}"
    first_line = commit.stdout.splitlines()[0] if commit.stdout.splitlines() else "committed"
    return first_line


def git_push_current_branch() -> str:
    branch = run(["git", "branch", "--show-current"])
    if branch.returncode != 0:
        return f"push_skipped (branch lookup failed): {(branch.stderr or branch.stdout).strip()}"
    branch_name = branch.stdout.strip()
    if not branch_name:
        return "push_skipped (detached HEAD)"

    pushed = run(["git", "push", "origin", branch_name])
    if pushed.returncode != 0:
        return f"push_failed: {(pushed.stderr or pushed.stdout).strip()}"
    first_line = pushed.stderr.splitlines()[0] if pushed.stderr.splitlines() else ""
    return first_line or f"pushed origin/{branch_name}"


def append_memory(
    *,
    since: str,
    until: str,
    raw_run: str,
    outputs: dict[str, str],
    manifest: dict,
    status: str,
    pending_update: dict[str, str] | None = None,
    git_status: str = "",
    git_push_status: str = "",
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
        f"Pending long-term update: `{(pending_update or {}).get('pending_update', '')}`",
        f"Pending update status: `{(pending_update or {}).get('pending_update_status', '')}`",
        f"Git pending update commit: `{git_status}`",
        f"Git pending update push: `{git_push_status}`",
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
    parser.add_argument(
        "--no-git-commit",
        action="store_true",
        help="Write the pending long-term update but do not commit it.",
    )
    parser.add_argument(
        "--no-git-push",
        action="store_true",
        help="Commit the pending long-term update locally but do not push it.",
    )
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
    until_dt = datetime.now(timezone.utc)
    since_dt = until_dt - timedelta(hours=args.window_hours)
    since = iso_utc(since_dt)
    until = iso_utc(until_dt)

    command = [
        sys.executable,
        str(SCRIPTS_DIR / "run_pipeline.py"),
        "--parser",
        "codex",
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
        "--fetch-retry-schedule",
        args.fetch_retry_schedule,
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
    current_report = report_path_for_run(values, raw_run)
    if not current_report:
        append_memory(
            since=since,
            until=until,
            raw_run=raw_run,
            outputs=values,
            manifest=manifest,
            status="failed missing-current-report",
        )
        print(
            "Pipeline completed without a current-run report path; refusing to use old latest_summary.md.",
            file=sys.stderr,
        )
        return 1
    pending_update = generate_pending_update(values, raw_run)
    git_status = "skipped (--no-git-commit)"
    git_push_status = "skipped (no commit)"
    if not args.no_git_commit and pending_update.get("pending_update_status") == "ok":
        git_status = git_commit_pending_update(pending_update.get("pending_update", ""))
        if git_status.startswith("["):
            git_push_status = "skipped (--no-git-push)" if args.no_git_push else git_push_current_branch()
        elif git_status.startswith("skipped"):
            git_push_status = "skipped (no new commit)"
        else:
            git_push_status = "skipped (commit did not succeed)"
    append_memory(
        since=since,
        until=until,
        raw_run=raw_run,
        outputs=values,
        manifest=manifest,
        status="ok",
        pending_update=pending_update,
        git_status=git_status,
        git_push_status=git_push_status,
    )

    if pending_update.get("pending_update_status") != "ok":
        print(pending_update.get("pending_update_error", ""), file=sys.stderr)

    report_to_print = Path(values.get("latest", "")).expanduser()
    if report_to_print.exists() and report_path_for_run(values, raw_run):
        print(report_to_print.read_text(encoding="utf-8", errors="replace"), end="")
    else:
        print(completed.stdout, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
