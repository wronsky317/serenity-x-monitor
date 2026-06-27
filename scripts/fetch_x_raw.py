#!/usr/bin/env python3
"""Fetch raw X/Supercycle feed rows for Serenity.

This script is intentionally agent-free: it only fetches source data and writes
raw JSON snapshots under the project's raw/ directory. It does not summarize,
edit reports, update memory, or send Feishu messages.
"""

from __future__ import annotations

import argparse
import http.client
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path("/Users/wronsky/Documents/codes/serenity-x-monitor")
DEFAULT_RAW_DIR = PROJECT_ROOT / "raw"
DEFAULT_HANDLE = "aleabitoreddit"
DEFAULT_ENDPOINTS = (
    "https://supercycle.fi/api/feed",
    "https://api.supercycle.fi/api/feed",
)


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def parse_iso_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso_for_cursor(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def row_time(row: dict[str, Any]) -> datetime | None:
    value = row.get("sortAt")
    if not isinstance(value, str):
        post = row.get("post")
        if isinstance(post, dict):
            value = post.get("postedAt")
    if not isinstance(value, str):
        return None
    try:
        return parse_iso_utc(value)
    except ValueError:
        return None


def in_time_window(row: dict[str, Any], since: datetime | None, until: datetime | None) -> bool:
    dt = row_time(row)
    if dt is None:
        return False
    if since is not None and dt < since:
        return False
    if until is not None and dt > until:
        return False
    return True


def oldest_row_time(rows: list[dict[str, Any]]) -> datetime | None:
    times = [dt for row in rows if (dt := row_time(row)) is not None]
    return min(times) if times else None


def fallback_cursor_from_rows(rows: list[dict[str, Any]]) -> str | None:
    oldest = oldest_row_time(rows)
    if oldest is None:
        return None
    return iso_for_cursor(oldest - timedelta(milliseconds=1))


def fetch_json(url: str, timeout: int) -> tuple[dict[str, Any], bytes]:
    transient_errors = (urllib.error.URLError, TimeoutError, http.client.IncompleteRead)
    last_error: BaseException | None = None
    for attempt in range(1, 4):
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json,text/plain,*/*",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                ),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError(f"Expected JSON object, got {type(data).__name__}")
            return data, raw
        except transient_errors as exc:
            last_error = exc
            if attempt == 3:
                break
            time.sleep(1.5 * attempt)
    assert last_error is not None
    raise last_error


def build_url(endpoint: str, take: int, cursor: str | None) -> str:
    params: dict[str, str] = {"take": str(take)}
    if cursor:
        # Supercycle history pagination walks backward with `before`; `cursor`
        # can repeat recent rows and fail to reach older pages.
        params["before"] = cursor
    return f"{endpoint}?{urllib.parse.urlencode(params)}"


def row_handle(row: dict[str, Any]) -> str:
    caller = row.get("caller")
    if not isinstance(caller, dict):
        return ""
    return str(caller.get("handle") or "").lstrip("@").lower()


def dump_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def collect_rows_from_page(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = data.get("rows")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def should_stop_after_page(rows: list[dict[str, Any]], since: datetime | None) -> bool:
    oldest = oldest_row_time(rows)
    return since is not None and oldest is not None and oldest < since


def fetch_pages(args: argparse.Namespace, run_dir: Path) -> dict[str, Any]:
    endpoint_errors: list[dict[str, str]] = []
    selected_endpoint = ""
    pages: list[dict[str, Any]] = []
    raw_rows: list[dict[str, Any]] = []
    seen_cursors: set[str] = set()
    cursor_fallbacks: list[dict[str, Any]] = []
    since = parse_iso_utc(args.since)
    until = parse_iso_utc(args.until)
    if since is not None and until is not None and since > until:
        raise ValueError("--since must be earlier than or equal to --until")
    cursor: str | None = args.cursor or iso_for_cursor(until)

    for endpoint in args.endpoint:
        try:
            url = build_url(endpoint, args.take, cursor)
            data, raw = fetch_json(url, args.timeout)
            page_file = "page_001.full.json"
            (run_dir / page_file).write_bytes(raw)
            selected_endpoint = endpoint
            rows = collect_rows_from_page(data)
            raw_rows.extend(rows)
            pages.append({"page": 1, "url": url, "file": page_file, "rows": len(rows)})
            cursor = data.get("nextCursor") if isinstance(data.get("nextCursor"), str) else None
            if cursor:
                seen_cursors.add(cursor)
            break
        except Exception as exc:
            endpoint_errors.append({"endpoint": endpoint, "error": repr(exc)})

    if not selected_endpoint:
        raise RuntimeError(f"All endpoints failed: {endpoint_errors}")

    stop_for_since = should_stop_after_page(raw_rows, since)
    for page_number in range(2, args.max_pages + 1):
        if stop_for_since or not cursor:
            break
        if cursor in seen_cursors and page_number > 2:
            fallback_cursor = fallback_cursor_from_rows(raw_rows)
            if not fallback_cursor or fallback_cursor in seen_cursors:
                break
            cursor_fallbacks.append(
                {
                    "page": page_number,
                    "reason": "cursor repeated before fetch",
                    "oldCursor": cursor,
                    "fallbackCursor": fallback_cursor,
                }
            )
            cursor = fallback_cursor
        seen_cursors.add(cursor)
        time.sleep(args.sleep)
        url = build_url(selected_endpoint, args.take, cursor)
        try:
            data, raw = fetch_json(url, args.timeout)
        except (
            urllib.error.URLError,
            TimeoutError,
            http.client.IncompleteRead,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            pages.append({"page": page_number, "url": url, "error": repr(exc)})
            break
        page_file = f"page_{page_number:03d}.full.json"
        (run_dir / page_file).write_bytes(raw)
        rows = collect_rows_from_page(data)
        raw_rows.extend(rows)
        pages.append({"page": page_number, "url": url, "file": page_file, "rows": len(rows)})
        stop_for_since = should_stop_after_page(rows, since)
        next_cursor = data.get("nextCursor") if isinstance(data.get("nextCursor"), str) else None
        if not next_cursor:
            cursor = next_cursor
            break
        if next_cursor == cursor or next_cursor in seen_cursors:
            fallback_cursor = fallback_cursor_from_rows(rows)
            if not fallback_cursor or fallback_cursor == cursor or fallback_cursor in seen_cursors:
                cursor = next_cursor
                break
            cursor_fallbacks.append(
                {
                    "page": page_number,
                    "reason": "api returned repeated nextCursor",
                    "oldCursor": next_cursor,
                    "fallbackCursor": fallback_cursor,
                }
            )
            cursor = fallback_cursor
            continue
        cursor = next_cursor

    deduped_unfiltered: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for row in raw_rows:
        post = row.get("post") if isinstance(row.get("post"), dict) else {}
        row_id = str(row.get("id") or post.get("xPostId") or "")
        if row_id and row_id in seen_ids:
            continue
        if row_id:
            seen_ids.add(row_id)
        deduped_unfiltered.append(row)

    deduped_rows = [
        row for row in deduped_unfiltered if in_time_window(row, since=since, until=until)
    ]
    target_handle = args.handle.lower().lstrip("@")
    handle_rows = [row for row in deduped_rows if row_handle(row) == target_handle]

    dump_json(run_dir / "all_rows.unfiltered.deduped.json", deduped_unfiltered)
    dump_json(run_dir / "all_rows.deduped.json", deduped_rows)
    dump_json(run_dir / f"{target_handle}.rows.json", handle_rows)

    return {
        "runStartedAtUtc": args.run_started_at,
        "selectedEndpoint": selected_endpoint,
        "endpointErrors": endpoint_errors,
        "handle": target_handle,
        "take": args.take,
        "maxPages": args.max_pages,
        "cursor": args.cursor,
        "paginationParam": "before",
        "since": iso_for_cursor(since),
        "until": iso_for_cursor(until),
        "effectiveInitialCursor": args.cursor or iso_for_cursor(until),
        "pages": pages,
        "rowCountDedupedUnfiltered": len(deduped_unfiltered),
        "rowCountDeduped": len(deduped_rows),
        "matchedHandleRowCount": len(handle_rows),
        "lastCursor": cursor,
        "stoppedAfterSinceReached": stop_for_since,
        "cursorFallbacks": cursor_fallbacks,
        "outputDir": str(run_dir),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch raw Serenity X rows into raw/.")
    parser.add_argument("--handle", default=DEFAULT_HANDLE, help="X handle to filter after fetching.")
    parser.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR), help="Directory for raw snapshots.")
    parser.add_argument(
        "--take",
        type=int,
        default=50,
        help="Rows requested per Supercycle API page. Example: --take 50.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=5,
        help=(
            "Safety cap on cursor pages to fetch. The rough scan limit is "
            "take * max-pages, but fetching stops earlier after reaching --since."
        ),
    )
    parser.add_argument("--cursor", help="Optional Supercycle cursor, usually an ISO timestamp.")
    parser.add_argument("--since", help="Inclusive UTC lower bound, e.g. 2026-06-20T00:00:00Z.")
    parser.add_argument("--until", help="Inclusive UTC upper bound, e.g. 2026-06-27T00:00:00Z.")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds.")
    parser.add_argument("--sleep", type=float, default=0.4, help="Delay between pages.")
    parser.add_argument("--endpoint", action="append", default=list(DEFAULT_ENDPOINTS))
    args = parser.parse_args(argv)
    args.run_started_at = datetime.now(timezone.utc).isoformat()
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    raw_dir = Path(args.raw_dir).expanduser()
    run_dir = raw_dir / now_stamp()
    run_dir.mkdir(parents=True, exist_ok=True)
    try:
        manifest = fetch_pages(args, run_dir)
        dump_json(run_dir / "manifest.json", manifest)
    except Exception as exc:
        error_manifest = {
            "runStartedAtUtc": args.run_started_at,
            "error": repr(exc),
            "handle": args.handle.lower().lstrip("@"),
            "since": args.since,
            "until": args.until,
            "outputDir": str(run_dir),
        }
        dump_json(run_dir / "manifest.json", error_manifest)
        print(f"Fetch failed; details written to {run_dir / 'manifest.json'}", file=sys.stderr)
        return 1

    print(run_dir)
    print(
        f"Matched {manifest['matchedHandleRowCount']} @{manifest['handle']} rows "
        f"from {manifest['rowCountDeduped']} filtered rows"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
