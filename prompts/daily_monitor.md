Monitor the public X/Twitter account Serenity (`@aleabitoreddit`) by running the local scheduled workflow script first:

```bash
python3 -B /Users/wronsky/Documents/codes/serenity-x-monitor/scripts/hermes_daily_archive.py
```

The script fetches raw Supercycle/X data, archives it under `raw/<timestamp>/`,
generates complete row-by-row parsed output under `parsed/<timestamp>.md`, writes
the daily report to `reports/<timestamp>_report.md` and
`reports/latest_summary.md`, calls Codex CLI again to generate an about-800 字
Xiaohongshu note with recommended short titles, appends that note to
`reports/latest_summary.md`, and updates `state/memory.md`.

Only use ad-hoc public-source searching if that script fails, and label the
fallback clearly with the exact failure reason.

Summarize new public posts in Chinese, focusing on: newly mentioned securities, stated long/short/hold views, thesis changes, supply-chain bottleneck claims, catalysts, risk warnings, portfolio/return claims, and notable replies that clarify his stance. Include source links and timestamps when available. Distinguish direct posts from third-party commentary or reposts. Add a brief investment-risk caveat and do not provide personalized financial advice.

Important extraction rule: do not only look for `$TICKER` patterns. Also capture non-US/global securities and names without `$`, including Chinese company names, A-share/H-share codes, Japanese tickers, German/French tickers, ETFs, and English aliases. Specifically watch for forms such as `绿的谐波`, `LeaderDrive`, `Leader Harmonious Drive`, `688017`, `SH:688017`, `Harmonic Drive`, `6324.T`, and similar robotics/humanoid supply-chain names. If third-party Chinese finance/news sites report a Serenity post that the X mirror missed, include it as a secondary-source item and label it clearly as secondary-source evidence.

Delivery requirement: every scheduled Hermes run must create a concise Chinese daily report at `reports/latest_summary.md`, with the current-run Xiaohongshu note attached in the same file; Hermes cron delivers the final suite response to Feishu group `祖国的花朵` via its local delivery config. Manual sends should use `FEISHU_CHAT_ID`. If no new posts are found, send a short `今日无新增/抓取结果` report rather than staying silent. If sources fail, send the failure reason and the last processed post/time. If Xiaohongshu generation fails, include the failure note and do not reuse old note content.

Manual fallback only: `bin/send_latest.sh` sends `reports/latest_summary.md` to the same Feishu chat if a human explicitly requests a resend. Do not use the fallback during Hermes scheduled runs.

After sending, update `/Users/wronsky/Documents/codes/serenity-x-monitor/state/memory.md` with: last run date/time Asia/Shanghai, source(s) used, newest processed post id/time, coverage window, delivery status, and notes for next run.
