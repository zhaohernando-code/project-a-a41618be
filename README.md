# 一个关于a股的当前数据和投资建议看板

当前仓库已经完成第 5 步“分离式模拟交易与内测准入”的 demo 实现：在证据优先的数据、建议和解释闭环之上，继续补齐了手动模拟交易、模型自动持仓、收益归因、回撤监控、基准对比、建议命中复盘，以及小范围内测所需的访问控制、刷新策略、性能阈值和上线门槛。

## 当前实现

- 后端技术栈：`Python 3.12 + FastAPI + SQLAlchemy`
- 前端技术栈：`Vite 4 + React 18 + TypeScript`
- 数据路线预留：`Tushare Pro + 巨潮资讯/交易所披露 + Qlib`，当前用 `DemoLowCostRouteProvider` 证明链路
- 新增 dashboard demo watchlist：`600519.SH`、`300750.SZ`、`601318.SH`、`002594.SZ`
- 强制血缘字段：`license_tag`、`usage_scope`、`redistribution_scope`、`source_uri`、`lineage_hash`
- 已交付信号层：
  - `price_baseline_factor`
  - `news_event_factor`
  - `llm_assessment_factor`
  - `fusion_scorecard`
- 已交付建议输出：方向、置信表达、核心驱动、反向风险、适用周期、更新时间、降级条件、因子拆解、验证快照
- 已交付用户闭环：
  - 候选股推荐页：按方向、置信度和趋势排序展示 watchlist
  - 单票分析页：价格走势、关键指标、相关新闻、建议摘要和变化原因
  - 解释与追问：术语解释、证据回溯、风险提示、GPT 追问包
- 已交付模拟交易与内测闭环：
  - 分离式模拟交易：`手动模拟仓` 与 `模型自动持仓模拟仓` 独立记账、独立收益归因、独立回撤阈值
  - A 股规则检查：整手约束、T+1 卖出、印花税方向、涨跌停边界
  - 组合运营视图：净值曲线、基准对比、收益归因、近期订单审计、建议命中复盘
  - 内测治理：header allowlist 访问控制、刷新节奏、性能预算、上线门槛
- 已落表域模型：
  - 股票与板块：`stocks`、`sectors`、`sector_memberships`
  - 行情与事件：`market_bars`、`news_items`、`news_entity_links`
  - 特征与模型：`feature_snapshots`、`model_registries`、`model_versions`、`model_runs`、`model_results`
  - 建议与证据：`prompt_versions`、`recommendations`、`recommendation_evidence`
  - 模拟交易：`paper_portfolios`、`paper_orders`、`paper_fills`
  - 采集审计：`ingestion_runs`
- 已交付入口：
  - CLI：初始化数据库、写入 demo 数据、写入 dashboard watchlist、查看候选页/单票页 payload、查看完整 trace
  - API：
    - `/health`
    - `/bootstrap/demo`
    - `/bootstrap/dashboard-demo`
    - `/dashboard/candidates`
    - `/dashboard/glossary`
    - `/dashboard/operations`
    - `/stocks/{symbol}/recommendations/latest`
    - `/stocks/{symbol}/dashboard`
    - `/recommendations/{id}/trace`
  - Frontend：`frontend/` 下可构建 GitHub Pages 子页面静态站点

## 目录

- [src/ashare_evidence/models.py](./src/ashare_evidence/models.py): 证据化数据模型
- [src/ashare_evidence/providers.py](./src/ashare_evidence/providers.py): 低成本路线 provider contract 与 demo provider
- [src/ashare_evidence/dashboard_demo.py](./src/ashare_evidence/dashboard_demo.py): 多股票 watchlist demo 数据与上一版/当前版建议构造
- [src/ashare_evidence/signal_engine.py](./src/ashare_evidence/signal_engine.py): 价格/新闻/LLM/融合信号引擎
- [src/ashare_evidence/services.py](./src/ashare_evidence/services.py): 入库、trace、建议查询服务
- [src/ashare_evidence/dashboard.py](./src/ashare_evidence/dashboard.py): 候选页、单票页、变化原因、术语和追问聚合服务
- [src/ashare_evidence/api.py](./src/ashare_evidence/api.py): FastAPI 应用
- [tests/test_traceability.py](./tests/test_traceability.py): 回溯链路验证
- [tests/test_dashboard_views.py](./tests/test_dashboard_views.py): 用户看板 payload 验证
- [frontend/src/App.tsx](./frontend/src/App.tsx): 候选股页 + 单票解释页主界面

## 本地运行

当前环境可直接用 `PYTHONPATH=src` 启动，无需先打包安装。

```bash
PYTHONPATH=src python3 -m ashare_evidence load-demo --database-url sqlite:///./data/validation.db
PYTHONPATH=src python3 -m ashare_evidence load-dashboard-demo --database-url sqlite:///./data/validation.db
PYTHONPATH=src python3 -m ashare_evidence candidates --database-url sqlite:///./data/validation.db
PYTHONPATH=src python3 -m ashare_evidence stock-dashboard --database-url sqlite:///./data/validation.db --symbol 600519.SH
PYTHONPATH=src python3 -m ashare_evidence operations --database-url sqlite:///./data/validation.db --sample-symbol 600519.SH
PYTHONPATH=src python3 -m ashare_evidence latest --database-url sqlite:///./data/validation.db --symbol 600519.SH
PYTHONPATH=src python3 -m ashare_evidence trace --database-url sqlite:///./data/validation.db --recommendation-id 1
PYTHONPATH=src uvicorn ashare_evidence.api:app --reload

cd frontend
npm install
npm run build
```

### 小范围内测访问控制

默认配置为 `open_demo`，方便本地直接打开前端和 API。

如果要切到带 allowlist 的闭测模式，可设置：

```bash
export ASHARE_BETA_ACCESS_MODE=allowlist
export ASHARE_BETA_ACCESS_HEADER=X-Ashare-Beta-Key
export ASHARE_BETA_ALLOWLIST="viewer-token:viewer,analyst-token:analyst,operator-token:operator"
```

前端也可通过以下方式附带 key：

```bash
export VITE_BETA_ACCESS_HEADER=X-Ashare-Beta-Key
export VITE_BETA_ACCESS_KEY=viewer-token
```

## 当前边界

- 真实 `Tushare / 巨潮 / Qlib` 网络适配器还未接入，当前以 demo provider 验证 schema、信号引擎 contract 和 trace 逻辑
- 当前滚动验证指标和 LLM 因子历史评估仍为 demo/offline payload，下一步要替换成真实 walk-forward 结果
- GPT 追问入口当前交付为“带证据上下文的追问包生成器”，尚未直接接入在线 LLM 会话服务
- 当前访问控制仍是轻量级 allowlist/header 方案，正式外部部署前仍建议接到更稳妥的身份系统或反向代理鉴权
