# Serenity 2026-07-24 Missing Posts — Investigation

## Context

- Symptom: today's Serenity run reportedly did not capture posts.
- Goal: determine whether the scheduled job ran, whether upstream collection failed, whether the fetch window/cursor excluded posts, whether account matching failed, or whether there were genuinely no new matching rows.
- Investigation is read-only with respect to production code and runtime state; no fix will be applied without root-cause evidence.

## Step 1: Capture today's runtime evidence ✅
**Files**: `state/memory.md`, `reports/latest_summary.md`, `raw/`, `parsed/`, scheduler logs — inspect

- Identify today's run id, timestamps, exit/status fields, fetch counts, matching counts, and exact error output.
- Compare filesystem artifacts with scheduler execution records.

## Step 2: Trace fetch and matching path ✅
**Files**: `scripts/hermes_daily_archive.py`, `scripts/run_pipeline.py`, `scripts/fetch_x_raw.py` — inspect

- Trace time-window calculation, retry behavior, API endpoints, cursor handling, row deduplication, and Serenity handle matching.
- Check recent Git changes relevant to the observed path.

## Step 3: Test concrete hypotheses ✅
**Files**: current runtime artifacts and targeted read-only commands — verify

- H1 ruled out: scheduler ran at 21:15 CST, exited through the success path, and generated raw, parsed, report, long-image, XHS draft, pending update, memory, and Git commit artifacts.
- H2 confirmed as a stale-success failure: the primary API returned HTTP/JSON but its 25 row IDs were identical to the previous day's first page. At 21:25 CST its newest row was still `2026-07-23T13:10:37Z`; only `generatedAt` advanced. The backup hostname `api.supercycle.fi` did not resolve.
- H3 ruled out as the primary cause: the two Serenity rows visible in today's unfiltered page were at `2026-07-23T04:35:37Z` and `04:49:37Z`, before today's `07:15:21Z` lower bound, and both were already present in the 2026-07-23 archive.

## Step 4: Report confirmed cause ✅
**File**: `PLAN_missing_posts_20260724.md` — update

- Root cause: Supercycle ingestion/feed froze after `2026-07-23T13:10:37Z` while continuing to return successful regenerated responses.
- Detection gap: `fetch_x_raw.py` accepts any valid JSON response and `hermes_daily_archive.py` records `ok` whenever the pipeline produces a current-run report; neither verifies that the upstream page is fresh relative to the requested `until`.
- A code fix is warranted if requested: add feed-freshness/stale-page detection, classify the run as degraded/error rather than `ok`, try a healthy alternate source when available, and include the full generated article in the failure notification as already required by the delivery workflow.

## Step 5: Reject stale successful feed responses ✅
**Files**: `scripts/fetch_x_raw.py`, `tests/test_fetch_x_raw.py` — modify/add

- Measure the first page's newest valid row timestamp against the requested `until`.
- Reject an endpoint when its newest row is more than the configured maximum lag behind `until`; continue to the next configured endpoint.
- Default the maximum lag to 12 hours, preserving valid zero-Serenity days when the overall feed itself is current.
- Add regression coverage for stale rejection, fresh acceptance, missing `until`, and endpoint fallback.
- Implemented `StaleFeedError`, first-page freshness validation, `--max-feed-lag-hours` (default 12, `0` disables), endpoint fallback, and exact failure text in stderr.
- Focused tests: 4/4 passed. Full Serenity tests: 47/47 passed. Syntax compilation and `git diff --check` passed.

## Step 6: Re-run today's scheduled workflow ✅
**Files**: Serenity/suite runtime artifacts and Feishu delivery status — execute/verify

- Run the relevant tests and syntax checks.
- Execute the actual investment-monitor suite entry used by Hermes.
- Verify current-run Serenity status, report, delivery state, and whether upstream recovered.
- First rerun exposed a timeout interaction: the deterministic stale-feed failure entered the generic 20/60/120-second retry ladder, so the suite's 300-second child timeout killed Serenity before `run_pipeline.py` could write its failure placeholder. The main digest was delivered but referenced the prior 21:16 report, with the timeout only appended as a suite error.
- Follow-up fix required: stop generic fetch retries immediately when stderr identifies `Stale Supercycle feed`, allowing the existing failure-report and memory paths to complete before the suite timeout.
- Implemented fail-fast handling for the deterministic stale-feed marker and moved the compact exact error into the first lines of the failure report so the existing Feishu digest includes it.
- Final validation run completed at 21:45 CST in about 30 seconds. Serenity was correctly recorded as `failed exit=1`; PTR continued; the main digest and XHS failure-status message were both delivered to Feishu. The main receipt was `om_x100b6902867a30a0de21df98517d3df`; the XHS status receipt was `om_x100b6902860b80a0c22d195bf6a5e1a`.
- The upstream remained frozen: newest primary-feed row `2026-07-23T13:10:37Z`, 24.6 hours behind the final run's requested `until`. No current-run article or long image was generated, and no historical draft was reused.

## Step 7: Recover a current source and generate the actual article ✅
**Files**: Supercycle alternate endpoints/site data, authenticated X timeline, current-run raw/report/XHS artifacts — investigate/execute

- User correctly rejected the degraded notification as completion because no current Serenity content or normal article was produced.
- Recheck whether the primary feed recovered.
- Inspect Supercycle's public caller page and application routes for a current per-account data source.
- If needed, use the existing signed-in browser session to read the visible Serenity timeline without interacting with the account.
- Only regenerate and deliver the article after current source rows are captured and bound to a new run id.
- Recovered the current public timeline through X public pages rendered by Jina Reader. Direct status pages supplied exact status IDs, UTC timestamps, canonical URLs, and complete visible post text.
- Added automatic Jina recovery after all Supercycle endpoints fail freshness/transport checks. The recovery path requires at least one row to overlap the requested window, archives the profile/status source Markdown, and strips embedded replied-to cards from Serenity's own post text.
- Successful run: `raw/20260724T140659Z`, 4 in-window Serenity posts, current-run report/XHS/long-image artifacts generated.
- Article validation: 904-character body, exact fixed AI disclaimer, 10 topics with final two `#白毛女神 #长期主义`.
- Feishu delivery succeeded: main digest `om_x100b69036f75c0a4c2edab6fe27399d`, XHS article `om_x100b690369879ca0c02c2541dc9a833`, long image `om_x100b690369a69ca0c45ea4313e23044`.
- Full Serenity test suite: 51/51 passed; syntax and `git diff --check` passed.

## 实施顺序

1. ✅ Capture today's runtime evidence.
2. ✅ Trace the fetch/matching path.
3. ✅ Test up to three concrete hypotheses.
4. ✅ Report the confirmed cause without changing production behavior.
5. ✅ Implement stale-feed detection and regression tests.
6. ✅ Re-run today's scheduled workflow and verify delivery.
7. ✅ Recover current Serenity rows and complete normal article generation/delivery.

## 关键文件清单

| 文件 | 操作 | 状态 |
|---|---|---|
| `state/memory.md` | 检查 | ✅ |
| `reports/latest_summary.md` | 检查 | ✅ |
| `raw/`, `parsed/` | 检查 | ✅ |
| `scripts/hermes_daily_archive.py`, `scripts/run_pipeline.py`, `scripts/fetch_x_raw.py` | 链路追踪 | ✅ |
| `scripts/fetch_x_raw.py` | 修复 | ✅ |
| `tests/test_fetch_x_raw.py` | 新增测试 | ✅ |
| 当前 Serenity 数据源 | 恢复/替代 | ✅ |
| `PLAN_missing_posts_20260724.md` | 调查记录 | ✅ |

## 验证状态

| 验证项 | 状态 |
|---|---|
| 今日任务是否执行 | ✅ 21:15 CST 正常执行 |
| 今日抓取是否成功 | ⚠️ HTTP 成功但数据快照陈旧 |
| 抓取窗口与游标是否正确 | ✅ 30 小时窗口及 `before` 游标正确 |
| Serenity 账号匹配是否正确 | ✅ 两条窗口外记录被正确排除且已在昨日归档 |
| 根因有直接证据支持 | ✅ 连续两日第一页 25/25 ID 完全相同，最新全站时间停滞 |
| 陈旧 feed 会触发失败/备用端点 | ✅ 4 项定向测试覆盖 |
| 今日定时任务重跑与飞书投递 | ✅ degraded 状态正确；主摘要与 XHS 失败通知均已投递 |
| 正常文章与长图生成 | ✅ 当前 run 已生成并完成飞书文章/长图投递 |

## 遗留项

| 项目 | 说明 | 优先级 |
|---|---|---|
| Supercycle 主源仍冻结 | 最新记录仍停在 `2026-07-23T13:10:37Z`；当前已由可核验的 X 公共页面恢复路径兜底 | 中 |
| Supercycle 备用域名不稳定 | `api.supercycle.fi` 在调查期间出现 DNS/SSL 连接失败；不会阻止后续 Jina recovery | 低 |
