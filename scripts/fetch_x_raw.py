#!/usr/bin/env python3
"""Fetch raw X/Supercycle feed rows for Serenity.

This script is intentionally agent-free: it only fetches source data and writes
raw JSON snapshots under the project's raw/ directory. It does not summarize,
edit reports, update memory, or send Feishu messages.
"""

from __future__ import annotations

import argparse
import html
import http.client
import json
import re
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
DEFAULT_MAX_FEED_LAG_HOURS = 12.0
JINA_PROFILE_PREFIX = "https://r.jina.ai/https://x.com"


class StaleFeedError(RuntimeError):
    """Raised when an endpoint responds successfully with an obsolete feed snapshot."""


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


def newest_row_time(rows: list[dict[str, Any]]) -> datetime | None:
    times = [dt for row in rows if (dt := row_time(row)) is not None]
    return max(times) if times else None


def validate_feed_freshness(
    rows: list[dict[str, Any]],
    *,
    until: datetime | None,
    max_lag_hours: float,
    endpoint: str,
) -> None:
    if until is None or max_lag_hours <= 0:
        return
    newest = newest_row_time(rows)
    if newest is None:
        raise StaleFeedError(
            f"Stale Supercycle feed from {endpoint}: first page has no timestamped rows"
        )
    lag = until - newest
    max_lag = timedelta(hours=max_lag_hours)
    if lag > max_lag:
        raise StaleFeedError(
            f"Stale Supercycle feed from {endpoint}: newest row "
            f"{iso_for_cursor(newest)} is {lag.total_seconds() / 3600:.1f}h behind "
            f"requested until {iso_for_cursor(until)} (limit {max_lag_hours:g}h)"
        )


def validate_recovery_window(
    rows: list[dict[str, Any]],
    *,
    since: datetime | None,
    until: datetime | None,
    endpoint: str,
) -> None:
    if any(in_time_window(row, since=since, until=until) for row in rows):
        return
    newest = newest_row_time(rows)
    raise StaleFeedError(
        f"Stale recovery feed from {endpoint}: no rows overlap the requested window; "
        f"newest row is {iso_for_cursor(newest)}"
    )


def fallback_cursor_from_rows(rows: list[dict[str, Any]]) -> str | None:
    oldest = oldest_row_time(rows)
    if oldest is None:
        return None
    return iso_for_cursor(oldest - timedelta(milliseconds=1))


def fetch_json(url: str, timeout: int) -> tuple[dict[str, Any], bytes]:
    # Treat HTTP 4xx/5xx (Cloudflare challenges, rate limits, transient server
    # errors) as retryable. The supercycle.fi CDN frequently returns 403/404/503
    # for a few seconds when challenged, then serves normally — a single failed
    # request should not abort the run.
    transient_errors = (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        http.client.IncompleteRead,
    )
    last_error: BaseException | None = None
    for attempt in range(1, 5):
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
            status = getattr(exc, "code", None)
            # 4xx other than 408 (Request Timeout) / 429 (Too Many Requests) is
            # almost always a permanent client error — no point hammering it.
            if (
                isinstance(exc, urllib.error.HTTPError)
                and status is not None
                and 400 <= status < 500
                and status not in (408, 425, 429)
                and attempt >= 2
            ):
                break
            if attempt == 4:
                break
            time.sleep(1.5 * attempt)
    assert last_error is not None
    raise last_error


def fetch_text(url: str, timeout: int) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "text/plain,*/*",
            "User-Agent": "Mozilla/5.0",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def extract_jina_status_ids(profile_text: str, handle: str) -> list[str]:
    pattern = re.compile(
        rf"https://x\.com/{re.escape(handle)}/status/(\d+)",
        re.IGNORECASE,
    )
    return list(dict.fromkeys(pattern.findall(profile_text)))


def clean_jina_markdown(text: str) -> str:
    value = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    value = re.sub(r"\[([^\]]*)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"\s+", " ", value)
    return html.unescape(value).strip()


def extract_jina_post(status_text: str, handle: str, status_id: str) -> tuple[str, str]:
    published_match = re.search(
        r"^Published Time:\s*(\S+)\s*$",
        status_text,
        re.MULTILINE,
    )
    if not published_match:
        raise ValueError(f"Jina status {status_id} is missing Published Time")
    timestamp = published_match.group(1)
    post_match = re.search(
        (
            rf"\[@{re.escape(handle)}\]\(https://x\.com/{re.escape(handle)}\)"
            rf"\s+(.*?)"
            rf"\[\d{{1,2}}:\d{{2}}\s+[AP]M\s+·\s+[^\]]+\]"
            rf"\(https://x\.com/{re.escape(handle)}/status/{re.escape(status_id)}\)"
        ),
        status_text,
        re.DOTALL | re.IGNORECASE,
    )
    if not post_match:
        raise ValueError(f"Jina status {status_id} is missing the visible post body")
    # X renders the parent/replied-to card between the post's media and its
    # timestamp. The card starts with its own avatar image and is not part of
    # Serenity's post text.
    visible_body = post_match.group(1).split("[![", 1)[0]
    text = clean_jina_markdown(visible_body)
    if not text:
        raise ValueError(f"Jina status {status_id} has an empty post body")
    return timestamp, text


def jina_row(handle: str, status_id: str, timestamp: str, text: str) -> dict[str, Any]:
    return {
        "id": f"xpost:{status_id}",
        "kind": "post",
        "sortAt": timestamp,
        "caller": {
            "bio": (
                "Only on X, don’t trust fake accs AI/Semi Supply Chains Research "
                "NFA DYOR, no paid promos; may trade/hold names disc, views my own."
            ),
            "handle": handle,
            "name": "Serenity",
            "path": f"/c/{handle}",
            "profileImageUrl": (
                "https://pbs.twimg.com/profile_images/"
                "1996176688414367744/LXfA_lIx_normal.jpg"
            ),
            "xUserId": "1940360837547565056",
        },
        "post": {
            "canonicalUrl": f"https://x.com/{handle}/status/{status_id}",
            "emphasizedPhrases": [],
            "postedAt": timestamp,
            "text": text,
            "xPostId": status_id,
        },
    }


def fetch_jina_rows(
    *,
    handle: str,
    timeout: int,
    run_dir: Path,
) -> tuple[list[dict[str, Any]], str]:
    profile_url = f"{JINA_PROFILE_PREFIX}/{handle}"
    profile_text = fetch_text(profile_url, timeout)
    (run_dir / "jina_profile.md").write_text(profile_text, encoding="utf-8")
    status_ids = extract_jina_status_ids(profile_text, handle)
    if not status_ids:
        raise ValueError(f"Jina profile for @{handle} exposed no status URLs")

    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for status_id in status_ids:
        status_url = f"{JINA_PROFILE_PREFIX}/{handle}/status/{status_id}"
        try:
            status_text = fetch_text(status_url, timeout)
            (run_dir / f"jina_status_{status_id}.md").write_text(
                status_text,
                encoding="utf-8",
            )
            timestamp, text = extract_jina_post(status_text, handle, status_id)
            rows.append(jina_row(handle, status_id, timestamp, text))
        except Exception as exc:
            errors.append(f"{status_id}: {exc!r}")
    if not rows:
        raise ValueError(f"Jina status recovery produced no usable rows: {errors}")
    return rows, profile_url


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
            rows = collect_rows_from_page(data)
            validate_feed_freshness(
                rows,
                until=until,
                max_lag_hours=args.max_feed_lag_hours,
                endpoint=endpoint,
            )
            page_file = "page_001.full.json"
            (run_dir / page_file).write_bytes(raw)
            selected_endpoint = endpoint
            raw_rows.extend(rows)
            pages.append({"page": 1, "url": url, "file": page_file, "rows": len(rows)})
            cursor = data.get("nextCursor") if isinstance(data.get("nextCursor"), str) else None
            if cursor:
                seen_cursors.add(cursor)
            break
        except Exception as exc:
            endpoint_errors.append({"endpoint": endpoint, "error": repr(exc)})

    if not selected_endpoint:
        target_handle = args.handle.lower().lstrip("@")
        try:
            rows, profile_url = fetch_jina_rows(
                handle=target_handle,
                timeout=args.timeout,
                run_dir=run_dir,
            )
            validate_recovery_window(
                rows,
                since=since,
                until=until,
                endpoint=profile_url,
            )
            page_file = "page_001.full.json"
            dump_json(run_dir / page_file, {"rows": rows, "source": profile_url})
            selected_endpoint = profile_url
            raw_rows.extend(rows)
            pages.append(
                {
                    "page": 1,
                    "url": profile_url,
                    "file": page_file,
                    "rows": len(rows),
                    "recoverySource": "X public page via Jina Reader",
                }
            )
            cursor = None
        except Exception as exc:
            endpoint_errors.append(
                {
                    "endpoint": f"{JINA_PROFILE_PREFIX}/{target_handle}",
                    "error": repr(exc),
                }
            )
            raise RuntimeError(f"All endpoints failed: {endpoint_errors}") from exc

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
    parser.add_argument(
        "--max-feed-lag-hours",
        type=float,
        default=DEFAULT_MAX_FEED_LAG_HOURS,
        help=(
            "Reject an endpoint when its newest first-page row is older than this many "
            "hours relative to --until. Use 0 to disable. Default: 12."
        ),
    )
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
        print(
            f"Fetch failed: {exc}; details written to {run_dir / 'manifest.json'}",
            file=sys.stderr,
        )
        return 1

    print(run_dir)
    print(
        f"Matched {manifest['matchedHandleRowCount']} @{manifest['handle']} rows "
        f"from {manifest['rowCountDeduped']} filtered rows"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
