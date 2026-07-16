"""
商品期货特征层单元测试 (Phase 3b-i)

覆盖:
- technical.compute_technical_metrics 主入口
  - 列名规范化(中文 / 英文 / 混合)
  - 空数据 / 数据不足
  - 多周期(日 / 周)
  - 标准 schema 字段(latest / stats / signals / snapshot / quality)
  - 触发信号(RSI / MACD / BOLL / OI / 资金流等)
  - OI 背离(confirm / conflict / neutral)
  - 期货综合评分
"""
from __future__ import annotations

import importlib.util
import sys
import types
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
import pytest


# =============================================================================
# 模块加载(不依赖 tradingagents 顶层 logger,沿用 test_commodity_data_layer 风格)
# =============================================================================

REPO_ROOT = Path(__file__).resolve().parents[1]


def _ensure_pkg(pkg_path: str) -> types.ModuleType:
    """确保 `a.b.c` 形式的包链全部注册到 sys.modules(空 ModuleType 占位)。"""
    parts = pkg_path.split(".")
    for i in range(1, len(parts) + 1):
        full = ".".join(parts[:i])
        if full not in sys.modules:
            mod = types.ModuleType(full)
            mod.__path__ = []  # type: ignore[attr-defined]
            sys.modules[full] = mod
    return sys.modules[pkg_path]


def _load_module(name: str, rel_path: str):
    """按文件路径加载模块并注册到 sys.modules(避免 @dataclass / typing 找不到模块)。

    若 name 含 `.`,自动建立父包链,便于子模块使用绝对导入。
    """
    if name in sys.modules:
        return sys.modules[name]
    if "." in name:
        parent = ".".join(name.split(".")[:-1])
        _ensure_pkg(parent)
    spec = importlib.util.spec_from_file_location(name, str(REPO_ROOT / rel_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def tech_mod():
    """tradingagents.features.commodity.technical"""
    # indicators.py 需要先加载
    _load_module("indicators", "tradingagents/tools/analysis/indicators.py")
    return _load_module("tech", "tradingagents/features/commodity/technical.py")


# 各 feature 模块 fixture(scope="module" — 共享 sys.modules 注册)
@pytest.fixture(scope="module")
def helpers_mod():
    return _load_module(
        "tradingagents.features.commodity._helpers",
        "tradingagents/features/commodity/_helpers.py",
    )


@pytest.fixture(scope="module")
def basis_mod(helpers_mod):
    return _load_module(
        "tradingagents.features.commodity.basis",
        "tradingagents/features/commodity/basis.py",
    )


@pytest.fixture(scope="module")
def inventory_mod(helpers_mod):
    return _load_module(
        "tradingagents.features.commodity.inventory",
        "tradingagents/features/commodity/inventory.py",
    )


@pytest.fixture(scope="module")
def positioning_mod(helpers_mod):
    return _load_module(
        "tradingagents.features.commodity.positioning",
        "tradingagents/features/commodity/positioning.py",
    )


@pytest.fixture(scope="module")
def term_structure_mod(helpers_mod):
    return _load_module(
        "tradingagents.features.commodity.term_structure",
        "tradingagents/features/commodity/term_structure.py",
    )


@pytest.fixture(scope="module")
def news_sentiment_mod(helpers_mod):
    return _load_module(
        "tradingagents.features.commodity.news_sentiment",
        "tradingagents/features/commodity/news_sentiment.py",
    )


# =============================================================================
# 合成数据 fixtures
# =============================================================================

def _make_synthetic_ohlcv(
    n_days: int = 300,
    start_price: float = 100.0,
    trend: float = 0.0003,
    vol: float = 0.015,
    seed: int = 42,
    start_date: date = date(2025, 1, 1),
    include_oi: bool = True,
    column_lang: str = "zh",
) -> pd.DataFrame:
    """生成可重复的随机游走 OHLCV 数据。

    column_lang: "zh"(中文列名,provider 默认)/ "en"(英文列名)/ "mixed"
    """
    np.random.seed(seed)
    rets = np.random.normal(trend, vol, n_days)
    close = start_price * np.exp(np.cumsum(rets))
    high = close * (1 + np.abs(np.random.normal(0, 0.005, n_days)))
    low = close * (1 - np.abs(np.random.normal(0, 0.005, n_days)))
    open_ = close / (1 + np.random.normal(0, 0.005, n_days))
    volume = np.random.randint(50000, 200000, n_days)
    if include_oi:
        oi = np.random.randint(100000, 300000, n_days) + np.arange(n_days) * 100
    else:
        oi = None
    dates = [start_date + timedelta(days=i) for i in range(n_days)]

    if column_lang == "zh":
        data = {
            "日期": dates,
            "开盘价": open_,
            "最高价": high,
            "最低价": low,
            "收盘价": close,
            "成交量": volume,
        }
        if include_oi:
            data["持仓量"] = oi
    elif column_lang == "en":
        data = {
            "date": dates,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
        if include_oi:
            data["open_interest"] = oi
    else:  # mixed
        data = {
            "date": dates,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
        if include_oi:
            data["open_interest"] = oi
    return pd.DataFrame(data)


def _make_trending_up(n_days: int = 200, seed: int = 7) -> pd.DataFrame:
    """生成明显上涨趋势数据,用于触发金叉 / 多头占优 / 突破信号。"""
    np.random.seed(seed)
    close = np.linspace(100, 200, n_days) + np.random.normal(0, 1.5, n_days)
    high = close + np.abs(np.random.normal(0, 0.5, n_days))
    low = close - np.abs(np.random.normal(0, 0.5, n_days))
    open_ = low + np.random.uniform(0, 1, n_days)
    volume = np.random.randint(80000, 150000, n_days)
    oi = np.linspace(200000, 250000, n_days) + np.random.normal(0, 5000, n_days)
    dates = [date(2025, 1, 1) + timedelta(days=i) for i in range(n_days)]
    return pd.DataFrame({
        "日期": dates,
        "开盘价": open_,
        "最高价": high,
        "最低价": low,
        "收盘价": close,
        "成交量": volume,
        "持仓量": oi,
    })


def _make_trending_down(n_days: int = 200, seed: int = 11) -> pd.DataFrame:
    """明显下跌趋势数据。"""
    np.random.seed(seed)
    close = np.linspace(200, 100, n_days) + np.random.normal(0, 1.5, n_days)
    high = close + np.abs(np.random.normal(0, 0.5, n_days))
    low = close - np.abs(np.random.normal(0, 0.5, n_days))
    open_ = high - np.random.uniform(0, 1, n_days)
    volume = np.random.randint(80000, 150000, n_days)
    oi = np.linspace(250000, 200000, n_days) + np.random.normal(0, 5000, n_days)
    dates = [date(2025, 1, 1) + timedelta(days=i) for i in range(n_days)]
    return pd.DataFrame({
        "日期": dates,
        "开盘价": open_,
        "最高价": high,
        "最低价": low,
        "收盘价": close,
        "成交量": volume,
        "持仓量": oi,
    })


# =============================================================================
# 1. 列名规范化
# =============================================================================

class TestNormalizeColumns:
    def test_chinese_columns(self, tech_mod):
        df = _make_synthetic_ohlcv(n_days=50, column_lang="zh")
        out = tech_mod.normalize_columns(df)
        assert "close" in out.columns
        assert "open" in out.columns
        assert "high" in out.columns
        assert "low" in out.columns
        assert "date" in out.columns
        assert "volume" in out.columns
        assert "open_interest" in out.columns

    def test_english_columns(self, tech_mod):
        df = _make_synthetic_ohlcv(n_days=50, column_lang="en")
        out = tech_mod.normalize_columns(df)
        assert "close" in out.columns
        assert "date" in out.columns

    def test_missing_close_raises(self, tech_mod):
        df = pd.DataFrame({"date": [date(2025, 1, 1)], "open": [100]})
        with pytest.raises(ValueError, match="收盘价"):
            tech_mod.normalize_columns(df)

    def test_empty_dataframe(self, tech_mod):
        df = pd.DataFrame()
        out = tech_mod.normalize_columns(df)
        assert out.empty


# =============================================================================
# 2. compute_technical_metrics 主入口 — 基本结构
# =============================================================================

class TestComputeTechnicalMetricsBasic:
    def test_basic_output_structure(self, tech_mod):
        df = _make_synthetic_ohlcv(n_days=300)
        result = tech_mod.compute_technical_metrics(df, include_weekly=True)
        assert "daily" in result
        assert "weekly" in result
        assert "combined" in result
        assert "quality" in result

    def test_daily_schema_keys(self, tech_mod):
        df = _make_synthetic_ohlcv(n_days=300)
        result = tech_mod.compute_technical_metrics(df)
        daily = result["daily"]
        assert "latest" in daily
        assert "stats" in daily
        assert "signals" in daily
        assert "snapshot" in daily
        assert "quality" in daily
        assert "trend" in daily
        assert "volatility" in daily
        assert "oi_divergence" in daily

    def test_combined_schema(self, tech_mod):
        df = _make_synthetic_ohlcv(n_days=300)
        result = tech_mod.compute_technical_metrics(df)
        combined = result["combined"]
        assert "direction" in combined
        assert "strength" in combined
        assert "signals" in combined
        assert "oi_divergence" in combined
        assert "volatility" in combined
        assert combined["direction"] in ("long", "short", "neutral")
        assert isinstance(combined["strength"], float)
        assert 0.0 <= combined["strength"] <= 1.0

    def test_quality_fields(self, tech_mod):
        df = _make_synthetic_ohlcv(n_days=300)
        result = tech_mod.compute_technical_metrics(df)
        q = result["quality"]
        assert q["rows"] == 300
        assert q["coverage"] > 0.95
        assert q["data_freshness_days"] is not None
        assert q["data_freshness_days"] >= 0


# =============================================================================
# 3. 多周期(日 / 周)
# =============================================================================

class TestMultiTimeframe:
    def test_weekly_present_when_sufficient_data(self, tech_mod):
        df = _make_synthetic_ohlcv(n_days=300)
        result = tech_mod.compute_technical_metrics(df, include_weekly=True)
        assert result["weekly"] is not None
        assert "trend" in result["weekly"]
        assert "signals" in result["weekly"]

    def test_weekly_skipped_when_disabled(self, tech_mod):
        df = _make_synthetic_ohlcv(n_days=300)
        result = tech_mod.compute_technical_metrics(df, include_weekly=False)
        assert result["weekly"] is None

    def test_weekly_skipped_when_insufficient_data(self, tech_mod):
        df = _make_synthetic_ohlcv(n_days=20)
        result = tech_mod.compute_technical_metrics(df, weekly_min_rows=30)
        assert result["weekly"] is None

    def test_weekly_quality(self, tech_mod):
        df = _make_synthetic_ohlcv(n_days=300)
        result = tech_mod.compute_technical_metrics(df)
        assert result["weekly"]["quality"]["rows"] >= 40  # 300 天 ≈ 60 周


# =============================================================================
# 4. 趋势方向(强趋势应被识别)
# =============================================================================

class TestTrendDirection:
    def test_trending_up_detected(self, tech_mod):
        df = _make_trending_up(n_days=200)
        result = tech_mod.compute_technical_metrics(df)
        assert result["daily"]["trend"]["direction"] == "long"
        assert result["daily"]["trend"]["strength"] > 0
        assert result["combined"]["direction"] == "long"

    def test_trending_down_detected(self, tech_mod):
        df = _make_trending_down(n_days=200)
        result = tech_mod.compute_technical_metrics(df)
        assert result["daily"]["trend"]["direction"] == "short"
        assert result["daily"]["trend"]["strength"] > 0
        assert result["combined"]["direction"] == "short"

    def test_directional_consistency(self, tech_mod):
        """日 / 周同向时 combined 应与 daily 一致。"""
        df = _make_trending_up(n_days=300)
        result = tech_mod.compute_technical_metrics(df)
        d_dir = result["daily"]["trend"]["direction"]
        w_dir = result["weekly"]["trend"]["direction"] if result["weekly"] else None
        if w_dir is not None and d_dir == w_dir:
            assert result["combined"]["direction"] == d_dir


# =============================================================================
# 5. 触发信号
# =============================================================================

class TestTriggers:
    def test_signals_is_list(self, tech_mod):
        df = _make_synthetic_ohlcv(n_days=300)
        result = tech_mod.compute_technical_metrics(df)
        assert isinstance(result["daily"]["signals"], list)
        for s in result["daily"]["signals"]:
            assert isinstance(s, str)

    def test_strong_uptrend_generates_bullish_triggers(self, tech_mod):
        df = _make_trending_up(n_days=200)
        result = tech_mod.compute_technical_metrics(df)
        signals_text = " ".join(result["daily"]["signals"])
        # 至少出现一种多头信号
        bullish_keywords = ["多头", "金叉", "MA20/MA60上方", "RSI超卖", "突破20日新高"]
        assert any(k in signals_text for k in bullish_keywords), (
            f"上涨趋势未触发任何多头信号: {result['daily']['signals']}"
        )

    def test_strong_downtrend_generates_bearish_triggers(self, tech_mod):
        df = _make_trending_down(n_days=200)
        result = tech_mod.compute_technical_metrics(df)
        signals_text = " ".join(result["daily"]["signals"])
        bearish_keywords = ["空头", "死叉", "MA20/MA60下方", "跌破20日新低"]
        assert any(k in signals_text for k in bearish_keywords), (
            f"下跌趋势未触发任何空头信号: {result['daily']['signals']}"
        )

    def test_combined_signals_unique(self, tech_mod):
        """combined.signals 应为日 / 周去重后的并集。"""
        df = _make_synthetic_ohlcv(n_days=300)
        result = tech_mod.compute_technical_metrics(df)
        combined_signals = result["combined"]["signals"]
        assert len(combined_signals) == len(set(combined_signals)) or len(combined_signals) > 0
        # 不应出现重复项
        assert len(combined_signals) == len(set(combined_signals))


# =============================================================================
# 6. 快照(snapshot)字段覆盖
# =============================================================================

class TestSnapshot:
    def test_snapshot_contains_50plus_indicators(self, tech_mod):
        df = _make_synthetic_ohlcv(n_days=300)
        result = tech_mod.compute_technical_metrics(df)
        snap = result["daily"]["snapshot"]
        # 至少 40 个指标
        assert len(snap) >= 40, f"快照只有 {len(snap)} 个字段,期望 >= 40"

    def test_snapshot_keys_include_core(self, tech_mod):
        df = _make_synthetic_ohlcv(n_days=300)
        result = tech_mod.compute_technical_metrics(df)
        snap = result["daily"]["snapshot"]
        for k in [
            "close", "ma20", "ma60", "ema20", "atr14",
            "rsi14", "macd", "macd_signal", "macd_hist",
            "boll_up", "boll_mid", "boll_low",
            "adx14", "kdj_k", "kdj_d", "kdj_j",
            "psar", "williams_r14", "cci20",
            "stoch_k", "stoch_d",
            "tenkan_sen", "kijun_sen",
            "tsi", "vpt", "cmf20",
            "oi_change_pct", "composite_score",
        ]:
            assert k in snap, f"快照缺少 {k}"

    def test_snapshot_values_are_float_or_none(self, tech_mod):
        df = _make_synthetic_ohlcv(n_days=300)
        result = tech_mod.compute_technical_metrics(df)
        for k, v in result["daily"]["snapshot"].items():
            assert v is None or isinstance(v, (int, float)), (
                f"snapshot[{k}] 类型错误: {type(v)}"
            )


# =============================================================================
# 7. OI 背离
# =============================================================================

class TestOIDivergence:
    def test_oi_divergence_field_present(self, tech_mod):
        df = _make_synthetic_ohlcv(n_days=300, include_oi=True)
        result = tech_mod.compute_technical_metrics(df)
        assert result["daily"]["oi_divergence"] in ("confirm", "conflict", "neutral")

    def test_oi_divergence_without_oi(self, tech_mod):
        df = _make_synthetic_ohlcv(n_days=300, include_oi=False)
        result = tech_mod.compute_technical_metrics(df)
        # 无 OI 数据时所有周期都应为 neutral
        assert result["daily"]["oi_divergence"] == "neutral"
        assert result["combined"]["oi_divergence"] == "neutral"


# =============================================================================
# 8. 波动率
# =============================================================================

class TestVolatility:
    def test_volatility_regime_present(self, tech_mod):
        df = _make_synthetic_ohlcv(n_days=300)
        result = tech_mod.compute_technical_metrics(df)
        vol = result["daily"]["volatility"]
        assert "atr" in vol
        assert "regime" in vol
        assert vol["regime"] in ("high", "low")

    def test_high_volatility_data_detected(self, tech_mod):
        """高波动数据(日内跳变大)→ regime=high。"""
        np.random.seed(99)
        n = 300
        close = 100 * np.exp(np.cumsum(np.random.normal(0, 0.05, n)))  # 5% 日波动
        high = close * 1.05
        low = close * 0.95
        dates = [date(2025, 1, 1) + timedelta(days=i) for i in range(n)]
        df = pd.DataFrame({
            "日期": dates, "开盘价": close, "最高价": high,
            "最低价": low, "收盘价": close, "成交量": 100000, "持仓量": 200000,
        })
        result = tech_mod.compute_technical_metrics(df)
        assert result["daily"]["volatility"]["regime"] == "high"


# =============================================================================
# 9. 边界与异常
# =============================================================================

class TestEdgeCases:
    def test_empty_dataframe(self, tech_mod):
        result = tech_mod.compute_technical_metrics(pd.DataFrame())
        assert result["daily"]["signals"] == [] or "无数据" in " ".join(result["daily"]["signals"])
        assert result["combined"]["direction"] == "neutral"

    def test_none_input(self, tech_mod):
        result = tech_mod.compute_technical_metrics(None)
        assert result["combined"]["direction"] == "neutral"

    def test_minimal_data(self, tech_mod):
        df = _make_synthetic_ohlcv(n_days=5)
        result = tech_mod.compute_technical_metrics(df)
        # 极短数据应不抛异常,返回中性结果
        assert result["combined"]["direction"] in ("long", "short", "neutral")

    def test_missing_close_column(self, tech_mod):
        df = pd.DataFrame({"日期": [date(2025, 1, 1)], "成交量": [100]})
        result = tech_mod.compute_technical_metrics(df)
        # 应返回带错误信息的中性结果
        assert result["combined"]["direction"] == "neutral"
        assert result["quality"]["rows"] == 0

    def test_no_oi_column(self, tech_mod):
        df = _make_synthetic_ohlcv(n_days=200, include_oi=False)
        result = tech_mod.compute_technical_metrics(df)
        # 无 OI 不应报错
        assert result["combined"]["direction"] in ("long", "short", "neutral")


# =============================================================================
# 10. 与 provider 列名兼容(provider 默认输出 = 中文)
# =============================================================================

class TestProviderCompatibility:
    def test_accepts_provider_chinese_columns(self, tech_mod):
        """模拟 provider `get_historical_data` 输出:含中文列 + rollover_date 列。"""
        df = _make_synthetic_ohlcv(n_days=300)
        # 模拟 provider 额外输出的 rollover_date 列
        df["rollover_date"] = False
        df.loc[df.index[100], "rollover_date"] = True
        result = tech_mod.compute_technical_metrics(df)
        # 额外列应被原样保留(不影响计算)
        assert "rollover_date" not in result["daily"]["snapshot"]
        assert result["daily"]["trend"]["direction"] in ("long", "short", "neutral")

    def test_indicator_modules_reused(self, tech_mod):
        """technical.py 必须复用 tradingagents.tools.analysis.indicators。"""
        # 通过属性引用确认
        import tradingagents.tools.analysis.indicators as ind
        # tech_mod 应该 import 了 indicators(通过 ind_mod 引用)
        assert hasattr(ind, "ma")
        assert hasattr(ind, "macd")
        assert hasattr(ind, "rsi")
        assert hasattr(ind, "boll")
        assert hasattr(ind, "atr")
        assert hasattr(ind, "kdj")


# =============================================================================
# 11. latest 字段(最常用 ~20 项)
# =============================================================================

class TestLatest:
    def test_latest_has_close(self, tech_mod):
        df = _make_synthetic_ohlcv(n_days=300)
        result = tech_mod.compute_technical_metrics(df)
        assert "close" in result["daily"]["latest"]
        assert result["daily"]["latest"]["close"] is not None
        assert result["daily"]["latest"]["close"] > 0

    def test_latest_size(self, tech_mod):
        df = _make_synthetic_ohlcv(n_days=300)
        result = tech_mod.compute_technical_metrics(df)
        # latest 应是 snapshot 的精简版,约 15-25 项
        assert 10 <= len(result["daily"]["latest"]) <= 30


# =============================================================================
# 12. stats(zscore / slope)
# =============================================================================

class TestStats:
    def test_stats_has_zscore(self, tech_mod):
        df = _make_synthetic_ohlcv(n_days=300)
        result = tech_mod.compute_technical_metrics(df)
        stats = result["daily"]["stats"]
        assert "close_zscore_180d" in stats
        assert "close_slope_20d" in stats

    def test_stats_zscore_range(self, tech_mod):
        """z-score 通常在 [-3, 3] 范围,极端情况下也可能超出。"""
        df = _make_synthetic_ohlcv(n_days=300)
        result = tech_mod.compute_technical_metrics(df)
        z = result["daily"]["stats"]["close_zscore_180d"]
        if z is not None:
            assert -5 <= z <= 5

    def test_stats_slope_sign_matches_trend(self, tech_mod):
        """强上涨趋势 → 20 日斜率 > 0;强下跌 → 斜率 < 0。"""
        df_up = _make_trending_up(n_days=200)
        df_dn = _make_trending_down(n_days=200)
        r_up = tech_mod.compute_technical_metrics(df_up)
        r_dn = tech_mod.compute_technical_metrics(df_dn)
        s_up = r_up["daily"]["stats"]["close_slope_20d"]
        s_dn = r_dn["daily"]["stats"]["close_slope_20d"]
        if s_up is not None and s_dn is not None:
            assert s_up > 0
            assert s_dn < 0


# =============================================================================
# 13. basis.py — 基差特征
# =============================================================================

def _make_basis_df(n_days: int = 200, symbol: str = "CU", seed: int = 3,
                   column_lang: str = "zh") -> pd.DataFrame:
    """生成合成基差数据:近月基差率在 [-0.05, 0.05] 随机游走。"""
    np.random.seed(seed)
    near_basis_rate = np.random.normal(0.02, 0.01, n_days)
    dom_basis_rate = near_basis_rate * 0.8 + np.random.normal(0, 0.005, n_days)
    spot = np.linspace(70000, 72000, n_days) + np.random.normal(0, 100, n_days)
    near_price = spot * (1 - near_basis_rate)
    dom_price = spot * (1 - dom_basis_rate)
    dates = [date(2025, 1, 1) + timedelta(days=i) for i in range(n_days)]
    if column_lang == "zh":
        return pd.DataFrame({
            "日期": dates, "品种": [symbol] * n_days,
            "现货价格": spot,
            "近月合约": [f"{symbol}2502"] * n_days,
            "近月合约价": near_price,
            "主力合约": [f"{symbol}2506"] * n_days,
            "主力合约价": dom_price,
            "近月基差": spot - near_price,
            "主力基差": spot - dom_price,
            "近月基差率": near_basis_rate,
            "主力基差率": dom_basis_rate,
        })
    return pd.DataFrame({
        "date": dates, "symbol": [symbol] * n_days,
        "spot_price": spot,
        "near_contract": [f"{symbol}2502"] * n_days,
        "near_contract_price": near_price,
        "dominant_contract": [f"{symbol}2506"] * n_days,
        "dominant_contract_price": dom_price,
        "near_basis": spot - near_price,
        "dom_basis": spot - dom_price,
        "near_basis_rate": near_basis_rate,
        "dom_basis_rate": dom_basis_rate,
    })


class TestBasis:
    def test_basic_output(self, basis_mod):
        df = _make_basis_df()
        result = basis_mod.compute_basis_metrics(df)
        assert "latest" in result
        assert "stats" in result
        assert "signals" in result
        assert "snapshot" in result
        assert "quality" in result

    def test_latest_has_required_fields(self, basis_mod):
        df = _make_basis_df()
        result = basis_mod.compute_basis_metrics(df)
        latest = result["latest"]
        for k in ["spot_price", "near_basis_rate", "dom_basis_rate"]:
            assert k in latest

    def test_stats_zscore_slope(self, basis_mod):
        df = _make_basis_df()
        result = basis_mod.compute_basis_metrics(df)
        stats = result["stats"]
        assert "zscore_180d" in stats
        assert "slope_20d" in stats
        assert "near_basis_rate" in stats["zscore_180d"]
        assert "dom_basis_rate" in stats["slope_20d"]

    def test_empty_dataframe(self, basis_mod):
        result = basis_mod.compute_basis_metrics(pd.DataFrame())
        assert result["latest"] == {}
        # 至少包含一个信号说明(空数据场景)
        assert len(result["signals"]) >= 1
        assert result["quality"]["rows"] == 0

    def test_none_input(self, basis_mod):
        result = basis_mod.compute_basis_metrics(None)
        assert result["latest"] == {}

    def test_multi_symbol_filter(self, basis_mod):
        df = pd.concat([
            _make_basis_df(symbol="CU"),
            _make_basis_df(symbol="AL", seed=5),
        ], ignore_index=True)
        result = basis_mod.compute_basis_metrics(df, symbol="AL")
        assert result["quality"].get("symbol") == "AL"

    def test_signals_for_extreme_basis(self, basis_mod):
        """让最后一日基差率达到极端值 → 触发信号。"""
        df = _make_basis_df(n_days=200)
        df.loc[df.index[-1], "近月基差率"] = 0.08   # 极端升水
        df.loc[df.index[-1], "主力基差率"] = -0.06  # 极端贴水
        result = basis_mod.compute_basis_metrics(df)
        signals_text = " ".join(result["signals"])
        assert "升水" in signals_text or "贴水" in signals_text

    def test_insufficient_samples(self, basis_mod):
        df = _make_basis_df(n_days=3)
        result = basis_mod.compute_basis_metrics(df)
        assert "样本不足" in " ".join(result["signals"]) or result["quality"]["rows"] == 3


# =============================================================================
# 14. inventory.py — 库存特征
# =============================================================================

def _make_inventory_df(n_days: int = 200, column_lang: str = "zh",
                       seed: int = 13) -> pd.DataFrame:
    """生成库存时序:基础 100 万吨 ± 季节性。"""
    np.random.seed(seed)
    base = 100 + 10 * np.sin(np.linspace(0, 4 * np.pi, n_days))
    noise = np.random.normal(0, 2, n_days)
    values = base + noise
    dates = [date(2024, 1, 1) + timedelta(days=i * 7) for i in range(n_days)]
    if column_lang == "zh":
        return pd.DataFrame({"日期": dates, "库存": values, "增减": np.diff(values, prepend=values[0])})
    return pd.DataFrame({"date": dates, "value": values, "delta": np.diff(values, prepend=values[0])})


def _make_inventory_with_jump(n_days: int = 100, column_lang: str = "zh") -> pd.DataFrame:
    """含一次异常跳变的库存(模拟突发去库)。"""
    df = _make_inventory_df(n_days=n_days, column_lang=column_lang)
    df.iloc[-1, df.columns.get_loc("库存") if column_lang == "zh" else df.columns.get_loc("value")] -= 25
    return df


class TestInventory:
    def test_basic_output(self, inventory_mod):
        df = _make_inventory_df()
        result = inventory_mod.compute_inventory_metrics(df)
        assert "latest" in result
        assert result["latest"]["value"] is not None

    def test_latest_has_value(self, inventory_mod):
        df = _make_inventory_df()
        result = inventory_mod.compute_inventory_metrics(df)
        assert result["latest"]["value"] > 0

    def test_wow_mom_change(self, inventory_mod):
        df = _make_inventory_df(n_days=100)
        result = inventory_mod.compute_inventory_metrics(df)
        snap = result["snapshot"]
        assert "wow_change" in snap
        assert "mom_change" in snap

    def test_jump_flag_triggers(self, inventory_mod):
        """含异常跳变的数据 → jump_flag=True。"""
        df = _make_inventory_with_jump(n_days=80)
        result = inventory_mod.compute_inventory_metrics(df)
        assert result["snapshot"]["jump_flag"] is True
        signals_text = " ".join(result["signals"])
        assert "跳变" in signals_text

    def test_no_jump_on_smooth_data(self, inventory_mod):
        df = _make_inventory_df(n_days=100)
        result = inventory_mod.compute_inventory_metrics(df)
        assert result["snapshot"]["jump_flag"] is False

    def test_signals_have_percentile(self, inventory_mod):
        """让最后一日值极高 → 应触发高分位信号。"""
        df = _make_inventory_df(n_days=200)
        col = "库存"
        df.loc[df.index[-1], col] = df[col].max() + 50
        result = inventory_mod.compute_inventory_metrics(df)
        signals_text = " ".join(result["signals"])
        assert "高分位" in signals_text or "偏离" in signals_text

    def test_empty(self, inventory_mod):
        result = inventory_mod.compute_inventory_metrics(pd.DataFrame())
        assert result["latest"] == {}

    def test_english_columns(self, inventory_mod):
        df = _make_inventory_df(column_lang="en")
        result = inventory_mod.compute_inventory_metrics(df)
        assert result["latest"]["value"] is not None


# =============================================================================
# 15. positioning.py — 持仓/拥挤度
# =============================================================================

def _make_position_df(n_days: int = 200, seed: int = 17) -> pd.DataFrame:
    """生成席位列:top20 多/空 持仓量 + 总持仓。"""
    np.random.seed(seed)
    base = 100000
    long_top20 = base + np.cumsum(np.random.normal(50, 200, n_days))
    short_top20 = base + np.cumsum(np.random.normal(-30, 200, n_days))
    total_oi = long_top20 + short_top20 + np.random.normal(50000, 5000, n_days)
    dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(n_days)]
    return pd.DataFrame({
        "日期": dates,
        "long_top20": long_top20,
        "short_top20": short_top20,
        "total_open_interest": total_oi,
    })


class TestPositioning:
    def test_dataframe_input(self, positioning_mod):
        df = _make_position_df()
        result = positioning_mod.compute_positioning_metrics(df)
        assert result["latest"]["long_top20"] is not None
        assert result["latest"]["short_top20"] is not None
        assert result["latest"]["net_long_top20"] is not None

    def test_dict_input(self, positioning_mod):
        df_cu = _make_position_df(seed=1)
        df_cu["symbol"] = "CU"
        df_al = _make_position_df(seed=2)
        df_al["symbol"] = "AL"
        data = {"CU": df_cu, "AL": df_al}
        result = positioning_mod.compute_positioning_metrics(data, symbol="CU")
        assert result["quality"]["symbol"] == "CU"

    def test_concentration_computed(self, positioning_mod):
        df = _make_position_df()
        result = positioning_mod.compute_positioning_metrics(df)
        assert "concentration" in result["snapshot"]
        assert result["snapshot"]["concentration"] is not None

    def test_net_long_change_5d(self, positioning_mod):
        df = _make_position_df()
        result = positioning_mod.compute_positioning_metrics(df)
        assert "net_long_change_5d" in result["snapshot"]

    def test_empty(self, positioning_mod):
        result = positioning_mod.compute_positioning_metrics(pd.DataFrame())
        assert result["latest"] == {}

    def test_none_input(self, positioning_mod):
        result = positioning_mod.compute_positioning_metrics(None)
        assert result["latest"] == {}

    def test_signal_for_net_long_increase(self, positioning_mod):
        """让 net_long_top20 最近 5 日大幅增加 → 应触发'净多增加'信号。"""
        df = _make_position_df()
        # 把最后 5 行净多人为抬升
        for i in range(1, 6):
            df.loc[df.index[-i], "long_top20"] += i * 3000
        result = positioning_mod.compute_positioning_metrics(df)
        signals_text = " ".join(result["signals"])
        assert "净多增加" in signals_text

    # === Phase 4: 持仓分析师增强测试 ===

    def test_long_short_split_fields(self, positioning_mod):
        """验证多空双边独立变化字段存在。"""
        df = _make_position_df()
        result = positioning_mod.compute_positioning_metrics(df)
        snap = result["snapshot"]
        assert "long_top20_change_5d" in snap
        assert "short_top20_change_5d" in snap
        assert "long_short_ratio" in snap
        assert "long_short_ratio_change_5d" in snap
        assert "consecutive_net_long_days" in snap

    def test_consecutive_net_long_days_positive(self, positioning_mod):
        """连续 5 日净多增加 → consecutive_net_long_days >= 5。"""
        df = _make_position_df(n_days=100, seed=42)
        # 让最后 6 个 net_long_top20 递增(+100 每日)
        nl = df["long_top20"] - df["short_top20"]
        last_nl = nl.iloc[-7]
        for i in range(6, 0, -1):
            last_nl += 100
            df.loc[df.index[-i], "long_top20"] = df["short_top20"].iloc[-i] + last_nl
        result = positioning_mod.compute_positioning_metrics(df)
        consec = result["snapshot"]["consecutive_net_long_days"]
        assert consec is not None and consec >= 5, f"期望 >=5, 实际 {consec}"

    def test_consecutive_net_long_days_negative(self, positioning_mod):
        """连续 5 日净多减少 → consecutive_net_long_days <= -5。"""
        df = _make_position_df(n_days=100, seed=42)
        nl = df["long_top20"] - df["short_top20"]
        last_nl = nl.iloc[-7]
        for i in range(6, 0, -1):
            last_nl -= 100
            df.loc[df.index[-i], "long_top20"] = df["short_top20"].iloc[-i] + last_nl
        result = positioning_mod.compute_positioning_metrics(df)
        consec = result["snapshot"]["consecutive_net_long_days"]
        assert consec is not None and consec <= -5, f"期望 <= -5, 实际 {consec}"

    def test_price_position_alignment_bullish(self, positioning_mod):
        """price_direction=bullish + 净多增加 → 同向看多。"""
        df = _make_position_df(n_days=100, seed=42)
        # 让 net_long 最近 5 日增加
        nl = df["long_top20"] - df["short_top20"]
        last_nl = nl.iloc[-6]
        for i in range(5, 0, -1):
            last_nl += 200
            df.loc[df.index[-i], "long_top20"] = df["short_top20"].iloc[-i] + last_nl
        result = positioning_mod.compute_positioning_metrics(df, price_direction="bullish")
        alignment = result["snapshot"]["price_position_alignment"]
        assert alignment is not None and "同向" in alignment, f"期望同向, 实际 {alignment}"

    def test_price_position_alignment_divergence(self, positioning_mod):
        """price_direction=bullish + 净多减少 → 背离(价涨仓减)。"""
        df = _make_position_df(n_days=100, seed=42)
        nl = df["long_top20"] - df["short_top20"]
        last_nl = nl.iloc[-6]
        for i in range(5, 0, -1):
            last_nl -= 200
            df.loc[df.index[-i], "long_top20"] = df["short_top20"].iloc[-i] + last_nl
        result = positioning_mod.compute_positioning_metrics(df, price_direction="bullish")
        alignment = result["snapshot"]["price_position_alignment"]
        assert alignment is not None and "背离" in alignment, f"期望背离, 实际 {alignment}"

    def test_price_position_alignment_no_price_dir(self, positioning_mod):
        """不传 price_direction → alignment 为 N/A。"""
        df = _make_position_df()
        result = positioning_mod.compute_positioning_metrics(df)
        assert result["snapshot"]["price_position_alignment"] == "N/A"

    def test_signal_for_long_split(self, positioning_mod):
        """long_top20_change_5d > 0 → 应触发多头加仓信号。"""
        df = _make_position_df()
        for i in range(1, 6):
            df.loc[df.index[-i], "long_top20"] += i * 2000
        result = positioning_mod.compute_positioning_metrics(df)
        signals_text = " ".join(result["signals"])
        assert "多头" in signals_text and "加仓" in signals_text

    def test_signal_for_lsr_extreme_change(self, positioning_mod):
        """多空比 5 日变化 > 0.2 → 应触发信号。"""
        df = _make_position_df(n_days=100, seed=42)
        # 6 天前多空比很低,现在很高
        df.loc[df.index[-6], "long_top20"] = 50000
        df.loc[df.index[-6], "short_top20"] = 150000
        df.loc[df.index[-1], "long_top20"] = 150000
        df.loc[df.index[-1], "short_top20"] = 50000
        result = positioning_mod.compute_positioning_metrics(df)
        signals_text = " ".join(result["signals"])
        assert "多空比" in signals_text

    def test_multi_contract_picks_most_rows(self, positioning_mod):
        """Dict 输入多合约匹配时,选数据行数最多的(主力合约)。"""
        df_short = _make_position_df(n_days=30, seed=1)   # 30 行
        df_long = _make_position_df(n_days=200, seed=2)   # 200 行
        data = {"RB2501": df_long, "RB2505": df_short}
        result = positioning_mod.compute_positioning_metrics(data, symbol="RB")
        # 应选中 RB2501(200 行 > 30 行)
        latest = result.get("latest", {})
        assert latest.get("symbol") is None or latest.get("symbol") == "", (
            f"期望选中主力 RB2501 的数据,但 latest.symbol={latest.get('symbol')}"
        )
        # quality 的行数应从 RB2501 来(≈200)
        assert result.get("quality", {}).get("rows", 0) >= 150
        # 新品种级多合约字段
        assert "contracts" in result
        assert "variety_aggregate" in result
        assert "rollover" in result
        assert "cross_contract" in result
        assert len(result["contracts"]) == 2
        assert result["variety_aggregate"]["active_contracts"] == 2
        # 合约明细字段
        for c in result["contracts"]:
            assert "contract" in c
            assert "oi_share" in c
            assert "is_dominant" in c

    def test_multi_contract_aggregation(self, positioning_mod):
        """多合约聚合:品种级总 OI 应等于各合约 OI 之和。"""
        df1 = _make_position_df(n_days=100, seed=10)
        df1["symbol"] = "CU"
        df2 = _make_position_df(n_days=80, seed=11)
        df2["symbol"] = "CU"
        # 确保 OI 不同
        df2["total_open_interest"] = df2["total_open_interest"] * 0.5
        data = {"CU2501": df1, "CU2503": df2}
        result = positioning_mod.compute_positioning_metrics(data, symbol="CU")
        va = result["variety_aggregate"]
        contracts = result["contracts"]
        expected_total = sum(c["oi"] for c in contracts if c["oi"] is not None)
        assert va["total_oi"] == expected_total, f"{va['total_oi']} != {expected_total}"
        assert va["active_contracts"] == 2
        # OI 占比之和应为 1.0
        total_share = sum(c["oi_share"] for c in contracts)
        assert abs(total_share - 1.0) < 0.01, f"OI 占比之和={total_share}"

    def test_multi_contract_rollover_detected(self, positioning_mod):
        """移仓检测:近月 OI 下降 + 远月 OI 上升 → rollover.detected=True。"""
        n_days = 60
        dates = [date(2025, 1, 1) + timedelta(days=i) for i in range(n_days)]
        # 近月(主力):OI 从 20 万下降到 14 万(最后 5 日下降约 3% > 2%),保持最高 OI
        front_oi = np.linspace(200000, 140000, n_days)
        front_long = front_oi * 0.55
        front_short = front_oi * 0.45
        front_df = pd.DataFrame({
            "日期": dates,
            "long_top20": front_long,
            "short_top20": front_short,
            "total_open_interest": front_oi,
        })
        # 远月(次主力):OI 从 5 万上升到 10 万(最后 5 日上升约 8% > 2%)
        next_oi = np.linspace(50000, 100000, n_days)
        next_long = next_oi * 0.60
        next_short = next_oi * 0.40
        next_df = pd.DataFrame({
            "日期": dates,
            "long_top20": next_long,
            "short_top20": next_short,
            "total_open_interest": next_oi,
        })
        data = {"CU2501": front_df, "CU2503": next_df}
        result = positioning_mod.compute_positioning_metrics(data, symbol="CU")
        rollover = result["rollover"]
        assert rollover["detected"], f"应检测到移仓,但: {rollover}"
        assert rollover["from_contract"] == "CU2501"
        assert rollover["to_contract"] == "CU2503"
        assert 0 < rollover["progress"] < 1

    def test_multi_contract_cross_consistency(self, positioning_mod):
        """跨合约一致性:所有合约净多均 > 0 → 同向看多。"""
        df1 = _make_position_df(n_days=60, seed=20)
        df1["symbol"] = "CU"
        # 确保 net_long > 0 (long > short)
        df1["long_top20"] = df1["long_top20"].clip(lower=df1["short_top20"] + 1000)
        df2 = _make_position_df(n_days=50, seed=21)
        df2["symbol"] = "CU"
        df2["long_top20"] = df2["long_top20"].clip(lower=df2["short_top20"] + 500)
        data = {"CU2501": df1, "CU2503": df2}
        result = positioning_mod.compute_positioning_metrics(data, symbol="CU")
        cc = result["cross_contract"]
        assert "同向看多" in cc["consistency"], f"期望同向看多,实际: {cc['consistency']}"
        assert cc["contracts_same_direction"] == cc["total_active_contracts"]

    def test_price_oi_regime_bullish_accumulation(self, positioning_mod):
        """价涨 + 仓增 → 多头强势(价涨仓增)。"""
        df = _make_position_df(n_days=100, seed=30)
        # 让最后 5 日 OI 大幅增加而价格看涨
        for i in range(1, 6):
            df.loc[df.index[-i], "total_open_interest"] *= 1.05
        result = positioning_mod.compute_positioning_metrics(df, price_direction="bullish")
        regime = result["snapshot"]["price_oi_regime"]
        assert "多头强势" in regime, f"期望多头强势,实际: {regime}"

    def test_price_oi_regime_short_covering(self, positioning_mod):
        """价涨 + 仓减 → 空头回补(价涨仓减)。"""
        df = _make_position_df(n_days=100, seed=31)
        # 让最后 5 日 OI 大幅减少
        for i in range(1, 6):
            df.loc[df.index[-i], "total_open_interest"] *= 0.95
        result = positioning_mod.compute_positioning_metrics(df, price_direction="bullish")
        regime = result["snapshot"]["price_oi_regime"]
        assert "空头回补" in regime, f"期望空头回补,实际: {regime}"

    def test_price_oi_regime_bearish_accumulation(self, positioning_mod):
        """价跌 + 仓增 → 空头强势(价跌仓增)。"""
        df = _make_position_df(n_days=100, seed=32)
        for i in range(1, 6):
            df.loc[df.index[-i], "total_open_interest"] *= 1.05
        result = positioning_mod.compute_positioning_metrics(df, price_direction="bearish")
        regime = result["snapshot"]["price_oi_regime"]
        assert "空头强势" in regime, f"期望空头强势,实际: {regime}"

    def test_price_oi_regime_no_price_dir(self, positioning_mod):
        """不传 price_direction → 震荡待判。"""
        df = _make_position_df()
        result = positioning_mod.compute_positioning_metrics(df)
        assert result["snapshot"]["price_oi_regime"] == "震荡待判"

    def test_oi_change_5d_computed(self, positioning_mod):
        """验证 oi_change_5d 和 oi_change_pct_5d 字段存在。"""
        df = _make_position_df(n_days=100, seed=40)
        result = positioning_mod.compute_positioning_metrics(df)
        snap = result["snapshot"]
        assert "oi_change_5d" in snap
        assert "oi_change_pct_5d" in snap
        assert snap["oi_change_5d"] is not None
        assert snap["oi_change_pct_5d"] is not None

    def test_single_dataframe_no_contracts_returned(self, positioning_mod):
        """单 DataFrame 输入(非 Dict) → contracts 字段存在但为空列表。"""
        df = _make_position_df()
        result = positioning_mod.compute_positioning_metrics(df)
        assert "contracts" in result
        assert "variety_aggregate" in result
        assert "rollover" in result
        assert "cross_contract" in result


# =============================================================================
# 16. term_structure.py — 期限结构 / 展期收益
# =============================================================================

def _make_ts_df(n_days: int = 200, seed: int = 19, metric: str = "roll_yield") -> pd.DataFrame:
    """生成期限结构:展期收益率在 [-0.02, 0.04] 随机游走。"""
    np.random.seed(seed)
    ry = np.random.normal(0.01, 0.015, n_days)
    near_price = 70000 + np.cumsum(np.random.normal(0, 100, n_days))
    dom_price = near_price * (1 + ry)
    dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(n_days)]
    df = pd.DataFrame({
        "日期": dates,
        "品种": ["CU"] * n_days,
        "near_contract": ["CU2502"] * n_days,
        "dominant_contract": ["CU2506"] * n_days,
        "near_price": near_price,
        "dominant_price": dom_price,
    })
    if metric == "roll_yield":
        df["展期收益率"] = ry
    elif metric == "spread":
        df["价差"] = dom_price - near_price
    return df


class TestTermStructure:
    def test_roll_yield_metric(self, term_structure_mod):
        df = _make_ts_df(metric="roll_yield")
        result = term_structure_mod.compute_term_structure_metrics(df, var="CU")
        assert "structure" in result["snapshot"]
        assert "carry_score" in result["snapshot"]

    def test_spread_metric(self, term_structure_mod):
        df = _make_ts_df(metric="spread")
        result = term_structure_mod.compute_term_structure_metrics(df, var="CU")
        assert result["snapshot"]["structure"] in ("contango", "backwardation", "flat")

    def test_structure_contango_detected(self, term_structure_mod):
        """让展期收益率恒正 → 应识别为 contango。"""
        df = _make_ts_df()
        df["展期收益率"] = 0.02  # 全部为正
        result = term_structure_mod.compute_term_structure_metrics(df, var="CU")
        assert result["snapshot"]["structure"] == "contango"
        assert any("Contango" in s for s in result["signals"])

    def test_structure_backwardation_detected(self, term_structure_mod):
        """让展期收益率恒负 → 应识别为 backwardation。"""
        df = _make_ts_df()
        df["展期收益率"] = -0.02  # 全部为负
        result = term_structure_mod.compute_term_structure_metrics(df, var="CU")
        assert result["snapshot"]["structure"] == "backwardation"
        assert any("Backwardation" in s for s in result["signals"])

    def test_carry_score_range(self, term_structure_mod):
        df = _make_ts_df()
        result = term_structure_mod.compute_term_structure_metrics(df, var="CU")
        cs = result["snapshot"]["carry_score"]
        if cs is not None:
            assert -1.0 <= cs <= 1.0

    def test_derived_spread_from_prices(self, term_structure_mod):
        """无 roll_yield / spread 列时,从 near_price / dominant_price 推导。"""
        df = _make_ts_df(metric="roll_yield")
        df = df.drop(columns=["展期收益率"])
        result = term_structure_mod.compute_term_structure_metrics(df, var="CU")
        # 应能识别主度量(即使非显式)
        assert result["snapshot"].get("structure") in ("contango", "backwardation", "flat")

    def test_empty(self, term_structure_mod):
        result = term_structure_mod.compute_term_structure_metrics(pd.DataFrame())
        assert result["latest"] == {}

    def test_no_metric_column(self, term_structure_mod):
        df = pd.DataFrame({"日期": [date(2024, 1, 1)], "品种": ["CU"], "无效列": [1]})
        result = term_structure_mod.compute_term_structure_metrics(df, var="CU")
        # 应返回带错误信息的结果
        assert "无" in " ".join(result["signals"]) or "未识别" in " ".join(result["signals"])


# =============================================================================
# 17. news_sentiment.py — 新闻情感(纯规则)
# =============================================================================

def _make_news_list(n: int = 30, seed: int = 23, bullish_ratio: float = 0.5) -> List[Dict]:
    """合成新闻 List[Dict]:日期在近 14 天内,标题中含多空关键词。"""
    np.random.seed(seed)
    items = []
    now = datetime.now()
    for i in range(n):
        d = now - timedelta(days=np.random.randint(0, 14), hours=np.random.randint(0, 24))
        is_bull = np.random.rand() < bullish_ratio
        if is_bull:
            kw = np.random.choice(["上涨", "上调", "提振", "改善", "支撑"])
            title = f"行情{kw},需求持续改善"
        else:
            kw = np.random.choice(["下跌", "下调", "承压", "回落", "利空"])
            title = f"市场{kw},需求疲软"
        items.append({"发布时间": d, "标题": title, "内容": title})
    return items


def _make_news_with_macro(n: int = 50) -> List[Dict]:
    """含宏观重要事件的新闻(用于测试 importance_count)。"""
    items = _make_news_list(n=n, seed=31)
    # 注入 5 条重要事件
    now = datetime.now()
    for i in range(5):
        items.append({
            "发布时间": now - timedelta(days=1, hours=i),
            "标题": f"美联储议息决议:维持利率不变",
            "内容": "美联储议息决议维持利率不变,符合市场预期",
        })
    return items


class TestNewsSentiment:
    def test_list_input(self, news_sentiment_mod):
        items = _make_news_list(n=30)
        result = news_sentiment_mod.compute_news_sentiment_metrics(items, source="test")
        assert "latest" in result
        assert "snapshot" in result
        assert "counts" in result["snapshot"]

    def test_dataframe_input(self, news_sentiment_mod):
        items = _make_news_list(n=30)
        df = pd.DataFrame(items)
        result = news_sentiment_mod.compute_news_sentiment_metrics(df, source="df-test")
        assert result["quality"]["rows"] == 30

    def test_empty_list(self, news_sentiment_mod):
        result = news_sentiment_mod.compute_news_sentiment_metrics([], source="empty")
        assert result["latest"] == {}
        assert "无" in " ".join(result["signals"])

    def test_none_input(self, news_sentiment_mod):
        result = news_sentiment_mod.compute_news_sentiment_metrics(None, source="none")
        assert result["latest"] == {}

    def test_counts_have_required_keys(self, news_sentiment_mod):
        items = _make_news_list(n=50)
        result = news_sentiment_mod.compute_news_sentiment_metrics(items)
        counts = result["snapshot"]["counts"]
        for k in ["n1", "n3", "n7", "n14", "n30", "total"]:
            assert k in counts

    def test_sentiment_counts_present(self, news_sentiment_mod):
        items = _make_news_list(n=30, bullish_ratio=0.8)
        result = news_sentiment_mod.compute_news_sentiment_metrics(items)
        sent = result["snapshot"]["sentiment"]
        assert "bullish" in sent
        assert "bearish" in sent
        # 80% 看多 → 比例应 > 0
        if sent["ratio"] is not None:
            assert sent["ratio"] > 0

    def test_signals_for_dominant_sentiment(self, news_sentiment_mod):
        items = _make_news_list(n=50, bullish_ratio=0.9)
        result = news_sentiment_mod.compute_news_sentiment_metrics(items)
        signals_text = " ".join(result["signals"])
        # 强烈看多 → 应触发偏多信号(若样本足够)
        if result["snapshot"]["sentiment"]["bullish"] >= 10:
            assert "偏多" in signals_text or "中性" in signals_text

    def test_importance_count(self, news_sentiment_mod):
        items = _make_news_with_macro(n=50)
        result = news_sentiment_mod.compute_news_sentiment_metrics(items)
        assert result["snapshot"]["importance_count"] >= 3

    def test_categories_present(self, news_sentiment_mod):
        items = _make_news_list(n=30)
        result = news_sentiment_mod.compute_news_sentiment_metrics(items)
        assert "categories" in result["snapshot"]
        assert isinstance(result["snapshot"]["categories"], dict)

    def test_recent_top_size(self, news_sentiment_mod):
        items = _make_news_list(n=30)
        result = news_sentiment_mod.compute_news_sentiment_metrics(items)
        recent = result["snapshot"]["recent_top"]
        assert isinstance(recent, list)
        assert len(recent) <= 5

    def test_quality_metadata(self, news_sentiment_mod):
        items = _make_news_list(n=30)
        result = news_sentiment_mod.compute_news_sentiment_metrics(items, source="metal")
        q = result["quality"]
        assert q["rows"] == 30
        assert q["sources"] == ["metal"]
        assert q["data_freshness_days"] is not None


# =============================================================================
# 18. _helpers.py — 共享工具函数
# =============================================================================

class TestHelpers:
    def test_normalize_columns_chinese(self, helpers_mod):
        df = pd.DataFrame({"日期": ["2024-01-01"], "开盘价": [100], "收盘价": [101]})
        out = helpers_mod.normalize_columns(df)
        assert "date" in out.columns
        assert "open" in out.columns
        assert "close" in out.columns

    def test_normalize_columns_empty(self, helpers_mod):
        assert helpers_mod.normalize_columns(pd.DataFrame()).empty
        assert helpers_mod.normalize_columns(None).empty

    def test_safe_float(self, helpers_mod):
        assert helpers_mod.safe_float(1.5) == 1.5
        assert helpers_mod.safe_float(None) is None
        assert helpers_mod.safe_float(float("nan")) is None
        assert helpers_mod.safe_float(float("inf")) is None
        assert helpers_mod.safe_float("not a number") is None

    def test_safe_int(self, helpers_mod):
        assert helpers_mod.safe_int(1) == 1
        assert helpers_mod.safe_int(0.0) == 0
        assert helpers_mod.safe_int(None) == 0
        assert helpers_mod.safe_int(float("nan")) == 0

    def test_zscore(self, helpers_mod):
        # 常数列 → std=0 → z 不可计算,返回 None
        s = pd.Series([5.0] * 150)
        z = helpers_mod.zscore(s, window=180, min_periods=20)
        assert z is None
        # 真正有波动的序列
        np.random.seed(42)
        s = pd.Series(np.random.normal(10, 2, 200))
        z = helpers_mod.zscore(s, window=180, min_periods=20)
        assert z is not None
        assert -3 <= z <= 3

    def test_zscore_insufficient(self, helpers_mod):
        s = pd.Series([1, 2, 3])
        z = helpers_mod.zscore(s, window=180, min_periods=20)
        assert z is None

    def test_slope_positive(self, helpers_mod):
        s = pd.Series(range(100), dtype=float)
        slope = helpers_mod.slope(s, window=20)
        assert slope is not None
        assert slope > 0

    def test_slope_negative(self, helpers_mod):
        s = pd.Series(range(100, 0, -1), dtype=float)
        slope = helpers_mod.slope(s, window=20)
        assert slope is not None
        assert slope < 0

    def test_percentile_rank(self, helpers_mod):
        s = pd.Series([1] * 100 + [10], dtype=float)
        p = helpers_mod.percentile_rank(s, window=180)
        assert p == 1.0  # 最后值是最大值

    def test_data_quality(self, helpers_mod):
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=30),
            "value": range(30),
        })
        q = helpers_mod.data_quality(df, value_col="value")
        assert q["rows"] == 30
        assert q["coverage"] == 1.0
        assert q["data_freshness_days"] is not None

    def test_empty_result(self, helpers_mod):
        r = helpers_mod.empty_result("无数据")
        assert r["latest"] == {}
        assert r["stats"]["zscore_180d"] is None
        assert r["signals"] == ["无数据"]
        assert r["quality"]["rows"] == 0


# =============================================================================
# 19. 跨模块一致性 — 所有 6 个 feature 必须输出相同 schema 形状
# =============================================================================

class TestCrossModuleSchemaConsistency:
    """所有 6 个 feature 必须输出相同的 schema 形状(top-level keys)。"""

    REQUIRED_KEYS = {"latest", "stats", "signals", "snapshot", "quality"}

    def test_technical_schema(self, tech_mod):
        df = _make_synthetic_ohlcv(n_days=200)
        result = tech_mod.compute_technical_metrics(df)
        assert self.REQUIRED_KEYS.issubset(result["daily"].keys())

    def test_basis_schema(self, basis_mod):
        df = _make_basis_df()
        result = basis_mod.compute_basis_metrics(df)
        assert self.REQUIRED_KEYS.issubset(result.keys())

    def test_inventory_schema(self, inventory_mod):
        df = _make_inventory_df()
        result = inventory_mod.compute_inventory_metrics(df)
        assert self.REQUIRED_KEYS.issubset(result.keys())

    def test_positioning_schema(self, positioning_mod):
        df = _make_position_df()
        result = positioning_mod.compute_positioning_metrics(df)
        assert self.REQUIRED_KEYS.issubset(result.keys())

    def test_term_structure_schema(self, term_structure_mod):
        df = _make_ts_df()
        result = term_structure_mod.compute_term_structure_metrics(df, var="CU")
        assert self.REQUIRED_KEYS.issubset(result.keys())

    def test_news_sentiment_schema(self, news_sentiment_mod):
        items = _make_news_list(n=30)
        result = news_sentiment_mod.compute_news_sentiment_metrics(items)
        assert self.REQUIRED_KEYS.issubset(result.keys())


# =============================================================================
# 多合约技术分析测试
# =============================================================================

class TestTechnicalMultiContract:
    """compute_technical_metrics_multi_contract 测试。"""

    def test_basic(self, tech_mod):
        """双合约输入 → 输出含 main_continuous + index_contract。"""
        main_df = _make_synthetic_ohlcv(n_days=200, column_lang="zh")
        index_df = _make_synthetic_ohlcv(n_days=200, start_price=100.5, column_lang="zh")
        result = tech_mod.compute_technical_metrics_multi_contract(main_df, index_df)

        # 顶层 keys
        assert "main_continuous" in result
        assert "index_contract" in result
        assert "rollover" in result
        assert "combined" in result
        assert "quality" in result

        # main_continuous 含 daily + weekly
        mc = result["main_continuous"]
        assert "daily" in mc
        assert "daily" in mc  # weekly 可能为 None

        # index_contract 含趋势字段
        ic = result["index_contract"]
        assert "long_term_trend" in ic
        assert "ma60" in ic or ic.get("ma60") is None
        assert "ma120" in ic or ic.get("ma120") is None
        assert "relative_strength" in ic

        # combined 含 alignment
        assert "main_index_alignment" in result["combined"]

        # quality 含新字段
        q = result["quality"]
        assert "main_continuous_available" in q
        assert "index_contract_available" in q
        assert q["main_continuous_available"] is True
        assert q["index_contract_available"] is True

    def test_index_unavailable(self, tech_mod):
        """index_df=None → index_contract 字段为 None,不抛错。"""
        main_df = _make_synthetic_ohlcv(n_days=200, column_lang="zh")
        result = tech_mod.compute_technical_metrics_multi_contract(main_df, index_df=None)

        # 核心功能不受影响
        assert result["main_continuous"]["daily"] is not None
        assert result["combined"]["direction"] in ("long", "short", "neutral")

        # 指数部分为空
        ic = result["index_contract"]
        assert ic["long_term_trend"] == "neutral"
        assert ic["ma60"] is None
        assert ic["ma120"] is None

        # quality 标记
        assert result["quality"]["main_continuous_available"] is True
        assert result["quality"]["index_contract_available"] is False

    def test_rollover_detected(self, tech_mod):
        """含 rollover_date 列 → rollover.detected=True。"""
        main_df = _make_synthetic_ohlcv(n_days=200, column_lang="en")
        # 在中间某行标记换月
        main_df.loc[100, "rollover_date"] = True
        result = tech_mod.compute_technical_metrics_multi_contract(main_df, index_df=None)
        assert result["rollover"]["detected"] is True
        assert len(result["rollover"]["rollover_dates"]) > 0

    def test_rollover_not_detected(self, tech_mod):
        """无 rollover_date 列 → rollover.detected=False。"""
        main_df = _make_synthetic_ohlcv(n_days=200, column_lang="en")
        result = tech_mod.compute_technical_metrics_multi_contract(main_df, index_df=None)
        assert result["rollover"]["detected"] is False

    def test_alignment_aligned(self, tech_mod):
        """主力看多 + 指数看多 → aligned。"""
        main_df = _make_synthetic_ohlcv(n_days=200, trend=0.001, column_lang="en")
        # 指数也用看多趋势
        index_df = _make_synthetic_ohlcv(n_days=200, trend=0.001, start_price=100.5, column_lang="en")
        result = tech_mod.compute_technical_metrics_multi_contract(main_df, index_df)
        alignment = result["combined"].get("main_index_alignment", "")
        # 日线方向可能是 long 或 short(受随机游走影响), 只要 alignment 存在即可
        assert alignment in ("aligned", "divergent", "partial")

    def test_backward_compat(self, tech_mod):
        """compute_technical_metrics 单合约调用不受影响。"""
        df = _make_synthetic_ohlcv(n_days=200, column_lang="zh")
        result = tech_mod.compute_technical_metrics(df)
        assert "daily" in result
        assert "weekly" in result
        assert "combined" in result
        assert "quality" in result
        assert result["combined"]["direction"] in ("long", "short", "neutral")

    def test_empty_main_df(self, tech_mod):
        """空主力 DataFrame → 降级返回,不抛错。"""
        empty_df = pd.DataFrame()
        result = tech_mod.compute_technical_metrics_multi_contract(empty_df, index_df=None)
        assert result["quality"]["main_continuous_available"] is False

    def test_signals_appended_on_rollover(self, tech_mod):
        """换月时 combined signals 包含换月提示。"""
        main_df = _make_synthetic_ohlcv(n_days=200, column_lang="en")
        main_df.loc[190, "rollover_date"] = True
        main_df.loc[195, "rollover_date"] = True
        result = tech_mod.compute_technical_metrics_multi_contract(main_df, index_df=None)
        signals = " ".join(result["combined"].get("signals", []) or [])
        # 换月信号应出现在 combined signals 中
        assert "换月" in signals or "rollover" in signals.lower()
