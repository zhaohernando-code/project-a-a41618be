# 一个关于A股的当前数据和投资建议看板

当前版本已经从“适配 GitHub Pages 的离线演示前端”收口为“适配自托管服务器的一期服务端模式”：

- 前端不再暴露“在线 API / 离线快照”切换，也不再让用户配置项目后端地址。
- 股票真实数据统一由服务端获取，围绕全站共享关注池做热点缓存。
- 一期本地持久化确定为 `SQLite`，热点缓存方案确定为 `Redis`。
- Web 新增“模型配置”视图，支持整站共享的大模型 `API Key` 管理、默认 Key 和故障切换。

## 当前实现

- 后端：`Python 3.10+ + FastAPI + SQLAlchemy`
- 前端：`Vite + React + TypeScript + Ant Design`
- 本地持久化：
  - `watchlist_entries`
  - `app_settings`
  - `provider_credentials`
  - `model_api_keys`
- 统一数据源策略：
  - `AKShare`：实时行情与公开站点补缺
  - `Tushare`：日线/K 线、财报与结构化指标
  - 运行时选源，不在一期固化单一主源
- 统一缓存策略：
  - 实时行情：`5s`
  - K 线：`60s`
  - 财报：`86400s`
  - 仅对全站共享关注池预热
  - 启用单飞刷新、失败读旧值、空结果 TTL、锁超时与抖动
- LLM 分析链路：
  - 多个模型 Key
  - 默认 Key
  - 分析时显式选择 Key
  - 主 Key 失败时按优先级自动故障切换

## 主要接口

- `/health`
- `/watchlist`
- `/watchlist/{symbol}/refresh`
- `/dashboard/candidates`
- `/dashboard/glossary`
- `/dashboard/operations`
- `/stocks/{symbol}/dashboard`
- `/recommendations/{id}/trace`
- `/settings/runtime`
- `/settings/provider-credentials/{provider_name}`
- `/settings/model-api-keys`
- `/settings/model-api-keys/{id}`
- `/settings/model-api-keys/{id}/default`
- `/analysis/follow-up`

## 运行方式

```bash
PYTHONPATH=src uvicorn ashare_evidence.api:app --reload

cd frontend
npm run dev
```

如果前后端分离部署，需要在构建前设置：

```bash
export VITE_API_BASE_URL=http://127.0.0.1:8000
```

## 验证

本轮已完成：

```bash
python3 -m py_compile \
  src/ashare_evidence/models.py \
  src/ashare_evidence/runtime_config.py \
  src/ashare_evidence/llm_service.py \
  src/ashare_evidence/api.py \
  src/ashare_evidence/operations.py \
  src/ashare_evidence/schemas.py \
  tests/test_runtime_config.py

cd frontend
npm run build
```

本轮未完成：

- `PYTHONPATH=src python3 -m unittest discover -s tests`

原因：当前沙箱内缺少 `fastapi`、`sqlalchemy` 等 Python 依赖，且网络被限制，无法在线安装。

## 当前边界

- 真实 `AKShare / Tushare` 适配器与 `Redis` 实连尚未在当前受限环境完成联调。
- `frontend_snapshot` 等离线导出工具仍保留在仓库里作为历史产物，但前端主路径已不再依赖它们。
- LLM 分析接口采用 OpenAI-compatible 协议，当前已完成 Key 选择与故障切换逻辑，但未在本环境对外部模型服务做真实连通验证。
