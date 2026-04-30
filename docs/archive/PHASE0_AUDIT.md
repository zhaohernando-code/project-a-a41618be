# Phase 0 Audit

## Goal

审计当前 `stock_dashboard` 的实现，识别所有会误导用户、夸大量化可信度、或把旧假设包装成正式能力的模块。这个文档只回答两件事：

1. 现在的实现哪里名不副实。
2. 深度改造应该先拆哪几块，避免继续在伪量化壳上迭代。

## High-Severity Findings

### F001. 验证结果和 lift 指标是硬编码常量，不是真实实验产物

- 证据：`src/ashare_evidence/signal_engine.py:15-57`
- 表现：`BASELINE_VALIDATION` 和 `LLM_FACTOR_EVALUATION` 直接写死了方向命中率、策略收益、成本后收益、最大回撤、稳定性、样本数和 LLM lift。
- 风险：前端和 API 会把这些字段当成已经验证过的量化结果，导致用户误以为系统具备真实历史表现背书。
- 处理：在真实实验流水线产出 `model_run` / `model_result` 之前，所有这类字段必须降级为 `pending_validation` 或从前端隐藏。

### F002. 当前“LLM 因子”不是 LLM 推理结果，而是价格和新闻分数的派生启发式

- 证据：`src/ashare_evidence/signal_engine.py:356-416`
- 表现：`_compute_llm_factor` 用价格因子和新闻因子线性组合，再叠加冲突惩罚和硬编码稳定性分数，生成所谓 `llm_assessment`。
- 风险：系统名义上宣称有 LLM 分析因子，实际上只是另一个手工规则层，会夸大“AI 参与决策”的真实性。
- 处理：将该能力拆分为两层：
  - 核心量化分数里移除伪 LLM 因子。
  - 另建 `manual_llm_review`，只承载手动触发的 Codex/GPT 研究输出。

### F003. 融合权重、方向阈值、适用周期和摘要文案是手工设定，不是研究锁定结果

- 证据：`src/ashare_evidence/signal_engine.py:120-127`, `419-477`, `491-672`
- 表现：
  - `14/28/56` horizon 和 `28` 天主窗口被硬编码。
  - `0.58 / 0.27 / 0.15` 融合权重被硬编码。
  - `buy / reduce / watch / risk_alert` 的阈值被硬编码。
  - 摘要和置信表达直接写成“适用 2-8 周波段”“当前以 4 周信号最强”。
- 风险：旧假设被包装成模型输出，后续即使研究结论推翻这些窗口，产品仍会沿旧口径对外表达。
- 处理：窗口、权重、动作映射和周期文案必须从“研究批准参数”读取，不能继续写死在引擎里。

### F004. 运营面板的 benchmark 路径是伪造的常量收益序列

- 证据：`src/ashare_evidence/operations.py:31-64`, `197-204`
- 表现：`BENCHMARK_DAILY_RETURNS` 是固定数组，`_benchmark_close_map` 基于该数组生成指数路径。
- 风险：所有组合收益、超额收益、复盘结论和 beta readiness 都建立在假 benchmark 上。
- 处理：使用真实指数行情替换；若真实 benchmark 不可用，前端必须显示“基准不可用”，不能继续生成超额收益。

### F005. 建议命中复盘口径过于宽松，且没有和预测 horizon 绑定

- 证据：`src/ashare_evidence/operations.py:320-345`, `691-756`, `1002-1005`
- 表现：
  - `buy` 只要求绝对收益为正且相对基准不显著跑输。
  - `watch` 只要求超额波动不大。
  - `risk_alert` 只要轻微跑输或回撤即可判 hit。
  - 回放窗口来自“上一条 recommendation 到当前最新价”，不是和预测 horizon 对齐。
- 风险：命中率容易被高估，也无法和真实模型目标一一对应。
- 处理：复盘逻辑必须重建为“预测标签一致的 horizon-based evaluation”，并公开 hit 的严格定义。

### F006. 自动持仓建议使用固定预算和卖半仓规则，缺乏组合层依据

- 证据：`src/ashare_evidence/simulation.py:524-577`
- 表现：`buy` 统一使用 `available_cash * 0.24`；`reduce/risk_alert` 统一卖出一半左右仓位。
- 风险：看起来像组合引擎，实际上只是演示性仓位规则，会误导用户对“模型自动持仓”能力的理解。
- 处理：在真实组合策略就绪前，应改名为“规则化动作建议”；真实组合引擎完成后再恢复“自动持仓”表述。

## Medium-Severity Findings

### F007. 当前 LLM 服务实现是 API-key 驱动的追问接口，不符合新的手动 Codex/GPT 目标

- 证据：`src/ashare_evidence/llm_service.py:20-149`
- 表现：当前链路依赖 OpenAI-compatible endpoint、API Key 和 failover 逻辑。
- 风险：这和新的产品约束冲突，即 v1 先走手动触发 Codex/GPT，再保留未来 API 适配层。
- 处理：保留 `LLMTransport` 抽象，但把默认运行方式切到 `manual_trigger_pending`，把现有 API 实现降级成未来 provider。

### F008. 运营面板里的刷新节奏、回撤门槛和上线闸门仍然是产品常量

- 证据：`src/ashare_evidence/operations.py:66-109`, `612-615`, `916-1027`
- 表现：刷新频率、回撤阈值、性能预算、上线门槛和命中覆盖阈值都是手动常量。
- 风险：会把“暂定运营口径”伪装成“研究批准指标”。
- 处理：区分 `ops_policy` 与 `quant_validation`，避免研究指标和运行策略混用。

### F009. 测试更偏 contract/traceability，不验证量化有效性

- 证据：现有测试主要覆盖 traceability、runtime config、API access 和 fixtures；缺少真实滚动验证、真实 benchmark 和标签一致性测试。
- 风险：现有测试绿并不意味着量化结论可信。
- 处理：新增研究级测试资产，至少覆盖数据时间可得性、标签构造、滚动切分和回测真实性。

## 2026-04-26 Frontend Display Closure Audit

### 审计范围

- 标准入口以 `https://www.hernando-zhao.cn/projects/ashare-dashboard/` 为准。
- 当前线上入口会先跳统一登录，因此本轮展示审计以三层证据交叉确认：
  - 已发布 runtime bundle 与 repo bundle 是否同版
  - runtime API 实际返回的 payload
  - `frontend/src/App.tsx` 的真实渲染路径
- 审计目标不是判断研究本身是否完成，而是回答：如果把前端视为“已完成展示面”，当前用户还能看到哪些不该外露的旧假设、迁移态或内部 contract 语义。

## Frontend Closure Findings

### F010. Runtime payload 仍把已废弃旧假设作为用户可见文案输出

- 证据：
  - `frontend/src/App.tsx:3883-3927`
  - `frontend/src/App.tsx:4122-4144`
  - `GET /dashboard/candidates?limit=8`
  - `GET /stocks/002028.SZ/dashboard`
- 表现：
  - 候选列表和单票页继续展示 `2-8 周波段`、`14-56 个交易日（研究窗口待批准）`
  - recommendation payload 继续输出 `horizon_min_days=14`、`horizon_max_days=56`
  - risk/evidence 文案仍写 `LLM 因子历史增益有限，权重上限固定为 15%`
- 风险：
  - 已被研究重置降级的历史窗口、固定权重和旧周期话术，仍会被用户理解成当前产品结论。
  - 即使后端内部把这些字段视为 compat shell，只要主页面继续渲染，它们就仍是对外语义。
- 处理：
  - 前端主展示停止消费这类旧假设文案。
  - runtime payload 对外改成研究批准后的展示语义，或明确降级为非承诺说明，不再出现旧窗口数字。

### F011. 前端主界面仍直接暴露“未完成态/迁移态”标签

- 证据：
  - `frontend/src/App.tsx:194-212`
  - `frontend/src/App.tsx:3790-3796`
  - `frontend/src/App.tsx:1061-1086`
  - `frontend/src/App.tsx:3168-3218`
- 表现：
  - 头部直接展示 `研究重置中`
  - 候选和单票页继续展示 `待重建`、`研究候选`
  - 组合与运营页继续提示 `基准与超额收益正在重建`、`验证仍未完成`
  - `Artifact-backed`、`迁移占位` 被直接渲染为面向用户的状态标签
- 风险：
  - 如果 operator 认为当前 phase 已完成，前端却继续呈现未完成态，会造成产品状态和实际展示的口径冲突。
  - 用户会把内部迁移治理语言误认为正式产品标签。
- 处理：
  - 把 operator/governance 语义与用户展示语义拆开。
  - 未完成态只留在内部治理视图或调试层；面向用户的主路径改成更克制的风险提示或暂不可用提示。

### F012. 单票主界面仍把内部工作流 ID 和执行元数据作为主展示内容

- 证据：
  - `frontend/src/App.tsx:2361-2468`
- 表现：
  - 页面直接展示 `Artifact ID`、`Request ID`、`Request Key`、`trigger_mode`、`executor_kind`
  - `manual_llm_review` 的内部工作流元数据与正文内容处于同一主内容层级
- 风险：
  - 这些字段有助于排障，但不属于完成态产品的主界面信息。
  - 对非操作者用户来说，它们会制造“系统还在调试/半内部工具”的观感。
- 处理：
  - 把内部追踪 ID 下沉到 operator-only 的调试抽屉、诊断卡或二级详情。
  - 主界面仅保留用户能理解的研究结论、引用、风险和时间戳。

### F013. 前端仍直接展示未产品化的研究枚举和内部 benchmark 名称

- 证据：
  - `frontend/src/App.tsx:210-212`
  - `frontend/src/App.tsx:2176-2234`
  - `frontend/src/App.tsx:4127-4135`
  - `GET /stocks/002028.SZ/dashboard`
  - `GET /dashboard/operations?sample_symbol=002028.SZ`
- 表现：
  - `forward_excess_return_20d` 直接作为目标 horizon 出现在页面
  - `phase2_equal_weight_market_proxy`、`active_watchlist_equal_weight_proxy` 直接出现在复盘/组合上下文里
- 风险：
  - 这些是研究或 contract 术语，不是面向非专业用户的产品语言。
  - 即使语义本身正确，也会把内部实现细节暴露为用户界面的一部分。
- 处理：
  - 所有 horizon、benchmark 和验证定义都要有产品化映射文案。
  - 内部枚举只允许留在调试层，不应直接进入主展示。

### F014. 运营总览仍以治理台口径暴露迁移计数和 artifact 覆盖率

- 证据：
  - `frontend/src/App.tsx:3168-3218`
  - `GET /dashboard/operations?sample_symbol=002028.SZ`
- 表现：
  - 运营页直接展示 `Synthetic replay`、`复盘迁移占位`、`组合 pending_rebuild`、`artifact-backed` 等计数
  - payload 也仍以 `pending_rebuild`、`migration_placeholder`、`research_candidate` 作为第一层状态词
- 风险：
  - 这类信息适合治理审计，不适合完成态产品默认页面。
  - 主界面把“内部治理覆盖率”和“用户决策信息”混在一起，会稀释核心产品语义。
- 处理：
  - 运营页拆成用户复盘视图和内部治理视图两层，默认页不再突出迁移计数。
  - artifact/gating 统计保留，但进入 operator-only 区域。

## Frontend Closure Backlog

1. 停止在候选、单票和风险文案中直接展示 `2-8 周`、`14-56`、固定 `15%` 等旧假设。
2. 把 `pending_rebuild`、`research_candidate`、`migration_placeholder`、`Artifact-backed` 从默认用户视图移除或下沉。
3. 把 `Artifact ID / Request ID / Request Key / trigger_mode / executor_kind` 从主内容层移到调试层。
4. 为 `forward_excess_return_20d`、`phase2_equal_weight_market_proxy` 等内部枚举补产品化映射，不再直接展示原值。
5. 将运营页的治理计数与用户复盘信息分层，避免默认页继续充当迁移治理控制台。

## 2026-04-26 Runtime Closure Verification Addendum

- 本地 runtime 已完成一轮渲染后 DOM 验证，验证入口为 `http://127.0.0.1:5173/`。
- 验证方法：
  - 使用 headless Chrome 的 `--virtual-time-budget=12000 --dump-dom` 抓取运行态 DOM，而不是只看 repo 源码或 bundle 文本。
  - 对 DOM 直接搜索 `2-8 周`、`14-56 个交易日（研究窗口待批准）`、`研究重置中`、`待重建`、`Artifact-backed`、`迁移占位`、`forward_excess_return_20d`、`phase2_equal_weight_market_proxy`、`executor_kind`、`Request ID`、`Artifact ID`、`Request Key` 等审计词。
  - 额外确认 `当前研究周期`、`验证样本待补充`、`验证摘要` 等新展示词已进入 DOM。
- 当前结果：
  - 本地 runtime DOM 对上述旧词搜索结果为空，说明 `F010-F014` 对应的旧展示已不再出现在默认运行态首屏内容中。
  - 运行态 DOM 已出现 `当前研究周期`、`验证样本待补充`、`验证摘要` 等新映射文案。
  - repo `frontend/dist/assets` 与 runtime `~/codex/runtime/projects/ashare-dashboard/frontend/dist/assets` 当前一致，均为 `index-73b43f58.js` 与 `index-f042356a.css`；`127.0.0.1:5173` 也确实在服务这组 asset。
- 标准入口复核结果：
  - `codex-server` 本机带真实登录态访问 `https://127.0.0.1/projects/ashare-dashboard/` 并附带 `Host: www.hernando-zhao.cn`，当前可稳定返回 `200 OK` 和标准入口 HTML，入口 shell 指向 `./assets/index-73b43f58.js` 与 `index-f042356a.css`。
  - 本机 shell 在显式移除 `HTTP_PROXY / HTTPS_PROXY / ALL_PROXY / NO_PROXY` 后，再次登录访问 `https://www.hernando-zhao.cn/projects/ashare-dashboard/`，同样返回 `200 OK` 和相同入口 HTML；因此标准入口当前并未挂起。
  - 先前“认证后挂起”的结论来自带代理环境的本机请求假阴性：该路径先收到 `HTTP/1.1 200 Connection established`，并未形成可直接归因于站点的源站证据。
  - 结合本地 runtime 的渲染后 DOM 核验与标准入口返回的同名 bundle，可以确认“本地 runtime 默认视图 + 标准入口 transport/bundle parity”已经收口；但这还不等于浏览器层的最终可视验收已经通过。

## 2026-04-26 Canonical Browser Acceptance Addendum

- 本轮额外补做了认证后的标准入口浏览器验收，验证目标是确认真实用户在 `https://www.hernando-zhao.cn/projects/ashare-dashboard/` 看到的 SPA 页面是否已经达到“phase 完成态”。
- 验证方法：
  - 使用无代理的 headless Chrome DevTools 会话，而不是沿用当前桌面 Chrome 的代理/扩展环境。
  - 先对统一登录入口执行真实账号登录，再把认证 cookie 注入 headless Chrome，随后访问标准入口。
  - 分别抓取 `候选与自选`、`单票分析`、`运营复盘`、`设置` 四个工作区的渲染后文本与整页截图，产物保存在 `output/acceptance/` 下。
- 当前结果：
  - `候选与自选` 默认工作区未再命中 `2-8 周`、`14-56 个交易日（研究窗口待批准）`、`研究重置中`、`Artifact-backed`、`phase2_equal_weight_market_proxy`、`Request ID` 等既有审计词，说明默认 landing 视图比之前更接近完成态。
  - `单票分析` 仍未通过收口：页面仍直接展示“历史验证仍处于迁移重建阶段”，`历史验证层` 仍暴露 `标签定义：research_rebuild_pending`、`基准定义：pending_rebuild`；`人工研究层` 仍包含 `Manual research workflow`；`研究输入包` 仍把 `recommendation_key`、`target_horizon:14-56 trade days`、`validation_artifact_id`、`validation_manifest_id` 直接展示给用户。
  - `运营复盘` 仍未通过收口：顶部警示继续写“运营复盘口径仍在迁移”，正文仍暴露 `research contract`、`replay artifact`、`manifest`、`verified`、`pending_rebuild` 等内部治理词，同时 `模型轨道建议 (Phase 5 baseline)` 也把 phase 内部命名直接展示在默认页。
  - `设置` 也未达到面向完成态用户的产品化表达：仍直接展示 `self_hosted_server`、`runtime_policy`、`global_shared_pool` 以及 `quote / kline / financial_report` 等内部统一字段映射说明。这些更像 operator/debug 合同视图，而不是默认产品前台。
- 结论修正：
  - `F010-F014` 不能再被视为“已经整体关闭”。
  - 更准确的状态是：`候选与自选` 默认视图和标准入口 transport/bundle parity 已收口，但 `单票分析 / 运营复盘 / 设置` 三个工作区仍然存在内部 contract、迁移状态词和旧 horizon 语义外露的问题。
  - 后续前端完成态验收必须按“认证后的标准入口 + 多工作区浏览器渲染”执行，而不能只凭默认 landing 视图或本地 runtime 首屏 DOM。

## False-Feature Inventory

| 模块/表述 | 当前真实状态 | 问题 | 建议动作 |
| --- | --- | --- | --- |
| `LLM 因子` | 价格/新闻启发式派生分数 | 名不副实 | 拆成 `manual_llm_review`，从核心分数移除 |
| `validation_snapshot` | 硬编码验证摘要 | 非真实回测 | 隐藏或标记 `pending_validation` |
| `benchmark_return` / `excess_return` | 基于伪 benchmark | 超额收益失真 | 改成真实指数行情 |
| `建议命中率` | 宽松回放规则 | 口径虚高 | 改成 horizon 对齐复盘 |
| `模型自动持仓` | 固定预算/卖半仓 | 更像演示规则 | 改名或重做组合层 |
| `2-8 周适用周期` | 写死在文案和引擎里 | 旧假设冒充研究结论 | 参数化并等待研究批准 |

## Rebuild Order

1. 先移除或降级所有伪验证、伪 LLM 和伪 benchmark 展示。
2. 再重建真实数据时间可得性、标签定义和 benchmark 合约。
3. 然后重建滚动验证、排序模型和组合/回测层。
4. 最后再重写前端话术与手动 LLM 研究入口。
