"""
test_commodity_data_freshness_validator.py — 数据时效性修复回归测试

覆盖:
  - app.schemas.commodity_validators.validate_trade_date(P0-1)
  - app.routers.commodity.analysis._has_sufficient_coverage / _short_circuit_result(P0-2)
  - app.utils.commodity_trading_calendar.is_trading_day / trading_days_between / freshness_in_trading_days(P2-1)
  - tradingagents.agents.managers.investment_director.compute_risk_assessment 的 data_quality 维度(P1-2)
  - tradingagents.dataflows.providers.commodity.akshare_futures._filter_news_by_end_day(P1-1)
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytest


# =============================================================================
# P0-1: trade_date 校验器
# =============================================================================

class TestValidateTradeDate:
    """validate_trade_date:YYYY-MM-DD + 不晚于今天 + 不超过历史回测上限。"""

    def test_none_passes(self):
        from app.schemas.commodity_validators import validate_trade_date
        assert validate_trade_date(None) is None
        assert validate_trade_date("") is None

    def test_today_passes(self):
        from app.schemas.commodity_validators import validate_trade_date
        assert validate_trade_date(date.today().isoformat()) == date.today().isoformat()

    def test_recent_passes(self):
        from app.schemas.commodity_validators import validate_trade_date
        d = (date.today() - timedelta(days=10)).isoformat()
        assert validate_trade_date(d) == d

    def test_future_date_rejected(self):
        from app.schemas.commodity_validators import validate_trade_date
        with pytest.raises(ValueError, match="不能晚于今天"):
            validate_trade_date((date.today() + timedelta(days=1)).isoformat())

    def test_too_old_rejected(self):
        from app.schemas.commodity_validators import validate_trade_date
        # 默认 30 天上限
        d = (date.today() - timedelta(days=999)).isoformat()
        with pytest.raises(ValueError, match="历史回测范围"):
            validate_trade_date(d)

    def test_bad_format_rejected(self):
        from app.schemas.commodity_validators import validate_trade_date
        for bad in ["20990101", "2099/01/01", "not-a-date", "abcdefgh"]:
            with pytest.raises(ValueError, match="YYYY-MM-DD"):
                validate_trade_date(bad)

    def test_non_string_rejected(self):
        from app.schemas.commodity_validators import validate_trade_date
        with pytest.raises(ValueError):
            validate_trade_date(20260101)  # int 拒绝
        with pytest.raises(ValueError):
            validate_trade_date(["2026-01-01"])  # list 拒绝

    def test_max_backtest_days_env_override(self, monkeypatch):
        """环境变量 COMMODITY_MAX_BACKTEST_DAYS 应可调整上限。"""
        monkeypatch.setenv("COMMODITY_MAX_BACKTEST_DAYS", "5")
        # 重载模块
        import importlib
        import app.schemas.commodity_validators as mod
        importlib.reload(mod)
        try:
            d = (date.today() - timedelta(days=10)).isoformat()
            with pytest.raises(ValueError, match="5 天"):
                mod.validate_trade_date(d)
        finally:
            monkeypatch.delenv("COMMODITY_MAX_BACKTEST_DAYS", raising=False)
            importlib.reload(mod)

    def test_pydantic_integration(self):
        """验证 Pydantic 模型实际拒绝非法日期(模拟 422 行为)。"""
        from app.routers.commodity.analysis import AnalysisRequest
        for bad in ["2099-01-01", "not-a-date", (date.today() - timedelta(days=200)).isoformat()]:
            with pytest.raises(Exception):  # ValidationError
                AnalysisRequest(full_symbol="RB2501.SHF", trade_date=bad)


# =============================================================================
# P0-2: features 短路
# =============================================================================

class TestShortCircuit:
    """_has_sufficient_coverage 和 _short_circuit_result。"""

    def test_empty_features_rejected(self):
        from app.routers.commodity.analysis import _has_sufficient_coverage
        assert _has_sufficient_coverage({}) is False

    def test_all_rows_below_threshold_rejected(self):
        from app.routers.commodity.analysis import _has_sufficient_coverage
        features = {
            "technical": {"quality": {"rows": 10}},
            "positioning": {"quality": {"rows": 0}},
            "basis": {"quality": {"rows": 5}},
        }
        assert _has_sufficient_coverage(features) is False

    def test_one_core_module_meets_threshold(self):
        from app.routers.commodity.analysis import _has_sufficient_coverage
        for module in ("technical", "positioning", "basis", "inventory"):
            features = {module: {"quality": {"rows": 30}}}
            assert _has_sufficient_coverage(features) is True, f"failed for {module}"

    def test_non_core_module_only_rejected(self):
        """news_sentiment 不在核心 4 模块里,即使满足行数也不通过。"""
        from app.routers.commodity.analysis import _has_sufficient_coverage
        features = {"news_sentiment": {"quality": {"rows": 200}}}
        assert _has_sufficient_coverage(features) is False

    def test_malformed_quality_handled(self):
        """quality 字段缺失或非 dict 不崩溃。"""
        from app.routers.commodity.analysis import _has_sufficient_coverage
        assert _has_sufficient_coverage({"technical": {}}) is False
        assert _has_sufficient_coverage({"technical": {"quality": "not-a-dict"}}) is False
        assert _has_sufficient_coverage({"technical": {"quality": None}}) is False

    def test_short_circuit_result_shape(self):
        from app.routers.commodity.analysis import _short_circuit_result
        r = _short_circuit_result("RB2501.SHF", "2026-07-22", "no data", {})
        assert r["error"] == "DATA_UNAVAILABLE"
        assert r["trade_date"] == "2026-07-22"
        assert r["decision"]["action"] == "neutral"
        assert r["decision"]["confidence"] == 0.0
        assert "no data" in r["message"]
        assert "数据不可用" in r["market_report"]
        assert r["safety_override"]["applied"] is False


# =============================================================================
# P2-1: 期货交易日历
# =============================================================================

@pytest.fixture(autouse=True)
def _reset_holidays():
    """每个测试前后清空节假日,避免污染。"""
    from app.utils import commodity_trading_calendar as cal
    cal.clear_holidays()
    yield
    cal.clear_holidays()


class TestIsTradingDay:
    def test_weekday(self):
        from app.utils.commodity_trading_calendar import is_trading_day
        # 2026-07-20 是周一
        assert is_trading_day(date(2026, 7, 20)) is True

    def test_saturday(self):
        from app.utils.commodity_trading_calendar import is_trading_day
        assert is_trading_day(date(2026, 7, 25)) is False

    def test_sunday(self):
        from app.utils.commodity_trading_calendar import is_trading_day
        assert is_trading_day(date(2026, 7, 26)) is False

    def test_holiday_registered(self):
        from app.utils.commodity_trading_calendar import is_trading_day, register_holidays
        register_holidays([date(2026, 10, 1)])  # 国庆
        assert is_trading_day(date(2026, 10, 1)) is False


class TestTradingDaysBetween:
    """(start, end] 半开区间交易日数。"""

    def test_friday_to_monday(self):
        from app.utils.commodity_trading_calendar import trading_days_between
        # (7-17 fri, 7-20 mon]:只含 7-20 -> 1
        assert trading_days_between(date(2026, 7, 17), date(2026, 7, 20)) == 1

    def test_friday_to_tuesday(self):
        from app.utils.commodity_trading_calendar import trading_days_between
        # (7-17, 7-21]:含 7-20(mon) + 7-21(tue) -> 2
        assert trading_days_between(date(2026, 7, 17), date(2026, 7, 21)) == 2

    def test_same_day_zero(self):
        from app.utils.commodity_trading_calendar import trading_days_between
        assert trading_days_between(date(2026, 7, 20), date(2026, 7, 20)) == 0

    def test_inverted_zero(self):
        from app.utils.commodity_trading_calendar import trading_days_between
        assert trading_days_between(date(2026, 7, 21), date(2026, 7, 17)) == 0

    def test_holiday_subtracts(self):
        from app.utils.commodity_trading_calendar import trading_days_between, register_holidays
        register_holidays([date(2026, 7, 21)])  # 周二放假
        # (7-17, 7-22]:7-20(mon) + 7-22(wed) = 2(7-21 被排除)
        assert trading_days_between(date(2026, 7, 17), date(2026, 7, 22)) == 2


class TestFreshnessInTradingDays:
    """freshness_in_trading_days:用交易日替代日历日。"""

    def test_yesterday_trading_day_returns_one(self):
        from app.utils.commodity_trading_calendar import freshness_in_trading_days
        # 假设今天 2026-07-22 wed, last=2026-07-21 tue -> 1 个交易日
        d = freshness_in_trading_days(date(2026, 7, 21), date(2026, 7, 22))
        assert d == 1

    def test_last_friday_to_tuesday(self):
        from app.utils.commodity_trading_calendar import freshness_in_trading_days
        # 7-17 fri -> 7-21 tue:7-20(mon)+7-21(tue)=2
        assert freshness_in_trading_days(date(2026, 7, 17), date(2026, 7, 21)) == 2

    def test_string_input(self):
        from app.utils.commodity_trading_calendar import freshness_in_trading_days
        assert freshness_in_trading_days("2026-07-17", date(2026, 7, 21)) == 2
        assert freshness_in_trading_days("2026-07-17 10:00:00", date(2026, 7, 21)) == 2

    def test_today_today_zero(self):
        from app.utils.commodity_trading_calendar import freshness_in_trading_days
        assert freshness_in_trading_days(date(2026, 7, 22), date(2026, 7, 22)) == 0

    def test_invalid_returns_none(self):
        from app.utils.commodity_trading_calendar import freshness_in_trading_days
        assert freshness_in_trading_days("not-a-date", date(2026, 7, 22)) is None


# =============================================================================
# P1-2: data_freshness 接入风险等级
# =============================================================================

def _make_features(overall="fresh", stalest_days=1, stalest_module="technical"):
    return {
        "technical": {
            "quality": {"rows": 100, "coverage": 0.9, "data_freshness_days": 1},
            "combined": {"volatility": {"atr_ratio_pctl180": 0.30}, "oi_divergence": "confirm"},
        },
        "basis": {"quality": {"rows": 100, "coverage": 0.9, "data_freshness_days": 1}},
        "inventory": {"quality": {"rows": 100, "coverage": 0.9, "data_freshness_days": 1}},
        "positioning": {
            "quality": {"rows": 100, "coverage": 0.9, "data_freshness_days": 1},
            "snapshot": {"crowding_pctl_180d": 0.50},
        },
        "term_structure": {"quality": {"rows": 100, "coverage": 0.9, "data_freshness_days": 1}},
        "news_sentiment": {"quality": {"rows": 100, "coverage": 0.9, "data_freshness_days": 1}},
        "data_freshness": {
            "overall": overall,
            "stalest_module": stalest_module,
            "stalest_days": stalest_days,
        },
    }


class TestDataQualityDimension:
    """compute_risk_assessment 必须消费 features.data_freshness.overall。"""

    def test_fresh_is_r1(self):
        from tradingagents.agents.managers.investment_director import compute_risk_assessment
        r = compute_risk_assessment(_make_features("fresh", 1))
        dq = r["dimensions"]["data_quality"]
        assert dq["level"] == 1
        assert dq["value"] == "fresh"

    def test_acceptable_is_r2(self):
        from tradingagents.agents.managers.investment_director import compute_risk_assessment
        dq = compute_risk_assessment(_make_features("acceptable", 3))["dimensions"]["data_quality"]
        assert dq["level"] == 2

    def test_degraded_is_r3_medium_flag(self):
        from tradingagents.agents.managers.investment_director import compute_risk_assessment
        r = compute_risk_assessment(_make_features("degraded", 5))
        dq = r["dimensions"]["data_quality"]
        assert dq["level"] == 3
        flag = next((f for f in r["flags"] if f["name"] == "data_stale"), None)
        assert flag is not None
        assert flag["severity"] == "medium"

    def test_stale_is_r4_high_flag(self):
        from tradingagents.agents.managers.investment_director import compute_risk_assessment
        r = compute_risk_assessment(_make_features("stale", 14))
        dq = r["dimensions"]["data_quality"]
        assert dq["level"] == 4
        flag = next((f for f in r["flags"] if f["name"] == "data_stale"), None)
        assert flag is not None
        assert flag["severity"] == "high"

    def test_missing_data_freshness_is_unknown(self):
        from tradingagents.agents.managers.investment_director import compute_risk_assessment
        features = _make_features("fresh", 1)
        features.pop("data_freshness")
        dq = compute_risk_assessment(features)["dimensions"]["data_quality"]
        assert dq["level"] == 0
        assert dq["value"] == "unknown"


# =============================================================================
# P1-1: _filter_news_by_end_day
# =============================================================================

class TestFilterNewsByEndDay:
    def test_no_filter_when_none(self):
        from tradingagents.dataflows.providers.commodity.akshare_futures import (
            _filter_news_by_end_day,
        )
        items = [{"t": "A"}, {"t": "B"}]
        assert _filter_news_by_end_day(items, None) == items
        assert _filter_news_by_end_day(items, "") == items

    def test_filter_future_items(self):
        from tradingagents.dataflows.providers.commodity.akshare_futures import (
            _filter_news_by_end_day,
        )
        items = [
            {"published_at": "2026-07-20T10:00:00+08:00", "t": "A"},
            {"published_at": "2026-07-22T10:00:00+08:00", "t": "B"},
            {"published_at": "2026-07-23T10:00:00+08:00", "t": "C"},
            {"t": "D"},  # 无日期保留
            {"published_at": "", "t": "E"},  # 空日期保留
        ]
        out = _filter_news_by_end_day(items, "2026-07-22")
        assert [x["t"] for x in out] == ["A", "B", "D", "E"]

    def test_naive_timestamp_handled(self):
        """tz-naive 字符串也能正常过滤(归一化为 UTC 比较)。"""
        from tradingagents.dataflows.providers.commodity.akshare_futures import (
            _filter_news_by_end_day,
        )
        items = [{"published_at": "2026-07-22 10:00:00", "t": "X"}]
        assert _filter_news_by_end_day(items, "2026-07-22")[0]["t"] == "X"

    def test_invalid_end_day_returns_all(self):
        from tradingagents.dataflows.providers.commodity.akshare_futures import (
            _filter_news_by_end_day,
        )
        items = [{"published_at": "2026-07-23T10:00:00+08:00", "t": "X"}]
        assert _filter_news_by_end_day(items, "not-a-date") == items


# =============================================================================
# P1-1 副:features/__init__.py 把 data_staleness 传给 detect_signal_convergence
# =============================================================================

class TestSignalConvergenceDataStaleness:
    """detect_signal_convergence 应接受 data_staleness 参数(features/__init__.py 已传入)。"""

    def test_signal_convergence_accepts_staleness(self):
        from tradingagents.features.commodity.signal_convergence import detect_signal_convergence
        # 不传 data_staleness 仍兼容
        out = detect_signal_convergence({}, contract_warning=None)
        assert "convergences" in out

        # 传入 data_staleness 也兼容
        out2 = detect_signal_convergence(
            {},
            contract_warning=None,
            data_staleness={"technical": {"freshness_days": 14, "quality": "stale"}},
        )
        assert "convergences" in out2
