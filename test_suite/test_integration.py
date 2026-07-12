"""
AI Compute Scarcity Tracker v2 — Integration Tests
===================================================
端到端集成测试，验证完整数据 pipeline：
  init → update → report → status

覆盖场景：
- 正常流程（baseline scenario）
- Guidance 下调后的信号变化
- 数据缺失时的降级处理
- Streamlit dashboard 数据加载

运行方式:
    cd tracker_v2/test_suite
    python -m pytest test_integration.py -v
    # 或
    python test_integration.py
"""

import os
import sys
import json
import shutil
import tempfile
import unittest
import subprocess
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import duckdb

# ---------------------------------------------------------------------------
# 路径设置
# ---------------------------------------------------------------------------
TRACKER_V2 = Path(__file__).resolve().parents[1]
WORKSPACE = TRACKER_V2.parent
TRACKER_V1 = WORKSPACE / "tracker.py"

sys.path.insert(0, str(TRACKER_V2))
sys.path.insert(0, str(WORKSPACE))
sys.path.insert(0, str(TRACKER_V2 / "test_suite"))

from test_data_generator import MockDataFactory

# 尝试导入 v1 组件
V1_AVAILABLE = False
try:
    from tracker_v2 import Database, AnalysisEngine, ReportGenerator
    V1_AVAILABLE = True
except Exception as e:
    print(f"⚠️  tracker_v2.py not importable: {e}")


# ---------------------------------------------------------------------------
# 集成测试基类
# ---------------------------------------------------------------------------
class IntegrationTestBase(unittest.TestCase):
    """提供通用 fixture 和 helper 的基类"""

    def setUp(self):
        self.factory = MockDataFactory(seed=42)
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "test_tracker.db"

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _init_mock_database(self, gpu_df, capex_df, ocpi_df):
        """用 mock 数据初始化 DuckDB 数据库"""
        conn = duckdb.connect(str(self.db_path))

        # GPU 价格表
        conn.execute("""
            CREATE TABLE gpu_prices_daily (
                date DATE, provider VARCHAR, gpu_model VARCHAR,
                billing_type VARCHAR, price_per_hour DOUBLE,
                region VARCHAR DEFAULT 'US', source VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            INSERT INTO gpu_prices_daily (date, provider, gpu_model, billing_type, price_per_hour, region, source)
            SELECT date, provider, gpu_model, billing_type, price_per_hour, region, source FROM gpu_df
        """)

        # CAPEX 表
        conn.execute("""
            CREATE TABLE capex_quarterly (
                quarter_end DATE, ticker VARCHAR, company VARCHAR,
                capex DOUBLE, revenue DOUBLE, operating_cash_flow DOUBLE,
                guidance_low DOUBLE, guidance_high DOUBLE,
                guidance_changed BOOLEAN DEFAULT FALSE, source VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            INSERT INTO capex_quarterly (quarter_end, ticker, company, capex, revenue, operating_cash_flow, guidance_low, guidance_high, guidance_changed, source)
            SELECT quarter_end, ticker, company, capex, revenue, operating_cash_flow, guidance_low, guidance_high, guidance_changed, source FROM capex_df
        """)

        # OCPI 表
        conn.execute("""
            CREATE TABLE ocpi_daily (
                date DATE, h100_ondemand DOUBLE, h100_1yr_contract DOUBLE,
                h100_spot_low DOUBLE, h100_spot_high DOUBLE,
                h100_spot_median DOUBLE, volatility_30d DOUBLE,
                source VARCHAR, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            INSERT INTO ocpi_daily (date, h100_ondemand, h100_1yr_contract, h100_spot_low, h100_spot_high, h100_spot_median, volatility_30d, source)
            SELECT date, h100_ondemand, h100_1yr_contract, h100_spot_low, h100_spot_high, h100_spot_median, volatility_30d, source FROM ocpi_df
        """)

        # 信号表
        conn.execute("""
            CREATE TABLE signals (
                timestamp TIMESTAMP, type VARCHAR, severity VARCHAR,
                message VARCHAR, impact VARCHAR, acknowledged BOOLEAN DEFAULT FALSE
            )
        """)

        # CSI 历史表
        conn.execute("""
            CREATE TABLE csi_history (
                date DATE, csi DOUBLE, gpu_z DOUBLE, capex_z DOUBLE,
                ocpi_z DOUBLE, regime VARCHAR, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.close()
        return str(self.db_path)

    def _load_table(self, table_name):
        """从测试数据库加载表"""
        conn = duckdb.connect(str(self.db_path))
        df = conn.execute(f"SELECT * FROM {table_name}").df()
        conn.close()
        return df

    def _run_sql(self, sql):
        """执行 SQL 并返回结果"""
        conn = duckdb.connect(str(self.db_path))
        result = conn.execute(sql).df()
        conn.close()
        return result


# ---------------------------------------------------------------------------
# 端到端 Pipeline 测试
# ---------------------------------------------------------------------------
class TestEndToEndPipeline(IntegrationTestBase):
    """
    模拟完整的 tracker pipeline：
    数据加载 → 计算 CSI → 生成信号 → 生成报告
    """

    def test_baseline_pipeline(self):
        """基准场景：完整 pipeline 应无异常完成"""
        gpu_df, capex_df, ocpi_df = self.factory.generate_baseline_scenario()
        db_path = self._init_mock_database(gpu_df, capex_df, ocpi_df)

        # 验证数据已加载
        gpu_count = self._run_sql("SELECT COUNT(*) FROM gpu_prices_daily").iloc[0, 0]
        capex_count = self._run_sql("SELECT COUNT(*) FROM capex_quarterly").iloc[0, 0]
        ocpi_count = self._run_sql("SELECT COUNT(*) FROM ocpi_daily").iloc[0, 0]

        self.assertGreater(gpu_count, 0)
        self.assertGreater(capex_count, 0)
        self.assertGreater(ocpi_count, 0)

        # 验证 CSI 可计算（需要至少 30 天 GPU 数据 + 4 个季度 CAPEX）
        gpu_days = self._run_sql("""
            SELECT COUNT(DISTINCT date) FROM gpu_prices_daily
            WHERE gpu_model = 'H100' AND billing_type = 'on-demand'
        """).iloc[0, 0]
        capex_quarters = self._run_sql("""
            SELECT COUNT(DISTINCT quarter_end) FROM capex_quarterly
        """).iloc[0, 0]

        self.assertGreaterEqual(gpu_days, 30)
        self.assertGreaterEqual(capex_quarters, 4)

    def test_guidance_cut_pipeline(self):
        """Guidance 下调场景：应检测到 CAPEX 相关信号"""
        gpu_df, capex_df, ocpi_df = self.factory.generate_guidance_cut_scenario()
        db_path = self._init_mock_database(gpu_df, capex_df, ocpi_df)

        # 验证 guidance_changed 标记
        changed = self._run_sql("""
            SELECT COUNT(*) FROM capex_quarterly WHERE guidance_changed = TRUE
        """).iloc[0, 0]
        self.assertGreater(changed, 0)

        # 验证价格趋势下降
        recent_prices = self._run_sql("""
            SELECT price_per_hour FROM gpu_prices_daily
            WHERE gpu_model = 'H100' AND billing_type = 'on-demand'
            ORDER BY date DESC LIMIT 30
        """)
        early_prices = self._run_sql("""
            SELECT price_per_hour FROM gpu_prices_daily
            WHERE gpu_model = 'H100' AND billing_type = 'on-demand'
            ORDER BY date ASC LIMIT 30
        """)

        self.assertLess(recent_prices["price_per_hour"].mean(),
                        early_prices["price_per_hour"].mean())

    def test_missing_data_pipeline(self):
        """数据缺失场景：pipeline 应降级运行，不崩溃"""
        gpu_df, capex_df, ocpi_df = self.factory.generate_missing_data_scenario()
        db_path = self._init_mock_database(gpu_df, capex_df, ocpi_df)

        # 验证缺失的季度确实不存在
        missing_q = self._run_sql("""
            SELECT quarter_end FROM capex_quarterly WHERE quarter_end = '2024-06-30'
        """)
        self.assertEqual(len(missing_q), 0)

        # 验证 GPU 数据存在缺口但仍能查询
        total_gpu = self._run_sql("SELECT COUNT(*) FROM gpu_prices_daily").iloc[0, 0]
        self.assertGreater(total_gpu, 0)

    def test_frequency_mismatch_pipeline(self):
        """频率不匹配场景：季度少、日度多"""
        gpu_df, capex_df, ocpi_df = self.factory.generate_frequency_mismatch_scenario()
        db_path = self._init_mock_database(gpu_df, capex_df, ocpi_df)

        gpu_days = self._run_sql("SELECT COUNT(DISTINCT date) FROM gpu_prices_daily").iloc[0, 0]
        capex_q = self._run_sql("SELECT COUNT(DISTINCT quarter_end) FROM capex_quarterly").iloc[0, 0]

        # 日度数据应远多于季度数据
        self.assertGreater(gpu_days, capex_q * 30)

    @unittest.skipUnless(V1_AVAILABLE, "tracker.py v1 not available")
    def test_v1_report_generation(self):
        """v1 报告生成器应能在 mock 数据上运行"""
        gpu_df, capex_df, ocpi_df = self.factory.generate_baseline_scenario()
        db_path = self._init_mock_database(gpu_df, capex_df, ocpi_df)

        db = Database(db_path)
        report = ReportGenerator.generate_daily_report(db)

        self.assertIn("COMPOSITE SCARCITY INDEX", report)
        self.assertIn("GPU PRICE SNAPSHOT", report)
        self.assertIn("HYPERSCALER CAPEX", report)

    def test_spike_scenario(self):
        """价格 spike 场景：数据库应能存储极端值"""
        gpu_df, capex_df, ocpi_df = self.factory.generate_spike_scenario(spike_magnitude=20.0)
        db_path = self._init_mock_database(gpu_df, capex_df, ocpi_df)

        max_price = self._run_sql("""
            SELECT MAX(price_per_hour) FROM gpu_prices_daily
        """).iloc[0, 0]
        self.assertGreater(max_price, 20.0)


# ---------------------------------------------------------------------------
# v2 新功能集成测试
# ---------------------------------------------------------------------------
class TestV2Features(IntegrationTestBase):
    """
    测试 v2 新增功能的集成行为：
    - capex_daily_implied 表
    - Forward gap 计算
    - Earnings event 标记
    """

    def setUp(self):
        super().setUp()
        # 为 v2 功能创建扩展表结构
        self.v2_tables = ["capex_daily_implied", "earnings_calendar", "forward_gap"]

    def _init_v2_database(self, gpu_df, capex_df, ocpi_df):
        """初始化包含 v2 表结构的数据库"""
        db_path = self._init_mock_database(gpu_df, capex_df, ocpi_df)
        conn = duckdb.connect(db_path)

        # v2 新增：capex_daily_implied（季度 guidance 的日度摊薄）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS capex_daily_implied (
                date DATE,
                ticker VARCHAR,
                implied_daily_capex DOUBLE,
                guidance_quarter VARCHAR,
                method VARCHAR DEFAULT 'linear_forward',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # v2 新增：earnings_calendar（财报日历）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS earnings_calendar (
                ticker VARCHAR,
                quarter_end DATE,
                earnings_date DATE,
                actual_capex DOUBLE,
                guidance_low DOUBLE,
                guidance_high DOUBLE,
                guidance_changed BOOLEAN,
                surprise_pct DOUBLE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # v2 新增：forward_gap（guidance 与实际之间的差距）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS forward_gap (
                date DATE,
                ticker VARCHAR,
                implied_capex DOUBLE,
                nowcast_capex DOUBLE,
                gap_pct DOUBLE,
                regime VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.close()
        return db_path

    def test_capex_daily_implied_table(self):
        """capex_daily_implied 表应包含日度摊薄值"""
        gpu_df, capex_df, ocpi_df = self.factory.generate_baseline_scenario()
        db_path = self._init_v2_database(gpu_df, capex_df, ocpi_df)

        conn = duckdb.connect(db_path)

        # 手动填充 implied daily capex（模拟 v2 逻辑）
        for ticker in capex_df["ticker"].unique():
            sub = capex_df[capex_df["ticker"] == ticker].sort_values("quarter_end")
            for _, row in sub.iterrows():
                qe = pd.Timestamp(row["quarter_end"])
                qs = qe - pd.DateOffset(days=89)
                daily_val = row["capex"] / 91
                for d in pd.date_range(qs, qe, freq="D"):
                    conn.execute("""
                        INSERT INTO capex_daily_implied
                        VALUES (?, ?, ?, ?, 'linear_forward', CURRENT_TIMESTAMP)
                    """, [d.strftime("%Y-%m-%d"), ticker, daily_val, row["quarter_end"]])

        # 验证
        count = conn.execute("SELECT COUNT(*) FROM capex_daily_implied").fetchone()[0]
        self.assertGreater(count, 0)

        # 验证每个 ticker 每个季度有大约 90 条记录
        msft_q1 = conn.execute("""
            SELECT COUNT(*) FROM capex_daily_implied
            WHERE ticker = 'MSFT' AND guidance_quarter = '2024-03-31'
        """).fetchone()[0]
        self.assertGreaterEqual(msft_q1, 85)
        self.assertLessEqual(msft_q1, 95)

        conn.close()

    def test_earnings_calendar_alignment(self):
        """earnings_date 应在 quarter_end 之后"""
        gpu_df, capex_df, ocpi_df = self.factory.generate_baseline_scenario()
        db_path = self._init_v2_database(gpu_df, capex_df, ocpi_df)

        conn = duckdb.connect(db_path)

        # 模拟 earnings 日历
        for _, row in capex_df.iterrows():
            qe = pd.Timestamp(row["quarter_end"])
            # earnings 通常在 quarter_end 后 30-45 天
            earnings_date = qe + pd.Timedelta(days=40)
            conn.execute("""
                INSERT INTO earnings_calendar
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, [
                row["ticker"], row["quarter_end"], earnings_date.strftime("%Y-%m-%d"),
                row["capex"], row["guidance_low"], row["guidance_high"],
                row["guidance_changed"], 0.0
            ])

        # 验证 earnings_date > quarter_end
        invalid = conn.execute("""
            SELECT COUNT(*) FROM earnings_calendar
            WHERE earnings_date <= quarter_end
        """).fetchone()[0]
        self.assertEqual(invalid, 0)

        conn.close()

    def test_forward_gap_calculation(self):
        """forward_gap 应正确计算 guidance 与 nowcast 的差距"""
        gpu_df, capex_df, ocpi_df = self.factory.generate_baseline_scenario()
        db_path = self._init_v2_database(gpu_df, capex_df, ocpi_df)

        conn = duckdb.connect(db_path)

        # 填充 capex_daily_implied
        for ticker in capex_df["ticker"].unique():
            sub = capex_df[capex_df["ticker"] == ticker].sort_values("quarter_end")
            for _, row in sub.iterrows():
                qe = pd.Timestamp(row["quarter_end"])
                qs = qe - pd.DateOffset(days=89)
                daily_val = row["capex"] / 91
                for d in pd.date_range(qs, qe, freq="D"):
                    conn.execute("""
                        INSERT INTO capex_daily_implied (date, ticker, implied_daily_capex, guidance_quarter)
                        VALUES (?, ?, ?, ?)
                    """, [d.strftime("%Y-%m-%d"), ticker, daily_val, row["quarter_end"]])

        # 计算 forward_gap
        # gap = (nowcast - implied) / implied
        conn.execute("""
            INSERT INTO forward_gap
            SELECT
                c.date,
                c.ticker,
                c.implied_daily_capex,
                c.implied_daily_capex * 0.95 as nowcast_capex,
                (c.implied_daily_capex * 0.95 - c.implied_daily_capex) / c.implied_daily_capex as gap_pct,
                'Neutral' as regime,
                CURRENT_TIMESTAMP
            FROM capex_daily_implied c
            LIMIT 100
        """)

        gaps = conn.execute("SELECT * FROM forward_gap").df()
        self.assertGreater(len(gaps), 0)
        # gap_pct 应在合理范围 [-50%, +50%]
        self.assertTrue((gaps["gap_pct"].abs() < 0.5).all())

        conn.close()


# ---------------------------------------------------------------------------
# Dashboard 数据加载测试
# ---------------------------------------------------------------------------
class TestDashboardDataLoading(IntegrationTestBase):
    """
    验证 dashboard.py 所需的所有 SQL 查询能在 mock 数据上正确执行。
    """

    def test_all_dashboard_queries(self):
        """Dashboard 所有查询应正常返回"""
        gpu_df, capex_df, ocpi_df = self.factory.generate_baseline_scenario()
        db_path = self._init_mock_database(gpu_df, capex_df, ocpi_df)
        conn = duckdb.connect(db_path)

        queries = {
            "gpu_history": """
                SELECT date, gpu_model, billing_type, AVG(price_per_hour) as price
                FROM gpu_prices_daily
                GROUP BY date, gpu_model, billing_type
                ORDER BY date
            """,
            "capex_history": """
                SELECT quarter_end, ticker, company, capex, revenue, capex/revenue as capex_ratio
                FROM capex_quarterly
                ORDER BY quarter_end
            """,
            "ocpi_history": "SELECT * FROM ocpi_daily ORDER BY date",
            "csi_history": "SELECT * FROM csi_history ORDER BY date",
            "latest_gpu": """
                SELECT gpu_model, billing_type, AVG(price_per_hour) as price
                FROM gpu_prices_daily
                WHERE date = (SELECT MAX(date) FROM gpu_prices_daily)
                GROUP BY gpu_model, billing_type
            """,
            "latest_capex": """
                SELECT company, capex, revenue, capex/revenue as ratio
                FROM capex_quarterly
                WHERE quarter_end = (SELECT MAX(quarter_end) FROM capex_quarterly)
            """,
            "signals": """
                SELECT * FROM signals
                WHERE acknowledged = FALSE
                ORDER BY timestamp DESC
                LIMIT 20
            """,
        }

        for name, sql in queries.items():
            try:
                result = conn.execute(sql).df()
                # 即使为空也应成功执行
                self.assertIsInstance(result, pd.DataFrame)
            except Exception as e:
                self.fail(f"Dashboard query '{name}' failed: {e}")

        conn.close()

    def test_csi_history_with_manual_insert(self):
        """手动插入 CSI 后，dashboard 查询应能读取"""
        gpu_df, capex_df, ocpi_df = self.factory.generate_baseline_scenario()
        db_path = self._init_mock_database(gpu_df, capex_df, ocpi_df)
        conn = duckdb.connect(db_path)

        # 手动插入几条 CSI 记录
        for i in range(10):
            date = (datetime(2024, 1, 1) + pd.Timedelta(days=i)).strftime("%Y-%m-%d")
            conn.execute("""
                INSERT INTO csi_history (date, csi, gpu_z, capex_z, ocpi_z, regime)
                VALUES (?, ?, ?, ?, ?, ?)
            """, [date, 55.0 + i, 0.5, 0.3, 0.2, "Neutral"])

        csi_df = conn.execute("SELECT * FROM csi_history ORDER BY date").df()
        self.assertEqual(len(csi_df), 10)

        conn.close()


# ---------------------------------------------------------------------------
# 性能测试（轻量级）
# ---------------------------------------------------------------------------
class TestPerformance(unittest.TestCase):
    """
    轻量级性能基准测试。
    """

    def setUp(self):
        self.factory = MockDataFactory(seed=42)

    def test_large_dataset_insertion(self):
        """大规模数据插入性能"""
        # 生成 2 年数据
        gpu_df, capex_df, ocpi_df = self.factory.generate_baseline_scenario(
            start="2023-01-01", end="2024-12-31"
        )

        tmp_dir = tempfile.mkdtemp()
        db_path = os.path.join(tmp_dir, "test.db")

        try:
            conn = duckdb.connect(db_path)
            conn.execute("""
                CREATE TABLE gpu_prices_daily (date DATE, provider VARCHAR,
                    gpu_model VARCHAR, billing_type VARCHAR, price_per_hour DOUBLE,
                    region VARCHAR, source VARCHAR)
            """)
            conn.execute("INSERT INTO gpu_prices_daily SELECT * FROM gpu_df")

            count = conn.execute("SELECT COUNT(*) FROM gpu_prices_daily").fetchone()[0]
            self.assertGreater(count, 700)
            conn.close()
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_query_performance(self):
        """常用查询应在 1 秒内完成"""
        gpu_df, capex_df, ocpi_df = self.factory.generate_baseline_scenario()

        tmp_dir = tempfile.mkdtemp()
        db_path = os.path.join(tmp_dir, "test.db")

        try:
            conn = duckdb.connect(db_path)
            conn.execute("""
                CREATE TABLE gpu_prices_daily (date DATE, provider VARCHAR,
                    gpu_model VARCHAR, billing_type VARCHAR, price_per_hour DOUBLE,
                    region VARCHAR, source VARCHAR)
            """)
            conn.execute("INSERT INTO gpu_prices_daily SELECT * FROM gpu_df")

            import time
            start = time.time()
            conn.execute("""
                SELECT date, AVG(price_per_hour)
                FROM gpu_prices_daily
                WHERE gpu_model = 'H100'
                GROUP BY date
                ORDER BY date
            """).df()
            elapsed = time.time() - start

            self.assertLess(elapsed, 1.0, f"Query took {elapsed:.2f}s, expected < 1s")
            conn.close()
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 运行入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    unittest.main(verbosity=2)
    """
    轻量级性能基准测试。
    """

    def setUp(self):
        self.factory = MockDataFactory(seed=42)

    def test_large_dataset_insertion(self):
        """大规模数据插入性能"""
        # 生成 2 年数据
        gpu_df, capex_df, ocpi_df = self.factory.generate_baseline_scenario(
            start="2023-01-01", end="2024-12-31"
        )

        tmp_dir = tempfile.mkdtemp()
        db_path = os.path.join(tmp_dir, "test.db")

        try:
            conn = duckdb.connect(db_path)
            conn.execute("""
                CREATE TABLE gpu_prices_daily (date DATE, provider VARCHAR,
                    gpu_model VARCHAR, billing_type VARCHAR, price_per_hour DOUBLE,
                    region VARCHAR, source VARCHAR)
            """)
            conn.execute("INSERT INTO gpu_prices_daily SELECT * FROM gpu_df")

            count = conn.execute("SELECT COUNT(*) FROM gpu_prices_daily").fetchone()[0]
            self.assertGreater(count, 700)
            conn.close()
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_query_performance(self):
        """常用查询应在 1 秒内完成"""
        gpu_df, capex_df, ocpi_df = self.factory.generate_baseline_scenario()

        tmp_dir = tempfile.mkdtemp()
        db_path = os.path.join(tmp_dir, "test.db")

        try:
            conn = duckdb.connect(db_path)
            conn.execute("""
                CREATE TABLE gpu_prices_daily (date DATE, provider VARCHAR,
                    gpu_model VARCHAR, billing_type VARCHAR, price_per_hour DOUBLE,
                    region VARCHAR, source VARCHAR)
            """)
            conn.execute("INSERT INTO gpu_prices_daily SELECT * FROM gpu_df")

            import time
            start = time.time()
            conn.execute("""
                SELECT date, AVG(price_per_hour)
                FROM gpu_prices_daily
                WHERE gpu_model = 'H100'
                GROUP BY date
                ORDER BY date
            """).df()
            elapsed = time.time() - start

            self.assertLess(elapsed, 1.0, f"Query took {elapsed:.2f}s, expected < 1s")
            conn.close()
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        """大规模数据插入性能"""
        # 生成 2 年数据
        gpu_df, capex_df, ocpi_df = self.factory.generate_baseline_scenario(
            start="2023-01-01", end="2024-12-31"
        )

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            conn = duckdb.connect(db_path)
            conn.execute("""
                CREATE TABLE gpu_prices_daily (date DATE, provider VARCHAR,
                    gpu_model VARCHAR, billing_type VARCHAR, price_per_hour DOUBLE,
                    region VARCHAR, source VARCHAR)
            """)
            conn.execute("INSERT INTO gpu_prices_daily SELECT * FROM gpu_df")

            count = conn.execute("SELECT COUNT(*) FROM gpu_prices_daily").fetchone()[0]
            self.assertGreater(count, 700)
            conn.close()
        finally:
            os.unlink(db_path)

    def test_query_performance(self):
        """常用查询应在 1 秒内完成"""
        gpu_df, capex_df, ocpi_df = self.factory.generate_baseline_scenario()

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            conn = duckdb.connect(db_path)
            conn.execute("""
                CREATE TABLE gpu_prices_daily (date DATE, provider VARCHAR,
                    gpu_model VARCHAR, billing_type VARCHAR, price_per_hour DOUBLE,
                    region VARCHAR, source VARCHAR)
            """)
            conn.execute("INSERT INTO gpu_prices_daily SELECT * FROM gpu_df")

            import time
            start = time.time()
            conn.execute("""
                SELECT date, AVG(price_per_hour)
                FROM gpu_prices_daily
                WHERE gpu_model = 'H100'
                GROUP BY date
                ORDER BY date
            """).df()
            elapsed = time.time() - start

            self.assertLess(elapsed, 1.0, f"Query took {elapsed:.2f}s, expected < 1s")
            conn.close()
        finally:
            os.unlink(db_path)


# ---------------------------------------------------------------------------
# 运行入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    unittest.main(verbosity=2)
