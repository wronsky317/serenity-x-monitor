# Serenity X 2026 Backfill

## Context
- 目标：抓取并解析 `@aleabitoreddit` / Serenity 自 2026-01-01 以来到 2026-06-27 的 X/Supercycle 原始数据。
- 原始数据落地：`raw/<timestamp>/`，只保留原始 API 页面和去重筛选 JSON。
- 解析归档：`parsed/<timestamp>.md` 保存详细解析；`reports/<timestamp>_report.md` 和 `reports/latest_summary.md` 保存可发送报告。
- 不主动发送飞书，除非显式传 `run_pipeline.py --send` 或用户要求发送。

## Step 1: 修复历史分页 ✅
**File**: `scripts/fetch_x_raw.py` — 修改

- Supercycle 历史翻页实测应使用 `before=<ISO timestamp>`。
- 原脚本使用 `cursor=<ISO timestamp>`，会重复近期页面，导致 2026 全量回填只能抓到少量行。
- `build_url(endpoint, take, cursor)` 保留内部变量名，但查询参数改为 `before`。

## Step 2: 小窗口验证 ✅
**File**: `raw/<timestamp>/manifest.json` — 生成

- 已运行 2026-06-26 08:00-16:00 UTC 小窗口，生成 `raw/20260627T020652Z/`。
- 结果：`rowCountDeduped=18`，`matchedHandleRowCount=3`，并抓到 `2026-06-26T15:56:32.000Z` 的 Serenity 帖。

## Step 3: 全量抓取 ✅
**File**: `raw/<timestamp>/` — 生成

- 运行：
  `python3 scripts/fetch_x_raw.py --since 2026-01-01T00:00:00Z --until 2026-06-27T23:59:59Z --take 50 --max-pages 1200`
- 检查 `manifest.json` 的 `matchedHandleRowCount`、`rowCountDeduped`、`stoppedAfterSinceReached`。
- 第一次全量 run `raw/20260627T020735Z/` 在第 63 页后遇到 `IncompleteRead(0 bytes read)`，脚本未汇总已抓页面；已给 `fetch_json` 增加 3 次瞬时错误重试，并让分页阶段捕获 `IncompleteRead` 后保存已抓结果。
- 第二次全量 run `raw/20260627T021227Z/` 成功：170 页、`rowCountDedupedUnfiltered=4250`、`rowCountDeduped=4240`、`matchedHandleRowCount=567`、`lastCursor=2025-12-08T18:44:57.000Z`、`stoppedAfterSinceReached=true`。
- Serenity 行时间范围：`2026-04-23T04:19:39.000Z` 到 `2026-06-26T17:25:46.000Z`；1 月到 4 月 22 日在该源内未命中 `@aleabitoreddit` 行。

## Step 4: 全量解析 ✅
**File**: `parsed/<timestamp>.md`, `reports/<timestamp>_report.md` — 生成

- 先尝试现有 `parse_x_raw_with_codex.py`。
- 如果账号行太多导致 Codex CLI 输入过大，则按月份/批次拆分解析后再生成汇总报告。
- `parse_x_raw_with_codex.py` 成功生成文件，但详细解析只完整展开了最新日，全年旧行被折叠为聚合统计。
- 新增 `scripts/build_x_archive_report.py` 确定性全量归档脚本，直接从 `aleabitoreddit.rows.json` 逐条展开 567 行，覆盖生成 `parsed/20260627T021227Z.md` 和 `reports/20260627T021227Z_report.md`。

## 实施顺序
1. 修复分页参数：已完成
2. 小窗口验证：已完成
3. 2026 全量抓取：已完成
4. 解析并落盘报告：已完成

## 关键文件清单

| 文件 | 操作 | 状态 |
|---|---|---|
| `scripts/fetch_x_raw.py` | 修改分页参数 | ✅ |
| `scripts/README.md` | 更新参数说明 | ✅ |
| `raw/20260627T020735Z/` | 首次全量尝试，中途网络失败 | ⚠️ |
| `raw/20260627T021227Z/` | 生成 2026 原始抓取 | ✅ |
| `scripts/build_x_archive_report.py` | 大回填全量逐条归档 | ✅ |
| `parsed/20260627T021227Z.md` | 生成详细解析，18,425 行，逐条 567 条 | ✅ |
| `reports/20260627T021227Z_report.md` | 生成报告 | ✅ |

## 验证状态

| 验证项 | 状态 |
|---|---|
| Python 语法检查 | ✅ |
| 小窗口能向历史翻页 | ✅ |
| 全量抓取覆盖到 2026-01-01 | ✅ |
| 解析文件生成 | ✅ |

## 遗留项 (Blockers)

| 项目 | 说明 | 优先级 |
|---|---|---|
| Supercycle 接口分页行为 | 若接口限流或改变参数，需调整抓取方式 | 高 |
| Codex CLI 上下文大小 | 全年内容可能需要分批解析 | 中 |
