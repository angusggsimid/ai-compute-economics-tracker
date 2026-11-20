# 数据源替代调研 2026-11-20

目标：解决 `gpufinder_market` 的 429（上次成功 `2026-10-31`），给「市场紧张度」三张图找可替换的真实来源。

所有候选都在本机实测过端点（2026-11-20 15:05–15:25 UTC），不是只看文档。

## 结论

1. **GPUFinder 不是坏了，是配额被设计卡死**：免费档 `60` 次/月，我们的轨道预算约 `55` 次/月，任何一次重试或手跑就越界，越界后当月剩余时间全部 429。
2. **没有任何一个免费源能 1:1 顶替**——三张图需要三种数据（在库状态、报价-在库价差、provider 广度），加上月度历史。单一替代要么没有库存字段，要么没有历史。
3. **可行组合（全部 CC BY 4.0 或免费档，$0）**：

| 角色 | 源 | 补哪块 |
|---|---|---|
| 每日主源 | GrabGPU | 在库/缺货状态 + 报价-在库价差 + provider 广度 |
| 超大厂与近期历史 | datacentercensus `gpu-prices.json` | AWS/Azure/GCP/Oracle 等 13 家，含 13 天日度历史 |
| 历史回补 | HF `afhubbard/gpu-prices` | 2026-01-12 → 11-08，231 天日分区，带 `available` 字段 |
| 交叉校验（免鉴权） | RunPod GraphQL、Vast.ai offers | 单点真实报价，做 sanity check |

4. **必须同步改口径**：`availabilityPct` 要从「实例数加权 `Σavailable/Σtotal`」改成「有报价的 provider 中当前有库存的占比」。这不是退让——`Σavailable/Σtotal` 的分母（总容量）本来就没人公开，GPUFinder 给的也只是 provider 上报的挂牌数；改成 provider 口径后反而可解释、可复核。旧序列不能与新序列直接连线。

## 1. GPUFinder 现在提供什么

`scripts/backfill_gpufinder.py` 按四条轨道采，落到 `rows`（每日 × GPU）+ `monthlyHistory`：

| 轨道 | 端点 | 产出字段 | 我们的预算 |
|---|---|---|---:|
| availability | `/availability?gpu=` | `availabilityPct`、`availabilityByProvider`（7 天滚动逐日） | ~21 次/月 |
| snapshot | `/snapshot?gpu=` | `listedAvailableGapPct = cheapestAvailable/cheapestListed - 1` | 30 次/月 |
| history | `/history?gpu=` | `monthlyHistory`（按 provider 的 on-demand/spot 月价） | 3 次/月 |
| catalog | `/gpus` | providerCount / 价格区间 | 1 次/月 |

三张图分别读 `availabilityPct`（稀缺度）、`listedAvailableGapPct`（虚低度）、`_breadth_value()`（广度 = 当日有在架库存的 provider 数）。

失败链：额度耗尽 → `/snapshot` 与 `/availability` 全部 429 → 只保留 `availabilityPct` 的最后一次成功值（`2026-10-31`）→ `listed_gap` 序列因此**一个点都没有**（`time_series_snapshot.json` 里 `listed_gap` 点数 0），等于三张图里有一张一直是空的。这不是本次告警的起因，但属于同一根因。

## 2. 候选源实测

| 源 | 端点 | 鉴权 | 限额 | 许可 | 覆盖 | 库存字段 | 历史 |
|---|---|---|---|---|---|---|---|
| **GrabGPU** | `https://grabgpu.com/api/{offers,gpus,providers,search}.json` | 匿名可用；免费 key 提额 | 匿名 20 次/天 + 50 次 MCP 搜索/天 | 页面声明「Quote it, cite it, build on it」，生产/转售需另议 | 73 型号 × 29 家 × 296 报价 | ✅ `availability: in_stock / out_of_stock / unknown`，分 on-demand/spot/reserved；`providers_in_stock`；`cheapest` vs `cheapest_in_stock` | ❌ 只有当前快照 |
| **datacentercensus** | `https://datacentercensus.com/data/gpu-prices.json` | 无 | 静态文件 | CC BY 4.0 | 168 行 / 13 家（含 AWS、Azure、Google Cloud、Oracle、CoreWeave…） | 部分（`stale` 标记，非实时库存） | ✅ `history` 13 天（10-15→11-19） |
| **HF afhubbard/gpu-prices** | `prices/dt=YYYY-MM-DD/*.parquet` | 无 | 静态 | CC BY 4.0 | 13 家（含三巨头）、70+ 型号、3M+ 观测 | ✅ 每条报价带 `available` 布尔 | ✅ 231 天（01-12→11-08，批次日 2 次），**11-08 后停更** |
| **RunPod GraphQL** | `https://api.runpod.io/graphql` | 无 | 未公开 | 官方价目 | RunPod 单家 | ❌ 无 `stockStatus` 字段（实测报 `Cannot query field`） | ❌ |
| **Vast.ai** | `https://console.vast.ai/api/v0/bundles/` | 无 | 未公开 | 市场报价 | Vast 市场（主机数多） | ✅ `rentable`、`reliability`、`machine_id` | ❌ |
| **Shadeform** | `https://api.shadeform.ai/v1/instances/types?available=true` | 需 key + 充值钱包 | 不按请求计费 | 转售同价、无附加费 | 多云聚合，按 region 给可用性 | ✅ `availability[]` | ❌ |
| **Prime Intellect** | `https://api.primeintellect.ai/api/v1/availability/gpus` | 需 Bearer key | 未标明 | 待核 | 其聚合 provider 的 GPU 可用性 | ✅ availability 列表 | ❌ |
| **Silicon Data / Compute Desk** | `docs.silicondata.com`、`docs.computedesk.com` | 订阅 token | 付费 | 商业授权 | 指数级（H100 日/月、1y 合约） | ❌ | ✅ 2 年 |
| **Ornn** | `https://index.ornn.com/api/...` | 已在用（free reference tier） | — | 已确认 | OCPI/OTPI 指数 | ❌ | ✅ |
| Zenodo / adriannutiu | 已在用的 `neocloud` 价格底表 | 无 | 无 | CC BY 4.0 | 39→43 家、日度 | ❌ | ✅ 上游 git 历史可回补 |

实测要点（2026-11-20）：

- GrabGPU `captured_at = 2026-11-20T15:11:50Z`，`/api/offers.json` 一次请求返回 **296 家/provider-型号报价**（242 KB），覆盖 29 家、73 型号，`in_stock 199 / out_of_stock 50 / unknown 47`。
- 单档取值（GrabGPU `gpus.json` + 明细）：

| GPU | providers | in_stock | 最低挂牌 | 最低在库 | 价差 | median |
|---|---:|---:|---:|---:|---:|---:|
| H100 | 17 | 5 | 1.66 | 1.69 | +1.81% | 2.50 |
| H200 | 9 | 4 | 3.00 | 3.36 | +11.89% | 4.20 |
| B200 | 9 | 4 | 3.74 | 5.00 | +33.69% | 6.34 |

  （`B200` 的 `providers_in_stock=4` 而 in-stock offer 只有 3 条，是因为同一 provider 有多条报价，两者口径不同，落库时要用 provider 去重。）

- **一次请求就够**：只用 `/api/offers.json`（1 次调用）在本地重算，三个指标与官方 `gpus.json` 字段完全一致——`providers`、`in_stock`、`cheapest`、`cheapest_in_stock`、`gap` 全部复现（H100 `17/5`、`1.66`/`1.69`；H200 `9/4`、`3.00`/`3.3567`；B200 `9/4`、`3.74`/`5.00`）。也就是说每天 **1 次请求**即可覆盖全部三个面板，匿名档 `20 次/天` 都绰绰有余。
- 对照 GPUFinder 最后一次成功（2026-10-31）：H100 `availabilityPct 29.72`、H200 `25.09`、B200 `5.18`（实例数加权）。GrabGPU 今日 H100 的 provider 在库占比为 `5/17 = 29.4%`，量级一致，但口径不同，不能拼接成一条线。
- datacentercensus `as_of=2026-11-20`，`prices` 168 行、`history` 13 天；H100 有 26 行、覆盖 `aws/azure/coreweave/crusoe/digitalocean/hyperstack/lambda/lium/nebius/oracle/runpod/together`——**这正是 GrabGPU 缺的超大厂那一块**。
- HF 数据集 `lastModified=2026-11-08`，分区止于 `dt=2026-11-08`，即已停更 12 天：只能当历史回补，不能当日常源。

## 3. 指标级替代矩阵

| 我们的图表字段 | GPUFinder 原口径 | 谁能顶 | 新口径 | 可回补？ |
|---|---|---|---|---|
| `scarcity`（稀缺度） | `Σavailable/Σtotal`（实例数加权） | GrabGPU `providers_in_stock / providers`；HF `available`（历史） | **provider 在库占比**；分母只算「状态已知」的 provider | 2026-01-12→11-08 可从 HF 回补；11-09 起只能当日积累 |
| `listed_gap`（虚低度） | `cheapestAvailable/cheapestListed-1` | GrabGPU `cheapest` vs `cheapest_in_stock`（公式完全一致） | 不变 | ❌ 只能从接入日起积累 |
| `breadth`（广度） | 当日有在架库存的 provider 数 | GrabGPU `providers_in_stock` | 不变 | ❌ |
| `monthlyHistory`（月价） | GPU Finder `/history` | 我们自己的 neocloud 底表（39→43 家，日度）+ datacentercensus 13 天 + HF 231 天 | 用自建日度序列聚合月值 | ✅ |

## 4. 推荐落地（三步，互不阻塞）

1. **主源换 GrabGPU**：新建 `scripts/backfill_grabgpu_market.py`，每天 1 次 `/api/offers.json` + 3 次 `/api/gpus/<slug>.json`（或直接只用 offers.json 全量算，省到 1 次/天），写 `tracker_data/backfills/gpu_market_stock.json`，schema 兼容现有 `rows`（`date/gpu/availabilityPct/listedAvailableGapPct/availabilityByProvider/breadth`），图表代码零改动或最小改动。
2. **保留 GPUFinder 但降频**：只跑 `/availability`，每周 1 次（3 次/月 ≈ 12 次/月），用来守住「实例数加权」这条只有它有的口径；额度从此不再逼近上限，也不会再因为一次重试就整月挂掉。
3. **历史补齐**：一次性从 HF（`available` 字段）+ datacentercensus（13 天）回补 2026-01→11-08 的在库状态，作为「口径变更前的参考序列」，与接入后的新序列分开画、分开标注。

`$0` 成本。GrabGPU 若要把派生指标长期公开发布，按它的页面说明应与其书面确认「生产使用」；当前每天 1–3 次取数在免费档内，且我们只发布派生指标、不转售原始 feed。

## 5. 口径变更声明（必须写进页面和回执）

- `availabilityPct` 旧口径：`Σavailable/Σtotal`（实例数加权，GPUFinder 上报值）。
- 新口径：**在有报价的 provider 中，当前报告有库存的 provider 占比**；分母排除 `unknown`。
- 两者不可直接连线。页面图注需写明「2026-11-21 起为 provider 在库占比；此前为实例数加权，两段仅供参考，不作同口径对比」。黄色警示沿用现有 stale/口径提示组件，不新造 UI。
- `listedAvailableGapPct` 公式不变，可以直接接续。

## 6. 成本与风险

| 项 | 评估 |
|---|---|
| 代码量 | 新采集器 ~150 行 + 适配 3 个字段 + 4 条测试；`build_time_series_dashboard.py` 改动很小 |
| 数据风险 | GrabGPU 是聚合器（按 `source_terms_checklist` 归 `public_proxy`，不能叫官方市场价）；其库存为「provider 最后上报」，与 GPUFinder 同性质 |
| 断供风险 | 单一免费聚合器仍可能变条款。建议主源 GrabGPU + 备份 RunPod/Vast.ai（免鉴权）+ 超大规模厂用 datacentercensus，三层各自独立 |
| 许可 | GrabGPU：引用+链接；datacentercensus / HF：CC BY 4.0（需署名） |
| 时效 | GrabGPU 每小时刷新；我们的日频提交不会滞后超过 1 天 |

## 7. 明确不采用

- **Vast.ai 直接当市场价**：它是 marketplace，低价多为社区/闲置卡，不能代表 neocloud 在售价；只做交叉校验。
- **Shadeform / Prime Intellect 当主源**：需要账号与 key，且要给钱包充值才能建实例（查询虽不按次计费），维护成本高于收益；留作 P2 备选。
- **Silicon Data / Compute Desk**：付费订阅，覆盖的是指数（1y 合约、blended），不是我们的在库状态口径。
- **把 HF 数据集当日常源**：已停更 12 天，只用于历史回补。
