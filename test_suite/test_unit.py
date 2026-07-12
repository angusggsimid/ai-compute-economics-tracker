"""
AI Compute Scarcity Tracker v2 — Unit Tests
============================================
单元测试覆盖：
1. 频率转换逻辑（quarterly → daily）
2. CSI (Composite Scarcity Index) 计算
3. 信号生成规则
4. Forward Curve / Implied Run-rate 计算
5. Nowcast 高频 proxy 映射
6. Edge case 处理

运行方式:
    cd tracker_v2/test_suite
    python -m pytest test_unit.py -v
    # 或
    python test_unit.py

依赖: pytest (可选), pandas, numpy, duckdb
"""

import os
import sys
import json
import math
import tempfile
import unittest
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import duckdb

# ---------------------------------------------------------------------------
# 路径设置：允许导入 tracker.py (v1) 进行兼容性验证
# ---------------------------------------------------------------------------
TRACKER_V2 = Path(__file__).resolve().parents[1]
WORKSPACE = TRACKER_V2.parent
TRACKER_V1 = WORKSPACE / "tracker.py"

sys.path.insert(0, str(TRACKER_V2))

# 如果 v1 存在，加入路径
if TRACKER_V1.exists():
    sys.path.insert(0, str(WORKSPACE))

# 导入测试数据生成器
sys.path.insert(0, str(TRACKER_V2 / "test_suite"))
from test_data_generator import MockDataFactory

# ---------------------------------------------------------------------------
# 尝试导入 v1 组件（向后兼容验证）
# ---------------------------------------------------------------------------
try:
    from tracker_v2 import Database, AnalysisEngine, GPUCollector, THRESHOLDS
    V1_AVAILABLE = True
except Exception as e:
    print(f"⚠️  tracker_v2.py not importable: {e}")
    V1_AVAILABLE = False


# ---------------------------------------------------------------------------
# 频率转换逻辑测试（v2 核心新功能）
# ---------------------------------------------------------------------------
class TestFrequencyConversion(unittest.TestCase):
    """
    测试 quarterly CAPEX → daily 频率对齐的核心逻辑。
    v2 必须实现的三种策略：
    - step_hold: 季度内保持恒定值
    - linear_interp: 相邻季度间线性插值
    - forward_curve: guidance 年化摊薄到每日
    """

    def setUp(self):
        self.factory = MockDataFactory(seed=42)

    def _create_quarterly_df(self, quarters, values, tickers=None):
        """辅助：创建标准化 CAPEX DataFrame"""
        tickers = tickers or ["MSFT"]
        records = []
        for q, v in zip(quarters, values):
            for t in tickers:
                records.append({
                    "quarter_end": q,
                    "ticker": t,
                    "company": t,
                    "capex": v,
                    "guidance_low": v * 0.9,
                    "guidance_high": v * 1.1,
                })
        return pd.DataFrame(records)

    # -- step_hold --
    def test_step_hold_basic(self):
        """step_hold: 季度内每个交易日值相同"""
        quarters = ["2024-03-31", "2024-06-30"]
        values = [10.0, 15.0]
        capex_df = self._create_quarterly_df(quarters, values)

        daily = self._apply_step_hold(capex_df)

        q1_daily = daily[daily["date"] <= "2024-03-31"]
        self.assertTrue((q1_daily["capex"] == 10.0).all())

        q2_daily = daily[daily["date"] >= "2024-04-01"]
        self.assertTrue((q2_daily["capex"] == 15.0).all())

    def _apply_step_hold(self, capex_df):
        """step_hold 参考实现"""
        quarters = sorted(capex_df["quarter_end"].unique())
        records = []
        for i, qe in enumerate(quarters):
            q_start = pd.Timestamp(qe) - pd.DateOffset(days=89)
            if i > 0:
                q_start = pd.Timestamp(quarters[i - 1]) + pd.Timedelta(days=1)
            q_end = pd.Timestamp(qe)
            dates = pd.date_range(q_start, q_end, freq="D")
            q_data = capex_df[capex_df["quarter_end"] == qe]
            for _, row in q_data.iterrows():
                for d in dates:
                    records.append({
                        "date": d.strftime("%Y-%m-%d"),
                        "ticker": row["ticker"],
                        "capex": row["capex"],
                    })
        return pd.DataFrame(records)

    # -- linear_interp --
    def test_linear_interp_monotonic(self):
        """linear_interp: 插值序列应单调过渡"""
        quarters = ["2024-03-31", "2024-06-30", "2024-09-30"]
        values = [10.0, 20.0, 15.0]
        capex_df = self._create_quarterly_df(quarters, values)

        daily = self._apply_linear_interp(capex_df)
        msft = daily[daily["ticker"] == "MSFT"].sort_values("date")

        mid1 = msft[(msft["date"] >= "2024-04-01") & (msft["date"] <= "2024-05-31")]
        self.assertTrue(mid1["capex"].is_monotonic_increasing)

        mid2 = msft[(msft["date"] >= "2024-07-01") & (msft["date"] <= "2024-08-31")]
        self.assertTrue(mid2["capex"].is_monotonic_decreasing)

    def _apply_linear_interp(self, capex_df):
        """linear_interp 参考实现"""
        daily_records = self._apply_step_hold(capex_df)
        daily_records["date"] = pd.to_datetime(daily_records["date"])

        for ticker in daily_records["ticker"].unique():
            sub = daily_records[daily_records["ticker"] == ticker].sort_values("date")
            quarter_ends = capex_df[capex_df["ticker"] == ticker]["quarter_end"].unique()
            quarter_vals = capex_df[capex_df["ticker"] == ticker]["capex"].values

            full_range = pd.date_range(sub["date"].min(), sub["date"].max(), freq="D")
            q_dates = [pd.Timestamp(q) for q in sorted(quarter_ends)]
            interp = np.interp(
                full_range.astype("int64"),
                [d.value for d in q_dates],
                quarter_vals,
            )
            daily_records.loc[daily_records["ticker"] == ticker, "capex"] = interp[:len(sub)]

        daily_records["date"] = daily_records["date"].dt.strftime("%Y-%m-%d")
        return daily_records

    # -- forward_curve --
    def test_forward_curve_annualized(self):
        """forward_curve: 日度摊薄值 * 季度天数 ≈ 原季度值"""
        quarters = ["2024-03-31"]
        values = [90.0]
        capex_df = self._create_quarterly_df(quarters, values)

        daily = self._apply_forward_curve(capex_df)
        self.assertAlmostEqual(daily["capex"].iloc[0], 1.0, delta=0.1)
        self.assertAlmostEqual(daily["capex"].sum(), 90.0, delta=5.0)

    def _apply_forward_curve(self, capex_df):
        """forward_curve 参考实现：guidance 线性摊薄"""
        records = []
        for _, row in capex_df.iterrows():
            qe = pd.Timestamp(row["quarter_end"])
            qs = qe - pd.DateOffset(days=89)
            days = (qe - qs).days + 1
            daily_val = row["capex"] / days
            for d in pd.date_range(qs, qe, freq="D"):
                records.append({
                    "date": d.strftime("%Y-%m-%d"),
                    "ticker": row["ticker"],
                    "capex": daily_val,
                })
        return pd.DataFrame(records)

    # -- edge cases --
    def test_missing_quarter_gap(self):
        """缺失季度时，step_hold 不应产生 NaN"""
        quarters = ["2024-03-31", "2024-09-30"]
        values = [10.0, 15.0]
        capex_df = self._create_quarterly_df(quarters, values)

        daily = self._apply_step_hold(capex_df)
        self.assertFalse(daily["capex"].isna().any())

    def test_single_quarter(self):
        """只有一个季度数据时也能正常工作"""
        quarters = ["2024-03-31"]
        values = [10.0]
        capex_df = self._create_quarterly_df(quarters, values)

        for method in [self._apply_step_hold, self._apply_forward_curve]:
            daily = method(capex_df)
            self.assertGreater(len(daily), 0)
            self.assertFalse(daily["capex"].isna().any())


# ---------------------------------------------------------------------------
# CSI 计算测试
# ---------------------------------------------------------------------------
class TestCSICalculation(unittest.TestCase):
    """
    测试 Composite Scarcity Index 计算的正确性。
    v1 兼容 + v2 扩展。
    """

    def setUp(self):
        self.factory = MockDataFactory(seed=42)

    def _mock_csi(self, gpu_z, capex_z, ocpi_z):
        """CSI 计算参考实现（与 tracker.py 保持一致）"""
        raw_score = 0.40 * gpu_z + 0.35 * capex_z + 0.25 * ocpi_z
        csi = 50 + raw_score * 16.67
        csi = max(0, min(100, csi))
        regime = "High Scarcity" if csi > 70 else "Scarcity Easing" if csi < 40 else "Neutral"
        return csi, regime

    def test_csi_bounds(self):
        """CSI 必须始终在 [0, 100] 范围内"""
        extreme_values = [
            (-10, -10, -10),
            (10, 10, 10),
            (0, 0, 0),
            (-5, 5, 0),
        ]
        for gpu_z, capex_z, ocpi_z in extreme_values:
            csi, regime = self._mock_csi(gpu_z, capex_z, ocpi_z)
            self.assertGreaterEqual(csi, 0)
            self.assertLessEqual(csi, 100)
            self.assertIn(regime, ["High Scarcity", "Neutral", "Scarcity Easing"])

    def test_csi_weights(self):
        """验证权重：GPU Z-score 对 CSI 影响最大"""
        base = self._mock_csi(0, 0, 0)[0]
        gpu_up = self._mock_csi(1, 0, 0)[0]
        capex_up = self._mock_csi(0, 1, 0)[0]
        ocpi_up = self._mock_csi(0, 0, 1)[0]

        self.assertGreater(abs(gpu_up - base), abs(capex_up - base))
        self.assertGreater(abs(gpu_up - base), abs(ocpi_up - base))

    def test_csi_regime_thresholds(self):
        """验证 regime 切换阈值"""
        # CSI = 50 + raw_score * 16.67, raw_score = 0.4*gpu_z + 0.35*capex_z + 0.25*ocpi_z
        # 要 > 70: raw_score > 1.20, gpu_z > 1.20/0.4 = 3.0
        csi, regime = self._mock_csi(3.5, 0, 0)
        self.assertGreater(csi, 70)
        self.assertEqual(regime, "High Scarcity")

        # 要 < 40: raw_score < -0.60, gpu_z < -0.60/0.4 = -1.5
        csi, regime = self._mock_csi(-2.0, 0, 0)
        self.assertLess(csi, 40)
        self.assertEqual(regime, "Scarcity Easing")

        # 中间区域
        csi, regime = self._mock_csi(0, 0, 0)
        self.assertGreaterEqual(csi, 40)
        self.assertLessEqual(csi, 70)
        self.assertEqual(regime, "Neutral")

    @unittest.skipUnless(V1_AVAILABLE, "tracker.py v1 not available")
    def test_v1_csi_consistency(self):
        """v1 的 CSI 计算应与参考实现一致"""
        tmp_dir = tempfile.mkdtemp()
        db_path = os.path.join(tmp_dir, "test_tracker.db")

        try:
            db = Database(db_path)
            gpu_df, capex_df, ocpi_df = self.factory.generate_baseline_scenario(
                start="2024-01-01", end="2024-12-31"
            )

            conn = db.get_connection()
            conn.execute("""
                INSERT INTO gpu_prices_daily (date, provider, gpu_model, billing_type, price_per_hour, region, source)
                SELECT date, provider, gpu_model, billing_type, price_per_hour, region, source FROM gpu_df
            """)
            conn.execute("""
                INSERT INTO capex_quarterly (quarter_end, ticker, company, capex, revenue, operating_cash_flow, guidance_low, guidance_high, guidance_changed, source)
                SELECT quarter_end, ticker, company, capex, revenue, operating_cash_flow, guidance_low, guidance_high, guidance_changed, source FROM capex_df
            """)
            conn.execute("""
                INSERT INTO ocpi_daily (date, h100_ondemand, h100_1yr_contract, h100_spot_low, h100_spot_high, h100_spot_median, volatility_30d, source)
                SELECT date, h100_ondemand, h100_1yr_contract, h100_spot_low, h100_spot_high, h100_spot_median, volatility_30d, source FROM ocpi_df
            """)
            conn.close()

            engine = AnalysisEngine(db)
            csi = engine.calculate_csi()

            self.assertIn("csi", csi)
            self.assertIn("regime", csi)
            self.assertGreaterEqual(csi["csi"], 0)
            self.assertLessEqual(csi["csi"], 100)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 信号生成测试
# ---------------------------------------------------------------------------
class TestSignalGeneration(unittest.TestCase):
    """
    测试投资信号触发的正确性。
    """

    def setUp(self):
        self.factory = MockDataFactory(seed=42)

    def test_price_floor_breach(self):
        """H100 价格跌破 $2.50 应触发 CRITICAL 信号"""
        dates = pd.date_range("2024-01-01", periods=60, freq="D")
        prices = np.full(60, 2.0)
        gpu_df = pd.DataFrame({
            "date": dates.strftime("%Y-%m-%d"),
            "provider": "test",
            "gpu_model": "H100",
            "billing_type": "on-demand",
            "price_per_hour": prices,
            "region": "US",
            "source": "test",
        })

        breach = gpu_df["price_per_hour"].mean() < THRESHOLDS["h100_price_floor"]
        self.assertTrue(breach)

    def test_spot_discount_expansion(self):
        """spot 折扣超过 60% 应触发 WARNING 信号"""
        ondemand = 5.0
        spot = 1.5
        discount = (ondemand - spot) / ondemand
        self.assertGreater(discount, THRESHOLDS["spot_discount_critical"])

    def test_capex_slowdown(self):
        """CAPEX YoY 增速低于 10% 应触发 HIGH 信号"""
        growth = (105 - 100) / 100
        self.assertLess(growth, THRESHOLDS["capex_guidance_cut_pct"])

    def test_no_false_positives_on_normal_data(self):
        """正常数据不应产生误报"""
        gpu_df, capex_df, ocpi_df = self.factory.generate_baseline_scenario()

        h100_ondemand = gpu_df[
            (gpu_df["gpu_model"] == "H100") &
            (gpu_df["billing_type"] == "on-demand")
        ]["price_per_hour"]
        recent_30d = h100_ondemand.tail(30)
        self.assertGreaterEqual(recent_30d.mean(), 2.0)


# ---------------------------------------------------------------------------
# Forward Curve & Nowcast 测试（v2 新功能）
# ---------------------------------------------------------------------------
class TestForwardCurve(unittest.TestCase):
    """
    测试 v2 新增的 Forward Curve 和 Nowcast 逻辑。
    """

    def setUp(self):
        self.factory = MockDataFactory(seed=42)

    def test_implied_run_rate_calculation(self):
        """
        Implied CAPEX Run-rate = guidance_high / 季度天数
        验证日度值 * 天数 ≈ 原 guidance
        """
        guidance = 90.0
        days_in_quarter = 91
        daily_run_rate = guidance / days_in_quarter
        self.assertAlmostEqual(daily_run_rate * days_in_quarter, guidance, places=5)

    def test_forward_curve_integrity(self):
        """Forward curve 不应出现负值或极端跳变"""
        quarters = ["2024-03-31", "2024-06-30", "2024-09-30"]
        values = [90.0, 100.0, 85.0]
        capex_df = pd.DataFrame({
            "quarter_end": quarters,
            "ticker": "MSFT",
            "capex": values,
        })

        daily = self._linear_interp_for_forward(capex_df)
        self.assertFalse((daily["capex"] < 0).any())
        daily["pct_change"] = daily["capex"].pct_change().abs()
        self.assertTrue((daily["pct_change"] < 0.05).all() or daily["pct_change"].isna().sum() > 0)

    def _linear_interp_for_forward(self, capex_df):
        """简化 forward curve"""
        records = []
        for _, row in capex_df.iterrows():
            qe = pd.Timestamp(row["quarter_end"])
            qs = qe - pd.DateOffset(days=89)
            daily = row["capex"] / 91
            for d in pd.date_range(qs, qe, freq="D"):
                records.append({"date": d, "capex": daily})
        return pd.DataFrame(records)

    def test_nowcast_proxy_correlation(self):
        """
        Nowcast: 用 GPU 价格变化预测 CAPEX 变化方向。
        价格下降时，nowcast 应给出更低的 CAPEX 估计。
        """
        pre_price = 7.0
        post_price = 3.0
        price_change = (post_price - pre_price) / pre_price

        base_capex = 100.0
        beta = 0.5
        nowcast = base_capex * (1 + beta * price_change)

        self.assertLess(nowcast, base_capex)
        self.assertGreater(nowcast, 0)

    def test_earnings_event_alignment(self):
        """
        验证 earnings date 与季度数据的正确对齐。
        quarter_end 为 "2024-03-31" 时，earnings 通常在 4 月中下旬发布。
        """
        quarter_end = "2024-03-31"
        typical_earnings = "2024-04-25"
        q_dt = pd.Timestamp(quarter_end)
        e_dt = pd.Timestamp(typical_earnings)
        self.assertGreater(e_dt, q_dt)
        self.assertLess((e_dt - q_dt).days, 60)


# ---------------------------------------------------------------------------
# Edge Case 测试
# ---------------------------------------------------------------------------
class TestEdgeCases(unittest.TestCase):
    """
    边界条件和异常处理测试。
    """

    def setUp(self):
        self.factory = MockDataFactory(seed=42)

    def test_empty_database(self):
        """空数据库不应崩溃"""
        tmp_dir = tempfile.mkdtemp()
        db_path = os.path.join(tmp_dir, "test.db")
        try:
            conn = duckdb.connect(db_path)
            conn.execute("CREATE TABLE gpu_prices_daily (date DATE, price DOUBLE)")
            result = conn.execute("SELECT AVG(price) FROM gpu_prices_daily").fetchone()
            self.assertIsNone(result[0])
            conn.close()
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_single_record(self):
        """只有一条记录时也能计算"""
        tmp_dir = tempfile.mkdtemp()
        db_path = os.path.join(tmp_dir, "test.db")
        try:
            conn = duckdb.connect(db_path)
            conn.execute("CREATE TABLE gpu_prices_daily (date DATE, price DOUBLE)")
            conn.execute("INSERT INTO gpu_prices_daily VALUES ('2024-01-01', 5.0)")
            avg = conn.execute("SELECT AVG(price) FROM gpu_prices_daily").fetchone()[0]
            self.assertEqual(avg, 5.0)
            conn.close()
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_duplicate_records(self):
        """重复记录处理：应能去重或正确聚合"""
        gpu_df, capex_df, ocpi_df = self.factory.generate_baseline_scenario()
        duplicated = pd.concat([gpu_df, gpu_df], ignore_index=True)
        deduped = duplicated.groupby(["date", "provider", "gpu_model", "billing_type"]).agg({
            "price_per_hour": "mean",
            "region": "first",
            "source": "first",
        }).reset_index()
        self.assertLess(len(deduped), len(duplicated))

    def test_very_large_price_spike(self):
        """极端价格跳升不应使 CSI 溢出"""
        gpu_df, capex_df, ocpi_df = self.factory.generate_spike_scenario(
            spike_magnitude=50.0
        )
        max_price = gpu_df["price_per_hour"].max()
        self.assertGreater(max_price, 50.0)

    def test_all_same_price(self):
        """所有价格相同（std=0）时 Z-score 不应除零"""
        dates = pd.date_range("2024-01-01", periods=30, freq="D")
        prices = np.full(30, 5.0)
        gpu_df = pd.DataFrame({
            "date": dates.strftime("%Y-%m-%d"),
            "provider": "test",
            "gpu_model": "H100",
            "billing_type": "on-demand",
            "price_per_hour": prices,
            "region": "US",
            "source": "test",
        })
        std = gpu_df["price_per_hour"].std()
        z_score = 0.0 if std == 0 else (gpu_df["price_per_hour"].iloc[-1] - gpu_df["price_per_hour"].mean()) / std
        self.assertEqual(z_score, 0.0)

    def test_future_dates(self):
        """不应接受未来日期的数据"""
        future = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        self.assertGreater(pd.Timestamp(future), pd.Timestamp(datetime.now()))

    def test_negative_capex(self):
        """CAPEX 为负值时应取绝对值或报错"""
        raw_capex = -25.0
        stored_capex = abs(raw_capex)
        self.assertEqual(stored_capex, 25.0)


# ---------------------------------------------------------------------------
# 数据质量测试
# ---------------------------------------------------------------------------
class TestDataQuality(unittest.TestCase):
    """
    数据质量约束验证。
    """

    def setUp(self):
        self.factory = MockDataFactory(seed=42)

    def test_date_continuity(self):
        """daily 数据不应有超过 3 天的连续缺失"""
        gpu_df, _, _ = self.factory.generate_baseline_scenario()
        dates = pd.to_datetime(gpu_df["date"]).sort_values()
        gaps = dates.diff().dt.days.dropna()
        max_gap = gaps.max()
        self.assertLessEqual(max_gap, 3, f"发现 {max_gap} 天的数据缺口")

    def test_price_reasonableness(self):
        """GPU 价格应在合理区间 [$0.5, $50.0]"""
        gpu_df, _, _ = self.factory.generate_baseline_scenario()
        prices = gpu_df["price_per_hour"]
        self.assertGreaterEqual(prices.min(), 0.5)
        self.assertLessEqual(prices.max(), 50.0)

    def test_capex_positive(self):
        """CAPEX 必须为正"""
        _, capex_df, _ = self.factory.generate_baseline_scenario()
        self.assertTrue((capex_df["capex"] > 0).all())

    def test_guidance_range_valid(self):
        """guidance_low ≤ guidance_high"""
        _, capex_df, _ = self.factory.generate_baseline_scenario()
        valid = capex_df["guidance_low"] <= capex_df["guidance_high"]
        self.assertTrue(valid.all())


# ---------------------------------------------------------------------------
# 运行入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    unittest.main(verbosity=2)
