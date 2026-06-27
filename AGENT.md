# Agent Operating Contract

You are running the Serenity X monitor.

## Inputs

- Target account: `Serenity` / `@aleabitoreddit`.
- Primary output: `reports/latest_summary.md`.
- Memory: `state/memory.md`.
- Delivery chat: Feishu `祖国的花朵`, configured locally via Hermes or `FEISHU_CHAT_ID`.

## Required Workflow

1. Read `state/memory.md` first. Use it to identify the last processed post id,
   approximate timestamp, known source gaps, and next-run notes.
2. Search public sources for new posts and important replies since the last run.
   Prefer direct public X pages if accessible; use public mirrors such as
   Instalker/Sotwe only when direct access is blocked.
3. Cross-check non-US and Chinese security mentions. Do not rely on `$TICKER`.
4. Write the final Chinese report to `reports/latest_summary.md`.
5. During Hermes scheduled runs, do not call `scripts/send_feishu_text.py`; write the report locally and let Hermes cron deliver the final response to Feishu via Atlas. For manual fallback only, `bin/send_latest.sh` can send to the same chat id.
6. Update `state/memory.md` with last run time, sources, newest processed item,
   coverage window, delivery status, and next-run notes.

## Report Requirements

- Title: `Serenity（@aleabitoreddit）X 日报`.
- Separate direct posts, replies, reposts, and secondary-source items.
- For each item, capture timestamp, source URL, securities/themes, stance, and
  thesis/catalyst/risk.
- Include a short section for missed-risk checks: Chinese names, A-shares,
  global tickers, aliases, and reposts.
- If no new posts are found, send a short no-new-post report.
- If sources fail, still send a failure report with the exact reason and last
  processed cursor.

## Quality Bar

- Label uncertainty explicitly.
- Do not fabricate source links or timestamps.
- Do not convert social-media views into investment advice.
