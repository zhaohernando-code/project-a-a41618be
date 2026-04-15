# PROCESS

## 2026-04-14

- Project scaffold created.
- Commit ID: pending

## 2026-04-14

- Problem: 免费 A 股数据源在授权、稳定性、字段覆盖和新闻可分发性上差异很大，若不先做基线评估，后续数据底座和建议引擎会反复返工。
- Resolution: 完成了行情、财务、板块、公告、新闻与量化框架的分层评估，明确一期采用 `Tushare Pro + 巨潮资讯 + Qlib` 的低成本主路线，并要求在数据底座内置 `license_tag`、`source_lineage` 和可替换适配层。
- Prevention: 以后涉及金融数据接入时，先确认来源授权、付费模式、升级触发条件和字段级展示边界，再开始表结构与采集实现。
- Commit ID: pending
- Context: project=一个关于a股的当前数据和投资建议看板, step=数据与开源基线评估

## 2026-04-14

- Problem: task task-mnybrlmg-83zgf9 (Create project: 一个关于a股的当前数据和投资建议看板) finished with status failed.
- Resolution: Task failed during recovery: Task was marked failed after prolonged inactivity without a final summary.
- Prevention: Finalization path now records and surfaces publish outcomes to avoid silent drift.
- Commit ID: pending
- Context: project=一个关于a股的当前数据和投资建议看板, source=issue #37

## 2026-04-14

- Problem: task task-mnyilln4-hynas9 (Create project: 一个关于a股的当前数据和投资建议看板) finished with status failed.
- Resolution: Task failed during recovery: Task was marked failed after prolonged inactivity without a final summary.
- Prevention: Finalization path now records and surfaces publish outcomes to avoid silent drift.
- Commit ID: pending
- Context: project=一个关于a股的当前数据和投资建议看板, source=issue #37

## 2026-04-14

- Problem: task task-mnyoe1rd-wgy1zx (数据与开源基线评估) finished with status needs_revision.
- Resolution: Publish skipped because no origin remote is configured.
- Prevention: Finalization path now records and surfaces publish outcomes to avoid silent drift.
- Commit ID: pending
- Context: project=一个关于a股的当前数据和投资建议看板, source=direct

## 2026-04-14

- Problem: project flow research outputs had completed in the step worktree, but the project repository was never provisioned and the successful research result was not synchronized back into the canonical project baseline.
- Resolution: Synced the latest research artifacts back into the project root, created the GitHub repository `zhaohernando-code/project-a-a41618be`, and prepared the project state to continue from the post-research decision gate.
- Prevention: Auto-created repositories now use a stable GitHub-safe ASCII name, trust the repository creation response directly, and internal project steps no longer fail just because no origin was configured.
- Commit ID: pending
- Context: project=一个关于a股的当前数据和投资建议看板, source=local remediation

## 2026-04-14

- Problem: task task-mnypmmip-zl4l2x (数据与开源基线评估) finished with status needs_revision.
- Resolution: Publish skipped because no origin remote is configured.
- Prevention: Finalization path now records and surfaces publish outcomes to avoid silent drift.
- Commit ID: pending
- Context: project=一个关于a股的当前数据和投资建议看板, source=direct

## 2026-04-14

- Problem: task task-mnysioxi-xi1z1c (证据化数据底座) finished with status failed.
- Resolution: Task failed during recovery: Task was marked failed after prolonged inactivity without a final summary.
- Prevention: Finalization path now records and surfaces publish outcomes to avoid silent drift.
- Commit ID: pending
- Context: project=一个关于a股的当前数据和投资建议看板, source=direct

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

- Problem: 当前 worktree 沙箱无法在主仓库 `.git/worktrees/...` 下创建 `index.lock`，导致本轮不能执行 `git add` / `git commit` / `git push`。
- Resolution: 保留已验证的工作树改动并在交付总结中明确说明提交阻塞点。
- Prevention: 后续如果任务要求强制提交，需要先确认当前 worktree 的 `.git` 元数据目录具备写权限，或切换到具备提交权限的仓库环境。
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

- Problem: 本轮已完成代码与验证，但当前 worktree 仍无法创建 `.git/worktrees/.../index.lock`，导致 `git add -A` 直接失败，不能继续执行 commit/push。
- Resolution: 已保留所有已验证改动，并在交付总结中明确说明版本提交阻塞来自当前 worktree 的 git 元数据写权限，而不是代码验证失败。
- Prevention: 后续若任务要求强制提交，需要切换到具备 `.git/worktrees/...` 写权限的仓库环境，或在 canonical repo 中直接执行提交流程。
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
