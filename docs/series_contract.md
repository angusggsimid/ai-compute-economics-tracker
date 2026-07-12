# Comparable Series Contract

## 稳定身份

市场 series 的身份由 `track + source_id + vendor + entity + sub_entity + metric + unit + dimension` 决定。`run_id`、`source_url`、snapshot 路径和抓取时间不进入 `series_id`。

官方 CAPEX/guidance 事件使用公司、指标、单位和事件类型形成稳定身份，披露页面 URL 不改变 series。

## 自然频率

| 类型 | natural_frequency | 展示方式 |
|---|---|---|
| exact-config GPU / cloud price | daily | 达标后可连线 |
| OpenRouter frontend proxy | weekly | 完整周可连线，但不可触发 inflection |
| token list price / ARR / guidance | event | step/event，不用重复快照连线 |
| CAPEX actual | quarterly | event/quarterly bar，不做日频插值 |
| orderbook / fixing / catalog snapshot | snapshot | point/distribution only |

## 资格门

| 资格 | 日频 | 周频 |
|---|---|---|
| chart | >=10 个有效日期，覆盖率 >=80% | >=8 个完整周，覆盖率 >=80% |
| inflection | >=20 个有效日期、跨度 >=24 日 | >=12 个完整周、跨度 >=77 日 |
| 90D | >=60 个有效日期、跨度 >=74 日 | 不适用 |

公开 proxy 即使覆盖达标，也不能取得 inflection/90D 资格。

## GPU Matched Panel

成员必须同时具备 `billing`、`variant`、`region`、`gpu_count`，并保持同一 GPU family、单位和 configuration dimension。Panel 至少 3 个成员、2 个独立 source 才能取得 `eligible_for_market_inference=true`。

当前生产数据没有合格成员：普通报价缺配置字段；ComputePrices 聚合趋势的 provider composition 每日变化。

Phase 3 起，GPUPerHour offer 会按以下完整配置聚合为日度中位价：

`billing + variant + region + gpu_count + security + deployment + provider + GPU family`

同一配置当天的多个 offer 保留 median、min、max、offer count 和原始 offer ids。任何 `variant=unknown`、`region=unknown` 或 `gpu_count=0` 的记录不能获得 matched-series 身份。

## 失败原因码

- `unstable_configuration`
- `missing_exact_configuration`
- `aggregate_composition_not_fixed`
- `insufficient_daily_history`
- `insufficient_weekly_history`
- `insufficient_coverage`
- `event_series_only`
- `snapshot_only`
- `proxy_not_inflection_eligible`
- `insufficient_30d_history`
- `insufficient_90d_history`
