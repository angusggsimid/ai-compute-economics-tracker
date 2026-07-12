# OCPI Licensed-Unavailable And Public Proxy Policy

## 结论

生产模式下，ORNN/OCPI 不再使用旧的硬编码 `fetch_ocpi_public()`。没有授权 feed 时，只写入质量事件：

- `error_code=DATA_SOURCE_UNAVAILABLE`
- `source_type=licensed_unavailable`
- `collection_method=unavailable_marker`
- `affected_key=ornn_ocpi`

不会向生产表写入 OCPI fallback value，也不会把 `source=composite_public` 当成生产数据。

## 旧函数边界

`GPUCollector.fetch_ocpi_public()` 只保留给 legacy/demo 路径。它返回的 `source=composite_public` 不能用于 production update、production report 或决策层。

## Public Proxy

公开代理序列来自 T3 已写入 `production_gpu_prices` 的 ComputePrices H100/H200 aggregator rows。写入表：

`production_public_proxy_prices`

固定命名：

`proxy_name=public_gpu_price_proxy`

它不能命名为 OCPI，也不能替代 ORNN/OCPI 授权指数。

## Proxy 指标口径

proxy 只从当前生产表里的 ComputePrices aggregator rows 计算透明指标：

- `computeprices_row_count_proxy`
- `computeprices_row_min_price_per_gpu_hour_proxy`
- `computeprices_row_median_price_per_gpu_hour_proxy`

这些指标表示“已采集 aggregator 行”的 row count、min、median。它们不是页面级 `from price`，也不是 market median、official price 或成交价。

每条 proxy row 保留底层 ComputePrices row 的：

- `source_url`
- `snapshot_path`
- `raw_payload_hash`
- `source_id`
- `observed_at`
- `fetched_at`
- `source_type=aggregator`

## CLI 行为

运行：

```bash
python3 tracker_v2.py update --production --only public-proxy-prices
```

结果分两条线显示：

- `OCPI unavailable`
- `public_gpu_price_proxy available` 或 `public_gpu_price_proxy unavailable`

如果没有授权 OCPI feed，会写 `DATA_SOURCE_UNAVAILABLE`。如果没有 ComputePrices H100/H200 production rows，会写 `PUBLIC_PROXY_SOURCE_MISSING`，不插入 proxy fallback value。
