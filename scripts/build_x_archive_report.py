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

THEME_ZH = {
    "PHOTONICS": "光互连 / CPO / 光子链",
    "SEMIS": "半导体 / Memory",
    "AI INFRA": "AI 基建 / 电力与算力基础设施",
    "NEOCLOUD": "Neocloud / AI 算力平台",
    "CRYPTO": "Crypto / 链上金融",
    "SOFTWARE": "软件 / 机器人链",
    "FINTECH": "金融科技",
    "MACRO": "宏观利率",
    "EV": "机器人 / EV 供应链",
    "ENERGY": "能源 / 储能",
    "CONSUMER": "消费 / 主题交易",
    "MEDIA": "平台 / 媒体",
    "OTHER": "其他",
}


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


def has_word(text: str, word: str) -> bool:
    return re.search(rf"\b{re.escape(word)}\b", text) is not None


def has_memory_anchor(text: str, tickers: list[str]) -> bool:
    return (
        "MU" in tickers
        or has_word(text, "mu")
        or has_word(text, "micron")
        or "sk hynix" in text
        or "samsung memory" in text
        or "samsung hbm" in text
    )


def has_robotics_anchor(text: str) -> bool:
    return any(
        word in text
        for word in [
            "robotics",
            "robot",
            "robots",
            "optimus",
            "schaeffler",
            "nabtesco",
            "sanhua",
            "actuator",
            "actuators",
            "gearbox",
            "gearboxes",
        ]
    )


def row_theme(row: dict[str, Any]) -> str:
    portfolio = row.get("portfolio")
    if isinstance(portfolio, dict) and isinstance(portfolio.get("theme"), str):
        theme = portfolio["theme"]
        text = row_text(row).lower()
        if theme == "SEMIS" and has_robotics_anchor(text) and not has_memory_anchor(text, row_tickers(row)):
            return "EV"
        return theme
    text = row_text(row).lower()
    if any(word in text for word in ["cpo", "photonics", "laser", "optical", "sive", "lite"]):
        return "PHOTONICS"
    if has_robotics_anchor(text):
        return "EV"
    if any(word in text for word in ["memory", "hbm", "dram", "nand", "micron", "sk hynix"]):
        return "SEMIS"
    if any(word in text for word in ["fed", "fomc", "treasury"]) or has_word(text, "rate"):
        return "MACRO"
    if any(word in text for word in ["power semi", "800v", "data center", "datacenter"]):
        return "AI INFRA"
    if any(word in text for word in ["nbis", "iren", "neocloud"]):
        return "NEOCLOUD"
    return "OTHER"


def theme_zh(theme: str) -> str:
    return THEME_ZH.get(theme, theme or "其他")


def row_headline(row: dict[str, Any]) -> str:
    portfolio = row.get("portfolio")
    if isinstance(portfolio, dict) and isinstance(portfolio.get("thesisHeadline"), str):
        return portfolio["thesisHeadline"]
    return one_line(row_text(row), 140)


def zh_row_title(row: dict[str, Any]) -> str:
    text_l = row_text(row).lower()
    tickers = row_tickers(row)
    if "spacex" in text_l and any(ticker in tickers for ticker in ["LITE", "SIVE", "SIVE.ST", "POET", "MTSI"]):
        return "SpaceX 线索强化光互连供应链与潜在并购目标"
    if "deepseek" in text_l or "distillation" in text_l or "kyc" in text_l:
        return "DeepSeek/模型蒸馏引出美国前沿模型访问控制问题"
    if has_robotics_anchor(text_l):
        return "机器人供应链与汽车零部件玩家的长期可选性"
    if "openai" in text_l and ("model" in text_l or "anthropic" in text_l):
        return "OpenAI 新模型叙事强化 AI 平台竞争观察"
    if "million+" in text_l and "sive" in text_l:
        return "SIVE 仓位与 hyperscaler mapping conviction 被再次强化"
    if (
        "federal reserve" in text_l
        or "fomc" in text_l
        or ("morgan stanley" in text_l and ("rate" in text_l or "fed" in text_l or "no-hike" in text_l))
    ):
        return "Morgan Stanley 维持不加息预测，利好长久期美债叙事"
    if any(word in text_l for word in ["memory", "hbm", "dram", "nand"]) and has_memory_anchor(text_l, tickers):
        return "AI memory/HBM 供需紧张继续强化"
    if "softbank" in text_l or "ipo" in text_l:
        return "SoftBank/OpenAI IPO 延迟带来 AI 资产估值风险提示"
    if "global correction" in text_l or "kospi" in text_l or "nikkei" in text_l:
        return "全球市场回调下高 beta 资产承压"
    if "power semi" in text_l or "yangjie" in text_l or "800v" in text_l:
        return "中国功率半导体涨价向 US power semi 和 800V DC 链条传导"
    return row_headline(row)


def row_summary_source(row: dict[str, Any]) -> str:
    portfolio = row.get("portfolio")
    if isinstance(portfolio, dict) and isinstance(portfolio.get("thesisSummary"), str):
        return portfolio["thesisSummary"]
    return row_text(row)


def zh_row_takeaway(row: dict[str, Any]) -> str:
    text = row_text(row)
    text_l = text.lower()
    tickers = row_tickers(row)
    ticker_text = ", ".join(tickers) if tickers else "无明确代码"
    headline = row_headline(row)
    url = row_url(row)

    if "spacex" in text_l and any(ticker in tickers for ticker in ["LITE", "SIVE", "SIVE.ST", "POET", "MTSI"]):
        view = "SpaceX 相关线索强化了光互连供应链的重要性，Serenity 将 LITE、SIVE、POET、MTSI 等放在光学供应商和潜在并购目标框架里。"
    elif "deepseek" in text_l or "distillation" in text_l or "kyc" in text_l:
        view = "AI 安全与模型蒸馏成为新增政策变量：低成本中国模型、账号滥用、前沿模型访问控制，会影响美国 AI 平台和推理成本竞争。"
    elif has_robotics_anchor(text_l):
        view = "Serenity 将 Schaeffler、Nabtesco、三花等汽车零部件/执行器玩家放进 humanoid/Optimus 供应链框架，核心是传统汽车业务估值拖累下的机器人收入可选性；但当前收入占比仍小，需要下游机器人龙头和 2027 之后放量验证。"
    elif "openai" in text_l and ("model" in text_l or "anthropic" in text_l):
        view = "OpenAI 新模型叙事被视为 AI 模型竞争重新加速的信号，但该条未形成可直接落地的组合，更多是 AI 平台竞争观察。"
    elif "million+" in text_l and "sive" in text_l:
        view = "Serenity 明确强化 SIVE 仓位和研究 conviction，核心仍是 hyperscaler mapping、2027 volume ramp、Nasdaq listing 和向 LITE 式路径重估。"
    elif (
        "federal reserve" in text_l
        or "fomc" in text_l
        or ("morgan stanley" in text_l and ("rate" in text_l or "fed" in text_l or "no-hike" in text_l))
    ):
        view = "宏观上偏向“年内不加息/利率压力缓和”，对应长久期美债 TLT、IEF 的顺风，但需要继续验证通胀和 Fed 口径。"
    elif any(word in text_l for word in ["memory", "hbm", "dram", "nand"]) and has_memory_anchor(text_l, tickers):
        view = "Memory/HBM 结构性短缺继续被强化，MU、SK Hynix、Samsung 是核心表达；逻辑是 AI 需求、涨价和供给不足共同驱动。"
    elif "softbank" in text_l or "ipo" in text_l:
        view = "SoftBank/OpenAI IPO 延迟属于 AI 资产估值和流动性风险提示，更多是事件评论，不是明确新增做多主线。"
    elif "global correction" in text_l or "kospi" in text_l or "nikkei" in text_l:
        view = "市场层面提示高 beta 回调压力，SOI、RKLB 等高弹性标的在指数快速下跌中承压，但不一定破坏长期 AI 供应链逻辑。"
    elif "power semi" in text_l or "yangjie" in text_l or "800v" in text_l:
        view = "中国功率半导体涨价被解读为需求验证，并向 AOSL、POWI、铜/材料和 800V DC AI 数据中心电力链传导。"
    else:
        summary = one_line(row_summary_source(row), 180)
        view = f"{headline}。{summary}"

    pieces = [
        f"{theme_zh(row_theme(row))}",
        f"时间：{row_time(row)}",
        f"涉及：{ticker_text}",
        f"观点：{view}",
    ]
    if url:
        pieces.append(f"来源：{url}")
    return "\n".join(f"- {piece}" for piece in pieces)


def row_is_contentful(row: dict[str, Any]) -> bool:
    if row.get("kind") == "thesis":
        return True
    text = row_text(row).lower()
    if row_tickers(row):
        return True
    return any(
        keyword in text
        for keyword in [
            "openai",
            "deepseek",
            "distillation",
            "fed",
            "softbank",
            "memory",
            "spacex",
            "sive",
            "power semi",
        ]
    )


def row_importance(row: dict[str, Any]) -> int:
    text = row_text(row).lower()
    score = 0
    if row.get("kind") == "thesis":
        score += 40
    theme = row_theme(row)
    if theme == "PHOTONICS":
        score += 35
    elif theme == "SEMIS":
        score += 30
    elif theme == "AI INFRA":
        score += 25
    elif theme == "NEOCLOUD":
        score += 20
    elif theme == "MACRO":
        score += 10
    if "million+" in text and "sive" in text:
        score += 35
    if "spacex" in text:
        score += 25
    if "memory" in text or "hbm" in text:
        score += 20
    if "power semi" in text or "800v" in text:
        score += 18
    if "deepseek" in text or "distillation" in text:
        score += 10
    if row.get("kind") == "failed":
        score -= 10
    return score


def build_theme_summary(rows_sorted: list[dict[str, Any]]) -> list[str]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows_sorted:
        if row_is_contentful(row):
            grouped[row_theme(row)].append(row)

    theme_order = [
        "PHOTONICS",
        "SEMIS",
        "AI INFRA",
        "NEOCLOUD",
        "MACRO",
        "SOFTWARE",
        "EV",
        "CRYPTO",
        "FINTECH",
        "OTHER",
    ]
    lines: list[str] = []
    for theme in theme_order:
        rows = grouped.get(theme, [])
        if not rows:
            continue
        ticker_counter: Counter[str] = Counter()
        for row in rows:
            ticker_counter.update(row_tickers(row))
        tickers = ", ".join(ticker for ticker, _ in ticker_counter.most_common(8)) or "无明确代码"
        latest = rows[0]
        headline = zh_row_title(latest)
        lines.append(
            f"- {theme_zh(theme)}：{len(rows)} 条相关内容；重点代码：{tickers}；最新焦点：{headline}"
        )
    return lines


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
        if row_is_contentful(row):
            theme_counts[row_theme(row)] += 1
        ticker_counts.update(row_tickers(row))

    content_rows = [row for row in rows_sorted if row_is_contentful(row)]
    top_rows = sorted(
        content_rows,
        key=lambda row: (row_importance(row), parse_iso(row_time(row))),
        reverse=True,
    )[:8]
    latest_rows = rows_sorted[:12]
    title = "Serenity X 日报" if len(rows_sorted) <= 50 else "Serenity 2026 回填报告"
    lines = [
        f"# {title}",
        "",
        f"生成口径：本报告只基于本地 raw 抓取结果，未联网核验；覆盖 `{manifest.get('since')}` 到 `{manifest.get('until')}`，命中 Serenity {len(rows_sorted)} 行。",
        "",
        "## 今日核心总结",
        "",
    ]
    if not rows_sorted:
        lines.append("- 今日未抓到 Serenity 新内容。")
    elif not content_rows:
        lines.append("- 今日有抓取记录，但未识别到明确投资主题、证券代码或长期观点变化。")
    else:
        lines.extend(build_theme_summary(rows_sorted))

    lines.extend(["", "## 重点内容解读", ""])
    if top_rows:
        for idx, row in enumerate(top_rows, start=1):
            lines.extend([f"{idx}. {zh_row_title(row)}", zh_row_takeaway(row), ""])
    else:
        lines.append("- 暂无可解读重点。")

    lines.extend(["", "## 对长期观点的影响", ""])
    if theme_counts:
        for theme, count in theme_counts.most_common(8):
            tickers_for_theme: Counter[str] = Counter()
            for row in rows_sorted:
                if row_theme(row) == theme:
                    tickers_for_theme.update(row_tickers(row))
            tickers = ", ".join(ticker for ticker, _ in tickers_for_theme.most_common(6)) or "无明确代码"
            lines.append(f"- {theme_zh(theme)}：新增/强化 {count} 条；关注 {tickers}。")
    else:
        lines.append("- 今日没有新的 portfolio theme；主要是事件评论、政策观察或市场风险提示。")

    lines.extend(["", "## 风险与待验证事项", ""])
    risk_lines: list[str] = []
    joined_text = "\n".join(row_text(row).lower() for row in rows_sorted)
    if "sive" in joined_text:
        risk_lines.append("SIVE/光子链仍需客户披露、收入 ramp、Nasdaq listing 或供应链订单验证，不能只依赖 mapping。")
    semis_rows = [row for row in rows_sorted if row_theme(row) == "SEMIS" and row_is_contentful(row)]
    if any(has_memory_anchor(row_text(row).lower(), row_tickers(row)) for row in semis_rows):
        risk_lines.append("Memory/HBM 逻辑需要继续跟踪 Micron、SK Hynix、Samsung 的价格、capex 和供需指引。")
    elif semis_rows:
        risk_lines.append("半导体瓶颈线索需要继续区分封测、MLCC、DDR/CXL、OSAT 与 HBM，不应把所有 memory/semis 提及都合并成同一条 HBM thesis。")
    if "power semi" in joined_text or "800v" in joined_text:
        risk_lines.append("功率半导体 read-through 需要验证中国涨价是否持续，以及 800V DC/AI 数据中心电力链是否真正放量。")
    if "fed" in joined_text or "rate" in joined_text:
        risk_lines.append("利率交易对通胀、Fed 口径和长端收益率非常敏感，偏宏观战术而非产业长期主线。")
    if "correction" in joined_text or "high beta" in joined_text:
        risk_lines.append("高 beta 小票在指数回调时可能先跌且跌幅更大，长期 thesis 和仓位波动需要分开看。")
    if not risk_lines:
        risk_lines.append("本报告为社媒观点整理，所有供应链映射和投资含义都需要后续公告、财报或订单验证。")
    lines.extend(f"- {line}" for line in risk_lines)

    lines.extend(["", "## 抓取与归档状态", ""])
    lines.append(
        f"- Serenity 时间范围：`{min(times) if times else ''}` 到 `{max(times) if times else ''}`。"
    )
    lines.append(
        f"- 抓取完整性：feed 去重后 {manifest.get('rowCountDeduped')} 行，分页 {len(manifest.get('pages') or [])} 页，已翻到 `{manifest.get('lastCursor')}`，`stoppedAfterSinceReached={manifest.get('stoppedAfterSinceReached')}`。"
    )
    lines.append(
        "- 分类：" + "，".join(f"{key} {value}" for key, value in kind_counts.most_common())
    )
    if month_counts:
        lines.append(
            "- 月度/窗口分布：" + "，".join(f"{key} {value}" for key, value in sorted(month_counts.items(), reverse=True))
        )
    lines.append("- 高频代码：" + (", ".join(f"{key}({value})" for key, value in ticker_counts.most_common(20)) or "无"))

    lines.extend(["", "## 最新条目索引", ""])
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
