# 一个关于a股的当前数据和投资建议看板 Research Notes

## 2026-04-27 producer contract study、runtime publish 与浏览器复验

### 当前结论
- `missing_news_evidence` 的上游 contract 已不再只停在“待研究”的状态。repo 研究库上的 Phase 5 producer study 现在给出了可执行结论：当前最窄且最稳妥的替代方案是 `watch_ceiling_keep_penalty`，而不是继续维持 missing-news-only case 的硬性 `risk_alert` 覆盖。
- 这条 contract 已经完成代码落地、runtime publish、runtime DB refresh 和浏览器复验。当前 localhost 与 canonical served 页面都能看到同一件事：`600522.SH` 的模型原始方向已经是偏积极，但公开表达仍被 `claim_gate` 收口为 `仅观察 / 继续观察`。这说明 live runtime 现在既没有回到旧的硬性 producer abstention，也没有越过 validation gate 提前 promotion。
- 因此，当前 Phase 5 主 blocker 又收敛了一层。它不再是“producer 是否把缺新闻 case 全打成 risk_alert”，而是“post-change 的真实 runtime evidence 仍然太薄，holding-policy / horizon 还没有积累出足够宽的样本”。

### repo 研究库上的 producer-contract study 读数
- 新增 study artifact surface：`phase5_producer_contract_study`，支持 history/latest 两种 selection mode，并把结论写入 `data/artifacts/studies/`。
- 在 repo 研究库的 history scope 上，四个变体的关键区别是：
  - `current_hard_block`: 基线 long supply 最少。
  - `remove_hard_override_keep_penalty`: 能恢复 long supply，但会把一部分 missing-news-only case 直接推成 `buy`。
  - `watch_ceiling_keep_penalty`: 同样恢复 long supply，但 missing-news-only case 最多只到 `watch`，不直接暴露为 `buy`。
  - `remove_hard_override_and_penalty`: 恢复幅度最大，但 claim risk 也最大。
- 当前 study 决策因此落在 `watch_ceiling_keep_penalty`，理由是“恢复 deployable supply，但不放宽到 missing-news-only 直接 `buy`”。这和当前产品的 honesty / non-promotion 目标更一致。

### runtime 发布与 refresh 后的现状
- 代码发布通过临时干净快照 repo `/private/tmp/stock-dashboard-producer-contract-publish-zmbkZM/repo` 执行。`scripts/publish-local-runtime.sh` 的 build、runtime sync、LaunchAgent restart、localhost health 和 served asset parity 均通过。
- 自动 release verifier 没有完全绿灯，但它当前失败在 `/dashboard/operations` 的 fingerprint compare 上；进一步对比后，local/canonical 归一化 payload 的唯一差异是 `data_latency_seconds`，不是语义字段漂移。
- runtime DB 随后执行 `phase5-daily-refresh --analysis-only` 后，关键读数更新为：
  - `600522.SH.latest_generated_at = 2026-04-27 16:35:49`
  - `600589.SH.latest_generated_at = 2026-04-27 16:36:12`
  - latest/history horizon artifacts 当前都从 runtime 视角给出 `consensus_front_runner`，frontier 为 `40d`
  - 但 holding-policy 仍是 `phase5-holding-policy-study:auto_model:no_included_dates:0portfolios`，`gate_status=draft_gate_insufficient_evidence`
- 这说明 producer change 已经进入 runtime，但还没有自动把 holding-policy 研究从 “几乎无组合样本” 推进到可 promotion 的阶段。

### 浏览器复验结果
- Safari localhost `http://127.0.0.1:5173/`：`600522.SH` 在候选表与单票页中都显示 `继续观察`，并带 `模型原始方向：偏积极`、`对外表达：仅观察`、`样本 146 · RankIC -0.15 · 正超额 +76.7%`、`最近分析 04/27 16:35`。
- Safari canonical `https://hernando-zhao.cn/projects/ashare-dashboard/`：与 localhost 保持一致，说明这次不是只改了 repo 或 localhost runtime，而是真正进入了用户实际入口。

### 直接含义
- 后续 Phase 5 主线不应再把“是否需要放松 missing-news hard block”当作首要问题，这一步已经实现并发布。
- 下一步更值得追的是 post-change evidence formation：随着更多 `as_of` 日期累积，deployable `buy/watch` 覆盖、horizon frontier 稳定性、holding-policy included portfolio count 是否真正改善。

## 2026-04-27 接手“继续评估股票专业性”会话后的现状诊断

### 当前结论
- 当前“专业性”主问题已经不再是前端是否还在直接泄漏 placeholder 或 raw gate token。`claim_gate`、explanation normalization 和 abstention contract 已经在 durable docs、代码和 live publish 记录里对齐，说明页面的诚实表达层基本收口完成。
- 当前更深层的专业性短板分成两层：一层是真实研究 evidence 仍受 universe 过窄、自动持仓部署过薄、primary horizon 未批准所限制；另一层是此前 live runtime 没有在本地生成 Phase 5 研究 artifact，导致页面一度夹着 runtime data drift 的扭曲。后一层已通过 runtime `phase5-daily-refresh` 和调度脚本修复，但前一层仍然成立。换句话说，现在阻碍产品进一步接近“可较强依赖的决策支持系统”的，不是措辞，而是“研究证据仍偏薄，且仍不能 promotion”。

### 接手后重新核对到的事实
- 当前仍存在两个不能混用的数据库视角。repo 研究库 `/Users/hernando_zhao/codex/projects/stock_dashboard/data/ashare_dashboard.db` 的 active watchlist 只有 `3` 只股票：`002028.SZ`、`002270.SZ`、`600522.SH`；真实服务中的 runtime 库 `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db` 还有第 `4` 只 active 股票 `600589.SH`。这不是研究结论波动，而是 publish 流程显式 `--exclude data` 导致 code/runtime 会同步、数据库不会随发布同步。修复后的重点不再是“runtime 完全缺 artifact”，而是“repo/runtime universe 仍不同，任何结论必须标明所用 DB”。
- 这 `3` 只 active symbols 虽然在 `2026-04-07` 到 `2026-04-27` 之间几乎每天都有 recommendation 生成，但 recommendation 分布明显偏向 `risk_alert/watch`。其中 `002028.SZ` 只有少数日期转成 `buy`，`002270.SZ` 主要停留在 `watch` 或 `risk_alert`，`600522.SH` 大部分日期也保持 `risk_alert`，只在少数日期转成 `buy`。
- 如果按“每只股票、每个 as-of date 只保留最后一条 recommendation”重算当前 active universe 的有效方向分布，那么 `2026-04-07` 到 `2026-04-24` 这 `14` 个 symbol-days 里，`risk_alert=31`、`buy=5`、`watch=4`、`reduce=2`。其中 `2026-04-08`、`2026-04-09`、`2026-04-10`、`2026-04-13`、`2026-04-15`、`2026-04-16`、`2026-04-17`、`2026-04-24` 都是三只股票全体 `risk_alert`；只有 `2026-04-20` 到 `2026-04-23` 这四个交易日，`002028.SZ` 稳定为 `buy`、`002270.SZ` 稳定为 `watch`、`600522.SH` 仍为 `risk_alert`。这说明“near-empty deployment”首先是 long-direction supply 本身极薄，而不只是持仓参数过严。
- latest recommendation 的 validation payload 已经具备 `artifact_id / manifest_id / coverage_ratio=1.0 / sample_count=83 / full_baseline walk_forward` 这类基础研究信息，因此 `P1.3 claim gate` 当前把公开方向压到 `observe_only` 的主要原因，不是 artifact 缺失，而是 validation status 仍是 `research_candidate` 而非 `verified`。这一点与 `services.py` 当前硬门槛一致：只要 validation 未进入 `verified`，就不得放开 stronger public claim。
- 上面这条“已有 artifact / sample_count / coverage_ratio”的判断最初只对 repo 研究库成立；接手后已对 runtime 服务库补跑 `phase5-daily-refresh --skip-simulation`，runtime 现在有 `8` 条 recommendation，且 recommendation payload 均带 `historical_validation.metrics`。因此 live 页面现在显示的 `research_candidate / observe_only` 更接近真实专业性语义：有 artifact-backed 观察证据，但未达到 verified 或 promotion。
- `phase5-horizon-study:latest:active_watchlist:2026-04-24:3symbols` 仍只覆盖 `3` 个 symbols、`1` 个 as-of date。当前结论依然是 `split_leadership`：`10d` 领先 `2` 个 symbol、`20d` 领先 `1` 个 symbol、`40d` 明显劣后。因此 horizon 研究目前更适合被理解为“还没收敛”，而不是“已经证明某个主周期成立”。
- `phase5-holding-policy-study:auto_model:2026-04-24:3portfolios` 的 decision 继续显示 `draft_gate_blocked`，而 primary fail gate 仍是 `positive_after_cost_portfolio_ratio`。同时，两个已落 artifact 的 redesign experiments 也进一步证实：当前更大的 blocker 不是简单调阈值，而是 recommendation coverage / deployed exposure 太薄，导致组合在 `736` 个 trade days 的回放窗口里大部分时间几乎接近空仓。
- 继续下钻 `holding_policy_experiments.py` 后可以确认，experiment timeline 里的 `candidate_count` 只是“这天有几只股票存在可用的最新 recommendation”，并不等于“这天有几只股票满足入仓方向”。真正入仓要再经过 `PHASE5_LONG_DIRECTIONS = {'buy', 'watch'}`、confidence floor 和 board-lot sizing。当前 active universe 的空仓段并不是被 board-lot 卡住，因为 `002028.SZ / 002270.SZ / 600522.SH` 在当前 starting cash 与 `20%` cap 下都能形成 `>=100` 股的目标手数；真正的主因是大多数日子的最新 recommendation 方向本身已经落在 `risk_alert / reduce`。
- 继续下钻 recommendation producer 后，当前“方向为什么大量坍缩成 `risk_alert`”也已经有了更具体的代码级解释：`signal_engine_parts/base.py` 里的 `recommendation_direction(score, degraded)` 只要 `degraded=True` 就会无条件返回 `risk_alert`，不会继续区分 `buy / watch / reduce`。而在当前 active universe 的 `42` 个有效 symbol-days 里，只有 `11` 个完全没有 degrade flag；其余 `31` 个都被某种 degrade contract 覆盖，其中 `28` 个是 `["missing_news_evidence"]`，`2` 个是 `["market_data_stale"]`，`1` 个是 `["missing_news_evidence", "market_data_stale"]`。这说明当前 long-direction supply 的稀薄，不只是价格/事件原始分数天然偏弱，也与“缺少新增新闻证据时直接一刀切降成 risk_alert”的现行 contract 强相关。
- `2026-04-24` 这组当前最新有效 recommendation 还暴露了一个额外扭曲来源：三只 active 股票的最后一条 recommendation 实际都在 `2026-04-27` 才生成，相对 `2026-04-24 15:00` 的 as-of time 已经滞后约 `58` 小时，因此统一触发了 `market_data_stale`。其中 `002028.SZ` 和 `600522.SH` 的 price/news direction 仍是 `positive/positive`，但因为 stale flag 非空，最终对外方向仍被直接压成 `risk_alert`。这说明当前“最新 recommendation 供给很差”的表象里，至少混入了一部分“晚生成导致的统一降级”，不能直接把它全解释成模型基本面转空。
- 按这轮新落地的 same-`as_of_data_time` 选择语义重新回看 repo 研究库后，当前 active universe 的 `42` 个 symbol-days 实际应解释为：`missing_news_evidence=28`、`none=14`；而最新 `2026-04-24` 这一天的 `3/3` recommendation 在非-stale 版本下都已恢复为无 degrade flag，其中 `002028.SZ=buy`、`002270.SZ=watch`、`600522.SH=buy`。这说明当前 live 页面上“全部风险提示”的观感，已经不再能简单归因于 recommendation producer 当天供给太差，而必须拆出 runtime stale backfill、claim gate 和数据库漂移三层因素。
- `construction_max_position_count_sweep_v1` 这份 `5symbols` artifact 也不能被直接当成“当前 active watchlist 组合行为”的同义证据。artifact 的 `scope.symbols` 实际是 `["600519.SH", "000858.SZ", "000333.SZ", "688981.SH", "002028.SZ"]`，而不是当前 active watchlist 的三只股票。它仍能说明“单纯改 top-k / weight 无法解决近空仓”这一结构性问题，但不应被误读成当前 active universe 的一手部署快照。

### 2026-04-27 runtime research-data refresh 补跑结果
- 已直接对 runtime DB 执行 `PYTHONPATH=src python3 -m ashare_evidence.cli phase5-daily-refresh --database-url sqlite:////Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db --skip-simulation`，写出 latest/history horizon study artifact 和 holding-policy study artifact。
- runtime 当前 active watchlist 为 `002028.SZ`、`002270.SZ`、`600522.SH`、`600589.SH`，`/dashboard/candidates` 返回 `4` 只 artifact-backed 候选。Safari 本地和 canonical 页面均显示 `最近刷新 04/27 11:51`；前三只候选为 `继续观察 / 仅观察 / 研究观察中`，`600589.SH` 为 `偏谨慎`，页面同时显示样本量、RankIC 和正超额摘要。
- 这个结果把 live 页面从“像是完全缺 validation artifact”推进到“有 validation artifact，但只能 observe-only”。这对专业性是改进，因为它区分了“缺证据”和“有证据但未验证到可放大结论”。
- 但这仍不支持 promotion：runtime horizon artifact 只有 `3` 个 symbols / `1` 个 as-of date；holding-policy artifact 是 `phase5-holding-policy-study:auto_model:no_included_dates:0portfolios`，`gate_status=draft_gate_insufficient_evidence`。因此当前公开表达继续停在 `research_candidate / observe_only` 是正确的。

### 对下一步执行的直接含义
- 如果继续做“专业性整改”，默认主线不应回到 UI polish，而应继续沿 `docs/contracts/PHASE5_CREDIBILITY_REMEDIATION_PLAN.md` 的 `P0.1 / P1.1 / P1.2` 推进：先解决 after-cost profitability、primary horizon selection 和 sample / universe expansion。
- 当前最该追的问题不是“要不要把页面说得更专业”，而是“为什么 active watchlist recommendation supply 只能支撑 3-symbol / near-empty deployment 的研究状态”。在这个问题没有被拆清之前，继续优化 threshold / top-k 参数的解释力会很有限。
- 更具体地说，下一步研究应把“threshold/top-k redesign”降到第二优先级，先补三类一阶证据：`1)` active universe 为什么长期只产出极少数 `buy/watch`；`2)` 是否需要扩大 watchlist / regime coverage 才能让 horizon 与 holding-policy artifact 摆脱 3-symbol 视角；`3)` 当前 recommendation producer 是否过于容易在 real data 上退化成全体 `risk_alert`，从而让组合研究还没开始就先失去部署样本。
- 如果把上面的 producer 行为也纳入视角，那么 P0.1 的第一批根因排查不应只盯着 portfolio construction，还应优先核对两件事：`1)` `missing_news_evidence => degraded => risk_alert` 这条 contract 是否过度保守，以至于把“缺少新增事件”与“明确风险警报”混成同一输出级别；`2)` replay / latest recommendation 是否应把严重滞后的 backfill recommendation 直接当成当期有效方向，否则 late rerun 会把本来非负面的历史 observation 机械覆盖成 stale-driven `risk_alert`。
- 在继续用 live 页面判断“专业性”之前，runtime 服务库的 Phase 5 research-data rebuild 路径已经补上：调度脚本分析档现在必须跑 `phase5-daily-refresh --analysis-only`，不能只跑 `refresh-runtime-data`。但 publish 仍排除 `data/`，所以后续所有 repo/runtime 对比仍必须先标明 DB 视角；live 页面不再适合作为“缺 artifact”证据，但仍适合作为“artifact-backed claim gate 是否过度放大或过度压制”的验收面。

### 2026-04-27 latest-selection 语义核对与回归修正
- 这轮继续下钻后，`replay / dashboard / watchlist / operations / manual research / simulation` 确实都存在同一类风险：多个读取路径默认按 `generated_at desc` 直接取“最新 recommendation”，会让同一个 `as_of_data_time` 上晚到的 backfill version 覆盖原本更合理的版本。
- 当前已经把 selection contract 统一收口到 `src/ashare_evidence/recommendation_selection.py`：
  - 先按 `as_of_data_time` 折叠同日多版本；
  - 同一 `as_of_data_time` 下优先取不带 `market_data_stale` 的版本；
  - 只有当该 `as_of_data_time` 的所有版本都 stale 时，才退回到“这些 stale version 里 `generated_at` 最新的一条”。
- 已接入这套 contract 的入口包括：`services.py`、`dashboard.py`、`operations.py`、`watchlist.py`、`manual_research_workflow.py`、`simulation.py` 与 `phase2/replay.py`。这意味着“同日回补版本覆盖正常版本”的问题不再只修一处，而是至少在主要用户/运营/研究读取链上统一收口。
- 回归过程中还顺手暴露了两个重要事实：
  - `analysis_pipeline` 的原始 fixture 里，所谓 “fresh” recommendation 本身也已经带有 `market_data_stale`；所以如果没有显式构造一个 non-stale fresh version，系统按 contract 退回到“所有 stale 版本里取最新生成的一条”是预期行为，不是 bug。
  - `holding_policy` 当前 fixture 并没有触发 profitability/redesign gate。真实 fail gates 是 `included_portfolio_count`、`mean_turnover_ceiling` 和 `mean_rebalance_interval_days_floor`，因此当前 governance 更接近 `maintain_non_promotion_until_gate_passes`，而不是 `prioritize_policy_redesign`。这说明此前那条测试期望已经落后于当前 contract / fixture 真相。
- 针对这轮语义收口，已补/修的回归覆盖包括：
  - same-as-of stale backfill 不应再覆盖 dashboard candidate、stock dashboard、watchlist latest recommendation；
  - manual research request 选择 recommendation key 时应优先取 non-stale same-as-of version；
  - replay rebuild 在 same-as-of collapse 之后，如果历史只剩一条有效 observation，不应再错误地产生 replay artifact；
  - datetime 比较现在统一做 UTC comparable normalization，避免 naive / aware datetime 混排时报 `TypeError`。
- 当前针对这轮修正的目标回归已经通过：
  - `PYTHONPATH=src python3 -m unittest tests.test_traceability tests.test_dashboard_views tests.test_manual_research_workflow tests.test_simulation_workspace tests.test_analysis_pipeline`

### 对后续 Phase 5 诊断的新增含义
- latest-selection 这条语义修正已经把“晚到 backfill 覆盖有效版本”这个机械扭曲源先压掉了，因此后续如果 active universe 仍然长期只有极薄的 `buy/watch` supply，就更能确信问题主要在 producer contract 和 research scale，而不是 hydration 错选。
- 这轮在 Safari 对本地 `http://127.0.0.1:5173/` 和已登录标准入口 `https://hernando-zhao.cn/projects/ashare-dashboard/` 的刷新复看也进一步说明：selection 修复并不会自动把页面重新放宽成 `偏积极`。刷新后的真实页面上，`600522.SH` 与 `002028.SZ` 仍因 `claim_gate=insufficient_validation` 被压成 `风险提示`，但它们的 `当前触发点` 继续保留正向的 price-trend 解释。这证明本轮关闭的是 stale overwrite，而当前对外表达仍主要被 validation/claim gate ceiling 控制。
- `holding_policy` 当前默认 governance 仍是 “先维持 non-promotion，继续补证据”，说明要进入真正的 `prioritize_policy_redesign`，还需要先证明 profitability/redesign signals 持续而不是偶发。换句话说，P0.1 现在仍应先追 recommendation supply / exposure formation，而不是抢跑去重写全套 holding-policy narrative。

## 2026-04-26 builtin Codex manual research 默认执行语义

### 当前结论
- `manual research` 的默认 builtin 路径现在应当被理解为“本机 Codex executor”，而不是“一个未来可能接上的 server queue”。只要本机存在可用 `codex` CLI，用户在不选择模型 Key 的情况下提交请求，就应该直接得到一条 builtin `gpt-5.5` 分析结果，而不是只留下 `queued` 状态。
- 因此前端再继续写“留空仅排队、等待 operator 处理”已经是不正确语义；那会让真实产品能力和页面提示互相矛盾，也会让用户误判成功能还没做完。

### 本轮观察
- 本机 PATH 上原本的 `codex` 版本是 `0.120.0`，直接 `codex exec -m gpt-5.5` 会失败；App bundle 自带的 binary 已经更高，但页面默认走 PATH 时并不能自动受益。
- 把全局 CLI 升到 `0.125.0` 后，正常 PATH 下的 `codex exec -C /Users/hernando_zhao/codex/projects/stock_dashboard --skip-git-repo-check -s read-only -m gpt-5.5 -o <tmpfile> -` 已可完成最小调用，说明“本机起 Codex 进程做 builtin 研究”在这台机器上不是设想，而是已验证可用。
- `runtime_config.py` 当前 builtin 配置会优先解析 `shutil.which("codex")`，其次再找 `/Applications/Codex.app/Contents/Resources/codex`。这意味着只要 PATH 或 App bundle 有任一可执行器，manual research builtin 路径就应该视为 enabled。

### 研究含义
- Phase 4 manual research workflow 现在已经不只是在访问权限层面从 operator-only 放宽到了 beta write access，还在执行能力层面把默认 builtin executor 真正接通了。
- 后续如果用户再次看到 builtin 路径只返回 queued，应优先检查两类问题：一类是本机 Codex binary 不可用或版本过旧；另一类是前端/UI 仍残留旧 submit 逻辑或旧文案，而不是先假定“server 端 builtin executor 尚未实现”。

## 2026-04-26 标准入口与缓存语义修正

### 当前结论
- `?cb=20260426-1819` 这类 query 参数不应再被理解为“最新版入口”。它只是验收时临时绕过缓存的调试手段，如果用户长期保留旧 `cb` 链接，之后刷新反而可能继续命中旧 HTML。
- 正确目标应当是：标准入口 `https://hernando-zhao.cn/projects/ashare-dashboard/` 本身就尽量稳定切到最新发布，query 参数不承担版本分发职责。

### 当前代码收口
- `frontend/index.html` 现已加入 no-cache meta，显式告诉浏览器入口 HTML 不应做长期缓存。
- `frontend/src/main.tsx` 现已新增 release drift 自检。当前 bundle 会在启动、窗口聚焦、标签页重新变为 visible，以及每 `60` 秒一次的轮询时，以 `cache: "no-store"` 抓取当前 URL 的最新 HTML，并比较其中指向的 `assets/index-*.js` 与自己当前运行的 build。
- 若发现当前页面还跑着旧 bundle，前端会自动 reload 一次，从标准入口切回最新构建，而不是要求用户手动拼新的 `cb` 参数。本轮发布 manifest 为 `/private/tmp/stock-dashboard-publish-2NogWR/repo/output/releases/20260426T110821Z-f84d42681210/manifest.json`，并已在 Safari 直接打开不带参数的标准入口复看通过。

## 2026-04-26 运营复盘焦点/K线/研究入口行为澄清

### 当前结论
- 用户这轮看到的四个现象，不应再被混成一个“运营复盘还没修完”的模糊问题。它们实际分成两类：一类是确实需要修的交互/数据 contract 缺口，另一类是产品语义此前写得不够清楚。
- `焦点 K 线没有数据` 这条现在按产品 contract 收口为“intraday 优先、daily fallback 兜底”。也就是说，只要 symbol 在库里有日线，焦点 K 线就不应该再因为缺少 `5min` bars 而整块空白。
- `运营复盘 table 默认为什么只有几只股票` 这条当前真相是：表格展示的是 simulation workspace 的当前股票池，而不是全量候选或全量历史股票。默认情况下它跟随 active watchlist；如果 session/config 被显式改成 custom pool，就显示 custom pool。
- `manual research workflow is operator-only` 这条此前更多是权限边界错放。创建和首次执行人工研究请求本质上是写入/触发动作，不应和治理终态动作绑定到同一 operator-only 门槛。

### 数据与代码观察
- 当前真实库 active watchlist 是 `3` 只，但旧 simulation session payload 曾只保留 `2` 只 symbol；因此用户之前看到“为什么不是全都进表格”并不只是感受问题，而是 default watchlist scope 没有把 session payload 和 active watchlist 持续同步。
- `simulation.py` 现已补上 `watch_symbols_scope` contract。默认 `active_watchlist_default` 模式下，只要 active watchlist 增减 symbol，session workspace 就会自动同步；只有 custom scope 才允许继续偏离共享自选池。
- `App.tsx` 里的 focus 切换原先会改 `selectedSymbol`，从而触发 stock detail / operations 的整页 reload。现在焦点切换只更新 simulation config 里的 `focus_symbol` 并刷新 workspace，因此点击运营复盘行或 K 线切换不再等价于“全页面重选一只股票”。
- `api.py` 已把 manual research create / execute 放宽到 beta write access；operator-only 只保留 `complete / fail / retry`，因为这些动作会改写治理终态与 artifact 生命周期。

## 2026-04-26 运营复盘双轨表格 live 发布验收

### 当前结论
- 这条问题现在不应再归类为“repo 已修但是否上线未知”的开放项。`运营复盘` 双轨模拟台的轨道表格 containment 修复已经完成真实发布，并在 canonical 入口上做了登录后的浏览器复看。
- 当前远端验收 URL 为 `https://hernando-zhao.cn/projects/ashare-dashboard/?cb=20260426-1738`。在 Safari 登录后进入 `运营复盘`，`用户轨道` 和 `模型轨道` 表格均保持在各自卡片边界内，没有再出现旧的整页被表格横向撑开的现象。
- 这次验收同时验证了一个流程层事实：之前“刷新后还是旧问题”的主要原因不是用户误判，而是修复尚未真正发布或尚未在真实入口完成复看。

### 发布链补充观察
- 主 repo 当前工作区很脏，因此本次 live publish 通过临时干净 repo 快照执行 `scripts/publish-local-runtime.sh`；成功 manifest 为 `/private/tmp/stock-dashboard-publish-rsync-WyJZXt/repo/output/releases/20260426T093041Z-0f8fe79d90f6/manifest.json`。
- 发布过程中唯一需要额外收口的是 release verifier 对 runtime-only 性能数值过敏：`launch_gates[*].current_value`（限 `刷新与性能预算` gate）和 `performance_thresholds[*].observed` 会随环境抖动，因此已在 fingerprint normalization 中排除；真实语义字段仍继续参与 parity 校验。
- 这说明后续若再遇到“本地已修、远端仍旧”的情况，优先要检查的是 publish 是否实际完成、manifest 是否生成、以及 canonical 登录后的浏览器复看，而不是先怀疑历史记录缺失。

## 2026-04-26 全历史回退审计

### 审计结论
- 当前 repo 的 durable history 并没有丢。`PROCESS.md` 仍保留了多次“已修复后又回退”的关键记录，尤其是运营复盘文案与发布链路漂移问题。
- 全历史里至少能确认一类真实回退：`用户轨道 / 模型轨道` 的产品化修复曾在后续发布、sync 或 runtime 漂移中反复失效；这不是记忆误差，而是 `PROCESS.md` 已明确记为“第三次回退”的发布治理问题。
- 也能确认一类“看起来像回退、其实是 docs 落后”的情况：例如 Phase 5 simulation holding-policy contract 已切到 target-weight auto-execution research baseline 后，durable docs 一度还停留在 `withheld quantity preview` 叙述；这类问题属于合同文档漂移，而不是代码真正退回旧实现。
- 另有一类当前更应视为“从未被 durable 锁成专门修复”的遗留 UI 问题：运营复盘轨道内表格超出。当前 `frontend/src/App.tsx` 里的 `TrackHoldingsTable` 仍主要依赖 `scroll={{ x: 980 }}`，`frontend/src/styles.css` 也没有对应的专门 containment 规则，因此这更像是一个没有被完整锁定的反复暴露点，而不是已有明确 fix commit 后又被删掉。

### 分类结果
- `真实回退 / 漂移`
  - 运营复盘产品化文案与轨道语义曾反复回到 `运营复盘口径仍在迁移`、`Phase 5 baseline`、`research contract` 等旧词，根因是旧发布链只能证明 localhost 健康，不能证明 canonical route 和 runtime bundle 与 repo 同版。
  - 标准入口浏览器验收曾出现“本地代码已改、live route 仍看到旧 UI”的现象；后续通过 release verifier、asset parity、canonical acceptance artifact 才把这个问题收口为可验证流程。
- `docs 漂移，不是代码回退`
  - Phase 5 simulation holding-policy 研究合同升级后，docs 曾短暂保留旧 maintenance 叙述，造成“代码是不是回退了 honesty contract”的假象。
  - GitHub Pages / 在线 API / 离线快照等旧部署叙述仍保留在部分历史 research/decision notes 中，但 active docs 已改为 server-entrypoint + local runtime path；这属于历史上下文未删除，不应直接算当前实现回退。
- `未锁定修复，仍应按开放问题处理`
  - 运营复盘轨道内表格超出问题目前没有找到足够硬的专门 fix anchor、对应 CSS containment 方案或回归测试锚点。后续若修复，必须把 UI containment、浏览器验收与 durable 记录一起补齐，否则仍会继续在会话中反复出现“以为修过”的判断偏差。

## 2026-04-26 Phase 5 redesign experiment menu

### 当前 redesign 研究起点
- `phase5_holding_policy_study` 现已在 decision payload 里继续输出 `redesign_experiment_candidates / redesign_primary_experiment_ids`，不再只停留在 `redesign_focus_areas`。
- 当前 redesign diagnostic context version 已升级到 `phase5-holding-policy-redesign-diagnostics-draft-v2`，因为同一个 context 现在同时冻结 redesign signal rules 和 draft experiment menu。
- 对真实 snapshot `phase5-holding-policy-study:auto_model:2026-04-24:3portfolios`，当前 active focus areas 仍是 `after_cost_profitability` 与 `portfolio_construction`，但下一步研究入口已进一步收口为一组可回查 experiment ids，而不是抽象问题描述。

### 当前 experiment menu 含义
- `after_cost_profitability` 这条线当前收口到两个候选实验：`profitability_signal_threshold_sweep_v1` 与 `profitability_rebalance_hold_band_v1`。
- `portfolio_construction` 这条线当前收口到两个候选实验：`construction_max_position_count_sweep_v1` 与 `construction_deployment_floor_fallback_v1`。
- 当前 primary experiment ids 的选择规则是“每个 active focus area 先挑一个优先实验”。因此对当前 real snapshot，后续主线应优先从 `profitability_signal_threshold_sweep_v1` 与 `construction_max_position_count_sweep_v1` 开始做 redesign 对照研究。
- 这些 experiment ids 仍然只是 `Phase 5` 的 research candidates，不代表 operator 已批准新的正式持仓策略。

## 2026-04-26 Phase 5 redesign diagnostic readout

### 当前 redesign 结论
- `phase5_holding_policy_study` 现已在 decision payload 里继续输出 `redesign_status / redesign_note / redesign_diagnostics / redesign_triggered_signal_ids / redesign_focus_areas / redesign_context`，不再只停留在 `governance_action=prioritize_policy_redesign`。
- 当前 redesign diagnostic context version 为 `phase5-holding-policy-redesign-diagnostics-draft-v2`。
- 对真实 snapshot `phase5-holding-policy-study:auto_model:2026-04-24:3portfolios`，当前 redesign 结论已可以拆成两类 focus area：`after_cost_profitability` 与 `portfolio_construction`。

### 研究含义
- `after_cost_profitability` 对应的仍是当前已知 blocker：`mean_annualized_excess_return_after_baseline_cost=-12.849842` 与 `positive_after_baseline_cost_portfolio_count=0`。
- `portfolio_construction` 现在也被明确收口为独立 redesign signal，而不是附带观察。当前 real snapshot 的 `mean_invested_ratio=0.075433`、`mean_active_position_count=1.0` 说明这条 top-k equal-weight baseline 在真实样本下几乎没有形成有意义的资金部署和持仓覆盖。
- 后续 redesign research 应围绕这两类结构化 signal 展开：一类是 after-cost profitability 是否被改善，另一类是 portfolio construction 是否能把信号真正转成足够的持仓暴露，而不是继续把工作停留在 gate / governance 表达层。

## 2026-04-26 Phase 5 governance readout

### 当前 governance 结论
- `phase5_holding_policy_study` 现已在 decision payload 里继续输出 `governance_status / governance_action / governance_note / redesign_trigger_gate_ids / governance_context`，不再要求 consumer 自己从 `gate_status + failing_gate_ids` 反推默认治理动作。
- 当前 governance context version 为 `phase5-holding-policy-governance-draft-v1`。
- 对真实 snapshot `phase5-holding-policy-study:auto_model:2026-04-24:3portfolios`，当前默认治理结论是 `governance_status=maintain_non_promotion_prioritize_policy_redesign`，`governance_action=prioritize_policy_redesign`。

### 研究含义
- 当前 Phase 5 在 holding policy 这条线上，已经不需要再讨论“默认是不是继续 non-promotion”，因为默认治理结论已经被结构化写死在 artifact / CLI / operations 里。
- 真正剩下的主动研究工作变成：是否重做 policy 设计，以及重做后要用什么真实 evidence 才允许重新进入 promotion 讨论。

## 2026-04-26 Phase 5 draft gate readout

### 当前 gate 结论
- `phase5_holding_policy_study` 现已在 artifact 本体里输出 `gate_status / failing_gate_ids / incomplete_gate_ids / gate_checks / gate_context`，不再只给出 `approval_state`。
- 当前 draft gate version 为 `phase5-holding-policy-promotion-gate-draft-v1`，真实 snapshot `phase5-holding-policy-study:auto_model:2026-04-24:3portfolios` 的 gate 结论是 `draft_gate_blocked`。
- 当前显式 blocker 至少包括 `after_cost_excess_non_negative` 与 `positive_after_cost_portfolio_ratio`；换手与调仓间隔 guardrail 当前并不是首要阻断项。

### 研究含义
- 后续 Phase 5 工作不应再把 holding-policy baseline 视为“接近批准，只差一组阈值”，而应把它视为“已有明确 blocker 的 research candidate”。
- 这份 gate readout 目前仍只是研究诊断，不代表 operator 已批准自动 promotion 规则；它的作用是让 daily refresh、CLI 和 operations 能把“不晋级理由”稳定暴露出来。

## 2026-04-26 Phase 5 真实 holding-policy refresh snapshot

### 真实库日更结果
- 已执行 `PYTHONPATH=src python3 -m ashare_evidence.cli phase5-daily-refresh --database-url sqlite:///data/ashare_dashboard.db --analysis-only --skip-simulation`。
- 当前 real study artifact 为 `phase5-holding-policy-study:auto_model:2026-04-24:3portfolios`，生成时间 `2026-04-26T15:02:53.850463+08:00`。
- `operations` 总览已能直接读取该 artifact，说明 Phase 5 holding-policy 研究现在既有 typed durable artifact，也已有真实库 snapshot，而不再只是 fixture / ad-hoc evidence。

### 当前观察
- 样本纳入：`included_portfolio_count=3`，`excluded_portfolio_count=0`。
- 换手与调仓：`mean_turnover=0.25`、`rebalance_day_count=3`、`mean_rebalance_interval_days=10.5`、`mean_orders_per_rebalance_day=7.0`。
- 收益与成本：`mean_annualized_return=0.076467`，但 `mean_annualized_excess_return=-12.848967`，加入 baseline 成本后为 `mean_annualized_excess_return_after_baseline_cost=-12.849842`；`positive_after_baseline_cost_portfolio_count=0`。
- 持仓形态：`mean_active_position_count=1.0`、`mean_invested_ratio=0.075433`，说明当前 sample 下策略实际暴露较薄，尚不能把这条 baseline 包装成已具备产品级持仓研究结论。

### 当前研究含义
- 这份 snapshot 解决的是“真实库上到底有没有 holding-policy artifact”这个问题，答案现在是有。
- 但它同时给出了更重要的研究结论：当前 `phase5_simulation_topk_equal_weight_v1` baseline 并没有展示出足以支持 promotion 的 after-cost excess evidence。
- 因此后续 `Phase 5` policy work 不应把目标默认为“挑一组阈值让它通过”，而应先回答两件事：1) 是否需要 policy redesign；2) 如果暂不 redesign，promotion gate 应如何明确把当前 baseline 维持在 `research_candidate_only`。

## 2026-04-24 研究重置约束

### 新增约束
- 历史文档和代码里出现的 `2-8 周`、`14/28/56 天`、`15%`、固定置信阈值、固定回放口径、固定命中率规则，都视为旧假设，不再默认成立。
- 本轮深度改造要优先回答“什么窗口和口径在真实历史数据上更稳健”，而不是继续围绕旧窗口做工程化包装。
- 若低成本数据条件下无法证明某个窗口、某种建议粒度或某个融合占比具有稳定增益，则应收缩产品承诺，而不是保留该能力。

### 对研究阶段的直接影响
- 研究设计必须显式比较多个 horizon、多个标签定义和多个调仓频率，而不是只验证单一旧窗口。
- 所有展示给用户的周期、权重和阈值都要区分 `research_candidate` 与 `approved_for_product` 两种状态。
- 任何当前名不副实的“量化结论”在拿到真实实验产物前，都只能作为迁移占位，不得继续作为正式能力描述。

## 2026-04-24 官方方法论复核补充

### Qlib 工作流结论

- `Qlib` 官方工作流明确区分数据处理、训练、策略和回测模块，适合把“研究结论”和“产品展示”分层，而不是在产品接口里直接硬编码验证指标。
- `Estimator` 文档给出了 `RollingTrainer`、训练/验证/测试时间切片和 backtest 配置，说明滚动训练和时间切分应该是主路径，而不是随机切分或手工填入 validation 摘要。
- `Portfolio Strategy` 文档明确以预测分数驱动组合策略，再通过 backtest 检查策略表现；这更接近“排序分数 -> 组合动作 -> 风险分析”的结构，而不是“单票一句话建议 -> 命中率”。

参考来源
- Qlib Workflow / Estimator: <https://qlib.readthedocs.io/en/v0.5.1/component/estimator.html>
- Qlib Portfolio Strategy: <https://qlib.readthedocs.io/en/v0.9.6/component/strategy.html>

### 当前项目的直接含义

- 一期重建应优先采用“横截面排序/相对评分 + 滚动验证 + 真实 backtest + 风险分析”。
- 若只分析自选股，也应把目标股票放在相对框架里比较，而不是继续使用纯单票启发式阈值。
- 量化验证的最小闭环应包含：标签构造、滚动切分、策略映射、benchmark、成本和风险分析。

### Tushare 低成本数据约束复核

- `daily`、`daily_basic`、`fina_indicator`、`disclosure_date`、`anns_d` 等接口具备支撑低频自选股研究的基础能力，但权限和刷新时间并不统一。
- `fina_indicator` 对单票历史拉取友好，但如果要跨全市场做截面研究会碰到更高权限需求。
- `major_news` 和 `anns_d` 都属于更强权限或单独权限接口，这意味着“事件层”可以做，但应优先围绕官方公告和可追溯披露，不应默认承诺完整新闻覆盖。

参考来源
- Tushare 权限总览: <https://tushare.pro/document/1?doc_id=108>
- 财务指标 `fina_indicator`: <https://tushare.pro/document/2?doc_id=79>
- 财报披露计划 `disclosure_date`: <https://tushare.pro/document/2?doc_id=162>
- 全量公告 `anns_d`: <https://www.tushare.pro/document/2?doc_id=176>
- 新闻通讯 `major_news`: <https://tushare.pro/document/2?doc_id=195>

## 2026-04-14 数据与开源基线评估

### 决策摘要
- 一期研发和历史回测建议采用 `Tushare Pro + 巨潮资讯/交易所公告 + Qlib` 的低成本主路线。
- `AkShare` 适合做接口原型、字段探索和补缺回填，但不适合作为一期面向用户的主数据许可基座。
- 一期如果没有商业数据审批，不应把“新闻”定义为抓取来的媒体资讯，而应收缩为“官方公告、问询、互动平台、交易所披露”等可追溯事件流。
- 面向 2-8 周波段场景，建议建模目标改为 `10/20/40 个交易日 forward return / excess return 排序`，而不是预测某只股票的精确价格点位。
- 对外内测一旦扩展到非操作者用户，或者要展示媒体新闻/更高频数据，就必须进入商业授权闸门；否则只能维持内部研发或非常受控的小范围验证。

### 一期推荐技术路线

#### 1. 数据路线
- 行情、财务、板块基线：`Tushare Pro`
  - 适用范围：日线、复权、估值、财务指标、概念/行业/指数成分、交易日历等结构化字段。
  - 原因：A 股字段覆盖较全，接口统一，足够支撑自选股池和日级/延迟更新场景。
  - 限制：官方用户协议明确偏向研究学习用途，不宜默认外推到商业化、实盘或面向外部用户的强决策产品。
- 公告与事件证据：`巨潮资讯 + 交易所公开披露`
  - 适用范围：上市公司公告、定期报告、临时公告、问询回复等正式披露材料。
  - 原因：这是一期最稳妥的“新闻/事件”主证据源，来源权威、时间戳明确、便于证据回溯。
  - 限制：更适合作为事件因子和证据链接，不适合简单做全文再分发。
- 辅助原型工具：`AkShare`
  - 适用范围：快速试字段、补少量缺口、验证不同公开站点是否存在可用数据。
  - 限制：它是接口封装层，不是数据授权本身；上线前仍要回到原始来源和使用条款判断合法性。
- 商业升级候选：`Choice / Wind / Datayes / 巨潮数据服务`
  - 触发场景：外部内测、商业发布、媒体新闻接入、更高稳定性、分钟级甚至更高频刷新、需要正式商务合同与 SLA。

#### 2. 建模路线
- 主基线：`Qlib + LightGBM/XGBoost 横截面排序模型`
  - 目标：预测 10/20/40 个交易日的收益分位或超额收益分位，覆盖约 2-8 周波段。
  - 输入：价格量能、波动率、换手率、估值、财务质量、板块映射、公告事件标签、市场状态特征。
  - 输出：排序分数、方向桶、风险桶、证据摘要。
- 事件因子链路：公告/新闻先做 `去重 -> 实体映射 -> 发布时间对齐 -> 影响衰减 -> 分层归属`
  - 个股层：业绩预告、回购、减持、重大合同、诉讼处罚、定增重组、问询回复。
  - 行业层：政策、价格周期、供需变化。
  - 市场层：监管、流动性、风险偏好。
- LLM 角色
  - 允许：公告摘要、事件分类、冲突证据解释、候选因子生成。
  - 不允许：脱离结构化证据直接给最终结论。
  - 权重约束：历史评估稳定前，LLM 因子建议权重上限 `<= 15%`，且必须能单独回放。
- 回测与验证
  - 采用滚动时间验证，不使用随机切分。
  - 推荐窗口：`36 个月训练 + 6 个月验证 + 3 个月测试`，按月滚动。
  - 验收指标：方向命中、分组收益、最大回撤、换手、阶段稳定性、交易成本后收益、行业暴露偏移。

### 数据源评估

| 来源 | 类别 | 公开价格/付款模式 | 优点 | 主要风险 | 一期建议 |
| --- | --- | --- | --- | --- | --- |
| `Tushare Pro` | 行情/财务/板块/部分公告与资讯 | 官网公开年费积分档；示例档位包含 `500 元/年 120 积分`、`2000 元/年 5000 积分`、`5000 元/年 10000 积分`；部分模块单独收费 | A 股字段广、Python 生态友好、适合回测与特征工程 | 协议对商业用途和实盘用途限制明显；模块权限碎片化 | `推荐作为研发主线，不推荐直接视为对外上线授权` |
| `AkShare` | 多站点公开数据接口封装 | 开源免费，MIT 代码许可证 | 原型快、字段多、探索效率高 | 不是数据许可本身；上游站点稳定性和权利边界不统一 | `仅作辅助，不作主源` |
| `巨潮资讯` | 官方公告/报告/披露 | 官网公开站点免费；数据服务平台需商务洽谈 | 权威、时间戳清晰、证据可追溯 | 更适合作证据链接和事件抽取；商业再分发边界需单独确认 | `推荐作为一期事件主证据源` |
| `巨潮数据服务` | 官方数据 API / SDK | 官网未公开标准价，商务咨询/试用模式 | 官方授权路径清晰，适合作为公告与披露升级源 | 价格不透明，需要谈判和字段确认 | `推荐作为公告商业升级首选` |
| `Choice 数据` | 企业级行情/财务/资讯 | 官网未公开标准价，试用/销售询价 | A 股覆盖完整，适合企业采购 | 预算不透明，模块采购复杂 | `推荐进入商务比价清单` |
| `Wind` | 企业级行情/财务/资讯/终端 | 官网未公开标准价，销售询价 | 市场覆盖和机构认可度强 | 成本通常最高，采购周期长 | `适合作为高预算上限方案` |
| `Datayes` | API/数据服务/私有化 | 官网未公开标准价，试用+商务模式 | API 和私有化能力较强，工程接入友好 | 仍需单独确认 A 股字段、新闻和授权边界 | `适合作为中间价位候选` |

### 价格与付款模式结论
- `Tushare Pro` 是唯一能在官网直接拿到相对明确标准价的主候选，适合做研发/回测/低成本验证。
- 企业级供应商普遍采用 `试用 -> 方案沟通 -> 模块报价 -> 年度合同/私有化` 的付款模式，官网通常不公开标准价。
- 如果操作者希望一期继续坚持低成本，最现实的做法不是“找另一个免费新闻源”，而是把产品口径收缩到 `官方公告事件 + 延迟行情 + 结构化因子建议`。
- 如果操作者坚持一期就要做“更像投顾的新闻+建议”并对外展示，那么应直接准备商业数据审批，而不是继续投入时间在抓取型免费源上。

### 开源项目筛选

#### 推荐纳入一期研发栈
- `microsoft/qlib`
  - 用途：数据集组织、因子工程、模型训练、实验管理、回测分析。
  - 选择理由：对中国市场支持成熟，适合滚动训练和多模型实验。
- `cloudQuant/alphalens`
  - 用途：单因子 IC、分层收益、换手和风险暴露分析。
  - 选择理由：适合评估新闻/公告因子是否真正有效。
- 自建 A 股模拟交易模块
  - 原因：一期需要明确区分“手动模拟”和“按模型组合自动持仓”，并补齐 `T+1`、涨跌停、停牌、最小交易单位、交易成本等 A 股规则。

#### 可作为参考，但不建议直接成为一期主干
- `backtrader`
  - 优点：成熟、易上手。
  - 不足：A 股规则仍需大量自定义；GPL 许可证也需要在分发边界上谨慎处理。
- `rqalpha`
  - 优点：中国市场语义更强。
  - 不足：官方仓库声明偏向非商业使用，不适合作为后续对外产品的默认底层。
- `FinGPT`
  - 优点：适合做公告/新闻摘要和实验性 LLM 因子。
  - 不足：不应在一期成为主建议引擎；先做离线历史增益验证更稳妥。

### 成熟建模方案筛选

#### 推荐方案 A：横截面收益排序
- 标签：`10/20/40 个交易日超额收益`。
- 模型：`LightGBM` 优先，`XGBoost` 作为对照。
- 优点：可解释性和稳健性都优于直接价格回归，适合自选池候选排序与单票建议。

#### 推荐方案 B：事件增强型排序
- 在方案 A 基础上增加事件与情绪特征。
- 事件值采用 `发布时间衰减 + 来源权重 + 层级映射 + 去重哈希`。
- 适用于公告驱动、热点轮动和政策冲击场景。

#### 暂不推荐作为一期主基线
- 纯深度学习价格点预测：更容易过拟合，解释性差。
- 强化学习直接交易策略：调参与验证成本高，不适合当前阶段。
- 直接让 LLM 输出买卖建议：证据绑定和历史校准不足，合规风险高。

### 数据适配层设计

#### 适配器接口
- `fetch_quotes(symbols, start, end, freq, adjust)`
- `fetch_fundamentals(symbols, report_periods, fields)`
- `fetch_sector_memberships(symbols, asof_date, taxonomy)`
- `fetch_events(symbols, start, end, event_types)`
- `fetch_news_items(symbols, start, end, source_scope)`
- `fetch_calendar(exchange, start, end)`
- `fetch_corporate_actions(symbols, start, end)`

#### 标准化字段
- 每条原始记录必须带上：
  - `provider`
  - `provider_dataset`
  - `source_uri`
  - `source_license_tag`
  - `usage_scope`
  - `redistribution_scope`
  - `published_at`
  - `ingested_at`
  - `asof_at`
  - `lineage_hash`
  - `raw_payload_ref`
- 这些字段是一期建议回溯、合规审计和供应商切换的基础，不应后补。

#### 存储分层
- `raw_ingest`: 原始响应和网页抓取快照。
- `normalized_core`: 标准化后的 bars、fundamentals、sector、events。
- `feature_store`: 可回放的因子快照。
- `model_registry`: 模型版本、训练窗口、指标、阈值。
- `recommendation_log`: 建议文本、结构化证据、提示词版本、置信表达。

### 升级触发条件
- 出现任何非操作者外部测试用户，或开始考虑收费/商用。
- 需要展示媒体新闻全文、摘录或更广泛资讯，而不仅是公告事件。
- 刷新频率提升到分钟级，或股票池扩大到需要更高吞吐和 SLA。
- 免费源日缺失率持续 `> 0.5%`，或字段结构月度漂移频繁影响生产。
- 需要更严格的点位时序一致性、正式合同、账单、审计和售后支持。

### 授权与合规风险清单
- 免费/社区数据常常解决的是“能拿到数据”，不是“可以合法展示和分发数据”。
- `Tushare Pro`、`rqalpha`、部分终端产品公开协议都对商业或非个人用途有限制，不能直接假设满足后续产品化。
- 媒体新闻版权风险高于公告数据；没有商业授权时，应避免存储和对外展示全文。
- 产品定位已明确偏向更强决策支持，需尽早按更高标准设计：
  - 用户白名单与访问控制
  - 每条建议的证据留档和版本留档
  - 风险揭示与非收益承诺表达
  - 手动模拟与自动持仓分开留痕、分开验收
  - 对冲突信号和证据不足情形的强制降级
- 需要重点复核的监管文本包括：
  - `证券投资顾问业务暂行规定`
  - `发布证券研究报告暂行规定`
  - `证券期货投资者适当性管理办法`

### 一期最终建议
- 若预算暂不审批：按 `Tushare Pro + 巨潮公告事件 + Qlib` 落地研发与数据底座，同时把产品文案和交付范围限定为受控内测、延迟更新、公告事件驱动建议。
- 若操作者坚持一期就覆盖更完整资讯和更强建议：不要继续打磨免费新闻抓取，应直接进入商业数据询价和授权审查。
- 无论走哪条路线，第二步数据底座都必须先把授权字段、证据链、滚动验证和降级机制做进系统骨架。

## 2026-04-15 证据化数据底座实现备注

### 具体落地
- 已用 `FastAPI + SQLAlchemy` 落地证据化后端骨架，覆盖 `行情 / 新闻 / 板块 / 特征 / 模型结果 / 提示词版本 / 建议记录 / 模拟交易 / 采集运行`
- 每类核心记录都带有 `license_tag`、`usage_scope`、`redistribution_scope`、`source_uri`、`lineage_hash`
- 当前通过 `DemoLowCostRouteProvider` 写入 `600519.SH` 的完整样例链路，并可从 recommendation trace 反查到原始行情、公告、特征、模型和模拟成交

### 实现取舍
- 证据链接没有直接做多态外键，而是使用 `recommendation_evidence(evidence_type, evidence_id)` 统一挂载
  - 原因：证据类型横跨行情、新闻、特征、模型结果和板块归属，多态外键在 SQLite/Postgres 兼容层面不够经济
  - 代价：trace 查询需要服务层做 artifact resolver
- `lineage_hash` 改为基于完整规范化记录生成，而不是仅对局部 payload 取 hash
  - 原因：否则同类记录容易因为共享 payload 模板而得到同一 hash，削弱审计粒度
- 真实外部 provider 暂未联网接入，优先先把 schema 和 contract 固定
  - 原因：当前步骤的首要目标是“可回溯底座”，不是“真实信号优劣”

### 对第 3 步的建议
- 优先补真实 `Tushare / 巨潮 / Qlib` 适配器，保持输出结构与 `DemoLowCostRouteProvider` 一致
- 建立 `feature_snapshot` 与 `model_run/model_result` 的真实滚动训练产物，不要在第 3 步直接绕过第 2 步表结构落临时 CSV
- 在建议融合前，先补“证据不足 / 信号冲突 / 数据延迟”的降级规则和阈值配置

### 参考来源
- Tushare 官网与文档：<https://tushare.pro/>、<https://tushare.pro/document/1?doc_id=290>
- AkShare：<https://github.com/akfamily/akshare>、<https://akshare.akfamily.xyz/>
- 巨潮资讯与数据服务：<https://www.cninfo.com.cn/>、<https://webapi.cninfo.com.cn/>
- Choice 数据：<https://choice.eastmoney.com/>
- Wind：<https://www.wind.com.cn/>
- Datayes：<https://www.datayes.com/>
- Qlib：<https://github.com/microsoft/qlib>、<https://qlib.readthedocs.io/>
- Alphalens：<https://github.com/cloudQuant/alphalens>
- Backtrader：<https://github.com/mementum/backtrader>
- RQAlpha：<https://github.com/ricequant/rqalpha>
- FinGPT：<https://fingpt.ai/>

## 2026-04-15 信号建模与建议引擎实现备注

### 本轮实现结论
- demo 链路已从“静态 recommendation 样例”升级为“原始行情/新闻证据 -> 因子 -> 融合建议”的可执行结构。
- 当前推荐的最小可替换架构是：
  - `price_baseline_factor` 负责 2-8 周波段的价格与量能基线
  - `news_event_factor` 负责去重、层级映射、发布时间对齐和衰减后的事件打分
  - `llm_assessment_factor` 负责证据整合和有限度加权，必须绑定历史评估摘要
  - `fusion_scorecard` 负责权重、冲突惩罚、降级触发和最终方向输出
- recommendation 输出层已经显式包含方向、置信表达、核心驱动、反向风险、适用周期、更新时间、降级条件、因子拆解和验证快照。

### 本轮取舍
- 当前 `model_run.metrics_payload` 中的滚动验证指标与 `LLM_FACTOR_EVALUATION` 仍是 demo/offline contract，而不是实时从历史数据库重算
  - 原因：当前沙箱没有真实 `Tushare / 巨潮 / Qlib` 联网接入，也没有完整历史训练集
  - 好处：先把验证数据结构、权重治理和降级机制固化，后续接真实回测时不会推翻接口
- LLM 因子被限制为 `<= 15%` 的 capped weight
  - 原因：已知目标要求是“LLM 可作为因子，但若增益不稳定不得占主导权重”
  - 当前实现：如果历史 lift 或稳定性跌破阈值，LLM 因子会自动退回解释层
- recommendation 主结果仍保留 `14/28/56` 天三个 horizon
  - 原因：一期场景是 2-8 周波段，不能只给单一 horizon；当前 recommendation 以 28 天作为主解释窗口，14/56 天保留在 model results 中

### 对下一步的建议

## 2026-04-15 验收返修记录

### 本轮结论
- 本轮拒绝验收的根因不是页面样式本身，而是前端对在线 demo API 的硬依赖使 GitHub Pages 部署无法形成最小可用闭环。
- 在当前约束下，最稳妥的返修方式不是补另一套前端 mock，而是把现有 `dashboard` / `operations` contract 直接导出为前端离线快照，再由页面在在线 API 失败时自动回退。
- 这种方式能保留现有 schema、推荐解释链路和运营面板 contract，同时给验收方一条不依赖后端存活的实际操作路径。

### 取舍
- 选择 `离线快照` 而不是临时本地 fake API：
  - 优点：前后端结构不分叉；离线数据与当前 recommendation contract 保持一致；静态部署直接可用。
  - 代价：前端构建体积会变大，后续若继续扩 watchlist 或证据规模，需要改成快照懒加载或静态 JSON 分片。
- 选择 `Ant Design` 重做主界面：
  - 优点：更容易把候选股、单票和运营闭环压缩成密度更高的操作台，而不是展示型 hero 页面。
  - 代价：初次构建体积上升，正式公网发布前需要继续做拆包优化。
- 用真实 `Tushare + 巨潮 + Qlib` 结果替换当前 demo validation payload，保持 `validation_snapshot` 和 `factor_breakdown` 的输出结构不变
- 在用户看板阶段优先消费 `recommendation.factor_breakdown`、`validation_snapshot` 和 trace evidence，而不是重新发明前端侧拼装逻辑
- 若后续引入真实 LLM 推理服务，必须沿当前 `prompt_version + llm_assessment_factor + capped weight + downgrade_conditions` 结构接入，避免绕开治理层

## 2026-04-15 用户看板与解释闭环实现备注

### 本轮实现结论
- 已新增面向非专业用户的 dashboard watchlist demo，覆盖 `600519.SH`、`300750.SZ`、`601318.SH`、`002594.SZ` 四只股票，并为每只股票同时生成上一版与当前版 recommendation，用于解释“为何变化”。
- 已把用户看板抽象为后端聚合 contract，而不是让前端自己拼 recommendation、trace、行情和新闻：
  - `/dashboard/candidates` 负责候选池排序与摘要
  - `/stocks/{symbol}/dashboard` 负责单票页、变化原因、风险提示、术语解释和 GPT 追问上下文
  - `/dashboard/glossary` 负责统一术语口径
- 已新增 `frontend/` 的 `Vite + React + TypeScript` 工程，可直接构建 GitHub Pages 子页面静态资源。

### 本轮取舍
- GPT 追问入口当前交付为“可复制的追问包”，而不是直接联通线上 LLM 会话
  - 原因：当前项目尚未进入真实 OpenAI/LLM 服务接入步骤，先把证据上下文、提问模版和前端入口固化，可以避免后续接模型时重做 UI 和后端 contract
- 候选页排序暂按 `direction -> confidence -> 20 日趋势` 的轻量规则输出
  - 原因：当前 watchlist 很小，一期目标是解释闭环而不是做全市场选股器
- 变化原因依赖“上一版 recommendation”对比，而不是前端对行情做临时 diff
  - 原因：只有 recommendation-to-recommendation 的对比，才能把方向切换、置信变化、降级标记和因子强弱变动一起解释清楚

### 对下一步的建议
- 下一步进入“分离式模拟交易与内测准入”时，应直接复用当前 dashboard 的 `simulation_orders` 区块，不要重新设计独立的建议承接入口
- 若后续接真实 GPT 服务，建议保留当前 `copy_prompt` 结构，并把回答限制继续绑定到 `evidence_packet` 和结构化 recommendation 字段
- 如果要支持真实 GitHub Pages 部署，需在后端部署时明确 `ASHARE_CORS_ALLOW_ORIGINS`，并把当前默认宽松策略收紧到内测域名白名单
