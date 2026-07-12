#!/usr/bin/env python3
"""Validate and publish a current-run Serenity Xiaohongshu note."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import error, request

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]

PROJECT_ROOT = Path("/Users/wronsky/Documents/codes/serenity-x-monitor")
DEFAULT_IMAGE = PROJECT_ROOT / "pic.png"
DEFAULT_STATE_FILE = PROJECT_ROOT / "state" / "xhs_publish_history.json"
DEFAULT_BASE_URL = "http://127.0.0.1:18060"
FIXED_TAGS = ("白毛女神", "长期主义")
MAX_TITLE_LENGTH = 20
MAX_CONTENT_LENGTH = 1000
MAX_TAGS = 10


class PublishError(RuntimeError):
    """A safe, user-facing publish failure."""


def now_cst() -> datetime:
    if ZoneInfo is None:
        return datetime.now()
    return datetime.now(ZoneInfo("Asia/Shanghai"))


def section(markdown: str, heading: str) -> str:
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s+|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(markdown)
    return match.group(1).strip() if match else ""


def recommended_title(markdown: str) -> str:
    candidates = section(markdown, "短标题候选")
    if not candidates:
        raise PublishError("missing-title-candidates")
    first = ""
    for raw in candidates.splitlines():
        match = re.match(r"^\s*\d+[.)、]\s*(.+?)\s*$", raw)
        if not match:
            continue
        title = re.sub(r"[（(]\s*推荐\s*[）)]", "", match.group(1)).strip()
        if not first:
            first = title
        if "推荐" in match.group(1):
            return title
    if not first:
        raise PublishError("missing-title-candidates")
    return first


def parse_tags(markdown: str) -> list[str]:
    source = re.findall(r"#([^#\s]+)", section(markdown, "话题"))
    result: list[str] = []
    for tag in source:
        if tag in FIXED_TAGS or tag in result:
            continue
        result.append(tag)
        if len(result) == MAX_TAGS - len(FIXED_TAGS):
            break
    return result + list(FIXED_TAGS)


def validate_current_run(xhs_file: Path, raw_run: Path) -> str:
    run_id = raw_run.name
    if not raw_run.is_dir():
        raise PublishError(f"raw-run-not-found:{raw_run}")
    if xhs_file.name != f"{run_id}_xhs.md":
        raise PublishError("xhs-file-does-not-match-current-run")
    return run_id


def build_payload(
    *, xhs_file: Path, raw_run: Path, images: list[Path], published_at: datetime
) -> tuple[dict[str, Any], str]:
    run_id = validate_current_run(xhs_file, raw_run)
    if not xhs_file.is_file():
        raise PublishError(f"xhs-file-not-found:{xhs_file}")
    if not images:
        raise PublishError("images-required")
    for image in images:
        if not image.is_file() or image.stat().st_size == 0:
            raise PublishError(f"image-not-found-or-empty:{image}")
    markdown = xhs_file.read_text(encoding="utf-8", errors="replace")
    title = f"【财经】{published_at.strftime('%m%d')} {recommended_title(markdown)}"
    content = section(markdown, "正文")
    tags = parse_tags(markdown)
    if len(title) > MAX_TITLE_LENGTH:
        raise PublishError(f"title-too-long:{len(title)}>{MAX_TITLE_LENGTH}")
    if not content:
        raise PublishError("empty-content")
    if len(content) > MAX_CONTENT_LENGTH:
        raise PublishError(f"content-too-long:{len(content)}>{MAX_CONTENT_LENGTH}")
    if len(tags) > MAX_TAGS or tags[-2:] != list(FIXED_TAGS):
        raise PublishError("invalid-tags")
    payload = {
        "title": title,
        "content": content,
        "images": [str(image.resolve()) for image in images],
        "tags": tags,
        "visibility": "公开可见",
    }
    fingerprint = hashlib.sha256(
        json.dumps(
            {"run_id": run_id, **payload},
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return payload, fingerprint


def load_history(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"published": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublishError(f"invalid-state-file:{exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("published", {}), dict):
        raise PublishError("invalid-state-file-shape")
    data.setdefault("published", {})
    return data


def write_history(path: Path, history: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(history, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_name, path)
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise


def request_json(base_url: str, path: str, *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json; charset=utf-8"} if data else {}
    req = request.Request(
        base_url.rstrip("/") + path,
        data=data,
        headers=headers,
        method="POST" if data else "GET",
    )
    try:
        with request.urlopen(req, timeout=300 if data else 60) as response:
            body = response.read().decode("utf-8", errors="replace")
    except (error.URLError, TimeoutError, socket.timeout) as exc:
        raise PublishError(f"service-request-failed:{path}:{exc}") from exc
    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        raise PublishError(f"invalid-service-response:{path}") from exc
    if not isinstance(result, dict):
        raise PublishError(f"invalid-service-response:{path}")
    return result


def publish(base_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not request_json(base_url, "/health").get("success"):
        raise PublishError("service-unhealthy")
    login = request_json(base_url, "/api/v1/login/status")
    login_data = login.get("data") if isinstance(login.get("data"), dict) else {}
    if not login.get("success") or not login_data.get("is_logged_in"):
        raise PublishError("not-logged-in")
    result = request_json(base_url, "/api/v1/publish", payload=payload)
    if not result.get("success"):
        message = str(result.get("error") or result.get("message") or "")[:500]
        raise PublishError(f"publish-failed:{message}")
    return result


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish a current Serenity Xiaohongshu note.")
    parser.add_argument("--xhs-file", required=True)
    parser.add_argument("--raw-run", required=True)
    parser.add_argument("--image", action="append", dest="images")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--state-file", default=str(DEFAULT_STATE_FILE))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm-publish", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    xhs_file = Path(args.xhs_file).expanduser().resolve()
    raw_run = Path(args.raw_run).expanduser().resolve()
    images = [Path(value).expanduser().resolve() for value in (args.images or [str(DEFAULT_IMAGE)])]
    state_file = Path(args.state_file).expanduser().resolve()
    try:
        payload, fingerprint = build_payload(
            xhs_file=xhs_file, raw_run=raw_run, images=images, published_at=now_cst()
        )
        history = load_history(state_file)
        if fingerprint in history["published"]:
            print(json.dumps({"status": "skipped-duplicate", "fingerprint": fingerprint}))
            return 0
        if args.dry_run:
            print(json.dumps({"status": "dry-run", "fingerprint": fingerprint, "payload": payload}, ensure_ascii=False, indent=2))
            return 0
        if not args.confirm_publish:
            raise PublishError("refusing-to-publish-without---confirm-publish")
        result = publish(args.base_url, payload)
        history["published"][fingerprint] = {
            "published_at": now_cst().isoformat(),
            "title": payload["title"],
            "xhs_file": str(xhs_file),
            "response": result.get("data", {}),
        }
        try:
            write_history(state_file, history)
        except OSError as exc:
            raise PublishError(f"published-state-write-failed:{exc}") from exc
        print(json.dumps({"status": "published", "fingerprint": fingerprint, "data": result.get("data", {})}, ensure_ascii=False))
        return 0
    except PublishError as exc:
        print(f"xhs_publish_error={exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
