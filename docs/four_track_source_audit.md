# Four-track Source Audit

更新时间：2026-07-08

## 已接入生产源

| 轨道 | 数据源 | 采集方式 | 生产表 | 当前样本 | 用途 |
|---|---|---|---|---:|---|
| GPU 租赁/spot | ComputePrices GPU API | JSON API + raw snapshot | `production_market_facts` | 284 | H100/H200/B200/B300/A100/MI300X 等 GPU 租赁价格横截面 |
| 当前可用 GPU 订单簿 | GPUPerHour Offers API | OpenAPI JSON API + raw snapshot | `production_market_facts` | 181 | 9 个重点 GPU 的 available=true 当前可用 offer、provider、region、GPU count、security tier、host specs |
| GPU 租赁趋势 | ComputePrices GPU Trend API | JSON API + raw snapshot | `production_market_facts` | 24 | H100/H200/B200 public tier 7 日平均价格趋势 |
| GPU 30/90 日 movers | GPUs.io Trends | Browser-rendered text + raw snapshot | `production_market_facts` | 90 | 18 个 material movers 的当前中位价、30d delta、90d delta 和 90d range |
| GPU 聚合价格指数 | AIMultiple GPU Index | HTML text parse + raw snapshot | `production_market_facts` | 23 | H100/H200/B200/B300/A100/L40S/RTX/MI300X 的 median/range/provider count 指数读数 |
| GPU 聚合价格指数 | GetDeploying GPU pages | Embedded JSON-LD parse + raw snapshot | `production_market_facts` | 27 | 9 个重点 GPU 页面级 aggregate low/high/offer count |
| 官方云实例价格 | Azure Retail Prices API | JSON API + raw snapshot | `production_market_facts` | 220 | Azure GPU VM on-demand/spot/low-priority VM-hour 价格 |
| 官方云实例价格 | AWS EC2 current Spot JSON | JSON API + raw snapshot | `production_market_facts` | 42 | AWS GPU instance current Linux spot VM-hour 价格 |
| Token/API 价格 | ComputePrices LLM API | JSON API + raw snapshot | `production_market_facts` | 1,399 中的一部分 | 模型 input/output/cached input 每 1M tokens 价格 |
| Token/API 价格 | OpenRouter Models API | JSON API + raw snapshot | `production_market_facts` | 1,399 中的一部分 | 路由市场模型价格横截面 |
| Token/API 价格 | LiteLLM model_prices JSON | JSON API + raw snapshot | `production_market_facts` | 4,067 | 社区维护模型 input/output/cached input 每 1M tokens 价格 |
| Token/API 价格 | models.dev API | JSON API + raw snapshot | `production_market_facts` | 7,522 | 多 provider 模型价格 catalog，按 focused model/provider 过滤 |
| 模型质量/价效比 | CostGoat LLM API comparison | Next.js `__NEXT_DATA__` parse + raw snapshot | `production_market_facts` | 820 | 205 个模型的质量分、输入价、输出价和 value score |
| AI 应用 ARR | ARR.club public homepage | HTML parse + raw snapshot | `production_market_facts` | 11 | 免费公开榜单上的 ARR 公开信号 |
| AI 应用企业采用率 | Ramp AI Index public article | HTML fetch + expected-value verification + raw snapshot | `production_market_facts` | 3 | Anthropic/OpenAI/overall AI 企业卡与 invoice 支付采用率 |
| 多模态生成成本 | BytePlus ModelArk pricing | Embedded JSON parse + raw snapshot | `production_market_facts` | 6 | Dreamina Seedance 2.0 官方 USD/1M tokens 单价 |
| 多模态生成成本 | seedance2.ai public pricing | HTML parse + raw snapshot | `production_market_facts` | 32 | Seedance 2.0 / Fast / Mini 第三方 credits/sec 与 5s example credits |
| GPU public proxy | ComputePrices public proxy | HTML/API-derived proxy | `production_public_proxy_prices` | 84 | H100/H200 proxy 历史，只有 `quote_count >= 3` 日期进趋势 |
| CAPEX actual | SEC companyfacts | Official API + raw snapshot | `production_capex_actuals` | 5 | MSFT/AMZN/GOOGL/META/ORCL CAPEX actual |
| 官方 CAPEX/RPO/需求事件 | SEC exhibits + Microsoft IR | Official HTML/text re-fetch + proof excerpt | `production_official_events` | 9 | MSFT/AMZN/GOOGL/META/ORCL 的 source-backed guidance/RPO/AI capex/需求证据 |

## 当前可用判断

| 判断问题 | 当前状态 | 原因 |
|---|---|---|
| GPU 租赁价格是否可横截面监控 | 可用 | 有 284 条真实 source-backed 样本，含 spot/on-demand/reserved |
| 当前可用 GPU 订单簿是否可观察 | 可用 | GPUPerHour OpenAPI 已接入 181 条 available=true offer；H100/H200/B200 样本深度分别为 48/20/15 个可用 offer |
| GPU 租赁价格是否可判断短期方向 | 早期可用 | ComputePrices public tier 返回 8 个日期；H100 +7.6%、H200 +14.4%、B200 +28.7%，不支持“短期单边下行” |
| GPU 租赁价格是否可观察 30/90 日方向 | 早期可用 | GPUs.io 30/90 日 movers 已接入；A100 80GB 90d -36.9%，但 H200 90d +8.1%、B200 90d +7.1%，说明代际分化 |
| GPU 聚合价格指数是否可观察 | 早期可用 | AIMultiple 与 GetDeploying 已接入 `gpu_rental_index`，但它们是指数/页面级聚合源，不混入可成交/可租赁报价曲线 |
| 官方云 spot/实例价格是否可横截面监控 | 早期可用 | Azure/AWS 已有 262 条官方/准官方公开样本；价格是 VM-hour，不与 per-GPU-hour 混算 |
| GPU 价格是否可判断趋势拐点 | 早期可观察，不足以定论 | 公开 proxy 有 17 个 quote-date，其中 3 个日期达到样本门槛；官方价格页快照仍太少 |
| Token/API 价格是否可横截面监控 | 可用 | 有 OpenRouter、LiteLLM、models.dev、ComputePrices 公开源；不同 catalog 保留 source_name 和 source_url |
| Token/API 价格是否可判断趋势拐点 | 早期可观察 | 当前已有 2026-06-10 至 2026-07-08 的离散公开 catalog 快照，但仍需继续沉淀定时采集历史 |
| 模型 API 是否可做质量调整后的价效比横截面 | 早期可用 | CostGoat 公开页给出 205 个模型的质量分、input/output 价和 value score；可用于横截面筛选，但不能替代 Artificial Analysis 授权 benchmark |
| AI 应用 ARR 是否可做完整历史 | 不可用 | 免费公开页不是完整私企财务数据库，缺 source links 和历史 |
| AI 应用企业采用是否可横截面观察 | 早期可用 | Ramp AI Index public article 给出 Anthropic/OpenAI/overall 企业付费采用率，但不是收入、ARR 或用户份额 |
| 多模态生成成本是否可横截面观察 | 早期可用 | BytePlus 官方 token 单价和 seedance2.ai credits 表已接入，但 USD/token 与 credits 不能混算 |
| 官方 CAPEX/RPO 层是否支持 capex 下修 | 不支持 | 官方事件覆盖 5/5 hyperscalers：META capex 上修、GOOGL backlog、ORCL RPO、AMZN AI capex、MSFT demand>supply 仍偏扩张 |
| 是否能输出“算力稀缺溢价破裂” | 不可输出 | `quality_gate=WARN`，价格层有代际分化，但官方 CAPEX/RPO 层仍偏扩张；ORNN/GCP/AWS history/ARR 深源仍有缺口 |

## 真实样本摘要

| 样本 | 数值 |
|---|---:|
| H100 spot median | `$2.14/hr` |
| GPUPerHour H100 available min / offers | `$1.07/GPU hr / 48 offers` |
| GPUPerHour H200 available min / offers | `$2.45/GPU hr / 20 offers` |
| GPUPerHour B200 available min / offers | `$3.95/GPU hr / 15 offers` |
| GPUPerHour B300 available min / offers | `$7.39/GPU hr / 2 offers` |
| H100 ComputePrices public trend | `+7.6%` |
| H200 ComputePrices public trend | `+14.4%` |
| B200 ComputePrices public trend | `+28.7%` |
| GPUs.io A100 80GB 30d / 90d | `+5.6% / -36.9%` |
| GPUs.io H200 30d / 90d | `+6.5% / +8.1%` |
| GPUs.io B200 30d / 90d | `-0.2% / +7.1%` |
| GPUs.io Tesla V100 30d / 90d | `+42.9% / -41.7%` |
| AIMultiple H100 median / provider count | `$2.99/GPU hr / 46 providers` |
| AIMultiple H200 median / range | `$4.00/GPU hr / $2.30-$13.78` |
| AIMultiple B200 median / range | `$6.11/GPU hr / $3.44-$16.11` |
| AIMultiple B300 median / range | `$7.92/GPU hr / $5.44-$18.00` |
| H200 spot median | `$2.77/hr` |
| B200 on-demand median | `$5.10/hr` |
| Azure H100 spot min | `$1.42/VM hr` |
| AWS H100 current spot min | `$2.53/VM hr` |
| META FY2026 capex guidance | `$125-145B` vs prior `$115-135B` |
| GOOGL Cloud backlog | `>$460B` |
| ORCL RPO | `$638B` |
| AMZN TTM PPE increase tied to AI | `$59.3B` |
| MSFT demand indicator | `customer demand exceeds supply` |
| OpenAI output median | `$7.50/1M tokens` |
| CostGoat high-quality value leader | `xiaomi/mimo-v2.5 quality 81 / output $0.28/1M / value 289.3` |
| CostGoat high-quality value runner-up | `minimax/minimax-m2.7 quality 82 / output $0.72/1M / value 113.9` |
| CostGoat flagship quality leader | `openai/gpt-5.5 quality 100 / output $30.00/1M / value 3.3` |
| Anthropic ARR.club public signal | `$47B ARR` |
| OpenAI ARR.club public signal | `$25B ARR` |
| Ramp Anthropic business adoption | `34.4%` |
| Ramp OpenAI business adoption | `32.3%` |
| Ramp overall AI adoption | `50.6%` |
| BytePlus Seedance 1080p no-video input | `$7.70/1M tokens` |
| BytePlus Seedance 4K with-video input | `$2.40/1M tokens` |
| seedance2.ai Seedance 2.0 720p 5s no-video example | `60 credits` |
| seedance2.ai Seedance 2.0 Mini 480p 5s with-video example | `16 credits` |

## 未接入或需授权源

| 缺口 | 失败暴露方式 | 下一步 |
|---|---|---|
| AWS 90 天 spot history | `AUTH_REQUIRED` | Current Spot JSON 已接入；90 天 history 需要签名 AWS API/CLI |
| GCP 官方 spot 价格 | `AUTH_REQUIRED` | GCP Cloud Billing Pricing API 需要 API key；未配置前不插入生产值 |
| Vast.ai host market metrics history | `AUTH_REQUIRED` | Vast bundles 当前订单薄已接入 `vast_offer_snapshot`；host-level P10/median/P90 历史 metrics 仍需要 host API key，未配置前不插入历史值 |
| OCI 动态 spot | `SOURCE_NOT_NORMALIZED` | OCI 公开价更接近 list price / preemptible 规则，不是 AWS/Azure 这种动态 spot quote |
| 硬件现货 GPU 价格 | 暂未插入生产值 | GPUPerHour 已补可用租赁订单簿，但不是硬件买卖成交；后续接 eBay sold listings、渠道报价或二手成交源，必须区分 ask 与成交 |
| ORNN/OCPI H100 指数 | `DATA_SOURCE_UNAVAILABLE` | 配置授权源后接入，不用 ComputePrices 冒充 |
| ARR.club Pro | `AUTH_REQUIRED` | 若有账号/API 再接完整历史和 source links |
| Sacra private company financials | `AUTH_REQUIRED` | 若有订阅再接入，不做无来源估算 |
| Artificial Analysis API | `AUTH_REQUIRED` | 若有 API key 再接官方 benchmark；CostGoat 只是公开 proxy，不冒充授权源 |
| SemiAnalysis GPU Pricing Index | `AUTH_REQUIRED` | 若有订阅再接入合同价/指数 |

## 最新运行暴露

2026-07-06 live update 时官方事件层已改用可重新抓取的 SEC exhibit / filing text 路径并补入 Amazon，`production_official_events=9`，`OFFICIAL_EVENT_MISSING` 已消失。GPUPerHour 当前可用订单簿正常写入，当前 `production_market_facts=3,118`，其中 `gpu_available_offer=181`、`model_value_score=820`。旧 403 质量事件保留在审计表，但质量门会在同一家公司已有更新 source-backed 事件时抑制这些过期失败。ComputePrices Trend/LLM API 仍返回 `429 Too Many Requests`，影响 `gpu_rental_trend_h200/b200`、`token_price` 本轮刷新。ORNN/OCPI 仍无授权源，Artificial Analysis API 仍需要账号/API key。

## 产品口径

四轨数据不合成为一个总分。页面只做三件事：

1. 展示每条轨道自己的价格、样本数、来源和缺口。
2. 当样本不足时暴露低样本或授权缺口，不补假数据。
3. 未来本地快照积累到足够历史后，再增加趋势拐点检测。
