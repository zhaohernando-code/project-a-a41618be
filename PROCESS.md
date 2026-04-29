# PROCESS

反回归笔记和可复用经验。状态快照见 PROJECT_STATUS.json。

## 2026-04-29

- **移动端设置 affordance**：只读状态行不能默认带右箭头；只有真实可操作且已接 handler/API 的项目才显示导航 affordance。二态偏好优先用 `Switch`，多选或模型选择才进入二级菜单。
- **移动端滑动操作视觉**：左滑删除这类 destructive action 的红色背景只能在展开状态出现；闭合态要避免卡片抗锯齿透出红色，展开态要取消卡片相邻侧圆角，避免出现双圆角边框。滑动释放后需吞掉下一次 click，防止误打开详情。
- **移动端 app 化边界**：手机端不要把 PC 工作台继续压缩或在 `App.tsx` 堆 `isMobile` JSX。正确做法是 `App.tsx` 保持数据/handler 薄入口，移动端进独立 `components/mobile/*` shell；复盘页禁止复用 PC 宽表，必须用移动端卡片/列表表达同一数据。
- **Pydantic + future annotations 陷阱**：不要同时使用 `from __future__ import annotations` 和 `TYPE_CHECKING` 导入跨模块 Pydantic 类型。Pydantic v2 的 `model_rebuild()` 使用模块自身的 `sys.modules[module].__dict__` 解析前向引用，TYPE_CHECKING-only 类型不在该命名空间中。循环依赖时在 `__init__.py` 所有模块加载后注入类型并调用 `model_rebuild()`。
- **bash 脚本拼接陷阱**：不要用 `.join("; ")` 拼接数组生成 bash 命令，多余分号（如 `do;`、`then;`）会导致语法错误。改用字符串拼接，并对产物跑 `bash -n` 检查。
- **API 错误响应 key 约定**：JSON 错误响应用 `detail` 而非 `error`，前端 `core.ts` 只提取 `payload.detail` 展示给用户。key 用错会导致前端显示裸 HTTP 状态码而非中文提示。
- **LaunchAgent 配置规范**：定时任务用 `RunAtLoad` + `StartInterval`（或 `StartCalendarInterval`），服务进程用 `RunAtLoad` + `KeepAlive`。`StartInterval=300` 无法精确命中特定时钟分钟（如 08:10），需同时配置 `StartCalendarInterval` 数组。
- **SSH 隧道自愈**：隧道重连失败时先检查远端端口是否被旧 sshd 占坑；清理脚本失败时优先排查 bash 语法。隧道进程需自愈重连循环（指数退避），不能遇错即退。

## 2026-04-28

- **live-facing 任务完成定义**：repo 改动 → 测试 → publish → runtime refresh → 真实浏览器验收。缺任一步都不能算完成。
- **浏览器验收优先用 Safari**。Chrome 出现旧缓存页/空白页/异常 profile，但 curl/health/assets 正常时，直接切 Safari 复核。
- **canonical "打不开" 三步排查**：(1) `localhost 5173/8000` 是否健康？(2) canonical 是否只是 302 回登录页？(3) `com.codex.project-tunnel.ashare-dashboard` 是否被远端旧端口占坑？
- **canonical stale 排查**：先查 tunnel / remote port ownership，不要先误判为 repo 或 runtime 代码失效。
- **DeepSeek timeout 排查**：先对照运行时 `urlopen(..., timeout=...)` 阈值，再判断 provider 故障。当前机器默认代理链路对 DeepSeek 比显式 no-proxy 更稳，不能想当然把"走代理"当根因。
- **simulation 刷新**：不允许只 restart session，必须 `restart → step → rebuild`。持续运行时用"交易时段后台 tick + 单次 anchored step"，不要复用研究刷新链路。
- **Phase 5 holding-policy artifact**：必须容忍 payload 里 legacy `backtest_artifact_id` 漂移，优先使用真实存在的 artifact。
- **historical validation**：不能复用 `as_of_data_time` 之后的 future exit bars，否则 horizon study 会被未来泄漏污染。
- **盘后 freshness 文案**：用户可见层用 `截至 MM/DD HH:MM` 快照表达，不显示原始秒数。
- **follow-up prompt**：不要把 recommendation 结论前置成"答案模板"，先给事实、验证状态和冲突要求，系统结论放最后。
- **运营复盘文案**：同一状态优先压成一条摘要，不在多个位置重复堆叠。
- **Safari 缓存**：Safari 可能保留旧标签页内存态，页面自相矛盾时先刷新再判断。
- **dirty worktree 发布**：应通过临时干净快照仓执行，manifest 路径写回 durable docs。

## 2026-04-27 之前

- **项目入口**：固定以 PROJECT_STATUS.json、DECISIONS.md 为主，不回到根目录散落 phase 文档模式。
- **"统一账号"三层边界**：谁发身份、谁消费身份、谁负责路由授权。任一层仍是单账号就不能描述为"已支持多账户"。
- **"系统能力"三层归属**：每项能力必须说明属于 Web 控制面、会话工具、还是本机 CLI/脚本，不能因中台有按钮就假设当前环境也有同样入口。
- **Phase 5 真值源**：以 runtime DB 为准，repo 本地库不再当作 live 评估的替代品。
