#!/usr/bin/env python3
"""Build complete Markdown archives from Serenity raw JSON.

This deterministic parser is useful for large backfills where an LLM summary may
choose to collapse older rows. It writes every matched Serenity row into
parsed/<run_id>.md and a compact report into reports/<run_id>_report.md.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path("/Users/wronsky/Documents/codes/serenity-x-monitor")
RAW_DIR = PROJECT_ROOT / "raw"
PARSED_DIR = PROJECT_ROOT / "parsed"
REPORTS_DIR = PROJECT_ROOT / "reports"
DEFAULT_HANDLE = "aleabitoreddit"
TICKER_RE = re.compile(r"\$([A-Z][A-Z0-9._-]{0,12})\b")


def parse_iso(value: str | None) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    text = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\n{3,}", "\n\n", value.strip())


def one_line(value: str | None, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", clean_text(value))
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def row_post(row: dict[str, Any]) -> dict[str, Any]:
    post = row.get("post")
    return post if isinstance(post, dict) else {}


def row_time(row: dict[str, Any]) -> str:
    post = row_post(row)
    return str(row.get("sortAt") or post.get("postedAt") or "")


def row_url(row: dict[str, Any]) -> str:
    return str(row_post(row).get("canonicalUrl") or "")


def row_text(row: dict[str, Any]) -> str:
    return clean_text(str(row_post(row).get("text") or ""))


def row_xpost_id(row: dict[str, Any]) -> str:
    return str(row_post(row).get("xPostId") or "")


def row_tickers(row: dict[str, Any]) -> list[str]:
    tickers: set[str] = set(TICKER_RE.findall(row_text(row)))
    portfolio = row.get("portfolio")
    if isinstance(portfolio, dict):
        for ticker in portfolio.get("topTickers") or []:
            if isinstance(ticker, str):
                tickers.add(ticker)
        for position in portfolio.get("positions") or []:
            if isinstance(position, dict) and isinstance(position.get("ticker"), str):
                tickers.add(position["ticker"])
    return sorted(tickers)


def latest_raw_run(raw_dir: Path) -> Path:
    runs = sorted(path for path in raw_dir.iterdir() if path.is_dir())
    if not runs:
        raise FileNotFoundError(f"No raw run directories found under {raw_dir}")
    return runs[-1]


def portfolio_block(row: dict[str, Any]) -> list[str]:
    portfolio = row.get("portfolio")
    if not isinstance(portfolio, dict):
        return []
    lines: list[str] = []
    for label, key in [
        ("portfolioId", "id"),
        ("theme", "theme"),
        ("headline", "thesisHeadline"),
        ("summary", "thesisSummary"),
        ("topTickers", "topTickers"),
    ]:
        value = portfolio.get(key)
        if value:
            if isinstance(value, list):
                value = ", ".join(str(item) for item in value)
            lines.append(f"- {label}: {value}")
    positions = portfolio.get("positions")
    if isinstance(positions, list) and positions:
        lines.append("- positions:")
        for position in positions:
            if not isinstance(position, dict):
                continue
            ticker = position.get("ticker") or position.get("displayLabel") or ""
            direction = position.get("direction") or ""
            weight = position.get("weightPercent")
            rationale = one_line(str(position.get("rationale") or ""), 180)
            weight_text = f"{weight}%" if weight is not None else "n/a"
            lines.append(f"  - {ticker}: {direction}, weight={weight_text}, rationale={rationale}")
    return lines


def build_detail(raw_run: Path, rows: list[dict[str, Any]], manifest: dict[str, Any]) -> str:
    rows_sorted = sorted(rows, key=lambda row: parse_iso(row_time(row)), reverse=True)
    kind_counts = Counter(str(row.get("kind") or "unknown") for row in rows_sorted)
    theme_counts: Counter[str] = Counter()
    ticker_counts: Counter[str] = Counter()
    for row in rows_sorted:
        portfolio = row.get("portfolio")
        if isinstance(portfolio, dict) and portfolio.get("theme"):
            theme_counts[str(portfolio["theme"])] += 1
        ticker_counts.update(row_tickers(row))

    times = [row_time(row) for row in rows_sorted if row_time(row)]
    lines = [
        "# Serenity X 完整逐条解析",
        "",
        "## 抓取口径",
        "",
        f"- raw_run: `{raw_run}`",
        f"- handle: `@{manifest.get('handle', DEFAULT_HANDLE)}`",
        f"- requested_since: `{manifest.get('since')}`",
        f"- requested_until: `{manifest.get('until')}`",
        f"- feed_rows_deduped: `{manifest.get('rowCountDeduped')}`",
        f"- serenity_rows: `{len(rows_sorted)}`",
        f"- serenity_newest: `{max(times) if times else ''}`",
        f"- serenity_oldest: `{min(times) if times else ''}`",
        f"- stopped_after_since_reached: `{manifest.get('stoppedAfterSinceReached')}`",
        "",
        "## 分类统计",
        "",
    ]
    for key, value in kind_counts.most_common():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## 主题统计", ""])
    for key, value in theme_counts.most_common():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## 高频证券 / 代码", ""])
    for key, value in ticker_counts.most_common(80):
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## 逐条明细", ""])

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows_sorted:
        grouped[row_time(row)[:10] or "unknown"].append(row)

    index = 1
    for day in sorted(grouped.keys(), reverse=True):
        lines.extend([f"## {day}", ""])
        for row in grouped[day]:
            text = row_text(row)
            tickers = row_tickers(row)
            lines.extend(
                [
                    f"### {index}. {row_time(row)} | {row.get('kind') or 'unknown'}",
                    "",
                    f"- id: `{row.get('id') or ''}`",
                    f"- xPostId: `{row_xpost_id(row)}`",
                    f"- url: {row_url(row)}",
                    f"- skipReason: `{row.get('skipReason') or ''}`",
                    f"- failureReason: `{row.get('failureReason') or ''}`",
                    f"- tickers: {', '.join(tickers) if tickers else '无'}",
                    "",
                    "原文:",
                    "",
                    text if text else "(empty)",
                    "",
                ]
            )
            block = portfolio_block(row)
            if block:
                lines.extend(["Portfolio / thesis:", "", *block, ""])
            index += 1
    return "\n".join(lines).rstrip() + "\n"


def build_report(raw_run: Path, rows: list[dict[str, Any]], manifest: dict[str, Any]) -> str:
    rows_sorted = sorted(rows, key=lambda row: parse_iso(row_time(row)), reverse=True)
    times = [row_time(row) for row in rows_sorted if row_time(row)]
    kind_counts = Counter(str(row.get("kind") or "unknown") for row in rows_sorted)
    theme_counts: Counter[str] = Counter()
    ticker_counts: Counter[str] = Counter()
    month_counts: Counter[str] = Counter()
    for row in rows_sorted:
        month_counts[row_time(row)[:7] or "unknown"] += 1
        portfolio = row.get("portfolio")
        if isinstance(portfolio, dict) and portfolio.get("theme"):
            theme_counts[str(portfolio["theme"])] += 1
        ticker_counts.update(row_tickers(row))

    latest_rows = rows_sorted[:12]
    lines = [
        "# Serenity 2026 回填报告",
        "",
        f"范围：本次从本地 raw 抓取 `{manifest.get('since')}` 到 `{manifest.get('until')}`，共命中 Serenity {len(rows_sorted)} 行；该源内 Serenity 最早命中为 `{min(times) if times else ''}`，最新为 `{max(times) if times else ''}`。",
        "",
        f"抓取完整性：feed 去重后 {manifest.get('rowCountDeduped')} 行，分页 {len(manifest.get('pages') or [])} 页，已翻到 `{manifest.get('lastCursor')}`，`stoppedAfterSinceReached={manifest.get('stoppedAfterSinceReached')}`。",
        "",
        "分类："
    ]
    lines.extend(f"- {key}: {value}" for key, value in kind_counts.most_common())
    lines.extend(["", "月度分布："])
    lines.extend(f"- {key}: {value}" for key, value in sorted(month_counts.items(), reverse=True))
    lines.extend(["", "主要主题："])
    lines.extend(f"- {key}: {value}" for key, value in theme_counts.most_common(15))
    lines.extend(["", "高频代码："])
    lines.append(", ".join(f"{key}({value})" for key, value in ticker_counts.most_common(30)) or "无")
    lines.extend(["", "最新 12 条："])
    for row in latest_rows:
        portfolio = row.get("portfolio") if isinstance(row.get("portfolio"), dict) else {}
        headline = portfolio.get("thesisHeadline") if isinstance(portfolio, dict) else ""
        title = headline or one_line(row_text(row), 120)
        lines.extend(
            [
                f"- {row_time(row)} | {row.get('kind') or 'unknown'} | {title}",
                f"  链接：{row_url(row)}",
                f"  代码：{', '.join(row_tickers(row)) if row_tickers(row) else '无'}",
            ]
        )
    lines.extend(
        [
            "",
            "完整逐条文本和 portfolio 字段已归档到 parsed 目录。本报告只基于本地 JSON，未联网核验，不构成投资买卖建议。",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build complete Serenity Markdown archive/report.")
    parser.add_argument("--raw-run", help="Timestamped raw run directory. Defaults to latest raw/* dir.")
    parser.add_argument("--handle", default=DEFAULT_HANDLE)
    parser.add_argument("--detail-out", help="Optional detailed Markdown path.")
    parser.add_argument("--report-out", help="Optional report Markdown path.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    raw_run = Path(args.raw_run).expanduser() if args.raw_run else latest_raw_run(RAW_DIR)
    handle = args.handle.lower().lstrip("@")
    rows_path = raw_run / f"{handle}.rows.json"
    manifest_path = raw_run / "manifest.json"
    if not rows_path.exists():
        raise SystemExit(f"Rows file not found: {rows_path}")
    if not manifest_path.exists():
        raise SystemExit(f"Manifest file not found: {manifest_path}")

    rows = load_json(rows_path)
    manifest = load_json(manifest_path)
    if not isinstance(rows, list):
        raise SystemExit(f"Expected list rows in {rows_path}")
    rows = [row for row in rows if isinstance(row, dict)]

    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    run_id = raw_run.name
    detail_out = Path(args.detail_out).expanduser() if args.detail_out else PARSED_DIR / f"{run_id}.md"
    report_out = Path(args.report_out).expanduser() if args.report_out else REPORTS_DIR / f"{run_id}_report.md"
    latest_out = REPORTS_DIR / "latest_summary.md"

    detail_out.write_text(build_detail(raw_run, rows, manifest), encoding="utf-8")
    report_out.write_text(build_report(raw_run, rows, manifest), encoding="utf-8")
    shutil.copyfile(report_out, latest_out)

    print(f"detailed={detail_out}")
    print(f"report={report_out}")
    print(f"latest={latest_out}")
    print(f"rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
