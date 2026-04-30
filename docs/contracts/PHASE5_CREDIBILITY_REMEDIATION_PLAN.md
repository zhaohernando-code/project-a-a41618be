# Phase 5 Credibility Remediation Plan

## Purpose

本文件把当前股票看板的“专业性和可信度整改”收口成可执行路线，供后续实现、研究和会话恢复直接使用。

它不替代现有合同文档：

- `PROJECT_PLAN.md` 负责长期路线和阶段边界
- `docs/contracts/PHASE5_RESEARCH_CONTRACT.md` 负责当前研究合同
- `DECISIONS.md` 负责批准和关键取舍
- `PROCESS.md` 负责执行日志

本文件只回答一个问题：

- 当前要先改什么，才能把产品从“透明的研究辅助看板”推进到“更专业、更可信、可较强依赖的决策支持系统”

## Current Assessment

当前系统的主要优点不是“预测已经证明成立”，而是“展示比多数同类产品诚实”。当前专业性来自以下几点：

- recommendation 已明确拆成 `core_quant / evidence / risk / historical_validation / manual_llm_review`
- 风险层会在验证未通过或证据不足时主动暴露 `coverage_gaps`
- manual research 没有再伪装成核心打分因子
- simulation auto-execution 仍被严格限定在 web 模拟盘，不扩展到真实交易

当前系统仍不够“高可信”的核心原因也很明确：

- 组合层 after-cost 结果仍显著为负
- 主 horizon 仍停留在 `10d / 20d` 的 split leadership
- 当前真实样本规模过小，无法支撑强结论
- 部分展示仍会把内部融合层语义翻译成对用户帮助有限的占位式解释

## Baseline Facts

以下事实构成当前整改的起点，而不是可选解释：

- `phase5-holding-policy-study:auto_model:2026-04-24:3portfolios` 仍为 `research_candidate_only`
- 当前 holding-policy gate 为 `draft_gate_blocked`
- `mean_annualized_excess_return_after_baseline_cost = -12.849842`
- `positive_after_baseline_cost_portfolio_count = 0`
- `mean_invested_ratio = 0.075433`
- `mean_active_position_count = 1.0`
- `phase5-horizon-study:latest:active_watchlist:2026-04-24:3symbols` 当前结论仍是 `split_leadership`
- 当前 candidate frontier 仍是 `10d` 与 `20d`

因此，当前整改重点不能放在“页面更好看”或“话术更专业”，而必须先放在：

- 组合层 profitability 是否成立
- 主 horizon 是否批准
- 研究样本是否足够
- 对外展示是否严格服从 artifact 和 gate

## Remediation Principles

1. 信任优先来自实证，不来自解释。
2. 组合层未成立之前，不升级任何更强产品承诺。
3. 主 horizon 未批准之前，不把单一周期包装成产品事实。
4. 样本不足时，默认降级展示，而不是补强话术。
5. UI 专业感只能跟在研究可信度之后，不能反过来替代它。

## Priority P0

### P0.1 Rebuild after-cost profitability

目标：
先把“组合层扣成本后是否成立”变成当前 phase 的第一判断轴。

当前问题：

- after-cost excess 仍为负
- 正 after-cost 组合数为零
- 实际持仓暴露过薄

执行重点：

- 以 `profitability_signal_threshold_sweep_v1` 为当前收益侧第一实验
- 以 `construction_max_position_count_sweep_v1` 为当前持仓构造侧第一实验
- 保持当前 policy 为 non-promotion，直到 gate 不再被 profitability blocker 拦住
- 每轮实验都必须落成 durable artifact，禁止只在 notebook 或临时日志里讨论结论

完成标准：

- `mean_annualized_excess_return_after_baseline_cost >= 0`
- `positive_after_baseline_cost_portfolio_ratio` 不再接近零
- `mean_invested_ratio` 与 `mean_active_position_count` 不再表现为过薄暴露
- gate 至少从“明确 blocked”推进到“可继续研究而非立即 redesign”

### P0.2 Freeze product claim ceiling

目标：
在 P0.1 没通过之前，所有用户可见表达都不得强于当前研究事实。

执行重点：

- simulation policy 继续保持 `research_candidate_only`
- 不新增任何接近“自动实盘”或“已验证组合策略”的产品表述
- 对外主语义继续以辅助观察、风险提示、研究候选为上限

完成标准：

- 页面、文档、状态文件和 artifact 对当前 policy 级别表达一致
- 没有 consumer 绕过 gate/governance 直接把研究候选说成已批准能力

## Priority P1

### P1.1 Resolve primary horizon

目标：
把当前 `10d / 20d` 的 split leadership 收敛为明确可执行口径。

执行重点：

- 在统一 benchmark、cost、walk-forward coverage 口径下继续比较 `10 / 20 / 40`
- 扩大研究样本后重跑 horizon study，而不是继续依赖当前 3-symbol 视角
- 若仍无法收敛，则必须明确双轨使用规则，而不是默认选择其中一个

完成标准：

- `primary_horizon_status` 不再停留在 `pending_phase5_selection`
- recommendation、validation、replay 和 operations 统一消费同一主 horizon 定义

### P1.2 Expand sample and robustness coverage

目标：
把当前研究证据从“可说明方向”推进到“可支撑稳健性判断”。

执行重点：

- 扩大研究 universe
- 拉长有效观察期
- 提升可用 replay/validation 样本数
- 增加 regime、行业、时段切片
- 补齐子区间表现，而不是只看聚合均值

完成标准：

- 单票和组合层都能提供比当前更大规模的样本支持
- 研究结论不再主要依赖少量 symbol 或少量 portfolio
- 稳健性结论可按切片回查，而不是只保留总均值

### P1.3 Introduce user-facing claim gates

目标：
建立“什么时候允许展示方向判断”的硬规则。

执行重点：

- 为方向类展示绑定最低 `sample_count`
- 为验证展示绑定最低 `coverage_ratio`
- 要求 benchmark、cost、window definition 都明确可回查
- 未达标时统一降级为“观察/风险提示/待补样本”

完成标准：

- `偏积极 / 偏谨慎 / 继续观察` 不再只是前端展示习惯，而是受验证门槛约束
- 没有 artifact 支撑的方向表达自动降级

## Priority P2

### P2.1 Add robustness reporting

目标：
让用户和 operator 看到“稳定不稳定”，而不只是一个均值。

执行重点：

- 补充阶段表现
- 补充行业切片
- 补充子区间波动
- 补充稳定/不稳定标签或置信区间式表达

完成标准：

- 历史验证层不再只展示单一均值指标
- 主界面与运营层都能表达结论的稳定性边界

### P2.2 Remove placeholder-style explanatory copy

目标：
把“内部模块解释”替换成“用户可理解的研究解释”。

当前反例：

- “用于汇总价格、事件与降级状态的融合层” 这类文案对用户没有直接帮助

执行重点：

- 核心驱动必须解释是什么信号在起作用
- 风险项必须解释什么事件会使结论失效
- 不再把内部系统层名当成对外专业表达

完成标准：

- 用户在 `核心驱动 / 反向风险 / 何时失效` 中看到的是研究解释，不是内部实现术语

### P2.3 Strengthen abstention as a first-class capability

目标：
把“不下判断”正式化，而不是把所有情况都压成方向标签。

执行重点：

- 证据冲突时默认降级
- 样本不足时默认降级
- manual research 未完成时不补强主判断
- coverage gaps 必须能实质影响页面结论级别

完成标准：

- 系统在证据不足时能稳定输出“放弃强结论”
- 弃权是正式能力，不再只是提示文案

## Execution Order

当前建议按三波推进：

1. Wave 1
   先完成 P0.1 与 P0.2，严格锁住 claim ceiling，并围绕 holding-policy redesign 主实验推进。
2. Wave 2
   完成 P1.1、P1.2、P1.3，把 horizon、样本规模和展示门槛一起收口。
3. Wave 3
   完成 P2.1、P2.2、P2.3，在不削弱 honesty 的前提下提升专业表达。

## File And Module Landing Map

### Research and artifacts

- `src/ashare_evidence/phase2/holding_policy_study.py`
- `src/ashare_evidence/phase2/horizon_study.py`
- `src/ashare_evidence/phase2/validation.py`
- `src/ashare_evidence/research_artifacts.py`
- `data/artifacts/studies/`
- `data/artifacts/validation/`

### Product contract and gating

- `src/ashare_evidence/services.py`
- `src/ashare_evidence/operations.py`
- `src/ashare_evidence/contract_status.py`
- `docs/contracts/PHASE5_RESEARCH_CONTRACT.md`

### User-facing display

- `frontend/src/App.tsx`
- `frontend/src/types.ts`
- `output/acceptance/`

## Non-Goals

以下事项当前不应成为主线：

- 单纯为了“更像专业终端”而做视觉包装
- 在未通过 P0/P1 之前增强建议语气
- 在未补足样本前提前宣传命中率或收益率
- 把 manual research 重新包装成主评分能力

## Acceptance Checklist

当且仅当以下条件大体成立，才可以认为“可信度整改”进入下一阶段：

- 组合层 after-cost 结果不再明显为负
- primary horizon 已批准或有明确双轨规则
- 样本规模和切片稳健性明显高于当前基线
- 页面方向表达受到硬门槛约束
- 主界面解释文案不再泄漏内部占位语义
- 风险提示和弃权能力能真实压低结论强度

## Status

当前状态：

- 本文件已创建，但大部分整改项仍未完成
- 当前默认活动 phase 仍为 `Phase 5 - Real Validation Rebuild and Model Portfolio Policy Research`
- 当前首要执行目标仍是 holding-policy redesign 与 horizon/sample 收口，而不是前端包装

