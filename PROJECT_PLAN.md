# 一个关于a股的当前数据和投资建议看板

## Approved Plan

目标
规划一期面向自选股池的小范围内测 A 股决策看板：以“可信、可回放、可审计的量化研究与决策支持”为优先目标，整合延迟行情、板块与事件证据、可回测量化模型、LLM 辅助解释、优质股候选池，以及分离式模拟交易，形成面向非专业用户但具备真实参考价值的决策支持闭环；同时预留从低成本数据源升级到付费数据与更强建议能力的可替换架构。

补充原则
- 历史文档与现有代码中的 `2-8 周`、`14/28/56 天`、固定权重、固定占比、固定阈值、固定样本期等设定，一律视为旧假设而不是既定规则。
- 后续任何时间窗口、权重配比、刷新节奏、建议周期、回测样本期与门槛值，都必须服从研究证据与历史验证结果；若旧设定损害可信度，应直接替换或删除。
- 在真实研究结论产出前，系统不得继续把拍脑袋得出的窗口、占比或命中率包装成“模型能力”。

一期范围
- 一期边界限定为自选股池、小范围内测、盘中延迟更新，不覆盖全市场高频扫描、不接自动实盘交易。
- 交付形态为 Web 看板：用户从 `https://hernando-zhao.cn/stocks` 进入，底层规范挂载路径为 `/projects/ashare-dashboard/`；本机负责后端、数据库、定时任务与模型服务，通过 API 提供数据、信号、建议与模拟交易能力。
- 核心工作流收敛为四条：单票分析与建议、优质股候选池、GPT 追问解释、模拟交易验证；手动模拟与按模型组合自动持仓分开建设、分开验收。
- 建议引擎优先采用成熟、可审计、可回测的量化与时间序列基线，统一使用滚动时间验证；新闻、板块与事件信号通过去重、层级映射、时滞控制和影响衰减纳入因子体系。LLM 可参与解释与候选研究，但在真实历史增益未稳定前不得主导建议融合。

分阶段计划
1. 数据与开源基线评估：完成 A 股行情、新闻、财务与板块数据源的免费/付费评估，以及可复用开源项目与成熟建模方案筛选；输出一期推荐技术路线、数据适配层设计、升级触发条件、价格与付款模式比选和授权/合规风险清单。
2. 证据化数据底座：建立行情、新闻、板块、特征、模型结果、建议记录与模拟交易的数据模型与采集链路，确保任一建议都能按股票、时间、模型版本、提示词版本和原始证据完整回溯。
3. 信号建模与建议引擎：先完成研究重置，确定一期真正有效的预测窗口、标签定义和调仓频率，再交付价格预测/排序基线、新闻事件因子、LLM 辅助研究与融合评分框架，输出包含方向、置信表达、核心驱动、反向风险、适用周期、更新时间与降级条件的建议结果。
4. 用户看板与解释闭环：交付面向非专业用户的单票分析页、候选股推荐页、术语解释、证据回溯、风险提示、变化原因展示和 GPT 追问入口，让用户看得懂建议为何成立、为何变化、何时失效。
5. 分离式模拟交易与内测准入：分别交付手动模拟交易与按模型组合自动持仓两条闭环，补齐 A 股交易规则、收益归因、回撤监控、基准对比、建议命中复盘，以及小范围内测所需的访问控制、刷新策略、性能阈值和上线门槛。

验证与验收
- 任意自选股都能在单页查看延迟行情走势、成交量、板块归属、关键指标、相关新闻、建议摘要、术语解释和最近更新时间。
- 每条建议都必须绑定结构化证据，并输出方向、置信表达、适用周期、核心驱动、反向风险、数据时间戳、生成时间戳和模型版本。
- 历史建模必须采用滚动时间窗口验证，禁止随机切分；验收指标至少覆盖方向命中、策略收益、最大回撤、稳定性、阶段分布和交易成本影响。具体窗口与 horizon 必须由研究阶段锁定，不能继承旧的拍脑袋设定。
- 新闻因子链路必须支持事件去重、来源追溯、个股/行业/市场层级标注、发布时间对齐和影响衰减；当证据不足或信号冲突过大时，系统必须降级为风险提示。LLM 因子必须有独立历史评估结果，并与纯结构化基线对比；若增益不稳定，不得在建议中占主导权重。
- 所有对外展示的周期、占比、阈值、命中率、收益率和 lift 指标都必须来自真实实验产物；没有实验支撑的字段必须降级为“待验证”或直接隐藏。

主要风险
- 免费与付费 A 股数据在授权、稳定性、时效性和字段完整度上的差异，可能直接改变一期方案；因此数据源评估、适配层设计、替换预案以及价格与付款模式评估应作为正式需求，而不是实现细节。
- 金融预测在风格切换和热点轮动阶段容易过拟合；即使滚动验证通过，也需要保留失效监控、快速降级、模型冻结、版本回滚和阶段性复盘机制。
- 新闻到因子的映射存在噪声、重复报道、发布时间偏差和市场提前反应问题，只能通过去重、窗口控制、衰减和分层标注减轻，不能完全消除。
- LLM 同时参与解释和因子生成会带来漂移与幻觉风险；如果缺少证据绑定、阈值治理和历史校准，系统会把弱信号包装成高确定性建议。
- 产品方向偏向更强决策支持，意味着合规表达、责任边界、访问控制、建议留档、日志审计与数据许可要求明显高于普通资讯看板，需要在一期内测阶段提前固化。

## Current Transformation Status

- 为避免把已完成旧步骤误读成当前执行计划，本文件不再保留 legacy delivery snapshot 与已完成 execution checklist；历史收口细节以 `PROCESS.md` 和 `DECISIONS.md` 为准。
- `Phase 0` 研究重置、`Phase 1` contract cleanup 与 `Phase 2 - Research Artifact Producer and Quant Core Rebuild` 已完成；`signal_engine` 已重构为分模块 Phase 2 quant core，manual follow-up 也已落成 durable `manual_review` artifact 流。
- `Phase 3 - Product Rewrite and User-facing Evidence/Risk Presentation` 已完成：单票、候选、治理与 replay/portfolio 主界面现已以 `core_quant / evidence / risk / historical_validation / manual_llm_review` 和对应的 artifact-backed operations contract 作为主展示语义，legacy compat 字段退回到统一派生壳。
- `Phase 4 - Manual Research Workflow Hardening and Stable manual_llm_review Contract` 已完成；当前默认活动 phase 已由 operator 批准切换为 `Phase 5 - Real Validation Rebuild and Model Portfolio Policy Research`。
- 截至 `2026-04-26`，已经完成的当前代收口范围还包括：live publish hardened parity workflow、authenticated canonical browser acceptance cleanup、`phase5-horizon-study` artifact 化与日更自动化、expanding-watchlist join-date-forward benchmark contract 锁定，以及真实数据库上的 validation manifest / portfolio backtest 重建。
- `Phase 5` 的已批准边界是：继续使用当前自选池作为一期研究 universe，但要显式区分两层语义。研究验证层允许每只股票使用其完整历史做 rolling validation；自选池运营统计、加入后表现和用户可见的“自选池跟踪”指标则只从加入自选池的时点开始计算。benchmark 由实现阶段按可信度原则决定，当前默认是 `active_watchlist_equal_weight_proxy` 作为主研究 benchmark、`CSI300` 作为市场参考线。LLM 不作为主评分因子，而是保留为用户手动触发的附加分析入口：前端在用户点击时，把当前结构化上下文、证据和风险信息喂给大模型生成分析。主持有周期与标签定义不预先拍板，先由 rolling validation 的结果决定。产品目标是“真自动持仓建议”，且在 web 模拟盘内允许系统自动执行调仓与模拟成交；但这项批准只限模拟交易，不扩展到真实下单或真实交易路由。
- 当前活动状态以 `PROJECT_STATUS.json`、`PROCESS.md` 和 `docs/contracts/` / `docs/archive/` 下的最新材料为准；旧阶段的完成记录只保留在执行日志中，不再作为默认开发路线展示。

Current step: `Phase 5 - Real Validation Rebuild and Model Portfolio Policy Research` remains in progress; the P-1/P0 professionalization tranche is implemented, published to the local runtime, and fully closed through tests, deploy verifier, and served-browser verification. The latest closeout has `pytest -q` at `212 passed`, deploy verification at `19 passed / 0 failed`, and a Chrome served-page check with zero console errors. Summary-first operations loading, lazy detail loading, data-quality, benchmark, factor-IC, weight-sweep, and product-facing validation fields are now the active contract. Replay time-window accumulation, holding-policy breadth, horizon approval, and production weight calibration remain open.
Last completed milestone: `Phase 4 - Manual Research Workflow Hardening and Stable manual_llm_review Contract`
