# 一个关于a股的当前数据和投资建议看板

当前仓库已经完成第 3 步“信号建模与建议引擎”的 demo 后端实现，目标是让任一建议都能按股票、时间、模型版本、提示词版本和原始证据完整回溯，并同时暴露价格/新闻/LLM/融合四层信号拆解。

## 当前实现

- 后端技术栈：`Python 3.12 + FastAPI + SQLAlchemy`
- 数据路线预留：`Tushare Pro + 巨潮资讯/交易所披露 + Qlib`，当前用 `DemoLowCostRouteProvider` 证明链路
- 强制血缘字段：`license_tag`、`usage_scope`、`redistribution_scope`、`source_uri`、`lineage_hash`
- 已交付信号层：
  - `price_baseline_factor`
  - `news_event_factor`
  - `llm_assessment_factor`
  - `fusion_scorecard`
- 已交付建议输出：方向、置信表达、核心驱动、反向风险、适用周期、更新时间、降级条件、因子拆解、验证快照
- 已落表域模型：
  - 股票与板块：`stocks`、`sectors`、`sector_memberships`
  - 行情与事件：`market_bars`、`news_items`、`news_entity_links`
  - 特征与模型：`feature_snapshots`、`model_registries`、`model_versions`、`model_runs`、`model_results`
  - 建议与证据：`prompt_versions`、`recommendations`、`recommendation_evidence`
  - 模拟交易：`paper_portfolios`、`paper_orders`、`paper_fills`
  - 采集审计：`ingestion_runs`
- 已交付入口：
  - CLI：初始化数据库、写入 demo 数据、查看最新建议、查看完整 trace
  - API：`/health`、`/bootstrap/demo`、`/stocks/{symbol}/recommendations/latest`、`/recommendations/{id}/trace`

## 目录

- [src/ashare_evidence/models.py](./src/ashare_evidence/models.py): 证据化数据模型
- [src/ashare_evidence/providers.py](./src/ashare_evidence/providers.py): 低成本路线 provider contract 与 demo provider
- [src/ashare_evidence/signal_engine.py](./src/ashare_evidence/signal_engine.py): 价格/新闻/LLM/融合信号引擎
- [src/ashare_evidence/services.py](./src/ashare_evidence/services.py): 入库、trace、建议查询服务
- [src/ashare_evidence/api.py](./src/ashare_evidence/api.py): FastAPI 应用
- [tests/test_traceability.py](./tests/test_traceability.py): 回溯链路验证

## 本地运行

当前环境可直接用 `PYTHONPATH=src` 启动，无需先打包安装。

```bash
PYTHONPATH=src python3 -m ashare_evidence load-demo --database-url sqlite:///./data/validation.db
PYTHONPATH=src python3 -m ashare_evidence latest --database-url sqlite:///./data/validation.db --symbol 600519.SH
PYTHONPATH=src python3 -m ashare_evidence trace --database-url sqlite:///./data/validation.db --recommendation-id 1
PYTHONPATH=src uvicorn ashare_evidence.api:app --reload
```

## 当前边界

- 真实 `Tushare / 巨潮 / Qlib` 网络适配器还未接入，当前以 demo provider 验证 schema、信号引擎 contract 和 trace 逻辑
- 当前滚动验证指标和 LLM 因子历史评估仍为 demo/offline payload，下一步要替换成真实 walk-forward 结果
- 下一阶段重点转向用户看板与解释闭环，而不是继续扩 demo 数据
