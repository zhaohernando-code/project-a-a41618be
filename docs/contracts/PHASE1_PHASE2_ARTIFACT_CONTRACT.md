# Phase 1 To Phase 2 Research Artifact Contract

## Purpose

本文件定义 `stock_dashboard` 从 `Phase 1` 迁移到 `Phase 2` 时，真实滚动验证、排序实验和回测结果必须遵守的 artifact contract。

目标只有一个：后续所有 `historical_validation`、组合回测和研究门禁，都只能引用真实实验产物，而不能继续把临时统计、手工摘要或硬编码数值塞回 recommendation payload。

## Core Rules

- 每个研究产物都必须能回答：
  - `这是哪个实验版本`
  - `使用了哪批数据`
  - `哪些时间段用于 train / validation / test`
  - `标签、benchmark、成本和调仓规则是什么`
  - `哪些指标允许进入产品层`
- 推荐层只允许引用 artifact summary，不允许把完整实验细节平铺进 recommendation。
- 任何 `verified` 状态都必须绑定 artifact manifest；没有 manifest，就不能进入 `verified`。
- `research_candidate` 可以存在实验结果，但默认只允许研究页消费，不允许直接提升到外行主视图。

## Artifact Families

### 1. Validation Manifest

回答“这次滚动验证是如何定义的”。

必填字段：

- `artifact_id`
- `artifact_type=rolling_validation`
- `generated_at`
- `experiment_version`
- `model_version`
- `policy_version`
- `data_snapshot_id`
- `universe_definition`
- `availability_rule`
- `feature_set_version`
- `label_definition`
- `benchmark_definition`
- `cost_definition`
- `rebalance_definition`
- `split_plan`

约束：

- `availability_rule` 必须明确可得时间约束，禁止未来函数。
- `split_plan` 必须显式列出 rolling / walk-forward 切片，不能只写“滚动验证”四个字。

### 2. Validation Metrics Artifact

回答“模型在滚动验证中表现如何”。

必填字段：

- `artifact_id`
- `manifest_id`
- `status`
- `sample_count`
- `rank_ic_mean`
- `rank_ic_std`
- `rank_ic_ir`
- `ic_mean`
- `bucket_spread_mean`
- `bucket_spread_std`
- `positive_excess_rate`
- `turnover_mean`
- `coverage_ratio`

推荐附加字段：

- `period_metrics`
- `market_regime_metrics`
- `industry_slice_metrics`
- `feature_drift_summary`

约束：

- `sample_count`、`coverage_ratio` 和 `turnover_mean` 必须一起出现，防止只展示漂亮收益。
- 任何进入 recommendation 的验证摘要都必须来自这里的可追溯聚合，而不是二次手写。

### 3. Backtest Artifact

回答“把排序信号映射成组合动作后，结果如何”。

必填字段：

- `artifact_id`
- `artifact_type=portfolio_backtest`
- `manifest_id`
- `strategy_definition`
- `position_limit_definition`
- `execution_assumptions`
- `benchmark_definition`
- `cost_definition`
- `annualized_return`
- `annualized_excess_return`
- `max_drawdown`
- `sharpe_like_ratio`
- `turnover`
- `win_rate_definition`
- `win_rate`
- `capacity_note`

推荐附加字段：

- `nav_series_ref`
- `drawdown_series_ref`
- `trade_log_ref`
- `exposure_summary`
- `stress_period_summary`

约束：

- `execution_assumptions` 必须包含 `T+1`、涨跌停、停牌、最小交易单位、滑点和费用。
- 如果 benchmark 仍是 `synthetic_demo`，整个 backtest artifact 不能升到 `verified`。

### 4. Replay Alignment Artifact

回答“单票 recommendation replay 如何与研究标签对齐”。

必填字段：

- `artifact_id`
- `manifest_id`
- `recommendation_id`
- `recommendation_key`
- `label_definition`
- `review_window_definition`
- `entry_rule`
- `exit_rule`
- `benchmark_definition`
- `hit_definition`
- `stock_return`
- `benchmark_return`
- `excess_return`
- `validation_status`

约束：

- `review_window_definition` 必须与 manifest 中的 label horizon 对齐。
- `hit_definition` 必须是研究批准规则，不允许继续使用“直到今天最新价”的迁移口径。

## Split Plan Contract

每个 rolling validation manifest 的 `split_plan` 至少应包含：

- `train_start`
- `train_end`
- `validation_start`
- `validation_end`
- `test_start`
- `test_end`
- `slice_label`
- `market_regime_tag`

约束：

- 每个 slice 必须可独立复跑。
- 任何跨 slice 聚合指标都必须能反查到原 slice 结果。

## Product-Facing Projection Rules

从 artifact 到产品层的投影必须遵守以下规则：

- `historical_validation.status`
  - 只能由 artifact gate 决定，不能由 recommendation payload 直接硬写。
- `historical_validation.artifact_id`
  - 必须指向 validation manifest 或 validation metrics artifact。
- `historical_validation.metrics`
  - 默认只投影经过批准的摘要指标。
- `portfolio.validation_status`
  - 必须来自 backtest artifact gate，而不是组合页面本地逻辑。
- `replay.validation_status`
  - 必须来自 replay alignment artifact 与 manifest 对齐结果。

## Migration Projection Envelope

Phase 1 迁移态 consumer 还需要额外暴露一层“当前这是不是正式验证”的语义壳，直到 Phase 2 真实产物完全接管。

固定字段：

- `source_classification`
  - 只允许取值 `artifact_backed` 或 `migration_placeholder`
  - 用来回答“当前页面展示是否已经接到了 artifact 文件/对象”
- `validation_mode`
  - 只允许取值 `artifact_backed` 或 `migration_placeholder`
  - 用来回答“当前字段是否已经可以被解释为正式验证结论”

约束：

- `artifact_backed` 不等于 `verified`；只说明已经有 artifact 产物可读。
- 只要 benchmark、成本、执行假设或 hit 定义仍属迁移占位，`validation_mode` 就必须保持 `migration_placeholder`。
- 前端必须优先展示定义性字段和 `validation_mode`，不能在 `validation_mode=migration_placeholder` 时突出展示命中率、超额收益或拍脑袋窗口数字。
- 对于仍需保留的 compat 命中率字段，例如 `recommendation_hit_rate` 与 `recommendation_replay_hit_rate`，只要结果未进入 `verified`，产品层就必须返回 `null` 或缺失，而不是 `0.0` 这类看似真实的统计值。
- `simulation` 与 `portfolio workspace` 中保留的执行动作如果仍来自 placeholder 预算、半仓或其他启发式试算，必须显式标记为 `execution_policy_placeholder` / `migration_placeholder_estimate`，且不得自动落成模型轨道成交。

## Minimum Gate For `verified`

以下条件同时满足，结果才允许进入 `verified`：

- 存在可读取的 validation manifest
- 存在与 manifest 对齐的 validation metrics artifact
- benchmark 来源为真实可追溯定义
- execution / cost assumptions 完整
- 无未来函数或时间可得性违规
- 已记录 sample coverage 与 turnover
- 研究批准日志已写入 `DECISIONS.md`

## Storage Layout

建议落盘结构：

- `artifacts/manifests/<artifact_id>.json`
- `artifacts/validation/<artifact_id>.json`
- `artifacts/backtests/<artifact_id>.json`
- `artifacts/replays/<artifact_id>.json`

约束：

- artifact 文件内容必须可序列化、可版本化、可被 recommendation trace 间接引用。
- 后续如果切换到数据库或对象存储，路径语义仍要保留为 manifest identity 的一部分。
