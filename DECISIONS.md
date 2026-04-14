# 一个关于a股的当前数据和投资建议看板 Decisions

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
