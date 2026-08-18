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
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
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
X_PROFILE_PREFIX = "https://x.com"
FXTWITTER_API_PREFIX = "https://api.fxtwitter.com"
JINA_PROFILE_PREFIX = "https://r.jina.ai/https://x.com"


class StaleFeedError(RuntimeError):
    """Raised when an endpoint responds successfully with an obsolete feed snapshot."""


class IncompleteRecoveryError(RuntimeError):
    """Raised when a finite recovery snapshot does not cover the requested window."""


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
    if since is not None and newest is not None and newest < since:
        # A current profile whose newest post predates the window confirms that
        # the account had no posts in the requested interval.
        return
    raise StaleFeedError(
        f"Stale recovery feed from {endpoint}: no rows overlap the requested window; "
        f"newest row is {iso_for_cursor(newest)}"
    )


def validate_recovery_coverage(
    rows: list[dict[str, Any]],
    *,
    since: datetime | None,
    endpoint: str,
) -> None:
    if since is None:
        return
    oldest = oldest_row_time(rows)
    if oldest is None:
        raise IncompleteRecoveryError(
            f"Incomplete recovery from {endpoint}: no timestamped rows"
        )
    if oldest > since:
        raise IncompleteRecoveryError(
            f"Incomplete recovery from {endpoint}: oldest exposed row "
            f"{iso_for_cursor(oldest)} is newer than requested since "
            f"{iso_for_cursor(since)}; refusing to publish a partial report"
        )


def fallback_cursor_from_rows(rows: list[dict[str, Any]]) -> str | None:
    oldest = oldest_row_time(rows)
    if oldest is None:
        return None
    return iso_for_cursor(oldest - timedelta(milliseconds=1))


def decode_json_object(raw: bytes) -> dict[str, Any]:
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object, got {type(data).__name__}")
    return data


def fetch_json_with_curl(url: str, timeout: int) -> tuple[dict[str, Any], bytes]:
    try:
        completed = subprocess.run(
            [
                "curl",
                "--fail",
                "--silent",
                "--show-error",
                "--location",
                "--noproxy",
                "*",
                "--max-time",
                str(timeout),
                "--header",
                "Accept: application/json,text/plain,*/*",
                "--header",
                (
                    "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                ),
                url,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout + 5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise urllib.error.URLError(f"curl request failed: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise urllib.error.URLError(
            f"curl exited with status {completed.returncode}: {detail or 'unknown error'}"
        )
    raw = completed.stdout
    return decode_json_object(raw), raw


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
            return decode_json_object(raw), raw
        except transient_errors as exc:
            last_error = exc
            status = getattr(exc, "code", None)
            hostname = urllib.parse.urlparse(url).hostname
            if (
                isinstance(exc, urllib.error.HTTPError)
                and status == 403
                and hostname == urllib.parse.urlparse(FXTWITTER_API_PREFIX).hostname
            ):
                try:
                    return fetch_json_with_curl(url, timeout)
                except urllib.error.URLError as curl_exc:
                    last_error = curl_exc
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


class XProfileArticleParser(HTMLParser):
    def __init__(self, handle: str) -> None:
        super().__init__(convert_charrefs=True)
        self.handle = handle.lower()
        self.article_depth = 0
        self.current: dict[str, str] | None = None
        self.candidates: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag == "article":
            self.article_depth += 1
            if self.article_depth == 1:
                self.current = {}
            return
        if self.article_depth < 1 or self.current is None:
            return
        if tag == "meta":
            itemprop = values.get("itemprop", "")
            if itemprop in {"alternateName", "datePublished"} and itemprop not in self.current:
                self.current[itemprop] = values.get("content", "")
        elif tag == "a" and "status_id" not in self.current:
            href = values.get("href", "")
            match = re.search(
                rf"(?:https://x\.com)?/{re.escape(self.handle)}/status/(\d+)(?:$|[/?#])",
                href,
                re.IGNORECASE,
            )
            if match:
                self.current["status_id"] = match.group(1)

    def handle_endtag(self, tag: str) -> None:
        if tag != "article" or self.article_depth < 1:
            return
        if self.article_depth == 1 and self.current is not None:
            author = self.current.get("alternateName", "").lstrip("@").lower()
            status_id = self.current.get("status_id", "")
            timestamp = self.current.get("datePublished", "")
            if author == self.handle and status_id and timestamp:
                self.candidates.append((status_id, timestamp))
            self.current = None
        self.article_depth -= 1


def extract_x_profile_candidates(profile_html: str, handle: str) -> list[tuple[str, str]]:
    parser = XProfileArticleParser(handle)
    parser.feed(profile_html.replace("\x00", ""))
    return list(dict.fromkeys(parser.candidates))


def twitter_time_to_iso(value: str) -> str:
    dt = datetime.strptime(value, "%a %b %d %H:%M:%S %z %Y")
    return iso_for_cursor(dt) or ""


def public_x_row(
    handle: str,
    status_id: str,
    timestamp: str,
    text: str,
    author: dict[str, Any] | None = None,
    kind: str = "post",
) -> dict[str, Any]:
    author = author or {}
    return {
        "id": f"xpost:{status_id}",
        "kind": kind,
        "sortAt": timestamp,
        "caller": {
            "bio": str(
                author.get("description")
                or (
                    "Only on X, don’t trust fake accs AI/Semi Supply Chains Research "
                    "NFA DYOR, no paid promos; may trade/hold names disc, views my own."
                )
            ),
            "handle": handle,
            "name": str(author.get("name") or "Serenity"),
            "path": f"/c/{handle}",
            "profileImageUrl": str(
                author.get("avatar_url")
                or (
                    "https://pbs.twimg.com/profile_images/"
                    "1996176688414367744/LXfA_lIx_normal.jpg"
                )
            ),
            "xUserId": str(author.get("id") or "1940360837547565056"),
        },
        "post": {
            "canonicalUrl": f"https://x.com/{handle}/status/{status_id}",
            "emphasizedPhrases": [],
            "postedAt": timestamp,
            "text": text,
            "xPostId": status_id,
        },
    }


def fxtwitter_timeline_rows(data: dict[str, Any], handle: str) -> list[dict[str, Any]]:
    results = data.get("results")
    if not isinstance(results, list):
        raise ValueError("FxTwitter timeline response is missing results")
    rows: list[dict[str, Any]] = []
    for result in results:
        if not isinstance(result, dict) or result.get("type") != "status":
            continue
        author = result.get("author")
        author = author if isinstance(author, dict) else {}
        screen_name = str(author.get("screen_name") or "").lstrip("@").lower()
        if screen_name != handle:
            raise ValueError(f"FxTwitter timeline returned unexpected author @{screen_name or 'unknown'}")
        status_id = str(result.get("id") or "")
        text = str(result.get("text") or "").strip()
        created_at = str(result.get("created_at") or "")
        if not status_id or not text or not created_at:
            raise ValueError(f"FxTwitter timeline status is incomplete: id={status_id or 'missing'}")
        timestamp = twitter_time_to_iso(created_at)
        kind = "reply" if result.get("replying_to") else "post"
        rows.append(public_x_row(handle, status_id, timestamp, text, author, kind))
    if not rows:
        raise ValueError(f"FxTwitter timeline for @{handle} produced no usable status rows")
    return rows


def fetch_fxtwitter_timeline_rows(
    *,
    handle: str,
    timeout: int,
    run_dir: Path,
    since: datetime | None,
    max_pages: int = 5,
) -> tuple[list[dict[str, Any]], str]:
    endpoint = f"{FXTWITTER_API_PREFIX}/2/profile/{handle}/statuses"
    rows: list[dict[str, Any]] = []
    cursor = ""
    coverage_reached = since is None
    for page_number in range(1, max_pages + 1):
        params = {"count": "100"}
        if cursor:
            params["cursor"] = cursor
        url = f"{endpoint}?{urllib.parse.urlencode(params)}"
        data, raw = fetch_json(url, timeout)
        (run_dir / f"fxtwitter_timeline_page_{page_number:03d}.json").write_bytes(raw)
        page_rows = fxtwitter_timeline_rows(data, handle)
        rows.extend(page_rows)
        coverage_reached = timeline_page_reaches_since(page_rows, since)
        if coverage_reached:
            break
        cursor_data = data.get("cursor")
        next_cursor = cursor_data.get("bottom") if isinstance(cursor_data, dict) else ""
        if not isinstance(next_cursor, str) or not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor
    if not coverage_reached:
        trailing = next(
            (timestamp for row in reversed(rows) if (timestamp := row_time(row)) is not None),
            None,
        )
        raise IncompleteRecoveryError(
            f"Incomplete FxTwitter timeline recovery from {endpoint}: trailing row "
            f"{iso_for_cursor(trailing)} is newer than requested since "
            f"{iso_for_cursor(since)}; pagination ended before covering the full window"
        )
    return rows, endpoint


def fetch_x_public_rows(
    *,
    handle: str,
    timeout: int,
    run_dir: Path,
) -> tuple[list[dict[str, Any]], str]:
    profile_url = f"{X_PROFILE_PREFIX}/{handle}"
    profile_html = fetch_text(profile_url, timeout)
    (run_dir / "x_profile.html").write_text(profile_html, encoding="utf-8")
    candidates = extract_x_profile_candidates(profile_html, handle)
    if not candidates:
        raise ValueError(f"X public profile for @{handle} exposed no authored status rows")

    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for status_id, profile_timestamp in candidates:
        status_url = f"{FXTWITTER_API_PREFIX}/{handle}/status/{status_id}"
        try:
            data, raw = fetch_json(status_url, timeout)
            (run_dir / f"fxtwitter_status_{status_id}.json").write_bytes(raw)
            tweet = data.get("tweet")
            if not isinstance(tweet, dict):
                raise ValueError("response is missing tweet object")
            author = tweet.get("author")
            author = author if isinstance(author, dict) else {}
            screen_name = str(author.get("screen_name") or "").lstrip("@").lower()
            if screen_name != handle:
                raise ValueError(f"unexpected author @{screen_name or 'unknown'}")
            text = str(tweet.get("text") or "").strip()
            if not text:
                raise ValueError("tweet text is empty")
            created_at = str(tweet.get("created_at") or "")
            timestamp = twitter_time_to_iso(created_at) if created_at else profile_timestamp
            rows.append(public_x_row(handle, status_id, timestamp, text, author))
        except Exception as exc:
            errors.append(f"{status_id}: {exc!r}")
    if errors:
        raise ValueError(
            f"X public recovery was incomplete ({len(rows)}/{len(candidates)} rows): {errors}"
        )
    if not rows:
        raise ValueError(f"X public recovery produced no usable rows: {errors}")
    return rows, profile_url


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
            rows.append(public_x_row(handle, status_id, timestamp, text))
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


def timeline_page_reaches_since(
    rows: list[dict[str, Any]], since: datetime | None
) -> bool:
    if since is None:
        return True
    trailing = next(
        (timestamp for row in reversed(rows) if (timestamp := row_time(row)) is not None),
        None,
    )
    return trailing is not None and trailing <= since


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
        recovery_sources = [
            (
                f"{FXTWITTER_API_PREFIX}/2/profile/{target_handle}/statuses",
                lambda **kwargs: fetch_fxtwitter_timeline_rows(
                    **kwargs,
                    since=since,
                    max_pages=args.max_pages,
                ),
                "FxTwitter profile statuses API",
            ),
            (
                f"{X_PROFILE_PREFIX}/{target_handle}",
                fetch_x_public_rows,
                "X public profile + FxTwitter status API",
            ),
            (
                f"{JINA_PROFILE_PREFIX}/{target_handle}",
                fetch_jina_rows,
                "X public page via Jina Reader",
            ),
        ]
        for recovery_endpoint, recovery_fetcher, recovery_label in recovery_sources:
            try:
                rows, profile_url = recovery_fetcher(
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
                validate_recovery_coverage(
                    rows,
                    since=since,
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
                        "recoverySource": recovery_label,
                    }
                )
                cursor = None
                break
            except Exception as exc:
                endpoint_errors.append(
                    {
                        "endpoint": recovery_endpoint,
                        "error": repr(exc),
                    }
                )
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
