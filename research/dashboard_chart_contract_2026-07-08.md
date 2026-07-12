# HTML Dashboard 图表合同 | 2026-07-08

交付物：`tracker_v2/html_dashboard/ai_compute_trend_board.html`

目标：只给投资判断所需的“带时间的价格/成本/用量趋势”和 CAPEX 官方确认层，不做复合打分，不把不同频率混权重。

## 图表清单

| Exhibit | 问题 | 图形 | 数据源 | 数据频率/覆盖 | 验收标准 |
|---|---|---|---|---|---|
| 1 GPU 租赁价格趋势 | GPU 租赁价格是否松动 | 多线趋势图 | `production_market_facts.gpu_rental` | 26 个日期，2026-06-07 至 2026-07-08 | 有标题、轴、图例、来源；日期筛选后重算 |
| 2 GPUMarkets fixing 与 30D 变化 | 当前市场 fixing 是否下行 | 横向点图 | GPUMarkets `fixings.csv` | 1 个 fixing 日期；含 1D/7D/30D delta | 只画 fixing + delta，不伪装完整历史趋势 |
| 3 可用订单薄价格与深度 | 低价是否有深度 | 分 source 气泡图 | GPUPerHour available offers、Vast bundles、RunPod gpuTypes | 2 个抓取日；Vast/RunPod 为当前快照 | 气泡大小为 offers/capacity proxy；不称为硬件现货价 |
| 4 官方云 GPU 实例价格 | 官方云 VM-hour 是否同步变化 | 多线趋势/快照图 | Azure Retail Prices API、AWS current Spot JSON | 2 个抓取日 | 不与 GPU-hour 混算；低频时明确是 crawl-day |
| 5 OpenRouter 模型 token 用量 | 应用需求是否增长/转移 | 多线趋势图 | Socialpranker/token-history | archive：2026-06-03 至 2026-06-17，按模型稀疏 | 标注 archive/stale/sparse，不冒充官方实时 API |
| 6 OpenRouter activity proxy | 工具/图像活动是否变化 | 双线趋势图 | OpenRouter frontend rankings | 13 个周频点，2026-04-13 至 2026-07-06 | 标注 proxy，不当成总文本请求 |
| 7 模型输出 token 价格 | 输出价是否下降 | 多线趋势图 | OpenRouter Models、LiteLLM、models.dev、ComputePrices LLM | 10 个日期，2026-06-16 至 2026-07-08 | 单位为 USD/1M output tokens |
| 8 高质量模型输出成本 | 高质量模型成本是否压缩 | 多线趋势/点图 | CostGoat public proxy | 2 个抓取日 | 质量分 >=80；标注不替代 Artificial Analysis |
| 9 多模态生成成本 | 视频/多模态成本是否下降 | 分轴趋势/点图 | BytePlus ModelArk、seedance2.ai | 2 个抓取日 | USD/token 与 credits 分轴，不混算 |
| 10 ARR 与商业化信号 | 应用商业化是否接棒 | 分轴趋势/点图 | ARR.club、Ramp AI Index | ARR 2 个日期；adoption 1 个日期 | ARR 与采用率分轴，采用率不当收入 |
| CAPEX 表 | 云厂商管理层是否仍扩张 | 表格 | SEC/官方披露、中国官方/手工验证源 | 季度/事件型 | 美国 5 家 + 中国厂商口径限制清楚显示 |

## 交互合同

1. 顶部日期范围控件是唯一全局时间筛选，更新后所有图重画。
2. 每张图的 legend 可点击隐藏/恢复 series，坐标轴按可见 series 重新计算。
3. 低频数据被筛掉时显示“该窗口无数据”，这是风险暴露，不是完成信号。
4. HTML 不依赖 Streamlit；所有图由嵌入数据 + 原生 SVG 绘制。

## 浏览器验收

| 检查项 | 结果 |
|---|---|
| 桌面渲染 | 10 张图卡、2 个表、12 个 SVG、0 个默认缺失卡 |
| 390px 移动端 | `scrollWidth=390`、`clientWidth=390`，无横向溢出 |
| 日期筛选 | 日期窗口更新到 `2026-06-23 / 2026-07-08` 后 GPU 租赁图 SVG 重新绘制；被筛掉的数据诚实显示空窗口 |
| 图例隐藏 | 订单薄图隐藏 1 个 source 后 SVG 重新绘制，坐标轴按可见 source 重算 |
| 控制台 | 0 error/warn |

截图：

- `tracker_v2/output/playwright/html_trend_dashboard_20260708_desktop_r2.png`
- `tracker_v2/output/playwright/html_trend_dashboard_20260708_mobile_r2.png`
