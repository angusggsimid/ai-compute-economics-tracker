"""
AI Compute Scarcity Tracker v2 — Test Data Generator
=====================================================
生成可控的 mock 数据，用于单元测试、集成测试和 edge case 验证。

支持场景：
- 正常趋势（价格缓慢下降，CAPEX 稳步上升）
- Guidance 上调 / 下调
- 数据缺失（跳空、季度数据延迟）
- 频率切换（quarterly → daily 的对齐验证）
- Regime 切换（High Scarcity ↔ Scarcity Easing）

用法:
    from test_data_generator import MockDataFactory
    factory = MockDataFactory(seed=42)
    gpu_df, capex_df, ocpi_df = factory.generate_baseline_scenario()
"""

import os
import sys
import json
import random
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# 配置常量
# ---------------------------------------------------------------------------
RNG = np.random.default_rng(seed=42)

HYPERSCALERS = ["MSFT", "AMZN", "GOOGL", "META"]
GPU_MODELS = ["H100", "H200", "A100", "B200", "B300", "MI300X"]
BILLING_TYPES = ["on-demand", "spot", "1yr-reserved"]

# 关键阈值（与 tracker.py 保持一致）
THRESHOLDS = {
    "h100_price_floor": 2.50,
    "h100_price_peak": 7.00,
    "spot_discount_critical": 0.60,
    "capex_guidance_cut_pct": 0.10,
}


# ---------------------------------------------------------------------------
# Data Models (与 tracker.py v1 兼容)
# ---------------------------------------------------------------------------
@dataclass
class GPUPriceRecord:
    date: str
    provider: str
    gpu_model: str
    billing_type: str
    price_per_hour: float
    region: str = "US"
    source: str = "mock"

    def to_dict(self):
        return asdict(self)


@dataclass
class CAPEXRecord:
    quarter_end: str
    ticker: str
    company: str
    capex: float
    revenue: Optional[float] = None
    operating_cash_flow: Optional[float] = None
    guidance_low: Optional[float] = None
    guidance_high: Optional[float] = None
    guidance_changed: bool = False
    source: str = "mock"

    def to_dict(self):
        return asdict(self)


@dataclass
class OCPIRecord:
    date: str
    h100_ondemand: Optional[float] = None
    h100_1yr_contract: Optional[float] = None
    h100_spot_low: Optional[float] = None
    h100_spot_high: Optional[float] = None
    h100_spot_median: Optional[float] = None
    volatility_30d: Optional[float] = None
    source: str = "mock"

    def to_dict(self):
        return asdict(self)


# ---------------------------------------------------------------------------
# Mock Data Factory
# ---------------------------------------------------------------------------
class MockDataFactory:
    """
    可控的测试数据工厂。
    所有随机过程使用固定 seed，保证可复现性。
    """

    def __init__(self, seed: int = 42):
        self.rng = np.random.default_rng(seed)
        self.seed = seed

    # ------------------------------------------------------------------
    # 基础生成器
    # ------------------------------------------------------------------
    def generate_daily_dates(self, start: str, end: str) -> pd.DatetimeIndex:
        """生成连续交易日（简化：每周 7 天）"""
        return pd.date_range(start=start, end=end, freq="D")

    def generate_quarter_ends(self, start: str, end: str) -> List[str]:
        """生成季度末日期列表"""
        dr = pd.date_range(start=start, end=end, freq="Q")
        return [d.strftime("%Y-%m-%d") for d in dr]

    # ------------------------------------------------------------------
    # GPU 价格生成
    # ------------------------------------------------------------------
    def generate_gpu_prices(
        self,
        dates: pd.DatetimeIndex,
        base_price: float = 7.0,
        trend_per_day: float = -0.015,
        noise_sigma: float = 0.25,
        model: str = "H100",
        billing_type: str = "on-demand",
        provider: str = "composite_median",
        floor: float = 2.0,
    ) -> pd.DataFrame:
        """
        生成带趋势的 GPU 价格序列。
        price_t = base + trend * t + N(0, sigma)
        """
        n = len(dates)
        trend = np.arange(n) * trend_per_day
        noise = self.rng.normal(0, noise_sigma, n)
        prices = base_price + trend + noise
        prices = np.maximum(prices, floor)

        df = pd.DataFrame({
            "date": dates,
            "provider": provider,
            "gpu_model": model,
            "billing_type": billing_type,
            "price_per_hour": prices,
            "region": "US",
            "source": "mock",
        })
        df["date"] = df["date"].dt.strftime("%Y-%m-%d")
        return df

    def generate_gpu_prices_with_regime_shift(
        self,
        dates: pd.DatetimeIndex,
        shift_date: str,
        pre_params: Dict = None,
        post_params: Dict = None,
    ) -> pd.DataFrame:
        """
        生成包含 regime shift 的 GPU 价格：
        shift_date 前/后使用不同的 trend/noise 参数。
        """
        pre_params = pre_params or {"base": 7.0, "trend": -0.005, "sigma": 0.2}
        post_params = post_params or {"base": 4.0, "trend": -0.03, "sigma": 0.4}

        shift_dt = pd.Timestamp(shift_date)
        pre_mask = dates < shift_dt
        post_mask = dates >= shift_dt

        prices = np.zeros(len(dates))

        # pre-shift
        pre_dates = dates[pre_mask]
        if len(pre_dates) > 0:
            pre_trend = np.arange(len(pre_dates)) * pre_params["trend"]
            pre_noise = self.rng.normal(0, pre_params["sigma"], len(pre_dates))
            prices[pre_mask] = pre_params["base"] + pre_trend + pre_noise

        # post-shift（以 shift 当天价格为新 base）
        post_dates = dates[post_mask]
        if len(post_dates) > 0:
            post_base = prices[pre_mask][-1] if np.any(pre_mask) else post_params["base"]
            post_trend = np.arange(len(post_dates)) * post_params["trend"]
            post_noise = self.rng.normal(0, post_params["sigma"], len(post_dates))
            prices[post_mask] = post_base + post_trend + post_noise

        prices = np.maximum(prices, 1.5)

        df = pd.DataFrame({
            "date": dates,
            "provider": "composite_median",
            "gpu_model": "H100",
            "billing_type": "on-demand",
            "price_per_hour": prices,
            "region": "US",
            "source": "mock_regime_shift",
        })
        df["date"] = df["date"].dt.strftime("%Y-%m-%d")
        return df

    def generate_multi_billing_gpu_prices(
        self,
        dates: pd.DatetimeIndex,
        base_ondemand: float = 7.0,
    ) -> pd.DataFrame:
        """生成同一型号、多种计费方式的 GPU 价格"""
        records = []
        for billing in ["on-demand", "spot", "1yr-reserved"]:
            if billing == "spot":
                discount = self.rng.uniform(0.35, 0.65)
                base = base_ondemand * (1 - discount)
                sigma = 0.4
                trend = -0.02
            elif billing == "1yr-reserved":
                base = base_ondemand * 0.82
                sigma = 0.15
                trend = -0.008
            else:
                base = base_ondemand
                sigma = 0.25
                trend = -0.015

            df = self.generate_gpu_prices(
                dates, base_price=base, trend_per_day=trend,
                noise_sigma=sigma, billing_type=billing
            )
            records.append(df)
        return pd.concat(records, ignore_index=True)

    # ------------------------------------------------------------------
    # CAPEX 生成
    # ------------------------------------------------------------------
    def generate_capex_quarterly(
        self,
        quarter_ends: List[str],
        tickers: List[str] = None,
        base_capex: Dict[str, float] = None,
        growth_rate: float = 0.08,
        noise_sigma: float = 2.0,
    ) -> pd.DataFrame:
        """
        生成季度 CAPEX 数据。
        capex_t = base * (1 + growth)^t + N(0, sigma)
        """
        tickers = tickers or HYPERSCALERS
        base_capex = base_capex or {
            "MSFT": 20.0, "AMZN": 19.0, "GOOGL": 13.0, "META": 9.0
        }

        records = []
        for t, qe in enumerate(quarter_ends):
            for ticker in tickers:
                base = base_capex.get(ticker, 15.0)
                trend = base * ((1 + growth_rate) ** t)
                noise = self.rng.normal(0, noise_sigma)
                capex_val = max(trend + noise, 1.0)

                records.append({
                    "quarter_end": qe,
                    "ticker": ticker,
                    "company": ticker,
                    "capex": round(capex_val, 2),
                    "revenue": round(capex_val * self.rng.uniform(3.0, 6.0), 2),
                    "operating_cash_flow": round(capex_val * self.rng.uniform(1.5, 3.0), 2),
                    "guidance_low": round(capex_val * 0.9, 2),
                    "guidance_high": round(capex_val * 1.1, 2),
                    "guidance_changed": False,
                    "source": "mock",
                })
        return pd.DataFrame(records)

    def generate_capex_with_guidance_revision(
        self,
        quarter_ends: List[str],
        revision_quarter: str,
        revision_type: str = "cut",  # "cut" or "raise"
        revision_pct: float = 0.15,
    ) -> pd.DataFrame:
        """
        生成包含 guidance revision 的 CAPEX 数据。
        revision_quarter 及之后的季度会体现 revision 影响。
        """
        df = self.generate_capex_quarterly(quarter_ends)
        mask = df["quarter_end"] >= revision_quarter
        if revision_type == "cut":
            df.loc[mask, "capex"] *= (1 - revision_pct)
            df.loc[mask, "guidance_low"] *= (1 - revision_pct)
            df.loc[mask, "guidance_high"] *= (1 - revision_pct)
        else:
            df.loc[mask, "capex"] *= (1 + revision_pct)
            df.loc[mask, "guidance_low"] *= (1 + revision_pct)
            df.loc[mask, "guidance_high"] *= (1 + revision_pct)

        df.loc[mask, "guidance_changed"] = True
        return df

    def generate_capex_with_missing_quarters(
        self,
        quarter_ends: List[str],
        missing_quarters: List[str],
    ) -> pd.DataFrame:
        """模拟某些季度数据缺失（延迟披露）"""
        df = self.generate_capex_quarterly(quarter_ends)
        df = df[~df["quarter_end"].isin(missing_quarters)]
        return df

    # ------------------------------------------------------------------
    # OCPI 生成
    # ------------------------------------------------------------------
    def generate_ocpi_daily(
        self,
        dates: pd.DatetimeIndex,
        base_ondemand: float = 7.0,
        trend_per_day: float = -0.015,
    ) -> pd.DataFrame:
        """生成 OCPI 日度数据"""
        n = len(dates)
        ondemand = base_ondemand + np.arange(n) * trend_per_day + self.rng.normal(0, 0.2, n)
        ondemand = np.maximum(ondemand, 1.5)

        records = []
        for i, d in enumerate(dates):
            records.append({
                "date": d.strftime("%Y-%m-%d"),
                "h100_ondemand": round(ondemand[i], 2),
                "h100_1yr_contract": round(ondemand[i] * 0.82, 2),
                "h100_spot_low": round(ondemand[i] * 0.55, 2),
                "h100_spot_high": round(ondemand[i] * 1.75, 2),
                "h100_spot_median": round(ondemand[i] * 0.75, 2),
                "volatility_30d": round(self.rng.uniform(0.08, 0.25), 3),
                "source": "mock",
            })
        return pd.DataFrame(records)

    # ------------------------------------------------------------------
    # 预设场景（Scenario）
    # ------------------------------------------------------------------
    def generate_baseline_scenario(
        self,
        start: str = "2024-01-01",
        end: str = "2025-12-31",
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        基准场景：
        - GPU 价格从 $7.0 缓慢下降到 $3.0
        - CAPEX 稳步增长 8% QoQ
        - OCPI 同步跟踪
        """
        dates = self.generate_daily_dates(start, end)
        quarters = self.generate_quarter_ends(start, end)

        gpu_df = self.generate_gpu_prices(dates, base_price=7.0, trend_per_day=-0.011)
        capex_df = self.generate_capex_quarterly(quarters, growth_rate=0.08)
        ocpi_df = self.generate_ocpi_daily(dates, base_ondemand=7.0, trend_per_day=-0.011)

        return gpu_df, capex_df, ocpi_df

    def generate_guidance_cut_scenario(
        self,
        start: str = "2024-01-01",
        end: str = "2025-12-31",
        cut_date: str = "2025-03-31",
        cut_pct: float = 0.15,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Guidance 下调场景：
        - 2025 Q1 起 CAPEX guidance 下调 15%
        - GPU 价格同步加速下跌
        """
        dates = self.generate_daily_dates(start, end)
        quarters = self.generate_quarter_ends(start, end)

        gpu_df = self.generate_gpu_prices_with_regime_shift(
            dates, shift_date=cut_date,
            pre_params={"base": 7.0, "trend": -0.005, "sigma": 0.2},
            post_params={"base": 4.0, "trend": -0.025, "sigma": 0.35},
        )
        capex_df = self.generate_capex_with_guidance_revision(
            quarters, revision_quarter=cut_date, revision_type="cut", revision_pct=cut_pct
        )
        ocpi_df = self.generate_ocpi_daily(dates, base_ondemand=7.0, trend_per_day=-0.011)
        # 让 OCPI 在 cut_date 后也加速下跌
        cut_dt = pd.Timestamp(cut_date)
        post_mask = dates >= cut_dt
        ocpi_df.loc[post_mask, "h100_ondemand"] *= np.linspace(1.0, 0.85, post_mask.sum())

        return gpu_df, capex_df, ocpi_df

    def generate_guidance_raise_scenario(
        self,
        start: str = "2024-01-01",
        end: str = "2025-12-31",
        raise_date: str = "2024-09-30",
        raise_pct: float = 0.20,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Guidance 上调场景：
        - 2024 Q3 起 CAPEX guidance 上调 20%
        - GPU 价格止跌回升
        """
        dates = self.generate_daily_dates(start, end)
        quarters = self.generate_quarter_ends(start, end)

        gpu_df = self.generate_gpu_prices_with_regime_shift(
            dates, shift_date=raise_date,
            pre_params={"base": 7.0, "trend": -0.015, "sigma": 0.2},
            post_params={"base": 5.5, "trend": 0.01, "sigma": 0.3},
        )
        capex_df = self.generate_capex_with_guidance_revision(
            quarters, revision_quarter=raise_date, revision_type="raise", revision_pct=raise_pct
        )
        ocpi_df = self.generate_ocpi_daily(dates, base_ondemand=7.0, trend_per_day=-0.011)

        return gpu_df, capex_df, ocpi_df

    def generate_missing_data_scenario(
        self,
        start: str = "2024-01-01",
        end: str = "2025-12-31",
        missing_quarters: List[str] = None,
        missing_gpu_weeks: int = 2,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        数据缺失场景：
        - 某些季度 CAPEX 缺失
        - GPU 价格中间有两周缺失
        """
        dates = self.generate_daily_dates(start, end)
        quarters = self.generate_quarter_ends(start, end)
        missing_quarters = missing_quarters or ["2024-06-30", "2025-03-31"]

        gpu_df = self.generate_gpu_prices(dates)
        # 删除中间两周
        mid_start = dates[len(dates) // 2]
        mid_end = mid_start + timedelta(days=missing_gpu_weeks * 7)
        gpu_df = gpu_df[
            ~((pd.to_datetime(gpu_df["date"]) >= mid_start) &
              (pd.to_datetime(gpu_df["date"]) <= mid_end))
        ]

        capex_df = self.generate_capex_with_missing_quarters(quarters, missing_quarters)
        ocpi_df = self.generate_ocpi_daily(dates)

        return gpu_df, capex_df, ocpi_df

    def generate_frequency_mismatch_scenario(
        self,
        start: str = "2024-01-01",
        end: str = "2025-06-30",
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        频率不匹配场景：
        - 只有 3 个季度的 CAPEX 数据
        - 但有 500+ 天的 daily GPU 价格
        用于验证 quarterly→daily 频率转换逻辑。
        """
        dates = self.generate_daily_dates(start, end)
        # 只取前 3 个季度
        quarters = self.generate_quarter_ends(start, end)[:3]

        gpu_df = self.generate_gpu_prices(dates)
        capex_df = self.generate_capex_quarterly(quarters)
        ocpi_df = self.generate_ocpi_daily(dates)

        return gpu_df, capex_df, ocpi_df

    def generate_spike_scenario(
        self,
        start: str = "2024-01-01",
        end: str = "2025-12-31",
        spike_date: str = "2025-01-15",
        spike_magnitude: float = 3.0,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        价格 spike 场景：
        - 某一天 GPU 价格异常跳升（模拟供应链中断）
        用于验证异常值处理和 volatility 计算。
        """
        dates = self.generate_daily_dates(start, end)
        quarters = self.generate_quarter_ends(start, end)

        gpu_df = self.generate_gpu_prices(dates)
        spike_mask = gpu_df["date"] == spike_date
        if spike_mask.any():
            gpu_df.loc[spike_mask, "price_per_hour"] += spike_magnitude

        capex_df = self.generate_capex_quarterly(quarters)
        ocpi_df = self.generate_ocpi_daily(dates)
        if spike_mask.any():
            ocpi_df.loc[spike_mask, "h100_ondemand"] += spike_magnitude

        return gpu_df, capex_df, ocpi_df

    # ------------------------------------------------------------------
    # 导出辅助
    # ------------------------------------------------------------------
    def save_scenario(
        self,
        gpu_df: pd.DataFrame,
        capex_df: pd.DataFrame,
        ocpi_df: pd.DataFrame,
        out_dir: str,
        scenario_name: str,
    ) -> Dict[str, str]:
        """将场景数据保存为 CSV"""
        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        paths = {}
        for name, df in [("gpu", gpu_df), ("capex", capex_df), ("ocpi", ocpi_df)]:
            p = out_path / f"{scenario_name}_{name}.csv"
            df.to_csv(p, index=False)
            paths[name] = str(p)

        # 保存元数据
        meta = {
            "scenario": scenario_name,
            "generated_at": datetime.now().isoformat(),
            "seed": self.seed,
            "records": {
                "gpu": len(gpu_df),
                "capex": len(capex_df),
                "ocpi": len(ocpi_df),
            }
        }
        meta_path = out_path / f"{scenario_name}_meta.json"
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        paths["meta"] = str(meta_path)

        return paths


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    factory = MockDataFactory(seed=42)
    out_dir = Path(__file__).parent / "fixtures"

    scenarios = {
        "baseline": factory.generate_baseline_scenario,
        "guidance_cut": factory.generate_guidance_cut_scenario,
        "guidance_raise": factory.generate_guidance_raise_scenario,
        "missing_data": factory.generate_missing_data_scenario,
        "frequency_mismatch": factory.generate_frequency_mismatch_scenario,
        "spike": factory.generate_spike_scenario,
    }

    for name, fn in scenarios.items():
        print(f"Generating scenario: {name} ...")
        gpu, capex, ocpi = fn()
        paths = factory.save_scenario(gpu, capex, ocpi, str(out_dir), name)
        print(f"  → {paths}")

    print(f"\n✅ All scenarios saved to: {out_dir}")
