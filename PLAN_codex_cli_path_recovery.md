# Codex CLI Path Recovery

## Context
- 2026-07-10 21:15 Hermes cron successfully fetched and archived Serenity rows, but report synthesis failed with `FileNotFoundError: codex`.
- The long-running Hermes gateway PATH still references `/Applications/Codex.app/Contents/Resources`, while the installed executable moved to `/Applications/ChatGPT.app/Contents/Resources/codex`.
- Keep report generation read-only and preserve the existing stale-report protection.

## Step 1: Add resilient Codex executable resolution ✅
**File**: `scripts/codex_cli.py` - add

- Resolution order: explicit `CODEX_BIN`, `PATH`, current ChatGPT app path, legacy Codex app path.
- Reject missing/non-executable explicit overrides with a clear error.

## Step 2: Route all Codex content scripts through the resolver ✅
**Files**: `scripts/summarize_x_archive_with_codex.py`, `scripts/generate_xhs_note_with_codex.py`, `scripts/parse_x_raw_with_codex.py` - modify

- Replace the literal `codex` executable with the shared resolver result.
- Preserve all existing Codex arguments, sandboxing, marker validation, and output behavior.

## Step 3: Add regression coverage ✅
**File**: `tests/test_codex_cli.py` - add

- Verify explicit override precedence, PATH lookup, app fallback, and actionable failure.
- Verify the current machine resolves the ChatGPT-bundled executable even under a minimal cron-like PATH.

## Step 4: Verify and rerun today's monitor ✅
**Files**: runtime archives and reports - execute only

- Run focused tests and the existing relevant test suite.
- Run the scheduled investment monitor suite again and confirm current-run report, Xiaohongshu note, pending update, Git archive result, and Feishu delivery output.

## 实施顺序
1. ✅ Add resolver and wire call sites.
2. ✅ Add and run regression tests.
3. ✅ Re-run today's complete task and verify outputs.

## 关键文件清单
| 文件 | 操作 | 状态 |
|---|---|---|
| `scripts/codex_cli.py` | 新增 | ✅ |
| Three Codex content scripts | 修改 | ✅ |
| `tests/test_codex_cli.py` | 新增 | ✅ |

## 验证状态
| 验证项 | 状态 |
|---|---|
| Minimal-PATH resolver regression | ✅ |
| Existing unit tests | ✅ (24 tests) |
| Full daily suite rerun | ✅ (Serenity/PTR/compose exit 0) |
| Feishu delivery | ✅ (`last_delivery_error=None`) |

## 遗留项 (Blockers)
| 项目 | 说明 | 优先级 |
|---|---|---|
| None | Root cause and executable location are confirmed. | - |
