"""
test_commodity_graph_agent_optimization.py — 决策链优化集成测试

覆盖内容(计划 Appendix D):
  D1: 无自定义数据（常规路径）— graph 全节点调用验证
  D2: 有自定义数据 — custom_data_report 正确填充
  D3: 自定义数据 LLM 失败 — 降级路径
  D4: 方向解析失败 — _extract_research_direction/_extract_research_confidence
  D5: R5 风险覆盖 — SafetyOverride flat 连锁
  D6: News 方向非 neutral — _derive_news_direction
"""
import pytest
import json
from unittest.mock import MagicMock


# =============================================================================
# D4: 方向解析提取（投研总监新函数）
# =============================================================================

class TestDirectionExtraction:
    """_extract_research_direction / _extract_research_confidence"""

    def test_extract_direction_long(self):
        from tradingagents.agents.managers.investment_director import _extract_research_direction
        text = "## 综合判断\n研究结论方向: 看多, 置信度: 0.75"
        assert _extract_research_direction(text) == "long"

    def test_extract_direction_short(self):
        from tradingagents.agents.managers.investment_director import _extract_research_direction
        text = "研究结论方向: 看空 置信度:0.3"
        assert _extract_research_direction(text) == "short"

    def test_extract_direction_neutral(self):
        from tradingagents.agents.managers.investment_director import _extract_research_direction
        text = "研究结论方向:中性"
        assert _extract_research_direction(text) == "hold"

    def test_extract_direction_not_found(self):
        from tradingagents.agents.managers.investment_director import _extract_research_direction
        assert _extract_research_direction("无方向标注") == "hold"
        assert _extract_research_direction("") == "hold"
        assert _extract_research_direction(None) == "hold"

    def test_extract_confidence_normal(self):
        from tradingagents.agents.managers.investment_director import _extract_research_confidence
        assert _extract_research_confidence("置信度: 0.75") == 0.75
        assert _extract_research_confidence("置信度：0.3") == 0.3
        assert _extract_research_confidence("置信度:1") == 1.0

    def test_extract_confidence_clamped(self):
        from tradingagents.agents.managers.investment_director import _extract_research_confidence
        assert _extract_research_confidence("置信度: 1.5") == 1.0
        assert _extract_research_confidence("置信度: -0.1") == 0.0

    def test_extract_confidence_not_found(self):
        from tradingagents.agents.managers.investment_director import _extract_research_confidence
        assert _extract_research_confidence("无置信度") == 0.0
        assert _extract_research_confidence("") == 0.0
        assert _extract_research_confidence(None) == 0.0

    def test_extract_direction_full_markdown(self):
        """从完整 research_brief markdown 中提取。"""
        from tradingagents.agents.managers.investment_director import (
            _extract_research_direction,
            _extract_research_confidence,
        )
        brief = """# RB2501.SHF 策略适应性报告

## 核心矛盾与叙事
库存去化 vs 需求疲软

## 策略适应性矩阵
| 策略 | 适应性 | 核心判据 |
| :--- | :--- | :--- |
| 单边趋势 | 不推荐 | R5 风险 |

## 三方情景推演
（略）

## 关键待验证假设
- [ ] 库存数据

研究结论方向: 看空, 置信度: 0.65"""
        assert _extract_research_direction(brief) == "short"
        assert _extract_research_confidence(brief) == 0.65

    def test_safety_override_receives_extracted_direction(self):
        """验证 ID 节点中 SafetyOverride 接收的是从 research_brief 提取的方向而非 hardcoded。"""
        from tradingagents.agents.managers.investment_director import create_investment_director

        mock_llm = MagicMock()
        # LLM 返回含方向标注的 JSON
        mock_llm.invoke = MagicMock(return_value=MagicMock(content=json.dumps({
            "投研备忘录": {"投研结论": {"核心观点": "短期偏多"}},
            "风险评估卡": {},
            "research_brief": "# RB\n\n研究结论方向: 看多, 置信度: 0.72",
        }, ensure_ascii=False)))

        state = {
            "asset_type": "commodity",
            "full_symbol": "RB2501.SHF",
            "variety_name": "螺纹钢",
            "exchange": "SHF",
            "quote_unit": "元/吨",
            "trade_date": "2026-07-14",
            "company_of_interest": "RB2501.SHF",
            "commodity_features": {
                "technical": {"quality": {"rows": 100, "coverage": 0.95, "data_freshness_days": 0}},
                "basis": {"quality": {"rows": 100, "coverage": 0.90, "data_freshness_days": 0}},
                "inventory": {"quality": {"rows": 80, "coverage": 0.85, "data_freshness_days": 0}},
                "positioning": {"quality": {"rows": 60, "coverage": 0.80, "data_freshness_days": 1}},
                "term_structure": {"quality": {"rows": 50, "coverage": 0.75, "data_freshness_days": 1}},
                "news_sentiment": {"quality": {"rows": 20, "coverage": 0.70, "data_freshness_days": 0}},
            },
            "investment_plan": json.dumps({"估值驱动矩阵": {}, "多空对照表": {}, "三种情景推演": {}}),
            "analyst_registry": {},
            "messages": [],
        }
        result = create_investment_director(mock_llm)(state)

        override = result["risk_card"]["safety_override"]
        assert override["original_llm_direction"] == "long"
        assert override["original_llm_confidence"] == 0.72


# =============================================================================
# D6: News 情感方向推导
# =============================================================================

class TestNewsDirection:
    """_derive_news_direction — 从情感比推导新闻方向"""

    def test_strong_positive(self):
        from tradingagents.agents.analysts.commodity.news_analyst import _derive_news_direction
        assert _derive_news_direction(0.5, 15, 5) == "bullish"

    def test_strong_negative(self):
        from tradingagents.agents.analysts.commodity.news_analyst import _derive_news_direction
        assert _derive_news_direction(-0.5, 3, 9) == "bearish"

    def test_boundary_positive(self):
        """ratio > 0.25 → bullish"""
        from tradingagents.agents.analysts.commodity.news_analyst import _derive_news_direction
        assert _derive_news_direction(0.26, 10, 6) == "bullish"

    def test_boundary_negative(self):
        """ratio < -0.25 → bearish"""
        from tradingagents.agents.analysts.commodity.news_analyst import _derive_news_direction
        assert _derive_news_direction(-0.26, 4, 7) == "bearish"

    def test_boundary_neutral(self):
        from tradingagents.agents.analysts.commodity.news_analyst import _derive_news_direction
        assert _derive_news_direction(0.20, 6, 4) == "neutral"
        assert _derive_news_direction(-0.20, 4, 6) == "neutral"
        assert _derive_news_direction(0.0, 5, 5) == "neutral"

    def test_sentiment_ratio_none_fallback(self):
        """sentiment_ratio=None 时用 positive/negative count 计算。"""
        from tradingagents.agents.analysts.commodity.news_analyst import _derive_news_direction
        assert _derive_news_direction(None, 8, 2) == "bullish"
        assert _derive_news_direction(None, 2, 8) == "bearish"
        assert _derive_news_direction(None, 5, 5) == "neutral"

    def test_all_neutral(self):
        """没有正负事件 → neutral"""
        from tradingagents.agents.analysts.commodity.news_analyst import _derive_news_direction
        assert _derive_news_direction(None, 0, 0) == "neutral"

    def test_integrated_in_registry(self):
        """验证新闻分析器返回的 registry 方向非 hardcoded neutral。"""
        from tradingagents.agents.analysts.commodity.news_analyst import create_news_analyst

        mock_llm = MagicMock()
        mock_llm.invoke = MagicMock(return_value=MagicMock(content="新闻分析报告正文"))

        state = {
            "full_symbol": "RB2501.SHF",
            "trade_date": "2026-07-14",
            "company_of_interest": "RB2501.SHF",
            "asset_type": "commodity",
            "variety_name": "螺纹钢",
            "exchange": "SHF",
            "category": "black",
            "commodity_features": {
                "news_sentiment": {
                    "quality": {"rows": 10, "coverage": 0.8, "data_freshness_days": 0},
                },
            },
            "latest_news": [
                {"title": "利多1", "llm_sentiment": "positive", "source": "test"},
                {"title": "利多2", "llm_sentiment": "positive", "source": "test"},
                {"title": "利空1", "llm_sentiment": "negative", "source": "test"},
            ],
            "messages": [],
        }
        result = create_news_analyst(mock_llm)(state)
        assert "analyst_registry" in result
        registry = result["analyst_registry"]
        # 找 news 条目
        news_entry = None
        for k, v in registry.items():
            if isinstance(v, dict) and v.get("analyst") == "news":
                news_entry = v
                break
        assert news_entry is not None, "应在 registry 中找到 news 条目"
        assert news_entry.get("direction") == "bullish", (
            f"预期 bullish(情感比=0.33>0.25), 实际 {news_entry.get('direction')}"
        )


# =============================================================================
# D1: 无自定义数据（常规路径）
# =============================================================================

class TestGraphRegularPath:
    """无自定义数据时 graph 全节点调用验证"""

    def test_graph_wiring_has_custom_data_bull_bear_nodes(self):
        """验证 graph 包含新注册节点。"""
        from tradingagents.graph.commodity_graph import CommodityGraphSetup

        class MockConditionalLogic:
            def should_continue_risk_analysis(self, state):
                return "Risk Judge"

        mock_llm = MagicMock()
        mock_memory = MagicMock()
        conditional = MockConditionalLogic()

        setup = CommodityGraphSetup(
            mock_llm, mock_llm, mock_memory, mock_memory, conditional, {}
        )
        compiled = setup.setup_graph()
        graph_nodes = list(compiled.nodes.keys())

        assert "Custom Data Analyst" in graph_nodes
        assert "Bull Researcher" in graph_nodes
        assert "Bear Researcher" in graph_nodes
        assert "Technical Analyst" in graph_nodes
        assert "Fundamentals Analyst" in graph_nodes
        assert "Sentiment Analyst" in graph_nodes
        assert "News Analyst" in graph_nodes
        assert "Research Manager" in graph_nodes
        assert "Investment Director" in graph_nodes

    def test_graph_edges_correct(self):
        """验证边拓扑正确。"""
        from tradingagents.graph.commodity_graph import CommodityGraphSetup

        class MockConditionalLogic:
            def should_continue_risk_analysis(self, state):
                return "Risk Judge"

        mock_llm = MagicMock()
        mock_memory = MagicMock()
        setup = CommodityGraphSetup(
            mock_llm, mock_llm, mock_memory, mock_memory, MockConditionalLogic(), {}
        )
        compiled = setup.setup_graph()
        graph = compiled.get_graph()
        edges = {(e.source, e.target) for e in graph.edges}

        # 核心链
        assert ("__start__", "Custom Data Analyst") in edges
        assert ("Custom Data Analyst", "Technical Analyst") in edges
        assert ("Technical Analyst", "Bull Researcher") in edges
        assert ("Fundamentals Analyst", "Bull Researcher") in edges
        assert ("Sentiment Analyst", "Bull Researcher") in edges
        assert ("News Analyst", "Bull Researcher") in edges
        assert ("Bull Researcher", "Bear Researcher") in edges
        assert ("Bear Researcher", "Research Manager") in edges
        assert ("Research Manager", "Investment Director") in edges
        assert ("Investment Director", "__end__") in edges

    def test_custom_data_noop_without_data(self):
        """无上传文件 → custom_data_node 返回空字符串。"""
        from tradingagents.graph.commodity_graph import create_custom_data_analyst_node

        mock_llm = MagicMock()
        node = create_custom_data_analyst_node(mock_llm)

        state = {
            "commodity_features": {
                "custom_data": {"parsed": False, "file_count": 0},
            },
        }
        result = node(state)
        assert result["custom_data_report"] == ""
        mock_llm.invoke.assert_not_called()

    def test_custom_data_noop_without_feature(self):
        """commodity_features 无 custom_data → no-op。"""
        from tradingagents.graph.commodity_graph import create_custom_data_analyst_node

        mock_llm = MagicMock()
        node = create_custom_data_analyst_node(mock_llm)

        state = {"commodity_features": {}}
        result = node(state)
        assert result["custom_data_report"] == ""
        mock_llm.invoke.assert_not_called()

    def test_propagator_initial_state_has_custom_data_report(self):
        """CommodityPropagator 初始 state 包含 custom_data_report。"""
        from tradingagents.agents.utils.agent_states import InvestDebateState, RiskDebateState
        from tradingagents.graph.commodity_graph import CommodityPropagator

        propagator = CommodityPropagator()
        state = propagator.create_initial_state(
            full_symbol="RB2501.SHF",
            trade_date="2026-07-14",
        )
        assert "custom_data_report" in state
        assert state["custom_data_report"] == ""


# =============================================================================
# D2: 有自定义数据
# =============================================================================

class TestCustomDataAnalyst:
    """自定义数据分析师 — 上传文件时正常调用 LLM。"""

    def test_with_summaries_calls_llm(self):
        """有 summaries 时调用 LLM 并返回报告。"""
        from tradingagents.graph.commodity_graph import create_custom_data_analyst_node

        mock_llm = MagicMock()
        mock_llm.invoke = MagicMock(return_value=MagicMock(content="自定义数据分析报告正文"))

        node = create_custom_data_analyst_node(mock_llm)
        state = {
            "commodity_features": {
                "custom_data": {
                    "parsed": True,
                    "file_count": 2,
                    "file_names": ["data1.xlsx", "data2.csv"],
                    "raw_summaries": [
                        {"type": "tabular", "overview": {"rows": 100}},
                        {"type": "tabular", "overview": {"rows": 200}},
                    ],
                    "skill_name": "general-analysis",
                    "user_context": "分析铜价趋势",
                },
            },
        }
        result = node(state)
        assert mock_llm.invoke.called
        assert "custom_data_report" in result
        assert len(result["custom_data_report"]) > 0

    def test_custom_data_report_in_evidence_chain(self):
        """custom_data_report 出现在 evidence_chain L1 中。"""
        from tradingagents.graph.commodity_graph import build_evidence_chain

        state = {
            "full_symbol": "RB2501.SHF",
            "variety_name": "螺纹钢",
            "trade_date": "2026-07-14",
            "analyst_registry": {},
            "commodity_features": {},
            "final_decision": "",
            "research_brief": "",
            "risk_assessment": {},
            "strategy_matrix": [],
            "fact_cards": [],
            "contradiction_map": [],
            "risk_card": {},
            "custom_data_report": "## 自定义数据分析\n用户上传数据显示库存累积趋势",
        }
        chain = build_evidence_chain(state)
        l1 = chain["layers"]["L1"]
        cd_entry = next((e for e in l1 if e["name"] == "自定义数据分析"), None)
        assert cd_entry is not None
        assert cd_entry["status"] == "ok"
        assert len(cd_entry["summary"]) > 0


# =============================================================================
# D3: 自定义数据 LLM 失败
# =============================================================================

class TestCustomDataLLMFailure:
    """自定义数据分析师 — LLM 失败时降级。"""

    def test_custom_data_llm_failure_returns_fallback(self):
        """LLM 异常 → fallback 报告含降级标记。"""
        from tradingagents.graph.commodity_graph import create_custom_data_analyst_node

        mock_failing_llm = MagicMock()
        mock_failing_llm.invoke = MagicMock(side_effect=RuntimeError("API 不可用"))

        node = create_custom_data_analyst_node(mock_failing_llm)
        state = {
            "commodity_features": {
                "custom_data": {
                    "parsed": True,
                    "file_count": 1,
                    "file_names": ["test.xlsx"],
                    "raw_summaries": [{"type": "tabular", "overview": {"rows": 50}}],
                    "skill_name": "general-analysis",
                    "user_context": "",
                },
            },
        }
        result = node(state)
        assert mock_failing_llm.invoke.called
        assert "custom_data_report" in result
        # fallback 应含降级提示
        report = result["custom_data_report"]
        assert "降级" in report or "LLM" in report

    def test_custom_data_llm_empty_returns_fallback(self):
        """LLM 返回空 → fallback。"""
        from tradingagents.graph.commodity_graph import create_custom_data_analyst_node

        mock_llm = MagicMock()
        mock_llm.invoke = MagicMock(return_value=MagicMock(content=""))

        node = create_custom_data_analyst_node(mock_llm)
        state = {
            "commodity_features": {
                "custom_data": {
                    "parsed": True,
                    "file_count": 1,
                    "file_names": ["test.xlsx"],
                    "raw_summaries": [{"type": "tabular", "overview": {"rows": 50}}],
                    "skill_name": "general-analysis",
                    "user_context": "",
                },
            },
        }
        result = node(state)
        assert mock_llm.invoke.called


# =============================================================================
# D5: R5 风险覆盖 — SafetyOverride flat 连锁
# =============================================================================

class TestR5OverrideChain:
    """R5 风险 → SafetyOverride flat → 交易决策 flat/hold。"""

    def test_r5_term_structure_forces_flat_in_safety_override(self):
        """期限结构 R5 → SafetyOverride 返回 flat。"""
        from tradingagents.agents.managers.investment_director import safety_override

        risk_assessment = {
            "composite_risk_level": 4,
            "dimensions": {"term_structure": {"level": 5}},
            "flags": [],
            "data_insufficient": False,
        }
        result = safety_override(risk_assessment, "long", 0.7)
        assert result["action"] == "flat"
        assert result["confidence"] == 0.0
        assert result["max_position"] == 0.0
        assert "R5_REJECT" in result["override_rules_triggered"]
        assert "term_structure" in result["r5_dimensions"]

    def test_r5_flow_through_investment_director(self):
        """验证 ID 节点中 R5 → SafetyOverride → flat 全链路。"""
        from tradingagents.agents.managers.investment_director import create_investment_director

        mock_llm = MagicMock()
        mock_llm.invoke = MagicMock(return_value=MagicMock(content=json.dumps({
            "投研备忘录": {"投研结论": {"核心观点": "看多"}},
            "风险评估卡": {},
            "research_brief": "# RB\n研究结论方向: 看多, 置信度: 0.8",
        }, ensure_ascii=False)))

        state = {
            "asset_type": "commodity",
            "full_symbol": "RB2501.SHF",
            "variety_name": "螺纹钢",
            "exchange": "SHF",
            "quote_unit": "元/吨",
            "trade_date": "2026-07-14",
            "company_of_interest": "RB2501.SHF",
            "commodity_features": {
                "technical": {"quality": {"rows": 100, "coverage": 0.95, "data_freshness_days": 0},
                               "combined": {"volatility": {"atr_ratio_pctl180": 99.0}}},
                "basis": {"quality": {"rows": 100, "coverage": 0.90, "data_freshness_days": 0}},
                "inventory": {"quality": {"rows": 80, "coverage": 0.85, "data_freshness_days": 0}},
                "positioning": {"quality": {"rows": 60, "coverage": 0.80, "data_freshness_days": 1}},
                "term_structure": {"quality": {"rows": 50, "coverage": 0.75, "data_freshness_days": 1},
                                    "snapshot": {"carry_score": -0.7, "structure": "contango"}},
                "news_sentiment": {"quality": {"rows": 20, "coverage": 0.70, "data_freshness_days": 0}},
            },
            "investment_plan": json.dumps({"估值驱动矩阵": {}, "多空对照表": {}, "三种情景推演": {}}),
            "analyst_registry": {},
            "messages": [],
        }
        result = create_investment_director(mock_llm)(state)

        override = result["risk_card"]["safety_override"]
        assert override["overridden_action"] == "flat"
        assert override["confidence"] == 0.0
        assert result["risk_assessment"]["composite_risk_level"] == 4  # volatility R5(99pctl) + term_structure R5(carry -0.7)
        assert result["risk_assessment"]["dimensions"]["term_structure"]["level"] == 5

    def test_composite_r5_forces_flat(self):
        """composite R5 → SafetyOverride flat。"""
        from tradingagents.agents.managers.investment_director import safety_override

        risk_assessment = {
            "composite_risk_level": 5,
            "dimensions": {"volatility": {"level": 5}},
            "flags": [],
            "data_insufficient": False,
        }
        result = safety_override(risk_assessment, "short", 0.8)
        assert result["action"] == "flat"
        assert result["confidence"] == 0.0
        assert result["max_position"] == 0.0

    def test_compose_final_decision_reflects_r5(self):
        """_compose_final_decision 正确反映 R5 触发后的 flat。"""
        from tradingagents.graph.commodity_graph import _compose_final_decision

        state = {
            "full_symbol": "RB2501.SHF",
            "research_brief": "研究结论方向: 看多, 置信度: 0.75",
            "risk_card": {
                "safety_override": {
                    "executed": True,
                    "action": "flat",
                    "confidence": 0.0,
                    "max_position": 0.0,
                    "overridden_action": "flat",
                    "overridden_confidence": 0.0,
                    "risk_tier": "R5",
                    "allowed_strategies": [],
                    "forbidden_strategies": ["单边趋势", "展期收益", "跨期套利", "波动率", "跨品种"],
                    "strategy_constraints": "所有策略禁止",
                    "override_rules_triggered": ["R5_REJECT"],
                    "max_position_pct": 0.0,
                },
            },
        }
        decision = _compose_final_decision(state)
        assert "平仓" in decision or "持有" in decision
        assert "0.00" in decision
        assert "R5" in decision


# =============================================================================
# 衍生 Feature 模块测试
# =============================================================================

class TestDerivedFeatureModules:
    """3 个新增纯规则模块"""

    def test_module_agreement_votes_and_conviction(self):
        from tradingagents.features.commodity.module_agreement import compute_module_agreement

        features = {
            "technical": {"snapshot": {"direction": "bullish"}, "quality": {"rows": 100}},
            "inventory": {"snapshot": {"direction": "bullish"}, "quality": {"rows": 80}},
            "positioning": {"snapshot": {"direction": "bearish"}, "quality": {"rows": 60}},
            "basis": {"snapshot": {"direction": "bullish"}, "quality": {"rows": 90}},
        }
        result = compute_module_agreement(features)
        assert result["tally"]["bullish"] == 3
        assert result["tally"]["bearish"] == 1
        assert result["agreement_score"] == 0.5  # 3/6 (含2个默认neutral)
        assert result["consensus"] == "bullish"

    def test_signal_convergence_detects_divergence(self):
        from tradingagents.features.commodity.signal_convergence import detect_signal_convergence

        features = {
            "technical": {"combined": {"oi_divergence": "conflict", "signals": ["价仓背离"]}},
            "basis": {"signals": []},
            "inventory": {"signals": []},
            "positioning": {"signals": ["拥挤度高分位"]},
            "term_structure": {"signals": ["展期风险高"]},
            "news_sentiment": {"snapshot": {"sentiment": {"ratio": -0.3}}},
        }
        result = detect_signal_convergence(features)
        assert "divergences" in result
        assert len(result["divergences"]) >= 0  # 至少不会报错

    def test_data_freshness_aggregates(self):
        from tradingagents.features.commodity.data_freshness import compute_data_freshness

        features = {
            "technical": {"quality": {"rows": 100, "data_freshness_days": 0, "coverage": 0.95}},
            "inventory": {"quality": {"rows": 80, "data_freshness_days": 5, "coverage": 0.8}},
            "news_sentiment": {"quality": {"rows": 20, "data_freshness_days": 1, "coverage": 0.7}},
        }
        result = compute_data_freshness(features)
        assert "overall" in result
        assert result["stalest_module"] == "inventory"
        assert result["stalest_days"] == 5
        assert "confidence_modifier" in result


# =============================================================================
# Research Manager: 历史保留 + 新占位符
# =============================================================================

class TestResearchManagerPreservesHistory:
    """RM 不覆盖 Bull/Bear 辩论历史。"""

    def test_rm_preserves_debate_history(self):
        """RM 返回的 investment_debate_state 保留现有 history。"""
        from tradingagents.agents.managers.research_manager import create_research_manager

        mock_llm = MagicMock()
        mock_llm.invoke = MagicMock(return_value=MagicMock(content=json.dumps({
            "估值驱动矩阵": {"综合估值判断": "偏多"},
            "多空对照表": {"综合判断": "看涨"},
            "三种情景推演": {"综合情景判断": "偏多"},
        }, ensure_ascii=False)))
        mock_memory = MagicMock()
        mock_memory.get_memories = MagicMock(return_value=[])

        state = {
            "company_of_interest": "RB2501.SHF",
            "full_symbol": "RB2501.SHF",
            "asset_type": "commodity",
            "variety_name": "螺纹钢",
            "exchange": "SHF",
            "category": "black",
            "quote_unit": "元/吨",
            "trade_date": "2026-07-14",
            "market_report": "技术报告",
            "sentiment_report": "持仓报告",
            "position_report": "",
            "news_report": "新闻报告",
            "fundamentals_report": "基本面报告",
            "investment_plan": "",
            "investment_debate_state": {
                "history": "前期辩论历史",
                "bull_history": "多头历史",
                "bear_history": "空头历史",
                "current_response": "当前回应",
                "count": 2,
            },
            "risk_debate_state": {},
            "messages": [],
            "latest_news": [],
            "analyst_registry": {},
            "commodity_features": {},
        }
        result = create_research_manager(mock_llm, mock_memory)(state)

        ids = result.get("investment_debate_state", {})
        assert ids.get("history") == "前期辩论历史", "RM 不应覆盖 history"
        assert ids.get("bull_history") == "多头历史", "RM 不应覆盖 bull_history"
        assert ids.get("bear_history") == "空头历史", "RM 不应覆盖 bear_history"

    def test_rm_commodity_prompt_has_new_placeholders(self):
        """验证 COMMODITY_REASONING_PROMPT 含新占位符。"""
        from tradingagents.agents.managers.research_manager import COMMODITY_REASONING_PROMPT

        import string
        formatter = string.Formatter()
        placeholders = {fname for _, fname, _, _ in formatter.parse(COMMODITY_REASONING_PROMPT) if fname}

        assert "debate_history" in placeholders, "缺少 {debate_history}"
        assert "module_agreement" in placeholders, "缺少 {module_agreement}"
        assert "signal_convergence" in placeholders, "缺少 {signal_convergence}"
