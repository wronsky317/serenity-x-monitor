#!/usr/bin/env python3
"""Publish a validated Serenity note through xhs_ai_publisher."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from publish_xhs import build_payload, load_history, now_cst, write_history


XHS_AI_ROOT = Path("/Users/wronsky/Documents/skill_codebases/xhs_ai_publisher")
DEFAULT_STATE_FILE = Path("/Users/wronsky/Documents/codes/serenity-x-monitor/state/xhs_publish_history.json")


async def publish_with_xhs_ai(payload: dict[str, object]) -> bool:
    os.environ.setdefault("XHS_HEADLESS", "false")
    os.environ.setdefault("XHS_ENABLE_FORCE_DOM_ACTIONS", "true")
    os.environ.setdefault("XHS_AUTO_IMPORT_SYSTEM_CHROME_STATE", "true")
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(Path.home() / ".xhs_system" / "ms-playwright"))
    sys.path.insert(0, str(XHS_AI_ROOT))
    from src.core.write_xiaohongshu import XiaohongshuPoster

    tags = payload["tags"]
    body = str(payload["content"]) + "\n\n" + " ".join(f"#{tag}" for tag in tags)
    poster = XiaohongshuPoster()
    await poster.initialize()
    try:
        return await poster.post_article(
            str(payload["title"]),
            body,
            list(payload["images"]),
            auto_publish=True,
        )
    finally:
        await poster.cleanup()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish Serenity through xhs_ai_publisher.")
    parser.add_argument("--xhs-file", required=True)
    parser.add_argument("--raw-run", required=True)
    parser.add_argument("--image", action="append", dest="images", required=True)
    parser.add_argument("--state-file", default=str(DEFAULT_STATE_FILE))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--auto-publish", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    xhs_file = Path(args.xhs_file).expanduser().resolve()
    raw_run = Path(args.raw_run).expanduser().resolve()
    images = [Path(value).expanduser().resolve() for value in args.images]
    state_file = Path(args.state_file).expanduser().resolve()
    payload, fingerprint = build_payload(
        xhs_file=xhs_file,
        raw_run=raw_run,
        images=images,
        published_at=now_cst(),
    )
    history = load_history(state_file)
    if fingerprint in history["published"]:
        print(json.dumps({"status": "skipped-duplicate", "fingerprint": fingerprint}))
        return 0
    if args.dry_run:
        print(json.dumps({"status": "dry-run", "fingerprint": fingerprint, "payload": payload}, ensure_ascii=False))
        return 0
    if not args.auto_publish:
        print("xhs_publish_error=refusing-without---auto-publish", file=sys.stderr)
        return 1
    if not XHS_AI_ROOT.is_dir():
        print(f"xhs_publish_error=engine-not-found:{XHS_AI_ROOT}", file=sys.stderr)
        return 1
    if not asyncio.run(publish_with_xhs_ai(payload)):
        print("xhs_publish_error=engine-did-not-confirm-success", file=sys.stderr)
        return 1
    history["published"][fingerprint] = {
        "published_at": now_cst().isoformat(),
        "title": payload["title"],
        "xhs_file": str(xhs_file),
        "response": {"engine": "xhs_ai_publisher", "status_text": "发布成功"},
    }
    write_history(state_file, history)
    print(json.dumps({"status": "published", "fingerprint": fingerprint}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
