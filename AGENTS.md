# Agent Operating Contract

You are running the Serenity X monitor.

## Inputs

- Target account: `Serenity` / `@aleabitoreddit`.
- Primary output: `reports/latest_summary.md`.
- Memory: `state/memory.md`.
- Delivery chat: Feishu `祖国的花朵`, configured locally via Hermes or `FEISHU_CHAT_ID`.

## Required Workflow

1. For scheduled Hermes runs, execute:
   `python3 -B /Users/wronsky/Documents/codes/serenity-x-monitor/scripts/hermes_daily_archive.py`
2. That script is the source of truth. It fetches raw Supercycle/X data, writes
   `raw/<timestamp>/`, builds a complete row-by-row archive at
   `parsed/<timestamp>.md`, asks Codex CLI to synthesize
   `reports/<timestamp>_report.md`, asks Codex CLI to write an about-800 字
   Xiaohongshu note with recommended short titles, appends that note to
   `reports/latest_summary.md`, writes
   a reviewable long-term-view candidate to
   `long_term_views/pending_updates/<date>.md`, commits only that pending file
   to git when it changed, pushes the current branch to `origin`, and prepends
   `state/memory.md`.
3. Do not replace the scheduled workflow with ad-hoc web searching unless the
   script fails and the failure reason is included in the report.
4. During Hermes scheduled runs, do not call `scripts/send_feishu_text.py`; write
   the report locally and let Hermes cron deliver the final suite response to
   Feishu via Atlas. For manual fallback only, `bin/send_latest.sh` can send to
   the same chat id.
5. Do not directly edit `long_term_views/serenity_core_asset_map.md` during a
   daily run. Review pending files and merge them manually according to
   `long_term_views/maintenance_rules.md`.

## Report Requirements

- Title: `Serenity（@aleabitoreddit）X 日报`.
- The report-level thesis synthesis should come from Codex CLI via
  `scripts/summarize_x_archive_with_codex.py`, not from keyword templates.
- The Xiaohongshu note should come from Codex CLI via
  `scripts/generate_xhs_note_with_codex.py`, not from keyword templates. It
  must be generated from the current-run report and appended to the Feishu
  message; if generation fails, include the failure note and do not reuse any
  old Xiaohongshu draft.
- Separate direct posts, replies, reposts, and secondary-source items.
- For each item, capture timestamp, source URL, securities/themes, stance, and
  thesis/catalyst/risk.
- Explain raw row status labels when they appear: `thesis` means upstream
  structured portfolio/thesis generation succeeded, not that the conclusion is
  automatically correct; `failed` usually means upstream portfolio/thesis
  generation failed while text may still be captured; `skipped` means no
  directional portfolio was generated. Do not present any status label as the
  report's confidence level or as source collection failure unless the reason
  says so.
- Include a short section for missed-risk checks: Chinese names, A-shares,
  global tickers, aliases, and reposts.
- If no new posts are found, send a short no-new-post report.
- If sources fail, still send a failure report with the exact reason and last
  processed cursor.

## Quality Bar

- Label uncertainty explicitly.
- Do not fabricate source links or timestamps.
- Do not convert social-media views into investment advice.
