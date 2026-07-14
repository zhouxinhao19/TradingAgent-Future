"""
test_commodity_cio.py — CIO (ExecutiveDecisionMaker) 单元测试(Phase 3b-ii)
"""
import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.invoke = MagicMock(return_value=MagicMock(content="# RB2501.SHF 最终决策\n\n## 决策摘要\n- 方向:做多\n- 合约:RB2501.SHF\n- 入场:3500\n- 止损:3400\n- 目标:3800\n- 持仓:5 手\n- 置信度:0.75\n- 风险敞口:15%"))
    return llm


@pytest.fixture
def commodity_state():
    return {
        "company_of_interest": "RB2501.SHF",
        "full_symbol": "RB2501.SHF",
        "asset_type": "commodity",
        "investment_plan": "建议做多 RB2501,目标 3800,止损 3400",
        "trader_investment_plan": "做多 RB2501 5 手,入场 3500",
        "final_trade_decision": "风控通过,可执行做多 5 手方案",
        "messages": [],
    }


def test_cio_commodity_happy_path(mock_llm, commodity_state):
    from tradingagents.agents.managers.executive_decision_maker import create_executive_decision_maker

    node = create_executive_decision_maker(mock_llm)
    result = node(commodity_state)

    # 输出字段
    assert "final_decision" in result
    assert "RB2501" in result["final_decision"]
    assert "做多" in result["final_decision"]

    # 验证 LLM 被调用
    assert mock_llm.invoke.called

    # 验证 messages 字段
    assert "messages" in result
    assert "cio_decision_timestamp" in result


def test_cio_commodity_llm_failure_fallback(mock_llm, commodity_state):
    """LLM 抛错时,fallback 到默认平仓决策。"""
    from tradingagents.agents.managers.executive_decision_maker import create_executive_decision_maker

    mock_llm.invoke = MagicMock(side_effect=RuntimeError("LLM 不可用"))

    node = create_executive_decision_maker(mock_llm)
    result = node(commodity_state)

    assert "final_decision" in result
    assert "平仓" in result["final_decision"]
    assert "RB2501" in result["final_decision"]
    # fallback 不污染 messages
    assert result["messages"] == []


def test_cio_stock_returns_none():
    """stock 路径 Phase 3b-ii 不实现,返回 None final_decision。"""
    from tradingagents.agents.managers.executive_decision_maker import create_executive_decision_maker

    llm = MagicMock()
    state = {
        "company_of_interest": "AAPL",
        "asset_type": "stock",
        "investment_plan": "",
        "trader_investment_plan": "",
        "final_trade_decision": "",
        "messages": [],
    }

    node = create_executive_decision_maker(llm)
    result = node(state)

    assert result["final_decision"] is None
    # stock 路径不调 LLM
    assert not llm.invoke.called


def test_cio_commodity_default_asset_type_detection():
    """不传 asset_type 时,默认走 stock(返回 None)。"""
    from tradingagents.agents.managers.executive_decision_maker import create_executive_decision_maker

    llm = MagicMock()
    state = {
        "company_of_interest": "RB2501.SHF",
        "investment_plan": "",
        "trader_investment_plan": "",
        "final_trade_decision": "",
        "messages": [],
    }

    node = create_executive_decision_maker(llm)
    result = node(state)

    assert result["final_decision"] is None


def test_cio_prompt_contains_three_layer_decisions(mock_llm, commodity_state):
    """commodity CIO prompt 应包含三层决策(研究/交易/风控)。"""
    from tradingagents.agents.managers.executive_decision_maker import COMMODITY_CIO_SYSTEM_PROMPT

    assert "研究经理" in COMMODITY_CIO_SYSTEM_PROMPT or "investment_plan" in COMMODITY_CIO_SYSTEM_PROMPT
    assert "交易员" in COMMODITY_CIO_SYSTEM_PROMPT or "trader_plan" in COMMODITY_CIO_SYSTEM_PROMPT
    assert "风控" in COMMODITY_CIO_SYSTEM_PROMPT or "final_trade_decision" in COMMODITY_CIO_SYSTEM_PROMPT
    assert "止损" in COMMODITY_CIO_SYSTEM_PROMPT
    assert "目标" in COMMODITY_CIO_SYSTEM_PROMPT


def test_cio_prompt_placeholders():
    """commodity CIO prompt 应该有 4 个占位符(full_symbol + 三层决策)。"""
    from tradingagents.agents.managers.executive_decision_maker import COMMODITY_CIO_SYSTEM_PROMPT
    import string
    formatter = string.Formatter()
    actual = {fname for _, fname, _, _ in formatter.parse(COMMODITY_CIO_SYSTEM_PROMPT) if fname}
    expected = {"full_symbol", "investment_plan", "trader_plan", "final_trade_decision"}
    assert actual == expected