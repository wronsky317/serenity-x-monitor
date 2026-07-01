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

## 2. Archive Raw Data, Then Summarize With Codex CLI

For backfills and daily runs, first use the deterministic full archive builder
after fetching. It writes every matched Serenity row into the parsed Markdown
file, so older rows will not be collapsed by an LLM:

```bash
python3 -B /Users/wronsky/Documents/codes/serenity-x-monitor/scripts/build_x_archive_report.py \
  --raw-run /Users/wronsky/Documents/codes/serenity-x-monitor/raw/<timestamp>
```

Outputs are the same paths:

- `/Users/wronsky/Documents/codes/serenity-x-monitor/parsed/<timestamp>.md`

Then use Codex CLI for report-level thesis synthesis:

```bash
python3 /Users/wronsky/Documents/codes/serenity-x-monitor/scripts/summarize_x_archive_with_codex.py \
  --raw-run /Users/wronsky/Documents/codes/serenity-x-monitor/raw/<timestamp> \
  --detail /Users/wronsky/Documents/codes/serenity-x-monitor/parsed/<timestamp>.md
```

Report outputs:

- `/Users/wronsky/Documents/codes/serenity-x-monitor/reports/<timestamp>_report.md`
- `/Users/wronsky/Documents/codes/serenity-x-monitor/reports/latest_summary.md`

Legacy one-step Codex parsing is still available, but daily runs do not use it:

```bash
python3 /Users/wronsky/Documents/codes/serenity-x-monitor/scripts/parse_x_raw_with_codex.py
```

## 3. Full Pipeline

Fetch -> parse -> report:

```bash
python3 /Users/wronsky/Documents/codes/serenity-x-monitor/scripts/run_pipeline.py
```

By default `run_pipeline.py` uses deterministic archive coverage plus Codex CLI
opinion synthesis. Use `--parser archive` only when you explicitly want the
older deterministic rule-based report without Codex CLI.

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
- Generate the report with Codex CLI via `summarize_x_archive_with_codex.py`.
- Write report files under `reports/`.
- Write a reviewable candidate update under
  `long_term_views/pending_updates/<date>.md`.
- Commit only that pending update file if it changed. Use `--no-git-commit`
  for local dry runs.
- Push the current branch to `origin` after a successful pending update commit.
  Use `--no-git-push` when you want to inspect the local commit first.
- Update `state/memory.md`.
- Print `reports/latest_summary.md` to stdout.

This script never sends Feishu directly. The investment suite cron sends the
final digest via Atlas.

Generate only the long-term-view candidate from an existing report:

```bash
python3 -B /Users/wronsky/Documents/codes/serenity-x-monitor/scripts/update_long_term_candidates.py \
  --report /Users/wronsky/Documents/codes/serenity-x-monitor/reports/latest_summary.md
```
