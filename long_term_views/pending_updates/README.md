# Pending Long-Term Updates

This directory stores auto-generated, reviewable candidate updates for
`long_term_views/serenity_core_asset_map.md`.

Daily Hermes runs create one file per Asia/Shanghai date:

```text
long_term_views/pending_updates/YYYY-MM-DD.md
```

These files are commit-safe summaries. They should not contain raw JSON, full
post dumps, Feishu chat ids, or private runtime state. Review and merge the
durable parts into the main asset map manually.

After a pending file has been manually merged into
`long_term_views/serenity_core_asset_map.md`, move it to
`long_term_views/merged/` with `git mv` so the pending directory only contains
unreviewed candidates.
