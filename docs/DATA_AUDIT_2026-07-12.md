# Dashboard 数据审计（2026-07-12）

## 结论

旧页面 10 张图中，只有 OpenRouter Token 总量和 10 日 GPU 聚合价格具备直接、可验证的时间序列含义。其余图表存在截断数据被当作零、样本不足、内部质量指标冒充投资指标或成本口径不可解释的问题，已从正式页面删除。

## 逐图审计

| 原图 | 审计结论 | 处理 |
|---|---|---|
| OpenRouter Token 总量 | 52 个完整周，含公开来源的 `Others` 长尾，可回答需求总量方向 | 保留 |
| 模型厂商可见份额 | 公开 frontend 图只单列少量头部模型，其余进入 `Others`；未单列厂商不能记为 0 | 删除，替换为 Top 3 模型身份更替 |
| Top 1 / Top 3 集中度 | 算术正确，但不能回答由谁获得份额，也不能区分闭源/开源迁移 | 删除 |
| 免费模型可见份额 | 只能计算被单列且带 `:free` 的下限，`Others` 内免费流量未知 | 删除 |
| Tool call / image processing | 是活动次数，不是 Token、收入或成本；缺少经济桥接 | 删除 |
| GPU 可用报价数量 | 只有 4 次本地快照，不足以形成趋势 | 删除主图，继续后台积累 |
| 云实例价格指数 | 4 次重复抓取不是 4 次真实调价；相同值不能证明市场价格稳定 | 删除主图 |
| 使用结构加权 Token 单价 | 公开榜单模型覆盖不完整，且总 Token 未拆 input/output；加权值不可稳定解释 | 删除 |
| 模型价格匹配覆盖率 | 属于数据工程质量指标，不是投资指标 | 删除主图 |

## 2026-07-06 公开榜单样本

| 公开名次 | 模型 | Token | 占公开总量 |
|---|---|---:|---:|
| Top 1 | `tencent/hy3-20260706:free` | 5.12T | 11.0% |
| Top 2 | `xiaomi/mimo-v2.5-20260422` | 4.91T | 10.6% |
| Top 3 | `deepseek/deepseek-v4-flash-20260423` | 4.67T | 10.1% |
| 未逐模型披露 | `Others` | - | 36.4% |

Google、OpenAI、Qwen 当周未被 frontend 图逐项披露；正确状态是“未知并包含在长尾或未单列模型中”，不是 0。

## 长期历史的真实可得性

| 目标 | 可用来源 | 可得范围 | 当前阻塞 |
|---|---|---|---|
| OpenRouter 厂商/模型份额 | `https://openrouter.ai/api/v1/datasets/rankings-daily` | 2025-01-01 起，日度 Top 50 + Other | 需要任意有效 OpenRouter API key |
| GPU 租赁价格 | `https://api.gpus.io/v1/gpus/{key}/price-history` | 1M / 3M / 6M / 12M / ALL | Pro plan + API key |
| AWS Spot | `DescribeSpotPriceHistory` | 最近 90 天 | AWS 凭证；官方不提供一年回看 |
| Azure Retail | `https://prices.azure.com/api/retail/prices` | 当前 retail catalog，带 effective start date | 不是利用率驱动的市场 Spot 历史 |
| GPUMarkets fixing | `https://gpumarkets.dev/data/fixings.csv` | 当前公开 CSV 只有 2026-04-18 一个 fixing date | 不能组成历史曲线 |

## 正式页面现有证据

1. OpenRouter 周度 Token 总量与 4 周均线：52 周。
2. OpenRouter 每周公开 Top 3 模型身份：52 周；缺席不记零。
3. 固定模型 output 牌价：53 周 Git 历史。
4. 固定模型 input 牌价：53 周 Git 历史。
5. H100 / H200 / B200 聚合租赁价格：10 日，仅作为短期代理。
6. 美国与中国云厂商 CAPEX / 官方承诺：按季度或事件原频率列示。

固定模型价格历史来自 LiteLLM `model_prices_and_context_window.json` 的逐周 Git as-of commit。它代表公开目录牌价，不代表模型厂商内部推理成本或实际大客户折扣。
