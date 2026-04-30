# stock_dashboard

A 股波段决策看板。源码在 `projects/stock_dashboard`，运行时在 `runtime/projects/ashare-dashboard`。

**技术栈**：Python 3.12 FastAPI + React 18 TypeScript + Vite 4 + Ant Design 6

## 命令

```bash
# 测试
PYTHONPATH=src python3 -m pytest tests/ -v

# 发布（源码 → 运行时）
bash scripts/publish-local-runtime.sh

# 手动刷新
bash scripts/run-scheduled-refresh.sh

# 前端 dev
cd frontend && npm run dev
```

## 已知陷阱

见根级 [KNOWN_TRAPS.md](../../KNOWN_TRAPS.md)，重点关注：
- \#1 Pydantic + future annotations（本项目历史 #1 bug）
- \#2 SQLite WAL 模式
- \#13 JSON `detail` vs `error` key
- \#14 `from __future__ import annotations` 本质
- \#15 大文件拆分前检查循环依赖

## 代码风格

- Python：snake_case，120 列，ruff（E/F/I/N/W/UP 规则）
- TypeScript：strict mode，Ant Design 6，无 ESLint（tsc --noEmit 足够）
- 注释：英文技术注释，中文用户界面文案

## 关键路径

| 文件 | 用途 | 大小 |
|------|------|------|
| `src/ashare_evidence/api.py` | 所有 FastAPI 路由 | - |
| `src/ashare_evidence/schemas/` | Pydantic 模型（7 个域文件） | ⚠️ 循环依赖风险 |
| `src/ashare_evidence/operations.py` | 运营复盘数据聚合 | 1710 行 |
| `frontend/src/App.tsx` | 主应用壳 | 2503 行 |
| `frontend/src/api/core.ts` | API 客户端（URL 重试、错误处理） | - |

## 项目文档

| 文件 | 用途 |
|------|------|
| `PROJECT_STATUS.json` | 当前阶段、阻塞项 |
| `DECISIONS.md` | 耐久决策 |
| `PROCESS.md` | 反回归教训 |
| `PROJECT_RULES.md` | 项目规则 |
