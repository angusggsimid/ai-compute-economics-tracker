# 路线校准 2026-08-23 | 双向拐点 × 外部锚 × 分层数据组合

> 基于五原则体检与外部方案调研（SemiAnalysis、Ornn、Epoch AI、GitHub 开源社区）得出的路线调整。用户已全部采纳。原则本身不变：可比性优先、不混频、可追溯、缺口暴露、服务判断。

## 校准（方向层面）

### C1 拐点判定双向化
现行 `THESIS_STATE_CONTRACT` 只监测"稀缺松动/破裂"单方向（Supply Price 看 panel 跌幅 ≥10%、Commitment 看指引下修）。市场现实是紧缩周期（SemiAnalysis 公开数据：H100 1Y 合约价 2025-10 $1.70 → 2026-03 $2.35，on-demand 多月售罄），产品在最该发声的窗口结构性失明。
调整：每个时钟增加对称的 `Intensification Watch` 条件（例：≥2 个 frontier panel 30D 涨幅 ≥10% 且订单簿深度收缩 ≥10%；Commitment 加 guidance 上修方向），报告同时输出两个方向的证据读数。

### C2 Supply Price 补合约层（tenor 维度）
大多数租赁成交量在长期合约市场，现货挂牌不是主要市场。
调整：接入 SemiAnalysis 公开的 H100 1Y 月度合约价作为事件型 source-backed 数据（标注来源与许可）；现货-合约背离作为独立观察项。

### C3 与商业指数定位切割
不做更好的 OCPI（无成交数据优势）；做它没有的：跨层交叉验证、反证条件、双向拐点状态机。Ornn 免费 API 作为 transaction-based 外部锚交叉验证自采层（来源类型标 `licensed_free_tier`）。

## 补强（执行层面）

### E1 四时钟状态机移植到每日管线（P0）
`thesis_state.py` 目前停在 2026-07-11 DuckDB 时代。移植到 JSON backfills 输入，Actions 每日自动产出 `latest-thesis-state.json/md` 提交进仓库并上页面；时钟审计输出各时钟到门槛的距离。

### E2 价格层可比性修复（P1）
用 Foundry 已存的 `providerPrices` 构建固定供应商面板指数；评估接入 adriannutiu/gpu-rental-prices（CC BY 4.0，22 家供应商 append-only 快照）扩展面板广度。

### E3 外部锚接入（P1/P2）
Ornn 免费 API（5 GPU 日频 3 个月滚动 + OTPI 4 lab）做交叉验证列；Demand 时钟评估 OPENROUTER_API_KEY 突破 proxy 天花板。

## 数据输入分层结论

| 层级 | 来源 | 替代/补充关系 |
|---|---|---|
| T1 | Ornn OCPI 免费层（成交型 GPU 日指数） | 升级 Supply Price 基准，Foundry 中位价降为广度补充 |
| T1 | Ornn OTPI 免费层（已实现 token 价/按 lab） | Demand 单位经济突破 proxy 天花板的首个真实机会 |
| T1 | adriannutiu/gpu-rental-prices | matched-panel 面板广度原料 |
| T2 | SemiAnalysis H100 1Y 合约价（月度公开） | 合约层缺失维度 |
| T2 | Epoch AI Chip Sales / Data Centers | Capacity 时钟供给侧物理部署节奏 |
| T3 | Vercel AI Gateway 用量、npm/PyPI SDK | 需求第二代理与采用广度 |

约束：Ornn 免费层是滚动窗口（GPU 3 个月/lab 1 个月），必须每日快照累积；CC BY 4.0 与免费层许可需署名并在来源表声明。
