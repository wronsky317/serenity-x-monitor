#!/usr/bin/env python3
"""Publish a validated Serenity note through xhs_ai_publisher."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from publish_xhs import build_payload, load_history, now_cst, write_history


XHS_AI_ROOT = Path("/Users/wronsky/Documents/skill_codebases/xhs_ai_publisher")
DEFAULT_STATE_FILE = Path("/Users/wronsky/Documents/codes/serenity-x-monitor/state/xhs_publish_history.json")

CONTENT_SELECTORS = (
    "div[data-placeholder*='请输入正文'] div[contenteditable='true']",
    "div[data-placeholder*='正文描述'] div[contenteditable='true']",
    "div[data-placeholder*='正文'] div[contenteditable='true']",
    "div.tiptap div.ProseMirror[contenteditable='true']",
    "div.ProseMirror[contenteditable='true']",
    "[role='textbox'][contenteditable='true']",
    "[contenteditable='true'][role='textbox']",
    "[contenteditable='true']:nth-child(2)",
    ".note-content",
    "[data-placeholder='添加正文']",
    ".DraftEditor-root",
    "div[data-placeholder*='请输入正文'] p.is-editor-empty:first-child",
    "p.is-editor-empty:first-child",
)


async def find_content_editor(page):
    for selector in CONTENT_SELECTORS:
        locator = page.locator(selector).first
        if await locator.count() <= 0:
            continue
        try:
            await locator.wait_for(state="visible", timeout=3_000)
            return locator
        except Exception:
            continue
    raise RuntimeError("xhs_topic_error=content-editor-not-found")


async def append_linked_topics(page, tags: list[str]) -> None:
    """Insert topics through XHS suggestions so they become linked topic nodes."""
    editor = await find_content_editor(page)
    await editor.evaluate("""el => {
        const root = el.matches('[contenteditable="true"]')
            ? el
            : el.closest('[contenteditable="true"]');
        if (!root) throw new Error('contenteditable root not found');
        root.focus();
        const range = document.createRange();
        range.selectNodeContents(root);
        range.collapse(false);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
    }""")
    await page.keyboard.press("Enter")
    await page.keyboard.press("Enter")

    for raw_tag in tags:
        tag = str(raw_tag).lstrip("#").strip()
        if not tag:
            continue
        await page.keyboard.insert_text("#")
        await page.keyboard.type(tag, delay=50)

        container = page.locator("#creator-editor-topic-container")
        try:
            await container.wait_for(state="visible", timeout=5_000)
            items = container.locator(".item")
            await items.first.wait_for(state="visible", timeout=5_000)
            matching = items.filter(has_text=tag)
            if await matching.count() > 0:
                candidate = matching.first
            else:
                candidate = items.first
            if await candidate.count() <= 0:
                raise RuntimeError("no candidate")
            await candidate.click(timeout=5_000)
            await page.wait_for_timeout(300)
        except Exception as exc:
            raise RuntimeError(f"xhs_topic_error=suggestion-not-selected:{tag}") from exc
        print(f"已选择小红书话题: #{tag}")


async def publish_prepared_article(poster, title: str) -> bool:
    """Publish a form already prepared by xhs_ai_publisher and verify success."""
    page = poster.page
    initial_url = page.url or ""
    selectors = (
        "xhs-publish-btn[is-publish='true']",
        "xhs-publish-btn",
        "button:has-text('确认发布')",
        "button:has-text('立即发布')",
        "button:has-text('发布')",
        ".submit-btn",
        ".publish-btn",
        "[data-testid='publish']",
    )
    clicked = False
    last_error = None
    for selector in selectors:
        try:
            matches = page.locator(selector)
            if await matches.count() <= 0:
                continue
            button = matches.last
            await button.wait_for(state="visible", timeout=5_000)
            await button.scroll_into_view_if_needed()
            if selector.startswith("xhs-publish-btn"):
                component_clicked = False
                inner = button.locator("button").filter(has_text="发布").last
                if await inner.count() > 0:
                    try:
                        await inner.click(timeout=8_000)
                        component_clicked = True
                    except Exception:
                        pass
                if not component_clicked:
                    component_clicked = bool(await button.evaluate("""el => {
                        const buttons = [...(el.shadowRoot?.querySelectorAll('button') || [])];
                        const target = buttons.find(x => (x.innerText || x.textContent || '').includes('发布'));
                        if (!target || target.disabled) return false;
                        target.click(); return true;
                    }"""))
                if not component_clicked:
                    box = await button.bounding_box()
                    if not box:
                        raise RuntimeError("publish component has no clickable box")
                    await page.mouse.click(
                        box["x"] + box["width"] * 0.65,
                        box["y"] + box["height"] * 0.5,
                    )
                    component_clicked = True
            else:
                await button.click(timeout=8_000)
            clicked = True
            print(f"已点击最终发布按钮: {selector}")
            break
        except Exception as exc:
            last_error = exc
    if not clicked:
        raise RuntimeError(f"xhs_publish_error=publish-button-not-clicked:{last_error}")

    for selector in (
        "div[role='dialog'] button:has-text('确认发布')",
        "div[role='dialog'] button:has-text('确认')",
        ".el-dialog button:has-text('确认发布')",
        ".el-dialog button:has-text('确认')",
    ):
        try:
            button = page.locator(selector).last
            if await button.count() > 0 and await button.is_visible():
                await button.click(timeout=5_000)
                break
        except Exception:
            continue

    deadline = time.time() + 30
    while time.time() < deadline:
        if await poster._has_blocking_auth_issue():
            raise RuntimeError("xhs_publish_error=authentication-lost")
        for text in ("发布成功", "发布完成", "审核中", "已发布"):
            try:
                if await page.locator(f"text={text}").first.is_visible():
                    return True
            except Exception:
                pass
        current_url = page.url or ""
        if current_url and current_url != initial_url:
            lowered = current_url.lower()
            if "publish" not in lowered and "/edit" not in lowered and "login" not in lowered:
                return True
        await asyncio.sleep(0.5)

    verify_page = None
    try:
        verify_page = await poster.context.new_page()
        await verify_page.goto(
            "https://creator.xiaohongshu.com/publish/manage",
            wait_until="domcontentloaded",
            timeout=30_000,
        )
        await verify_page.wait_for_timeout(5_000)
        exact_title = verify_page.get_by_text(title, exact=True)
        return await exact_title.count() > 0 and await exact_title.first.is_visible()
    finally:
        if verify_page:
            await verify_page.close()


async def publish_with_xhs_ai(payload: dict[str, object]) -> bool:
    os.environ.setdefault("XHS_HEADLESS", "false")
    os.environ.setdefault("XHS_ENABLE_FORCE_DOM_ACTIONS", "true")
    os.environ.setdefault("XHS_AUTO_IMPORT_SYSTEM_CHROME_STATE", "true")
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(Path.home() / ".xhs_system" / "ms-playwright"))
    sys.path.insert(0, str(XHS_AI_ROOT))
    from src.core.write_xiaohongshu import XiaohongshuPoster

    tags = [str(tag) for tag in payload["tags"]]
    body = str(payload["content"])
    poster = XiaohongshuPoster()
    await poster.initialize()
    try:
        prepared = await poster.post_article(
            str(payload["title"]),
            body,
            list(payload["images"]),
            auto_publish=False,
        )
        if not prepared:
            return False
        await append_linked_topics(poster.page, tags)
        return await publish_prepared_article(poster, str(payload["title"]))
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
