# 时钟月度审计 | 2026-09

> 每次刷新覆盖更新当月文件；历史轨迹见 history/ 目录。

## Supply Price — Confirmed（intensifying）
- 下一个证明点：订单簿深度已积累 30/20 有效日；面板 30D 变化每日更新。
- 关键指标：`{"chartReadyPanels": 8, "looseningConfirmedFamilies": [], "intensifyingConfirmedFamilies": ["B200", "H100", "H200"]}`
- 阻塞项：无

## Capacity & Utilization — Trend
- 下一个证明点：积累订单簿至 10/20 有效日（当前 30）。
- 关键指标：`{"depthValidDates": 30, "latestTotalOffers": 364, "depthGrowthPct": 21.2, "latestGpuCapacity": 10275, "providerSnapshotRows": 10155, "providersCovered": 34}`
- 阻塞项：无

## Demand & Unit Economics — Trend
- 下一个证明点：获取官方 usage 授权或接入新的非 proxy 用量源；OTPI 继续按日累积。
- 关键指标：`{"completeWeeks": 52, "latestWeeklyTokens": 126763022044183.0, "weightedOutputPriceChange8wPct": -45.86, "recentPriceCutModels": 97, "otpiLabsCovered": 4, "otpiLatestDate": "2026-09-18"}`
- 阻塞项：['proxy_ceiling_requires_official_usage_for_inflection']

## Commitment & Monetization — Inflection Watch（intensifying）
- 下一个证明点：下一财报季追加季度行；合约区间每半年更新。
- 关键指标：`{"companiesCovered": 5, "companiesWith3ConsecutiveQuarters": 2, "guidanceRevisedUp": ["Alphabet", "Meta"], "guidanceRevisedDown": [], "h100ContractDirectionSinceStart": "falling", "h100ContractFirstMidpoint": 3.05, "h100ContractLatestMidpoint": 2.8}`
- 阻塞项：['companies_with_3_consecutive_quarters_2_of_3']
