# Long-Term View Maintenance Rules

Last updated: 2026-06-27

These rules define how future agents should maintain Serenity's durable thesis
layer under `long_term_views/`.

## Purpose

`long_term_views/` is not a daily report folder and not a raw-data archive. It is
the maintained investment-thesis layer derived from Serenity's public posts.

Use it to track:

- durable themes;
- core companies and watch-only companies;
- possible cycle timing;
- catalysts and verification events;
- thesis upgrades, downgrades, and invalidation risks.

## Source Hierarchy

Use local project artifacts first:

1. `raw/<timestamp>/`: original Supercycle/X JSON capture.
2. `parsed/<timestamp>.md`: complete row-by-row parsed archive.
3. `reports/<timestamp>_report.md` and `reports/latest_summary.md`: report-ready summaries.
4. `state/memory.md`: operational cursor and previous-run notes.

Do not update long-term views from memory alone. Always cite the local source run
or date range used for the update.

## Update Triggers

Generate a candidate update under `long_term_views/pending_updates/<date>.md`
when the daily run completes. Merge it into
`long_term_views/serenity_core_asset_map.md` only after review when one of these
happens:

- Serenity explicitly reinforces or weakens a core theme.
- A company moves from casual mention to direct beneficiary, supplier, customer,
  holding, or negative example.
- A watchlist company becomes part of a repeated thesis.
- Timing changes around 2026 H2, 2027, 2027 H2, or 2028 ramps.
- A mapped supply-chain relationship is validated, contradicted, or replaced.
- A new non-US ticker, Chinese name, Japanese/Korean/Taiwan ticker, or alias
  matters to a durable theme.
- A risk or invalidation condition becomes more concrete.

Do not update the long-term map for one-off jokes, memes, or pure market-color
comments unless they change a durable thesis.

## Required Fields For Theme Entries

Each maintained theme should include:

- Core companies.
- Possible cycle.
- Watchpoints.
- Long-term logic factors.
- Invalidation risks.

If information is uncertain, say so explicitly. Do not convert Serenity's social
media view into a recommendation.

## Privacy And Git Rules

- `long_term_views/` is commit-safe because it contains summarized thesis work,
  not raw tweet dumps.
- `long_term_views/pending_updates/` is also commit-safe, but it is a staging
  area rather than the maintained source of truth.
- Do not paste full raw JSON or long verbatim post text.
- Keep raw captures in `raw/`, parsed archives in `parsed/`, generated reports
  in `reports/`, and runtime state in `state/`.
- Before committing, verify `git diff --cached --name-only` does not include
  private data files from `raw/`, `parsed/`, `reports/`, or `state/`.

## Daily Hermes Behavior

Daily Hermes runs should:

1. Execute `scripts/hermes_daily_archive.py`.
2. Generate raw, parsed, and report artifacts.
3. Generate `long_term_views/pending_updates/<date>.md` from
   `reports/latest_summary.md`.
4. Commit only the pending update file if it changed.
5. Push the current branch to `origin` so pending update status is visible from
   git/GitHub.
6. Send the suite digest through Hermes/Atlas.
7. Never overwrite `long_term_views/serenity_core_asset_map.md` automatically.
