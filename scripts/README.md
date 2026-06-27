# Serenity X Monitor Scripts

This directory contains scripts that can run without an agent conversation.

## 1. Fetch Raw X Data

```bash
python3 /Users/wronsky/Documents/codes/serenity-x-monitor/scripts/fetch_x_raw.py
```

Writes raw snapshots to:

```text
/Users/wronsky/Documents/codes/serenity-x-monitor/raw/<timestamp>/
```

Files:

- `page_*.full.json`: unmodified Supercycle feed pages.
- `all_rows.deduped.json`: deduped raw rows from fetched pages.
- `aleabitoreddit.rows.json`: raw rows whose `caller.handle` is `aleabitoreddit`.
- `manifest.json`: fetch metadata and counts.

Batch fetch a date range:

```bash
python3 /Users/wronsky/Documents/codes/serenity-x-monitor/scripts/fetch_x_raw.py \
  --since 2026-06-20T00:00:00Z \
  --until 2026-06-27T00:00:00Z \
  --take 50 \
  --max-pages 80
```

`--since` and `--until` are inclusive UTC bounds. The script keeps
`page_*.full.json` as the unmodified raw API pages, then writes filtered
`all_rows.deduped.json` and `aleabitoreddit.rows.json` for the requested window.
It also writes `all_rows.unfiltered.deduped.json` for audit/debug.

Parameter meaning:

- `--take 50`: request up to 50 feed rows from Supercycle per API page. Larger
  values reduce page requests but each response is bigger.
- `--max-pages 80`: fetch at most 80 pages while walking backward with
  Supercycle's `before=<nextCursor>` pagination. This is a safety cap, not a target. The script
  stops earlier if it reaches rows older than `--since`, if there is no next
  cursor, or if the API repeats a cursor.
- Scan upper bound: `--take * --max-pages`. For example, `50 * 80` means the
  script can scan up to about 4,000 raw feed rows before filtering to Serenity
  and the requested time window.
- For a short window, use smaller values such as `--take 50 --max-pages 5`.
  For a wider backfill, increase `--max-pages` first.

## 2. Parse Raw Data With Codex CLI

```bash
python3 /Users/wronsky/Documents/codes/serenity-x-monitor/scripts/parse_x_raw_with_codex.py
```

By default this uses the latest `raw/<timestamp>/` directory.

Outputs:

- Detailed parsed archive:
  `/Users/wronsky/Documents/codes/serenity-x-monitor/parsed/<timestamp>.md`
- Report-ready summary:
  `/Users/wronsky/Documents/codes/serenity-x-monitor/reports/<timestamp>_report.md`
- Latest report copy:
  `/Users/wronsky/Documents/codes/serenity-x-monitor/reports/latest_summary.md`

For large backfills, use the deterministic full archive builder after fetching.
It writes every matched Serenity row into the parsed Markdown file, so older rows
will not be collapsed by the LLM:

```bash
python3 -B /Users/wronsky/Documents/codes/serenity-x-monitor/scripts/build_x_archive_report.py \
  --raw-run /Users/wronsky/Documents/codes/serenity-x-monitor/raw/<timestamp>
```

Outputs are the same paths:

- `/Users/wronsky/Documents/codes/serenity-x-monitor/parsed/<timestamp>.md`
- `/Users/wronsky/Documents/codes/serenity-x-monitor/reports/<timestamp>_report.md`
- `/Users/wronsky/Documents/codes/serenity-x-monitor/reports/latest_summary.md`

## 3. Full Pipeline

Fetch -> parse -> report:

```bash
python3 /Users/wronsky/Documents/codes/serenity-x-monitor/scripts/run_pipeline.py
```

By default `run_pipeline.py` now uses the deterministic archive parser:
`scripts/build_x_archive_report.py`. Use `--parser codex` only when you
explicitly want the Codex CLI LLM parser.

Fetch a range -> parse -> report:

```bash
python3 /Users/wronsky/Documents/codes/serenity-x-monitor/scripts/run_pipeline.py \
  --since 2026-06-20T00:00:00Z \
  --until 2026-06-27T00:00:00Z \
  --take 50 \
  --max-pages 80
```

Fetch -> parse -> report -> Feishu:

```bash
python3 /Users/wronsky/Documents/codes/serenity-x-monitor/scripts/run_pipeline.py --send
```

The pipeline does not send Feishu messages unless `--send` is provided.

## 4. Hermes Daily Entrypoint

Hermes scheduled jobs should call:

```bash
python3 -B /Users/wronsky/Documents/codes/serenity-x-monitor/scripts/hermes_daily_archive.py
```

Default behavior:

- Look back 30 hours in UTC to avoid missing data if cron runs late.
- Fetch raw pages into `raw/<timestamp>/`.
- Build complete parsed archive with `build_x_archive_report.py`.
- Write report files under `reports/`.
- Update `state/memory.md`.
- Print `reports/latest_summary.md` to stdout.

This script never sends Feishu directly. The investment suite cron sends the
final digest via Atlas.
