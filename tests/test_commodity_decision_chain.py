"""
test_commodity_decision_chain.py — 决策链 commodity 化单元测试(Phase 3b-ii-B)

测试 8 个决策链节点(bull/bear/research_manager/trader/aggresive/conservative/neutral/risk_manager)
在 commodity asset_type 下是否正确切换 prompt + 写入正确字段。
"""
import pytest
from unittest.mock import MagicMock


# === 共享 fixtures ===

@pytest.fixture
def mock_llm():
    """模拟 LLM,返回固定内容。"""
    llm = MagicMock()
    llm.invoke = MagicMock(return_value=MagicMock(content="[MOCK] 期货分析输出"))
    return llm


@pytest.fixture
def mock_memory():
    memory = MagicMock()
    memory.get_memories = MagicMock(return_value=[])
    return memory


@pytest.fixture
def base_state():
    """commodity 状态模板。"""
    return {
        "company_of_interest": "RB2501.SHF",
        "full_symbol": "RB2501.SHF",
        "asset_type": "commodity",
        "variety_name": "螺纹钢",
        "exchange": "SHF",
        "category": "black_metals",
        "quote_unit": "元/吨",
        "trade_date": "2026-07-14",
        "market_report": "技术面:突破 3500 元/吨,日线 MACD 金叉,周线布林带上轨",
        "sentiment_report": "持仓:前 20 名净多头增加 12%,主力加多,拥挤度 0.45",
        "position_report": "",  # 新字段,初始为空(测试 fallback)
        "news_report": "宏观:美联储维持利率;产业:钢厂限产 + 基建开工旺季",
        "fundamentals_report": "基差:现货升水 80 元;库存:螺纹钢社会库存环比 -3.2%;期限结构:Backwardation",
        "investment_plan": "建议做多 RB2501,目标 3800,止损 3400",
        "trader_investment_plan": "做多 RB2501 5 手,入场 3500,止损 3400,目标 3800",
        "investment_debate_state": {
            "history": "Bull:看多论据\nBear:看空论据",
            "bull_history": "",
            "bear_history": "",
            "current_response": "Bear:库存累积担忧",
            "count": 1,
            "judge_decision": "",
        },
        "risk_debate_state": {
            "history": "",
            "risky_history": "",
            "safe_history": "",
            "neutral_history": "",
            "current_risky_response": "激进:加仓",
            "current_safe_response": "保守:减仓",
            "current_neutral_response": "中性:对冲",
            "count": 1,
            "judge_decision": "",
        },
        "messages": [],
        "latest_news": [],
    }


# === Bull Researcher ===

def test_bull_commodity_uses_commodity_prompt(mock_llm, mock_memory, base_state):
    from tradingagents.agents.researchers.bull_researcher import create_bull_researcher

    node = create_bull_researcher(mock_llm, mock_memory)
    result = node(base_state)

    # 验证调用了 LLM
    assert mock_llm.invoke.called
    # 验证 commodity prompt 关键标识
    call_args = mock_llm.invoke.call_args[0][0]
    # prompt 是 list[BaseMessage] 或 str
    prompt_str = str(call_args)
    assert "期货" in prompt_str or "做多" in prompt_str or "基差" in prompt_str, (
        f"未检测到 commodity 关键词。prompt 头 500: {prompt_str[:500]}"
    )
    # 验证返回字段
    assert "investment_debate_state" in result


def test_bull_stock_uses_stock_prompt(mock_llm, mock_memory, base_state):
    from tradingagents.agents.researchers.bull_researcher import create_bull_researcher

    base_state["asset_type"] = "stock"
    base_state["company_of_interest"] = "AAPL"

    node = create_bull_researcher(mock_llm, mock_memory)
    node(base_state)

    call_args = mock_llm.invoke.call_args[0][0]
    prompt_str = str(call_args)
    # stock prompt 应该提到公司/股票
    assert "AAPL" in prompt_str or "股票" in prompt_str


def test_bull_default_asset_type_is_stock(mock_llm, mock_memory, base_state):
    """不传 asset_type 时默认走 stock 路径。"""
    from tradingagents.agents.researchers.bull_researcher import create_bull_researcher

    del base_state["asset_type"]
    base_state["company_of_interest"] = "AAPL"

    node = create_bull_researcher(mock_llm, mock_memory)
    node(base_state)

    call_args = mock_llm.invoke.call_args[0][0]
    prompt_str = str(call_args)
    assert "AAPL" in prompt_str


# === Bear Researcher ===

def test_bear_commodity_uses_commodity_prompt(mock_llm, mock_memory, base_state):
    from tradingagents.agents.researchers.bear_researcher import create_bear_researcher

    node = create_bear_researcher(mock_llm, mock_memory)
    result = node(base_state)

    assert mock_llm.invoke.called
    call_args = mock_llm.invoke.call_args[0][0]
    prompt_str = str(call_args)
    assert "期货" in prompt_str or "做空" in prompt_str or "基差" in prompt_str


def test_bear_stock_uses_stock_prompt(mock_llm, mock_memory, base_state):
    from tradingagents.agents.researchers.bear_researcher import create_bear_researcher

    base_state["asset_type"] = "stock"
    base_state["company_of_interest"] = "AAPL"

    node = create_bear_researcher(mock_llm, mock_memory)
    node(base_state)

    call_args = mock_llm.invoke.call_args[0][0]
    prompt_str = str(call_args)
    assert "AAPL" in prompt_str or "股票" in prompt_str


# === Research Manager ===

def test_research_manager_commodity(mock_llm, mock_memory, base_state):
    from tradingagents.agents.managers.research_manager import create_research_manager

    node = create_research_manager(mock_llm, mock_memory)
    result = node(base_state)

    assert mock_llm.invoke.called
    call_args = mock_llm.invoke.call_args[0][0]
    prompt_str = str(call_args)
    assert "期货" in prompt_str or "做多" in prompt_str or "做空" in prompt_str
    # 输出字段
    assert "investment_debate_state" in result
    assert "investment_plan" in result


def test_research_manager_stock(mock_llm, mock_memory, base_state):
    from tradingagents.agents.managers.research_manager import create_research_manager

    base_state["asset_type"] = "stock"
    base_state["company_of_interest"] = "AAPL"

    node = create_research_manager(mock_llm, mock_memory)
    node(base_state)

    call_args = mock_llm.invoke.call_args[0][0]
    prompt_str = str(call_args)
    assert "投资组合经理" in prompt_str or "买入" in prompt_str


# === Trader ===

def test_trader_commodity_uses_commodity_prompt(mock_llm, mock_memory, base_state):
    from tradingagents.agents.trader.trader import create_trader

    node = create_trader(mock_llm, mock_memory)
    result = node(base_state, name="Trader")

    assert mock_llm.invoke.called
    call_args = mock_llm.invoke.call_args[0][0]
    # trader 用 messages list
    messages = call_args if isinstance(call_args, list) else [call_args]
    full_str = " ".join(str(m) for m in messages)
    assert "期货" in full_str or "做多" in full_str or "做空" in full_str or "RB2501" in full_str

    # 输出字段
    assert "trader_investment_plan" in result


def test_trader_stock(mock_llm, mock_memory, base_state):
    from tradingagents.agents.trader.trader import create_trader

    base_state["asset_type"] = "stock"
    base_state["company_of_interest"] = "AAPL"

    node = create_trader(mock_llm, mock_memory)
    node(base_state, name="Trader")

    call_args = mock_llm.invoke.call_args[0][0]
    messages = call_args if isinstance(call_args, list) else [call_args]
    full_str = " ".join(str(m) for m in messages)
    assert "买入" in full_str or "卖出" in full_str


# === Risk Debators ===

def test_aggresive_commodity(mock_llm, base_state):
    from tradingagents.agents.risk_mgmt.aggresive_debator import create_risky_debator

    node = create_risky_debator(mock_llm)
    result = node(base_state)

    assert mock_llm.invoke.called
    call_args = mock_llm.invoke.call_args[0][0]
    prompt_str = str(call_args)
    assert "期货" in prompt_str or "杠杆" in prompt_str or "做多" in prompt_str
    assert "risk_debate_state" in result


def test_aggresive_stock(mock_llm, base_state):
    from tradingagents.agents.risk_mgmt.aggresive_debator import create_risky_debator

    base_state["asset_type"] = "stock"
    node = create_risky_debator(mock_llm)
    node(base_state)

    call_args = mock_llm.invoke.call_args[0][0]
    prompt_str = str(call_args)
    assert "激进" in prompt_str


def test_conservative_commodity(mock_llm, base_state):
    from tradingagents.agents.risk_mgmt.conservative_debator import create_safe_debator

    node = create_safe_debator(mock_llm)
    result = node(base_state)

    assert mock_llm.invoke.called
    call_args = mock_llm.invoke.call_args[0][0]
    prompt_str = str(call_args)
    assert "期货" in prompt_str or "穿仓" in prompt_str or "止损" in prompt_str
    assert "risk_debate_state" in result


def test_conservative_stock(mock_llm, base_state):
    from tradingagents.agents.risk_mgmt.conservative_debator import create_safe_debator

    base_state["asset_type"] = "stock"
    node = create_safe_debator(mock_llm)
    node(base_state)

    call_args = mock_llm.invoke.call_args[0][0]
    prompt_str = str(call_args)
    assert "保守" in prompt_str


def test_neutral_commodity(mock_llm, base_state):
    from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator

    node = create_neutral_debator(mock_llm)
    result = node(base_state)

    assert mock_llm.invoke.called
    call_args = mock_llm.invoke.call_args[0][0]
    prompt_str = str(call_args)
    assert "期货" in prompt_str or "对冲" in prompt_str or "跨期" in prompt_str
    assert "risk_debate_state" in result


def test_neutral_stock(mock_llm, base_state):
    from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator

    base_state["asset_type"] = "stock"
    node = create_neutral_debator(mock_llm)
    node(base_state)

    call_args = mock_llm.invoke.call_args[0][0]
    prompt_str = str(call_args)
    assert "中性" in prompt_str


# === Risk Manager ===

def test_risk_manager_commodity(mock_llm, mock_memory, base_state):
    from tradingagents.agents.managers.risk_manager import create_risk_manager

    node = create_risk_manager(mock_llm, mock_memory)
    result = node(base_state)

    assert mock_llm.invoke.called
    call_args = mock_llm.invoke.call_args[0][0]
    prompt_str = str(call_args)
    assert "期货" in prompt_str or "做多" in prompt_str or "做空" in prompt_str or "RB2501" in prompt_str
    # 输出字段
    assert "risk_debate_state" in result
    assert "final_trade_decision" in result


def test_risk_manager_stock(mock_llm, mock_memory, base_state):
    from tradingagents.agents.managers.risk_manager import create_risk_manager

    base_state["asset_type"] = "stock"
    base_state["company_of_interest"] = "AAPL"

    node = create_risk_manager(mock_llm, mock_memory)
    node(base_state)

    call_args = mock_llm.invoke.call_args[0][0]
    prompt_str = str(call_args)
    assert "买入" in prompt_str or "卖出" in prompt_str


def test_risk_manager_commodity_fallback(mock_llm, mock_memory, base_state):
    """LLM 失败时,commodity 路径返回平仓默认决策。"""
    from tradingagents.agents.managers.risk_manager import create_risk_manager

    mock_llm.invoke = MagicMock(side_effect=RuntimeError("LLM 不可用"))

    node = create_risk_manager(mock_llm, mock_memory)
    result = node(base_state)

    # fallback 应包含 commodity 关键词
    assert "平仓" in result["final_trade_decision"] or "RB2501" in result["final_trade_decision"]


def test_risk_manager_stock_fallback(mock_llm, mock_memory, base_state):
    """LLM 失败时,stock 路径返回持有默认决策。"""
    from tradingagents.agents.managers.risk_manager import create_risk_manager

    base_state["asset_type"] = "stock"
    base_state["company_of_interest"] = "AAPL"
    mock_llm.invoke = MagicMock(side_effect=RuntimeError("LLM 不可用"))

    node = create_risk_manager(mock_llm, mock_memory)
    result = node(base_state)

    assert "持有" in result["final_trade_decision"]


# === Prompt 完整性测试 ===

def test_bull_commodity_prompt_does_not_have_unfilled_braces():
    """commodity prompt 不能含未填充的 {} 占位符(只允许 {var} 形式且要 .format() 提供)。"""
    from tradingagents.agents.researchers.bull_researcher import COMMODITY_BULL_PROMPT

    # 仅含注释中说明的占位符
    expected_placeholders = {
        "full_symbol", "market_research_report", "sentiment_report",
        "news_report", "fundamentals_report", "history",
        "current_response", "past_memory_str"
    }
    import string
    formatter = string.Formatter()
    actual_placeholders = {
        fname for _, fname, _, _ in formatter.parse(COMMODITY_BULL_PROMPT)
        if fname
    }
    assert actual_placeholders == expected_placeholders, (
        f"placeholder 不匹配。期望 {expected_placeholders}, 实际 {actual_placeholders}"
    )


def test_bear_commodity_prompt_placeholders():
    from tradingagents.agents.researchers.bear_researcher import COMMODITY_BEAR_PROMPT
    import string
    formatter = string.Formatter()
    actual_placeholders = {
        fname for _, fname, _, _ in formatter.parse(COMMODITY_BEAR_PROMPT)
        if fname
    }
    expected = {
        "full_symbol", "market_research_report", "sentiment_report",
        "news_report", "fundamentals_report", "history",
        "current_response", "past_memory_str"
    }
    assert actual_placeholders == expected


def test_aggresive_commodity_prompt_placeholders():
    from tradingagents.agents.risk_mgmt.aggresive_debator import COMMODITY_AGGRESSIVE_PROMPT
    import string
    formatter = string.Formatter()
    actual_placeholders = {
        fname for _, fname, _, _ in formatter.parse(COMMODITY_AGGRESSIVE_PROMPT)
        if fname
    }
    expected = {
        "trader_decision", "market_research_report", "sentiment_report",
        "news_report", "fundamentals_report", "history",
        "current_safe_response", "current_neutral_response"
    }
    assert actual_placeholders == expected


def test_conservative_commodity_prompt_placeholders():
    from tradingagents.agents.risk_mgmt.conservative_debator import COMMODITY_CONSERVATIVE_PROMPT
    import string
    formatter = string.Formatter()
    actual_placeholders = {
        fname for _, fname, _, _ in formatter.parse(COMMODITY_CONSERVATIVE_PROMPT)
        if fname
    }
    expected = {
        "trader_decision", "market_research_report", "sentiment_report",
        "news_report", "fundamentals_report", "history",
        "current_risky_response", "current_neutral_response"
    }
    assert actual_placeholders == expected


def test_neutral_commodity_prompt_placeholders():
    from tradingagents.agents.risk_mgmt.neutral_debator import COMMODITY_NEUTRAL_PROMPT
    import string
    formatter = string.Formatter()
    actual_placeholders = {
        fname for _, fname, _, _ in formatter.parse(COMMODITY_NEUTRAL_PROMPT)
        if fname
    }
    expected = {
        "trader_decision", "market_research_report", "sentiment_report",
        "news_report", "fundamentals_report", "history",
        "current_risky_response", "current_safe_response"
    }
    assert actual_placeholders == expected


# === 字段一致性测试 ===

def test_all_decision_chain_return_investment_debate_state(mock_llm, mock_memory, base_state):
    """bull/bear/research_manager 都返回 investment_debate_state。"""
    from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
    from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
    from tradingagents.agents.managers.research_manager import create_research_manager

    bull = create_bull_researcher(mock_llm, mock_memory)(base_state)
    bear = create_bear_researcher(mock_llm, mock_memory)(base_state)
    rm = create_research_manager(mock_llm, mock_memory)(base_state)

    assert "investment_debate_state" in bull
    assert "investment_debate_state" in bear
    assert "investment_debate_state" in rm


def test_all_risk_debators_return_risk_debate_state(mock_llm, base_state):
    from tradingagents.agents.risk_mgmt.aggresive_debator import create_risky_debator
    from tradingagents.agents.risk_mgmt.conservative_debator import create_safe_debator
    from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator

    risky = create_risky_debator(mock_llm)(base_state)
    safe = create_safe_debator(mock_llm)(base_state)
    neutral = create_neutral_debator(mock_llm)(base_state)

    assert "risk_debate_state" in risky
    assert "risk_debate_state" in safe
    assert "risk_debate_state" in neutral


# === Phase 4: 双写兼容测试 ===

def test_bull_prefers_position_report_over_sentiment(mock_llm, mock_memory, base_state):
    """当 position_report 有值时,bull 节点优先使用它而非 sentiment_report。"""
    from tradingagents.agents.researchers.bull_researcher import create_bull_researcher

    base_state["position_report"] = "持仓分析:净多增加,价格-持仓同向"
    base_state["sentiment_report"] = "旧情绪数据(不应被使用)"

    node = create_bull_researcher(mock_llm, mock_memory)
    result = node(base_state)

    assert mock_llm.invoke.called
    call_args = mock_llm.invoke.call_args[0][0]
    prompt_str = str(call_args)
    # prompt 应包含 position_report 的内容而非 sentiment_report
    assert "净多增加" in prompt_str
    # 旧数据中的内容不应出现
    assert "旧情绪数据" not in prompt_str


def test_bull_falls_back_to_sentiment(mock_llm, mock_memory, base_state):
    """当 position_report 为空时,bull 节点应回退到 sentiment_report。"""
    from tradingagents.agents.researchers.bull_researcher import create_bull_researcher

    assert base_state["position_report"] == ""  # fixture 确保
    base_state["sentiment_report"] = "备用持仓数据(无 position_report 时)"

    node = create_bull_researcher(mock_llm, mock_memory)
    result = node(base_state)

    assert mock_llm.invoke.called
    call_args = mock_llm.invoke.call_args[0][0]
    prompt_str = str(call_args)
    assert "备用持仓数据" in prompt_str