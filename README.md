# 一个关于A股的当前数据和投资建议看板

当前版本已经收口为“服务器入口 + 本机后端与数据库 + 反向隧道暴露”的一期服务端模式：

- 前端不再暴露“在线 API / 离线快照”切换，也不再让用户配置项目后端地址。
- 股票真实数据统一由服务端获取，围绕全站共享关注池做热点缓存。
- 一期本地持久化确定为 `SQLite`，热点缓存方案确定为 `Redis`。
- Web 新增“模型配置”视图，支持整站共享的大模型 `API Key` 管理、默认 Key 和故障切换。

## Canonical docs

- `PROJECT_STATUS.json`: current phase, blockers, next step, and linked docs
- `README.md`: operator-facing overview, entry routes, and publish rules
- `PROJECT_RULES.md`: repo-local constraints and live-verification requirements
- `DECISIONS.md`: durable research, rollout, and product decisions
- `PROCESS.md`: reusable lessons and anti-regression notes
- `PROJECT_PLAN.md`: long-lived project plan and phase summary
- `docs/contracts/`: active research, rollout, and metric contracts
- `docs/archive/`: archived audit and research notes that are not default entry docs

## 当前访问入口

- 统一登录首页：`https://hernando-zhao.cn/`
- 用户入口：`https://hernando-zhao.cn/stocks`
- 规范挂载路径：`https://hernando-zhao.cn/projects/ashare-dashboard/`
- 标准访问与验收都应优先使用不带 query 参数的规范挂载路径；`?cb=...` 只允许在排查缓存异常时临时使用，不应作为日常固定入口
- 健康检查：`https://hernando-zhao.cn/projects/ashare-dashboard/api/health`
- 本机后端：`127.0.0.1:8000`
- 本机前端预览：`127.0.0.1:5173`

## 本机运行拓扑

- 开发目录：`~/codex/projects/stock_dashboard`
- 运行目录：`~/codex/runtime/projects/ashare-dashboard`
- 控制平面的 worker task 会自动把代码同步到运行目录，并重启本机 frontend/backend 的 LaunchAgent
- 直接在正式 repo 中运行的 Codex 会话不自动继承这条发布链；如果改动影响 live service，结束前必须手动执行 `scripts/publish-local-runtime.sh`
- 对外服务必须跑在运行目录，不直接跑开发目录

## 当前实现

- 后端：`Python 3.10+ + FastAPI + SQLAlchemy`
- 前端：`Vite + React + TypeScript + Ant Design`
- 本地持久化：
  - `watchlist_entries`
  - `app_settings`
  - `provider_credentials`
  - `model_api_keys`
- 统一数据源策略：
  - `AKShare`：已接入运行时主数据/公开站点补缺，当前通过 `stock_individual_info_em` 解析股票简称、行业与上市时间
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
  - `manual research` 在不选择模型 Key 时，默认改走本机 Codex CLI builtin executor，并以 `gpt-5.5` 直接执行；只有本机 Codex 不可用时才会回退到 unavailable 提示

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

如果只是在本机做前端调试，可以临时设置：

```bash
export VITE_API_BASE_URL=http://127.0.0.1:8000
```

当前长期运行由 LaunchAgent 管理，入口脚本应指向运行目录中的：

- `~/codex/runtime/projects/ashare-dashboard/scripts/start-local-backend.sh`
- `~/codex/runtime/projects/ashare-dashboard/scripts/start-local-frontend.sh`
- `~/codex/runtime/projects/ashare-dashboard/scripts/run-scheduled-refresh.sh`

推荐的本地发布命令：

```bash
cd ~/codex/projects/stock_dashboard
scripts/publish-local-runtime.sh
```

这条命令现在是项目内唯一批准的 live publish 路径。它会先拒绝 dirty worktree，然后从当前 `HEAD` commit 出发构建 repo 前端、同步到 runtime、重启 frontend/backend LaunchAgent，并校验 `127.0.0.1:8000/health` 与 `127.0.0.1:5173/`。

## Task closeout

- Default branch name: `task/stock_dashboard/<yyyymmdd>-<slug>`
- Before calling work complete, update `DECISIONS.md`, `PROCESS.md`, and `PROJECT_STATUS.json` when the change affects durable decisions, reusable lessons, or current handoff state.
- Live-facing work is not complete until publish and real browser verification have both finished.

## 开发测试必读

- 所有 live-facing 改动都必须区分 `repo` 与 `runtime`：`~/codex/projects/stock_dashboard` 只是可编辑源码，真实服务只认 `~/codex/runtime/projects/ashare-dashboard`。`npm run build` 或 repo 内本地测试通过，不代表用户已经能看到结果。
- 标准发布路径只有 `scripts/publish-local-runtime.sh`。如果主仓库是 dirty worktree，不要跳过发布，也不要直接改 runtime；应从当前 `HEAD` 做临时干净快照仓，再在快照仓里执行同一脚本。
- 发布后先看本机健康，再看浏览器：至少确认 `http://127.0.0.1:8000/health` 和 `http://127.0.0.1:5173/` 正常，再进入页面验收。不要把浏览器异常直接当成发布失败。
- `127.0.0.1:5173/` 首屏先出现 skeleton 或 hydration 延迟是允许现象，必须等待页面真正渲染完成后再判断。单个空白页、灰页或一次加载失败，不足以证明 runtime 没更新。
- 点击/浏览器验收至少分两路：1) 本机预览 `http://127.0.0.1:5173/`；2) 真实标准入口 `https://hernando-zhao.cn/projects/ashare-dashboard/`。两路都过，才算 live-facing 验收闭环。
- 标准入口默认只用不带 query 的规范路径。`?cb=...` 只能在明确排查缓存异常时临时使用，不能把带 `cb` 的链接当成日常验收入口，更不能据此宣布发布完成。
- 如果 Browser Use、Chrome 或当前标签页状态可疑，不要在一个异常标签上反复猜。先检查 URL 是否输对、标签页是否仍持有旧登录态或旧内存态；必要时改用 Safari 重新打开标准入口和本机入口做交叉验证。
- `scripts/publish-local-runtime.sh` 最后如果只卡在 canonical verifier 缺 `ASHARE_CANONICAL_USERNAME` / `ASHARE_CANONICAL_PASSWORD`，这次任务仍不能默认为“已自动验收完成”；必须补手工浏览器复验，并明确记录“自动 verifier 未跑通、改由人工复验”的事实。
- 每次手工点击验收都要记下这四类证据：发布所用仓库路径、是否为临时干净快照、实际检查的 URL、最终浏览器结果。若出现空白页、URL 手误、浏览器假阴性或 hydration 误判，也必须写回 `PROCESS.md`，防止后续会话重复踩坑。
- 使用 Playwright CLI 或其他自动化浏览器完成验收后，必须执行 `scripts/cleanup-browser-automation.sh`。这会关闭 Playwright daemon 和 `playwright_chromiumdev_profile-*` 自动化 Chrome，避免测试后残留进程越积越多；脚本不会关闭用户正常的 Chrome 主进程。

发布完成的定义也已经收紧：脚本最后会自动执行 release parity verifier，只有在以下条件全部满足时才算成功：

- repo build、runtime `frontend/dist`、localhost served frontend、canonical authenticated route 的 asset hash 全部一致
- `/dashboard/operations`、`/settings/runtime`、`/dashboard/candidates` 的本地与 canonical API fingerprint 一致
- 运营复盘的 user-visible 文本审计通过：必须保留 `用户轨道`、`模型轨道`，且不能重新出现 `运营复盘口径仍在迁移`、`Phase 5 baseline`、`research contract`、`pending_rebuild`、`manifest`、`verified`
- `output/releases/<release-id>/manifest.json` 与 `output/releases/latest-successful.json` 成功生成

如需执行 canonical parity 校验，请先提供这些环境变量：

```bash
export ASHARE_CANONICAL_USERNAME='<login-username>'
export ASHARE_CANONICAL_PASSWORD='<login-password>'
```

可选环境变量：

```bash
export ASHARE_CANONICAL_BASE_URL='https://hernando-zhao.cn/projects/ashare-dashboard/'
export ASHARE_CANONICAL_LOGIN_URL='https://hernando-zhao.cn/auth/login'
export ASHARE_LOCAL_API_BASE_URL='http://127.0.0.1:8000/'
export ASHARE_RELEASE_BETA_ACCESS_KEY='<beta-access-key-if-needed>'
export ASHARE_RELEASE_OUTPUT_ROOT="$PWD/output/releases"
```

每次成功发布都会生成 release manifest，记录 commit SHA、asset hashes、关键 API fingerprints、artifact 路径，以及上一份成功 manifest 的路径与 commit SHA。后续若要回滚，只能回到上一份成功 manifest 对应的 release，不再允许从任意当前工作树或模糊 baseline 直接重发。

推荐的刷新时点已经按 `Tushare 5000 积分 + 免费分钟兜底` 收口为：

- `08:10`：盘前轻刷新，补主数据、披露计划和财报增量
- `16:20`：盘后主刷新，刷新 `daily`、`daily_basic`、财务指标和主 recommendation
- `19:20`：晚间补录资金流、股东增减持等日终字段
- `21:15`：夜间补全龙虎榜、大宗交易、质押等夜间数据
- 交易时段：仅对关注池和模拟持仓做 `5 分钟` 分钟行情同步，优先复用本地缓存

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

- `AKShare` 已接入主数据补缺和免费分钟兜底；`Tushare` Token 负责低频日线、财务和结构化指标主链路。
- `Redis` 实连尚未在当前受限环境完成联调，但前端与后端已经不再依赖任何 demo/offline snapshot。
- 盘中分钟链路当前采取“公开分钟源 + 本地缓存沉淀”，适合内部运营复盘，不等同于商业级分钟数据 SLA。
- LLM 分析接口采用 OpenAI-compatible 协议，当前已完成 Key 选择与故障切换逻辑，但未在本环境对外部模型服务做真实连通验证。
