# Hermes Daily Archive Wiring

## Context
- 目标：让 Hermes 每日任务中的 Serenity 子监控使用本项目脚本执行抓取、完整归档和报告生成。
- 归档目录固定在 `/Users/wronsky/Documents/codes/serenity-x-monitor`：
  - `raw/<timestamp>/`
  - `parsed/<timestamp>.md`
  - `reports/<timestamp>_report.md`
  - `reports/latest_summary.md`
- Hermes/Atlas 仍通过投资监控套件发送飞书群 `祖国的花朵`。

## Step 1: Pipeline 默认使用完整归档解析 ✅
**File**: `scripts/run_pipeline.py` — 修改

- 新增 `--parser archive|codex`，默认 `archive`。
- `archive` 调用 `scripts/build_x_archive_report.py`，确保大窗口或日常窗口都逐条归档。
- `codex` 保留为可选 LLM 摘要路径。

## Step 2: Serenity Hermes 日常脚本 ✅
**File**: `scripts/hermes_daily_archive.py` — 新增

- 默认抓取最近 30 小时，避免 cron 延迟导致漏数据。
- 调用 `run_pipeline.py --parser archive --since ... --until ...`。
- 更新 `state/memory.md`，记录 raw/parsed/report 路径和计数。
- 输出 `reports/latest_summary.md`，供 suite digest 或人工检查。

## Step 3: Suite Runner ✅
**File**: `investment-monitor-suite/bin/run_daily_suite.py` — 新增

- 先执行 Serenity 日常归档脚本。
- 再执行 Congress PTR 原有 `/bin/run_daily.sh`。
- 最后执行 `compose_feishu_digest.py`，打印最终飞书文本。

## Step 4: Hermes Cron 更新 ✅
**Cron**: `2d5c1253f45f` — 修改

- Hermes CLI 要求 cron script 必须位于 `~/.hermes/scripts/` 且不能通过 symlink 逃逸目录。
- 已创建薄 wrapper：`/Users/wronsky/.hermes/scripts/investment_monitor_suite_daily.py`，内部转调 `/Users/wronsky/Documents/codes/investment-monitor-suite/bin/run_daily_suite.py`。
- 已设置 `--script investment_monitor_suite_daily.py`。
- Prompt 改为：脚本已完成所有工作，最终回复必须原样输出脚本生成的 digest。

## 实施顺序
1. 修改 pipeline：已完成
2. 新增 Serenity daily wrapper：已完成
3. 新增 suite runner：已完成
4. 更新 Hermes cron：已完成

## 关键文件清单

| 文件 | 操作 | 状态 |
|---|---|---|
| `scripts/run_pipeline.py` | 修改 | ✅ |
| `scripts/hermes_daily_archive.py` | 新增 | ✅ |
| `scripts/README.md` | 更新 | ✅ |
| `AGENTS.md` | 更新 | ✅ |
| `investment-monitor-suite/bin/run_daily_suite.py` | 新增 | ✅ |
| `/Users/wronsky/.hermes/scripts/investment_monitor_suite_daily.py` | Hermes wrapper | ✅ |
| Hermes cron `2d5c1253f45f` | 更新 | ✅ |

## 验证状态

| 验证项 | 状态 |
|---|---|
| `run_pipeline.py --help` | ✅ |
| `hermes_daily_archive.py --help` | ✅ |
| `run_daily_suite.py --help` | ✅ |
| `run_daily_suite.py --dry-run` | ✅ |
| Hermes cron 配置确认 | ✅ |

## 遗留项 (Blockers)

| 项目 | 说明 | 优先级 |
|---|---|---|
| PTR 子项目 | 本次只固定 Serenity 的归档方式，PTR 仍按原项目脚本归档 | 中 |
