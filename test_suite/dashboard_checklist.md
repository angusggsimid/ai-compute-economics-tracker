# Dashboard 验证 Checklist

## 验证环境

- 入口：`AI_COMPUTE_TRACKER_DB=ai_compute_tracker_production.db streamlit run dashboard_v2.py`
- 数据库：`/Users/agg/Documents/New project 2/tracker_v2/ai_compute_tracker_production.db`
- 核心原则：第一屏先显示数据质量和判断状态；图表只能作为证据展示，不能替代判断。

## 1. 第一屏

| 检查项 | 期望结果 | 状态 |
|---|---|---|
| 当前判断 | 显示 `No Signal` 或 `Blocked`，不显示旧 CSI regime | 通过 |
| 数据质量门 | 显示 `PASS` / `WARN` / `FAIL` | 通过 |
| 判断置信度 | 显示来自 `DecisionEngine` 的 confidence；质量失败时显示 `n/a` | 通过 |
| 价格历史 | 第一屏只显示 `production_public_proxy_prices` 的 ComputePrices proxy history；低样本日期不连线 | 通过 |
| 官方价格页快照 | RunPod/Lambda 单日价格页只作为当前快照，不包装成历史趋势 | 通过 |
| 生产数据行数 | 汇总 `production_*` 行数，不包含 legacy/demo 表 | 通过 |
| 数据覆盖表 | 放入展开区，不再占据第一屏主体 | 通过 |
| 缺口与失败源 | 首屏压缩显示关键缺口，完整明细可展开 | 通过 |

## 2. GPU Price Evidence

| 检查项 | 期望结果 | 状态 |
|---|---|---|
| 公共报价页 | RunPod / Lambda 用 `source_type=public_pricing_page` 单独展示 | 通过 |
| 聚合报价 | ComputePrices 用 `source_type=aggregator` 单独展示 | 通过 |
| 历史趋势 | GPU tab 复用 public proxy history，不再从 raw quote 行聚合伪趋势 | 通过 |
| 重复样本 | 图表层折叠重复 raw quote；未折叠明细只放审计区 | 通过 |
| 来源追溯 | 每行包含 `source_url` 和 `snapshot_path` | 通过 |
| 不混合口径 | 公共报价页和聚合报价不合成一个伪官方指标 | 通过 |

## 3. SEC CAPEX Actuals

| 检查项 | 期望结果 | 状态 |
|---|---|---|
| 官方来源 | 只展示 `production_capex_actuals` 的 SEC companyfacts rows | 通过 |
| 公司覆盖 | MSFT、AMZN、GOOGL、META、ORCL 行存在或明确失败 | 通过 |
| 口径清楚 | 显示 `fiscal_period`、`period_end`、`xbrl_tag`、`accession_no`、`unit` | 通过 |

## 4. Official Events And Gaps

| 检查项 | 期望结果 | 状态 |
|---|---|---|
| source-backed events | 只展示已经 source-backed 的 official events | 通过 |
| failed sources | Meta/Alphabet/Oracle 等 403/不可用源以失败事件显示 | 通过 |
| 不伪造 guidance | 缺官方事件时显示缺口，不用手工猜测替代 | 通过 |

## 5. Public Proxy And OCPI Policy

| 检查项 | 期望结果 | 状态 |
|---|---|---|
| OCPI 声明 | 明确说明 ORNN/OCPI 授权源未配置 | 通过 |
| proxy 命名 | ComputePrices 派生指标显示为 public GPU proxy，不叫 OCPI | 通过 |
| 失败暴露 | `DATA_SOURCE_UNAVAILABLE` 在缺口表中可见 | 通过 |

## 6. Legacy/Demo Not Used

| 检查项 | 期望结果 | 状态 |
|---|---|---|
| legacy 表 | 只作为提示表显示，不进入第一屏判断 | 通过 |
| seed-only 库 | 质量门为 `FAIL`，当前判断为 `Blocked` | 已由 `test_dashboard_queries.py` 覆盖 |
| 空生产库 | 质量门为 `FAIL`，当前判断为 `Blocked` | 已由 `test_dashboard_queries.py` 覆盖 |

## 自动化测试

- `python3 -m pytest test_suite/test_dashboard_queries.py -q`
- `python3 -m py_compile dashboard_v2.py`

## 当前验收记录

| 日期 | 结果 |
|---|---|
| 2026-07-05 | 自动化测试通过；真实生产库首屏摘要为 `quality_gate=WARN`、`decision_state=No Signal`、`confidence=15%`。 |
| 2026-07-06 | 首屏新增 H100/H200 历史 GPU 价格趋势；浏览器 smoke 通过并保存 `tracker_data/dashboard_v2_usable_trend_smoke.png`。 |
| 2026-07-06 | 修正上一版误导性趋势：首屏改为 public proxy history + 官方价格页快照；低样本日期暴露但不连线；保存 `tracker_data/dashboard_v2_repaired_decision_smoke.png`。 |
