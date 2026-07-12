# Decision Framework

本框架用于生产决策路径，目标是判断“算力稀缺溢价是否正在消退”。生产判断不再使用混合频率加权 CSI；CSI 只保留在 legacy/demo 路径。

## 分层

| 层级 | 数据 | 频率处理 | 作用 |
|---|---|---|---|
| L1 actual/event | SEC CAPEX actuals、official guidance/RPO/events | 保留季度或事件频率 | 官方确认或反证 |
| L2 commitment | guidance revision、RPO/backlog、CAPEX actual trend | 事件驱动，不日频摊薄成结论 | 判断承诺是否转弱 |
| L3 market proxy | RunPod/Lambda official H100 quote、ComputePrices H100/H200 public proxy | 日频快照只在有可比历史时算趋势 | 早期价格预警 |

## 状态

| 状态 | 含义 |
|---|---|
| No Signal | 数据不足，不能形成方向判断 |
| Watch | GPU 价格层出现松动，但官方 CAPEX/guidance/RPO 未确认，或官方层缺失 |
| Pressure Building | 官方价格和 aggregator breadth 同时转弱，但官方层还没确认破裂 |
| Scarcity Premium Cracking | 市场价格证据和官方 CAPEX/guidance/RPO 负向确认同时出现 |
| Scarcity Still Tight | 价格坚挺，或官方评论/指引/CAPEX 指向供给仍紧 |

## 数值触发

| 触发项 | 生产阈值 | 不足时处理 |
|---|---|---|
| GPU official easing | official H100 comparable median quote 30d 下跌 >=10%，或 90d 下跌 >=20% | 只有单日快照时标记 `GPU_OFFICIAL_TREND_INSUFFICIENT` |
| Aggregator breadth weakening | ComputePrices H100/H200 median 30d 下跌 >=15%，且 current quotes >=8、quote age <14d | 只有当前快照时标记 `AGGREGATOR_TREND_INSUFFICIENT` |
| CAPEX acceleration/deceleration | 每公司至少 4 个 sequential official quarters；再看 QoQ 与 4-quarter trend | 不足 4 期只 display-only，标记 `CAPEX_TREND_DISPLAY_ONLY` |
| Guidance revision | official event layer 中负修订是确认，正修订是反证 | 没有官方事件时不合成 |
| RPO/backlog | 必须有 comparable sequential 或 YoY 官方值 | 单一 RPO 值只 display-only |

## 硬性上限

1. 没有 CAPEX actual 或没有 official events 时，最高状态是 `Watch`。
2. 只有 GPU pricing 层通过时，最高状态是 `Watch`，confidence 不超过 40%。
3. `Scarcity Premium Cracking` 必须同时有市场价格证据和官方 CAPEX/guidance/RPO confirmation。
4. 生产 report 不写 `csi_history`，也不把 CSI 作为主结论。

每个 `DecisionResult` 必须包含 `evidence`、`counter_evidence`、`missing_data`、`quality_gate`、`confidence` 和 `source_references`。
