# Phase 5 Research Contract

## Purpose

本文件冻结 `Phase 5 - Real Validation Rebuild and Model Portfolio Policy Research` 的当前研究合同，作为 `PROJECT_PLAN.md`、`DECISIONS.md`、`PROCESS.md` 之外的专项事实源。

目标不是提前宣称验证已经完成，而是先把本 phase 的研究边界、状态词典和默认基线锁定，避免 validation、replay、portfolio、simulation 再各自漂移。

## Contract Freeze

### 1. 研究验证层与产品跟踪层必须分离

- `research_validation`
  - 研究 universe 继续使用当前自选池，但每只股票允许使用其完整历史做 rolling validation。
  - 任何历史时点只能使用当时可得的价格、公告、财务和派生特征，禁止未来函数。
- `watchlist_tracking`
  - 用户可见的自选池表现、加入后命中率、加入后建议质量，只能从加入自选池日期开始计算。
  - 不允许 retroactive 回填加入前历史来美化产品跟踪成绩。

### 2. benchmark 必须保留双层语义

- 主研究 benchmark: `active_watchlist_equal_weight_proxy`
- 市场参考线: `CSI300`

规则
- 主研究 benchmark 用于 rolling validation、组合策略和研究优化目标。
- `CSI300` 仅作为市场解释参考线，不是当前 phase 的主优化目标。
- 后续若 benchmark 变化，必须先写入 `DECISIONS.md`，再允许进入 artifact manifest。

### 3. horizon 先作为研究候选集存在

- 候选窗口: `10 / 20 / 40` 个交易日
- 当前主 horizon 状态: `pending_phase5_selection`

规则
- 这三个窗口当前只代表研究候选集，不是产品承诺。
- recommendation、replay 和 validation artifact 可以暴露候选窗口定义，但不能把任一窗口包装成已批准的最终产品周期。

### 4. rolling validation split 先锁定研究基线

- 当前 split baseline:
  - `train_days = 480`
  - `validation_days = 120`
  - `test_days = 60`
- 当前 split rule:
  - `walk_forward_train_480d_validation_120d_test_60d_daily_decision`

规则
- 这是当前 phase 的研究起点，不是长期不可变规则。
- 若后续真实实验表明 split baseline 需要调整，必须先补研究说明与决策记录，再改代码默认值。

当前最小历史覆盖要求
- `required_observation_count = 660`
- `required_bar_count = 740`
- `market_history_lookback_days = 1110`

说明
- `required_observation_count` 对应 `480/120/60` 的完整 walk-forward 决策样本。
- `required_bar_count` 额外计入 `10/20/40` 候选 horizon 的前后 warmup / forward window。
- `market_history_lookback_days` 是 refresh 路径的最小抓取基线，用来降低日历日与交易日换算带来的覆盖不足风险。

### 5. LLM 只保留为手动触发的附加分析

- scope: `manual_triggered_structured_context_analysis_only`

规则
- LLM 不参与核心评分、不参与主 validation 指标、不参与 policy 晋级。
- 当前允许的路径只有：用户手动触发时，将结构化 recommendation 上下文、证据、风险和验证摘要打包给模型生成附加分析。

### 6. simulation 自动执行边界必须显式受限

- policy type: `phase5_simulation_topk_equal_weight_v1`
- execution scope: `simulation_only_auto_execution_no_real_order_routing`

当前 baseline 约束
- 最多 `5` 只持仓
- 单票权重上限 `20%`
- 允许持有现金
- A 股 `100` 股整手
- action definition: `delta_to_constrained_target_weight_portfolio`
- quantity definition: `board_lot_delta_to_target_weight`
- policy status: `research_candidate`

规则
- 只允许 web 模拟盘自动调仓和自动模拟成交。
- 不允许任何真实下单、真实交易路由或实盘自动执行。
- 当前 target-weight / board-lot contract 只在 simulation rail 内作为研究候选策略生效，不等于已批准的对外产品策略。
- 若 execution policy 未来升级，必须先产出新的策略研究结果和回测 artifact。
- `phase5-holding-policy-study` 是当前 simulation policy research 的 typed durable artifact；它可以聚合仍处于产品侧 `pending_rebuild` 的 `portfolio_backtest`，前提是 benchmark 定义匹配当前主研究 benchmark 且 turnover / annualized excess return 已可计算，因为这一步的目标是量化研究 evidence，而不是提前宣称产品验证已完成。
- 截至 `2026-04-26` 当前 real-db snapshot `phase5-holding-policy-study:auto_model:2026-04-24:3portfolios` 仍保持 `research_candidate_only`。当前 evidence 已显示 `mean_annualized_excess_return_after_baseline_cost < 0` 且 `positive_after_baseline_cost_portfolio_count = 0`，因此本合同暂不批准任何 promotion，只允许继续研究 gate 或 redesign。
- 当前研究 artifact 还必须显式输出 draft promotion gate readout：`gate_status / failing_gate_ids / incomplete_gate_ids / gate_checks / gate_context`。当前共享 gate context 版本是 `phase5-holding-policy-promotion-gate-draft-v1`，仅作为诊断型 research helper 使用，不能被误读成 operator 已批准的 auto-promotion policy。
- 当前研究 artifact 也必须显式输出 governance readout：`governance_status / governance_action / governance_note / redesign_trigger_gate_ids / governance_context`。当前共享 governance context 版本是 `phase5-holding-policy-governance-draft-v1`，作用是把 gate 结果翻译成当前默认治理动作，而不是自动批准 promotion。
- 当前研究 artifact 还必须显式输出 redesign diagnostics：`redesign_status / redesign_note / redesign_diagnostics / redesign_triggered_signal_ids / redesign_focus_areas / redesign_context / redesign_experiment_candidates / redesign_primary_experiment_ids`。当前共享 redesign context 版本是 `phase5-holding-policy-redesign-diagnostics-draft-v2`，作用是把“为什么当前 baseline 需要 redesign、应优先改哪一层、下一步先跑哪组 draft experiments”结构化暴露出来，而不是只留下一个抽象的 governance action。
- 对当前 real-db snapshot，draft gate 的默认结论是 `draft_gate_blocked`；至少 `after_cost_excess_non_negative` 与 `positive_after_cost_portfolio_ratio` 两项 blocker 已明确存在。后续若 artifact 仍持续被这些 blocker 拦住，本 phase 的默认下一步应是 non-promotion governance 或 policy redesign，而不是把 gate 形式化误当成晋级本身。
- 对当前 real-db snapshot，默认治理结论现已进一步收口为 `maintain_non_promotion_prioritize_policy_redesign` + `prioritize_policy_redesign`。后续若真实 evidence 没有明显改善，默认工作方向应直接进入 redesign research，而不是重新争论是否先继续 non-promotion。
- 对当前 real-db snapshot，当前默认 redesign focus 也已经进一步收口为 `after_cost_profitability` 与 `portfolio_construction`。前者对应负向 after-cost excess / 正收益组合占比为零，后者对应过薄的 real exposure（当前 sample 的 `mean_invested_ratio=0.075433`、`mean_active_position_count=1.0`）。后续 policy redesign 应优先围绕这两类 signal 设计对照方案，而不是继续只追加 gate/governance 表达。
- 对当前 real-db snapshot，默认 redesign sequencing 也已进一步收口为 primary experiment ids：收益侧先从 `profitability_signal_threshold_sweep_v1` 开始，持仓构造侧先从 `construction_max_position_count_sweep_v1` 开始。其它 candidates 仍保留在 draft experiment menu 中作为后续扩展，而不是当前默认第一步。

## Implementation Rule

- validation manifest、replay artifact、portfolio backtest 和 simulation policy 必须引用本合同的统一常量或共享上下文，而不是各自手写字符串。
- validation artifact 必须显式暴露 walk-forward coverage 状态；若样本不足以覆盖完整 `480/120/60` 基线，artifact 只能标记为 `insufficient_history`，不能伪装成已满足 full baseline。
- candidate horizon comparison 可以给出 research leader，但在 `primary_horizon_status` 仍为 `pending_phase5_selection` 时，不得把任何单一 horizon 升级成已批准产品周期。
- holding-policy research 必须通过 typed `phase5_holding_policy_study` artifact 输出到 durable store，并由 CLI / daily refresh / operations 使用同一 payload 事实源；不得再次回退到只在某个 consumer 里临时聚合、其它地方无法回查的状态。
- 若代码与本文件冲突，以本文件和 `DECISIONS.md` 为准，并把代码视为待迁移状态。

## Next Step

- 基于本合同继续重建 expanding-watchlist rolling validation artifact。
- 用真实 artifact 比较 `10 / 20 / 40` 候选窗口，并为主 horizon 选择提供证据。
- 在 simulation track 上继续利用 `phase5_holding_policy_study` 的日更 artifact 迭代 draft promotion gate，但仍保持 `research_candidate`，直到后续批准。
- 在当前 real snapshot 仍为负向 after-cost excess evidence 且暴露构造过薄的前提下，后续主动工作应优先围绕 `after_cost_profitability` 与 `portfolio_construction` 做 policy redesign 对照研究，并从 `profitability_signal_threshold_sweep_v1` 与 `construction_max_position_count_sweep_v1` 这两个 primary experiments 开始；promotion gate 只保留为 non-promotion diagnostic，而不是默认主线。
