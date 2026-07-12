# GitHub 数据源审计 | 2026-07-08

本审计只回答一个问题：哪些 GitHub 项目能为 `AI compute tracker` 提供真实可调用的数据接口，支撑 GPU 价格、租赁、云实例价格、OpenRouter token/调用量、模型 token 价格和 CAPEX 确认层。

## 结论

| 排名 | 项目 | Stars | 可用数据 | 频率 | 鉴权 | 本项目处理 |
|---:|---|---:|---|---|---|---|
| 1 | [BerriAI/litellm](https://github.com/BerriAI/litellm) | 52,967 | `model_prices_and_context_window.json`，模型 input/output/cache token 单价、context window、provider | 当前 catalog；趋势需本地快照 | 无 | 已接入 `token_price`，趋势来自本地多日快照 |
| 2 | [infracost/infracost](https://github.com/infracost/infracost) | 12,397 | AWS/Azure/GCP 资源价格查询逻辑、VM/spot resource mapping | 当前价格；历史需快照 | 通常需要 Infracost API key | 作为云实例价格体系参考；生产已用 Azure Retail Prices + AWS current Spot 直连 |
| 3 | [runpod/runpod-python](https://github.com/runpod/runpod-python) | 302 | RunPod `gpuTypes` GraphQL：GPU 型号、memory、secure/community/spot/reserved price、lowestPrice | 当前快照；历史需本地快照 | 公开 `gpuTypes` 当前可免 key 读取；账号操作需 key | 已接入 `runpod_gpu_price_snapshot` |
| 4 | [vast-ai/vast-sdk](https://github.com/vast-ai/vast-sdk) | 23 | Vast bundles search：GPU、RAM、地区/机器、`dph_total`、`min_bid`、`dlperf`、可租赁状态 | 实时订单簿；历史需本地快照；host metrics history 需 host key | bundles search 当前可免 key 读取；host metrics/API 操作需 key | 已接入 `vast_offer_snapshot`；历史 metrics 缺口继续暴露 |
| 5 | [Socialpranker/token-history](https://github.com/Socialpranker/token-history) | 0 | OpenRouter 模型 token 日度 archive、趋势摘要、app fixture | 日度 archive；最新到 2026-06-17 | 无 | HTML dashboard 已作为 `OpenRouter archive` 图接入，但标注 stale/sparse |

辅助项目：[OpenRouterTeam/ai-sdk-provider](https://github.com/OpenRouterTeam/ai-sdk-provider) 可记录“自己的 OpenRouter 调用成本/usage”，但不是市场级数据源，不列入前五核心源。

## 字段与接口

| 项目 | 关键接口/文件 | 可取字段 | 适合图表 | 失败暴露 |
|---|---|---|---|---|
| LiteLLM | `model_prices_and_context_window.json` | `input_cost_per_token`、`output_cost_per_token`、`cache_read_input_token_cost`、`litellm_provider`、`max_input_tokens` | Token 输出价趋势、模型成本曲线 | GitHub raw 拉取失败或 schema 变更写 quality event；不沿用旧 catalog 假装最新 |
| Infracost | `internal/apiclient/pricing.go`、`internal/prices/prices.go`、cloud resource files | cloud/vendor、instance/SKU、price filters、usage price | 官方云 GPU 实例价格体系、价格归一化参考 | 无 API key 时不调用 Infracost Cloud；改用官方 Azure/AWS 直连并标注 |
| RunPod | GraphQL `gpuTypes` | `displayName`、`memoryInGb`、`securePrice`、`communityPrice`、`secureSpotPrice`、`communitySpotPrice`、`lowestPrice`、`maxGpuCount` | RunPod GPU 租赁价格、spot/reserved 分层、capacity proxy | GraphQL 失败写 quality event；账号/Pod 管理操作不进入本 tracker |
| Vast SDK | bundles endpoint `/api/v0/bundles/` | `gpu_name`、`num_gpus`、`gpu_ram`、`dph_total`、`min_bid`、`dlperf`、`verified/rentable` | GPU 实时订单簿、价格/性能、可用深度 | bundles 失败写 quality event；host metrics history 仍按 `AUTH_REQUIRED` 暴露 |
| token-history | `data/models/daily/*.json`、`data/models/trends.json` | model slug、daily token count、days covered、last date | OpenRouter 模型 token 用量趋势 | 最新 archive stale 或按模型覆盖稀疏时，在图表 caption 标明 |

## 本轮测试样本

| 数据源 | 测试结果 |
|---|---|
| GitHub metadata API | 6 个候选项目 live metadata 成功；保存到 `research/github_repo_metadata_live_2026-07-08.json` |
| token-history daily archive | 成功读取 12 个 daily JSON；`first_date=2026-06-03`、`last_date=2026-06-17`、`max_model_days=3` |
| Production DuckDB | `production_market_facts=18,135`、`production_data_quality_events=125` |
| GPUMarkets fixings CSV | 成功读取 `gpu_market_fixing`；dashboard extract 10 行、1 个 fixing 日期；当前用于 fixing + 1D/7D/30D delta，不包装成完整历史 |
| Vast bundles API | 成功写入 `vast_offer_snapshot`；dashboard extract 与 GPUPerHour/RunPod 合并为 33 行订单簿样本 |
| RunPod gpuTypes GraphQL | 成功写入 `runpod_gpu_price_snapshot`；包含 secure/community/spot price 与 capacity proxy |
| OpenRouter 官方 rankings API | 当前缺 `OPENROUTER_API_KEY`，`model_total_tokens` 和 app rankings 不写入生产表 |

## 不能假装完成的缺口

| 缺口 | 原因 | 应对 |
|---|---|---|
| OpenRouter 官方 daily token/app ranking | 需要 `OPENROUTER_API_KEY` | 当前只用 token-history archive + public frontend proxy；图上明确标注 |
| Vast.ai host market metrics history | host metrics 需要 host API key | 已接入公开 bundles 当前订单簿；P10/median/P90 历史仍不插估算 |
| RunPod 账号/Pod 管理数据 | 需要账号 API key，且不是市场级价格源 | 已接入公开 `gpuTypes` 当前价格；账号数据不纳入 production |
| Infracost/GCP 深度云价格 | API/key 或账号路径未配置 | 官方 Azure/AWS 已直连；GCP 和 Infracost 不用估算补齐 |
| 硬件现货成交价 | GitHub 项目无法直接提供可靠 sold transaction | 仍需 eBay sold listings、渠道报价或授权指数 |
