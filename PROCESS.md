# PROCESS

> Note: if older entries mention GitHub Pages or external dashboard hosting, treat them as historical context only. Current UI delivery is expected through the local self-hosted control plane.

## 2026-04-14

- Project scaffold created.
- Commit ID: pending

## 2026-04-22

- Problem: 本地发布会复用长生命周期的 baseline worktree；一旦该工作树残留了 `frontend/node_modules` 这类依赖符号链接，通用的目录忽略规则 `node_modules/` 不会命中这个 symlink，`git status` 就会把它当未跟踪文件，导致 auto-publish 反复以“无可提交变更但有脏工作树”失败。
- Resolution: 为前端依赖路径补了精确忽略规则 `frontend/node_modules`，并清理 baseline worktree 里的残留依赖链接，让发布基线重新只反映仓库内真实改动。
- Prevention: 以后凡是会在工作树内出现的依赖缓存、构建产物或符号链接，不能只依赖“目录型”忽略规则；如果发布/基线工作树可能残留 symlink，必须显式忽略该路径或把依赖放到仓库外。
- Commit ID: pending
- Context: project=一个关于a股的当前数据和投资建议看板, step=watchdog publish-state remediation

- Problem: 前端依赖 `echarts` 在当前镜像源安装结果里缺少 `package.json` 声明的 `index.d.ts`，`npm install` 虽然成功，但 `tsc` 在发布校验阶段会把 `import "echarts"` 判成“无声明文件”，导致任务被错误卡在 build gate。
- Resolution: 在前端源码内补了显式 `echarts` 类型 shim，让 TypeScript 直接落到包内实际存在的 `echarts/types/dist/echarts.d.ts`，不再依赖镜像产物里缺失的顶层类型入口。
- Prevention: 后续新增前端库时，不能只看 `package.json` 的 `types` 字段；如果发布链路依赖镜像或缓存包，必须确认声明文件真实存在，或在仓内提供稳定的本地类型入口，避免把第三方包体漂移放大成发布阻塞。
- Commit ID: pending
- Context: project=一个关于a股的当前数据和投资建议看板, step=watchdog build remediation

## 2026-04-14

- Problem: 免费 A 股数据源在授权、稳定性、字段覆盖和新闻可分发性上差异很大，若不先做基线评估，后续数据底座和建议引擎会反复返工。
- Resolution: 完成了行情、财务、板块、公告、新闻与量化框架的分层评估，明确一期采用 `Tushare Pro + 巨潮资讯 + Qlib` 的低成本主路线，并要求在数据底座内置 `license_tag`、`source_lineage` 和可替换适配层。
- Prevention: 以后涉及金融数据接入时，先确认来源授权、付费模式、升级触发条件和字段级展示边界，再开始表结构与采集实现。
- Commit ID: pending
- Context: project=一个关于a股的当前数据和投资建议看板, step=数据与开源基线评估

## 2026-04-14

- Problem: project flow research outputs had completed in the step worktree, but the project repository was never provisioned and the successful research result was not synchronized back into the canonical project baseline.
- Resolution: Synced the latest research artifacts back into the project root, created the GitHub repository `zhaohernando-code/project-a-a41618be`, and prepared the project state to continue from the post-research decision gate.
- Prevention: Auto-created repositories now use a stable GitHub-safe ASCII name, trust the repository creation response directly, and internal project steps no longer fail just because no origin was configured.
- Commit ID: pending
- Context: project=一个关于a股的当前数据和投资建议看板, source=local remediation

## 2026-04-15

- Problem: 第 2 步需要先把“建议可回溯”固化为底层 schema，否则后续接入真实 Tushare / 巨潮 / Qlib 时容易把证据字段散落在业务代码里，导致第 3 步建模和第 4 步解释页重复返工。
- Resolution: 新建了 `ashare_evidence` 后端包，落地了统一 lineage mixin、SQLAlchemy 域模型、demo provider、采集服务、trace API/CLI 和 unittest。当前已能把一条建议追溯到行情、公告、板块、特征、模型版本、提示词版本和模拟成交。
- Prevention: 后续所有真实 provider 都必须沿当前 contract 输出强制血缘字段，禁止在第 3 步绕开 `recommendation_evidence` 或单独存放无版本的建议文本。
- Commit ID: pending
- Context: project=一个关于a股的当前数据和投资建议看板, step=证据化数据底座

## 2026-04-15

- Problem: 初版 `lineage_hash` 只基于局部 payload 计算，导致不同模拟成交在 payload 模板相同时可能出现同一 hash，审计粒度不足。
- Resolution: 调整为对完整规范化记录计算 `lineage_hash`，并在测试中补充模拟成交 hash 不同的断言。
- Prevention: 以后新增任何证据记录时，hash 计算必须覆盖完整业务字段，不能只覆盖局部附加 payload。
- Commit ID: pending
- Context: project=一个关于a股的当前数据和投资建议看板, step=证据化数据底座

## 2026-04-15

- Problem: 第 3 步如果继续沿用静态 demo recommendation，就无法证明“价格基线 / 新闻因子 / LLM 因子 / 融合评分 / 降级规则”这条链路已经真正落地，后续接真实 provider 时会再次返工。
- Resolution: 新增 `signal_engine`，把 demo provider 改造成“原始行情和新闻证据 -> 因子快照 -> horizon 模型结果 -> recommendation”的可执行链路，并把 `confidence_expression`、`downgrade_conditions`、`factor_breakdown`、`validation_snapshot` 直接暴露到 API/CLI。
- Prevention: 后续接入真实 `Tushare / 巨潮 / Qlib` 或真实 LLM 时，必须沿当前 signal engine contract 接入，禁止重新回到在 provider 中手写 recommendation 文本的方式。
- Commit ID: pending
- Context: project=一个关于a股的当前数据和投资建议看板, step=信号建模与建议引擎

## 2026-04-15

- Problem: 如果用户看板阶段仍让前端自行拼接 recommendation、trace、行情、新闻和术语解释，后续一旦 recommendation schema 或风控口径变化，候选页、单票页和 GPT 追问入口会一起返工。
- Resolution: 新增 `dashboard_demo.py` 和 `dashboard.py`，把多股票 watchlist、上一版/当前版建议、变化原因、风险面板、术语解释和 GPT 追问上下文统一下沉为后端 contract；同时新增 `frontend/` 的 `Vite + React + TypeScript` 工程直接消费这些接口。
- Prevention: 后续接真实数据或真实 GPT 服务时，继续沿当前 `/dashboard/candidates`、`/stocks/{symbol}/dashboard` 和 `copy_prompt/evidence_packet` 结构扩展，避免把解释逻辑重新散落到前端。
- Commit ID: pending
- Context: project=一个关于a股的当前数据和投资建议看板, step=用户看板与解释闭环

## 2026-04-15

- Problem: 当前环境里的 `npm` 实际运行在 Node 16，直接使用 `Vite 5` 会触发 engine 不兼容，影响前端 build 验证。
- Resolution: 将前端工具链调整为 `Vite 4` 兼容组合，并把构建脚本改为 `tsc --noEmit -p tsconfig.app.json && vite build`，避免产生额外的编译输出文件。
- Prevention: 以后新建前端工程前先确认 `node` 与 `npm` 实际版本，优先选取与当前运行时兼容的 Vite/插件组合。
- Commit ID: pending
- Context: project=一个关于a股的当前数据和投资建议看板, step=用户看板与解释闭环

## 2026-04-15

- Problem: 第 6 步需要给组合层补历史净值、收益归因和建议命中复盘，但如果把历史 seed 订单也直接挂到当前 recommendation 上，单票 trace 会被旧订单污染，用户无法分清“当前建议触发的订单”和“组合历史仓位”。
- Resolution: 调整 `ingest_bundle`，只有 `order_record.recommendation_key` 与当前 recommendation 精确匹配时，订单才写入 `recommendation_id`；历史 seed 订单仅用于组合运营面板和回撤/基准演算。
- Prevention: 以后新增任何模拟交易历史样本时，都要显式区分 recommendation-linked orders 与 portfolio-history orders，禁止默认把同 bundle 内的所有订单都挂到当前 recommendation。
- Commit ID: pending
- Context: project=一个关于a股的当前数据和投资建议看板, step=分离式模拟交易与内测准入

## 2026-04-15

- Problem: 前端新增“模拟交易与内测”视图时，当前 worktree 里没有 `node_modules`，直接 `npm run build` 会因为找不到本地 `tsc` 而失败。
- Resolution: 使用本机缓存执行 `npm install --prefer-offline --no-audit --fund=false` 补齐依赖后重新 build，确认 `Vite + React + TypeScript` 前端可以成功产出静态包。
- Prevention: 以后在新 worktree 验证前端改动前，先确认依赖目录是否已准备好；若网络受限，优先尝试 `--prefer-offline` 走本机缓存。
- Commit ID: pending
- Context: project=一个关于a股的当前数据和投资建议看板, step=分离式模拟交易与内测准入

## 2026-04-15

- Problem: 并发对同一个 SQLite 文件同时执行 `load-dashboard-demo` 与查询命令时，`create_all()` 之间会发生建表竞态，触发 `table stocks already exists`。
- Resolution: 本轮验证改为串行初始化和查询，避免把第 6 步的运营面板结果建立在竞态数据库上。
- Prevention: 后续若要并发验证多个 CLI，使用不同的临时数据库文件，或先单独完成初始化再并发读写。
- Commit ID: pending
- Context: project=一个关于a股的当前数据和投资建议看板, step=分离式模拟交易与内测准入

## 2026-04-15

- Problem: 验收环境里的前端部署虽然能访问，但候选股、单票分析、运营看板和 demo 初始化都硬依赖在线 API；一旦后端不可达，GitHub Pages 页面就失去核心功能，无法形成最小可用闭环。
- Resolution: 新增 `frontend_snapshot` 导出器，把现有 dashboard contract 直接生成前端离线快照；前端改成“在线 API / 离线快照”双模式，并用 `Ant Design` 重构顶部操作面板与三大主视图。
- Prevention: 以后所有静态部署前端如果依赖独立后端，都必须提前设计离线降级路径或可演示的内置快照，验收文档里必须给出不依赖隐含环境的实际操作步骤。
- Note: 本轮仍无法执行 `git add -A`，同样受限于 `.git/worktrees/.../index.lock` 无法创建。
- Commit ID: pending
- Context: project=一个关于a股的当前数据和投资建议看板, step=Address acceptance feedback

## 2026-04-15

- Problem: 候选股列表之前完全依赖固定 demo watchlist，导致用户无法把自己的股票纳入候选池，也无法在加入后自动生成单票分析和候选排序。
- Resolution: 新增持久化 `watchlist_entries`、`/watchlist` 增删改接口、动态股票场景生成器和前端自选池操作区；现在输入股票代码后会立即生成上一版/当前版 recommendation，并同步进入候选股、单票分析和离线快照 contract。
- Prevention: 以后任何“自选池”需求都必须先落到可持久化的 watchlist 模型和统一分析入口，不能再只在前端维护一份静态 symbol 列表。
- Commit ID: pending
- Context: project=一个关于a股的当前数据和投资建议看板, step=Address acceptance feedback

## 2026-04-15

- Problem: 在线模式之前只读取构建时的 `VITE_API_BASE_URL`，页面里只有 `access key` 输入，没有后端地址配置入口；用户切到在线 API 后并不知道应该填什么地址，也无法在已部署页面上自行接入后端。
- Resolution: 前端新增运行时 `API Base URL` 配置，持久化到 `localStorage`，并在顶部“在线接入”里同时暴露后端地址、access key、恢复默认和明确提示文案，说明这里填写的是本项目后端地址，例如 `http://127.0.0.1:8000`，不是第三方行情或模型 API。
- Prevention: 以后凡是前后端分离的静态前端，只要支持“在线模式”，就必须同时提供运行时的后端地址配置入口和示例地址，不能只依赖构建时环境变量。
- Note: 本轮再次尝试 `git add` / `git commit`，仍然因为 `.git/worktrees/task-mnzv6k65-yigow8/index.lock` 无法创建而失败，提交与推送继续阻塞在 worktree 元数据写权限。
- Commit ID: pending
- Context: project=一个关于a股的当前数据和投资建议看板, step=Address acceptance feedback

## 2026-04-15

- Problem: 顶部 `候选股 / 当前焦点 / 最近刷新` 使用大号 `Statistic` 卡片并以 `2x2` 排列，头部高度被无效信息占据，压缩了真正的操作区。
- Resolution: 将顶部统计改为自定义紧凑指标条，缩小标题和数值字号、卡片内边距与整体 topbar 间距，并把桌面端统计区调整为四列、移动端调整为两列回落。
- Prevention: 后续新增顶部摘要信息时，优先采用紧凑指标或标签式表达，避免把非核心摘要做成大号展示卡片。
- Note: 当前 worktree 仍无法创建 `.git/worktrees/.../index.lock`，本轮变更已完成并验证，但不能在该环境内执行 commit / push。
- Commit ID: pending
- Context: project=一个关于a股的当前数据和投资建议看板, step=Address acceptance feedback

## 2026-04-15

- Problem: 顶部 `候选股 / 当前焦点 / 最近刷新` 在返修后仍然偏高，标签与数值上下堆叠导致头部继续占据过多垂直空间。
- Resolution: 进一步压缩 `workspace-topbar` 的 padding、间距与标题说明字号，并把顶部摘要改成单行横向指标条，收紧标签/数值字号、圆角和内边距。
- Prevention: 后续顶部摘要默认先用单行指标条验证信息密度；如果一组信息不驱动操作，不再给它独立的大高度卡片。
- Validation: `cd frontend && npm ci && npm run build`
- Note: 本轮尝试 `git add` / `git commit` 仍失败，worktree 不能创建 `.git/worktrees/task-mnzvewru-wx9o5x/index.lock`。
- Commit ID: pending
- Context: project=一个关于a股的当前数据和投资建议看板, step=Address acceptance feedback

## 2026-04-15

- Problem: 用户在静态前端里想用“自选模式”时，仍被迫理解并配置“在线 API”，实际又分不清这里指的是项目后端还是第三方行情接口，导致自选池在无后端地址时近乎不可用。
- Resolution: 前端新增浏览器本地离线自选池，离线模式下也支持新增/移除/重分析股票，并在前端本地生成同结构演示分析；同时把文案统一改成“在线 API = 本项目后端，不是 Tushare/AkShare/OpenAI”。
- Prevention: 后续凡是带离线演示能力的前端，只要存在用户写操作，就必须明确提供“本地模式”或“项目后端模式”二选一，不能再把核心操作默认锁死到隐含后端配置上。
- Validation: `cd frontend && npm ci --prefer-offline --no-audit --fund=false && npm run build`; `PYTHONPATH=src python3 -m unittest discover -s tests`
- Note: 当前 worktree 仍未验证 git 提交链路，历史问题仍是 `.git/worktrees/.../index.lock` 写权限受限。
- Commit ID: pending
- Context: project=一个关于a股的当前数据和投资建议看板, step=Address acceptance feedback

## 2026-04-19

- Problem: 控制中台里的工具入口仍显示“当前工具还在补齐交付物，暂时不能直接打开”，但 `ashare-dashboard` 实际已经具备 `frontend/package.json`、GitHub Pages workflow 和本地可服务的静态产物，问题不在业务项目缺交付，而在控制台仍把 `self_hosted + pending` 的工具一律拦截。
- Resolution: 核对了运行态项目记录与已发布静态包，确认当前真正缺的是过时的 `deployment_ready` 门禁；随后刷新控制台发布包，放行 `self_hosted` 且未失败的工具直接打开本地 `/tools/<id>`，避免把已本地发布的项目继续挡在入口页。
- Prevention: 后续控制台对 UI 项目的可打开判定，不能只依赖陈旧的 `deploymentStatus`；只要存在可服务的本地构建产物且部署提供方为 `self_hosted`，就应优先放行本地工具路由。
- Validation: `cd /root/codex/release/.codex-system/worktrees/dashboard-ui/task-mo5avwpw-gox7nh && npm install --prefer-offline --include=dev --no-audit --fund=false && npm run build`
- Commit ID: pending
- Context: project=一个关于a股的当前数据和投资建议看板, step=tool-entry remediation

## 2026-04-21

- Problem: 运行时配置页先展示了 `AKShare` 的“待配置”入口，但后端并没有真实适配器，导致用户误以为只差前端配置；在自托管模式下，这类“前端先行”会掩盖服务端未接通的真实缺陷。
- Resolution: `AKShare` 已接入后端主数据解析链，`stock_master` 现在会在无 `Tushare` token 时按真实适配器查询 `stock_individual_info_em` 解析股票简称、行业和上市时间；运行态状态也改为按后端适配器真实可用性展示，而不是把未接入能力伪装成“待配置”。
- Prevention: 以后任何数据源、模型、配置面板或服务开关，只有在后端适配器、验证链路和发布路径都已落地后，前端才能展示入口或状态；若后端尚未接通，UI 必须明确标记为未接入，不能把缺失实现包装成用户可配置项。
- Commit ID: pending
- Context: project=一个关于a股的当前数据和投资建议看板, step=runtime provider integration discipline

## 2026-04-21

- Problem: 部署环境已经从 GitHub Pages 迁移到自托管服务器，但项目仍保留“在线 API / 离线快照”双模式、浏览器本地自选池和用户侧在线接入配置，这些静态站假设与新的服务端真实数据模式冲突。
- Resolution: 前端收口为统一服务端模式；新增 `app_settings`、`provider_credentials`、`model_api_keys` 三类 SQLite 配置实体；新增 `/settings/runtime`、模型 Key 管理、数据源凭据管理和 `/analysis/follow-up` 分析接口；补齐 `AKShare + Tushare` 统一字段映射摘要、`Redis` 关注池缓存 TTL 和模型 Key 默认/显式选择/故障切换逻辑。
- Prevention: 后续凡是部署形态已经确定为自托管服务器的项目，不再为了静态演示保留离线快照主路径；如果必须保留历史快照工具，也要明确它是非主链路并从 UI 和验收文档中移除。
- Validation: `python3 -m py_compile src/ashare_evidence/models.py src/ashare_evidence/runtime_config.py src/ashare_evidence/llm_service.py src/ashare_evidence/api.py src/ashare_evidence/operations.py src/ashare_evidence/schemas.py tests/test_runtime_config.py`; `cd frontend && npm run build`
- Note: `PYTHONPATH=src python3 -m unittest discover -s tests` 仍无法执行，原因是当前沙箱缺少 `fastapi`、`sqlalchemy` 等依赖且网络受限，无法安装。
- Commit ID: pending
- Context: project=一个关于a股的当前数据和投资建议看板, step=deployment-migration refactor

## 2026-04-21

- Problem: 在自托管工具路由下，前端仍允许历史 `API Base` 覆盖值优先于当前挂载路径，导致页面即使已经从 `/tools/ashare-dashboard` 提供，也可能继续把请求打到过时的 `:8000` 或别的旧地址；与此同时，若控制台没有真正托管后端进程，前端回退再多次也无法修复线上页面。
- Resolution: 前端 API 基址探测现在优先使用当前工具挂载路径推导出的 `/tools/ashare-dashboard/api/*`，把历史本地覆盖值降级为次选；同时由控制台负责在该工具路由后启动并代理真实后端，而不是让页面自己猜测后端位置。
- Prevention: 自托管服务端模式下，项目必须只有一个控制面拥有的规范 API 入口，前端只能把浏览器里的历史覆盖值当调试兜底，不能让它覆盖当前真实部署路径。
- Commit ID: pending

## 2026-04-21

- Problem: 前端 API 探测只命中单一路径时，遇到代理/部署基址偏差会返回 `Tool not found`（被当作致命错误），导致看板持续“面板加载失败”。
- Resolution: 恢复前端 `API Base` 的路径回退策略：对每个候选基址先尝试 `base/api/{path}` 再尝试 `base/{path}`，并在无显式基址时保留当前的 `/api` 回退，以减少“静态路由误伤”导致的线上红屏。
- Prevention: 任何服务端模式前端在无显式基址时，都应保留 `/<api-prefix>` 与 `/<raw>` 的双探测路径；仅在基址明确且稳定后才允许缩减探测。
- Commit ID: pending

## 2026-04-21

- Problem: `404 JSON` 响应（含 `Not Found` / `tool not found`）在仍有备选 API 地址时会被直接抛错，导致基址前缀猜测失败后没有继续尝试下一条请求。
- Resolution: 前端 `request` 改为对 `404` 与可疑“未找到”响应统一走探测回退，并放宽 `HTML` 回退条件，不再仅依赖未显式基址。
- Prevention: API 层只要存在多个候选地址，路由级 404 应按“继续探测”处理；`/api` 与非 `/api` 前缀应同时保留，直到确认后端稳定。
- Commit ID: pending

## 2026-04-21

- Problem: 原来的“运营复盘/手动模拟”只有两个静态组合快照和聚合审计指标，没有真正的模拟会话、共享时间线和控制按钮，用户虽然能看结果，却无法在同一时间节点下把“我怎么做”与“模型怎么做”持续对比，也无法恢复暂停中的进程。
- Resolution: 新增持久化 `simulation_sessions + simulation_events` 状态机，把双轨模拟收口为单个可恢复会话；前端运营页也改成围绕该会话的启动/暂停/单步推进/重启/结束、手动下单、模型建议、K 线和时点差异工作台。
- Prevention: 以后凡是“手动 vs 模型”这类长期模拟需求，不能再只用两个 `paper_portfolios` 拼出结果页；必须先定义会话实体、共享时间线、控制动作和统一事件留痕，再让组合汇总挂在会话之下。
- Validation: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_dashboard_views tests.test_simulation_workspace`; `cd frontend && npm run build`
- Commit ID: pending

## 2026-04-21

- Problem: 用户新增自选股时，未知代码会落入演示用动态场景生成器的随机行业模板，导致真实股票可能被错误展示为 `医药生物` 等无关板块；而且一旦错误板块已写入库，后续修正后旧 `sector_membership` 仍可能继续参与候选页排序与展示。
- Resolution: 自选新增链路现在先走主数据解析层，优先读取本地已知映射并支持按已配置 `Tushare` 凭据调用 `stock_basic` 获取真实 `name / industry / list_date`；拿不到真实行业时改用中性“待确认行业”而不是随机板块；重分析前还会把当前股票上不再属于新结果的旧行业归属标记失效。
- Prevention: 以后任何“用户输入证券代码 -> 自动生成分析”的链路，都不能直接把演示模板当真实主数据；未知标的宁可明确标记“待确认”，也不能随机给出具体行业；同时修正主数据时必须同步处理历史残留归属，避免“新旧行业并存”。
- Commit ID: pending

## 2026-04-21

- Problem: 详情页和运营面板之前沿用了“候选股榜单里的当前 symbol”作为焦点来源；当用户自选变更后，如果新标的不在候选前列或前端还握着一个过期 symbol，模拟仓面板就可能继续盯旧票，甚至因为无效 `sample_symbol` 让 `/dashboard/operations` 降级失败。
- Resolution: 前端当前焦点改为优先从实际自选池续接；后端运营面板对 `sample_symbol` 做了自选池内回退，不再让仅用于体积测量的 symbol 选择影响组合看板主响应。
- Prevention: 以后凡是“自选池 + 候选排序 + 单票详情/运营面板”并存的页面，焦点 symbol 的真相必须来自当前自选池；榜单排序只能影响展示顺序，不能决定状态续接或让无效 symbol 打断主面板。
- Commit ID: pending

## 2026-04-21

- Problem: 运营复盘页把双轨模拟台当成必成功的阻塞依赖；一旦 `/simulation/workspace` 失败，前端会吞掉错误后一直停在骨架屏。同时后端在构建模拟工作区时会按全量 `MarketBar` 重算行情历史，数据量一上来就容易把“看起来卡住”放大成真实超时。
- Resolution: 运营复盘改成“运营概览”和“双轨模拟台”分开加载，任何一侧失败都要在页面内明确提示并允许重试，而不是继续假装加载中；后端行情历史聚合也收窄到当前自选池/会话股票池，并对缺失价格序列做容错。
- Prevention: 以后聚合型工作区不能把次级面板的失败伪装成全页 loading；所有重算链路都要先按当前上下文裁剪数据范围，再考虑展示层拼装。
- Validation: `cd frontend && npm run build`; `python3 -m py_compile src/ashare_evidence/operations.py src/ashare_evidence/simulation.py src/ashare_evidence/api.py`
- Commit ID: pending

## 2026-04-21

- Problem: 运营复盘页首次进入时并发请求 `/dashboard/operations` 和带写入副作用的 `/simulation/workspace`；在 SQLite/低 IOPS 场景下，这种“读面板 + GET 内建档”并发很容易放大成锁等待或超时，最终前端只能看到“双轨模拟台暂时不可用”的假降级。
- Resolution: 运营复盘首屏改为单次工作区请求，由 `/dashboard/operations` 直接内嵌模拟工作区；同时模拟工作区内部复用同一份行情上下文，不再为用户轨道和模型轨道重复扫描一次历史价格。
- Prevention: 以后只要 GET 接口会隐式建档、补状态或写留痕，就不能和同页其他聚合 GET 并发触发；这类首屏工作区要么合并成单个 contract，要么先消除 GET 写入副作用，再谈并发加载。
- Commit ID: pending
