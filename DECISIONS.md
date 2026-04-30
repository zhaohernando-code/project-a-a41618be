# 一个关于a股的当前数据和投资建议看板 Decisions

[2026-04-30T01:28:00+08:00] Multi-account watchlist presentation and root act-as lifetime decision:
多账号隔离上线后，前端不再允许把“当前账号自选”和“全局候选池”继续渲染成一个模糊共享列表；root 的 `act_as` 也不再跨页面刷新持久化。当前批准的交互 contract 是：账号自选单独成区显示，候选池单独成区显示；root 代看只在当前单页会话内有效，刷新或重开标签后默认回到 root 自己的空间。

补充说明
- 这轮真实用户反馈表面像“member 仍看到了所有自选、root 自己持仓不见了”，但 live 数据核对后发现两层问题并不相同：member 侧是候选池与自选池的展示边界不清，root 侧则是此前 `act_as` 持久化导致标签页回到 member 空间后，用户误以为 root 仓位消失。
- 新交互不改变后端隔离 contract。真实账号隔离仍由 `watchlist_follows` / `owner_login` / `StockAccessContext.target_login` 提供；这次只是把 UI 呈现与空间切换时间范围收口到不容易误判的形态。
- live 验证基于 canonical `https://hernando-zhao.cn/projects/ashare-dashboard/`：Safari root 会话仍能看到 `002028.SZ` 的原持仓，而通过真实签名根域 session 调用 canonical edge API、再配合 `X-Ashare-Act-As-Login`，`member-a` 与 `amoeba` 都已返回空 watchlist 和 draft simulation。

[2026-04-29T22:45:00+08:00] Mobile settings and home list actions must expose only real operations:
移动端设置页不再把只读状态行伪装成可点击导航；只有实际接入能力的项目才允许出现右侧箭头。主题因为只有浅色/夜间两态，继续使用行内 `Switch`；默认模型作为真实可操作项进入二级菜单，支持选择本机 Codex GPT builtin 执行器或已配置模型 Key，其中外部 Key 选择复用现有 `/settings/model-api-keys/{id}/default` 后端接口。首页关注股票卡片新增左滑移除入口，但删除仍进入现有确认弹窗，不做静默删除。

补充说明
- `规范路由` 不再作为移动端设置项展示，避免无意义长 URL 占据设置页宽度。运行状态、数据源、自动降级、研究模式、版式密度、风险提醒等当前只读项保留为状态行，不显示箭头。
- 首页左滑操作仅对 `source_kind !== "candidate_only"` 的关注来源标的开放；纯候选来源不展示移除入口，和桌面端自选删除边界保持一致。
- 左滑移除的红色按钮只在展开状态显示，展开后卡片右侧圆角归零，避免闭合状态红色透底和双圆角边框；滑动释放会吞掉下一次 click，避免误跳单票页。
- 发布先从主仓库提交 `a654cd9070a917f4050433e674fec5d7d638ff13`，再通过干净 worktree `/private/tmp/stock-dashboard-mobile-publish-ANQXdo/repo` 执行标准脚本，生成 manifest `/private/tmp/stock-dashboard-mobile-publish-ANQXdo/repo/output/releases/20260429T145429Z-a654cd9070a9/manifest.json`。localhost `http://127.0.0.1:5173/` 已在 390x844 验收：首页显示 `关注股票`、底部 tab 和移除入口，设置页显示 `外观主题` Switch，只有 `默认模型` 带箭头且二级页包含 `本机 Codex GPT` 与当前 `deepseek-v4-pro` Key。canonical 标准入口在当前浏览器会话被统一登录层拦截到登录页；脚本 release parity 已通过，但手工浏览器 canonical 复验需要有效登录态。

[2026-04-29T17:40:00+08:00] Mobile dashboard information architecture is app-native, not a compressed desktop workspace:
手机端正式固定为 `首页 / 单票 / 复盘 / 设置` 四个 bottom tabs；原先“首页”和“自选/候选”不再拆成两个移动端入口，统一合并到首页，用一个焦点卡片、搜索筛选和候选/自选列表承载。设置升为独立 tab，但只展示和操作已有真实运行时能力，不新增未接后端的假偏好项。

补充说明
- 桌面端继续保留现有候选、单票、运营复盘、设置工作台；移动端通过 `MobileAppShell` 走独立组件树，不再把大段 mobile JSX 继续塞进 `App.tsx`。
- 移动端复盘页不得复用 `TrackHoldingsTable` 这类 PC 宽表。用户轨道、模型轨道、持仓、模型建议和时间线都以移动端卡片/列表呈现，避免横向滚动和超长桌面栅格。
- 设计稿真值源为 `output/design/mobile-redesign/mobile-tab-home-candidates.png`、`mobile-tab-stock-detail.png`、`mobile-tab-operations-review.png` 和 `mobile-tab-settings.png`；已删除旧的半截 SVG 概念图和废弃的独立自选页图片，避免后续实现回退到错误 IA。

[2026-04-28T10:47:41+08:00] Manual-research request views must never borrow another request's LLM result on the live dashboard:
the live manual-research / follow-up workflow is no longer allowed to serialize a queued request together with the `manual_llm_review` payload of a different, newer completed request. From this round on, every `ManualResearchRequestView` must carry only its own request-scoped projection; if the request itself has not executed yet, its `manual_llm_review` must stay empty/queued instead of inheriting another artifact. This closes the request/result mismatch that could surface as follow-up actions targeting the wrong object and intermittently ending in `404 Not Found`.

补充说明
- 根因在 [manual_research_workflow.py](/Users/hernando_zhao/codex/projects/stock_dashboard/src/ashare_evidence/manual_research_workflow.py) 的 `_serialize_request(...)`。旧逻辑总是先取 `build_manual_llm_review_projection(...)` 的“当前 recommendation 最新人工研究结果”；当 `projection.request_id != request.id` 时，它只覆盖了 `status` 和 `stale_reason`，却把别的 request 的 `request_id / artifact_id / raw_answer / citations` 整包保留下来。这样前端看到的可能是“当前这条 queued 请求”，但内部挂着另一条已完成请求的结果。
- 修复现在显式回退到 request-scoped `_build_request_projection(...)`：一旦发现 recommendation-level projection 的 `request_id` 不等于当前 request，本条 view 就只按当前 request 自己的 `status/status_note/artifact` 生成 `manual_llm_review`。没有执行过的请求会保持 `generated_at=null / summary=null / artifact_id=null`，而不是再借旧结果。
- 回归锁在 [test_manual_research_workflow.py](/Users/hernando_zhao/codex/projects/stock_dashboard/tests/test_manual_research_workflow.py) 新增用例：当较旧请求仍是 `queued`、较新请求已经 `completed` 时，列表里的 queued request 必须继续指向自己的 `request_id/request_key`，且 `artifact_id/summary/raw_answer` 都为空。`tests.test_api_access` 也已复跑通过，确认 API 合同未被破坏。
- 发布通过干净快照仓 `/private/tmp/stock-dashboard-manual-research-fix-3R7Q3W/repo` 完成，manifest 为 `/private/tmp/stock-dashboard-manual-research-fix-3R7Q3W/repo/output/releases/20260428T024529Z-fd4436101087/manifest.json`。live 验收不是只看单测：我先创建了新的 `600522.SH` 请求 `id=11`，在未执行前直接查 `GET /manual-research/requests/11`，确认它返回 `status=queued`、`manual_llm_review.request_id=11`、`artifact_id=null`、`raw_answer=null`，不再借 `id=10` 的旧结果；随后再对同一条请求执行 `POST /manual-research/requests/11/execute`，live backend 返回 `HTTP/1.1 200 OK` 并成功落成新的 manual-review artifact。Safari 真实浏览器会话也已重新加载 localhost `http://127.0.0.1:5173/`，当前显示 `最近刷新 04/28 10:47`。

[2026-04-28T10:35:48+08:00] Candidate-return color semantics and operations-report entry must follow A-share intuition on the live dashboard:
the live frontend is no longer allowed to render positive return percentages with Ant Design `success` green and negative return percentages with `danger` red in the candidate / self-select modules. On this dashboard, user-facing涨跌语义 must stay aligned with A-share convention: gains render red, losses render green. From this round on, candidate 20-day return cells reuse the existing `value-positive / value-negative` class contract instead of AntD status colors, and `运营复盘` holdings tables now expose a direct `分析报告` action that opens a compact stock-analysis modal without forcing the user to leave the operations workspace.

补充说明
- 这轮问题来自真实前端 contract，而不是底层数据错误：`frontend/src/App.tsx` 里的候选列表桌面表格此前把 `20日` 涨跌直接映射成 `type={>=0 ? "success" : "danger"}`，导致上涨显示绿色、下跌显示红色，和当前看板其他位置已经采用的 A 股涨红跌绿语义冲突。
- 修复现在统一落在 [App.tsx](/Users/hernando_zhao/codex/projects/stock_dashboard/frontend/src/App.tsx)。候选桌面表格与移动卡片都改成通过 `valueTone(...)` 输出 `value-positive / value-negative`，从而复用现有 CSS：正值走红色、负值走绿色，不再依赖 AntD 默认 `success/danger` 配色语义。
- 同一轮里，`运营复盘` 的 `用户轨道 / 模型轨道` 持仓表新增了 `分析报告` 按钮。按钮会调用新的 `openAnalysisReportModal(symbol)` 路径：优先复用当前单票 dashboard；若当前焦点不是该 symbol，则额外请求一次 `api.getStockDashboard(symbol)`，然后在原地弹出 `运营复盘分析报告` 精简弹窗，集中展示建议摘要、触发点、风险、验证摘要和最近人工研究结论，并提供 `打开完整分析` 跳转。
- 回归锁在 [test_dashboard_views.py](/Users/hernando_zhao/codex/projects/stock_dashboard/tests/test_dashboard_views.py)：测试现在显式断言候选区使用 `className={\`value-\${valueTone(...)}\`}`，不再允许旧的 `success/danger` 逻辑回归；同时断言 `分析报告`、`运营复盘分析报告` 和 `onOpenReport` wiring 均存在。
- 发布继续通过干净快照仓 `/private/tmp/stock-dashboard-ops-report-0bQC1K/repo` 执行，manifest 为 `/private/tmp/stock-dashboard-ops-report-0bQC1K/repo/output/releases/20260428T023221Z-f2e7410af295/manifest.json`。本轮 repo 验证 `PYTHONPATH=src python3 -m unittest tests.test_dashboard_views` 与 `npm --prefix frontend run build` 已通过；live bundle 也已从 `http://127.0.0.1:5173/assets/index-9f572869.js` 复核到 `分析报告`、`运营复盘分析报告`、`onOpenReport` 以及新的 `value-` 渲染路径。

[2026-04-28T10:17:00+08:00] Background intraday refresh and simulation tick must live in the backend runtime, not behind page-open side effects:
the stock dashboard is no longer allowed to depend on someone opening `运营复盘` or any other frontend route before intraday market data and simulation state advance. From this round on, the FastAPI runtime starts a background operations tick on startup, runs it continuously during SSE/SZSE trading sessions, refreshes stale `5min` bars for the active watchlist, and advances the currently running simulation session exactly once to the newest landed market bar instead of restarting the session or replaying multiple fake catch-up steps.

补充说明
- 这次问题先在 live runtime DB `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db` 复核：即使本机已经处在 `2026-04-28 10:11 CST` 交易时段，`market_bars.timeframe='5min'` 仍停在 `2026-04-27 03:15:00`，运行中的 `simulation_sessions.id=9` 也还卡在 `current_step=1 / last_data_time=2026-04-27 03:20:00`。这说明旧实现并不会在前端关闭时自行推进。
- 根因分成两层。第一，`api.py` 之前没有 startup/lifespan 常驻任务，只有页面请求时临时兜底。第二，现有 CLI `refresh-runtime-data` 虽然能刷新研究态，但它的 simulation 路径是 `restart -> step`，适合研究重建，不适合拿来做持续运行的模拟盘。
- 代码修复落在 [api.py](/Users/hernando_zhao/codex/projects/stock_dashboard/src/ashare_evidence/api.py)、[runtime_ops.py](/Users/hernando_zhao/codex/projects/stock_dashboard/src/ashare_evidence/runtime_ops.py)、[simulation.py](/Users/hernando_zhao/codex/projects/stock_dashboard/src/ashare_evidence/simulation.py) 和 [market_clock.py](/Users/hernando_zhao/codex/projects/stock_dashboard/src/ashare_evidence/market_clock.py)。新逻辑只在交易时段运行；先判断 active watchlist 和 intraday stale 状态，再同步 `5min` 行情，然后仅当最新 bar 晚于当前 session 时钟时，调用单次 anchored simulation step，把 `last_data_time` 直接推进到最新已落库 bar，避免在同一最新价快照上重复补几十个虚假决策步。
- 回归测试覆盖了三类 contract：交易时段判断 [test_market_clock.py](/Users/hernando_zhao/codex/projects/stock_dashboard/tests/test_market_clock.py)、后台 tick 行为 [test_runtime_ops.py](/Users/hernando_zhao/codex/projects/stock_dashboard/tests/test_runtime_ops.py)、以及“运行中 session 只追到最新 bar 一次”的 simulation catch-up [test_simulation_workspace.py](/Users/hernando_zhao/codex/projects/stock_dashboard/tests/test_simulation_workspace.py)。同时 [test_api_access.py](/Users/hernando_zhao/codex/projects/stock_dashboard/tests/test_api_access.py) 显式关闭测试环境 background tick，避免 TestClient 与后台线程互扰。
- 由于主仓库仍是 dirty worktree，这轮发布继续通过临时干净快照仓 `/private/tmp/stock-dashboard-background-tick-ASEMyS/repo` 执行标准脚本，manifest 为 `/private/tmp/stock-dashboard-background-tick-ASEMyS/repo/output/releases/20260428T021238Z-3e056de237f4/manifest.json`。
- live 验收闭环已经完成，而且不依赖打开业务页接口推进数据：发布后先看到 live backend 首轮已把 runtime DB 推进到 `max(5min observed_at)=2026-04-28 02:10:00`、`simulation_sessions.id=9 current_step=2 / last_data_time=2026-04-28 02:10:00`；随后完全不访问 `/dashboard/operations`，只等待下一根真实 5 分钟 bar，再直接查 live DB，确认它已自行走到 `2026-04-28 02:15:00` 和 `current_step=3 / updated_at=2026-04-28 02:15:31.797831`。Safari localhost `http://127.0.0.1:5173/` 同时显示 `最近刷新 04/28 10:17`，证明 served page 已读到新 runtime。

[2026-04-28T01:07:00+08:00] Canonical tunnel stale-port recovery and auth-wall clarification from local execution:
the canonical stock-dashboard route is not currently failing because the frontend or backend is down. On this round, localhost `5173/8000` stayed healthy while the public tunnel agent had fallen back into the same stale remote-port condition seen earlier: old remote `sshd` listeners were still holding `127.0.0.1:3101/4101`, so `com.codex.project-tunnel.ashare-dashboard` kept exiting with code `255`. Clearing the stale remote forward and restarting the LaunchAgent restored the tunnel process; the canonical route now responds normally again, but unauthenticated requests still land on the shared login wall by design.

补充说明
- 这次用户反馈“股票看板直接打不开了”后，先复核了 localhost runtime：`http://127.0.0.1:5173/` 仍返回 `200` 静态入口，`http://127.0.0.1:8000/health` 也保持 `200 {"status":"ok"}`。因此问题不是 repo/runtime 代码崩溃。
- canonical `https://hernando-zhao.cn/projects/ashare-dashboard/` 的直接返回是 `302 -> /?next=%2Fprojects%2Fashare-dashboard%2F`，并附带 `set-cookie: hz_auth_session=; Max-Age=0`。这说明未登录访问会被统一身份入口接管，不是股票看板路由自身 500。
- 同时 `launchctl print gui/$(id -u)/com.codex.project-tunnel.ashare-dashboard` 显示 agent 长期处于 `last exit code = 255`，而远端主机 `codex-server` 上仍有旧 `sshd` 占着 `127.0.0.1:3101/4101`。本轮已清掉那组旧 listener，并执行 `launchctl kickstart -k gui/$(id -u)/com.codex.project-tunnel.ashare-dashboard`；当前 agent 已恢复到 `active count = 1 / state = running`，远端端口也已重新被新的 `sshd` pid 占用。
- Safari localhost 验收仍通过：`http://127.0.0.1:5173/` 当前可以正常打开 `波段决策看板` 首页。canonical 是否能直达业务页现在只取决于浏览器是否还保有有效登录态；未登录时落到统一登录页属于预期行为。

[2026-04-28T00:40:00+08:00] DeepSeek follow-up timeout and proxy-path decision from local execution:
the live follow-up path is no longer allowed to treat `30s` as a safe upper bound for configured OpenAI-compatible providers. On this machine, the default proxied network path to `https://api.deepseek.com` is currently the only verified path that completes reliably; the explicit no-proxy path remains slower and still timed out during local reproduction. From this round on, manual-research / follow-up execution keeps the default proxy path and raises the OpenAI-compatible read timeout to `75s`.

补充说明
- 这轮排查先在 live runtime DB `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db` 复核 `600522.SH` 的失败记录。`manual_research_requests.id=6` 和 `id=7` 都是 `executor_kind=configured_api_key`、`model_api_key_id=1`、`failure_reason=The read operation timed out`，开始到失败约 `31s`，与 [llm_service.py](/Users/hernando_zhao/codex/projects/stock_dashboard/src/ashare_evidence/llm_service.py) 里旧的 `timeout=30` 精确对齐。这说明不是前端没发请求，也不是 manual-research 编排没执行，而是 DeepSeek 调用已经发出，但在我们自己的读超时窗口内没拿到结果。
- 同机本地环境确实挂了全局代理：`HTTP_PROXY/HTTPS_PROXY=http://127.0.0.1:17890`、`ALL_PROXY=socks5://127.0.0.1:17891`。但实测结果与“DeepSeek 不该走代理”的直觉相反：按运行时代码路径、保留默认代理时，使用与失败案例同一份 `600522.SH` prompt 的本地请求在 `39.75s` 成功返回；显式 `disable_proxies=True` 后，同一请求在 `61.0s` 仍然报 `The read operation timed out`。因此这轮不做“禁代理直连 DeepSeek”的修复，当前机器上的代理链路反而更稳定。
- 真正修复落在 [llm_service.py](/Users/hernando_zhao/codex/projects/stock_dashboard/src/ashare_evidence/llm_service.py)：`OpenAICompatibleTransport` 现在把 `OPENAI_COMPATIBLE_TIMEOUT_SECONDS` 提升到 `75`，保留默认代理行为不变。回归锁在 [test_runtime_config.py](/Users/hernando_zhao/codex/projects/stock_dashboard/tests/test_runtime_config.py)，测试显式断言 transport 会把扩大的 timeout 传给 `urlopen(...)`。
- 发布继续通过干净快照仓 `/private/tmp/stock-dashboard-followup-prompt-o4Rc3S/repo` 完成，当前 manifest 为 `/private/tmp/stock-dashboard-followup-prompt-o4Rc3S/repo/output/releases/20260427T163737Z-0963fa9fabb2/manifest.json`。发布后我直接对 live backend `http://127.0.0.1:8000/analysis/follow-up` 重放了同一条 `中天科技最近长势喜人，你觉得他还会继续涨么`，真实返回在 `66.776s` 成功完成，`status=completed`、`executor_kind=configured_api_key`、`selected_key=deepseek-v4-pro`。这证明根因是 `30s` 超时过短，而不是请求流程本身坏掉。
- 浏览器侧这轮补了 Safari localhost 验收：`http://127.0.0.1:5173/` 当前已正常加载 `波段决策看板` 首页并显示 `最近刷新 04/28 00:40`。canonical 未登录状态会先落到统一登录页，所以这轮真实功能验收以 localhost Safari + live backend 直调为准。

[2026-04-27T23:33:00+08:00] Follow-up prompt de-anchoring and manual-research receipt verification decision from local execution:
the live follow-up prompt is no longer allowed to front-load the system verdict as if it were the answer. From this round on, `follow_up.copy_prompt` must start from explicit fact/prediction separation, require the model to explain validation-metric conflicts before giving direction, and treat the system recommendation as reference-only context. The latest `002028.SZ` manual-research receipt has also now been verified against the live runtime DB and artifact store as a successful `DeepSeek` execution rather than a builtin-model run.

补充说明
- 这轮提示词收口落在 [dashboard.py](/Users/hernando_zhao/codex/projects/stock_dashboard/src/ashare_evidence/dashboard.py)。`_follow_up_payload(...)` 现在先声明“不要补充未给出的事实”“先区分已知事实与推断”“如果验证指标之间存在张力或冲突，必须先解释冲突”，再列 validation metrics / 风险 / 驱动，最后才附上 `系统当前结论（仅供参考，不是必须采纳）`。这样 `可以买吗` 一类用户追问不再被已有 recommendation 文案强锚成单向复述器。
- 回归已经补到 [test_dashboard_views.py](/Users/hernando_zhao/codex/projects/stock_dashboard/tests/test_dashboard_views.py)：测试现在锁定 `copy_prompt` 必须包含冲突解释要求、证据不足直说要求，以及“系统当前结论仅供参考”字段，避免后续再把 recommendation 行提前回最前面。
- 发布仍通过临时干净快照仓完成，最新 manifest 为 `/private/tmp/stock-dashboard-followup-prompt-o4Rc3S/repo/output/releases/20260427T152726Z-dcb9531d1a10/manifest.json`。本地 live API `http://127.0.0.1:8000/stocks/002028.SZ/dashboard` 已返回新 prompt 文案，确认不是 repo-only 改动。
- `002028.SZ` 最近一次 manual research / follow-up 回执已在 live runtime DB `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db` 复核：`manual_research_requests.id=5`、`request_key=manual-research:reco-002028.SZ-20260427-phase2:20260427151723412637`、`executor_kind=configured_api_key`、`model_api_key_id=1`、`status=completed`。同一条记录的 `request_payload.selected_key` 与 artifact `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/artifacts/manual_reviews/manual-review:manual-research:reco-002028.SZ-20260427-phase2:20260427151723412637.json` 都显示 `provider_name=deepseek`、`model_name=deepseek-v4-pro`、`base_url=https://api.deepseek.com`、`attempted_keys[0].status=success`、`failover_used=false`。如果 DS 账单里没看到花费，更像是账单口径/计费账户侧问题，不是这次请求没走 DeepSeek。
- 浏览器验收方面，in-app browser 的 `iab` backend 当前不可用，所以这轮改走真实 Safari 会话复核 canonical。`https://hernando-zhao.cn/projects/ashare-dashboard/` 当前已加载到 `思源电气 · 002028.SZ`，页面显示 `最近刷新 04/27 23:33`，说明最新发布 bundle 已经在真实用户入口可见。

[2026-04-27T22:53:00+08:00] Operations-copy compression and market-freshness wording decision from local execution:
the live operations workspace is no longer allowed to repeat the same validation / governance caveat across metric cards, portfolio panels, strategy notes, and governance tabs. From this round on, `运营复盘` must collapse repeated warning copy into one concise research-validation summary, render post-close freshness as an “截至 HH:MM” market snapshot instead of raw seconds, and label the governance tracks as `用户轨道 / 模型轨道` so the page explains what each panel is for without leaking internal contract wording.

补充说明
- 这轮收口主要落在 [App.tsx](/Users/hernando_zhao/codex/projects/stock_dashboard/frontend/src/App.tsx)。前端现在统一通过 `compactValidationNote(...)`、`operationsValidationDescription(...)` 和 `formatMarketFreshness(...)` 压缩重复提示：顶部只保留一条 `研究验证 · 口径校准中` 摘要，`5 分钟延迟` 改成 `最新行情`，收盘后会显示 `截至 04/27 11:15` 一类时间快照，而不再暴露 `40335 s` 这种盘后秒数。
- 组合和治理区不再重复堆叠 `基准解读说明 / 组合验证口径 / 组合验证仍在补齐 / 模型自动持仓` 等多层提醒。组合面板现在只保留一条 `当前说明`，治理 tab 统一改成 `用户轨道 / 模型轨道`，并直接说明“用户轨道看手动下单结果，模型轨道看模拟盘里的自动调仓结果”。
- 用户提到反复出现的 `Phase 2 规则基线已完成 walk-forward 产物生成...`，根因是 `research_candidate` recommendation / validation payload 长期复用底层 `status_note`，多个页面又直接渲染 `validation_note`。这轮同时把 [validation.py](/Users/hernando_zhao/codex/projects/stock_dashboard/src/ashare_evidence/phase2/validation.py) 的默认文案收口成“已有滚动验证产物，当前仍处于观察阶段，尚未完成正式验证”，并把 [phase5_contract.py](/Users/hernando_zhao/codex/projects/stock_dashboard/src/ashare_evidence/phase2/phase5_contract.py) 里的等权组合/自动执行提示压成短句，避免相同长句继续从别的接口漏到页面。
- 回归与发布闭环已经完成：`npm run build`、`PYTHONPATH=src python3 -m unittest tests.test_dashboard_views tests.test_simulation_workspace` 通过；由于主仓库仍是 dirty worktree，这轮发布基于上一次可发布快照仓 `/private/tmp/stock-dashboard-ui-publish-M3NrD9/repo` 完成，manifest 为 `/private/tmp/stock-dashboard-ui-publish-M3NrD9/repo/output/releases/20260427T145228Z-2eb558b75fcb/manifest.json`。
- 真实浏览器复核以 canonical Safari 为准：`https://hernando-zhao.cn/projects/ashare-dashboard/` 当前显示 `最近刷新 04/27 22:53`；`运营复盘` 顶部已切换为 `最新行情 / 截至 04/27 11:15` 和单条 `研究验证` 提示，盘后不再显示 raw seconds；治理入口下的轨道命名也已改为 `用户轨道 / 模型轨道`。

[2026-04-27T22:26:00+08:00] Simulation workspace timeline-anchor decision from local execution:
the live simulation workspace is no longer allowed to let a same-step `order_filled` event appear in `最近动作理由` while leaving the corresponding model holding at zero. From this round on, portfolio replay must anchor to `simulation_session.last_data_time` whenever the newest `5min` market bar still lags behind the session clock, so the just-filled order is reflected immediately in holdings, NAV, and exposure.

补充说明
- 根因已经在真实 runtime DB 上复核清楚：`simulation_events`、`paper_orders` 和 `paper_fills` 都已记录 `600522.SH / 中天科技` 在 `2026-04-27 03:20:00` 的 `buy 1000`，但 `market_bars` 的最新 `5min` 点只到 `03:15:00`。旧版 `src/ashare_evidence/simulation.py` 仅按行情时间点回放成交，导致 `order_filled` 能出现在 `最近动作理由`，`recent_orders` 也能看到成交，但 `holdings` / `仓位` / `净值` 仍停在成交前状态。
- 修复现在在 `_portfolio_context(...)` 内显式把 `simulation_session.last_data_time` 追加为组合回放锚点，并在比较时兼容旧测试夹具里的 naive datetime 与 session aware datetime。这样即使最新一分钟/五分钟 K 线还没补到该时点，组合也会按“最后可用价格 + 当前 session 时钟”及时纳入刚成交的头寸。
- 回归覆盖已补到 `tests/test_simulation_workspace.py`：`PYTHONPATH=src python3 -m unittest tests.test_simulation_workspace` 现在锁定“模型自动成交后，`recent_orders` 非空且 `holdings` 里必须出现正持仓数量”；同时 `PYTHONPATH=src python3 -m unittest tests.test_dashboard_views` 复跑通过，确认运营复盘投影未被新锚点破坏。
- 由于主仓库仍是 dirty worktree，这次发布继续通过临时 git 快照仓 `/private/tmp/stock-dashboard-ops-holdings-fix-QnODE5/repo` 执行 `scripts/publish-local-runtime.sh`，生成 manifest `/private/tmp/stock-dashboard-ops-holdings-fix-QnODE5/repo/output/releases/20260427T142343Z-99c9ef25a4d4/manifest.json`。发布脚本的 parity verifier 这次直接通过，说明 repo/runtime/canonical 资源与关键 API 指纹一致。
- Safari 真实浏览器复验也已闭环：localhost `http://127.0.0.1:5173/` 与 canonical `https://hernando-zhao.cn/projects/ashare-dashboard/` 当前都显示 `最近刷新 04/27 22:26`；进入 `运营复盘` 后，模型轨道同时展示 `最近动作理由：中天科技 最新价 36.53 买入 1000 股`，并在持仓表内显示 `中天科技 1000 股 / 仓位 +18.3%`。另外，这轮也再次证明旧的 Safari 标签页或带旧 `?cb=` 的页面内存态可能继续显示“理由已更新、持仓仍为 0”，必须刷新页面后再判断 live verdict。

[2026-04-27T21:48:00+08:00] Phase 5 live-runtime source-of-truth and same-run holding-policy decision from local execution:
`Phase 5` runtime professionalism assessment must now treat `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db` as the authoritative live study database. The repo-local `data/ashare_dashboard.db` is no longer acceptable as a proxy for live policy evidence, because it can lag the actual runtime by multiple refresh cycles. Within that live DB, the already-published same-run rebuild path has now been proven to include the newest stepped model portfolio immediately rather than one run later.

补充说明
- 这轮先显式复核了 repo DB 与 runtime DB 的偏差：repo 本地库当时只显示 `5` 个 auto-model portfolios 和较早的 simulation event counts，而 live runtime DB 已经处于 `8portfolios`、`refresh_step=3`、`model_decision=3`、`order_filled=3` 的状态。后续所有 `phase5-daily-refresh --analysis-only`、holding-policy study 和 browser验收都必须以 runtime 路径下的 SQLite 为真相源，否则会把 repo-side 旧状态误读成 live blocker。
- 在这个前提下，继续对 live runtime 执行一轮 `phase5-daily-refresh --analysis-only`，CLI 输出已把 holding-policy artifact 推进到 `phase5-holding-policy-study:auto_model:2026-04-27:9portfolios`。最新 study 摘要为 `included_portfolio_count=9`、`total_order_count=4`、`rebalance_day_count=4`、`mean_turnover=0.037037`、`mean_invested_ratio=0.079822`、`mean_active_position_count=0.444444`、`mean_annualized_excess_return_after_baseline_cost=0.000581`，并保持 `excluded_reasons={}`。这说明“restart -> step -> rebuild”链路已经能把最新 `sim-20260427134635-5a4d9d-model` 同轮纳入研究，而不是继续卡在 `pending_rebuild`。
- gate 结论没有变成 promotion-ready。`decision.gate_status` 仍是 `draft_gate_insufficient_evidence`，唯一 incomplete gate 仍是 `mean_rebalance_interval_days_floor`；design diagnostics 也继续把 `mean_invested_ratio_floor` 和 `mean_active_position_count_floor` 指向 `portfolio_construction`。所以 blocker 已经不是 runtime wiring，而是跨日期 rebalance 证据仍然不足。
- Safari live 验收这轮重新闭环了两条入口：localhost `http://127.0.0.1:5173/?cb=20260427-2149` 与 canonical `https://hernando-zhao.cn/projects/ashare-dashboard/?cb=20260427-2149` 都显示 `最近刷新 04/27 21:48`、`最近分析 04/27 21:46`，当前焦点一致为 `思源电气 · 002028.SZ`。Chrome 当前 profile 会话一度出现旧缓存页和空白页，但 curl 直接验证了 localhost/canonical 的 HTML 和 JS/CSS 资产都正常可取，因此这次 live verdict 以 Safari 的 fresh-load 结果为准。

[2026-04-27T21:01:00+08:00] Phase 5 runtime simulation-step decision from local execution:
runtime `refresh-runtime-data` / `phase5-daily-refresh` is no longer allowed to stop after merely restarting the simulation session. From this round on, the published refresh path must immediately advance one `refresh_step` so the live auto-model track can produce a same-cycle `model_decision` and, when auto-execute is enabled, a real `order_filled` event instead of accumulating empty zero-step sessions.

补充说明
- `src/ashare_evidence/cli.py` 现在在 analysis refresh 结束后执行 `restart_simulation_session(session)` 并立刻调用 `step_simulation_session(session)`，同时把 `simulation_current_step` 暴露到 CLI 输出。`tests/test_cli_runtime_refresh.py` 新增/更新回归，锁定 refresh 后 session 必须来到 `current_step == 1`，并且当 `auto_execute_model` 为真时必须能在 refresh 链路里产生模型成交；`tests.test_simulation_workspace` 与 `tests.test_phase5_holding_policy_study` 也一并复跑通过。
- 这次修复的根因不是 artifact lookup，而是 runtime evidence-generation path 根本没跑起来。真实 DB 在补丁前只有 `session_created / session_started / session_restarted / config_updated` 事件，没有任何 `refresh_step / model_decision / order_filled`，所以 holding-policy 研究虽然已经从 `0portfolios` 误判恢复到可读状态，但其 exposure/turnover 仍全是零，因为它聚合的是一串从未推进过一步的空 session。
- 发布继续走临时 git-backed 快照仓 `/private/tmp/stock-dashboard-workingtree-gitpublish-lSN3TC/repo`，通过隔离提交 `8c90ef19255a9e10389042097e3e28b89f4a801d` 满足发布脚本的 clean-worktree 约束。`scripts/publish-local-runtime.sh` 完成 frontend build、runtime sync、LaunchAgent restart、health checks 和 parity verifier，manifest 为 `/private/tmp/stock-dashboard-workingtree-gitpublish-lSN3TC/repo/output/releases/20260427T125715Z-8c90ef19255a/manifest.json`。
- 真实 runtime 验证必须跑两轮 refresh 才能证明结果进入持仓研究，而不是只看到当下 session 的内存态。第一轮 `phase5-daily-refresh --analysis-only` 创建 `sim-20260427125859-7994a7-model`，实时事件计数首次出现 `model_decision=1` 与 `order_filled=1`，holding-policy artifact 升到 `phase5-holding-policy-study:auto_model:2026-04-27:5portfolios`；第二轮 refresh 则把这条已成交 session 重建进 backtest，使 holding-policy 再升到 `phase5-holding-policy-study:auto_model:2026-04-27:6portfolios`，并首次得到非零 `mean_turnover=0.013889`、`mean_invested_ratio=0.029933`、`mean_active_position_count=0.166667` 与 `total_order_count=1`。这说明 runtime professionalism assessment 已从“空 session artifact”转成“真实交易样本仍然偏薄”，下一步 blocker 应该围绕更多 rebalance dates，而不是继续怀疑 refresh 链是否在运行。
- Chrome 复验确认 localhost `http://127.0.0.1:5173/` 与 canonical `https://hernando-zhao.cn/projects/ashare-dashboard/` 当前都显示 `最近刷新 04/27 21:01`，焦点为 `思源电气 · 002028.SZ`。因此这次结论是已发布、已刷新 runtime DB、已 browser-verified 的 live repair，不是 repo-only 结论。

[2026-04-27T20:28:55+08:00] Phase 5 holding-policy artifact fallback and parity-noise decision from local execution:
runtime `phase5_holding_policy_study` is no longer allowed to treat stale payload `backtest_artifact_id` values as the only source of truth for auto-model portfolio backtests. When the payload still points at the legacy `portfolio-backtest:portfolio-auto-live` id but the real runtime artifact has already moved to `portfolio-backtest:{portfolio_key}`, the study must fall back to the canonical portfolio-key artifact before declaring `missing_backtest_artifact`.

补充说明
- `src/ashare_evidence/phase2/holding_policy_study.py` 现已先尝试 payload-configured artifact id，再尝试 `portfolio-backtest:{portfolio_key}`，并只在两者都不存在时才保留 `missing_backtest_artifact`。`tests/test_phase5_holding_policy_study.py` 新增 runtime 风格回归，锁定“payload 仍旧指向 legacy id，但真实 artifact 已经写到 `sim-*` id”时必须正确纳入 holding-policy 聚合。
- 真实 runtime DB 先用旧代码复核过一遍，确认当时的 `0portfolios` 完全是误判：三个 auto-model portfolios 都带着 `portfolio_payload.backtest_artifact_id = portfolio-backtest:portfolio-auto-live`，但 backtest 文件实际上已经写成 `portfolio-backtest:sim-...-model.json`。发布修复后，先直接运行 `phase5-holding-policy-study` 即把 runtime `included_portfolio_count` 从 `0` 提升到 `2`；随后再跑 `phase5-daily-refresh --analysis-only`，最新 artifact 进一步收口为 `phase5-holding-policy-study:auto_model:2026-04-27:3portfolios`。
- 这次 runtime 结果同时确认：`included_portfolio_count` 已不再是主要 gate blocker，但 baseline 仍不能 promotion。当前 `gate_status` 仍是 `draft_gate_insufficient_evidence`，主要残余问题变成 `mean_rebalance_interval_days` 仍无样本、`mean_invested_ratio_floor` 与 `mean_active_position_count_floor` 仍持续触发 `portfolio_construction` redesign diagnostics。
- 发布链上，这轮还顺手关闭了之前已经暴露出来的 parity tooling 假阳性：`src/ashare_evidence/release_verifier.py` 现在把 `data_latency_seconds` 视为 runtime-only noise，`tests/test_release_verifier.py` 已补回归。此前 `/dashboard/operations` 的唯一 fingerprint diff 就是这一秒级漂移，不属于业务 payload 漂移，不应继续阻塞有效发布。
- 因主仓库仍是 dirty worktree，这轮 live publish 继续通过临时全工作树快照仓 `/private/tmp/stock-dashboard-workingtree-publish-iyg9zC/repo` 执行 `scripts/publish-local-runtime.sh`。自动 parity verifier、runtime sync、LaunchAgent restart 与 health check 全部通过，manifest 为 `/private/tmp/stock-dashboard-workingtree-publish-iyg9zC/repo/output/releases/20260427T122519Z-011e338c29f7/manifest.json`。随后 Safari 复验 localhost `http://127.0.0.1:5173/` 已显示 `最近刷新 04/27 20:27`、`大位科技 · 600589.SH`；canonical `https://hernando-zhao.cn/projects/ashare-dashboard/` 也刷新到 `最近刷新 04/27 20:28` 并与 localhost 对齐。

[2026-04-27T20:09:12+08:00] Phase 5 future-leak fix and canonical tunnel recovery decision from local execution:
Phase 5 historical validation and horizon studies are no longer allowed to reuse exit bars that occur after a recommendation's own `as_of_data_time`. This round fixed that leakage in the validation builder, rebuilt repo/runtime research state, and then reclosed live verification all the way through the canonical route.

补充说明
- `src/ashare_evidence/phase2/validation.py` 现已在 horizon-metric aggregation 时跳过 `exit_observed_at > recommendation.as_of_data_time` 的样本；`tests/test_analysis_pipeline.py` 新增回归，锁定较早 recommendation 不能再借用未来 exit bars 扩大样本。
- 这次修复后，repo 研究库重建出来的 history-mode `phase5-horizon-study` 明显改观：`40d` 的 `leader_count` 变成 `40`，而 `20d` 只剩 `5`、`10d` 为 `0`。这说明前一轮“广泛 split leadership”的相当一部分噪声来自历史未来泄漏，而不是主 horizon 已经真实收敛到 `20d`。
- focused regression `PYTHONPATH=src python3 -m unittest tests.test_analysis_pipeline tests.test_phase5_horizon_study` 已通过。由于主仓库仍是 dirty worktree，这次 live publish 继续通过临时干净快照仓 `/private/tmp/stock-dashboard-phase5-horizon-fix-dadXUY/repo` 执行 `scripts/publish-local-runtime.sh`；build、runtime sync、LaunchAgent restart 与 localhost health 通过，随后对 runtime DB 执行 `phase5-daily-refresh --analysis-only`。
- runtime 侧当前仍不能 promotion：holding-policy 继续停在 `phase5-holding-policy-study:auto_model:no_included_dates:0portfolios`，但 latest/history horizon artifact 已同时指向 `40d` 为当前 consensus front runner。
- 这轮 canonical 验收还暴露出另一层 live-delivery 风险：`com.codex.project-tunnel.ashare-dashboard` 已经退出，但远端 `sshd` 仍占着 tunnel 端口 `3101/4101`，导致 canonical 页面长期卡在旧的 `04/27 16:35/16:38` 状态。清掉远端僵尸转发并 `launchctl kickstart -k gui/$(id -u)/com.codex.project-tunnel.ashare-dashboard` 后，Safari canonical 恢复到 live runtime，当前显示 `思源电气 · 002028.SZ`、`最近分析 04/27 19:58`、`最近刷新 04/27 20:08`。

[2026-04-27T17:30:00+08:00] Canonical stock-dashboard handoff decision:
This repo now treats `PROJECT_STATUS.json` as the first current-state handoff source, `DECISIONS.md` as the durable research and rollout decision log, `PROCESS.md` as the reusable lessons log, and `PROJECT_PLAN.md` as the long-lived plan summary. Active contracts move under `docs/contracts/`, while audit and research history move under `docs/archive/`.

补充说明
- New sessions should no longer use root-level phase files as their default entrypoint.
- Repo path remains `~/codex/projects/stock_dashboard`; live runtime remains `~/codex/runtime/projects/ashare-dashboard`.

[2026-04-27T16:39:36+08:00] Phase 5 producer-contract watch-ceiling decision from local execution:
对 `missing_news_evidence` 的 producer contract 不再维持“任何 degrade flag 都直接强制 raw `risk_alert`”的旧行为。对于仅因缺少新增新闻证据而退化、但价格/其余结构仍偏正的 recommendation，当前批准的最窄替代方案是 `watch_ceiling_keep_penalty`：保留 `0.12` evidence-gap penalty，不放开为直接 `buy`，但移除 missing-news-only 场景下的硬性 `risk_alert` 覆盖，并把正向 case 的上限收口到 `watch`。

补充说明
- repo 研究库上的 `phase5-producer-contract-study` 已比较 `current_hard_block`、`remove_hard_override_keep_penalty`、`watch_ceiling_keep_penalty` 与 `remove_hard_override_and_penalty` 四个变体。当前研究结论选择 `watch_ceiling_keep_penalty`，因为它能恢复 deployable supply，同时避免把 `missing_news_evidence` 的记录直接放大成 `buy`。
- 代码现已落在 `src/ashare_evidence/signal_engine_parts/base.py` 与 `src/ashare_evidence/signal_engine_parts/recommendation.py`，并通过 `PYTHONPATH=src python3 -m unittest tests.test_phase5_producer_contract_study tests.test_dashboard_views tests.test_traceability tests.test_analysis_pipeline`（`48` tests）。
- 本轮 live publish 继续经由临时干净快照 repo `/private/tmp/stock-dashboard-producer-contract-publish-zmbkZM/repo` 执行 `scripts/publish-local-runtime.sh`。build、runtime sync、LaunchAgent restart、localhost health 与 served asset parity 均通过。自动 parity verifier 只在 `/dashboard/operations` 上报 `API fingerprint mismatch`，进一步核对后发现唯一归一化差异是 `data_latency_seconds`，不属于业务 contract 漂移。
- 随后已对 runtime DB 执行 `phase5-daily-refresh --analysis-only`，并在 Safari 对本地 `http://127.0.0.1:5173/` 与 canonical `https://hernando-zhao.cn/projects/ashare-dashboard/` 复看通过。真实 served 页面上的 `600522.SH` 现已显示 `模型原始方向：偏积极`、`对外表达：仅观察`，说明 producer change 已进入 live runtime，但 claim gate 仍继续阻止 promotion。

[2026-04-27T14:18:00+08:00] Runtime Phase 5 refresh scheduling decision from local execution:
runtime 服务库的 Phase 5 研究证据不得依赖 repo 数据目录随发布同步。由于 `scripts/publish-local-runtime.sh` 明确排除 `data/`，调度链路必须在 runtime DB 本地生成 horizon / holding-policy / validation 投影 artifact；只跑 `refresh-runtime-data` 不足以支撑“专业性”页面判断。

补充说明
- `scripts/run-scheduled-refresh.sh` 现已把工作日分析档 `08:10 / 16:20 / 19:20 / 21:15` 和周末 `09:30` 从 plain `refresh-runtime-data` 改为 `phase5-daily-refresh --analysis-only`；盘中轻量刷新仍保留 `refresh-runtime-data --ops-only`，避免把研究重建压到每次盘中轮询。
- 已对真实 runtime DB 执行 `phase5-daily-refresh --skip-simulation`，写出 `phase5-horizon-study:latest:active_watchlist:2026-04-24:3symbols`、`phase5-horizon-study:history:active_watchlist:2026-04-24:3symbols` 与 `phase5-holding-policy-study:auto_model:no_included_dates:0portfolios`。runtime recommendation 从缺少 metrics 的单日薄状态推进到 `8` 条 recommendation 且均带 `historical_validation.metrics`。
- 本轮 publish 通过临时干净快照完成 runtime sync、LaunchAgent restart 和 localhost health；自动 canonical verifier 仍因缺少 `ASHARE_CANONICAL_USERNAME` / `ASHARE_CANONICAL_PASSWORD` 中止。随后已用 Safari 手动复验本地 `http://127.0.0.1:5173/` 与 canonical `https://hernando-zhao.cn/projects/ashare-dashboard/`，页面显示 `最近刷新 04/27 11:51`，候选股已呈现 artifact-backed `research_candidate / observe_only` 语义和样本、RankIC、正超额摘要。
- 这项决定只关闭 runtime research-data drift 与调度缺口，不构成 promotion。holding-policy runtime study 仍是 `0portfolios`，horizon runtime 读数仍只有 `3` 个 symbols / `1` 个 as-of date，不能覆盖后续更广样本研究。

[2026-04-27T10:24:09+08:00] Same-as-of latest recommendation selection decision from local execution:
当同一只股票、同一个 `as_of_data_time` 同时存在多个 recommendation 版本时，所有“取最新 recommendation”与 replay/history collapse 路径都不再允许简单按 `generated_at desc` 取最后一条。若某个晚到 backfill 版本只是因为生成时间滞后而带上 `market_data_stale`，它不能继续机械覆盖同一 market snapshot 下更早生成、但仍有效的 non-stale 版本。

补充说明
- 本轮新增集中 helper `src/ashare_evidence/recommendation_selection.py`，并把 `services.py`、`dashboard.py`、`operations.py`、`watchlist.py`、`manual_research_workflow.py`、`simulation.py` 与 `phase2/replay.py` 的 latest-selection / history-collapse 逻辑统一改为：先按 `as_of_data_time` 分组，再在组内优先选择 non-`market_data_stale` 版本；只有同一 `as_of_data_time` 下所有版本都 stale 时，才退回到最新生成的 stale backfill。
- 这次决定只关闭“晚到 stale backfill 覆盖有效版本”的机械扭曲，不等于已经放宽 `missing_news_evidence => degraded => risk_alert` 这条 producer contract。换句话说，本轮先修的是 selection truth，而不是 recommendation producer 的 abstention policy。
- 回归已补到 `tests.test_traceability`、`tests.test_dashboard_views`、`tests.test_manual_research_workflow`、`tests.test_simulation_workspace` 与 `tests.test_analysis_pipeline`，并通过 `PYTHONPATH=src python3 -m unittest tests.test_traceability tests.test_dashboard_views tests.test_manual_research_workflow tests.test_simulation_workspace tests.test_analysis_pipeline`。
- 因主仓库仍是 dirty worktree，这次 live-facing publish 继续通过临时干净快照仓 `/private/tmp/stock-dashboard-latest-selection-Nq7j3S/repo` 执行 `scripts/publish-local-runtime.sh`。脚本完成了前端 build、runtime sync、LaunchAgent restart 与 localhost health check，但在 canonical verifier 处仍因缺少 `ASHARE_CANONICAL_USERNAME` / `ASHARE_CANONICAL_PASSWORD` 中止。随后已在 Safari 手动复验两条实际 served 路径：`http://127.0.0.1:5173/` 会先显示 skeleton，随后正常 hydrate 出首页与候选表；已登录的标准入口 `https://hernando-zhao.cn/projects/ashare-dashboard/` 刷新后也正常渲染，并更新到 `最近刷新 04/27 10:23`。这说明本轮 selection 修复已经进入真实运行时，只是自动 canonical parity 仍受凭据缺口限制。

[2026-04-27T01:05:00+08:00] Phase 5 holding-policy experiment evidence decision from local execution:
`Phase 5` 的 holding-policy redesign 已经从“只有 experiment menu”推进到“真实数据库可执行、可落 artifact 的 typed experiments”，但本轮真实运行同时确认：当前首要 blocker 不是 threshold/top-k 参数本身，而是 active recommendation coverage 太薄，导致组合长期接近空仓，现阶段 sweep 结果只能作为 coverage/deployment 诊断，不能被高置信度解读成正式 policy selection。

补充说明
- 本轮已修复真实运行暴露的 replay bug：`_replay_variant(...)` 在统计 `mean_rebalance_interval_days` 时原先错误使用 `zip(rebalance_days, rebalance_days[1:], strict=True)`，一旦真实数据出现至少两次调仓就会崩溃。现已改成相邻配对，并新增回归测试直接覆盖多次调仓路径。
- 两个 primary experiments 现已在真实库 `/Users/hernando_zhao/codex/projects/stock_dashboard/data/ashare_dashboard.db` 上写出 durable artifacts：`phase5-holding-policy-experiment:profitability_signal_threshold_sweep_v1:2023-04-12_to_2026-04-24:3symbols:3variants` 与 `phase5-holding-policy-experiment:construction_max_position_count_sweep_v1:2023-04-12_to_2026-04-24:5symbols:3variants`。这意味着 redesign research 不再只是 CLI 占位，而是已经有稳定的 artifact surface 可供后续比较。
- 当前 profitability sweep 的结论是 `baseline_still_best`，但不是因为 baseline 真的已经证明有效，而是三组变体都几乎没有足够部署去形成差异：baseline `annualized_excess_return_after_baseline_cost=-1.463036`、`positive_after_cost_day_ratio=0.493878`、`mean_turnover=0.000286`，同时 `rebalance_day_count=2`、`mean_active_position_count=0.009524`，说明真实窗口里大部分日期都没有足够 recommendation coverage 去形成持仓。
- 当前 construction sweep 虽然把默认推荐变体推到 `capacity_top3_weight33_conf0`，并相对 baseline 把 `mean_invested_ratio` 从 `0.00184` 提升到 `0.003128`、把 after-cost excess 从 `-1.492753` 改善到 `-1.490014`，但 `history_symbol_count` 仍只有 `2`，`mean_active_position_count` 仍是 `0.009524`。因此这不是“已经找到了更优正式仓位规则”，而是“集中持仓在几乎无覆盖的环境里略微提高了部署率”。
- 从这轮起，`Phase 5` redesign 主线应收口为：先把 primary experiments 保持为 `profitability_signal_threshold_sweep_v1` 与 `construction_max_position_count_sweep_v1`，但对它们的解释统一视为 coverage/deployment diagnostic，直到 real watchlist recommendation coverage、mean invested ratio、active position count 和可用历史样本明显改善之后，再讨论正式 policy selection 或 promotion。

[2026-04-27T00:38:03+08:00] Professionalism copy normalization decision from local execution:
用户可见的 recommendation explanation 不再允许直接暴露 placeholder headline、内部 degrade token 或内部实现语义。对外解释必须优先呈现“当前有哪些研究信号、这些信号为什么支持/削弱结论、什么时候应降级为谨慎或弃权”，而不是把 `用于汇总价格、事件与降级状态的融合层`、`missing_news_evidence`、`event_conflict_high`、`market_data_stale`、`Phase 2 规则基线` 这类系统中间态直接投到首页、候选卡或单票详情。

补充说明
- 这次决定对应 `docs/contracts/PHASE5_CREDIBILITY_REMEDIATION_PLAN.md` 的 P2.2/P2.3：不是把页面包装得更像投顾，而是把“研究解释”和“内部实现术语”彻底分离，同时保留现有 abstention / degradation 语义。
- producer 与 service hydration 两层都必须执行 display normalization。`signal_engine_parts/recommendation.py` 负责不再生成 placeholder/internal copy，`services.py` 负责在读取 legacy payload 时统一修复 `factor_cards / primary_drivers / supporting_context / conflicts`，避免旧 snapshot 再次把内部词汇带回真实页面。
- raw `degrade_flags` 仍可保留为 machine-facing compat 数据，但对外展示只能投射为用户可理解的研究语言；前端 sanitization 与 release verifier banned-term audit 也必须继续把这类 raw token 当成回归风险，而不是正常显示项。
- 这次修复已通过 `tests.test_dashboard_views` 与前端 build，并已通过临时干净快照仓 `/private/tmp/stock-dashboard-professionalism-snapshot-S61bDK/repo` 发布到 live runtime。发布脚本仍因缺少 `ASHARE_CANONICAL_USERNAME` / `ASHARE_CANONICAL_PASSWORD` 无法自动完成 canonical verifier，但随后已在 Safari 对真实入口 `https://hernando-zhao.cn/projects/ashare-dashboard/` 手动复看通过：live page 已不再出现 placeholder fusion 文案、raw degrade token 或 `Phase 2` 内部说明。

[2026-04-27T00:18:11+08:00] Public claim-gate decision from local execution:
从这轮起，用户可见的方向表达不再允许直接读取 raw recommendation direction；所有 `偏积极 / 偏谨慎 / 继续观察 / 风险提示` 一类结论，都必须先经过 artifact-backed claim gate。若 validation 仍未完成、样本量或 coverage 不足，或者缺少可回查的 validation artifact / manifest，则 public direction 必须自动降级，不能因为内部模型方向更乐观就对外放大。

补充说明
- backend recommendation contract 现已新增 `claim_gate`，至少冻结三档 user-facing 状态：`claim_ready`、`observe_only`、`insufficient_validation`。其中 `observe_only` 允许在已有最小 artifact-backed 观察基础时把乐观结论收口到 `watch`；`insufficient_validation` 则进一步把所有未达标表达压到 `risk_alert`。
- dashboard hero、候选列表排序、单票顶部标签和“当前建议摘要”都必须主读 `claim_gate.public_direction`，而不是 legacy/raw direction。raw direction 仅允许作为附属解释存在，例如“模型原始方向：偏谨慎”，不能继续充当对外主结论。
- 这次决定对应 `docs/contracts/PHASE5_CREDIBILITY_REMEDIATION_PLAN.md` 的 P1.3，属于“先冻结公开 claim ceiling，再继续做 P0/P1 实证重建”的产品门禁，而不是在研究尚未成熟时补强建议语气。
- 修复已通过 `tests.test_dashboard_views` 和前端 build 验证，并已发布到 live runtime。由于发布脚本的自动 canonical verifier 仍缺少 `ASHARE_CANONICAL_USERNAME` / `ASHARE_CANONICAL_PASSWORD`，最终验收改由 Safari 对真实入口 `https://hernando-zhao.cn/projects/ashare-dashboard/` 手动完成；当前真实页面已可见 `验证不足` 告警、claim-gate 降级文案，以及单票摘要里的 `对外表达` 字段。

[2026-04-26T22:25:00+08:00] Manual-research stale-status hydration decision from local execution:
manual research request list 的 stale 判定必须和 dashboard projection 复用同一套 hydrated validation context，不能再直接依赖 raw recommendation payload 里的 `historical_validation` 空壳字段。对当前 runtime DB，这类 raw shell 可能为 `null`，但 artifact-backed 当前 validation 实际仍存在；若仍拿空壳做对比，就会把已完成请求误报成 `结果过期`。

补充说明
- `manual_research_workflow.py` 现已通过 `_current_recommendation_context(...)` 在 `_serialize_request(...)` 中调用 `services._build_historical_validation(...)`，先把当前 recommendation 的 validation artifact / manifest 从 artifact store 水合出来，再交给 `build_manual_review_source_packet(...)`、`manual_research_stale_reason(...)` 与 `build_manual_llm_review_projection(...)` 共同使用。
- 这次修复的核心不是放宽 stale 规则，而是让 request list、dashboard 和 recommendation serialization 对“当前 validation 是什么”达成一致。真正的 artifact drift 仍然会被识别；被关闭的是“raw payload 没水合，列表接口把空壳误当当前真相”的假 stale。
- 回归测试 `tests.test_manual_research_workflow.test_completed_request_stays_current_when_validation_is_hydrated_from_artifacts` 已补齐，并与 `tests.test_dashboard_views` 一起通过。修复已经发布到 live runtime，manifest 为 `/private/tmp/stock-dashboard-stale-fix-1guY22/repo/output/releases/20260426T141204Z-00a38a8230d8/manifest.json`；虽然发布脚本因缺少 canonical verifier 凭据没有自动跑完最后一步，但 Safari 强制刷新标准入口 `https://hernando-zhao.cn/projects/ashare-dashboard/` 后，`600589.SH` 的人工研究状态已回到 `已完成`，证明这次 stale 结果并非真实 artifact drift。

[2026-04-26T19:42:00+08:00] Builtin Codex manual-research execution decision from local execution:
manual research 的默认 builtin 路径不再允许停留在“只创建 queued request”的旧 contract。只要本机存在可用 Codex CLI，就应把无 Key 的默认动作视为“立即起本机 Codex 进程并用 `gpt-5.5` 执行人工研究”，而不是要求用户先去配置外部 API Key 或再到治理面板继续执行。

补充说明
- 本机 PATH 上的 Codex CLI 已在本轮主动升级到 `0.125.0`，并通过实际 `codex exec -m gpt-5.5` 调用确认可用。旧的 `0.120.0` 不支持当前需要的模型选择，因此不能继续作为 builtin executor 的隐式前提。
- `runtime_config.py` 现已把 builtin executor 收口为双通道解析：优先检测本机 `codex` CLI 或 App bundle 内置 binary 并使用 `transport_kind=codex_cli`、`base_url=codex-cli://local`、`model_name=gpt-5.5`；只有在显式切回 `openai_api` 或缺少本机 Codex 时，才继续依赖传统 API-key/base-url 组合。
- `manual_research_workflow.py` 现已把 builtin execute 真正接到 `codex exec`，并在默认 UI submit 路径上直接 create + execute。这样 `builtin_gpt` 不再只是一个“留给以后接 server executor”的名义队列，而是本机可落地的默认研究执行器。若本机 Codex 和 API 凭据都不可用，系统才会回退到 unavailable note，而不是假装请求正在正常排队。

[2026-04-26T19:12:00+08:00] Standard-entry latest-release decision from local execution:
`?cb=...` 不应成为 ashare dashboard 的正常访问方式。它只能作为缓存诊断手段；标准入口本身必须在正常刷新、切回标签页和重新聚焦时尽量拿到最新发布。

补充说明
- `frontend/index.html` 现已加入 `Cache-Control: no-cache, no-store, must-revalidate`、`Pragma: no-cache` 和 `Expires: 0` meta，明确把入口 HTML 当成“可随发布漂移”的资源，而不是长期缓存对象。
- `frontend/src/main.tsx` 现已在应用启动后以 `cache: "no-store"` 拉取当前 URL 的最新 HTML，并比较最新 `assets/index-*.js` 与当前运行 bundle；若发现自己跑的是旧 build，就自动 reload。相同逻辑还会在窗口聚焦、标签页重新可见和每 60 秒轮询时再次执行。
- 从这轮起，canonical 验收应优先验证无 query 参数的标准入口；`cb` 仅保留给“怀疑代理/浏览器缓存链路异常”时的临时排查。本轮发布 manifest 为 `/private/tmp/stock-dashboard-publish-2NogWR/repo/output/releases/20260426T110821Z-f84d42681210/manifest.json`，Safari 已直接打开 `https://hernando-zhao.cn/projects/ashare-dashboard/` 并看到最新页面。

[2026-04-26T18:14:13+08:00] Operations focus-workspace behavior and manual-research access decision from local execution:
这轮 `运营复盘` 的四个可见异常里，有三类现在已经被收口成明确 contract：焦点 K 线不再只依赖盘中 `5min` 行情、运营复盘点行切换焦点不再走整页选股刷新、默认股票池语义明确固定为“当前模拟股票池默认跟随 active watchlist”，而不是“永远展示全市场或所有历史候选”。同时，`追问与模拟` 初始触发不再被 operator-only 卡住，写权限用户已经可以创建并执行 manual research request；operator-only 只保留在人工完成/失败/retry 这类治理终态动作。

补充说明
- `simulation.py` 现在把 `watch_symbols_scope` 正式区分为 `active_watchlist_default` 与 `custom`。默认 scope 下，simulation session 会自动跟随当前 active watchlist 增减股票；只有当用户显式改过模拟配置后，才保留 custom pool。`运营复盘` 当前表格展示的是“当前模拟股票池”，不是无限制的全量 universe。
- 焦点 K 线的取数 contract 已补上 daily fallback：如果当前 symbol 没有可用的 `5min` bars，就回退到 `1d` bars，而不是直接把焦点面板显示成空图。这解决的是“当前界面没有 K 线”的产品问题，不改变 intraday-first 的研究语义。
- `frontend/src/App.tsx` 里的运营复盘焦点切换现在走 `api.updateSimulationConfig(... focus_symbol ...) -> applySimulationWorkspace(...)`，焦点变化只更新 simulation workspace 自身，不再触发 `selectedSymbol` 级别的整页 stock-detail reload。表格操作按钮也会显式 `stopPropagation()`，避免点击动作顺带触发行级焦点切换。
- `api.py` 已把 manual research 的 create / initial execute 权限从 operator-only 放宽为 beta write access；但 `complete / fail / retry` 仍保持 operator-only，因为这些动作会改写治理终态与 artifact 生命周期。

[2026-04-26T17:36:02+08:00] Live operations track-table containment publish and verifier-noise decision from local execution:
运营复盘双轨模拟台里“轨道内表格超出”的修复这次才算真正完成，因为它已经不只是本地 build 通过，而是成功发布到 canonical 入口并做了登录后的远端复看。

补充说明
- 前端修复保持为轨道卡片 containment + 更早堆叠的双列布局：`TrackHoldingsTable` 继续使用 `track-holdings-shell` 与 `scroll={{ x: "max-content" }}`，轨道列布局已收紧到 `xs={24} xxl={12}`，避免 `xl` 宽度下双轨卡片仍并排压缩造成表格区域过窄。
- 发布阶段发现 release verifier 会把 runtime-only 性能浮动误判为 canonical API drift，因此 `src/ashare_evidence/release_verifier.py` 现已在 fingerprint normalization 中仅忽略 `刷新与性能预算` gate 的 `launch_gates[*].current_value` 和 `performance_thresholds[*].observed`。这不会放过真实 contract 漂移，但能避免性能数字抖动把 live publish 错误拦下。
- 这次发布通过临时干净 repo 快照执行 `scripts/publish-local-runtime.sh`，生成 manifest `/private/tmp/stock-dashboard-publish-rsync-WyJZXt/repo/output/releases/20260426T093041Z-0f8fe79d90f6/manifest.json`。随后在 Safari 打开 `https://hernando-zhao.cn/projects/ashare-dashboard/?cb=20260426-1738` 完成登录后复看，`运营复盘` 下的 `用户轨道 / 模型轨道` 表格当前都保持在卡片边界内，未再看到旧的整页横向撑开问题。

[2026-04-26T16:04:41+08:00] Phase 5 holding-policy redesign experiment menu decision from local execution:
`Phase 5` 的 holding-policy artifact 现在不只会说“该改收益层还是持仓构造层”，还会直接给出当前优先应跑的 redesign experiment candidates。这样下一步研究不再只是抽象地“做 redesign”，而是已经收口到一组可回查的 draft experiment menu。

补充说明
- `phase5_holding_policy_study` 现已继续输出 `redesign_experiment_candidates / redesign_primary_experiment_ids`，并通过 CLI 与 operations summary 同步暴露 primary experiment ids。当前 redesign diagnostic context 版本已升级到 `phase5-holding-policy-redesign-diagnostics-draft-v2`，因为 context 本体现在同时冻结 signal rules 和 draft experiment menu。
- 当前 experiment menu 按 focus area 拆成两组 research candidates。`after_cost_profitability` 对应 `profitability_signal_threshold_sweep_v1` 与 `profitability_rebalance_hold_band_v1`；`portfolio_construction` 对应 `construction_max_position_count_sweep_v1` 与 `construction_deployment_floor_fallback_v1`。这些都是 Phase 5 的研究菜单，不是已批准产品策略。
- 对当前 fixture-backed study / CLI / operations summary，默认 primary experiment 已明确落成 `profitability_signal_threshold_sweep_v1`；对真实 snapshot `phase5-holding-policy-study:auto_model:2026-04-24:3portfolios`，由于 redesign focus 已包含 `after_cost_profitability + portfolio_construction`，后续主线应优先从 `profitability_signal_threshold_sweep_v1` 与 `construction_max_position_count_sweep_v1` 这两个 primary experiments 开始做对照，而不是继续停留在只描述 focus area 的阶段。

[2026-04-26T15:55:10+08:00] Phase 5 holding-policy redesign diagnostic readout decision from local execution:
`Phase 5` 的 holding-policy artifact 现在不只会给出 “该不该 redesign” 的治理结论，也会把 redesign 的结构化原因和焦点领域写出来。当前 default action 仍是 `prioritize_policy_redesign`，但下一步不再需要从几项原始指标里重新拼凑“到底该改哪一层”。

补充说明
- `phase5_holding_policy_study` 现已新增 `redesign_status / redesign_note / redesign_diagnostics / redesign_triggered_signal_ids / redesign_focus_areas / redesign_context`，并通过 CLI 与 operations summary 同步暴露。当前 redesign diagnostic context version 为 `phase5-holding-policy-redesign-diagnostics-draft-v1`。
- redesign diagnostics 会把收益侧 blocker 和持仓构造侧信号分开表达。对真实 snapshot `phase5-holding-policy-study:auto_model:2026-04-24:3portfolios`，当前默认研究结论不再只是“after-cost excess 为负”，还明确指向两类 redesign focus：`after_cost_profitability` 与 `portfolio_construction`；后者来自当前 real sample 的 `mean_invested_ratio=0.075433` 与 `mean_active_position_count=1.0`，说明 baseline 的资金部署和持仓覆盖都过薄。
- 这意味着后续 Phase 5 主线已经从“继续 formalize gate/governance”收口到“围绕 after-cost profitability 和 portfolio construction 做 policy redesign research”。如果未来 artifact 改善，应该比较 redesign 前后的这些结构化 signal，而不是重新回到纯文本判断。

[2026-04-26T15:37:06+08:00] Phase 5 holding-policy governance readout decision from local execution:
`Phase 5` 的 holding-policy artifact 现在不只会说“gate 有没有过”，还会给出当前默认治理动作。对当前 real-db snapshot，系统已明确把默认结论写成“继续 non-promotion，并优先进入 policy redesign”，不再需要从 `note` 文本里人工猜测下一步。

补充说明
- `phase5_holding_policy_study` 现已新增 `governance_status / governance_action / governance_note / redesign_trigger_gate_ids / governance_context`，并通过 CLI 与 operations summary 同步暴露。当前治理 context 版本是 `phase5-holding-policy-governance-draft-v1`，作用是把 gate blocker 翻译成 Phase 5 默认处理动作，而不是自动批准 promotion。
- 对真实 snapshot `phase5-holding-policy-study:auto_model:2026-04-24:3portfolios`，当前默认治理结论已收口为 `governance_status=maintain_non_promotion_prioritize_policy_redesign`、`governance_action=prioritize_policy_redesign`。触发这一结论的 redesign signal 仍是已知的收益侧 blocker：`after_cost_excess_non_negative` 与 `positive_after_cost_portfolio_ratio`。
- 这意味着后续 Phase 5 policy work 的默认主线不再是“继续讨论该不该 non-promotion”，因为当前代码化治理结论已经是 non-promotion；真正还要继续做的是 redesign research 本体，或在未来出现更强真实证据后再重新评估 gate / governance readout。

[2026-04-26T15:28:05+08:00] Phase 5 holding-policy draft promotion gate and refresh fallback decision from local execution:
`Phase 5` 的 holding-policy 研究现在不再只是“真实 snapshot 不支持 promotion”这一句口头结论，而是已经把 draft promotion gate readout 写进 durable artifact / CLI / operations。当前 real-db snapshot 仍保持 `research_candidate_only`，并且是被明确 gate blocker 阻断，而不是简单“阈值待定”。

补充说明
- `phase5_holding_policy_study` 现在会输出 `gate_status / failing_gate_ids / incomplete_gate_ids / gate_checks / gate_context`。当前 draft gate version 为 `phase5-holding-policy-promotion-gate-draft-v1`，guardrails 先锁定 `min_included_portfolio_count=3`、`after-cost excess >= 0`、`positive-after-cost portfolio ratio >= 0.5`、`mean_turnover <= 0.35`、`mean_rebalance_interval_days >= 5`，但这仍只是研究诊断，不是 operator 已批准的自动 promotion 规则。
- 对真实 snapshot `phase5-holding-policy-study:auto_model:2026-04-24:3portfolios`，当前 `gate_status=draft_gate_blocked`，核心 blocker 至少包括 `after_cost_excess_non_negative` 与 `positive_after_cost_portfolio_ratio`。因此后续 Phase 5 工作应从“是否继续 non-promotion / redesign”出发，而不是默认只需再补一段 gate 文案。
- 同轮还补了 runtime refresh 的稳健性缺口：`analysis_pipeline` 对 Eastmoney research metadata 的 AKShare 抓取现在会注入默认 requests timeout，并在失败时降级为空 metadata，不再让 `phase5-daily-refresh` 或 `refresh-runtime-data` 因外部研究报告元数据抓取卡住。

[2026-04-26T15:05:26+08:00] Phase 5 real holding-policy evidence non-promotion decision from local execution:
`Phase 5` 的 simulation holding-policy 研究现在不只是“artifact 化已经接通”，而是已经在真实数据库上跑出最新 snapshot。当前 real artifact 明确不足以支持 promotion：baseline 继续保持 `research_candidate_only`，后续 gate 设计必须从“为什么当前策略不该晋级”出发，而不是默认它只差一组阈值文案。

补充说明
- 已在真实库上执行 `PYTHONPATH=src python3 -m ashare_evidence.cli phase5-daily-refresh --database-url sqlite:///data/ashare_dashboard.db --analysis-only --skip-simulation`，并生成 `phase5-holding-policy-study:auto_model:2026-04-24:3portfolios`。`operations` 总览现已直接显示这份 artifact，`artifact_available=true`，因此 Phase 5 policy evidence 不再只是测试夹具或临时 CLI 输出。
- 当前 snapshot 纳入 `3` 个 portfolio、`0` 个排除样本；`mean_turnover=0.25`、`mean_rebalance_interval_days=10.5`、`mean_orders_per_rebalance_day=7.0`。但收益侧证据明显不足：`mean_annualized_excess_return=-12.848967`、`mean_annualized_excess_return_after_baseline_cost=-12.849842`，且 `positive_after_baseline_cost_portfolio_count=0`。
- 因此本轮批准结论不是“先把 simulation policy 提升到 approved_for_product，再补治理细节”，而是继续把它视为 simulation-only `research_candidate`。后续工作应优先定义 promotion gate 的否决条件、判断是否需要 policy redesign，并持续禁止任何向真实交易或更强产品承诺的升级。

[2026-04-26T14:59:39+08:00] Phase 5 holding-policy study artifactization decision from local execution:
`Phase 5` 的 simulation holding-policy 研究现在不再只是现场聚合结果，而是进入 typed durable artifact、daily refresh 和 operations 治理总览。当前 baseline 仍是 simulation-only 的 `phase5_simulation_topk_equal_weight_v1`，批准层级继续保持 `research_candidate_only`，但换手/成本/持仓稳定性证据已经可以被稳定回查。

补充说明
- `src/ashare_evidence/phase2/holding_policy_study.py` 现已新增统一研究入口，会读取 auto-model 组合及其 `portfolio_backtest` artifact，输出 `summary / cost_sensitivity / holding_stability / decision / portfolios`。研究纳入条件与产品验证状态已显式解耦：即使组合 backtest 仍处于 `pending_rebuild`，只要 benchmark 定义匹配当前 Phase 5 主研究 benchmark，且存在 turnover 与 annualized excess return，就仍可纳入 holding-policy evidence。
- `src/ashare_evidence/cli.py` 新增 `python3 -m ashare_evidence.cli phase5-holding-policy-study`，并把该 artifact 写入接到了 `phase5-daily-refresh`；`operations.build_operations_dashboard()` 也直接暴露 `approval_state / included_portfolio_count / mean_turnover / mean_annualized_excess_return_after_baseline_cost / artifact_id / artifact_available`，后续不需要临时读代码才能知道 simulation policy 研究是否已有 durable snapshot。
- 这次收口关闭的是“holding-policy evidence 只能临时计算”的缺口，不是 `F004` 本身。后续还需要继续用真实日更 artifact 定义 promotion gate，包括 turnover 上限、成本拖累阈值、持仓稳定性底线，以及何时才能从 `research_candidate` 升级。

[2026-04-26T14:32:06+08:00] Phase 5 simulation holding-policy contract alignment decision from local execution:
`Phase 5` 的 simulation holding policy 现已明确从“withheld quantity preview”升级为可执行的 research-candidate contract，但执行范围仍严格锁定在 web 模拟盘。当前正式基线是 `phase5_simulation_topk_equal_weight_v1`，动作语义为 `delta_to_constrained_target_weight_portfolio`，数量语义为 `board_lot_delta_to_target_weight`；旧的 `withheld_until_execution_policy_is_approved` 只代表 `2026-04-25` maintenance honesty 收口，不再代表当前 Phase 5 合同状态。

补充说明
- 当前代码、前端和测试已经一致落在同一条 contract 上：`simulation.py` 会按最多 `5` 只、单票上限 `20%`、允许留现金和 `100` 股整手约束生成 target-weight delta，并且在用户启用 `auto_execute_model` 后只对 simulation track 自动写入 paper fills，不扩展到任何真实下单或真实交易路由。
- `phase2/phase5_contract.py` 现已新增共享的 simulation policy / auto-execution context helper，`simulation.py` 与 `operations.py` 不再各自手写 `policy_status / policy_type / policy_note / action_definition / quantity_definition`，避免下一次再出现“代码已经前进到 target-weight contract，durable docs 却还停留在 withheld preview” 的分叉。
- 这次对齐不代表 `F004` 已关闭。当前批准层级仍然是 `research_candidate`：后续还需要继续补 simulation-only 策略的换手、成本、持仓稳定性和晋级门槛研究，再决定是否能升到 `approved_for_product`。

[2026-04-26T14:20:00+08:00] Phase 5 expanding-watchlist benchmark membership decision from local execution:
`Phase 5` 的 active-watchlist 主 benchmark 现已明确锁定为 `expanding_active_watchlist_join_date_forward_only`。研究验证仍允许单票使用 full history，但 active-watchlist 等权 proxy 不再把后来加入自选池的股票 retroactively 回填到更早日期。

补充说明
- `src/ashare_evidence/phase2/rebuild.py` 不再用“当前 active scope 静态全样本”构造 market proxy，而是先读取 `WatchlistEntry.created_at` 生成 membership start dates，再用 expanding equal-weight proxy 逐日扩展成分；若当前 refresh 仅临时把 symbol 纳入 active scope、却还没有正式 watchlist entry，则允许回退到该 symbol 最早可用行情日，避免单次 refresh 直接丢失 benchmark 覆盖。
- validation manifest、replay artifact 和 portfolio backtest manifest 现已统一写入 `primary_research_benchmark_membership_rule`、`defaulted_symbol_count`、`defaulted_symbols`、`min_constituent_count`、`max_constituent_count`、`first_active_day` 与 `last_active_day`，后续任何 Phase 5 benchmark 解释都必须以这些 artifact context 为准，而不是再靠口头假设说明。
- `rebuild_phase2_research_state()` 现已在读取 watchlist membership 前先 `session.flush()`。本仓库关闭了 ORM `autoflush`，因此如果不显式 flush，同一事务里刚写入的 watchlist 变更会被 benchmark rebuild 漏读，导致错误回退到 earliest-price fallback。

[2026-04-26T13:26:10+08:00] Phase 5 release parity and anti-regression publish decision from local execution:
`stock_dashboard` 的 live publish 现在不再允许“本地看起来改好了”就算完成。正式发布必须同时满足 clean-tree source、runtime commit 绑定、repo/runtime/canonical 三方 parity 验证，以及可回查的 release manifest。

补充说明
- `scripts/publish-local-runtime.sh` 现在会先拒绝 dirty worktree；只有从已提交的明确 commit 出发，才允许 build、rsync、restart 和后续校验，避免未提交修复再次被 `chore(sync)` 或模糊 baseline 覆盖。
- 新增 `src/ashare_evidence/release_verifier.py` 作为发布后 verifier：它会比较 repo build、runtime dist、localhost served frontend 与 canonical authenticated route 的 asset hash，并对 `/dashboard/operations`、`/settings/runtime`、`/dashboard/candidates` 生成去噪后的 API fingerprint。
- release verifier 会对运营复盘的 user-visible text projection 做专项审计，要求 `用户轨道`、`模型轨道` 必须存在，并阻断 `运营复盘口径仍在迁移`、`Phase 5 baseline`、`research contract`、`pending_rebuild`、`manifest`、`verified` 等历史回退词重新进入 live UI。
- 每次成功发布都会在 `output/releases/<release-id>/manifest.json` 生成 release manifest，并刷新 `output/releases/latest-successful.json`；manifest 同时记录上一个成功版本的 manifest path 与 commit SHA，后续回滚只能回到这份已证明成功的 release，而不是任意工作树状态。

[2026-04-26T01:55:00+08:00] Runtime publish enforcement decision from local execution:
`stock_dashboard` 的 runtime publish 约束不再只依赖控制平面的 task/worktree 自动发布。直接在正式 repo 中工作的 Codex 会话，同样必须把 repo 变更同步到 runtime 并完成本机健康校验，才能把 live-facing 修复视为完成。

补充说明
- 已定位到控制平面的 `publish-runtime.js` 自动 publish 依赖 `task.worktreePath` 与 `task.branchName`，因此它天然只覆盖 worker/task 路径，不覆盖所有交互式 Codex 会话。
- 本项目新增 `AGENTS.md` 与 `scripts/publish-local-runtime.sh`，把 “repo build -> rsync runtime -> kickstart backend/frontend -> check 8000/5173 -> compare served asset names with repo build” 固化成项目内强规则和单命令发布路径。
- 后续凡是声明“前端已验证”“live service 已修复”的会话，都必须以这条脚本成功作为验收依据，而不是只停在 repo build、单元测试或源码 diff。

[2026-04-26T05:05:00+08:00] Phase 5 daily refresh automation decision from local execution:
`Phase 5` 的日更研究链路不再批准继续依赖手动触发。runtime refresh、latest/history horizon-study artifact 写入，以及“是否出现新增 evidence”的比较，现在统一收口到单命令 workflow，并挂上工作日收盘后的自动任务。

补充说明
- `src/ashare_evidence/cli.py` 新增 `python3 -m ashare_evidence.cli phase5-daily-refresh`，它会先执行 runtime refresh，再连续写入 latest/history 两份 `phase5-horizon-study` artifact，输出当前 `approval_state`、`candidate_frontier`、`lagging_horizons`、`included_record_count`、`included_as_of_date_count` 与 artifact 元数据。
- Codex automation `stock-dashboard-phase5-daily-refresh` 已创建并启用，计划在工作日收盘后自动运行这条 workflow。后续这个研究更新属于系统自执行职责，而不是 operator 记忆性操作。
- `tests/test_cli_runtime_refresh.py` 也已收口到真实 artifact 行为：`phase5-daily-refresh` 的回归现在从 CLI 输出读取实际 artifact ID，再回查 typed store，避免把 refresh 后产生的新 snapshot 错误断言成固定的空样本 ID。

[2026-04-26T04:00:00+08:00] Phase 5 horizon-study artifactization and operations visibility decision from local execution:
`Phase 5` 的 horizon-selection 研究现在不再只是“能现场聚合”，而是进入了 durable artifact 和治理总览。当前 real DB 基线已经落成 latest/history 两份 typed snapshot，operations 也会直接展示当前主 horizon 仍卡在 `split_leadership`。

补充说明
- `phase5-horizon-study` 新增 `--write-artifact`，会把当前聚合结果落到 `data/artifacts/studies/` 下的 `phase5_horizon_study` artifact；artifact ID 按 `mode + scope + included as-of dates + symbol_count` 稳定生成，同一批 evidence rerun 会复用同一 ID，而不会伪装成“新增研究结论”。
- 当前 real DB 已写入两份基线 snapshot：`phase5-horizon-study:latest:active_watchlist:2026-04-24:3symbols` 与 `phase5-horizon-study:history:active_watchlist:2026-04-07_to_2026-04-24:3symbols`。它们都继续确认 `40d` 劣后、`10d vs 20d` split、`primary_horizon_status = pending_phase5_selection`。
- `operations.build_operations_dashboard()` 的 `overview.research_validation.phase5_horizon_selection` 现已直接暴露 `approval_state / candidate_frontier / lagging_horizons / included_record_count / artifact_id / artifact_available`。这意味着后续 operator 不需要先手跑 CLI，治理总览就能看到“当前主 horizon 研究是否已有 artifact baseline、是否仍未收敛”。

[2026-04-26T03:00:00+08:00] Phase 5 horizon-study aggregation decision from local execution:
`Phase 5` 的主 horizon 讨论不再依赖单票 payload 或临时 SQL。当前 active watchlist 已新增统一聚合 study 入口，并在真实库上再次确认：`40d` 继续视为劣后候选，`10d` 与 `20d` 仍保持 split leadership，因此主 horizon 继续挂在 `pending_phase5_selection`。

补充说明
- 新增 `python3 -m ashare_evidence.cli phase5-horizon-study`，默认读取 active watchlist 的最新 recommendation；传入 `--include-history` 时，则按 `symbol + as_of_day` 聚合历史 snapshot。study 只纳入满足 `phase5-validation-policy-contract-v1 + phase2_equal_weight_market_proxy + full_baseline + comparison_ready` 的记录，避免把 migration 或半截样本混入主 horizon 讨论。
- 在当前 real DB 上，latest-only 聚合结果为：`10d` leader `2/3`，`20d` leader `1/3`，`40d` leader `0/3`；`10d vs 20d` 的平均净超额收益差仅约 `0.000311`，而 `10d/20d` 对 `40d` 都是 `3/3` pairwise 胜出。
- history mode 目前覆盖 `2026-04-07`、`2026-04-14`、`2026-04-24` 三个 as-of 日期，共 `9` 条纳入记录；symbol-level leader 仍保持稳定，但横截面 split 没有收敛。因此批准结论不变：把 `phase5-horizon-study` 作为日后每个新交易日 refresh 后的标准研究检查点，在拿到更多新 as-of 日期前，不批准 `10d` 或 `20d` 成为正式主 horizon。

[2026-04-26T02:36:00+08:00] Phase 5 real-run benchmark scope and horizon-selection decision from local execution:
`Phase 5` 的 real validation rebuild 现已确认一个入口级 scope bug，并基于修正后的 real run 得出当前 horizon 研究结论：`40d` 可以先降为劣后候选，但 `10d` 与 `20d` 还不能在当前 active watchlist 样本上决出正式主 horizon。

补充说明
- `refresh_real_analysis()` 之前只按当前 symbol 调 `rebuild_phase2_research_state(session, symbols={...})`，会让 validation builder 在 real refresh 场景下错误退回 `phase2_single_symbol_absolute_return_fallback`。该入口现已改为显式传入 `active_watchlist_symbols(session) + 当前 symbol`，`phase2/rebuild.py` 也已区分 update scope 与 proxy scope，确保单 symbol rebuild 仍按 active watchlist equal-weight proxy 构造 Phase 5 benchmark。
- 修正后重新对 real DB 执行 `refresh-runtime-data --skip-simulation`，三只 active watchlist symbol 均达到 `full_baseline` coverage：`available_observation_count=683`、`evaluation_observation_count=83`、`window_count=24`。`historical_validation.benchmark_definition` 已恢复为 `phase2_equal_weight_market_proxy`，`candidate_horizon_comparison.selection_readiness` 也已全部回到 `comparison_ready`。
- 当前真实样本中，`40d` 在三只股票上都明显落后；`10d` 在 `002028.SZ` 与 `002270.SZ` 上领先，`20d` 在 `600522.SH` 上领先。批准结论因此是：继续维持 `primary_horizon_status = pending_phase5_selection`，暂不把 `10d` 或 `20d` 升为产品主 horizon；下一步先在更广或更多次 real run 上继续比较 `10d vs 20d`，再进入正式 selection。

[2026-04-26T02:10:00+08:00] Phase 5 walk-forward coverage and candidate-horizon comparison decision from local execution:
`Phase 5` 的 validation rebuild 现在不再只是冻结合同文案，而是开始把真实历史覆盖要求和 artifact-backed horizon comparison 写进 refresh/rebuild 主路径。

补充说明
- `phase5_contract` 现已新增 `required_history` 事实源，明确 `required_observation_count=660`、`required_bar_count=740` 和 `market_history_lookback_days=1110`；`analysis_pipeline.py` 的日线抓取窗口已切到该基线，避免 refresh 还停留在无法支撑 `480/120/60` 的 `180` 天短样本。
- `phase2/validation.py` 现在按 `480/120/60` 基线构建真实 walk-forward split coverage：样本足够时写出 daily rolling `split_plan`，metrics 只使用 warmup 后的 test-side observation；样本不足时显式标记 `insufficient_history`，而不是继续输出伪 full-baseline artifact。
- recommendation `historical_validation.metrics` 现已附带 `walk_forward` coverage 摘要与 `candidate_horizon_comparison`。其中 research leader 只用于 supporting evidence，`primary_horizon_status` 仍保持 `pending_phase5_selection`，不能被误读为已批准产品周期。

[2026-04-26T01:15:00+08:00] Phase 5 research contract freeze decision from local execution:
`Phase 5 - Real Validation Rebuild and Model Portfolio Policy Research` 的研究合同现已从 handoff 摘要提升为专项 durable spec，并同步收口到共享代码常量。后续 validation、replay、portfolio 和 simulation 不应再各自手写 Phase 5 语义。

补充说明
- 新增 `docs/contracts/PHASE5_RESEARCH_CONTRACT.md` 作为当前 phase 的专项事实源，明确锁定研究验证层与产品跟踪层的分离语义、双层 benchmark、候选 horizon、rolling split baseline、LLM scope 与 simulation auto-execution boundary。
- artifact manifest 现已新增 `research_contract` 上下文字段，用于把 `contract_version`、`candidate_label_horizons`、`rolling_split_baseline`、`llm_analysis_scope` 和 `simulation_execution_scope` 与具体 validation/backtest 产物绑定，避免 Phase 5 研究边界只剩零散文案。
- `simulation.py`、`operations.py`、`phase2/validation.py`、`phase2/replay.py` 与 `phase2/portfolio.py` 现在统一消费共享 `phase5_contract` 常量；若未来修改 benchmark、horizon、split 或 execution boundary，必须先更新专项合同与决策日志，再改代码默认值。

[2026-04-26T00:20:00+08:00] Phase 5 launch decision from local operator + local execution:
项目正式开启 `Phase 5 - Real Validation Rebuild and Model Portfolio Policy Research`。本 phase 直接承接尚未关闭的 `F001` 与 `F004`，目标不是继续做迁移态诚实化，而是把真实滚动验证和正式模型组合建议的研究合同锁定下来。

补充说明
- 一期研究 universe 继续使用当前自选池，但必须显式区分“研究验证层”和“产品跟踪层”。研究验证层允许每只股票使用其完整历史做 rolling validation，只要每个历史时点都严格使用当时可得数据即可；产品跟踪层里的自选池表现、加入后命中率和加入后建议质量，则只能从加入自选池的日期开始计算，不能 retroactive 回填，否则会夸大用户真实可见的历史跟踪成绩。
- benchmark 在本 phase 采用双层语义：研究/策略主 benchmark 先使用 `active_watchlist_equal_weight_proxy`，确保模型评估基于它真实可选的机会集；同时保留 `CSI300` 作为对外解释用的市场参考线，而不是主优化目标。
- label / horizon 研究先从 `10 / 20 / 40` 个交易日的候选窗口开始，但它们只是研究候选集，不是产品承诺。主 horizon 必须由 rolling validation 结果决定，而不是沿用历史一期文案。
- LLM 在本 phase 明确收口为“手动触发的附加分析功能”，不再作为主评分因子。当前推荐做法是由前端在用户点击 LLM 分析时，把当前股票、候选理由、证据摘要、风险标记、验证摘要和近期上下文打包后发给大模型，分析过程默认保持手动触发。
- `F004` 的产品目标已明确为“真自动持仓建议”。在 web 模拟盘里，系统被批准自动生成调仓建议并自动执行模拟成交，不需要人工逐笔确认；但这项权限只限模拟盘，不批准真实下单、真实交易路由或任何实盘自动执行。
- model portfolio policy research 的默认起点采用受约束 TopK 组合基线：周频调仓、最多 `5` 只持仓、单票权重上限 `20%`、允许持有现金、A 股 `100` 股整手约束、控制单次调仓换手；这些是研究起点，不是最终对外承诺，后续可被实证结果推翻。

[2026-04-25T23:58:00+08:00] Simulation model-advice honesty decision from local execution:
simulation model-track 的主 contract 不再允许向用户暴露固定预算买入股数或“卖出一半持仓”这类伪精确数量建议。自本轮起，`model_advices` 只表达人工复核候选动作和参考价格，数量语义保持 withheld，直到正式 execution policy 被研究、批准并锁定。

补充说明
- backend `simulation.model_advices` 现在只在“至少可买/可卖一个 board lot”时给出 `buy/sell` candidate，否则保持 `hold`；对外 `quantity` 统一为空，`action_definition` 收紧为 `manual_review_candidate_from_latest_recommendation`，`quantity_definition` 明确为 `withheld_until_execution_policy_is_approved`。
- frontend operations / simulation UI 已同步移除模型建议里的伪精确股数展示，手动下单参考只保留“买入候选 / 卖出候选 + 参考价”语义，避免把迁移期启发式 sizing 误读成正式策略。
- 这次收口只解决 user-facing honesty，不代表 auto-execution policy 已完成。`F004` 仍保留为未关闭维护项，剩余工作是把真实仓位规则、执行门槛和审批边界研究清楚后再恢复正式 quantity contract。

[2026-04-25T23:45:00+08:00] Manual review layer honesty decision from local execution:
信号引擎主 contract 不再允许把手动研究占位层继续命名成 `llm_assessment factor`。从本轮起，它在主语义里被明确降级为 `manual_review_layer`，只保留“人工研究 artifact 解释层、不可入核心评分”的含义。

补充说明
- signal engine 的主 snapshot、model registry metadata、evidence factor card 与 traceability 视图现在统一使用 `manual_review_layer` / `manual_review_placeholder_layer`；融合分数只允许由 `price_baseline + news_event` 组成，不能继续把手动研究占位包装成主定量因子。
- `llm_assessment` 仅允许作为 legacy compat projection 保留，供旧 factor breakdown consumer 平滑读取；它不再是主 product contract，也不应被作为“LLM lift”“LLM 因子”或任何可计分主特征解释。
- 从本轮起，`F002 so-called LLM factor` 视为已关闭；未完成项只剩真实 validation rebuild 与 auto-model quantity policy 的正式化。

[2026-04-25T23:15:00+08:00] Maintenance-mode honesty decision from local execution:
Phase 4 完成后的 maintenance 收口正式锁定两条迁移期 contract 语义：portfolio / replay benchmark 不再允许使用 synthetic demo 路径，model-track action 也不再允许以 `execution_policy_placeholder` 对外表述。

补充说明
- operations 与 simulation 的 benchmark 数值路径现在统一来自 active watchlist 真实价格构造的 equal-weight proxy；migration replay / portfolio artifact 的 `benchmark_definition` 统一收紧到 `phase2_equal_weight_market_proxy`。
- migration artifact consumer 必须尊重 artifact 自身 `status`，不得因为 benchmark/cost/execution 字段齐全就自动把 pending artifact 升成 `verified`。
- model-track action 现已明确标记为 `manual_review_preview_policy_v1`：它仍是人工复核预览，不会自动成交，也不应被解释成正式执行策略。
- 从本轮起，`F003 benchmark synthetic` 视为已关闭；后续 maintenance 或新 phase 只应继续处理真实量化问题，例如 live/offline validation、LLM lift 重建与正式 auto-execution policy。

[2026-04-25T21:46:24+08:00] Phase 4 governance completion decision from local execution:
`Phase 4 - Manual Research Workflow Hardening and Stable manual_llm_review Contract` 正式完成收尾；从本轮起，manual research request lifecycle 的 operator terminal actions 和 UI governance boundary 视为稳定 contract，而不是待补产品壳。

补充说明
- backend 终态 contract 已锁定：`complete` 负责生成稳定 `manual-review:{request_key}` artifact，并清空失败侧字段；`fail` 不再允许覆盖已生成 artifact 的 completed request，completed terminal state 只能通过 `retry` supersede。
- frontend governance 已锁定三处主入口：单票 follow-up receipt、operations queue、operations focus workspace 均支持 `执行 / 人工完成 / 标记失败 / Retry`，并显式展示 `status_note / failure_reason / stale_reason / request_key`。
- `manual_llm_review` 的真相源继续固定为 `manual_research_requests + manual_review artifact`；compat `/analysis/follow-up` 只保留触发包装层角色，不再定义主生命周期。
- 本轮验证 `PYTHONPATH=src python3 -m unittest tests.test_manual_research_workflow tests.test_dashboard_views`、`PYTHONPATH=src python3 -m unittest tests.test_runtime_config tests.test_manual_research_workflow tests.test_dashboard_views tests.test_traceability tests.test_analysis_pipeline tests.test_research_artifact_store` 与 `frontend && npm run build` 全部通过。

[2026-04-14T11:17:37.757Z] Operator feedback from github:zhaohernando-code:
本轮计划反馈
- 问题：一期先覆盖多大的股票范围？
  回复：自选股池
- 问题：你希望系统给出的“投资建议”定位是什么？
  回复：尽量接近投顾体验
- 问题：数据源策略更倾向哪种？
  回复：先免费后预留付费升级
- 问题：一期主要交付形态是什么？
  回复：Web看板
- 问题：建议风格希望更偏哪类？
  回复：平衡型

补充说明
这个web后续可以作为github page子页面进行部署
针对主要风险进行一些补充说明和提问：
Q1: A 股行情与新闻数据的授权、质量和实时性差异很大，若前期数据源选择失误，后续架构会频繁返工。
A1: 我需要你对当前的数据源进行评估，如果免费和付费差距过大，我可以考虑付费
Q2: 历史价格预测在金融场景中极易过拟合，若没有严格的时间滚动验证，离线结果会显著高估真实效果。
A2: 可以在里面做时间滚动验证么？
Q3: 新闻到因子的映射存在噪声和时滞，同一事件可能被重复计价或在市场中提前反映。
A3: 能否通过技术手段减轻影响？
Q4: LLM 容易把弱信号组织成看似确定的结论，必须被限制在解释层，并绑定结构化证据和风险提示。
A4: LLM的反馈也作为一个因子，可以先用历史数据来评估其分析可信度
Q5: 推荐、建议和模拟交易同时展开会迅速扩大一期复杂度，需要先限定股票池、刷新频率和建议粒度。 面向外行输出“投资建议”涉及合规表达和责任边界，需要尽早明确产品定位是研究辅助、教育用途还是更强的决策支持。
A5: 产品后续方向会更倾向于更强的决策支持而不是研究辅助和教育用途。在经过一段时间的模拟盘测试后可能会正式作为投资的决策建议

[2026-04-14T11:23:36.864Z] Operator feedback from github:zhaohernando-code:
本轮计划反馈
- 问题：GitHub Pages 在一期里承担到什么程度？
  回复：前端上 GitHub Pages，后端单独部署
- 问题：一期希望把数据时效性做到什么级别？
  回复：盘中延迟更新可接受
- 问题：建议主要面向哪类持有周期？
  回复：波段 2-8 周

[2026-04-14T11:34:11.618Z] Operator feedback from github:zhaohernando-code:
本轮计划反馈
- 问题：一期看板的访问范围需要如何控制？
  回复：小范围内测
- 问题：一期模拟交易更希望采用哪种方式？
  回复：两者都要

补充说明
“免费与付费 A 股数据在授权、稳定性、实时性和字段完整度上的差距可能显著高于预期；若前期不做适配层和替换预案，后续升级成本会很高”
上述行为是否为你调研过后的行为。如果只是猜测，那可能适配和替换预案都需要加入需求列表

[2026-04-14T11:48:50.205Z] Operator feedback from github:zhaohernando-code:
本轮计划反馈
- 问题：“两者都要”的模拟交易，具体希望覆盖哪两类路径？
  回复：手动模拟+自动持仓（这两个不要放在一起）
- 问题：如果数据源评估显示免费方案不足，一期是否允许直接落到付费数据方案？
  回复：先评估后单独审批

补充说明
我无法直接回答付费问题，因为你需要在评估后告诉我价格和付款模式

[2026-04-14T11:55:57.539Z] Operator feedback from github:zhaohernando-code:
本轮计划反馈
- 问题：自动持仓模式在一期更接近哪种机制？
  回复：按模型组合自动持仓

[2026-04-15T00:00:00+08:00] Pending operator decision:
第 1 步“数据与开源基线评估”已完成，等待操作者在 web decision gate 中选择后续数据路线与第 2 步执行方向。

[2026-04-14T15:39:04.955+08:00] Project flow decision from local operator:
采用 `Tushare Pro + 巨潮公告/交易所披露 + Qlib` 作为一期主路线；`AkShare` 仅作辅助原型和补缺。

补充说明
- 第 2 步“证据化数据底座”继续推进。
- `license_tag`、`usage_scope`、`redistribution_scope`、`source_uri`、`lineage_hash` 作为强制字段进入数据模型。

[2026-04-14T16:42:56.908+08:00] Project flow decision from github:zhaohernando-code:
项目流决策
当前步骤：数据与开源基线评估
- 决策项：下一步按哪条路线推进？
  结论：按低成本研发路线继续

补充说明
- 开发时要预留未来切换到“商业数据授权 / 询价”方案的代码架构。
- 后续需要补一份“效果 -> 价格”的商业数据授权调研报价单。

[2026-04-15T00:50:14+08:00] Implementation decision from local execution:
第 2 步采用 `FastAPI + SQLAlchemy` 的 Python 后端骨架，先把证据血缘、建议回溯和模拟交易留痕固化为统一 schema，再在同一 contract 下接入真实 provider。

补充说明
- `LineageMixin` 已覆盖股票、板块、行情、新闻、特征、模型版本、模型结果、提示词版本、建议、建议证据、模拟交易和采集运行表。
- 证据追溯采用 `recommendation -> recommendation_evidence -> domain artifact` 的解耦结构，避免在第 3 步前把供应商实现细节写死在业务层。
- 当前以 `DemoLowCostRouteProvider` 验证端到端链路；真实 `Tushare / 巨潮 / Qlib` 适配器将沿同一 provider contract 补齐。

[2026-04-15T10:30:00+08:00] Implementation decision from local execution:
第 3 步采用“价格基线 + 新闻事件因子 + capped LLM 因子 + 融合评分卡”的建议引擎结构，LLM 因子默认只在历史 lift 与稳定性同时过阈值时参与加权，且权重上限固定为 `15%`。

补充说明
- recommendation 输出必须直接暴露 `confidence_expression`、`reverse_risks`、`downgrade_conditions`、`factor_breakdown` 和 `validation_snapshot`，避免前端再去解析半结构化文本。
- demo provider 不再维护静态 recommendation，而是统一走 `raw evidence -> signal_engine -> persisted recommendation` 链路。
- 当前 `14/28/56` 天三个 horizon 都会落到 `model_results`；recommendation 以 28 天作为主解释窗口，但保留 2-8 周完整范围。

[2026-04-15T15:20:00+08:00] Implementation decision from local execution:
第 6 步将“手动模拟交易”和“按模型组合自动持仓”继续建成两个独立 `paper_portfolios`，共用 recommendation 流但独立资金池、独立收益归因、独立回撤阈值，不做合并记账。

补充说明
- 历史 seed 订单只服务于组合收益、回撤和基准对比演算；只有 `order_record.recommendation_key` 与当前 recommendation 精确匹配时，订单才进入 recommendation trace。
- 内测访问控制采用可配置的 header allowlist 方案：默认 `open_demo` 便于本地验证，部署小范围内测时切换为 `ASHARE_BETA_ACCESS_MODE=allowlist` 并使用 `ASHARE_BETA_ALLOWLIST` 管理 key/role。
- 新增 `/dashboard/operations` 作为模拟交易运营面板 contract，统一承载收益归因、A 股规则检查、建议命中复盘、刷新策略、性能阈值和上线门槛。

[2026-04-15T16:20:00+08:00] Acceptance revision decision from local execution:
为解决线上 API 不可用导致的验收失败，本轮采用“当前 API contract 导出的前端离线快照 + 在线优先回退机制”完成最小可用闭环，而不是新开一套平行前端 demo。

补充说明
- 新增 `frontend_snapshot` 导出器，离线数据直接由现有 `dashboard` 与 `operations` payload 生成。
- 前端默认在无 `VITE_API_BASE_URL` 时进入离线模式；若用户切到在线模式但接口失败，会自动回退并明确提示原因。
- UI 改为 `Ant Design` 控制台式布局，把数据模式、焦点股票、access key 和演示重置收敛到顶部操作面板，减少无效大文案占位。

[2026-04-24T23:40:00+08:00] Research reset decision from local operator:
历史计划与现有实现中的时间窗口、权重占比、阈值和样本期不再视为产品约束；凡是影响可信度的旧设定，包括但不限于 `2-8 周`、`14/28/56`、固定权重上限、固定命中口径，后续都允许被研究结果直接推翻。

补充说明
- 这些数字保留为“历史假设”仅用于审计与迁移，不再作为新一轮深度改造的默认输入。
- 后续开发必须先给出研究依据，再锁定窗口、标签、调仓频率、融合权重和展示口径。
- 若真实研究结果表明旧功能名不副实，应优先重命名、降级或删除，而不是继续沿用旧字段。

[2026-04-24T23:59:00+08:00] Execution governance decision from local execution:
项目新增 `PROJECT_STATUS.json` 作为机器可读的执行状态真相源，和 `PROJECT_PLAN.md`、`DECISIONS.md`、`docs/archive/RESEARCH_NOTES.md`、`PROCESS.md` 共同构成新的深度改造交接面。

补充说明
- `PROJECT_PLAN.md` 负责长期路线和阶段定义。
- `DECISIONS.md` 负责记录被批准的架构与策略决策。
- `docs/archive/RESEARCH_NOTES.md` 负责外部研究与研究结论。
- `PROCESS.md` 负责按日期追加执行日志。
- `PROJECT_STATUS.json` 负责让新会话和自动化进程快速判断当前 phase、里程碑、阻塞点和下一步动作。

[2026-04-25T00:38:39+08:00] Product honesty migration decision from local execution:
在真实滚动验证、真实 benchmark 和手动 Codex/GPT 研究链路重建完成前，前端和 API contract 不再把旧的 validation snapshot、超额收益、建议命中口径和所谓 LLM 因子展示为已验证能力。

补充说明
- recommendation contract 现在显式输出 `validation_status`、`validation_note`，并把旧的 `validation_snapshot` 对外清空。
- operations contract 现在显式区分 `benchmark_status`、`benchmark_note`、`replay_validation_status` 和 `replay_validation_note`。
- 所谓 `LLM 因子` 在核心评分中被降为零权重占位，只保留“手动触发研究链路待接管”的迁移语义。
- 在新的研究合同锁定前，任何旧验证指标都只能显示为 `pending_rebuild`、`synthetic_demo` 或 `manual_trigger_required`，不得再伪装成真实量化验证结果。

[2026-04-25T00:38:39+08:00] Phase 0 contract freeze decision from local execution:
项目正式冻结迁移期的 `recommendation / replay / portfolio / operations / manual_llm_review` 合同语义，并以 `docs/contracts/PHASE0_DATA_METRIC_CONTRACT.md` 作为后续 schema 与服务改写的事实来源。

补充说明
- recommendation 未来必须拆成 `core_quant`、`evidence`、`risk`、`historical_validation`、`manual_llm_review` 五层。
- replay 必须与 recommendation 的目标 horizon 和 label 定义对齐，不再允许沿用“直到当前最新价”的宽松窗口。
- portfolio 和 operations 必须显式区分 `运行健康`、`研究验证`、`演示策略` 和 `上线门禁`，不能再混成单一 readiness 指标。
- 没有真实 benchmark、真实回测和真实实验 artifact 支撑的数值字段，不得升级为 `verified`。

[2026-04-25T00:44:42+08:00] Continuous autonomous execution decision from local operator:
在用户离线或睡眠期间，项目按已批准 plan 持续推进；如果发生上下文压缩、线程切换或新会话恢复，也必须默认继续当前 phase 的下一步，而不是自动停在阶段性说明上。

补充说明
- 这条规则同样适用于上下文压缩后的恢复场景。
- 只要 handoff 文档和 `PROJECT_STATUS.json` 仍可读取，新会话应直接继续执行，不需要等待新的“继续”口令。
- 只有遇到真实外部阻塞、权限缺失、破坏性冲突或高风险不确定性时，才允许暂停并等待用户输入。

[2026-04-25T00:55:27+08:00] Phase 1 recommendation and replay contract decision from local execution:
Phase 1 正式要求前端和运营复盘开始消费新的 recommendation / replay 分层 contract，而不是继续把 legacy 兼容字段当成主要语义来源。

补充说明
- recommendation 主视图应优先读取 `core_quant`、`evidence`、`risk`、`historical_validation` 和 `manual_llm_review`。
- replay 记录至少要显式输出 `label_definition`、`review_window_definition`、`entry_time`、`exit_time` 和 `hit_definition`，即使当前仍属于迁移期演示口径。
- 旧 `core_drivers`、`reverse_risks`、`review_window_days` 和单一 `hit_status` 仍可保留为兼容层，但后续不能再独自承担真实语义。

[2026-04-25T01:24:00+08:00] Phase 1 governance workspace contract decision from local execution:
运营治理页和组合工作区现在必须以显式分层 contract 作为主语义来源；legacy `beta_readiness`、`benchmark_status`、`benchmark_note` 和 `replay_validation_note` 只允许作为兼容壳保留，不能继续主导用户可见的状态解释。

补充说明
- operations governance 主视图应优先读取 `overview.run_health`、`overview.research_validation` 和 `overview.launch_readiness`。
- portfolio workspace 主视图应优先读取 `benchmark_context`、`execution_policy` 和 `validation_status`，而不是继续把 top-level benchmark shorthand 当成真实量化语义。
- 后续若仍保留 legacy compat 字段，必须由新分层 contract 派生，不能再由独立的旧逻辑直接生成。

[2026-04-25T01:42:00+08:00] Phase 1 compatibility derivation decision from local execution:
从本轮起，operations 与 portfolio 的 legacy compat 字段必须从分层 contract 派生，同时性能预算测量必须基于接近最终返回结构的 payload，而不是旧版扁平 overview。

补充说明
- `beta_readiness`、`replay_validation_status`、`recommendation_replay_hit_rate` 等 overview 兼容字段，只能从 `launch_readiness` 与 `research_validation` 推导。
- `benchmark_status`、`benchmark_note`、`recommendation_hit_rate` 等 portfolio 兼容字段，只能从 `benchmark_context`、`validation_status` 等显式层派生；在验证未完成时不得继续输出乐观的 synthetic 命中率。
- 后续任何性能门禁或 payload 预算数字，都必须说明其测量对象对应的是哪一层 contract，避免“新 contract 已膨胀，旧 payload 预算仍显示过关”的假象。

[2026-04-25T09:40:36+08:00] Phase 1 candidate and factor-card contract decision from local execution:
候选列表、跟进提问和单票详情页中的建议解释现在必须优先消费 recommendation 的显式分层 contract；legacy `applicable_period`、`core_drivers`、`reverse_risks` 与 `factor_breakdown` 只允许作为服务端兼容壳继续保留。

补充说明
- candidate list 和 follow-up prompt 必须从 `historical_validation`、`core_quant`、`evidence`、`risk` 派生窗口、horizon、验证状态和主要风险，而不是继续直接读取旧 top-level 建议字段。
- 单票详情页的因子卡片主读取路径已切到 `evidence.factor_cards`；top-level `factor_breakdown` 保留仅用于迁移兼容和 traceability，不再作为前端主 contract。
- 后续若继续压缩 recommendation schema，优先删除的是“顶层 legacy 展示字段被前端主读”的路径，而不是盲目先删兼容字段本身。

[2026-04-25T09:53:33+08:00] Phase 1 helper cleanup and Phase 2 artifact contract decision from local execution:
`dashboard.py` 的变化解释 helper 现在必须优先消费 `evidence.factor_cards` 与 `evidence.degrade_flags`，同时项目正式冻结 `Phase 1 -> Phase 2` 的 research artifact contract，后续真实滚动验证、回测和 replay 结果只能按该 contract 落盘与投影。

补充说明
- `dashboard` 层的 `factor_score`、降级标记和 follow-up / risk helper 不应再依赖 recommendation 顶层 `factor_breakdown` 作为主语义来源；顶层 compat 字段仅保留为迁移壳。
- 新增 `docs/contracts/PHASE1_PHASE2_ARTIFACT_CONTRACT.md` 与 `src/ashare_evidence/research_artifacts.py`，预先冻结 rolling validation manifest、validation metrics artifact、portfolio backtest artifact 和 replay alignment artifact 的字段边界。
- 在后续真实量化结果重建前，任何 `historical_validation.status=verified` 的语义都必须绑定上述 artifact manifest，而不能由 recommendation payload 自己声称“已验证”。

[2026-04-25T10:05:48+08:00] Phase 1 artifact gate and storage layout decision from local execution:
从本轮起，产品层的 `historical_validation` 与 replay validation projection 必须经过统一 artifact gate；同时 Phase 2 的研究产物存储路径正式落成代码骨架，后续真实滚动验证、回测与 replay 结果应优先写入 artifact store，而不是继续直接挤进 recommendation payload。

补充说明
- `src/ashare_evidence/research_artifacts.py` 新增统一 validation gate，若 payload 试图在缺少 `artifact_id / manifest_id / approved benchmark / cost definition` 时自称 `verified`，服务层必须回落为 `pending_rebuild`。
- `src/ashare_evidence/research_artifact_store.py` 已按 `artifacts/manifests|validation|backtests|replays` 的目录语义提供落盘和读取接口，为后续 Phase 2 artifact producer 铺底。
- `simulation.py` 的模型建议理由和风险提取现在优先读取 recommendation 的 `evidence / risk` 分层字段，避免模拟轨道继续依赖旧 top-level compat 字段。

[2026-04-25T10:24:34+08:00] Phase 1 artifact-backed governance and simulation-layer decision from local execution:
`operations` 概览中的研究验证摘要现在必须显式投影 artifact 绑定覆盖率，而 `simulation` 的模型建议区不再允许从 recommendation 顶层 legacy reason/risk 字段回退取值。

补充说明
- `overview.research_validation` 现在新增 `manifest_bound_count`、`metrics_artifact_count` 和 `artifact_sample_count`，用于说明当前治理页看到的“研究验证”到底有多少条 recommendation 已经绑定 migration artifact，而不是只剩空泛的 `pending_rebuild` 状态。
- `simulation.py` 的建议理由与风险提示现在只能从 `evidence.primary_drivers / supporting_context` 和 `risk.risk_flags / invalidators / coverage_gaps` 读取；旧 `core_drivers` 与 `reverse_risks` 继续保留仅用于服务端兼容壳，不再作为 simulation 主语义来源。
- 对应回归测试已加入“毒化 top-level legacy 字段”的断言，后续如果有人把 simulation 再改回 legacy fallback，应当直接测试失败。
- `frontend/src/types.ts` 中 recommendation 的顶层 `applicable_period / core_drivers / reverse_risks / factor_breakdown / validation_snapshot` 等字段现已降为可选 compat 字段，避免新的前端开发继续把它们当成必填主 contract。

[2026-04-25T11:01:46+08:00] Phase 1 portfolio backtest projection decision from local execution:
组合层现在必须能读取 Phase 2 artifact store 中的 portfolio backtest 产物，并把 artifact-backed 的 benchmark/performance/validation 元数据投影到 portfolio contract；但只要 benchmark 定义仍是 `synthetic_demo`，产品层验证状态就必须继续回落为 `pending_rebuild`。

补充说明
- `tests/fixtures.py` 现在会在 watchlist fixture 完成后生成 `rolling-validation:portfolio-migration-watchlist` manifest，并为 `portfolio-manual-live / portfolio-auto-live` 写入 `portfolio-backtest:*` artifact，作为迁移期组合回测占位产物。
- `operations.py` 中 portfolio payload 会优先读取对应 backtest artifact，把 `artifact_id / manifest_id / benchmark_definition / annualized_return / annualized_excess_return / turnover / win_rate_definition` 投影到 `benchmark_context` 与 `performance`，并将 `validation_artifact_id / validation_manifest_id` 暴露给产品层。
- 统一 validation gate 仍然生效：由于当前 artifact 的 `benchmark_definition=synthetic_demo`，portfolio 的 `validation_status` 与 benchmark context status 只能是 `pending_rebuild`，不得借由 artifact 存在本身升级为 `verified`。

[2026-04-25T11:09:26+08:00] Phase 1 portfolio artifact governance projection decision from local execution:
治理页的 `research_validation` 现在必须同时投影 recommendation artifact 覆盖和 portfolio backtest artifact 覆盖，且 simulation/portfolio workspace 对组合产物的展示必须与这组治理数字保持一致。

补充说明
- `simulation.py` 现在会把 manual/model 轨道映射到 `portfolio-backtest:portfolio-manual-live` 与 `portfolio-backtest:portfolio-auto-live`，确保双轨工作区与 operations portfolio contract 使用同一组 migration backtest artifact。
- `operations.py` 新增 `portfolio_backtest_bound_count / portfolio_backtest_manifest_count / portfolio_backtest_verified_count / portfolio_backtest_pending_rebuild_count`，并把“组合回测产物绑定”加入 launch gates，避免治理页只看到 recommendation metrics 而忽略组合层 research artifact 接通情况。
- `frontend/src/App.tsx` 的运营概览现在直接展示 recommendation manifest/metrics 覆盖和 portfolio backtest 覆盖计数；当前这些数字仍只能说明“artifact 已接通”，不能替代正式 benchmark、成本和执行假设完成后的真实验证结论。

[2026-04-25T11:13:06+08:00] Phase 1 compat-shell reduction decision from local execution:
`portfolio` 与 `operations overview` 的顶层 benchmark/readiness compat 字段现在只应被视为派生壳；前端主 contract 和后端 response model 都必须允许这些字段降为 optional，以便后续逐步删除而不反向绑死实现。

补充说明
- `frontend/src/App.tsx` 的组合页已改为读取 `execution_policy.status` 而不是 `portfolio.strategy_status`；`frontend/src/types.ts` 也将 `strategy_status / benchmark_status / recommendation_hit_rate / beta_readiness / recommendation_replay_hit_rate / replay_validation_status` 降为 optional compat 字段。
- `src/ashare_evidence/schemas.py` 已同步把上述 compat 字段放宽为 optional，同时保持当前 API 继续输出这些字段，确保迁移期兼容不被破坏。
- `src/ashare_evidence/operations.py` 新增 `_portfolio_compat_projection` 与 `_overview_compat_projection` 两个 helper，后续若继续删除 compat 字段，只需在统一出口调整，不应再在 payload 组装逻辑里散落多处旧口径写入。

[2026-04-25T11:27:08+08:00] Phase 1 replay artifact consumer decision from local execution:
`operations.recommendation_replay` 现在必须优先消费 artifact store 中的 replay alignment 产物，而不是继续仅靠内联 synthetic replay payload 维持迁移语义；治理摘要也必须显式区分“已有 replay artifact”与“仍未进入 verified”的覆盖率。

补充说明
- `tests/fixtures.py` 现在会在 watchlist fixture 完成后，为 replay 列表生成并落盘 `replay-alignment:*` artifact，使 recommendation metrics、portfolio backtests 和 replay alignment 三条迁移期 artifact 路径共享同一 artifact store。
- `src/ashare_evidence/operations.py` 的 replay payload 会优先读取 replay artifact 的 `manifest_id / label_definition / review_window_definition / hit_definition / validation_status`，并新增 `source=replay_alignment_artifact|migration_inline_projection` 以区分真实 artifact-backed consumer 与仍未接通的 inline fallback。
- replay artifact 覆盖率在治理层使用 `replay_artifact_bound_count / replay_artifact_manifest_count / replay_artifact_nonverified_count` 表达，其中 `nonverified` 明确表示“尚未进入 verified”，避免把 `synthetic_demo` 误命名成 `pending_rebuild` 再次制造状态歧义。

[2026-04-25T11:38:37+08:00] Phase 1 candidate validation projection decision from local execution:
候选列表和单票详情页现在必须直接显示 artifact-backed validation 指标，而不是只给用户一个抽象的验证状态标签；推荐消费层的验证摘要应优先来自 `historical_validation.metrics` 与 artifact id/manifest id，而不是继续依赖 legacy 顶层说明字段。

补充说明
- `src/ashare_evidence/dashboard.py` 现在把 recommendation 的 `historical_validation` 中的 `artifact_id / manifest_id / sample_count / rank_ic_mean / positive_excess_rate` 投影进 candidate contract，使候选列表与自选池详情和 governance/portfolio 一样，消费同一条 stored validation artifact 路径。
- `frontend/src/App.tsx` 已新增 candidate validation summary 展示，并在 stock detail 的“历史验证层”中直接展示样本量、RankIC 均值、正超额占比和覆盖率，避免用户只能看到“待重建/已验证”这种低信息量标签。
- 这组指标当前仍属于 migration artifact 语义，不等于正式通过研究批准的实盘可信结论；但在 benchmark 仍为 `synthetic_demo` 的前提下，产品层至少必须诚实展示“当前状态之下到底有多少样本、什么分布指标”，而不是隐藏具体数值。

[2026-04-25T11:41:08+08:00] Phase 1 recommendation compat reprojection decision from local execution:
recommendation 顶层 `factor_breakdown` 这类 legacy compat 壳现在应尽量从分层 contract 回投，而不是继续直接透传原始 payload。兼容字段可以保留，但语义来源必须逐步切到 `evidence / risk / historical_validation / manual_llm_review`。

补充说明
- `src/ashare_evidence/services.py` 新增 `_legacy_factor_breakdown`，现在会优先用 `evidence.factor_cards`、`evidence.degrade_flags` 和 `manual_llm_review.status` 生成 compat `factor_breakdown`，只把原始 payload 中尚未迁移的细节字段当作补充，而不是主真相。
- 这样做的目的不是立即删除 compat 字段，而是避免后续 traceability 或兼容 consumer 继续把未审计的 payload 结构误当成产品层事实。
- 后续若继续收 recommendation legacy 壳，优先目标应是让更多 compat 字段由显式分层 contract 派生；只有在 consumer 全部迁走后，才考虑真正删除字段本身。

[2026-04-25T11:51:05+08:00] Phase 1 layered-producer strengthening decision from local execution:
不仅服务层 compat projection 要从分层 contract 回投，`signal_engine` 产出的 recommendation payload 本身也要减少 raw compat 字段并优先写入显式层字段，否则服务层每次序列化都还要被迫从旧 payload 兜底。

补充说明
- `src/ashare_evidence/signal_engine.py` 现在直接写入 `evidence.factor_cards`、`evidence.degrade_flags`、`historical_validation.artifact_type` 和 `historical_validation.manifest_id`，并停止继续生成 `applicable_period`、`reverse_risks` 与 recommendation 顶层 `validation_snapshot` 这类已可由分层 contract 派生的 raw compat 字段。
- `src/ashare_evidence/services.py` 的 `core_quant / evidence / risk / manual_llm_review` 在消费 payload 时也会先做规范化补全，再进入 compat projection，避免“有分层字段但内容不完整”导致后续 consumer 又回退到旧字段。
- 这一步的目标不是一次性删除所有顶层 compat 字段，而是先保证新的 producer 与 consumer 都以分层 contract 为主语义来源。

[2026-04-25T11:51:05+08:00] Phase 1 follow-up research packet decision from local execution:
手动 Codex/GPT 研究入口不应只复制一段带抽象状态的 prompt 文本；follow-up contract 现在必须携带 artifact-backed 的验证摘要和人工研究状态，作为后续 Phase 4 手动触发工作流的结构化输入。

补充说明
- `src/ashare_evidence/dashboard.py` 的 `follow_up` payload 现在新增 `research_packet`，其中包含 `validation_artifact_id / manifest_id / sample_count / rank_ic_mean / positive_excess_rate` 以及 `manual_review_status / trigger_mode / source_packet`。
- follow-up 的 `copy_prompt` 同步加入上述验证信息，使人工研究时能直接看到当前 recommendation 已绑定的 validation artifact 与样本统计，而不是只看到 `pending_rebuild` 这种低信息量状态词。
- 后续真正切到手动 Codex/GPT 进程时，应优先消费这组结构化 `research_packet`，而不是重新从页面文案或 legacy recommendation 顶层字段里反解上下文。

[2026-04-25T12:16:00+08:00] Phase 1 placeholder quarantine and latest-summary test decision from local execution:
从这一轮起，recommendation 的历史验证与人工研究层不再允许被 legacy compat 字段反向驱动；同时所有“修改 payload 后再读取 latest summary”的 Phase 1 回归都必须显式绑定最新 recommendation 版本，避免旧历史记录掩盖 contract 漂移。

补充说明
- `src/ashare_evidence/services.py` 中 `historical_validation` 不再从 raw `validation_snapshot` 回填，`manual_llm_review` 也不再从 `factor_breakdown.llm_assessment` 反向补齐；验证真相只能来自 artifact gate + manifest/metrics 投影，人工研究真相只能来自 `manual_llm_review` 自身或默认手动占位。
- `src/ashare_evidence/research_artifact_builders.py` 的迁移 validation artifact 构建现在只读取 `historical_validation` 层和统一 gate 状态，不再吸收 legacy validation snapshot 中的 cost/status 语义。
- `src/ashare_evidence/simulation.py` 与 `src/ashare_evidence/operations.py` 对动作建议和组合执行语义继续降级：execution policy 统一标记为 `execution_policy_placeholder / pending_rebuild`，没有真实回测与执行假设接管前，不得看起来像正式策略。
- `tests/test_traceability.py` 中所有会修改 recommendation payload 的收口回归，后续都必须先锁定最新 recommendation，再验证 legacy 字段不会反向驱动主 contract。

[2026-04-25T12:29:00+08:00] Phase 1 manual-LLM placeholder boundary decision from local execution:
`manual_llm_review` 在 Phase 1 内正式收紧为“人工触发研究助手占位”，未触发状态下不得再携带 placeholder 风险或分歧；任何这类说明都只能留在 compat shell 或产品说明文案中，不能冒充人工研究产物。

补充说明
- `src/ashare_evidence/signal_engine.py` 生成 recommendation payload 时，`manual_llm_review` 默认只保留 `status / trigger_mode / model_label / summary / source_packet`，并把 `risks / disagreements` 置空，避免 producer 直接把“尚未接入的 LLM 研究能力”写成一组看似真实的风险结论。
- `src/ashare_evidence/services.py` 会对历史 payload 做同样的净化：如果 `manual_llm_review.status=manual_trigger_required` 且没有真实 `generated_at`，则强制清空 `risks / disagreements`，确保旧 recommendation 进入新 contract 时不会把 placeholder 重新抬回主语义。
- 只有在后续真正接入手动 Codex/GPT 工作流并落下可追溯研究产物后，`manual_llm_review` 才允许展示具体风险、分歧与生成时间；在此之前，它只是研究入口状态，不是研究结论本身。

[2026-04-25T12:37:00+08:00] Phase 1 replay window-definition-first decision from local execution:
`recommendation_replay` consumer 现在必须优先展示结构化 `review_window_definition`，而不是继续把 `review_window_days` 这种 legacy 数字壳当成主语义；旧天数字段仅允许作为兼容层保留。

补充说明
- `frontend/src/App.tsx` 的 replay 表格现已把 secondary text 切到 `symbol + review_window_definition`，避免用户在迁移期看到一个来源不清、看似精确的窗口天数后误判这已经是研究批准过的定义。
- `frontend/src/types.ts` 与 `src/ashare_evidence/schemas.py` 已同步把 `review_window_days` 降为 optional compat 字段，为后续 Phase 1 继续收缩 replay legacy 壳留出空间。
- 后续如果 replay contract 继续细化，优先方向应始终是“定义性字段优先、数字性 legacy 壳后退”，直到 Phase 2 的真实 replay producer 接管。

[2026-04-25T12:26:34+08:00] Phase 1 artifact-backed vs migration-validation projection decision from local execution:
从这一轮开始，Phase 1 必须把“artifact 已接通”与“验证已成立”彻底分开投影。任何 replay 或 portfolio backtest 即使已经绑定 artifact/manifest，也只有在 benchmark、成本和执行假设完成重建后，才允许进入 `artifact_backed` 的 validation mode；否则只能以 `artifact_backed` source classification + `migration_placeholder` validation mode 对外展示。

补充说明
- `src/ashare_evidence/operations.py` 与对应 schema/type 现在新增统一的 `source_classification` 与 `validation_mode` 字段，并在 `portfolio`、`recommendation_replay`、治理摘要和 launch gate 上使用同一套口径；“组合回测产物绑定” gate 也不再因为 artifact 已绑定就显示通过，而是要求 `verified_count` 满足后才可 pass。
- `frontend/src/App.tsx` 已同步把 replay 表格和 portfolio workspace 的说明切到这组新字段，显式提示“artifact 已接通但 benchmark / cost / execution assumptions 仍属迁移占位”的状态，避免用户把 migration artifact 误读成正式回测结论。
- `docs/contracts/PHASE1_PHASE2_ARTIFACT_CONTRACT.md` 现已冻结 `source_classification` 与 `validation_mode` 两个迁移投影字段，后续 Phase 2 producer 只允许填充真实定义，不应再改消费层结构。

[2026-04-25T12:26:34+08:00] Phase 1 layered-evidence-first recommendation consumer decision from local execution:
recommendation 服务层现在必须优先消费 `core_quant` 与 `evidence.factor_cards` 这些显式分层字段，`factor_breakdown` 只允许作为 compat fallback；否则一旦 producer 继续清理 raw payload 壳，consumer 还会被旧结构拖住。

补充说明
- `src/ashare_evidence/services.py` 现在在构建 `core_quant` 时优先从 `evidence.factor_cards.fusion` 提取分数，在构建 `evidence` 时优先信任 `payload.evidence.factor_cards` 与 `payload.evidence.degrade_flags`，只有缺失时才回退到 `factor_breakdown`。
- `tests/test_traceability.py` 已补充“删除 raw factor_breakdown 后，core_quant.score 和 evidence.factor_cards 仍然稳定”的断言，确保这条 consumer contract 不会被后续改动重新绑回 raw compat 字段。
- 这一步的目标不是立刻删除 `factor_breakdown` 顶层 compat 壳，而是先确保主消费链路不再把它当真相源；后续 producer 清壳时就只需要继续删 compat，而不是再改一轮 consumer。

[2026-04-25T12:29:53+08:00] Phase 1 governance projection parity decision from local execution:
治理页不应只统计“有多少 artifact / manifest”，还必须统计“其中多少已经是 artifact-backed projection、多少仍停留在 migration-placeholder validation”。否则 overview 与 replay/portfolio 详情页会用不同的状态语言，用户仍然需要自己猜“这些 artifact 数字到底意味着什么”。

补充说明
- `src/ashare_evidence/operations.py` 现在会额外汇总 `replay_artifact_backed_projection_count / replay_migration_placeholder_count / portfolio_backtest_artifact_backed_projection_count / portfolio_backtest_migration_placeholder_count`，把 replay 和 portfolio 两条链路的“已接通产物”和“仍属迁移验证”同时暴露到治理层。
- `src/ashare_evidence/schemas.py`、`frontend/src/types.ts` 与 `frontend/src/App.tsx` 已同步接入这些字段，运营概览现已直接展示这组 projection parity 计数，而不是只展示 bound / pending 的混合数字。
- 这项决策的意义不是增加更多漂亮指标，而是冻结一条要求：overview、局部详情和后续 Phase 2 producer 都必须使用同一套状态词典，避免再次出现“局部页很诚实、总览页却显得更乐观”的偏差。

[2026-04-25T12:44:00+08:00] Phase 1 closure and Phase 2 entry decision from local execution:
`Phase 1` 现在正式收口。项目不再允许用未验证 compat 命中率字段返回 `0.0` 伪装结果，也不再允许 simulation 的 placeholder 执行动作自动落成模型轨道成交；从这一刻起，`Phase 2` 可以直接在现有 consumer contract 上接入真实 rolling validation / replay / backtest artifact producer，而无需再做一轮 schema 清壳。

补充说明
- `src/ashare_evidence/operations.py` 已把 `recommendation_hit_rate` 与 `recommendation_replay_hit_rate` 的非 verified compat 投影改为 `null`，明确表示“结果 withheld”，而不是“真实统计值等于零”。
- `src/ashare_evidence/simulation.py` 已把 `auto_execute_model` 的有效执行态冻结为关闭，同时新增 `auto_execute_status / auto_execute_note` 和 `migration_placeholder_estimate` 标记；占位动作现在只能作为人工复核试算存在，不能再自动写成模型成交。旧 session 中遗留的 `auto_execute_model=true` 也会在读取时被自动降级到同一条 Phase 1 规则上。
- `src/ashare_evidence/schemas.py`、`frontend/src/types.ts`、`frontend/src/App.tsx` 与相关测试已同步完成这轮 contract 收口，`phase_1_schema_service_rewrite` 在 `PROJECT_STATUS.json` 中正式记为完成。

[2026-04-25T15:07:20+08:00] Phase 2 producer wiring completion and artifact-hydration ordering decision from local execution:
`Phase 2` 的第一轮真实 producer 接线现已收口到模块化 `src/ashare_evidence/phase2/` 包，并正式接入 `analysis_pipeline.refresh_real_analysis(...) -> rebuild_phase2_research_state(...)` 主路径。后续产品层只允许把 manifest/metrics/replay/backtest 这些 artifact hydrate 完整后的结果投影到 contract，不再接受“producer 已写盘但 service 仍按空壳状态先降级”的旧顺序。

补充说明
- `src/ashare_evidence/phase2/` 现已拆成 `constants/common/data/observations/validation/replay/portfolio/rebuild` 多文件结构，保持单文件体量可控，避免 Phase 2 逻辑再次回长成单个超大模块。
- 新增 `tests/test_analysis_pipeline.py` 端到端回归，直接覆盖真实 refresh 后 recommendation 写库、validation metrics 落盘、replay alignment 生成，以及最小 `paper_portfolios / paper_orders / paper_fills` 输入下的 portfolio backtest artifact 生成。
- `src/ashare_evidence/phase2/validation.py` 现在会在 recommendation `as_of_data_time` 与 observation `as_of` 比较前先做时区对齐；`src/ashare_evidence/services.py` 中 recommendation `historical_validation` 的 product gating 改为“先 hydrate manifest/metrics，再归一化状态”；`src/ashare_evidence/watchlist.py` 也同步对齐 `latest_generated_at`，避免 SQLite 路径再次触发 naive/aware `datetime` 比较错误。
- 这项决策的直接结果是：Phase 2 artifact producer 已不再只是 contract 骨架，而是被真实 refresh/rebuild 路径、artifact store 与 consumer regression 一起锁住。下一阶段阻塞点不再是 producer 接线，而是 quant core 仍然沿用 placeholder horizon/weight heuristic，以及 manual Codex/GPT 研究链路尚未产出 durable artifact。

[2026-04-25T19:27:40+08:00] Phase 2 quant-core completion and manual-research durability decision from local execution:
`Phase 2` 现已正式完成从 placeholder signal heuristic 到结构化 quant core 的替换，同时 follow-up 手动研究链路也已接成 durable `manual_review` artifact 流。后续默认入口应从 `Phase 2` 切换到 `Phase 3`，不再把“替换 quant core / 接 manual artifact”当成未完成事项。

补充说明
- `src/ashare_evidence/signal_engine.py` 已重构为薄入口，真实实现拆到 `src/ashare_evidence/signal_engine_parts/{base,factors,recommendation,assembly}.py`，所有新增文件保持在 `500` 行内；producer 现统一输出 Phase 2 的 `10/20/40` horizon、`phase2_target_horizon_label()`、`PHASE2_LABEL_DEFINITION`、`PHASE2_WINDOW_DEFINITION` 和 `phase2_rule_baseline_score` 语义，不再继续沿用 placeholder `14/28/56` 或 `research_window_pending`。
- 价格因子现采用“趋势 + 确认 + 风险压力”的 rule-baseline 结构，新闻因子继续走去重/衰减/层级映射，手动 LLM 层保留为零权重解释位；recommendation 的 `core_quant`、`historical_validation`、`evidence` 与 compat `applicable_period` 现都以这一套 Phase 2 常量为主语义来源。
- `src/ashare_evidence/manual_research.py`、`src/ashare_evidence/research_artifact_store.py` 与 `src/ashare_evidence/llm_service.py` 现已让 `run_follow_up_analysis(...)` 在拿到人工答案后写出 durable `manual_review` artifact，并把 `artifact_id / question / raw_answer / generated_at` 回投到 recommendation 和 follow-up `research_packet`；这意味着人工 Codex/GPT 研究现在第一次成为可回放产物，而不是临时文本响应。
- 为匹配已批准的 `10/20/40` 研究窗口，`tests/fixtures.py` 的日线样本已扩展到 `42` 根 bar，确保 previous snapshot 仍可覆盖 `40` 日窗口；相关回归 `tests.test_traceability`、`tests.test_dashboard_views`、`tests.test_runtime_config`、`tests.test_analysis_pipeline` 与 `tests.test_research_artifact_store` 已再次全部通过。
- 从这一刻起，`Phase 2 - Research Artifact Producer and Quant Core Rebuild` 视为完成；下一活动 phase 应为 `Phase 3 - Product Rewrite and User-facing Evidence/Risk Presentation`。

[2026-04-25T20:05:00+08:00] Phase 3 product-language closure and Phase 4 workflow-hardening decision from local execution:
`Phase 3` 现已正式收口。用户可见的 stock detail、candidate、governance、replay/portfolio 和 follow-up 页面现在必须以 layered contract 和 artifact-backed projection 作为主语言，legacy compat 字段只允许停留在统一派生壳；下一活动 phase 切换为 `Phase 4 - Manual Research Workflow Hardening and Stable manual_llm_review Contract`。

补充说明
- `frontend/src/App.tsx` 现已把 candidate 与焦点摘要补齐 `source_classification / validation_mode`，replay 主展示固定为 `review_window_definition`，并在 stock detail 与 follow-up 中显式展示 `manual_review_status / trigger_mode / artifact_id / generated_at`，避免再把人工研究入口伪装成未来能力或已完成结论。
- `src/ashare_evidence/dashboard.py`、`src/ashare_evidence/operations.py` 与对应 schema/type 继续把 `applicable_period`、`review_window_days` 等 legacy 字段收敛到 compat helper；主 contract 现在默认依赖 `core_quant / evidence / risk / historical_validation / manual_llm_review` 以及 operations 的 `run_health / research_validation / launch_readiness / source_classification / validation_mode`。
- `tests.test_traceability` 与 `tests.test_dashboard_views` 已同步改写：主回归断言改为验证 layered contract 和 artifact-backed projection，legacy compat 行为仅在专门 compat 测试中保留。这样后续 `Phase 4` 可以继续稳定 manual research workflow，而不必再回头重做一轮产品语言迁移。

[2026-04-25T20:58:04+08:00] Phase 4 manual-research request-contract hardening decision from local execution:
`Phase 4` 的第一轮 backend workflow hardening 现已收口到 `manual_research_requests` request contract。后续 `manual_llm_review` 的主语义必须从 request state 与 durable `manual_review` artifact 投影，而不是继续从 recommendation payload shell、旧 follow-up 执行路径或孤立 artifact 写盘行为反向推断。

补充说明
- `src/ashare_evidence/services.py` 现在必须优先通过 `build_manual_llm_review_projection(...)` 构建 `manual_llm_review`；只有在对象脱离 session 或无法读取 request/artifact 真相时，才允许回退到 compat shell。这样 recommendation summary、dashboard detail 与 follow-up `research_packet` 会共享同一套 request/artifact 语义来源。
- `src/ashare_evidence/llm_service.py` 的 `run_follow_up_analysis(...)` 现已改为委托 `src/ashare_evidence/manual_research_workflow.py` 的 compat wrapper，旧的“直接解析 API key 并即时写 artifact”路径不再是主入口；`/analysis/follow-up` 因而降级为 operator-only compat trigger，稳定工作流改由 `/manual-research/requests`、`/execute`、`/complete`、`/fail`、`/retry` 这一组 API 承载。
- `src/ashare_evidence/runtime_config.py` 已新增 builtin executor 配置入口，`src/ashare_evidence/schemas.py`、`src/ashare_evidence/api.py`、`src/ashare_evidence/research_artifacts.py` 与 `src/ashare_evidence/dashboard.py` 也已同步补齐 `request_id / request_key / executor_kind / status_note / review_verdict / stale_reason` 等字段，确保 request、artifact、dashboard projection 与 compat response 之间不再各自发明一套状态语义。
- 新增 `tests/test_manual_research_workflow.py` 专门锁住“request/artifact projection 优先于 payload shell”的规则，`tests/test_runtime_config.py` 也补强了 compat response 和 persisted artifact 上的 `request_id / request_key / executor_kind` 断言；此外，`tests.test_dashboard_views`、`tests.test_traceability`、`tests.test_analysis_pipeline` 与 `tests.test_research_artifact_store` 已重新全绿，证明本轮 Phase 4 后端 contract 收口没有回归到 Phase 2/3 artifact consumer。

[2026-04-25T21:15:45+08:00] Phase 4 queue/workspace productization decision from local execution:
从这一轮起，`Phase 4` 的产品层人工研究入口正式以 `manual_research_requests` lifecycle 为主语义。前端 follow-up workspace、stock detail 人工研究层与 operations governance queue/workspace 都必须直接消费 request/artifact contract，而 `/analysis/follow-up` 只保留兼容触发器角色，不再作为用户心智中的“主工作流”。

补充说明
- `src/ashare_evidence/operations.py` 与 `src/ashare_evidence/schemas.py` 现已新增 `manual_research_queue` payload，治理页需要同时展示 queue counts、focus request 和 recent request items，确保 operator 能在总览层看到 queued / in_progress / failed / completed_current / completed_stale 的真实分布，而不是只看单票 `manual_llm_review` 摘要。
- `frontend/src/types.ts`、`frontend/src/api.ts` 与 `frontend/src/App.tsx` 现在必须把“提交人工研究”建成 request workflow：允许先创建 queued request，再按选定 key 执行，也允许在治理页和 follow-up workspace 对 queued / failed / stale request 执行或 Retry；直接把 follow-up 当成一次性文本调用的交互不再符合主产品 contract。
- `manual_llm_review`、follow-up `research_packet` 和 operations queue/workspace 的展示字段必须继续保持同构，至少同步暴露 `request_id / request_key / executor_kind / status_note / review_verdict / stale_reason / citations` 这一组 request/artifact 语义字段，避免不同页面重新发明各自的人工研究状态词典。
- Phase 4 在 backend hardening 之外现已完成 queue/workspace 的端到端 productization；后续剩余工作收缩为 operator approval boundary、explicit complete/fail governance action 和 stale-state UX polish，而不再是“前端尚未接线”的大面问题。

[2026-04-26T21:11:56+08:00] Live manual-research long-request timeout decision from local execution:
manual research 相关前端请求不再允许沿用全站统一的 10s 短请求超时。只要入口的默认动作会触发本机 Codex builtin `gpt-5.5` 或其他真实长耗时研究执行器，这条链路就必须被视为 long-running request，并使用独立的 request timeout policy；否则真实已开始执行的 builtin 研究会被前端先行误判成失败。

补充说明
- `frontend/src/api.ts` 现已将 `createManualResearchRequest`、`executeManualResearchRequest`、`retryManualResearchRequest` 和 `runFollowUpAnalysis` 切到专用 `manualResearchRequestBehavior`，统一使用 `180000ms` 总超时和 `60000ms` attempt 超时，而普通 dashboard/settings/candidate 请求仍保留原有短超时策略。
- 这条决策已经过真实 canonical 浏览器验收：Safari 在 `https://hernando-zhao.cn/projects/ashare-dashboard/` 的 `单票分析 -> 追问与模拟` 页面上成功触发默认 builtin 研究，页面在跨过旧的 10s 故障阈值后未再出现“请求超时（>10s）”，而是继续执行直至返回回执。
- 当轮 live 观察里页面一度显示 `结果过期`，并带出 `validation_artifact_id changed after the manual review completed`；但 2026-04-26 同日晚些时候已确认这是 request list 使用未水合 `historical_validation` 空壳做 stale 判定导致的误报，而非真实 artifact drift。timeout 缺口仍然是在这次验收里被独立关闭；后续 stale 语义只应在 hydrated validation context 下继续判断。

[2026-04-29T10:19:14+08:00] Pydantic v2.13 forward-reference repair:
在 schema 模块拆分后，`from __future__ import annotations` + TYPE_CHECKING 导致 Pydantic 运行时解析 `StockDashboardResponse` 等模型时抛出 `class-not-fully-defined`，大盘首页和运营复盘返回 500。按依赖图逐文件修复：无循环依赖的模块直接移除 future annotations；存在 `stock → operations → simulation` 循环的模块保留 annotations，通过 `__init__.py` 在所有模块加载后注入类型并 `model_rebuild()`。

[2026-04-29T10:19:14+08:00] 403 auth transparency:
用户看到的 "403 Forbidden" 无任何可操作信息。三层修复：(1) VPS 代理 JSON 401/403 响应从 `error` 改为 `detail` key，前端即展示中文提示；(2) 后端 env 显式 `ASHARE_BETA_ACCESS_MODE=open`；(3) `access.py` 移除 future annotations。

[2026-04-29T10:19:14+08:00] Scheduled 5-min market refresh + holiday awareness:
`run-scheduled-refresh.sh` 无调度器触发。创建 LaunchAgent `StartInterval=300` 每 5 分钟执行；修正开盘窗口 09:31/13:01；增加 AKShare 交易日检查（日级缓存 ~/.cache/codex/trade_calendar.json），节假日自动跳过。

[2026-04-29T10:19:14+08:00] SSH tunnel auto-recovery:
`buildRemoteCleanupScript()` 的 `.join("; ")` 导致 bash 出现 `do;`/`then;` 语法错误，远端端口清理失败，隧道断开后无法重连。改用字符串拼接 + 增加 bash `-n` 语法测试 + 无限重连循环（指数退避 1s→60s）+ cleanup 5 次重试。

[2026-04-29T23:40:00+08:00] `/stocks` multi-account isolation v1 contract:
股票看板本期正式采用“根域身份注入 + 本地账号空间隔离”的 v1 合同，而不是在项目内再造一套账号系统。可信身份主键先固定为 root-domain `login`；root 域只需向 `/stocks` 注入 `X-HZ-User-Login` / `X-HZ-User-Role`，股票项目负责基于 `StockAccessContext` 做 `actor_login / actor_role / target_login` 解析，并只允许 root 通过 `X-Ashare-Act-As-Login` 查看或代操作其他账号空间。

补充说明
- watchlist 不再直接把 `watchlist_entries` 当“谁关注了它”的真相源，而是拆成“全局 symbol 覆盖/分析状态表” + `watchlist_follows(account_login, symbol)` 关注关系表。日更/分析续航继续按全部 active follows 的并集决定，所以只要仍有任一账号关注，symbol 级缓存预热和分析刷新资格就不能断。
- simulation 改为按 `owner_login` 隔离 session / portfolio / order / fill / event，并额外记 `actor_login` 审计 root 代操作。既有共享 session、组合、订单、成交和事件全部一次性回填到 `root` 账号名下；迁移不重建 session，不改 `started_at/current_step/restart_count/last_data_time`，确保 root 旧复盘不重新计时。
- v1 明确把 settings / operations / manual-research / `/analysis/follow-up` 视为 root 全局资产；member 只保留自己的首页、自选、单票和模拟盘空间。前端因此必须先拉 `/auth/context` 再决定是否请求 `/settings/runtime`，否则 member 登录会直接打到 403。

[2026-04-26T21:11:56+08:00] Live manual-review sanitization fallback decision from local execution:
人工研究层对外展示的文案必须把内部治理 token 视为不可信输入。只要 manual review summary、risk、disagreement、decision note 或回执 answer 仍可能来自历史 artifact、compat payload 或运行时拼接，前后端都必须各自保留一层用户可见净化兜底，不能假设“后端已经完全清洗过一次”就足够。

补充说明
- `src/ashare_evidence/manual_research_contract.py` 现已继续扩展内部 token 清洗范围，覆盖 `pending_rebuild`、`Phase 5 baseline`、`replay-alignment:*`、`portfolio-backtest:*` 等词；`frontend/src/App.tsx` 同步保留 display-layer fallback，把剩余漏网词替换为用户可理解的研究语言。
- 这次 live 验收的真实页面已确认显示 `口径校准中`、`20日超额收益` 等净化后的文案，没有重新漏出 `pending_rebuild` 一类内部状态词；对应静态回归已补进 `tests/test_dashboard_views.py`。
- 这条决策不改变后端 contract 优先级。后端 projection 仍是主净化层；前端 fallback 的职责只是兜住历史 artifact、compat 漂移和未来漏网字段，避免用户先看到内部术语再等待下一轮发布修复。
