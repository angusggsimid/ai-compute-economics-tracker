# 贡献指南

## 数据纪律（必须遵守）

1. **可比性优先**：新序列必须有稳定 series_id 与门槛（日频 10 日画线 / 20 日拐点 / 60 日 90D 判断），横截面不得连线
2. **不混频**：季度数据不插值成日线；不同频率不合权重
3. **可追溯**：每个数字保留来源 URL 与 SHA256；无引用的数据点不发布
4. **缺口暴露**：抓取失败记录为 quality 事件，禁止估算填补
5. **双向判定**：拐点规则必须同时定义松动与紧缩方向及反证条件

## 流程

1. Fork → 分支 → 改动
2. `python3 -m pytest test_suite/test_time_series_dashboard.py test_suite/test_deploy_refresh.py` 必须全绿
3. 涉及页面的改动需通过 `python3 scripts/browser_smoke.py`
4. 提交信息用英文祈使句（`feat:` / `fix:` / `docs:` / `ci:`）
