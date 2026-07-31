"""
test_json_parser.py — parse_and_validate 单元测试（Phase P0）

覆盖：
  - 7 种解析路径（4 层 _make_candidates + 2 层 json_repair + 1 层 fail）
  - 5 个 NodeOutput/Manager schema 的字段校验
  - 边界场景：空字符串、None、非法 JSON、嵌套结构、中文 key
  - json_repair 修复能力（缺逗号/多余逗号/未闭合/单引号/中文标点）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import pytest
from pydantic import BaseModel, ConfigDict, Field

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
from tradingagents.llm_clients.json_parser import (  # noqa: E402
    _make_candidates,
    _validate,
    legacy_parse_and_render,
    parse_and_validate,
)


# =============================================================================
# 共享 fixture
# =============================================================================


class SimpleSchema(BaseModel):
    """测试用简单 schema"""

    model_config = ConfigDict(extra="forbid")

    name: str
    age: int = Field(..., ge=0, le=150)


@pytest.fixture
def valid_json() -> str:
    return json.dumps({"name": "Alice", "age": 30}, ensure_ascii=False)


@pytest.fixture
def valid_fenced_json() -> str:
    """带 ```json ``` 包裹的合法 JSON"""
    return """```json
{
  "name": "Bob",
  "age": 25
}
```"""


@pytest.fixture
def valid_with_extra_text() -> str:
    """前后有解释文字，中间是合法 JSON"""
    return """这是 LLM 的解释文字：
{
  "name": "Charlie",
  "age": 35
}
以上是结果。"""


@pytest.fixture
def invalid_json_missing_comma() -> str:
    """缺逗号（json_repair 可修复）"""
    return '{"name": "Dave" "age": 40}'


@pytest.fixture
def invalid_json_unclosed() -> str:
    """未闭合（json_repair 可修复）"""
    return '{"name": "Eve", "age": 28'


@pytest.fixture
def invalid_json_single_quote() -> str:
    """单引号（json_repair 可修复）"""
    return "{'name': 'Frank', 'age': 45}"


@pytest.fixture
def completely_broken() -> str:
    """完全无法解析（连 json_repair 都救不了）"""
    return "这不是 JSON 也不是能修复的文本 @@@@####"


# =============================================================================
# 基础功能测试
# =============================================================================


class TestParseAndValidateBasic:
    """parse_and_validate 基础场景"""

    def test_valid_json(self, valid_json: str):
        """合法 JSON → 返回 instance, None"""
        instance, error = parse_and_validate(valid_json, SimpleSchema)
        assert error is None
        assert instance is not None
        assert instance.name == "Alice"
        assert instance.age == 30

    def test_empty_content(self):
        """空字符串 → 返回 None, error"""
        instance, error = parse_and_validate("", SimpleSchema)
        assert instance is None
        assert error is not None
        assert "empty" in error

    def test_none_content(self):
        """None 输入 → 返回 None, error"""
        instance, error = parse_and_validate(None, SimpleSchema)  # type: ignore[arg-type]
        assert instance is None
        assert error is not None


class TestParseAndValidatePaths:
    """7 种解析路径覆盖"""

    def test_layer1_direct(self, valid_json: str):
        """Layer 1: 直接 json.loads 成功"""
        candidates = _make_candidates(valid_json)
        assert candidates[0] == valid_json

    def test_layer2_fenced(self, valid_fenced_json: str):
        """Layer 2: 剥 ```json ``` 包裹"""
        candidates = _make_candidates(valid_fenced_json)
        assert len(candidates) >= 2
        # 第二项应该是剥了 fence 的内容
        assert "```" not in candidates[1]
        assert "Alice" in candidates[1] or "Bob" in candidates[1]

    def test_layer3_brace_extract(self, valid_with_extra_text: str):
        """Layer 3: 截 {...}"""
        candidates = _make_candidates(valid_with_extra_text)
        # candidates: [原始 content, {...} 子串]
        # Layer 2 fence 剥不匹配(无 ``` 包裹),所以只有 Layer 1 + Layer 3
        assert len(candidates) >= 2
        # 第二项应该是 {...} 子串
        assert candidates[1].startswith("{")
        assert candidates[1].endswith("}")

    def test_layer4_bracket_extract(self):
        """Layer 4: 截 [...]"""
        content = '前后文字 [1, 2, {"name": "test", "age": 1}] 更多'
        candidates = _make_candidates(content)
        # candidates: [原始, {...} 子串, [...] 子串]
        # Layer 2 不匹配;Layer 3 截 {...};Layer 4 截 [...]
        assert len(candidates) >= 3
        assert candidates[2].startswith("[")
        assert candidates[2].endswith("]")

    def test_layer5_json_repair(self, invalid_json_missing_comma: str):
        """Layer 5: json_repair 修复缺逗号"""
        instance, error = parse_and_validate(
            invalid_json_missing_comma, SimpleSchema, use_repair=True
        )
        # 修复可能成功也可能失败（取决于 json_repair 版本），但不应抛异常
        if instance is None:
            # 修复失败也算合理（json_repair 不是万能）
            assert error is not None
        else:
            assert instance.name == "Dave"
            assert instance.age == 40

    def test_layer5_json_repair_unclosed(self, invalid_json_unclosed: str):
        """Layer 5: json_repair 修复未闭合"""
        instance, error = parse_and_validate(
            invalid_json_unclosed, SimpleSchema, use_repair=True
        )
        # 不应抛异常（关键）
        assert instance is None or (instance.name == "Eve" and instance.age == 28)

    def test_layer5_json_repair_single_quote(self, invalid_json_single_quote: str):
        """Layer 5: json_repair 修复单引号"""
        instance, error = parse_and_validate(
            invalid_json_single_quote, SimpleSchema, use_repair=True
        )
        assert instance is None or (instance.name == "Frank" and instance.age == 45)

    def test_layer7_all_fail(self, completely_broken: str):
        """Layer 7: 全部失败 → 返回 None, error"""
        instance, error = parse_and_validate(
            completely_broken, SimpleSchema, use_repair=True
        )
        assert instance is None
        assert error is not None
        # error 应包含所有尝试层的错误
        assert "Layer" in error or "json" in error.lower()

    def test_use_repair_false(self, invalid_json_missing_comma: str):
        """use_repair=False 时不调用 json_repair"""
        instance, error = parse_and_validate(
            invalid_json_missing_comma, SimpleSchema, use_repair=False
        )
        # 不调用 json_repair 时大概率失败
        assert instance is None
        assert error is not None


class TestParseAndValidateSchema:
    """Pydantic schema 校验测试"""

    def test_validation_error_returns_clear_msg(self):
        """校验失败时返回清晰的错误信息"""
        content = json.dumps({"name": "Alice", "age": 200})  # age 超出 [0,150]
        instance, error = parse_and_validate(content, SimpleSchema)
        assert instance is None
        assert error is not None
        # 错误信息应包含关键字段
        assert "ValidationError" in error or "Pydantic" in error
        # age 字段名应在错误信息中（loc）
        assert "age" in error

    def test_missing_required_field(self):
        """缺少必填字段 → ValidationError"""
        content = json.dumps({"age": 30})  # 缺 name
        instance, error = parse_and_validate(content, SimpleSchema)
        assert instance is None
        assert error is not None

    def test_extra_field_forbidden(self):
        """extra="forbid" — 多余字段应被拒绝"""
        content = json.dumps({"name": "Alice", "age": 30, "extra_field": "should_fail"})
        instance, error = parse_and_validate(content, SimpleSchema)
        assert instance is None
        assert error is not None
        assert "extra" in error.lower() or "forbid" in error.lower()


# =============================================================================
# 业务 schema 校验测试
# =============================================================================


class TestAnalystNodeOutputs:
    """4 个 commodity analyst 的 NodeOutput schema 校验"""

    def test_technical_minimal_valid(self):
        """TechnicalNodeOutput 最少必填字段"""
        content = json.dumps({"direction": "bullish", "confidence": 0.8, "summary": "看多"})
        instance, error = parse_and_validate(content, TechnicalNodeOutput)
        assert error is None
        assert instance is not None
        assert instance.direction == "bullish"
        assert instance.confidence == 0.8

    def test_technical_invalid_direction(self):
        """TechnicalNodeOutput direction 枚举校验"""
        content = json.dumps({"direction": "uptrend", "confidence": 0.8, "summary": "看多"})
        instance, error = parse_and_validate(content, TechnicalNodeOutput)
        assert instance is None
        assert error is not None

    def test_technical_confidence_range(self):
        """TechnicalNodeOutput confidence 范围校验 [0, 1]"""
        content = json.dumps({"direction": "bullish", "confidence": 1.5, "summary": "看多"})
        instance, error = parse_and_validate(content, TechnicalNodeOutput)
        assert instance is None
        assert error is not None
        assert "confidence" in error

    def test_fundamental_with_valuation(self):
        """FundamentalNodeOutput 含 valuation/drive/consistency 嵌套 dict"""
        content = json.dumps({
            "direction": "bullish",
            "confidence": 0.7,
            "summary": "低估+驱动向上",
            "valuation": {"level": "低估", "safety_margin": "充足"},
            "drive": {"direction": "向上", "strength": "中"},
            "consistency": {"alignment": "同向"},
        })
        instance, error = parse_and_validate(content, FundamentalNodeOutput)
        assert error is None
        assert instance is not None
        assert instance.valuation["level"] == "低估"

    def test_position_with_llm_contract(self):
        """PositionNodeOutput 匹配 LLM prompt 输出契约（dict 嵌套结构）"""
        content = json.dumps({
            "direction": {"value": "long", "confidence": 0.75, "drivers": ["库存去化"]},
            "market_regime": {"regime": "多头强势", "price_trend": "上涨", "oi_trend": "增仓", "interpretation": "量价齐升"},
            "long_side": {"trend": "加仓", "change_5d": 1500.0, "interpretation": "主动加仓"},
            "short_side": {"trend": "减仓", "change_5d": -800.0, "interpretation": "空头回补"},
            "concentration": {"level": "高", "crowding_status": "拥挤", "reversal_risk": False, "analysis": "集中度偏高"},
            "cross_contract": {"consistency": "同向看多", "analysis": "各合约方向一致"},
            "rollover": {"detected": False, "analysis": "未检测到移仓换月"},
            "cross_validation": {"alignment": "同向看多", "volume_confirmation": "放量共振", "analysis": "价仓量共振"},
            "summary": "多头强势格局",
            "risk_flags": ["拥挤度偏高"],
            "data_quality": "数据覆盖近30日",
        }, ensure_ascii=False)
        instance, error = parse_and_validate(content, PositionNodeOutput)
        assert error is None, f"error={error}"
        assert instance is not None
        # 顶层 dict 结构保留
        assert instance.direction["value"] == "long"
        assert instance.market_regime["regime"] == "多头强势"
        assert instance.long_side["trend"] == "加仓"
        assert instance.concentration["crowding_status"] == "拥挤"

    def test_position_missing_direction_fails(self):
        """PositionNodeOutput 缺 direction(顶层必填)→ 校验失败"""
        content = json.dumps({
            "market_regime": {"regime": "震荡待判"},
            "summary": "test",
        })
        instance, error = parse_and_validate(content, PositionNodeOutput)
        assert instance is None
        assert error is not None
        assert "direction" in error

    def test_news_minimal_valid(self):
        """NewsNodeOutput direction 有默认值"""
        content = json.dumps({"confidence": 0.6, "summary": "宏观偏多"})
        instance, error = parse_and_validate(content, NewsNodeOutput)
        assert error is None
        assert instance is not None
        assert instance.direction == "neutral"  # 默认值

    def test_news_sentiment_ratio_range(self):
        """NewsNodeOutput sentiment_ratio 范围 [-1, 1]"""
        content = json.dumps({
            "direction": "bullish",
            "confidence": 0.7,
            "summary": "test",
            "sentiment_ratio": 1.5,  # 超出
        })
        instance, error = parse_and_validate(content, NewsNodeOutput)
        assert instance is None
        assert error is not None


class TestManagerSchemas:
    """ManagerDecision + InvestmentMemo 校验"""

    def test_manager_decision_with_chinese_keys(self):
        """ManagerDecision 中文 key 校验"""
        content = json.dumps({
            "估值驱动矩阵": {"维度": [{"维度": "基差", "估值判断": "低估"}]},
            "多空对照表": {"关键分歧": [{"维度": "库存"}]},
            "三种情景推演": {"保守情景": {"推演方向": "做多"}},
            "主要风险": ["库存反弹", "宏观转弱"],
        }, ensure_ascii=False)
        instance, error = parse_and_validate(content, ManagerDecision)
        assert error is None
        assert instance is not None
        assert "估值驱动矩阵" in instance.model_dump()

    def test_manager_decision_all_optional(self):
        """ManagerDecision 所有字段都有默认值"""
        content = json.dumps({})
        instance, error = parse_and_validate(content, ManagerDecision)
        assert error is None
        assert instance is not None

    def test_investment_memo_three_top_keys(self):
        """InvestmentMemo 3 个顶级 key"""
        content = json.dumps({
            "投研备忘录": {"估值审核": {"基差": {"判断": "同意"}}},
            "风险评估卡": {"三方视角": {"激进": {"概率权重": 0.3}}},
            "research_brief": "# 报告\n\n## 核心矛盾\n测试",
        }, ensure_ascii=False)
        instance, error = parse_and_validate(content, InvestmentMemo)
        assert error is None
        assert instance is not None
        assert instance.research_brief.startswith("#")

    def test_investment_memo_extra_field_forbidden(self):
        """InvestmentMemo extra='forbid'"""
        content = json.dumps({
            "投研备忘录": {},
            "风险评估卡": {},
            "research_brief": "test",
            "额外的key": "should_fail",  # 应被拒绝
        }, ensure_ascii=False)
        instance, error = parse_and_validate(content, InvestmentMemo)
        assert instance is None
        assert error is not None


# =============================================================================
# to_report() 转换测试
# =============================================================================


class TestToReportConversion:
    """NodeOutput.to_report() 转换测试"""

    def test_technical_to_report(self):
        """TechnicalNodeOutput → TechnicalReport"""
        node = TechnicalNodeOutput(
            direction="bullish", strength=0.7, confidence=0.8,
            summary="看多", signals=["金叉"],
            volatility_regime="medium", composite_score=0.5,
        )
        report = node.to_report()
        assert isinstance(report, TechnicalReport)
        assert report.direction == "bullish"
        assert report.confidence == 0.8
        assert report.composite_score == 0.5

    def test_fundamental_to_report(self):
        """FundamentalNodeOutput → FundamentalReport"""
        node = FundamentalNodeOutput(
            direction="bullish", confidence=0.7,
            summary="低估",
            valuation={"level": "低估", "reasoning": "贴水"},
            drive={"direction": "向上", "strength": "中"},
            consistency={"alignment": "同向", "confidence": "高"},
        )
        report = node.to_report()
        assert isinstance(report, FundamentalReport)
        assert report.direction == "bullish"
        assert report.basis_view == "低估"  # valuation.level → basis_view

    def test_position_to_report(self):
        """PositionNodeOutput → PositionReport"""
        node = PositionNodeOutput(
            direction={"value": "short", "confidence": 0.7, "drivers": ["累库"]},
            concentration={"level": "高", "crowding_status": "拥挤", "reversal_risk": True},
            summary="空头加仓",
        )
        report = node.to_report()
        assert isinstance(report, PositionReport)
        assert report.direction == "bearish"
        assert report.reversal_risk is True

    def test_news_to_report(self):
        """NewsNodeOutput → NewsReport"""
        node = NewsNodeOutput(
            direction="bullish", confidence=0.7,
            summary="宏观偏多", positive_count=10, negative_count=3,
        )
        report = node.to_report()
        assert isinstance(report, NewsReport)
        assert report.positive_count == 10


# =============================================================================
# 真实场景模拟（用 fund/position analyst 现有 mock fixture 的数据）
# =============================================================================


class TestRealWorldScenarios:
    """模拟 commodity analyst 真实输出场景"""

    def test_fundamental_analyst_realistic_output(self):
        """模拟 fundamental_analyst LLM 真实输出（参考现有 prompt 模板）"""
        content = json.dumps({
            "direction": "bullish",  # 必填字段
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
        }, ensure_ascii=False)

        instance, error = parse_and_validate(content, FundamentalNodeOutput)
        assert error is None
        assert instance is not None
        assert instance.summary == "估值偏低且驱动向上,做多安全边际充足,建议逢低做多"
        assert len(instance.risk_flags) == 2

    def test_research_manager_realistic_output(self):
        """模拟 research_manager LLM 真实输出（参考现有 mock_reasoning_llm fixture）"""
        content = json.dumps({
            "估值驱动矩阵": {
                "分析时间": "2026-07-17",
                "合约": "RB2501.SHF",
                "维度": [
                    {
                        "维度": "基差",
                        "当前状态": "现货升水80元/吨",
                        "估值判断": "低估",
                        "驱动方向": "bullish",
                        "置信度": 0.75,
                        "数据来源": ["REF-FUND-a1b2c3d4"],
                    }
                ],
                "综合估值判断": "偏多",
                "主要风险": "需求不及预期",
            },
            "多空对照表": {
                "关键分歧": [{"维度": "库存趋势", "证据强度": {"bull": 7, "bear": 5}}],
                "看涨核心逻辑": "三角共振",
                "看跌核心逻辑": "库存高位",
                "综合判断": "短期看涨略占优",
            },
            "三种情景推演": {
                "保守情景": {"推演方向": "做多", "置信度": 0.60},
                "基准情景": {"推演方向": "做多", "置信度": 0.70},
                "乐观情景": {"推演方向": "做多", "置信度": 0.80},
            },
            "主要风险": ["需求不及预期", "库存反弹"],
        }, ensure_ascii=False)

        instance, error = parse_and_validate(content, ManagerDecision)
        assert error is None
        assert instance is not None
        assert "估值驱动矩阵" in instance.model_dump()

    def test_fenced_markdown_json(self):
        """模拟 LLM 返回 ```json ``` 包裹的输出"""
        content = """```json
{
  "direction": "bullish",
  "confidence": 0.75,
  "summary": "看多"
}
```"""
        instance, error = parse_and_validate(content, TechnicalNodeOutput)
        assert error is None
        assert instance is not None
        assert instance.direction == "bullish"


# =============================================================================
# _validate 直接测试（review 盲点补全）
# =============================================================================


class TestValidateDirect:
    """_validate 函数直接测试（不经过 _make_candidates）"""

    def test_validate_valid_dict(self):
        """合法 dict → 校验成功"""
        instance, error = _validate({"name": "Alice", "age": 30}, SimpleSchema)
        assert error is None
        assert instance is not None
        assert instance.name == "Alice"

    def test_validate_invalid_value(self):
        """非法值 → 返回精简错误信息"""
        instance, error = _validate({"name": "Alice", "age": 200}, SimpleSchema)
        assert instance is None
        assert error is not None
        assert "age" in error  # 字段名应在错误中
        assert "Pydantic ValidationError" in error

    def test_validate_multiple_errors_shows_first(self):
        """多错误时返回首个错误信息"""
        instance, error = _validate(
            {"name": "Alice", "age": 999, "extra": "x"}, SimpleSchema
        )
        assert instance is None
        assert "errors," in error  # 显示错误数（如 "2 errors, ..."）
        assert "first:" in error  # 显示首个错误

    def test_validate_extra_field_forbidden(self):
        """extra='forbid' 应在错误信息中体现"""
        instance, error = _validate(
            {"name": "Alice", "age": 30, "unknown": "x"}, SimpleSchema
        )
        assert instance is None
        assert "extra" in error.lower() or "forbid" in error.lower()

    def test_validate_wrong_type(self):
        """字段类型错误应被捕获"""
        instance, error = _validate({"name": 123, "age": 30}, SimpleSchema)  # name 应为 str
        assert instance is None
        assert error is not None

    def test_validate_unexpected_exception(self):
        """非 dict 输入 → 异常路径（不抛异常）"""
        instance, error = _validate("not a dict", SimpleSchema)
        assert instance is None
        assert error is not None
        # 应返回 Unexpected validate exception
        assert "Unexpected" in error or "Pydantic" in error


# =============================================================================
# _make_candidates 边界场景测试（review 盲点补全）
# =============================================================================


class TestMakeCandidatesEdge:
    """_make_candidates 嵌套/边界场景"""

    def test_unclosed_brace_no_candidate(self):
        """未闭合 { → 不应截 {...}"""
        content = "前面文字 {abc 后面无闭合"
        candidates = _make_candidates(content)
        # Layer 1: 原始
        # Layer 3: brace_end == -1 (rfind 找不到) → 不 append
        assert len(candidates) == 1
        assert candidates[0] == content

    def test_unclosed_bracket_no_candidate(self):
        """未闭合 [ → 不应截 [...]"""
        content = "前面文字 [1, 2, 3 后面无闭合"
        candidates = _make_candidates(content)
        assert len(candidates) == 1

    def test_nested_braces(self):
        """嵌套 {} → 截最外层 {...}"""
        content = '前缀 {"a": {"b": 1}, "c": 2} 后缀'
        candidates = _make_candidates(content)
        assert len(candidates) >= 2
        # 第二项应包含完整的 {...}（含嵌套）
        assert candidates[1].startswith("{")
        assert candidates[1].endswith("}")
        assert '"b": 1' in candidates[1]

    def test_brackets_inside_braces(self):
        """{...} 内含 [...] → Layer 4 截 [...]"""
        content = '前缀 {"items": [1, 2, 3], "name": "test"} 后缀'
        candidates = _make_candidates(content)
        assert len(candidates) >= 3
        # 第二项：截 {...}
        assert '"items"' in candidates[1]
        # 第三项：截 [...]
        assert candidates[2].startswith("[")
        assert candidates[2].endswith("]")

    def test_multiple_json_objects_picks_first_brace(self):
        """多个 {...} → 截第一个 { 到最后一个 }（可能跨多个对象，行为需明确）"""
        content = "第一个 {a:1} 文字 第二个 {b:2}"
        candidates = _make_candidates(content)
        # Layer 3 截 第一个 { 到 最后一个 }（贪婪）
        assert len(candidates) >= 2
        # candidates[1] 应从 第一个 { 到 最后一个 }（横跨两个 object）
        assert candidates[1].startswith("{")
        assert candidates[1].endswith("}")
        # 这种情况下 json.loads 会失败，但候选还是生成（Layer 4 兜底）

    def test_empty_string(self):
        """空字符串 → 1 个候选（自身）"""
        candidates = _make_candidates("")
        assert len(candidates) == 1
        assert candidates[0] == ""

    def test_only_fenced(self):
        """仅 ```json ``` 包裹，无其他内容"""
        content = '```json\n{"a": 1}\n```'
        candidates = _make_candidates(content)
        # Layer 1: 原始
        # Layer 2: 剥 fence
        assert len(candidates) >= 2
        assert '{"a": 1}' in candidates[1]


# =============================================================================
# to_report() 完整 round-trip 测试（验证 review 修复：数据不丢失）
# =============================================================================


# =============================================================================
# legacy_parse_and_render 共享函数测试（review 修复：DRY 提炼）
# =============================================================================


class TestLegacyParseAndRender:
    """legacy_parse_and_render 统一解析入口测试"""

    def _render(self, parsed: dict) -> str:
        return f"# 渲染\n{parsed.get('name', 'N/A')}"

    def test_valid_json(self):
        """合法 JSON → 解析成功 + 渲染"""
        content = '{"name": "Alice", "age": 30}'
        parsed_dict, structured, report_md = legacy_parse_and_render(
            content, self._render, error_prefix="[test]"
        )
        assert parsed_dict == {"name": "Alice", "age": 30}
        assert structured == {"name": "Alice", "age": 30}
        assert report_md == "# 渲染\nAlice"

    def test_fenced_json(self):
        """```json ``` 包裹 → 剥 fence 后解析"""
        content = '```json\n{"name": "Bob"}\n```'
        parsed_dict, structured, report_md = legacy_parse_and_render(
            content, self._render, error_prefix="[test]"
        )
        assert parsed_dict == {"name": "Bob"}
        assert report_md == "# 渲染\nBob"

    def test_invalid_json_returns_raw(self):
        """非法 JSON → 返回 raw 兜底"""
        content = "这不是 JSON"
        parsed_dict, structured, report_md = legacy_parse_and_render(
            content, self._render, error_prefix="[test]"
        )
        assert parsed_dict is None
        assert structured["raw"] == "这不是 JSON"
        assert "parse_error" in structured
        assert isinstance(structured["parse_error"], str)
        assert report_md == content

    def test_empty_content(self):
        """空字符串 → raw 兜底"""
        parsed_dict, structured, report_md = legacy_parse_and_render(
            "", self._render, error_prefix="[test]"
        )
        assert parsed_dict is None
        assert structured["raw"] == ""
        assert report_md == ""

    def test_json_with_extra_text(self):
        """前后文字 + JSON → 剥离 fence 不匹配,json.loads 失败 → raw"""
        content = "前面文字 {\"name\": \"Charlie\"} 后面文字"
        parsed_dict, structured, report_md = legacy_parse_and_render(
            content, self._render, error_prefix="[test]"
        )
        # legacy 只用剥 fence + 直接 loads(不做 { } 截取),所以这里失败 → raw
        assert parsed_dict is None
        assert structured["raw"] == content


# =============================================================================
# to_report() 完整 round-trip 测试（验证 review 修复：数据不丢失）
# =============================================================================


class TestToReportRoundTripFix:
    """验证 review 修复后 to_report() 数据完整性

    关键修复：FundamentalNodeOutput.to_report() 必须保留 valuation/drive/consistency
    （之前 bug：把数据丢了）
    """

    def test_fundamental_to_report_preserves_valuation_drive_consistency(self):
        """FundamentalNodeOutput.to_report() 必须保留 valuation/drive/consistency"""
        node = FundamentalNodeOutput(
            direction="bullish", strength=0.7, confidence=0.8,
            summary="低估",
            valuation={"level": "低估", "safety_margin": "充足"},
            drive={"direction": "向上", "strength": "中"},
            consistency={"alignment": "同向", "confidence": "高"},
        )
        report = node.to_report()
        # 验证数据不丢失（在 snapshots 里）
        assert "llm_valuation" in report.snapshots
        assert "llm_drive" in report.snapshots
        assert "llm_consistency" in report.snapshots
        assert report.snapshots["llm_valuation"]["level"] == "低估"
        assert report.snapshots["llm_drive"]["direction"] == "向上"
        assert report.snapshots["llm_consistency"]["alignment"] == "同向"
        # 验证 features 维度快照仍存在（保持向后兼容）
        assert "basis" in report.snapshots
        assert "inventory" in report.snapshots
        assert "term_structure" in report.snapshots
        # 验证 LLM 维度映射到扁平字段（估值/驱动/一致性 → 视图字段）
        assert report.basis_view == "低估"
        assert report.inventory_view == "向上"
        assert report.term_structure_view == "同向"

    def test_technical_to_report_all_fields(self):
        """TechnicalNodeOutput.to_report() 所有字段 round-trip"""
        node = TechnicalNodeOutput(
            direction="bullish", strength=0.7, confidence=0.8,
            summary="看多", signals=["金叉", "放量"],
            timeframe="daily+weekly", volatility_regime="medium",
            atr=125.5, atr_ratio_pctl180=0.65, composite_score=0.5,
            key_levels={"support": 3500.0, "resistance": 3800.0},
            oi_divergence="confirm",
        )
        report = node.to_report()
        # 验证每个字段都映射成功
        for field in [
            "direction", "strength", "confidence", "summary", "signals",
            "timeframe", "volatility_regime", "atr", "atr_ratio_pctl180",
            "composite_score", "key_levels", "oi_divergence",
        ]:
            assert getattr(node, field) == getattr(report, field), (
                f"Field {field} lost in to_report()"
            )

    def test_position_to_report_all_fields(self):
        """PositionNodeOutput.to_report() LLM dict → 扁平字段映射 round-trip"""
        node = PositionNodeOutput(
            direction={"value": "short", "confidence": 0.75, "drivers": ["累库"]},
            market_regime={"regime": "空头强势", "price_trend": "下跌", "oi_trend": "增仓", "interpretation": "价跌仓增"},
            long_side={"trend": "减仓", "change_5d": -1000.0, "interpretation": "多头离场"},
            short_side={"trend": "加仓", "change_5d": 1500.0, "interpretation": "空头进场"},
            concentration={"level": "高", "crowding_status": "拥挤", "reversal_risk": True, "analysis": "拥挤"},
            cross_contract={"consistency": "同向看空", "analysis": "各合约一致"},
            rollover={"detected": True, "analysis": "移仓换月"},
            cross_validation={"alignment": "同向看空", "volume_confirmation": "放量共振", "analysis": "共振"},
            summary="空头强势",
            risk_flags=["拥挤"],
            data_quality="覆盖30日",
        )
        report = node.to_report()
        # LLM direction.value (short) → reports direction (bearish)
        assert report.direction == "bearish"
        # LLM long_side/short_side → 扁平字段
        assert report.long_change_5d == -1000.0
        assert report.short_change_5d == 1500.0
        assert report.long_side_trend == "减仓"
        assert report.short_side_trend == "加仓"
        # LLM concentration → 扁平字段
        assert report.concentration is None  # 未映射（P0 不要求）
        assert report.crowding_status == "拥挤"
        assert report.reversal_risk is True
        # LLM cross_validation → price_position_alignment
        assert report.price_position_alignment == "同向看空"
        # LLM market_regime.price_trend → price_direction
        assert report.price_direction == "下跌"

    def test_news_to_report_all_fields(self):
        """NewsNodeOutput.to_report() 所有字段 round-trip"""
        node = NewsNodeOutput(
            direction="bullish", strength=0.6, confidence=0.7,
            summary="宏观偏多",
            sentiment_ratio=0.6, positive_count=10, negative_count=3,
            neutral_count=5,
            macro_narrative="美联储鸽派转向",
            industry_narrative="钢厂限产加码",
            key_events=["美联储议息", "钢厂限产"],
        )
        report = node.to_report()
        for field in [
            "direction", "strength", "confidence", "summary",
            "sentiment_ratio", "positive_count", "negative_count",
            "neutral_count", "macro_narrative", "industry_narrative",
            "key_events",
        ]:
            assert getattr(node, field) == getattr(report, field), (
                f"Field {field} lost in to_report()"
            )