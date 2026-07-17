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
        for chunk in graph.stream(initial):
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
                    "News Analyst", "Research Manager", "Risky Analyst", "Safe Analyst",
                    "Neutral Analyst", "Risk Judge", "CIO"}
        executed = set(completed_nodes)
        missing = expected - executed
        assert not missing, f"缺少节点执行: {missing}"
