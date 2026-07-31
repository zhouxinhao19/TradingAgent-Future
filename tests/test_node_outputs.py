"""
test_node_outputs.py — NodeOutput Pydantic Schema 单元测试（Phase P0）

覆盖：
  - 5 个 schema（4 analyst + 2 manager）的字段约束
  - extra="forbid" 严格性验证
  - to_report() 转换的字段映射正确性
  - 边界值（min/max/枚举外值）
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tradingagents.agents.analysts.commodity.node_outputs import (  # noqa: E402
    FundamentalNodeOutput,
    NewsNodeOutput,
    PositionNodeOutput,
    TechnicalNodeOutput,
)
from tradingagents.agents.analysts.commodity.reports import (  # noqa: E402
    FundamentalReport,
    NewsReport,
    PositionReport,
    TechnicalReport,
)
from tradingagents.agents.managers.schemas import (  # noqa: E402
    InvestmentMemo,
    ManagerDecision,
)


# =============================================================================
# TechnicalNodeOutput 测试
# =============================================================================


class TestTechnicalNodeOutput:
    def test_minimum_valid(self):
        node = TechnicalNodeOutput(
            direction="bullish", strength=0.5, confidence=0.7, summary="看多"
        )
        assert node.direction == "bullish"
        assert node.strength == 0.5

    def test_extra_field_forbidden(self):
        with pytest.raises(ValidationError) as exc_info:
            TechnicalNodeOutput(
                direction="bullish", strength=0.5, confidence=0.7,
                summary="看多", unknown_field="x",
            )
        assert "unknown_field" in str(exc_info.value).lower() or "extra" in str(exc_info.value).lower()

    def test_direction_enum(self):
        for d in ["bullish", "bearish", "neutral"]:
            node = TechnicalNodeOutput(direction=d, confidence=0.5, summary="t")
            assert node.direction == d

    def test_direction_invalid(self):
        with pytest.raises(ValidationError):
            TechnicalNodeOutput(direction="uptrend", confidence=0.5, summary="t")

    def test_strength_range(self):
        # 边界值
        TechnicalNodeOutput(direction="neutral", strength=0.0, confidence=0.0, summary="")
        TechnicalNodeOutput(direction="neutral", strength=1.0, confidence=1.0, summary="")
        with pytest.raises(ValidationError):
            TechnicalNodeOutput(direction="neutral", strength=-0.1, confidence=0.5, summary="")
        with pytest.raises(ValidationError):
            TechnicalNodeOutput(direction="neutral", strength=1.1, confidence=0.5, summary="")

    def test_volatility_regime_enum(self):
        for v in ["low", "medium", "high", None]:
            node = TechnicalNodeOutput(
                direction="neutral", confidence=0.5, summary="",
                volatility_regime=v,
            )
            assert node.volatility_regime == v

    def test_composite_score_range(self):
        TechnicalNodeOutput(direction="neutral", confidence=0.5, summary="", composite_score=-1.0)
        TechnicalNodeOutput(direction="neutral", confidence=0.5, summary="", composite_score=1.0)
        with pytest.raises(ValidationError):
            TechnicalNodeOutput(direction="neutral", confidence=0.5, summary="", composite_score=-1.5)
        with pytest.raises(ValidationError):
            TechnicalNodeOutput(direction="neutral", confidence=0.5, summary="", composite_score=1.5)

    def test_to_report_round_trip(self):
        node = TechnicalNodeOutput(
            direction="bullish", strength=0.7, confidence=0.8,
            summary="看多", signals=["金叉", "放量突破"],
            timeframe="daily+weekly", volatility_regime="medium",
            atr=125.5, composite_score=0.65,
            key_levels={"support": 3500.0, "resistance": 3800.0},
            oi_divergence="confirm",
        )
        report = node.to_report()
        assert isinstance(report, TechnicalReport)
        assert report.direction == node.direction
        assert report.strength == node.strength
        assert report.confidence == node.confidence
        assert report.summary == node.summary
        assert report.signals == node.signals
        assert report.timeframe == node.timeframe
        assert report.volatility_regime == node.volatility_regime
        assert report.atr == node.atr
        assert report.composite_score == node.composite_score
        assert report.key_levels == node.key_levels
        assert report.oi_divergence == node.oi_divergence


# =============================================================================
# FundamentalNodeOutput 测试
# =============================================================================


class TestFundamentalNodeOutput:
    """按 LLM prompt 输出契约校验（valuation/drive/consistency/summary 必填）"""

    def _minimal(self, **overrides):
        base = {
            "valuation": {"level": "低估", "safety_margin": "充足", "reasoning": "贴水"},
            "drive": {"direction": "向上", "strength": "中", "dominant_factor": "库存去化", "reasoning": "去库"},
            "consistency": {"alignment": "同向", "confidence": "高", "analysis": "同向", "key_uncertainty": "宏观"},
            "summary": "估值低估且驱动向上",
            "risk_flags": ["库存反弹"],
            "data_quality": "覆盖60日",
        }
        base.update(overrides)
        return FundamentalNodeOutput(**base)

    def test_minimum_valid(self):
        node = self._minimal()
        assert node.summary == "估值低估且驱动向上"
        assert node.direction is None  # LLM 不输出 direction,默认 None

    def test_direction_optional(self):
        """direction 是 Optional(LLM 不输出),默认 None"""
        node = self._minimal()
        assert node.direction is None
        node2 = self._minimal(direction="bullish")  # 节点层可填充
        assert node2.direction == "bullish"

    def test_missing_valuation_fails(self):
        """缺 valuation(顶层必填)→ 校验失败"""
        import json
        from tradingagents.llm_clients.json_parser import parse_and_validate
        data = self._minimal().model_dump()
        del data["valuation"]
        instance, error = parse_and_validate(json.dumps(data, ensure_ascii=False), FundamentalNodeOutput)
        assert instance is None
        assert error is not None
        assert "valuation" in error

    def test_valuation_dict(self):
        node = self._minimal()
        assert node.valuation["level"] == "低估"

    def test_to_report_maps_to_flat_fields(self):
        """to_report() 从 LLM dict 结构映射到 reports.py 扁平结构"""
        node = self._minimal(direction="bullish")
        report = node.to_report()
        assert isinstance(report, FundamentalReport)
        assert report.direction == "bullish"
        # valuation.level → basis_view, drive.direction → inventory_view, consistency.alignment → term_structure_view
        assert report.basis_view == "低估"
        assert report.inventory_view == "向上"
        assert report.term_structure_view == "同向"
        # LLM 推理维度保留在 snapshots
        assert "llm_valuation" in report.snapshots
        assert "llm_drive" in report.snapshots
        assert "llm_consistency" in report.snapshots

    def test_extra_field_forbidden(self):
        with pytest.raises(ValidationError):
            self._minimal(extra_field="x")


# =============================================================================
# PositionNodeOutput 测试
# =============================================================================


class TestPositionNodeOutput:
    """按 LLM prompt 输出契约校验（direction/market_regime/... dict 嵌套）"""

    def _minimal(self, **overrides):
        base = {
            "direction": {"value": "long", "confidence": 0.75, "drivers": ["库存去化"]},
            "market_regime": {"regime": "多头强势", "price_trend": "上涨", "oi_trend": "增仓", "interpretation": "量价齐升"},
            "long_side": {"trend": "加仓", "change_5d": 1500.0, "interpretation": "主动加仓"},
            "short_side": {"trend": "减仓", "change_5d": -800.0, "interpretation": "空头回补"},
            "concentration": {"level": "高", "crowding_status": "拥挤", "reversal_risk": False, "analysis": "集中度偏高"},
            "cross_contract": {"consistency": "同向看多", "analysis": "各合约方向一致"},
            "rollover": {"detected": False, "analysis": "未检测到移仓"},
            "cross_validation": {"alignment": "同向看多", "volume_confirmation": "放量共振", "analysis": "价仓量共振"},
            "summary": "多头强势格局",
            "risk_flags": ["拥挤度偏高"],
            "data_quality": "覆盖30日",
        }
        base.update(overrides)
        return PositionNodeOutput(**base)

    def test_minimum_valid(self):
        node = self._minimal()
        assert node.direction["value"] == "long"
        assert node.market_regime["regime"] == "多头强势"

    def test_direction_dict_structure(self):
        """direction 是 dict(LLM 输出 {value, confidence, drivers})"""
        node = self._minimal()
        assert node.direction["value"] == "long"
        assert node.direction["confidence"] == 0.75
        assert "drivers" in node.direction

    def test_missing_direction_fails(self):
        """缺 direction(顶层必填)→ 校验失败"""
        import json
        from tradingagents.llm_clients.json_parser import parse_and_validate
        data = self._minimal().model_dump()
        del data["direction"]
        instance, error = parse_and_validate(json.dumps(data, ensure_ascii=False), PositionNodeOutput)
        assert instance is None
        assert error is not None
        assert "direction" in error

    def test_change_5d_null_string_accepted(self):
        """prompt 允许 change_5d 为 "null" 字符串 → 不应校验失败"""
        node = self._minimal(long_side={"trend": "平稳", "change_5d": "null", "interpretation": "观望"})
        assert node.long_side["change_5d"] == "null"

    def test_to_report_maps_to_flat_fields(self):
        """to_report() 从 LLM dict 结构映射到 reports.py 扁平结构"""
        node = self._minimal(
            direction={"value": "short", "confidence": 0.7, "drivers": ["库存累库"]},
            long_side={"trend": "减仓", "change_5d": -1000.0, "interpretation": "多头离场"},
            short_side={"trend": "加仓", "change_5d": 1500.0, "interpretation": "空头进场"},
            concentration={"level": "高", "crowding_status": "拥挤", "reversal_risk": True, "analysis": "拥挤"},
            cross_validation={"alignment": "同向看空", "volume_confirmation": "放量共振", "analysis": "共振"},
        )
        report = node.to_report()
        assert isinstance(report, PositionReport)
        assert report.direction == "bearish"  # short → bearish
        assert report.long_change_5d == -1000.0
        assert report.short_change_5d == 1500.0
        assert report.reversal_risk is True
        assert report.crowding_status == "拥挤"
        assert report.long_side_trend == "减仓"
        assert report.short_side_trend == "加仓"

    def test_to_report_direction_default_neutral(self):
        """direction 缺失/未知 value → to_report 方向默认 neutral"""
        node = self._minimal(direction={"value": "unknown", "confidence": 0.5})
        report = node.to_report()
        assert report.direction == "neutral"


# =============================================================================
# NewsNodeOutput 测试
# =============================================================================


class TestNewsNodeOutput:
    def test_minimum_valid(self):
        node = NewsNodeOutput(confidence=0.5, summary="宏观偏多")
        assert node.direction == "neutral"  # 默认值
        assert node.positive_count == 0  # 默认值

    def test_sentiment_ratio_range(self):
        NewsNodeOutput(confidence=0.5, summary="", sentiment_ratio=-1.0)
        NewsNodeOutput(confidence=0.5, summary="", sentiment_ratio=0.0)
        NewsNodeOutput(confidence=0.5, summary="", sentiment_ratio=1.0)
        with pytest.raises(ValidationError):
            NewsNodeOutput(confidence=0.5, summary="", sentiment_ratio=1.5)

    def test_count_ge_zero(self):
        node = NewsNodeOutput(
            confidence=0.5, summary="",
            positive_count=10, negative_count=5, neutral_count=3,
        )
        assert node.positive_count == 10
        with pytest.raises(ValidationError):
            NewsNodeOutput(confidence=0.5, summary="", positive_count=-1)

    def test_to_report(self):
        node = NewsNodeOutput(
            direction="bullish", confidence=0.7, summary="宏观偏多",
            sentiment_ratio=0.6, positive_count=10, negative_count=3,
            macro_narrative="美联储鸽派转向",
            industry_narrative="钢厂限产加码",
            key_events=["美联储议息", "钢厂限产"],
        )
        report = node.to_report()
        assert isinstance(report, NewsReport)
        assert report.macro_narrative == "美联储鸽派转向"
        assert report.positive_count == 10
        assert len(report.key_events) == 2


# =============================================================================
# ManagerDecision 测试
# =============================================================================


class TestManagerDecision:
    def test_minimum_valid(self):
        node = ManagerDecision()
        assert node.估值驱动矩阵 == {}
        assert node.多空对照表 == {}
        assert node.三种情景推演 == {}
        assert node.主要风险 == []

    def test_extra_field_forbidden(self):
        with pytest.raises(ValidationError):
            ManagerDecision(未授权字段="x")

    def test_chinese_keys(self):
        """中文顶级 key 校验"""
        node = ManagerDecision(
            估值驱动矩阵={"综合估值判断": "偏多"},
            多空对照表={"看涨核心逻辑": "三角共振"},
            三种情景推演={"基准情景": {"推演方向": "做多"}},
            主要风险=["库存反弹"],
        )
        assert node.估值驱动矩阵["综合估值判断"] == "偏多"

    def test_main_risk_max_length(self):
        """主要风险 max_length=20"""
        node = ManagerDecision(主要风险=["x"] * 20)
        assert len(node.主要风险) == 20
        with pytest.raises(ValidationError):
            ManagerDecision(主要风险=["x"] * 21)


# =============================================================================
# InvestmentMemo 测试
# =============================================================================


class TestInvestmentMemo:
    def test_minimum_valid(self):
        node = InvestmentMemo()
        assert node.投研备忘录 == {}
        assert node.风险评估卡 == {}
        assert node.research_brief == ""

    def test_three_top_keys(self):
        """3 个固定顶级 key"""
        node = InvestmentMemo(
            投研备忘录={"估值审核": {"基差": {"判断": "同意"}}},
            风险评估卡={"三方视角": {"激进": {"概率权重": 0.3}}},
            research_brief="# 报告\n\n## 核心矛盾\n测试",
        )
        assert "估值审核" in node.投研备忘录
        assert "三方视角" in node.风险评估卡
        assert node.research_brief.startswith("#")

    def test_research_brief_max_length(self):
        """research_brief max_length=2000"""
        InvestmentMemo(research_brief="x" * 2000)
        with pytest.raises(ValidationError):
            InvestmentMemo(research_brief="x" * 2001)

    def test_extra_field_forbidden(self):
        with pytest.raises(ValidationError):
            InvestmentMemo(额外的key="x")


# =============================================================================
# 跨 schema 行为一致性
# =============================================================================


class TestCrossSchemaConsistency:
    """验证 4 个 analyst schema + 2 个 manager schema 的共同行为"""

    @pytest.mark.parametrize("schema_class", [
        TechnicalNodeOutput,
        FundamentalNodeOutput,
        PositionNodeOutput,
        NewsNodeOutput,
        ManagerDecision,
        InvestmentMemo,
    ])
    def test_extra_forbid_all_schemas(self, schema_class):
        """所有 schema 都应 extra='forbid'"""
        instance = _minimal_instance_for(schema_class)
        # 试图添加未知字段应失败
        with pytest.raises((ValidationError, TypeError)):
            schema_class.model_validate({**instance.model_dump(), "extra": "x"})

    @pytest.mark.parametrize("schema_class", [
        TechnicalNodeOutput,
        FundamentalNodeOutput,
        PositionNodeOutput,
        NewsNodeOutput,
        ManagerDecision,
        InvestmentMemo,
    ])
    def test_to_dict_round_trip(self, schema_class):
        """所有 schema 都应能 model_dump + model_validate 往返"""
        instance = _minimal_instance_for(schema_class)
        data = instance.model_dump()
        instance2 = schema_class.model_validate(data)
        assert instance.model_dump() == instance2.model_dump()


def _minimal_instance_for(schema_class):
    """为每个 schema 构造最简合法实例（匹配各自必填字段）。"""
    if schema_class is TechnicalNodeOutput:
        return TechnicalNodeOutput(direction="neutral", confidence=0.5, summary="t")
    if schema_class is FundamentalNodeOutput:
        return FundamentalNodeOutput(
            valuation={"level": "低估"},
            drive={"direction": "向上"},
            consistency={"alignment": "同向"},
            summary="test",
        )
    if schema_class is PositionNodeOutput:
        return PositionNodeOutput(
            direction={"value": "neutral", "confidence": 0.5},
            summary="test",
        )
    if schema_class is NewsNodeOutput:
        return NewsNodeOutput(confidence=0.5, summary="t")
    if schema_class is ManagerDecision:
        return ManagerDecision()
    return InvestmentMemo()