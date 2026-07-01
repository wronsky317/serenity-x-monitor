# Script Inventory

Last updated: 2026-06-27

This file archives all maintained scripts in `scripts/` and `bin/`.

## Primary Pipeline Scripts

### `scripts/fetch_x_raw.py`

Purpose: Fetch original Supercycle/X feed pages and write raw JSON snapshots.

Typical use:

```bash
python3 /Users/wronsky/Documents/codes/serenity-x-monitor/scripts/fetch_x_raw.py \
  --since 2026-06-20T00:00:00Z \
  --until 2026-06-27T00:00:00Z \
  --take 50 \
  --max-pages 80
```

Outputs:

- `raw/<timestamp>/page_*.full.json`
- `raw/<timestamp>/all_rows.unfiltered.deduped.json`
- `raw/<timestamp>/all_rows.deduped.json`
- `raw/<timestamp>/aleabitoreddit.rows.json`
- `raw/<timestamp>/manifest.json`

Important behavior:

- Uses Supercycle history pagination with `before=<nextCursor>`.
- `--since` and `--until` are inclusive UTC bounds.
- Raw pages are kept unmodified for auditability.

### `scripts/build_x_archive_report.py`

Purpose: Deterministically convert a raw run into a complete row-by-row Markdown
archive and a compact report.

Typical use:

```bash
python3 -B /Users/wronsky/Documents/codes/serenity-x-monitor/scripts/build_x_archive_report.py \
  --raw-run /Users/wronsky/Documents/codes/serenity-x-monitor/raw/<timestamp>
```

Outputs:

- `parsed/<timestamp>.md`
- `reports/<timestamp>_report.md`
- `reports/latest_summary.md`

Use this for complete row coverage because it does not collapse old rows. Daily
scheduled runs still call it first, but Codex CLI now owns the report-level
thesis synthesis.

### `scripts/summarize_x_archive_with_codex.py`

Purpose: Ask Codex CLI to synthesize a Feishu-ready report from an existing
deterministic parsed archive and raw metadata.

Typical use:

```bash
python3 /Users/wronsky/Documents/codes/serenity-x-monitor/scripts/summarize_x_archive_with_codex.py \
  --raw-run /Users/wronsky/Documents/codes/serenity-x-monitor/raw/<timestamp> \
  --detail /Users/wronsky/Documents/codes/serenity-x-monitor/parsed/<timestamp>.md
```

Outputs:

- `reports/<timestamp>_report.md`
- `reports/latest_summary.md`

Important behavior:

- Runs `codex exec` in read-only sandbox mode.
- Reads raw rows, manifest, and deterministic parsed archive.
- Writes only through this wrapper script after marker validation.
- Its prompt explicitly forbids substring-based causal leaps such as
  `Optimus -> MU`, `Unimicron -> Micron`, or Samsung MLCC news -> HBM thesis.

### `scripts/run_pipeline.py`

Purpose: Orchestrate fetch -> archive/parse -> report -> optional Feishu send.

Typical use:

```bash
python3 /Users/wronsky/Documents/codes/serenity-x-monitor/scripts/run_pipeline.py \
  --since 2026-06-20T00:00:00Z \
  --until 2026-06-27T00:00:00Z \
  --take 50 \
  --max-pages 80
```

Important behavior:

- Defaults to `--parser codex`, which calls `build_x_archive_report.py` for
  full archive coverage and then `summarize_x_archive_with_codex.py` for Codex
  CLI thesis synthesis.
- `--parser archive` skips Codex CLI and uses the deterministic rule-based
  report.
- Does not send Feishu unless `--send` is passed.
- `--send` requires `--chat-id` or `FEISHU_CHAT_ID`.

### `scripts/hermes_daily_archive.py`

Purpose: Daily scheduled entrypoint for Hermes.

Typical use:

```bash
python3 -B /Users/wronsky/Documents/codes/serenity-x-monitor/scripts/hermes_daily_archive.py
```

Important behavior:

- Looks back 30 hours by default.
- Calls `run_pipeline.py --parser codex`.
- Generates `long_term_views/pending_updates/<date>.md`.
- Commits only that pending update file if it changed. Pass
  `--no-git-commit` to disable this during manual dry runs.
- Pushes the current branch to `origin` after a successful pending update
  commit. Pass `--no-git-push` to keep the commit local.
- Updates `state/memory.md`.
- Prints `reports/latest_summary.md`.
- Does not send Feishu directly.

### `scripts/update_long_term_candidates.py`

Purpose: Convert the latest report into a reviewable long-term-view candidate
without touching the maintained asset map.

Typical use:

```bash
python3 -B /Users/wronsky/Documents/codes/serenity-x-monitor/scripts/update_long_term_candidates.py \
  --report /Users/wronsky/Documents/codes/serenity-x-monitor/reports/latest_summary.md
```

Output:

- `long_term_views/pending_updates/<date>.md`

The file is a commit-safe summary for later manual merge into
`long_term_views/serenity_core_asset_map.md`.

## Optional / Specialist Scripts

### `scripts/parse_x_raw_with_codex.py`

Purpose: Use Codex CLI to produce an LLM-written detailed analysis and
report-ready summary from a raw run.

Legacy/specialist path. Daily runs prefer deterministic archive plus
`summarize_x_archive_with_codex.py` so row coverage and thesis synthesis are
separated.

### `scripts/send_feishu_text.py`

Purpose: Manual Feishu text sender using the local Codex Feishu bridge.

Typical use:

```bash
FEISHU_CHAT_ID=oc_xxx \
/Users/wronsky/.codex/feishu-bridge/.venv/bin/python \
  /Users/wronsky/Documents/codes/serenity-x-monitor/scripts/send_feishu_text.py \
  --chat-id "$FEISHU_CHAT_ID" \
  --title "Serenity 日报" \
  --file /Users/wronsky/Documents/codes/serenity-x-monitor/reports/latest_summary.md
```

Do not use during scheduled Hermes runs.

## Bin Helpers

### `bin/send_latest.sh`

Purpose: Manual convenience wrapper around `scripts/send_feishu_text.py`.

Requires:

```bash
export FEISHU_CHAT_ID=oc_xxx
```

Do not use during scheduled Hermes runs.

## External Suite Script

The investment suite cron uses a wrapper under `~/.hermes/scripts/` that calls:

```text
/Users/wronsky/Documents/codes/investment-monitor-suite/bin/run_daily_suite.py
```

That suite script calls `scripts/hermes_daily_archive.py` for Serenity, then runs
the Congress PTR monitor, then composes the Feishu digest.
