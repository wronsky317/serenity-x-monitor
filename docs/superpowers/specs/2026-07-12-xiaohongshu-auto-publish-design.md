# Serenity 小红书自动发布设计

## 目标

将现有 21:15 Asia/Shanghai 的 Hermes 投资监控任务调整为：

1. Serenity 与 Congress PTR 监控照常执行。
2. Serenity + PTR 综合日报继续通过 Atlas 发送到飞书群。
3. 原本发送到飞书的第二条 Serenity 小红书稿，改为直接发布到小红书。
4. 小红书发布失败不能阻止综合飞书日报发送，但必须令总任务标记失败并留下可诊断记录。

## 不在范围内

- 不改变 Serenity 的抓取、确定性归档、Codex 日报综合和小红书正文生成逻辑。
- 不改变 Congress PTR 监控逻辑。
- 不复制或修改 `xpzouying/xiaohongshu-mcp` 源码。
- 不自动处理验证码、实名认证或账号风控提示。
- 不增加自动评论、点赞、收藏或其他账号运营动作。

## 架构

`xiaohongshu-mcp` 作为本机独立服务运行，发布适配器通过 REST API 调用它：

```text
Hermes 21:15
  -> run_daily_suite.py
     -> hermes_daily_archive.py
        -> run_pipeline.py
           -> reports/<run_id>_xhs.md
     -> publish_xhs.py
        -> GET 127.0.0.1:18060/api/v1/login/status
        -> POST 127.0.0.1:18060/api/v1/publish
     -> compose_feishu_digest.py
     -> send_feishu_deliveries.py（仅综合日报）
```

本机服务不得暴露到公网或不可信局域网。接入层默认使用 `http://127.0.0.1:18060`。

## 发布输入规则

### 来源文件

- 正文来源：当前 Serenity 运行产生的 `reports/<run_id>_xhs.md`。
- 第一张封面：`/Users/wronsky/Documents/codes/serenity-x-monitor/pic.png`。
- 第二张图片：由当前运行 `reports/<run_id>_report.md` 确定性渲染的完整日报长图。
- 禁止回退到旧的 `latest_summary` 或旧小红书稿；必须验证稿件路径属于当前 `raw_run`。

### 标题

- 格式：`【财经】MMDD <推荐标题>`。
- `MMDD` 使用实际发布时的 Asia/Shanghai 日期。
- 推荐标题优先读取稿件“短标题候选”中显式标记“推荐”的条目；没有标记时使用第一条。
- 发布前检查最终标题是否满足小红书页面限制；超过限制则失败，不静默截断。

### 正文

- 只读取稿件 `## 正文` 区段。
- 正文不包含 `## 话题` 区段及 Markdown 标题。
- 发布前校验正文非空且不超过 1000 个字符；超限时失败，不静默截断。

### 话题

- 从 `## 话题` 区段按原顺序解析并去掉 `#`。
- 移除原话题中的 `白毛女神` 和 `长期主义` 后，最多保留前 8 个。
- 最后固定追加 `白毛女神`、`长期主义`。
- 最终最多 10 个，且两个固定话题必须处于最后两位。

### 图片与可见范围

- 第一张发布 `pic.png`，作为首图/封面。
- 第二张发布 `reports/<run_id>_long.png`，包含当次完整 Serenity 日报；不得截断或回退旧报告。
- 长图使用中文字体、浅色背景和分级标题排版，渲染路径必须与当前 run id 匹配。
- 两张图片都必须存在且为非空文件，并共同进入防重复指纹。
- 可见范围默认 `公开可见`。
- 不声明原创，不绑定商品，不设置定时发布时间；Hermes 运行时立即发布。

## 发布适配器

新增 `scripts/publish_xhs.py`，提供：

- `--xhs-file`：必填，当前运行稿件。
- `--raw-run`：必填，用于校验稿件 run id。
- `--image`：默认项目根目录 `pic.png`。
- `--base-url`：默认 `http://127.0.0.1:18060`。
- `--dry-run`：只解析、校验并打印 JSON 预览，不调用发布接口。
- `--confirm-publish`：允许真正调用发布接口；没有该参数时不得发布。
- `--state-file`：默认 `state/xhs_publish_history.json`。

发布流程：

1. 校验输入路径、run id、标题、正文、话题和全部图片。
2. 计算由 run id、标题、正文、话题及图片路径组成的 SHA-256 内容指纹。
3. 若状态文件存在相同指纹且状态为成功，拒绝重复发布并返回成功的 skipped 状态。
4. dry-run 输出预览后退出。
5. 真正发布前检查 `/health` 和 `/api/v1/login/status`。
6. 仅在已登录时调用 `/api/v1/publish`。
7. 成功后原子更新状态文件；失败时输出阶段、HTTP 状态和安全截断后的错误信息。

状态文件位于已被 Git 忽略的 `state/`，不得记录 Cookie、二维码或其他认证信息。

## Hermes 与套件集成

### Serenity 子任务

`hermes_daily_archive.py` 在成功输出中保留当前 `xhs=<path>`，并保证该路径来自当前运行。它本身不调用发布接口，避免单独执行 Serenity 归档时产生意外外部发布。

### 投资套件

`run_daily_suite.py` 负责正式发布：

1. 运行 Serenity 与 PTR 子任务。
2. 从 Serenity stdout 解析当前 `raw`、`report` 和 `xhs` 路径。
3. 先调用 `render_report_long_image.py` 生成当前完整日报长图。
4. Serenity 成功且小红书稿和日报长图均有效时，调用：

   ```text
   python3 -B scripts/publish_xhs.py \
     --xhs-file <current_xhs> \
     --raw-run <current_raw> \
     --image pic.png \
     --image <current_long_image> \
     --confirm-publish
   ```

5. 无论小红书发布是否成功，都继续生成并发送综合飞书日报。
6. `send_feishu_deliveries.py` 调整为只发送综合日报，不再发送小红书稿。
7. suite memory 增加长图渲染、`XHS publish exit` 和发布结果摘要。
8. 长图渲染或小红书发布失败时 suite 最终退出码为非零，但飞书综合日报仍应已经发送，并在 stderr/memory 中记录失败原因。

## 服务安装与登录

- 本机为 Intel macOS，优先使用上游 `darwin-amd64` 预编译二进制。
- 二进制和 Cookie 数据放在项目外的本地运行目录，避免提交到 Git。
- 服务绑定本机地址；若上游二进制只接受 `:18060`，使用 macOS 防火墙并禁止路由器/公网端口映射。
- 首次登录必须由用户通过小红书 App 扫码完成。
- 同一个账号不同时登录另一个网页端，避免 Cookie 被踢下线；手机 App 可继续使用。
- 服务需在 Hermes 21:15 任务前常驻可用；启动方式记录在运维文档中。

## 错误处理

- 服务不可达：不发布，记录 `service-unavailable`。
- 未登录：不发布，记录 `not-logged-in`，不自动删除 Cookie。
- 稿件解析或限制校验失败：不发布，不回退旧稿。
- HTTP 发布失败或超时：不自动重试发布，避免响应丢失后产生重复笔记。
- 响应明确成功但状态写入失败：标记 `published-state-write-failed` 并要求人工核查，后续不得盲目重试。
- 当日没有新的有效 Serenity 内容：仍使用现有生成逻辑的当次稿件；若生成器明确失败，则不发布失败占位稿。

## 测试与验收

### 单元测试

- 推荐标题解析及日期前缀。
- 正文区段提取和 1000 字限制。
- 话题去重、前 8 个截取及固定末两位。
- run id 防串档。
- 内容指纹和重复发布跳过。
- dry-run 不产生 HTTP POST。
- 登录失败、服务失败和发布失败错误分类。

### 集成测试

- `run_daily_suite.py --dry-run` 显示新的发布命令与单条飞书交付链路。
- 使用假的本地 HTTP 服务验证请求 JSON，不连接真实小红书。
- 运行两个项目的现有测试套件，确保 Serenity/PTR/飞书综合日报未回归。

### 首次真实验收

1. 启动服务并由用户扫码登录。
2. 对最新稿件运行 `publish_xhs.py --dry-run`，人工核对标题、正文、封面及话题。
3. 获得用户对这一次真实发布的明确确认。
4. 执行一次真实发布并核对成功响应及小红书 App 中的笔记。
5. 验证相同指纹再次执行会跳过，且飞书只收到综合日报。

## 回滚

- 禁用套件中的 `publish_xhs.py` 调用。
- 恢复 `send_feishu_deliveries.py` 的第二条小红书飞书发送。
- 不删除本地 Cookie 或已发布笔记；如需删除公开笔记必须由用户单独确认。
