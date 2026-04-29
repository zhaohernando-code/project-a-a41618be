# PROCESS

## Purpose

- `PROCESS.md` 只保留当前 handoff 必需信息和可复用经验。
- 一次性执行流水、重复发布记录、已过时的逐轮试错，不再长期保留。
- 历史细节如果仍需追溯，优先看 [DECISIONS.md](/Users/hernando_zhao/codex/projects/stock_dashboard/DECISIONS.md) 和 [PROJECT_STATUS.json](/Users/hernando_zhao/codex/projects/stock_dashboard/PROJECT_STATUS.json)。

## Current Handoff Snapshot

- Last updated: `2026-04-28 10:47 CST`
- Current phase: `Phase 5 - Real Validation Rebuild and Model Portfolio Policy Research`
- Current milestone: `phase-5-validation-policy-research`
- Status: `in_progress`

## Current Truth

- 当前 live Phase 5 研究真相以 runtime DB 为准：
  `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db`
- repo 本地库
  `/Users/hernando_zhao/codex/projects/stock_dashboard/data/ashare_dashboard.db`
  不再允许当作 live professionalism assessment 的代替品。
- 当前 live runtime 已通过 `phase5-daily-refresh --analysis-only` 推进到：
  `phase5-holding-policy-study:auto_model:2026-04-27:9portfolios`
- 当前 live holding-policy 关键指标：
  `included_portfolio_count=9`
  `total_order_count=4`
  `rebalance_day_count=4`
  `mean_turnover=0.037037`
  `mean_invested_ratio=0.079822`
  `mean_active_position_count=0.444444`
  `mean_annualized_excess_return_after_baseline_cost=0.000581`
  `excluded_reasons={}`
- 当前 live horizon 结论仍是：
  `40d` 为当前 frontier
  覆盖仍只有 `3` symbols / `2` as-of dates
- 当前 live browser 验收基线：
  localhost `http://127.0.0.1:5173/`
  canonical `https://hernando-zhao.cn/projects/ashare-dashboard/`
  publish manifest:
  `/private/tmp/stock-dashboard-manual-research-fix-3R7Q3W/repo/output/releases/20260428T024529Z-fd4436101087/manifest.json`
  localhost Safari 当前显示 `最近刷新 04/28 10:47`
  `运营复盘` 顶部已压缩成单条
  `研究验证 · 口径校准中 / 已纳入 4 条复盘样本；当前结论先用于观察和模拟复盘。`
  盘后 freshness 文案已从 raw seconds 改为
  `最新行情 / 截至 04/27 11:15`
  治理轨道命名已改成
  `用户轨道 / 模型轨道`
  当前候选 / 自选模块的收益涨跌语义已回到 A 股口径：
  正收益红色，负收益绿色
  `运营复盘` 双轨持仓表已新增
  `分析报告`
  操作，弹出原地精简分析弹窗
  当前 manual research / llm 追问 request view 也已修正：
  queued 请求不会再借用别的已完成请求结果
  live 验收中 `600522.SH / id=11`
  已先验证 queued 视图干净，再执行成功返回 `200 OK`
- 当前 intraday refresh / simulation runtime contract 也已经改变：
  backend 现在会在 startup 后常驻后台 `ops tick`
  只在交易时段自动刷新 active watchlist 的 `5min` 行情
  并把运行中的 simulation session 单次推进到最新已落库 bar
  不再要求用户先打开前端页面触发刷新
- 这轮 live runtime 真验证不是只看接口返回：
  发布后 live DB 先自行从
  `max(5min observed_at)=2026-04-27 03:15:00 / current_step=1`
  推进到
  `2026-04-28 02:10:00 / current_step=2`
  随后在完全不访问业务页的情况下，再自行推进到
  `2026-04-28 02:15:00 / current_step=3`
  因此“前端不开也继续跑”这一条现在已经被 runtime DB 直接证明。
- 当前 `002028.SZ` follow-up prompt live 口径也已切到低锚定版：
  先要求区分事实 / 推断、解释 validation conflict，再把
  `系统当前结论（仅供参考，不是必须采纳）`
  放到靠后位置。
- 当前 `002028.SZ` 最近一次 manual research receipt 已确认不是 builtin：
  live runtime DB 与 manual-review artifact 都显示
  `executor_kind=configured_api_key`
  `provider_name=deepseek`
  `model_name=deepseek-v4-pro`
  `attempted_keys[0].status=success`
- 当前 `600522.SH` follow-up timeout 根因也已确认：
  不是前端流程问题，而是 configured API key 调用走到 DeepSeek 后被旧的 `30s` read timeout 截断。
  同机保留默认代理时，本地同 prompt 请求约 `39.75s` 成功；
  显式禁代理时，同请求约 `61.0s` 仍超时。
  发布后 live backend 重放同题已在 `66.776s` 成功返回，
  所以当前机器上不应把 DeepSeek 改成强制 no-proxy，真正修复是把 OpenAI-compatible timeout 提升到 `75s`。
- 当前 canonical “打不开” 的最近一次根因也已确认：
  localhost 前后端都健康，真正异常是 `com.codex.project-tunnel.ashare-dashboard`
  又一次被远端僵尸 `sshd` 占住 `3101/4101` 端口而退回 `exit 255`。
  这轮已清掉旧 remote listener 并重启 LaunchAgent，agent 已恢复 `running`。
  canonical 现在未登录访问会正常回到 `/?next=/projects/ashare-dashboard/` 登录墙；
  因此“登录态失效”和“tunnel 卡死”要分开判断。

## Active Blockers

- replay 仍缺完整 `20` trading-day forward window，所以这部分还是 data-window blocker，不是 rebuild-path blocker。
- holding-policy 仍不能 promotion：
  `gate_status = draft_gate_insufficient_evidence`
  `mean_rebalance_interval_days = null`
  `mean_invested_ratio` 和 `mean_active_position_count` 仍弱。
- horizon 样本仍偏窄：
  只覆盖 `3` symbols / `2` as-of dates。

## Next Step

- 继续对 live runtime DB 跑 `phase5-daily-refresh --analysis-only`，等待新的 real runtime 日期。
- 目标不是再证明链路会不会跑，而是累积跨日期 rebalance evidence。
- 下一阶段重点盯：
  `included_portfolio_count >= 9` 是否保持
  `mean_invested_ratio` 是否继续抬升
  `mean_active_position_count` 是否继续抬升
  `mean_rebalance_interval_days` 何时从 `null` 变成可用证据
  `40d` 在更多日期下是否继续领先

## Reusable Lessons

- 项目入口固定以 `PROJECT_STATUS.json`、`DECISIONS.md`、`PROCESS.md`、`PROJECT_PLAN.md` 为主；不要重新回到根目录 phase 文档散落模式。
- live-facing 任务的完成定义始终是：
  repo 改动
  测试
  publish
  runtime refresh
  真实浏览器验收
  缺任一步都不能算完成。
- 如果 Browser Use 的 `iab` backend 当前不可用，不要把 live browser 验收卡死在插件本身；先记录该阻塞，再回退到真实桌面 Safari/Chrome 会话完成 canonical 页面核验。
- 如果主仓库是 dirty worktree，发布应继续通过临时干净快照仓执行，并把 manifest 路径写回 durable docs。
- simulation workspace 的持仓回放不能只锚定最新行情 bar；若 `simulation_session.last_data_time` 已经晚于最新 `5min` 行情点，必须把 session 时钟补进时间线，否则会出现“最近动作理由与 recent_orders 已显示成交，但 holdings 仍是 0”的假矛盾。
- 运营复盘的验证/治理提示不能在顶部告警、组合卡、策略说明、治理摘要里重复堆叠；同一状态应优先压成一条摘要，再把补充解释留在最靠近上下文的位置。
- 盘后或非交易时段的 freshness 文案不要显示原始秒数；用户可见层统一改成 `截至 MM/DD HH:MM` 这类快照表达。
- follow-up prompt 不要把 recommendation 结论前置成“答案模板”；应先给事实、验证状态和冲突要求，再把系统结论降级为参考上下文。
- 如果 configured API key 的 follow-up / manual-research 报 `The read operation timed out`，先对照运行时 `urlopen(..., timeout=...)` 阈值再判断 provider 故障。当前这台机器默认代理链路对 DeepSeek 反而比显式 no-proxy 更稳，不能想当然把“走代理”当作根因。
- 如果 canonical 看起来“直接打不开”，先分三步判断：
  `localhost 5173/8000` 是否健康；
  canonical 是不是只是 `302` 回统一登录页；
  `com.codex.project-tunnel.ashare-dashboard` 是否又被远端旧 `3101/4101` 转发占坑。
- 对需要持续运行的模拟盘，不要复用 `refresh-runtime-data` 的 `restart -> step` 研究刷新链路去做后台执行；持续运行应使用“交易时段内的后台 tick + 单次 anchored step”路径，否则会不断重建 session 或在同一最新价快照上重复补假步数。
- Phase 5 holding-policy artifact 读取必须容忍 payload 里的 legacy `backtest_artifact_id` 漂移；优先使用真实存在的 artifact，而不是盲信 payload。
- Phase 5 simulation refresh 不允许只 restart session；必须 `restart -> step -> rebuild`，否则只会制造零步空 session 或一轮滞后的 `pending_rebuild`。
- historical validation 不能复用 `as_of_data_time` 之后的 future exit bars；否则 horizon study 会被未来泄漏污染。
- canonical 若看起来 stale，先排查 tunnel / remote port ownership；不要先把它误判成 repo 或 runtime 代码失效。
- 浏览器验收优先用 Safari。Chrome 如果出现旧缓存页、空白页、异常 profile 状态，但 curl/health/served assets 正常，不要继续在 Chrome 上浪费时间，直接切 Safari 复核。
- Safari 即使使用正确入口，也可能保留旧标签页或旧 `?cb=` 页面内存态；如果页面上出现”最近动作理由已更新，但模型持仓仍显示 0”这类自相矛盾现象，先刷新当前标签页，再判断是不是 live runtime 真问题。
- Pydantic schema 模块不要同时使用 `from __future__ import annotations` 和 `TYPE_CHECKING` 导入跨模块 Pydantic 类型，除非在 `__init__.py` 中所有模块加载后注入类型并显式调用 `model_rebuild()`。循环依赖时使用 `__init__.py` 命名空间注入模式，而非在源文件中做 bottom import。
- SSH 隧道清理脚本不要用 `.join(“; “)` 拼接数组生成 bash，多余分号会导致语法错误。必须用字符串拼接，并对生成脚本跑 `bash -n` 做语法检查。
- API 错误响应的 JSON key 必须用 `detail` 而非 `error`，因为前端 `core.ts` 只提取 `detail` 展示给用户。
- 定时刷新任务必须在 `~/Library/LaunchAgents/` 下配置 `RunAtLoad` + `StartInterval`（或 `StartCalendarInterval`），`KeepAlive` 只适用于长期运行的服务进程。
