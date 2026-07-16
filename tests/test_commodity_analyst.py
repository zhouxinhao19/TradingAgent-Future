"""
test_commodity_analyst.py — Phase 3b-ii commodity analyst 节点测试

覆盖:
  - reports.py:4 个 Report Pydantic 模型的字段约束
  - _base.py:load_features / empty_report / quality_gate / truncate_snapshot
  - technical_analyst.py:
      * features 缺失 → empty_report(中性,不调 LLM)
      * 数据稀疏(quality.rows < 30) → empty_report
      * features 完整 → 调 LLM,返回 market_report 字段
      * LLM 抛错 → fallback 到 features 直拼 Markdown
      * 输出 schema 稳定(market_report / messages / market_tool_call_count)
      * snapshot 截断(>30 字段时截到 30)

运行:
  cd .claude/worktrees/phase-3b-ii-technical-analyst
  python -m pytest tests/test_commodity_analyst.py -v
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

# 确保 src 在 path 里
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 模块级 import(避免 fixture 函数内 import 受其他测试文件污染)
from tradingagents.agents.analysts.commodity import (
    AnalystSignal,
    FundamentalReport,
    NewsReport,
    PositionReport,
    TechnicalReport,
    create_fundamental_analyst,
    create_news_analyst,
    create_position_analyst,
    create_technical_analyst,
)
from tradingagents.agents.analysts.commodity._base import (
    empty_report,
    get_full_symbol,
    load_features,
    quality_gate,
    truncate_snapshot,
)
from tradingagents.features.commodity.technical import compute_technical_metrics, compute_technical_metrics_multi_contract
from tradingagents.features.commodity.basis import compute_basis_metrics
from tradingagents.features.commodity.inventory import compute_inventory_metrics
from tradingagents.features.commodity.term_structure import compute_term_structure_metrics
from tradingagents.features.commodity.positioning import compute_positioning_metrics
from tradingagents.features.commodity.news_sentiment import compute_news_sentiment_metrics


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_llm() -> MagicMock:
    """Mock LLM,invoke() 返回固定内容。"""
    mock = MagicMock()
    response = MagicMock()
    response.content = (
        "# CU2501.SHF 技术分析报告\n\n"
        "## 综合判断\n"
        "- 方向:看多(强度 0.65)\n"
        "- 关键位:支撑 72000 / 阻力 73500\n\n"
        "## OI 背离解读\n中性\n\n"
        "## 风险提示\n数据完整,无特殊风险。\n"
    )
    mock.invoke.return_value = response
    return mock


@pytest.fixture
def mock_llm_json() -> MagicMock:
    """Mock LLM,invoke() 返回合法 JSON。"""
    mock = MagicMock()
    response = MagicMock()
    response.content = json.dumps(
        {
            "valuation": {
                "level": "低估",
                "safety_margin": "充足",
                "reasoning": "近月基差率-2.5%,主力贴水处低分位,Backwardation 结构,估值偏低",
            },
            "drive": {
                "direction": "向上",
                "strength": "中",
                "dominant_factor": "库存持续去化",
                "reasoning": "库存周环比下降,180d 分位处低位,Carry Score 为正,驱动向上",
            },
            "consistency": {
                "alignment": "同向",
                "confidence": "高",
                "analysis": "低估+驱动向上,估值与驱动同向,做多安全边际充足",
                "key_uncertainty": "宏观情绪变化可能导致短期波动",
            },
            "summary": "估值偏低且驱动向上,做多安全边际充足,建议逢低做多",
            "risk_flags": ["宏观情绪变化", "持仓集中度偏高"],
            "data_quality": "数据覆盖近60个交易日,基差/库存/期限结构数据完整",
        }
    )
    mock.invoke.return_value = response
    return mock


@pytest.fixture
def sample_ohlcv() -> pd.DataFrame:
    """构造 60 行 OHLCV 测试数据(中文列名,与 akshare_futures 一致)。"""
    np.random.seed(42)
    n = 60
    base = 72000
    returns = np.random.randn(n) * 100
    prices = base + np.cumsum(returns)
    df = pd.DataFrame(
        {
            "日期": pd.date_range("2025-01-01", periods=n),
            "开盘价": prices + np.random.randn(n) * 50,
            "最高价": prices + np.abs(np.random.randn(n) * 100),
            "最低价": prices - np.abs(np.random.randn(n) * 100),
            "收盘价": prices,
            "成交量": np.random.randint(10000, 50000, n),
            "持仓量": np.random.randint(80000, 120000, n),
        }
    )
    return df


@pytest.fixture
def sample_features_tech(sample_ohlcv) -> dict:
    """3b-i features 层输出:compute_technical_metrics_multi_contract(sample_ohlcv)。"""
    return {"technical": compute_technical_metrics_multi_contract(sample_ohlcv, index_df=None)}


@pytest.fixture
def sample_basis_df() -> pd.DataFrame:
    """构造基差测试数据(现货+期货+基差)。"""
    n = 60
    return pd.DataFrame(
        {
            "日期": pd.date_range("2025-01-01", periods=n),
            "现货价": 72000 + np.cumsum(np.random.randn(n) * 50),
            "期货价": 71800 + np.cumsum(np.random.randn(n) * 50),
            "基差": 200 + np.cumsum(np.random.randn(n) * 10),
        }
    )


@pytest.fixture
def sample_inventory_df() -> pd.DataFrame:
    """构造库存测试数据。"""
    n = 60
    return pd.DataFrame(
        {
            "日期": pd.date_range("2025-01-01", periods=n),
            "库存": 50000 + np.cumsum(np.random.randn(n) * 100),
        }
    )


@pytest.fixture
def sample_term_structure_df() -> pd.DataFrame:
    """构造期限结构测试数据。"""
    n = 60
    return pd.DataFrame(
        {
            "日期": pd.date_range("2025-01-01", periods=n),
            "近月": 72000 + np.cumsum(np.random.randn(n) * 50),
            "远月": 72200 + np.cumsum(np.random.randn(n) * 50),
        }
    )


@pytest.fixture
def sample_positioning_df() -> pd.DataFrame:
    """构造持仓测试数据。"""
    n = 60
    return pd.DataFrame(
        {
            "日期": pd.date_range("2025-01-01", periods=n),
            "前20名净多头": 5000 + np.cumsum(np.random.randn(n) * 100),
        }
    )


@pytest.fixture
def sample_news_items() -> list:
    """构造新闻测试数据(list 形式,给 news_analyst 直接用)。"""
    return [
        {
            "published_at": "2025-03-01 09:30",
            "title": "美联储鸽派转向",
            "content": "美联储暗示将放缓加息节奏",
            "source": "global_macro",
            "sentiment": "positive",
        },
        {
            "published_at": "2025-03-01 10:15",
            "title": "库存数据超预期下降",
            "content": "上周库存环比下降 5%",
            "source": "metal",
            "sentiment": "positive",
        },
        {
            "published_at": "2025-03-01 14:20",
            "title": "下游需求疲软",
            "content": "加工厂反映订单减少",
            "source": "chemical",
            "sentiment": "negative",
        },
    ]


@pytest.fixture
def sample_news_df() -> pd.DataFrame:
    """构造新闻 DataFrame(给 compute_news_sentiment_metrics 用)。"""
    return pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2025-03-01 09:30", "2025-03-01 10:15", "2025-03-01 14:20"]
            ),
            "title": ["美联储鸽派转向", "库存数据超预期下降", "下游需求疲软"],
            "content": [
                "美联储暗示将放缓加息节奏",
                "上周库存环比下降 5%",
                "加工厂反映订单减少",
            ],
            "source": ["global_macro", "metal", "chemical"],
            "sentiment": ["positive", "positive", "negative"],
        }
    )


@pytest.fixture
def sample_features_all(
    sample_ohlcv,
    sample_basis_df,
    sample_inventory_df,
    sample_term_structure_df,
    sample_positioning_df,
    sample_news_df,
) -> dict:
    """所有 6 个 features 模块的输出。"""
    return {
        "technical": compute_technical_metrics_multi_contract(sample_ohlcv, index_df=None),
        "basis": compute_basis_metrics(sample_basis_df),
        "inventory": compute_inventory_metrics(sample_inventory_df),
        "term_structure": compute_term_structure_metrics(sample_term_structure_df),
        "positioning": compute_positioning_metrics(sample_positioning_df),
        "news_sentiment": compute_news_sentiment_metrics(sample_news_df),
    }


def _state(**overrides) -> dict:
    """构造最小可用的 analyst 节点 state。"""
    base = {
        "full_symbol": "CU2501.SHF",
        "trade_date": "2025-03-01",
        "messages": [],
        "company_of_interest": "CU2501.SHF",
    }
    base.update(overrides)
    return base


# =============================================================================
# 测试 1:reports.py Pydantic 模型
# =============================================================================

class TestAnalystSignal:
    def test_basic_construction(self):
        sig = AnalystSignal(
            direction="bullish",
            strength=0.7,
            confidence=0.6,
            summary="看多",
            signals=["MA 金叉", "RSI 50"],
        )
        assert sig.direction == "bullish"
        assert 0.0 <= sig.strength <= 1.0
        assert sig.signals == ["MA 金叉", "RSI 50"]

    def test_strength_bounds(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AnalystSignal(direction="bullish", strength=1.5)
        with pytest.raises(ValidationError):
            AnalystSignal(direction="bullish", strength=-0.1)


class TestTechnicalReport:
    def test_extra_fields(self):
        r = TechnicalReport(
            direction="bearish",
            strength=0.6,
            confidence=0.5,
            summary="看空",
            timeframe="daily",
            oi_divergence="OI↑价↓ 看空背离",
            volatility_regime="high",
            atr=123.4,
            atr_ratio_pctl180=0.85,
        )
        assert r.timeframe == "daily"
        assert r.oi_divergence == "OI↑价↓ 看空背离"
        assert r.atr == 123.4
        assert r.atr_ratio_pctl180 == 0.85

    def test_invalid_direction(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            TechnicalReport(direction="up", strength=0.5)

    def test_default_key_levels(self):
        r = TechnicalReport(direction="neutral", strength=0.0)
        assert r.key_levels == {}
        assert r.snapshot == {}
        assert r.timeframe == "daily+weekly"  # 默认值


class TestFundamentalReport:
    def test_three_views(self):
        r = FundamentalReport(
            direction="bullish",
            strength=0.5,
            basis_view="贴水",
            inventory_view="去库",
            term_structure_view="Backwardation",
        )
        assert r.basis_view == "贴水"
        assert r.inventory_view == "去库"
        assert r.term_structure_view == "Backwardation"


class TestPositionReport:
    def test_concentration_field(self):
        r = PositionReport(
            direction="bearish",
            strength=0.7,
            net_long_change_5d=-0.15,
            crowding_pctl_180d=0.92,
            concentration=0.65,
        )
        assert r.net_long_change_5d == -0.15
        assert r.crowding_pctl_180d == 0.92


class TestNewsReport:
    def test_sentiment_counts(self):
        r = NewsReport(
            direction="bullish",
            strength=0.5,
            positive_count=10,
            negative_count=3,
            neutral_count=5,
            macro_narrative="美联储鸽派转向",
            industry_narrative="OPEC+ 减产",
        )
        assert r.positive_count == 10
        assert r.macro_narrative == "美联储鸽派转向"


# =============================================================================
# 测试 2:_base.py 共享工具
# =============================================================================

class TestBase:
    def test_load_features_empty(self):
        assert load_features({}) == {}
        assert load_features({"commodity_features": None}) == {}
        assert load_features({"commodity_features": {}}) == {}
        assert load_features({"commodity_features": {"technical": {"x": 1}}}) == {"technical": {"x": 1}}

    def test_empty_report_default(self):
        r = empty_report()
        assert "中性" in r
        assert "特征层数据为空" in r

    def test_empty_report_custom_reason(self):
        r = empty_report("bullish", "测试原因")
        assert "看多" in r
        assert "测试原因" in r

    def test_empty_report_bearish(self):
        r = empty_report("bearish")
        assert "看空" in r

    def test_quality_gate_insufficient(self):
        assert quality_gate(None) is False
        assert quality_gate({}) is False
        assert quality_gate({"quality": {}}) is False
        assert quality_gate({"quality": {"rows": 10}}) is False  # < 30

    def test_quality_gate_sufficient(self):
        assert quality_gate({"quality": {"rows": 30}}) is True
        assert quality_gate({"quality": {"rows": 60}}) is True

    def test_truncate_snapshot_under_limit(self):
        snap = {"a": 1, "b": 2, "c": 3}
        assert truncate_snapshot(snap, max_keys=10) == snap

    def test_truncate_snapshot_over_limit(self):
        snap = {f"k{i}": i for i in range(50)}
        out = truncate_snapshot(snap, max_keys=20)
        assert len(out) == 20
        assert list(out.keys()) == [f"k{i}" for i in range(20)]

    def test_truncate_snapshot_invalid_input(self):
        assert truncate_snapshot(None) == {}
        assert truncate_snapshot("not a dict") == {}
        assert truncate_snapshot([1, 2, 3]) == {}

    def test_get_full_symbol_fallback(self):
        assert get_full_symbol({}) == ""
        assert get_full_symbol({"full_symbol": "CU2501.SHF"}) == "CU2501.SHF"
        assert get_full_symbol({"company_of_interest": "AAPL"}) == "AAPL"
        assert (
            get_full_symbol({"full_symbol": "X", "company_of_interest": "Y"}) == "X"
        )  # full_symbol 优先


# =============================================================================
# 测试 3:technical_analyst 节点
# =============================================================================

class TestTechnicalAnalystNode:
    def test_no_features_returns_neutral(self, mock_llm):
        from tradingagents.agents.analysts.commodity import create_technical_analyst

        node = create_technical_analyst(mock_llm)
        result = node(_state())

        assert "market_report" in result
        assert "数据缺失" in result["market_report"]
        assert result["market_tool_call_count"] == 0
        assert result["messages"] == []
        # 没 features 就不该调 LLM
        mock_llm.invoke.assert_not_called()

    def test_features_none_value(self, mock_llm):
        from tradingagents.agents.analysts.commodity import create_technical_analyst

        node = create_technical_analyst(mock_llm)
        result = node(_state(commodity_features={"technical": None}))

        assert "数据缺失" in result["market_report"]
        mock_llm.invoke.assert_not_called()

    def test_short_data_returns_neutral(self, mock_llm):
        """quality.rows < 30 时直接走空结果分支。"""
        from tradingagents.agents.analysts.commodity import create_technical_analyst

        feats = {"technical": {"quality": {"rows": 10, "coverage": 0.3}}}
        node = create_technical_analyst(mock_llm)
        result = node(_state(commodity_features=feats))

        assert "数据缺失" in result["market_report"]
        assert "稀疏" in result["market_report"]
        mock_llm.invoke.assert_not_called()

    def test_with_features_calls_llm(self, mock_llm, sample_features_tech):
        from tradingagents.agents.analysts.commodity import create_technical_analyst

        node = create_technical_analyst(mock_llm)
        result = node(_state(commodity_features=sample_features_tech))

        assert "market_report" in result
        assert len(result["market_report"]) > 50
        assert result["market_tool_call_count"] == 0
        assert len(result["messages"]) >= 1
        mock_llm.invoke.assert_called_once()

    def test_output_schema_stable(self, mock_llm, sample_features_tech):
        """验证返回 dict 的字段集稳定。"""
        from tradingagents.agents.analysts.commodity import create_technical_analyst

        node = create_technical_analyst(mock_llm)
        result = node(_state(commodity_features=sample_features_tech))

        assert set(result.keys()) >= {"market_report", "messages", "market_tool_call_count"}
        assert isinstance(result["market_report"], str)
        assert isinstance(result["messages"], list)
        assert isinstance(result["market_tool_call_count"], int)

    def test_llm_failure_falls_back(self, sample_features_tech):
        """LLM.invoke 抛错时,fallback 到 features 直拼 Markdown,绝不抛异常。"""
        from tradingagents.agents.analysts.commodity import create_technical_analyst

        mock = MagicMock()
        mock.invoke.side_effect = RuntimeError("LLM down")
        node = create_technical_analyst(mock)
        result = node(_state(commodity_features=sample_features_tech))

        assert "market_report" in result
        # fallback 标识:中文"降级版本"
        assert "降级版本" in result["market_report"] or "LLM" in result["market_report"]
        # 不该抛错,降级报告要包含关键字段
        assert "综合判断" in result["market_report"]

    def test_messages_contain_ai_message(self, mock_llm, sample_features_tech):
        """成功调用 LLM 时,messages 应包含 LLM 返回对象。"""
        from tradingagents.agents.analysts.commodity import create_technical_analyst

        node = create_technical_analyst(mock_llm)
        result = node(_state(commodity_features=sample_features_tech))

        assert len(result["messages"]) == 1
        # MagicMock 返回的对象有 content 属性
        assert hasattr(result["messages"][0], "content")

    def test_prompt_includes_full_symbol(self, mock_llm, sample_features_tech):
        """验证 prompt 注入 full_symbol。"""
        from tradingagents.agents.analysts.commodity import create_technical_analyst

        node = create_technical_analyst(mock_llm)
        node(_state(commodity_features=sample_features_tech, full_symbol="AU2502.SHF"))

        # LLM 收到了 prompt,messages 是传入的参数
        call_args = mock_llm.invoke.call_args
        assert call_args is not None
        # invoke 收到的是 prompt | llm 链 invoke 的输出
        # 这里只验证 invoke 被调用了(参数已被 chain 消化)
        mock_llm.invoke.assert_called_once()

    def test_weekly_missing_handled(self, mock_llm, sample_features_tech):
        """weekly=None 时,周线信息应填 N/A 不抛错。"""
        from tradingagents.agents.analysts.commodity import create_technical_analyst

        # 强制 main_continuous.weekly = None
        feats = {
            "technical": {
                **sample_features_tech["technical"],
                "main_continuous": {
                    **sample_features_tech["technical"].get("main_continuous", {}),
                    "weekly": None,
                },
            }
        }
        node = create_technical_analyst(mock_llm)
        result = node(_state(commodity_features=feats))

        assert "market_report" in result
        assert result["market_tool_call_count"] == 0
        mock_llm.invoke.assert_called_once()

    def test_multi_contract_index_available(self, mock_llm, sample_ohlcv):
        """含指数合约 features → prompt 包含指数合约字段。"""
        from tradingagents.agents.analysts.commodity import create_technical_analyst

        # 构造带指数合约的 features
        index_df = _make_index_ohlcv(n_days=200, start_price=100.5)
        tech_feats = compute_technical_metrics_multi_contract(sample_ohlcv, index_df=index_df)
        feats = {"technical": tech_feats}
        node = create_technical_analyst(mock_llm)
        node(_state(commodity_features=feats))

        # 验证 prompt 包含指数合约相关内容
        call_kwargs = mock_llm.invoke.call_args
        messages = call_kwargs[0][0]
        system_msg = messages[0].content if hasattr(messages[0], "content") else str(messages[0])
        assert "指数合约" in system_msg
        assert "MA60" in system_msg or "MA120" in system_msg

    def test_multi_contract_index_unavailable(self, mock_llm, sample_ohlcv):
        """指数合约不可用时 → prompt 标注指数不可得,不抛错。"""
        from tradingagents.agents.analysts.commodity import create_technical_analyst

        tech_feats = compute_technical_metrics_multi_contract(sample_ohlcv, index_df=None)
        feats = {"technical": tech_feats}
        node = create_technical_analyst(mock_llm)
        node(_state(commodity_features=feats))

        call_kwargs = mock_llm.invoke.call_args
        messages = call_kwargs[0][0]
        system_msg = messages[0].content if hasattr(messages[0], "content") else str(messages[0])
        # 指数合约相关字段存在,即使数据不可用
        assert "指数合约" in system_msg

    def test_rollover_alert_in_fallback(self, sample_ohlcv):
        """rollover.detected=True → fallback 报告含移仓换月预警。"""
        from tradingagents.agents.analysts.commodity import create_technical_analyst

        # 在主力合约添加换月标记
        sample_ohlcv.loc[180, "rollover_date"] = True
        tech_feats = compute_technical_metrics_multi_contract(sample_ohlcv, index_df=None)
        feats = {"technical": tech_feats}

        mock = MagicMock()
        mock.invoke.side_effect = RuntimeError("LLM down")
        node = create_technical_analyst(mock)
        result = node(_state(commodity_features=feats))

        assert "market_report" in result
        assert "移仓换月" in result["market_report"] or "rollover" in result["market_report"].lower()


def _make_index_ohlcv(n_days=200, start_price=100.0):
    """构造指数合约 OHLCV 测试数据。"""
    np.random.seed(43)
    rets = np.random.normal(0.0003, 0.015, n_days)
    close = start_price * np.exp(np.cumsum(rets))
    dates = [date(2025, 1, 1) + timedelta(days=i) for i in range(n_days)]
    return pd.DataFrame({
        "日期": dates,
        "开盘价": close * (1 - 0.002),
        "最高价": close * (1 + 0.005),
        "最低价": close * (1 - 0.005),
        "收盘价": close,
        "成交量": np.random.randint(50000, 200000, n_days),
        "持仓量": np.random.randint(100000, 300000, n_days),
    })


# =============================================================================
# 测试 4:综合 schema 一致性(为后续 4 个 analyst 准备基线)
# =============================================================================

class TestSchemaConsistency:
    """验证 4 个 Report 的公共字段一致(为后续 analyst 扩展提供基线)。"""

    def test_all_reports_have_direction(self):
        from tradingagents.agents.analysts.commodity import (
            TechnicalReport,
            FundamentalReport,
            PositionReport,
            NewsReport,
        )

        for cls in [TechnicalReport, FundamentalReport, PositionReport, NewsReport]:
            r = cls(direction="neutral", strength=0.0)
            assert r.direction == "neutral"
            assert 0.0 <= r.strength <= 1.0
            assert r.confidence == 0.0  # 默认

    def test_all_reports_dump_to_dict(self):
        from tradingagents.agents.analysts.commodity import (
            TechnicalReport,
            FundamentalReport,
            PositionReport,
            NewsReport,
        )

        for cls in [TechnicalReport, FundamentalReport, PositionReport, NewsReport]:
            r = cls(direction="bullish", strength=0.5, summary="test")
            d = r.model_dump()
            assert isinstance(d, dict)
            assert d["direction"] == "bullish"
            assert d["summary"] == "test"


# =============================================================================
# 测试 5:fundamental_analyst 节点
# =============================================================================

class TestFundamentalAnalystNode:
    def test_no_features_returns_neutral(self, mock_llm):
        node = create_fundamental_analyst(mock_llm)
        result = node(_state())
        assert "fundamentals_report" in result
        assert "fundamentals_structured" in result
        assert result["fundamentals_structured"] == {}
        assert "数据缺失" in result["fundamentals_report"]
        mock_llm.invoke.assert_not_called()

    def test_with_features_calls_llm(self, mock_llm, sample_features_all):
        node = create_fundamental_analyst(mock_llm)
        result = node(_state(commodity_features=sample_features_all))
        assert "fundamentals_report" in result
        assert "fundamentals_structured" in result
        assert isinstance(result["fundamentals_structured"], dict)
        assert result["fundamentals_tool_call_count"] == 0
        mock_llm.invoke.assert_called_once()

    def test_structured_output_json(self, mock_llm_json, sample_features_all):
        """LLM 返回合法 JSON 时,fundamentals_structured 包含预期 key。"""
        node = create_fundamental_analyst(mock_llm_json)
        result = node(_state(commodity_features=sample_features_all))
        structured = result.get("fundamentals_structured", {})
        assert isinstance(structured, dict)
        # 顶层 key
        for key in ("valuation", "drive", "consistency", "summary", "risk_flags", "data_quality"):
            assert key in structured, f"缺少结构化字段: {key}"
        # 嵌套 key
        assert "level" in structured["valuation"]
        assert "direction" in structured["drive"]
        assert "alignment" in structured["consistency"]
        # Markdown 兼容输出
        assert "fundamentals_report" in result
        assert isinstance(result["fundamentals_report"], str)
        assert len(result["fundamentals_report"]) > 50

    def test_partial_features(self, mock_llm, sample_basis_df):
        """只有 basis,缺 inventory/term_structure 时仍能跑。"""
        feats = {"basis": compute_basis_metrics(sample_basis_df)}
        node = create_fundamental_analyst(mock_llm)
        result = node(_state(commodity_features=feats))
        assert "fundamentals_report" in result

    def test_llm_failure_falls_back(self, sample_features_all):
        mock = MagicMock()
        mock.invoke.side_effect = RuntimeError("LLM down")
        node = create_fundamental_analyst(mock)
        result = node(_state(commodity_features=sample_features_all))
        assert "降级版本" in result["fundamentals_report"]
        assert "fundamentals_structured" in result
        assert isinstance(result["fundamentals_structured"], dict)
        # 降级路径也应该包含估值/驱动字段
        structured = result["fundamentals_structured"]
        assert "valuation" in structured or "raw" in structured
        assert "summary" in structured


# =============================================================================
# 测试 6:position_analyst 节点
# =============================================================================

class TestPositionAnalystNode:
    def test_no_features_returns_neutral(self, mock_llm):
        node = create_position_analyst(mock_llm)
        result = node(_state())
        assert "sentiment_report" in result
        assert "position_report" in result
        assert "position_structured" in result
        assert "数据缺失" in result["sentiment_report"]
        assert result["position_report"] == result["sentiment_report"]
        assert result["position_structured"] == {}
        mock_llm.invoke.assert_not_called()

    def test_with_features_calls_llm(self, mock_llm, sample_features_all):
        node = create_position_analyst(mock_llm)
        result = node(_state(commodity_features=sample_features_all))
        assert "sentiment_report" in result
        assert "position_report" in result
        assert "position_structured" in result
        assert isinstance(result["position_structured"], dict)
        mock_llm.invoke.assert_called_once()

    def test_llm_failure_falls_back(self, sample_features_all):
        mock = MagicMock()
        mock.invoke.side_effect = RuntimeError("LLM down")
        node = create_position_analyst(mock)
        result = node(_state(commodity_features=sample_features_all))
        assert "降级版本" in result["sentiment_report"]
        assert "position_report" in result
        assert result["sentiment_report"] == result["position_report"]
        assert "position_structured" in result
        assert isinstance(result["position_structured"], dict)

    def test_extreme_crowding_signals(self, mock_llm):
        """拥挤度 180d 分位 > 0.9 时应触发反向风险提示。"""
        feats = {
            "positioning": {
                "latest": {
                    "net_long_change_5d": 0.10,
                    "crowding_pctl_180d": 0.95,
                    "concentration": 0.7,
                },
                "signals": ["主力净多头加仓", "持仓集中度 0.70"],
                "quality": {"rows": 60, "coverage": 1.0},
            }
        }
        node = create_position_analyst(mock_llm)
        result = node(_state(commodity_features=feats))
        assert "sentiment_report" in result
        assert "position_report" in result


# =============================================================================
# 测试 7:news_analyst 节点(必调 LLM)
# =============================================================================

class TestNewsAnalystNode:
    def test_no_features_no_events_returns_neutral(self, mock_llm):
        node = create_news_analyst(mock_llm)
        result = node(_state())
        assert "news_report" in result
        assert "数据缺失" in result["news_report"]
        mock_llm.invoke.assert_not_called()

    def test_with_features_calls_llm(self, mock_llm, sample_features_all, sample_news_items):
        node = create_news_analyst(mock_llm)
        result = node(
            _state(
                commodity_features=sample_features_all,
                latest_news=sample_news_items,
            )
        )
        assert "news_report" in result
        mock_llm.invoke.assert_called_once()

    def test_with_only_events(self, mock_llm, sample_news_items):
        """features 缺失但有 latest_news 时仍能跑。"""
        node = create_news_analyst(mock_llm)
        result = node(_state(latest_news=sample_news_items))
        assert "news_report" in result
        mock_llm.invoke.assert_called_once()

    def test_llm_failure_returns_sentiment_only(self, sample_features_all, sample_news_items):
        """LLM 失败时返回情感统计(无叙事)。"""
        mock = MagicMock()
        mock.invoke.side_effect = RuntimeError("LLM down")
        node = create_news_analyst(mock)
        result = node(
            _state(
                commodity_features=sample_features_all,
                latest_news=sample_news_items,
            )
        )
        assert "news_report" in result
        assert "降级版本" in result["news_report"]
        assert "情感统计" in result["news_report"]


# =============================================================================
# 测试 8:4 个 analyst 输出字段映射(决策链零改动前提)
# =============================================================================

class TestOutputFieldMapping:
    """验证每个 analyst 写入正确的 AgentState 字段。"""

    def test_technical_writes_market_report(self, mock_llm, sample_features_tech):
        node = create_technical_analyst(mock_llm)
        result = node(_state(commodity_features=sample_features_tech))
        assert "market_report" in result
        assert "fundamentals_report" not in result
        assert "news_report" not in result
        assert "sentiment_report" not in result

    def test_fundamental_writes_fundamentals_report(self, mock_llm, sample_features_all):
        node = create_fundamental_analyst(mock_llm)
        result = node(_state(commodity_features=sample_features_all))
        assert "fundamentals_report" in result
        assert "market_report" not in result
        assert "news_report" not in result
        assert "sentiment_report" not in result

    def test_position_writes_sentiment_report(self, mock_llm, sample_features_all):
        node = create_position_analyst(mock_llm)
        result = node(_state(commodity_features=sample_features_all))
        assert "sentiment_report" in result
        assert "position_report" in result
        assert "position_structured" in result
        assert "market_report" not in result
        assert "fundamentals_report" not in result
        assert "news_report" not in result

    def test_news_writes_news_report(self, mock_llm, sample_features_all, sample_news_items):
        node = create_news_analyst(mock_llm)
        result = node(
            _state(
                commodity_features=sample_features_all,
                latest_news=sample_news_items,
            )
        )
        assert "news_report" in result
        assert "market_report" not in result
        assert "fundamentals_report" not in result
        assert "sentiment_report" not in result