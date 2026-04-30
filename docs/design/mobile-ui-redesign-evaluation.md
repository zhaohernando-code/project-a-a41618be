# 股票看板移动端 UI 评估与重构方向

更新日期：2026-04-29

## 现状判断

当前移动端不是“少量样式问题”，而是典型的桌面工作台在手机上的缩放版。页面结构、信息顺序、操作密度、表格使用方式都继承了桌面思路，只在个别区域做了 `isMobile` 分支和 media query 收缩，因此手机体验天然会变成长页面、重卡片、横向表格和多层跳转。

本轮在 `390 x 844` 视口下复核到的页面高度：

- 候选与自选：`4620px`
- 单票分析：`8231px`
- 运营复盘：`6722px`
- 设置：`3356px`

这说明问题不是某个局部组件，而是四个主视图整体都超出手机单次会话的合理信息量。

## 关键问题

### 1. 信息架构仍然是桌面工作区

- 顶部 hero、数据源标签、全局切股、刷新、主题切换、四个导航卡长期占据首屏。[App.tsx](/Users/hernando_zhao/codex/projects/stock_dashboard/frontend/src/App.tsx:1581)
- 手机端导航仍然是“四张说明卡”，而不是底部 tab / 分段导航 / 手势化的 app 壳。[styles.css](/Users/hernando_zhao/codex/projects/stock_dashboard/frontend/src/styles.css:202)

### 2. 移动端只对候选列表做了局部适配

- `isMobile` 仅明显切换了候选列表展示形态，其他大视图仍沿用桌面信息组织。[App.tsx](/Users/hernando_zhao/codex/projects/stock_dashboard/frontend/src/App.tsx:112)
- 单票分析与运营复盘没有移动端专属的信息裁剪和流程重排，只是堆叠下去。[App.tsx](/Users/hernando_zhao/codex/projects/stock_dashboard/frontend/src/App.tsx:1854)

### 3. 卡片过长，单卡承担了过多职责

- 候选卡同时承担“排名、状态、指标、摘要、验证、操作”，每张卡都接近一个小页面。[App.tsx](/Users/hernando_zhao/codex/projects/stock_dashboard/frontend/src/App.tsx:1729)
- 单票页把行情、建议、验证、人工研究、事件、术语都放在一个连续滚动文档里。[App.tsx](/Users/hernando_zhao/codex/projects/stock_dashboard/frontend/src/App.tsx:1991)

### 4. 运营复盘仍依赖宽表格

- 持仓表明确保留横向滚动，并把表格最小宽度锁到 `980 / 920 / 860px`，这在手机上必然形成“看不全 + 需要左右拖”的交互。[styles.css](/Users/hernando_zhao/codex/projects/stock_dashboard/frontend/src/styles.css:882)
- 这类数据更适合改成“持仓摘要卡 + 详情抽屉 + 横向指标条”，而不是直接把桌面表压进手机。

### 5. 断点是在“缩”，不是在“重构”

- 当前 media query 主要是把列数从 4 改成 2 或 1，把高度和 padding 缩小，并没有改变页面的任务流和主次关系。[styles.css](/Users/hernando_zhao/codex/projects/stock_dashboard/frontend/src/styles.css:945)
- 这是“响应式修补”，不是“移动端产品设计”。

## 建议的方向

结论：移动端应该脱离当前桌面工作台结构，单独做一套 app 化布局，不再被 PC 页面框架约束。

建议改成四个一级入口：

1. 首页：焦点标的、今日变化、候选列表
2. 自选：可搜索、可排序、可批量查看
3. 单票：价格、建议、证据、风险、追问
4. 复盘：组合状态、轨道对比、持仓与操作

## 移动端专用设计原则

### 1. 先保留“决策动作”，再保留“解释文本”

- 首屏优先展示：当前该看什么、该做什么、风险在哪。
- 长段说明、完整验证口径、研究材料都放进二级页或底部抽屉。

### 2. 一个屏只做一件事

- 首页负责“发现”
- 单票页负责“判断”
- 复盘页负责“执行与复核”
- 设置页负责“配置”

### 3. 表格退后，卡片与抽屉前置

- 手机端默认不展示多列表格。
- 表格只在“查看更多”或横屏模式下保留。

### 4. 顶部信息减量，底部导航常驻

- 去掉当前大 hero 和四张导航说明卡。
- 改成 app bar + bottom tab bar。

### 5. 单票页改成“短摘要 + 分段详情”

- 顶部是价格、结论、置信、风险一句话。
- 中间只保留 1 张主图。
- 下方用 segmented tabs 切到“建议 / 证据 / 风险 / 追问”。

## 本轮设计稿

已补一张四屏概念稿：

- 文件：[mobile-ui-redesign-concepts.svg](/Users/hernando_zhao/codex/projects/stock_dashboard/docs/design/mobile-ui-redesign-concepts.svg)
- 内容：首页、候选、自选单票、运营复盘四个手机屏

## 推荐实施顺序

1. 先抽离移动端 app shell：`top bar + bottom tabs + safe-area`
2. 重做首页与单票页
3. 重做运营复盘的持仓与动作流
4. 最后再考虑桌面与移动端共用哪些业务组件

## 不建议继续的方向

- 不建议继续在当前页面上加更多 breakpoint 修补
- 不建议继续把桌面表格压缩到手机
- 不建议把所有解释信息都留在首屏
- 不建议维持当前“全局切股 + 多工作区同页切换”的桌面式 mental model
