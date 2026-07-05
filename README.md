# Serenity X Monitor

Daily monitor for public X/Twitter account `Serenity` / `@aleabitoreddit`.

This project is designed for Codex/agent execution, not as a fully automated
browser scraper. The scheduled agent reads the project prompt, checks public
sources, writes a Chinese daily report with Codex CLI synthesis, sends it to
Feishu, and updates memory.

## Purpose

- Track new public posts and notable replies from `@aleabitoreddit`.
- Extract securities, themes, long/short/hold views, thesis changes, catalysts,
  risk warnings, supply-chain bottleneck claims, and portfolio/return claims.
- Capture global/non-US securities and non-`$TICKER` mentions, especially
  Chinese names and A-share codes.
- Send a daily Chinese summary to Feishu group `祖国的花朵`.

## Project Interface

Other agents should start from:

- [AGENT.md](AGENT.md): operational contract and exact workflow.
- [prompts/daily_monitor.md](prompts/daily_monitor.md): daily monitoring prompt.
- [reports/latest_summary.md](reports/latest_summary.md): latest sent or staged report.
- [state/memory.md](state/memory.md): last-run memory and cursor notes.
- [long_term_views/](long_term_views/): maintained long-term thesis and core
  asset maps derived from Serenity's public-view framework.
- [long_term_views/pending_updates/](long_term_views/pending_updates/):
  auto-generated candidate thesis updates for later manual merge.
- [scripts/INVENTORY.md](scripts/INVENTORY.md): archived script inventory and
  calling conventions.

## Git Privacy

Before committing or pushing, check `codex_cli_privacy.toml` and `.gitignore`.
Raw captures, parsed outputs, generated reports, and local state are private
runtime artifacts and are ignored by git by default:

- `raw/`
- `parsed/`
- `reports/`
- `state/`

Safe-to-commit files are source code, prompts, docs, `.codexignore`,
`.gitignore`, `codex_cli_privacy.toml`, and reviewed summaries under
`long_term_views/`, including `long_term_views/pending_updates/`.

## Daily Output

The daily report should include:

- Coverage window and sources used.
- New direct posts, replies, and clearly labeled reposts/third-party commentary.
- Newly mentioned securities and aliases.
- Stance: bullish, bearish, neutral, risk warning, or unclear.
- Thesis change vs prior memory.
- Source links and timestamps when available.
- Risk caveat: social-media summaries are not investment advice.

## Important Extraction Rule

Do not only look for `$TICKER` patterns. Also capture:

- Chinese company names, A-share/H-share codes, and Chinese media reposts.
- Japanese, European, and other global tickers.
- English aliases and company/product names without ticker symbols.
- Robotics/humanoid supply-chain terms, especially `绿的谐波`,
  `LeaderDrive`, `Leader Harmonious Drive`, `688017`, `SH:688017`,
  `Harmonic Drive`, and `6324.T`.

## Feishu Delivery

Use the local sender helper:

```bash
/Users/wronsky/.codex/feishu-bridge/.venv/bin/python \
  /Users/wronsky/Documents/codes/serenity-x-monitor/scripts/send_feishu_text.py \
  --chat-id "$FEISHU_CHAT_ID" \
  --title "Serenity 日报" \
  --file /Users/wronsky/Documents/codes/serenity-x-monitor/reports/latest_summary.md
```

## Schedule

Hermes investment suite automation:

- Runs daily at 21:15 Asia/Shanghai.
- Working directory: `/Users/wronsky/Documents/codes/serenity-x-monitor`.
- Writes report to `reports/latest_summary.md`.
- Uses deterministic parsing for complete row coverage, then Codex CLI for
  report-level thesis synthesis.
- Uses Codex CLI again to generate an about-800 字 Xiaohongshu note with
  recommended short titles, stores it under `reports/<timestamp>_xhs.md`, and
  appends it to `reports/latest_summary.md` for Feishu delivery.
- Writes, commits, and pushes candidate updates under
  `long_term_views/pending_updates/`.
- Updates memory at `state/memory.md`.

## Known Limits

- X/Twitter public mirror sources can be delayed, incomplete, or missing replies.
- Secondary Chinese finance/news sources may report posts that are unavailable
  in a mirror; include them only as secondary-source evidence.
- Do not infer holdings unless Serenity directly states them.
