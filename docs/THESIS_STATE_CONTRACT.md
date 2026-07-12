# Thesis State Contract

## 状态

- `Unobservable`：没有可用事实。
- `Observing`：有真实事实，但历史或口径不足。
- `Trend`：可比序列达到最低覆盖门槛。
- `Inflection Watch`：幅度、持续、广度及对应确认条件同时触发。
- `Confirmed`：更长周期或下一频率的事实确认。

## Supply Price

- Chart：固定配置 panel >=10 个有效日。
- Inflection Watch：至少两个 frontier GPU panel 30D 跌幅 >=10%，且订单簿 >=20 日、深度增长 >=10%。
- Confirmed：至少两个 panel 具备 90D 资格且持续跌幅 >=15%。

## Capacity & Utilization

- Trend：订单簿/容量 >=10 个有效日。
- Inflection Watch：>=20 日且至少两个 GPU family 深度扩大 >=25%。
- Confirmed：>=60 日且市场广度持续满足。

## Demand & Unit Economics

- Trend：完整周 usage series 达标。
- Public frontend proxy 只能到 Trend。
- Inflection Watch：至少一个非 proxy usage inflection series，并有多个真实 token price cut。
- Confirmed：至少两个 official usage series，且商业化变化继续改善。

## Commitment & Monetization

- Observing：单期 CAPEX 或离散事件。
- Trend：至少三家公司有三个连续 CAPEX period。
- Inflection Watch：至少两家公司 guidance 下修。
- Confirmed：至少两家公司后续 actual CAPEX 同向下降。

每个 clock 必须输出 basis、confirm、disconfirm、next proof point、source coverage、metrics、blockers 和 evidence ids。
