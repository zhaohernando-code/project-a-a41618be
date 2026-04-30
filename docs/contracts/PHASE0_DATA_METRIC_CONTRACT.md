# Phase 0 Data And Metric Contract

## Purpose

本文件定义 `stock_dashboard` 深度改造期间，推荐、复盘、组合、benchmark 和人工研究层的正式语义边界。目标不是直接给出最终模型实现，而是先回答：

1. 哪些字段是 `产品事实`
2. 哪些字段是 `研究候选`
3. 哪些字段在真实实验完成前只能显示为 `迁移态`

如果没有这份 contract，后续 Phase 1/2 很容易再次把旧窗口、旧命中率和旧 benchmark 包装成正式能力。

## Contract Rules

- 任何面向用户展示的量化字段，都必须先能回答 `数据从哪里来`、`在什么时间可得`、`以什么窗口验证`、`由哪个实验版本生成`。
- 没有真实研究产物支撑的字段，不得用数值展示“看起来已验证”的能力；只能显示 `status + note`。
- `Recommendation`、`Replay`、`Portfolio`、`Manual LLM Review` 必须分层，不允许再把解释层和量化层揉成一个分数。
- 旧字段可以在迁移阶段保留，但只能作为兼容层；新前端不应再依赖它们作为真实语义来源。

## Canonical Layers

### 1. `core_quant`

这是唯一允许承载量化结论的核心层。它回答“当前对这只股票的相对判断是什么”。

最小字段：

- `score`
- `score_scale`
- `direction`
- `confidence_bucket`
- `target_horizon`
- `as_of_time`
- `available_time`
- `model_version`
- `policy_version`

约束：

- `score` 必须来自可复现模型或规则基线，不允许混入手工文案判断。
- `target_horizon` 必须对应研究批准的标签定义，例如 `forward_excess_return_10d`、`forward_excess_return_20d`。
- `confidence_bucket` 只能来自研究批准的分箱或不确定性估计，不允许来自拍脑袋阈值。

### 2. `evidence`

这是解释层，不是评分层。它回答“为什么当前结论成立”。

最小字段：

- `primary_drivers`
- `supporting_context`
- `conflicts`
- `data_freshness`
- `source_links`

约束：

- 证据必须能追溯到结构化 artifact。
- 证据数量和措辞不能强于 `core_quant` 的验证状态。

### 3. `risk`

这是失效条件层。它回答“什么情况下当前结论会失效或应降级”。

最小字段：

- `risk_flags`
- `downgrade_conditions`
- `invalidators`
- `coverage_gaps`

约束：

- 每条失效条件必须可映射到可监控信号。
- `risk` 不能只是情绪化措辞，必须是可观察的条件。

### 4. `historical_validation`

这是实验验证层。它回答“这个结论背后有没有真实历史验证”。

最小字段：

- `status`
- `note`
- `artifact_id`
- `artifact_generated_at`
- `label_definition`
- `window_definition`
- `benchmark_definition`
- `cost_definition`

仅在 `status=verified` 时允许展示的数值字段：

- `rank_ic_mean`
- `rank_ic_ir`
- `bucket_spread`
- `excess_return_annualized`
- `max_drawdown`
- `turnover`
- `sample_count`

约束：

- `historical_validation` 只能引用真实实验 artifact。
- `status != verified` 时，不显示任何伪数值。

### 5. `manual_llm_review`

这是人工研究层，不是核心量化层。它回答“人工触发的 Codex/GPT 研究补充了什么观察”。

最小字段：

- `status`
- `trigger_mode`
- `model_label`
- `requested_at`
- `generated_at`
- `summary`
- `risks`
- `disagreements`
- `source_packet`

约束：

- v1 固定为 `trigger_mode=manual`。
- `manual_llm_review` 不能反向写入 `core_quant.score`。
- 如果人工研究和量化结论冲突，必须显式列出 `disagreements`，而不是静默覆盖。

## Status Taxonomy

### Validation status

统一状态枚举：

- `pending_rebuild`
  - 含义：旧能力已被识别为不可信，真实验证尚未重建完成。
- `synthetic_demo`
  - 含义：当前结果只来自演示级或合成逻辑，不得作为量化验证依据。
- `research_candidate`
  - 含义：已经形成研究方案或候选实验，但还未达到产品批准标准。
- `verified`
  - 含义：已有真实实验 artifact，且通过研究门禁。
- `deprecated`
  - 含义：该字段或口径已被废弃，仅为兼容保留。

展示规则：

- `pending_rebuild` / `synthetic_demo`：只能展示说明，不展示背书式数字。
- `research_candidate`：允许内部研究页展示候选结果，不允许默认面对外行展示为正式能力。
- `verified`：允许进入用户主视图。

### Manual review status

统一状态枚举：

- `manual_trigger_required`
- `queued`
- `in_progress`
- `completed`
- `failed`
- `stale`

## Benchmark Contract

### Canonical benchmark types

一期只允许三类 benchmark：

- `market_index`
  - 例：沪深 300、中证 500、中证 1000
- `industry_index`
  - 与股票所属行业或风格桶对齐
- `peer_cohort`
  - 对同一研究股票池内的横截面分组或候选池中位数

### Benchmark minimum fields

- `benchmark_id`
- `benchmark_type`
- `benchmark_symbol`
- `benchmark_label`
- `source`
- `as_of_time`
- `available_time`
- `status`

约束：

- 没有真实来源的 benchmark，`status` 必须是 `synthetic_demo` 或 `pending_rebuild`。
- `benchmark_return`、`excess_return` 和任何 readiness 判定都只能在 benchmark `status=verified` 时展示为正式指标。

## Recommendation Contract

### Migration-period API shape

迁移期 recommendation 必须至少包含：

- `core_quant`
- `evidence`
- `risk`
- `historical_validation`
- `manual_llm_review`

旧字段处理规则：

- `applicable_period`
  - 迁移期只能作为文案兼容字段，默认显示“研究验证中（历史窗口待重建）”
- `validation_snapshot`
  - 外部 payload 置空，等待真实 `historical_validation`
- `llm_assessment`
  - 保留迁移壳，但不再代表真实 LLM 量化因子

### Direction semantics

一期不再使用“像投顾一样”的强买卖承诺作为底层语义。推荐底层应该先落成以下中性方向：

- `positive`
- `neutral`
- `negative`
- `insufficient_evidence`

产品层可以再映射为面向外行的表达，例如：

- `关注`
- `等待`
- `回避`

但映射必须在产品层完成，不能倒灌回研究层。

## Replay Contract

### Purpose

Replay 只回答一件事：`历史某次 recommendation 在它声明的 horizon 和 benchmark 定义下，后来表现如何`。

### Required fields

- `recommendation_id`
- `label_definition`
- `review_window_definition`
- `entry_time`
- `exit_time`
- `stock_return`
- `benchmark_return`
- `excess_return`
- `max_favorable_excursion`
- `max_adverse_excursion`
- `hit_definition`
- `hit_status`
- `validation_status`
- `validation_note`

### Required rules

- `review_window_definition` 必须和 recommendation 的 `target_horizon` 对齐，不能再用“上一条 recommendation 到当前最新价”的宽松口径。
- `hit_definition` 必须明确写出，例如“20 交易日超额收益 > 0 视为 hit”。
- `hit_status` 只能在 `validation_status=verified` 时进入运营主视图。

## Portfolio Contract

### Split of concerns

组合层必须拆成三个概念：

- `portfolio_performance`
- `execution_policy`
- `validation_status`

迁移期当前自动持仓建议只能表述为：

- `execution_policy.status=synthetic_demo`
- `execution_policy.label=演示策略`

不允许继续把固定预算买入、卖半仓动作包装成正式量化组合策略。

### Portfolio minimum fields

- `portfolio_key`
- `strategy_label`
- `strategy_status`
- `benchmark_context`
- `performance`
- `risk_exposure`
- `validation_status`
- `validation_note`

## Operations Contract

运营面板必须拆成三类卡片：

### 1. 运行健康

- 数据刷新是否正常
- 任务是否失败
- 数据是否延迟

### 2. 研究验证

- 是否已有真实 benchmark
- 是否已有 verified replay
- 当前推荐 contract 是否仍处于迁移态

### 3. 上线门禁

- 是否满足对外展示要求
- 是否存在 synthetic_demo 字段泄漏
- 是否通过研究与合规检查

约束：

- `recommendation_hit_rate` 不得再单独作为 readiness 主指标，除非其标签、horizon、benchmark 和命中定义均已 verified。

## Artifact Requirements

任何将来可展示为 `verified` 的能力，必须至少能关联到以下 artifact：

- `research_spec`
- `dataset_snapshot`
- `feature_snapshot`
- `experiment_config`
- `experiment_result`
- `backtest_result`
- `product_snapshot`

每个 artifact 至少要带：

- `artifact_id`
- `version`
- `generated_at`
- `source_range`
- `as_of_time`
- `available_time_policy`

## Phase Mapping

### Phase 0

- 清空或降级旧伪字段
- 固定 status taxonomy
- 固定 migration contract

### Phase 1

- 固定 benchmark truth
- 固定数据可得性字段
- 固定 recommendation/replay/portfolio 新 contract

### Phase 2

- 用真实研究 artifact 回填 `historical_validation`
- 用真实 backtest 回填 replay 与 portfolio 指标

### Phase 3

- 前端主视图完全切换到新 contract
- 不再依赖迁移字段

### Phase 4

- 手动 Codex/GPT 研究链路填充 `manual_llm_review`

## Exit Criteria

满足以下条件后，才允许认为 Phase 0 contract 重写完成：

- recommendation、replay、portfolio、operations 的迁移字段都已有明确语义和状态枚举
- 任何旧伪指标都已有 `rename / downgrade / hide` 处理方式
- 前后端后续开发都能以本文件为 contract 事实来源
- `PROJECT_STATUS.json` 和 `PROCESS.md` 已同步记录本规范已建立
