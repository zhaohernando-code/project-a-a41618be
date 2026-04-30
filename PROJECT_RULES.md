# 一个关于a股的当前数据和投资建议看板 Rules

- Follow the global conventions from `~/codex/CODEX.md`.
- Keep the canonical project entry docs aligned: `PROJECT_STATUS.json`, `README.md`, `PROJECT_RULES.md`, `DECISIONS.md`, `PROCESS.md`, and `PROJECT_PLAN.md`.
- Keep the project GitHub-ready and record important changes in `PROCESS.md` with commit IDs.
- Preserve interoperability with other projects under `~/codex`.
- If the project includes a UI, implement it as a TypeScript + React app with a formal framework/toolchain by default.
- The live deployment model is server entrypoint plus local backend/database/tunnel; do not reintroduce GitHub Pages or browser-side backend configuration as the primary path.
- The editable repo under `~/codex/projects/stock_dashboard` is not the live runtime. Public service must run from `~/codex/runtime/projects/ashare-dashboard`, and `.codex.deploy.json` plus LaunchAgent paths must stay aligned with that runtime split.
- When a Codex session changes live-facing code or validates the live frontend, completion requires publishing the repo into the runtime copy with `scripts/publish-local-runtime.sh`, then rechecking the actual remote-facing entry in a browser; a repo-only or runtime-only change is not a finished live fix.
- For this project, every live-facing fix must be treated as incomplete until the remote route has been refreshed and visually rechecked after publish. If that remote verification is blocked, the response must say the fix is not yet finished.
- Live browser acceptance must follow the `README.md` `开发测试必读` flow. A single blank Chrome tab, one failed click, or an unrefreshed authenticated tab is not enough evidence to declare publish failure or success; verification must distinguish runtime health, hydration delay, browser-state false negatives, and canonical-route rendering.
- If the main repo is dirty and `scripts/publish-local-runtime.sh` refuses to run, do not bypass publish and do not patch runtime directly. Create a temporary clean snapshot from the current `HEAD`, publish from that snapshot, then record the snapshot path and browser-verification result in `PROCESS.md`.
- If the canonical verifier cannot complete because credentials are missing, the task is still incomplete until both localhost preview and the authenticated canonical route have been manually rechecked in a real browser and that fallback path has been written into the durable logs.
- Durable research or rollout decisions go to `DECISIONS.md`; reusable lessons or rollback causes go to `PROCESS.md`; current progress and blockers go to `PROJECT_STATUS.json`.
- Active contracts belong in `docs/contracts/`; historical audit and research notes belong in `docs/archive/`.
- 用户访问入口当前是 `https://hernando-zhao.cn/stocks`；底层规范挂载路径仍是 `https://hernando-zhao.cn/projects/ashare-dashboard/`。文档和 UI 文案需要区分这两层，不要把业务别名和运行时挂载写成同一个概念。
- 本项目 UI 风格参考 `VoltAgent/awesome-design-md` 中接近 `Coinbase` 的金融产品规约：强调可信、克制、数据密度与清晰层级；在实现上使用浅色底、蓝绿信号色、强对比标题和证据卡片，而不是通用后台模板。
- 任何数据源、配置入口、状态标签或“待配置/已接入”提示，只有在对应后端适配器、验证链路和真实发布路径都已落地后才能出现在前端；禁止前端先行占位制造“只差用户配置”的假象。
