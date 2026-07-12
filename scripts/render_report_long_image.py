#!/usr/bin/env python3
"""Render a current-run Serenity Markdown report into one readable long PNG."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path("/Users/wronsky/Documents/codes/serenity-x-monitor")
FONT_REGULAR = "/System/Library/Fonts/Hiragino Sans GB.ttc"
FONT_BOLD = "/System/Library/Fonts/STHeiti Medium.ttc"
WIDTH = 1242
MARGIN_X = 72
MARGIN_TOP = 80
MARGIN_BOTTOM = 90
BACKGROUND = "#F6F1E8"
TEXT = "#222222"
MUTED = "#5E625F"
ACCENT = "#B9412D"


def clean_inline_markdown(text: str) -> str:
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^]]+)]\(([^)]+)\)", r"\1（\2）", text)
    return re.sub(r"[*_~]", "", text).strip()


def wrap_pixels(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    if not text:
        return [""]
    lines: list[str] = []
    current = ""
    for char in text:
        candidate = current + char
        if current and draw.textlength(candidate, font=font) > max_width:
            lines.append(current.rstrip())
            current = char.lstrip()
        else:
            current = candidate
    if current or not lines:
        lines.append(current.rstrip())
    return lines


def blocks(markdown: str) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            result.append(("body", clean_inline_markdown(" ".join(paragraph))))
            paragraph.clear()

    for raw in markdown.splitlines():
        line = raw.strip()
        if not line:
            flush()
            continue
        if line.startswith("### "):
            flush()
            result.append(("h3", clean_inline_markdown(line[4:])))
        elif line.startswith("## "):
            flush()
            result.append(("h2", clean_inline_markdown(line[3:])))
        elif line.startswith("# "):
            flush()
            result.append(("h1", clean_inline_markdown(line[2:])))
        elif re.match(r"^[-*]\s+", line):
            flush()
            result.append(("bullet", "• " + clean_inline_markdown(re.sub(r"^[-*]\s+", "", line))))
        elif re.match(r"^\d+[.)、]\s+", line):
            flush()
            result.append(("bullet", clean_inline_markdown(line)))
        elif line.startswith("> "):
            flush()
            result.append(("quote", clean_inline_markdown(line[2:])))
        else:
            paragraph.append(line)
    flush()
    return result


def render(markdown: str, output: Path) -> tuple[int, int]:
    fonts = {
        "h1": ImageFont.truetype(FONT_BOLD, 44),
        "h2": ImageFont.truetype(FONT_BOLD, 34),
        "h3": ImageFont.truetype(FONT_BOLD, 28),
        "body": ImageFont.truetype(FONT_REGULAR, 24),
        "bullet": ImageFont.truetype(FONT_REGULAR, 23),
        "quote": ImageFont.truetype(FONT_REGULAR, 22),
        "footer": ImageFont.truetype(FONT_REGULAR, 18),
    }
    scratch = Image.new("RGB", (WIDTH, 100), BACKGROUND)
    draw = ImageDraw.Draw(scratch)
    layout: list[tuple[str, list[str], int, int]] = []
    height = MARGIN_TOP
    for kind, text in blocks(markdown):
        font = fonts[kind]
        indent = 28 if kind in {"bullet", "quote"} else 0
        spacing_before = {"h1": 0, "h2": 34, "h3": 24, "body": 10, "bullet": 7, "quote": 10}[kind]
        line_height = {"h1": 62, "h2": 49, "h3": 42, "body": 36, "bullet": 35, "quote": 34}[kind]
        wrapped = wrap_pixels(draw, text, font, WIDTH - 2 * MARGIN_X - indent)
        height += spacing_before
        layout.append((kind, wrapped, indent, line_height))
        height += line_height * len(wrapped)
    height += 80 + MARGIN_BOTTOM

    image = Image.new("RGB", (WIDTH, height), BACKGROUND)
    draw = ImageDraw.Draw(image)
    y = MARGIN_TOP
    for kind, wrapped, indent, line_height in layout:
        spacing_before = {"h1": 0, "h2": 34, "h3": 24, "body": 10, "bullet": 7, "quote": 10}[kind]
        y += spacing_before
        if kind == "h2":
            draw.rounded_rectangle((MARGIN_X - 14, y - 5, MARGIN_X - 4, y + 35), radius=5, fill=ACCENT)
        color = ACCENT if kind == "h1" else MUTED if kind == "quote" else TEXT
        for line in wrapped:
            draw.text((MARGIN_X + indent, y), line, font=fonts[kind], fill=color)
            y += line_height
    y += 34
    draw.line((MARGIN_X, y, WIDTH - MARGIN_X, y), fill="#C9C0B2", width=2)
    y += 24
    draw.text(
        (MARGIN_X, y),
        "Serenity X Monitor · 社交媒体观点整理，不构成投资建议",
        font=fonts["footer"],
        fill=MUTED,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG", optimize=True)
    return image.size


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a Serenity report as a long PNG.")
    parser.add_argument("--report", required=True)
    parser.add_argument("--raw-run", required=True)
    parser.add_argument("--output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    report = Path(args.report).expanduser().resolve()
    raw_run = Path(args.raw_run).expanduser().resolve()
    run_id = raw_run.name
    if not raw_run.is_dir() or report.name != f"{run_id}_report.md" or not report.is_file():
        print("render_error=report-does-not-match-current-run", file=sys.stderr)
        return 1
    output = (
        Path(args.output).expanduser().resolve()
        if args.output
        else PROJECT_ROOT / "reports" / f"{run_id}_long.png"
    )
    width, height = render(report.read_text(encoding="utf-8", errors="replace"), output)
    print(f"report_image={output}")
    print(f"report_image_size={width}x{height}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
