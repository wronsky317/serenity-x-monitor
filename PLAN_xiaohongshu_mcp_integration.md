# Xiaohongshu MCP — 自动发布接入分析

## Context
- 目标：接入 `xpzouying/xiaohongshu-mcp`，让 Hermes 每日直接发布 Serenity 小红书图文，同时保留 Serenity + PTR 综合飞书日报。
- 当前发布数据：封面 `pic.png`，标题格式 `【财经】mmdd <推荐标题>`，正文来自最新 `reports/*_xhs.md`，话题最后固定 `#白毛女神 #长期主义`。
- 已完成可行性分析、设计、代码、服务安装和扫码登录；等待首次真实发布确认。

## Step 4: 设计规格 ✅
**File**: `docs/superpowers/specs/2026-07-12-xiaohongshu-auto-publish-design.md` — 新增

- 已记录架构、发布规则、防重复、失败语义、安装登录、安全边界、测试和回滚设计。

## Step 5: 发布适配器与测试 ✅
**File**: `scripts/publish_xhs.py`, `tests/test_publish_xhs.py` — 新增

- 已新增严格 current-run 校验、标题/正文/话题规则、dry-run、登录检查和发布历史防重复。
- Serenity 测试 32/32 通过，真实最新稿件 dry-run 符合预期。

## Step 6: Hermes 套件集成 ✅
**File**: `investment-monitor-suite/bin/*.py` — 修改

- 套件已调用直接发布器；飞书发送使用 `--main-only`，综合日报保留。
- 套件测试 13/13 通过，dry-run 显示单条飞书交付链路。

## Step 7: 本地服务安装与首次登录 ✅
**File**: 本地运行目录 — 安装/配置

- 已安装上游 `v2026.06.12.1403-5c43e3d` Intel 二进制并记录 SHA-256。
- 已加载仅绑定 `127.0.0.1:18060` 的 LaunchAgent；健康检查和登录状态均成功。

## Step 8: 首次发布验收
**File**: 当前运行稿件 — dry-run/发布

- 用户已确认真实发布；Go MCP 路径在批量上传完整长图时持续卡在预览完成等待或页面元素重渲染，尚未点击发布按钮。
- 用户手工在小红书页面上传同一长图可成功，证明图片本身有效，阻塞点位于 MCP/无头浏览器自动化层。

## Step 9: 完整日报长图 ✅
**File**: `scripts/render_report_long_image.py`, `tests/test_render_report_long_image.py` — 新增

- 当前完整日报确定性渲染为第二张 1242×8809 PNG，未截断；第一张仍为 `pic.png`。
- 发布器和套件已支持两张图片，长图路径与 current run 绑定。

## Step 10: 指定本地源码安装 ✅
**File**: `/Users/wronsky/Documents/skill_codebases/xiaohongshu-mcp`, `~/Library/LaunchAgents/com.wronsky.xiaohongshu-mcp.plist` — 构建/配置

- 已从用户指定的干净源码树 `main@5c5197d` 使用 Go 1.26.5 构建 Intel macOS 主程序与登录程序。
- 安装目录为 `~/.local/share/xiaohongshu-mcp/local-source-5c5197d/`；LaunchAgent 已切换到该主程序，Cookie 路径保持不变。
- `go test ./pkg/...` 与 `go test ./xiaohongshu -run '^$'` 通过；服务健康、登录状态均验证成功。
- 冷启动第 1 次探测复现 `curl (7)`，第 2 次约 1 秒后健康；调用方必须保留启动重试，不能以单次探测判死。
- 仓库自带 `post-to-xhs` CDP 脚本目前是 Windows 专用路径/profile 实现，未安装为 macOS 发布引擎。

## Step 11: 新版编辑器兼容修复 ⚠️
**File**: `/Users/wronsky/Documents/skill_codebases/xiaohongshu-mcp/xiaohongshu/publish.go` — 修复

- 真实发布在两张图片上传完成后于 `getContentElement().Race().MustDo()` 抛出 `no placeholder element found`，未进入点击发布按钮阶段。
- 根因是旧实现只识别 `div.ql-editor` 或旧版 `data-placeholder`；当前页面正文编辑器为 `div.tiptap.ProseMirror`。
- 修复增加 TipTap/ProseMirror 选择器并保留旧版回退；正文输入后重新查询标题节点，避免前端重渲染导致 stale element。
- 第一次修复验证后 panic 消失，但逐张 `SetFiles` 上传后页面未生成正文编辑器；根据此前批量上传能匹配 TipTap 的运行证据，改为一次性多文件上传并等待两张预览，最长 180 秒。
- 批量上传后正文编辑器成功匹配并完成输入；标题节点在等待 1 秒期间被前端再次替换，故将标题重新查询移动到等待之后，避免 stale element。
- 等待后重新查询标题节点仍一直阻塞到 REST 请求 120 秒上下文取消；日志确认失败发生在标签输入与发布按钮之前。连续三个修复假设已验证，按调查停止条件暂停继续试错。

## Step 12: xhs_ai_publisher 两图发布验收 ✅
**File**: `/Users/wronsky/Documents/skill_codebases/xhs_ai_publisher/src/core/write_xiaohongshu.py` — 安装/兼容修复/真实发布

- 已安装项目依赖与 Playwright Chromium，并在独立持久化 Chrome profile 完成登录。
- 增加新版发布页直达回退、新版 `xhs-publish-btn` 识别和 Shadow DOM 宿主坐标点击兼容。
- 两张图片、标题、正文和 10 个话题均成功填入；页面返回明确状态提示“发布成功”。
- 已将两图载荷指纹写入 `state/xhs_publish_history.json`，避免旧发布器或后续任务重复发送同一篇。

## Step 13: Hermes 无人值守引擎切换 ✅
**File**: `scripts/publish_xhs_ai.py`, `investment-monitor-suite/bin/run_daily_suite.py` — 新增/修改

- Hermes 已从旧 Go MCP REST 发布器切换到 `xhs_ai_publisher` Playwright 适配器。
- 每日命令显式使用 `--auto-publish`，无需逐次人工确认；固定使用封面 `pic.png` 与当前运行完整日报长图。
- 适配器复用原有 current-run 校验、标题/正文/话题规则及 SHA-256 防重复历史。
- 固化可见持久化 Chrome、DOM 兼容开关和 Playwright 浏览器路径；发布失败仍不阻断综合飞书日报。

## Step 14: Hermes 长图解释器修复 ✅
**File**: `investment-monitor-suite/bin/run_daily_suite.py`, `tests/test_run_daily_suite.py` — 修改

- 13:41 定时运行继承 Hermes Python 执行长图渲染，因缺少 Pillow 报 `ModuleNotFoundError: PIL`，导致发布器未启动。
- 长图渲染与自动发布现统一固定使用 `xhs_ai_publisher/venv/bin/python`；测试锁定解释器绝对路径，避免再次回归到 `sys.executable`。
- 同次验证发现当日推荐标题拼接后为 23 字。按用户要求不做截断：Codex 生成提示现限制 5 个标题各不超过 11 字（为 `【财经】MMDD ` 预留 9 字），正文绝对不超过 1000 字；生成结果会再次校验标题数量、标题长度和正文长度，发布阶段继续严格拒绝超限稿件。

## Step 15: 最终发布闭环加固 ✅
**File**: `/Users/wronsky/Documents/skill_codebases/xhs_ai_publisher/src/core/write_xiaohongshu.py` — 修改

- 已确认 13:58 失败发生在最终提交：新版 `xhs-publish-btn` 宿主坐标收到了自动化点击，但组件状态、URL 和页面均未变化，不能据此断言已提交，也没有证据证明是验证码接口导致。
- 最终点击优先穿透开放 Shadow DOM 定位真实 `button`，其次执行宿主 `shadowRoot` 内部按钮的原生 click；每次点击后观察 `submit-loading`、弹窗、宿主连接状态和 URL。
- 页面 8 秒无变化时在同一编辑会话内仅做一次坐标兜底，不重新上传或重新填表。
- 成功提示和跳转均未捕获时，在独立标签页进入笔记管理并按完整标题核验；只有核验存在才返回成功，找不到仍失败且不写发布历史。

## Step 1: 上游仓库能力核验 ✅
**File**: `xpzouying/xiaohongshu-mcp` — 只读检查

- 上游提交 `5c5197d`（2026-06-29）支持 MCP `publish_content` 与 REST `POST /api/v1/publish`。
- 参数：`title`, `content`, `images`, `tags`, `schedule_at`, `is_original`, `visibility`, `products`；本地图片绝对路径受支持。
- Cookie 存储在本地文件；支持二维码登录、macOS Intel 预编译二进制、Docker 和源码运行。
- 限制：标题最多 20 个中文字或英文单词、正文不超过 1000 字、标签最多 10 个；同一账号不应同时登录多个网页端。
- 仓库根目录未发现 LICENSE/COPYING 文件，不建议直接复制源码到本项目。

## Step 2: 本项目适配点分析 ✅
**File**: `scripts/`, `reports/`, `pic.png` — 读取

- 标题 `【财经】0712 CPO主线的关键验证点` 恰好 20 个 Unicode code point；建议发布前继续做显式长度校验。
- 最新正文 858 字符，低于文档所述 1000 字限制。
- 标签应取原标签前 8 个，再固定追加 `白毛女神`, `长期主义`，总数 10，保证两个固定标签位于最后。
- `pic.png` 为 1024×1536 PNG、约 2.29 MB，可作为单张本地封面图。
- 推荐从 Python wrapper 调本地 REST API，而不是让日报主流程直接依赖 MCP 客户端协议。

## Step 3: 输出接入建议 ✅
**File**: `PLAN_xiaohongshu_mcp_integration.md` — 更新

- 推荐独立运行 `xiaohongshu-mcp`，新增 `scripts/publish_xhs.py` 负责解析、校验、预览和经明确确认后的 REST 发布。
- 服务当前未运行（`127.0.0.1:18060/health` 不可达）；本机为 Intel macOS，Docker 已安装，Go 未在 PATH。
- 默认服务监听 `:18060` 且 API 无 OAuth，必须限制在本机/防火墙范围，不应暴露到局域网或公网。

## 实施顺序
1. 上游仓库能力核验 — ✅
2. 本项目适配点分析 — ✅
3. 输出接入建议 — ✅
4. 设计规格 — ✅
5. 发布适配器与测试 — ✅
6. Hermes 套件集成 — ✅
7. 本地服务安装与首次登录 — ✅
8. 首次发布验收 — 待执行
9. 完整日报长图 — ✅
10. 指定本地源码安装 — ✅
11. 新版编辑器兼容修复 — ⚠️（仍阻塞于正文后的标题节点重查）
12. xhs_ai_publisher 两图发布验收 — ✅
13. Hermes 无人值守引擎切换 — ✅
14. Hermes 长图解释器修复 — ✅
15. 最终发布闭环加固 — ✅

## 关键文件清单
| 文件 | 操作 | 状态 |
|---|---|---|
| 上游 `README.md` / 源码 / 配置 | 分析 | ✅ |
| `scripts/run_pipeline.py` | 适配分析 | ✅ |
| `reports/*_xhs.md`, `pic.png` | 输入映射 | ✅ |
| `docs/superpowers/specs/2026-07-12-xiaohongshu-auto-publish-design.md` | 新增 | ✅ |
| `scripts/publish_xhs.py`, `tests/test_publish_xhs.py` | 新增 | ✅ |
| `investment-monitor-suite/bin/*.py` | 修改 | ✅ |
| `scripts/render_report_long_image.py` | 新增 | ✅ |
| 用户指定 `xiaohongshu-mcp` 源码 | 构建并安装 | ✅ |
| `com.wronsky.xiaohongshu-mcp.plist` | 切换本地源码构建 | ✅ |

## 验证状态
| 验证项 | 状态 |
|---|---|
| 是否支持图文发布 | ✅ MCP + REST |
| 登录态持久化方式 | ✅ 本地 cookies.json |
| 标题/正文/图片参数 | ✅ 满足当前内容映射 |
| macOS 本地运行可行性 | ✅ Intel 二进制或 Docker |
| 指定源码构建、健康与登录 | ✅ `5c5197d` / healthy / logged in |
| Shadow DOM 真实发布按钮点击 | ✅ 本地开放 Shadow DOM 组件复现通过 |
| Serenity 回归测试 | ✅ 37 passed |

## 遗留项 (Blockers)
| 项目 | 说明 | 优先级 |
|---|---|---|
| 首次真实发布 | 已确认并尝试；MCP 无头浏览器多图上传/页面状态不稳定，未产生公开笔记 | 高 |
| 自动化引擎 | 指定源码已安装，但其 Go 实现仍是逐张上传旧逻辑；仓库 CDP 技能为 Windows 专用，真实多图发布稳定性尚未解决 | 高 |
| 登录稳定性 | 避免同一账号在另一个网页端登录导致 Cookie 失效 | 高 |
| 本地 API 安全 | 已绑定 `127.0.0.1:18060`；继续禁止代理或公网暴露 | 高 |
| 上游许可证 | 未发现 LICENSE，避免复制/修改其源码；优先以独立进程方式调用 | 中 |
| 真实平台最终验收 | 修复未额外发布真实笔记，避免与 13:58 状态不明的稿件重复；由下一次 Hermes 日报执行验证 | 中 |
