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
