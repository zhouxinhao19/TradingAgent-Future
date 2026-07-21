"""
test_commodity_graph_integration.py — 全链路集成测试

验证 4 个 L1 分析师 + 推理分析师的图编译与端到端执行。
"""
import pytest
import json
import sys
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage


@pytest.fixture
def mock_env():
    """Mock 环境变量，避免 MongoDB 连接。"""
    with patch.dict('os.environ', {
        'USE_MONGODB_STORAGE': 'false',
        'MONGODB_CONNECTION_STRING': '',
        'MONGODB_DATABASE_NAME': '',
    }, clear=False):
        yield


@pytest.fixture
def mock_llms():
    """Mock LLM 和 memory。

    所有 LLM.invoke() 必须返回 AIMessage 而非 MagicMock，
    否则 AgentState.messages (add_messages reducer) 会崩溃。
    """
    mock_response_text = "[MOCK] 技术面突破 3500"
    quick_llm = MagicMock()
    quick_llm.invoke = MagicMock(return_value=AIMessage(content=mock_response_text))

    deep_llm = MagicMock()
    deep_llm_json = json.dumps({
        "估值驱动矩阵": {"分析时间":"2026-07-17","合约":"RB2501.SHF","维度":[],"综合估值判断":"偏多","核心驱动":"...","主要风险":"..."},
        "多空对照表": {"关键分歧":[],"看涨核心逻辑":"...","看跌核心逻辑":"...","综合判断":"短期偏多"},
        "三种情景推演": {
            "保守情景": {"推演方向":"做多","触发条件":["库存去化"],"关注焦点":"买盘","风险节点":"库存反弹","置信度":0.6,"数据来源":["REF-TEST-xxx"]},
            "基准情景": {"推演方向":"做多","触发条件":["缓慢去化"],"关注焦点":"结构","风险节点":"宏观","置信度":0.7,"数据来源":["REF-TEST-xxx"]},
            "乐观情景": {"推演方向":"做多","触发条件":["旺季启动"],"关注焦点":"Backwardation","风险节点":"政策","置信度":0.8,"数据来源":["REF-TEST-xxx"]},
            "综合情景判断":"偏多"
        }
    }, ensure_ascii=False)
    deep_llm.invoke = MagicMock(return_value=AIMessage(content=deep_llm_json))

    mem = MagicMock()
    mem.get_memories = MagicMock(return_value=[])
    cl = MagicMock()
    cl.should_continue_risk_analysis = MagicMock(side_effect=[
        "Safe Analyst",     # Risky → Safe
        "Neutral Analyst",  # Safe → Neutral
        "Risk Judge",       # Neutral → Risk Judge
    ])
    return quick_llm, deep_llm, mem, cl


class TestGraphCompilation:
    """验证图能成功编译。"""

    def test_graph_compiles(self, mock_env):
        """CommodityGraphSetup.setup_graph() 能成功编译图。"""
        quick_llm, deep_llm, mem, cl = [MagicMock() for _ in range(4)]
        cl.should_continue_risk_analysis = MagicMock(return_value="Risk Judge")

        from tradingagents.graph.commodity_graph import CommodityGraphSetup
        setup = CommodityGraphSetup(quick_llm, deep_llm, mem, mem, cl, {})
        graph = setup.setup_graph()
        assert graph is not None, "图编译失败"

    def test_graph_stream_nodes(self, mock_env, mock_llms):
        """全图 stream 执行，验证所有预设节点均被调用。"""
        quick_llm, deep_llm, mem, cl = mock_llms

        from tradingagents.graph.commodity_graph import CommodityGraphSetup
        setup = CommodityGraphSetup(quick_llm, deep_llm, mem, mem, cl, {})
        graph = setup.setup_graph()

        initial = {
            "messages": [],
            "company_of_interest": "RB2501.SHF",
            "full_symbol": "RB2501.SHF",
            "asset_type": "commodity",
            "variety_name": "螺纹钢",
            "exchange": "SHF",
            "category": "black_metals",
            "quote_unit": "元/吨",
            "trade_date": "2026-07-17",
            "market_report": "",
            "fundamentals_report": "",
            "fundamentals_structured": {},
            "sentiment_report": "",
            "position_report": "",
            "position_structured": {},
            "news_report": "",
            "investment_plan": "",
            "trader_investment_plan": "",
            "investment_debate_state": {"history":"","bull_history":"","bear_history":"","current_response":"","count":0,"judge_decision":""},
            "risk_debate_state": {"history":"","risky_history":"","safe_history":"","neutral_history":"","current_risky_response":"","current_safe_response":"","current_neutral_response":"","count":0,"judge_decision":"","latest_speaker":""},
            "commodity_features": {
                "technical": {"combined": {"signals":["突破"],"direction":"bullish"},"quality":{"rows":100}},
                "basis": {"latest":{"basis_rate":0.02},"quality":{"rows":100}},
                "inventory": {"latest":{"value":100},"quality":{"rows":100}},
                "positioning": {"quality":{"rows":100}},
                "term_structure": {"quality":{"rows":100}},
                "news_sentiment": {},
            },
            "latest_news": [],
            "analyst_registry": {},
            "final_decision": "",
            "cio_decision_timestamp": "",
            "market_tool_call_count": 0,
            "news_tool_call_count": 0,
            "sentiment_tool_call_count": 0,
            "fundamentals_tool_call_count": 0,
        }

        final_state = None
        completed_nodes = []
        for chunk in graph.stream(
            initial,
            config={"configurable": {"thread_id": "test_graph_stream_nodes"}},
        ):
            for node_name, node_update in chunk.items():
                if node_name == "__end__":
                    continue
                completed_nodes.append(node_name)
                if final_state is None:
                    final_state = dict(initial)
                # 手动合并 reducer 字段 (analyst_registry 使用了 merge_dicts reducer)
                if "analyst_registry" in node_update:
                    current = final_state.get("analyst_registry", {})
                    node_update["analyst_registry"] = {**current, **node_update["analyst_registry"]}
                final_state.update(node_update)

        # 验证 4 个 L1 分析师已运行
        assert final_state.get("market_report"), "market_report 为空"
        assert final_state.get("fundamentals_report"), "fundamentals_report 为空"
        assert final_state.get("news_report"), "news_report 为空"
        assert final_state.get("sentiment_report") or final_state.get("position_report"), "sentiment/position report 为空"

        # 验证推理分析师（Research Manager）已运行
        inv_plan = final_state.get("investment_plan", "")
        assert inv_plan, "investment_plan 为空"
        parsed = json.loads(inv_plan)
        assert "估值驱动矩阵" in parsed
        assert "多空对照表" in parsed
        assert "三种情景推演" in parsed

        # 验证 analyst_registry 累积（4 个 L1 分析师各注册一条）
        registry = final_state.get("analyst_registry", {})
        assert len(registry) >= 3, f"analyst_registry 仅含 {len(registry)} 条（期望 >=3）"

        # 验证关键节点均已执行
        expected = {"Technical Analyst", "Fundamentals Analyst", "Sentiment Analyst",
                    "News Analyst", "Research Manager", "Investment Director"}
        executed = set(completed_nodes)
        missing = expected - executed
        assert not missing, f"缺少节点执行: {missing}"

        # 验证投研总监输出了 final_decision
        assert final_state.get("final_decision"), "final_decision 为空"
        assert final_state.get("risk_assessment"), "risk_assessment 为空"


class TestEffectiveDecisionSafety:
    def test_audit_overrides_conflicting_markdown_and_evidence(self):
        from tradingagents.graph.commodity_graph import _effective_research_conclusion, build_evidence_chain

        state = {
            "asset_type": "commodity",
            "full_symbol": "CU2508.SHF",
            "variety_name": "铜",
            "trade_date": "2026-07-21",
            "final_decision": "- **方向**:做多\n- **置信度**:0.80",
            "investment_memo": {"投研结论": {
                "方向倾向": "平仓", "置信度": 0.0, "硬约束说明": "期限结构 R5",
            }},
            "risk_assessment": {
                "composite_risk_level": 3,
                "dimensions": {"term_structure": {"level": 5}},
                "flags": [],
            },
            "risk_card": {"safety_override": {
                "executed": True,
                "action": "flat",
                "confidence": 0.0,
                "overridden_action": "flat",
                "overridden_confidence": 0.0,
                "override_rules_triggered": ["R5_REJECT"],
            }},
            "analyst_registry": {},
            "commodity_features": {},
            "investment_plan": "",
        }

        decision = _effective_research_conclusion(state)
        evidence = build_evidence_chain(state)
        assert decision["action"] == "flat"
        assert decision["confidence"] == 0.0
        assert evidence["summary"]["final_action"] == "flat"
        assert evidence["summary"]["confidence"] == 0.0
        assert evidence["layers"]["L3"]["safety_override"]["executed"] is True
        assert evidence["layers"]["L3"]["cio_memo"]["投研结论"]["方向倾向"] == "平仓"
        assert evidence["layers"]["L3"]["cio_memo"]["投研结论"]["硬约束说明"] == "期限结构 R5"

    def test_missing_audit_with_r5_fails_closed(self, caplog):
        from tradingagents.graph.commodity_graph import _effective_research_conclusion

        state = {
            "asset_type": "commodity",
            "final_decision": "- **方向**:做多\n- **置信度**:0.80",
            "risk_assessment": {
                "composite_risk_level": 3,
                "dimensions": {"term_structure": {"level": 5}},
                "flags": [],
            },
            "risk_card": {},
        }
        with caplog.at_level("ERROR"):
            decision = _effective_research_conclusion(state)
        assert decision["action"] == "flat"
        assert decision["confidence"] == 0.0
        assert any("fail closed" in record.message for record in caplog.records)

    def test_missing_audit_with_insufficient_data_holds(self):
        from tradingagents.graph.commodity_graph import _effective_research_conclusion

        decision = _effective_research_conclusion({
            "asset_type": "commodity",
            "final_decision": "- **方向**:做空\n- **置信度**:0.90",
            "risk_assessment": {
                "composite_risk_level": "UNKNOWN",
                "data_insufficient": True,
                "dimensions": {},
                "flags": [],
            },
            "risk_card": {},
        })
        assert decision["action"] == "hold"
        assert decision["confidence"] == 0.0

    def test_normal_audit_preserves_markdown_decision(self):
        from tradingagents.graph.commodity_graph import _effective_research_conclusion

        decision = _effective_research_conclusion({
            "asset_type": "commodity",
            "final_decision": "- **方向**:做空\n- **置信度**:0.65",
            "risk_assessment": {"dimensions": {}, "flags": []},
            "risk_card": {"safety_override": {
                "executed": True,
                "action": "short",
                "confidence": 0.65,
                "overridden_action": "short",
                "overridden_confidence": 0.65,
            }},
        })
        assert decision["action"] == "short"
        assert decision["confidence"] == 0.65


class TestDerivedTraderPlanAndFinalDecision:
    """trader_investment_plan / final_trade_decision 由投研总监策略产出派生（纯规则，零 LLM）。"""

    def _full_state(self):
        return {
            "asset_type": "commodity",
            "full_symbol": "CU2508.SHF",
            "research_brief": (
                "# CU2508.SHF 策略适应性报告\n\n"
                "## 核心矛盾与叙事\n当前铜市场基差贴水与库存去化拉锯。\n\n"
                "## 策略适应性矩阵\n（见下表）\n"
            ),
            "strategy_matrix": [
                {"strategy": "单边趋势", "fitness": "不推荐",
                 "rationale": "趋势弱", "key_conditions": ["ATR pctl=0.04 ✗", "拥挤度=R5 ⚠️"]},
                {"strategy": "波动率", "fitness": "谨慎推荐",
                 "rationale": "高波动低趋势", "key_conditions": ["regime=high"]},
            ],
            "risk_assessment": {
                "dimensions": {
                    "term_structure": {"level": 5, "reason": "深度 Contango"},
                    "volatility": {"level": 3, "reason": "波动率中等"},
                },
            },
            "investment_memo": {"投研结论": {
                "核心观点": "震荡蓄势，等待方向突破",
                "推荐关注策略": ["波动率"],
                "需规避策略": ["单边趋势"],
                "风险信号": ["拥挤度 R5"],
            }},
            "risk_card": {"safety_override": {
                "executed": True,
                "action": "flat",
                "confidence": 0.0,
                "overridden_action": "flat",
                "overridden_confidence": 0.0,
                "max_position_pct": 0.0,
                "risk_tier": "R4",
                "allowed_strategies": [],
                "forbidden_strategies": ["单边趋势", "波动率"],
                "strategy_constraints": "硬约束触发，禁止所有策略",
                "override_rules_triggered": ["R5_REJECT"],
            }},
        }

    def test_trader_plan_contains_report_and_tables(self):
        from tradingagents.graph.commodity_graph import _compose_trader_plan

        md = _compose_trader_plan(self._full_state())
        assert md, "trader_investment_plan 为空"
        assert "交易计划" in md
        assert "策略适应性" in md
        # 策略矩阵渲染成管道表格
        assert "| 策略 | 适应性 | 核心判据 |" in md
        assert "单边趋势" in md and "波动率" in md
        # 6 维风险表
        assert "量化风险维度" in md and "term_structure" in md
        # 投研结论摘要
        assert "震荡蓄势" in md
        # 免责声明
        assert "不构成投资建议" in md

    def test_final_decision_derives_from_safety_override(self):
        from tradingagents.graph.commodity_graph import _compose_final_decision

        md = _compose_final_decision(self._full_state())
        assert md, "final_trade_decision 为空"
        assert "最终交易决策" in md
        assert "**方向**：平仓" in md
        assert "**置信度**：0.00" in md
        assert "**建议最大仓位**：0%" in md
        assert "**风险等级**：R4" in md
        assert "R5_REJECT" in md
        assert "不构成投资建议" in md

    def test_handles_empty_state_without_crash(self):
        from tradingagents.graph.commodity_graph import (
            _compose_trader_plan,
            _compose_final_decision,
        )

        # 空 state / 缺 safety_override 不应抛异常
        plan = _compose_trader_plan({})
        decision = _compose_final_decision({})
        assert isinstance(plan, str) and plan
        assert isinstance(decision, str) and decision
        # 缺审计时给安全默认值 + 提示
        assert "**方向**：持有" in decision
        assert "SafetyOverride" in decision


class TestCustomDataPropagation:
    """Phase 自定义数据升级: commodity_features.custom_data 注入 L1/L2/L3 全链路 + SafetyOverride。"""

    def _build_features_with_custom_data(self, direction="bearish", as_of="2026-07-20"):
        """构造一个含 feature_dict 的 commodity_features。"""
        return {
            "technical": {},
            "basis": {},
            "inventory": {},
            "positioning": {},
            "term_structure": {},
            "news_sentiment": {},
            "custom_data": {
                "parsed": True,
                "feature_dict": {
                    "latest": {"inventory": 880.0, "_as_of": as_of},
                    "snapshot": {
                        "current_value": 880.0,
                        "current_value_label": "inventory",
                        "as_of": as_of,
                        "matched_module": "inventory",
                        "self_pctl_180d": 15.0,
                    },
                    "signals": ["用户上传: 库存=880 处于自身 15% 分位(bullish)"],
                    "quality": {"has_as_of": True, "reason": ""},
                    "_direction": direction,
                    "_direction_confidence": 0.7,
                    "_matched_module": "inventory",
                },
            },
        }

    def test_build_custom_data_context_propagates_feature_dict(
        self, mock_env, mock_llms
    ):
        """L1 prompt 通过 build_custom_data_context(feature_dict) → 输出含「低权重参考」。"""
        from tradingagents.agents.analysts.commodity._base import build_custom_data_context

        text = build_custom_data_context(self._build_features_with_custom_data())
        assert "低权重参考" in text
        assert "交叉验证" in text
        assert "[USER_DATA_CONFLICT]" in text
        assert "用户提供当前观测 [inventory]=880" in text

    def test_safety_override_audit_includes_custom_data_conflict(
        self, mock_env, mock_llms
    ):
        """注入 bearish custom_data + LLM long → SafetyOverride audit 标记冲突。"""
        from tradingagents.agents.managers.investment_director import safety_override

        fdict = self._build_features_with_custom_data(direction="bearish")["custom_data"]["feature_dict"]
        result = safety_override(
            risk_assessment={
                "composite_risk_level": 2,
                "dimensions": {},
                "flags": [],
                "data_insufficient": False,
            },
            llm_direction="long",
            llm_confidence=0.8,
            llm_raw="看多。",
            custom_data_feature_dict=fdict,
            counter_signal_explanation="用户数据已交叉验证为历史样本,可忽略",
        )
        assert result["custom_data_conflict"] is True
        assert result["custom_data_direction"] == "bearish"
        assert "CUSTOM_DATA_CONTRADICTION" in result["override_rules_triggered"]
        assert result["confidence"] == 0.3
        assert result["max_position"] == 0.5

    def test_safety_override_audit_no_conflict_when_aligned(
        self, mock_env, mock_llms
    ):
        """custom_data direction == LLM direction → audit.conflict = False。"""
        from tradingagents.agents.managers.investment_director import safety_override

        fdict = self._build_features_with_custom_data(direction="bullish")["custom_data"]["feature_dict"]
        result = safety_override(
            risk_assessment={
                "composite_risk_level": 2,
                "dimensions": {},
                "flags": [],
                "data_insufficient": False,
            },
            llm_direction="long",
            llm_confidence=0.8,
            llm_raw="看多。",
            custom_data_feature_dict=fdict,
        )
        assert result["custom_data_conflict"] is False
        assert "CUSTOM_DATA_CONTRADICTION" not in result["override_rules_triggered"]
        assert result["action"] == "long"
        assert result["confidence"] == 0.8
