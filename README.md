# 一个关于a股的当前数据和投资建议看板

当前仓库已经完成“返修验收”版本：在既有证据优先数据底座、建议引擎和模拟交易闭环之上，补齐了前端可离线运行的数据闭环，并把页面重构为可操作的控制台风格面板。即使在线 API 不可用，静态部署页面也能直接完成候选股、单票分析、运营看板和 demo 初始化的最小可用闭环。

## 当前实现

- 后端技术栈：`Python 3.12 + FastAPI + SQLAlchemy`
- 前端技术栈：`Vite 4 + React 18 + TypeScript + Ant Design`
- 数据路线预留：`Tushare Pro + 巨潮资讯/交易所披露 + Qlib`，当前用 `DemoLowCostRouteProvider` 证明链路
- 新增 dashboard demo watchlist：`600519.SH`、`300750.SZ`、`601318.SH`、`002594.SZ`
- 强制血缘字段：`license_tag`、`usage_scope`、`redistribution_scope`、`source_uri`、`lineage_hash`
- 新增前端离线闭环：
  - `frontend/src/offline-snapshot.json` 由当前后端 dashboard contract 导出，不是另一套手写伪数据
  - 前端支持 `在线 API / 离线快照` 两种模式，默认在无 `VITE_API_BASE_URL` 时走离线快照
  - 在线 API 不可用或 access key 缺失时，页面自动回退到离线快照并给出提示
  - `重置演示数据` 按钮在线上不可达时也可恢复内置 demo 快照
- 新增自选池闭环：
  - 在线 API 模式支持输入股票代码，把标的加入自选池、移除自选池、重新触发分析
  - 新增标的后会即时生成上一版/当前版 recommendation、候选排序、单票分析和模拟交易上下文
  - 固定 demo watchlist 已下沉为可持久化 `watchlist_entries`，不再只能靠前端写死列表
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
  - UI 重构：顶部改为紧凑操作面板，支持数据模式切换、焦点股票切换、自选股新增/移除/重分析、在线 access key 应用和演示数据重置
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
  - 自选池：`watchlist_entries`
- 已交付入口：
  - CLI：初始化数据库、写入 demo 数据、写入 dashboard watchlist、查看候选页/单票页 payload、查看完整 trace、导出前端离线快照
  - API：
    - `/health`
    - `/bootstrap/demo`
    - `/bootstrap/dashboard-demo`
    - `/watchlist`
    - `/watchlist/{symbol}/refresh`
    - `/dashboard/candidates`
    - `/dashboard/glossary`
    - `/dashboard/operations`
    - `/stocks/{symbol}/recommendations/latest`
    - `/stocks/{symbol}/dashboard`
    - `/recommendations/{id}/trace`
  - Frontend：`frontend/` 下可构建 GitHub Pages 子页面静态站点

## 验收路径

### 路径 A：直接验收静态前端闭环

1. 打开部署后的前端页面。
2. 确认顶部“数据模式”为 `离线快照`，状态提示显示当前使用仓库内置快照。
3. 在 `候选股` 视图中点击任一股票，确认可以切到 `单票分析` 查看价格、建议、事件、证据、术语和 GPT 追问包。
4. 切到 `运营看板`，确认可以查看手动模拟仓、自动持仓仓、净值轨迹、订单审计、刷新策略和上线门槛。
5. 点击 `重置演示数据`，页面应提示已恢复内置演示快照，候选股、单票和运营看板继续可用。

这条路径不依赖在线 API，适合 GitHub Pages 子页面直接验收。

### 路径 B：验收在线 API 接入

1. 启动后端：

```bash
PYTHONPATH=src uvicorn ashare_evidence.api:app --reload
```

2. 以前端连接在线 API 的方式启动：

```bash
cd frontend
VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

3. 如后端启用 allowlist，再在顶部“内测访问”里填写 access key 并点击 `应用 access key`。
4. 把“数据模式”切到 `在线 API`，确认页面不再显示离线回退提示。
5. 在“加入自选”区域输入如 `688981` 或 `300750.SZ`，点击 `加入并分析`。
6. 确认新股票进入右侧自选池列表，并能在候选股、单票分析中查看新生成的数据；再验证 `重分析` 和 `移除` 按钮可用。

## 目录

- [src/ashare_evidence/models.py](./src/ashare_evidence/models.py): 证据化数据模型
- [src/ashare_evidence/providers.py](./src/ashare_evidence/providers.py): 低成本路线 provider contract 与 demo provider
- [src/ashare_evidence/dashboard_demo.py](./src/ashare_evidence/dashboard_demo.py): 多股票 watchlist demo 数据与上一版/当前版建议构造
- [src/ashare_evidence/signal_engine.py](./src/ashare_evidence/signal_engine.py): 价格/新闻/LLM/融合信号引擎
- [src/ashare_evidence/services.py](./src/ashare_evidence/services.py): 入库、trace、建议查询服务
- [src/ashare_evidence/dashboard.py](./src/ashare_evidence/dashboard.py): 候选页、单票页、变化原因、术语和追问聚合服务
- [src/ashare_evidence/api.py](./src/ashare_evidence/api.py): FastAPI 应用
- [src/ashare_evidence/frontend_snapshot.py](./src/ashare_evidence/frontend_snapshot.py): 前端离线快照导出器
- [tests/test_traceability.py](./tests/test_traceability.py): 回溯链路验证
- [tests/test_dashboard_views.py](./tests/test_dashboard_views.py): 用户看板 payload 验证
- [tests/test_frontend_snapshot.py](./tests/test_frontend_snapshot.py): 离线快照导出验证
- [frontend/src/App.tsx](./frontend/src/App.tsx): Ant Design 控制台式主界面
- [frontend/src/offline-snapshot.json](./frontend/src/offline-snapshot.json): 由后端 contract 导出的前端离线快照

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
PYTHONPATH=src python3 -m ashare_evidence export-frontend-snapshot --output frontend/src/offline-snapshot.json
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

如果要让前端默认连在线 API，可同时设置：

```bash
export VITE_API_BASE_URL=http://127.0.0.1:8000
```

## 当前边界

- 真实 `Tushare / 巨潮 / Qlib` 网络适配器还未接入，当前以 demo provider 验证 schema、信号引擎 contract 和 trace 逻辑
- 当前滚动验证指标和 LLM 因子历史评估仍为 demo/offline payload，下一步要替换成真实 walk-forward 结果
- GPT 追问入口当前交付为“带证据上下文的追问包生成器”，尚未直接接入在线 LLM 会话服务
- 当前访问控制仍是轻量级 allowlist/header 方案，正式外部部署前仍建议接到更稳妥的身份系统或反向代理鉴权
- 当前前端构建产物因 `Ant Design + 离线快照` 较大，`vite build` 会给出 chunk size warning；当前不影响功能验收，但正式公网发布前建议再做拆包与快照懒加载
