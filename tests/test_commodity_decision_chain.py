"""
test_commodity_decision_chain.py — 决策链 commodity 化单元测试 (L2-L4 合并版)

测试包含:
  1. 推理分析师（Research Manager）3 模块输出验证（8 个新测试）
  2. Stock 分支零改动验证
  3. 风控辩论节点（6 个）
  4. 风险经理（4 个）
  5. Prompt 占位符完整性
"""
import pytest
import json
from unittest.mock import MagicMock


# =============================================================================
# 共享 fixtures
# =============================================================================

@pytest.fixture
def mock_reasoning_llm():
    """模拟 LLM，返回结构化复合 JSON（ensure_ascii=False 保留中文）。"""
    llm = MagicMock()
    llm.invoke = MagicMock(return_value=MagicMock(content=json.dumps({
        "估值驱动矩阵": {
            "分析时间": "2026-07-17",
            "合约": "RB2501.SHF",
            "维度": [
                {
                    "维度": "基差",
                    "当前状态": "现货升水80元/吨",
                    "估值判断": "低估",
                    "驱动方向": "bullish",
                    "驱动因素": ["库存去化加速"],
                    "置信度": 0.75,
                    "数据来源": ["REF-FUND-a1b2c3d4"]
                }
            ],
            "综合估值判断": "偏多",
            "核心驱动": "库存去化 [REF-FUND-a1b2c3d4]",
            "主要风险": "需求不及预期 [REF-NEWS-x9y8z7w6]"
        },
        "多空对照表": {
            "关键分歧": [
                {
                    "维度": "库存趋势",
                    "看涨逻辑": "社会库存环比-3.2% [REF-FUND-a1b2c3d4]",
                    "看跌逻辑": "绝对库存仍处高位 [REF-FUND-a1b2c3d4]",
                    "证据强度": {"bull": 7, "bear": 5},
                    "引用ID": ["REF-FUND-a1b2c3d4", "REF-TECH-e5f6a7b8"]
                }
            ],
            "看涨核心逻辑": "三角共振 [REF-FUND-xxx, REF-TECH-xxx]",
            "看跌核心逻辑": "库存高位 [REF-FUND-xxx]",
            "综合判断": "短期看涨略占优"
        },
        "三种情景推演": {
            "保守情景": {
                "推演方向": "做多",
                "触发条件": ["库存连续3周去化", "基差走强至80分位"],
                "关注焦点": "近月合约买盘确认",
                "风险节点": "若下周库存数据反弹，此情景失效",
                "置信度": 0.60,
                "数据来源": ["REF-FUND-a1b2c3d4", "REF-TECH-e5f6a7b8"]
            },
            "基准情景": {
                "推演方向": "做多",
                "触发条件": ["库存缓慢去化"],
                "关注焦点": "远月合约期限结构",
                "风险节点": "宏观数据不及预期",
                "置信度": 0.70,
                "数据来源": ["REF-FUND-a1b2c3d4", "REF-POSN-p2q3r4s5"]
            },
            "乐观情景": {
                "推演方向": "做多",
                "触发条件": ["需求旺季启动", "限产政策加码"],
                "关注焦点": "Backwardation是否加深",
                "风险节点": "政策转向",
                "置信度": 0.80,
                "数据来源": ["REF-FUND-a1b2c3d4", "REF-NEWS-x9y8z7w6"]
            },
            "综合情景判断": "偏多基调，需等待库存数据确认"
        }
    }, ensure_ascii=False)))
    return llm


@pytest.fixture
def mock_llm():
    """模拟 LLM，返回固定内容。"""
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
    """commodity 状态模板（不含 bull/bear/trader 字段）。"""
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
        "position_report": "",
        "news_report": "宏观:美联储维持利率;产业:钢厂限产 + 基建开工旺季",
        "fundamentals_report": "基差:现货升水 80 元;库存:螺纹钢社会库存环比 -3.2%;期限结构:Backwardation",
        "investment_plan": "",
        "investment_debate_state": {
            "history": "",
            "bull_history": "",
            "bear_history": "",
            "current_response": "",
            "count": 0,
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
        "analyst_registry": {
            "REF-TECH-e5f6a7b8": {
                "id": "REF-TECH-e5f6a7b8", "prefix": "TECH", "analyst": "technical",
                "cn_name": "技术分析师", "report_key": "market_report", "direction": "bullish",
                "summary": "日线突破 3500",
            },
            "REF-FUND-a1b2c3d4": {
                "id": "REF-FUND-a1b2c3d4", "prefix": "FUND", "analyst": "fundamental",
                "cn_name": "基本面分析师", "report_key": "fundamentals_report", "direction": "bullish",
                "summary": "库存去化加速",
            },
            "REF-NEWS-x9y8z7w6": {
                "id": "REF-NEWS-x9y8z7w6", "prefix": "NEWS", "analyst": "news",
                "cn_name": "新闻分析师", "report_key": "news_report", "direction": "bullish",
                "summary": "限产政策加码",
            },
        },
    }


# =============================================================================
# 推理分析师（Research Manager）— 8 个新测试
# =============================================================================

def test_reasoning_output_contains_three_modules(mock_reasoning_llm, mock_memory, base_state):
    """验证推理分析师输出含三大模块。"""
    from tradingagents.agents.managers.research_manager import create_research_manager

    node = create_research_manager(mock_reasoning_llm, mock_memory)
    result = node(base_state)

    assert mock_reasoning_llm.invoke.called
    plan = result.get("investment_plan", "")
    assert "估值驱动矩阵" in plan
    assert "多空对照表" in plan
    assert "三种情景推演" in plan


def test_reasoning_output_is_valid_json(mock_reasoning_llm, mock_memory, base_state):
    """验证复合 JSON 可用 json.loads() 解析。"""
    from tradingagents.agents.managers.research_manager import create_research_manager

    node = create_research_manager(mock_reasoning_llm, mock_memory)
    result = node(base_state)

    plan = result.get("investment_plan", "")
    parsed = json.loads(plan)
    assert "估值驱动矩阵" in parsed
    assert "多空对照表" in parsed
    assert "三种情景推演" in parsed


def test_reasoning_output_no_buy_sell_wording(mock_reasoning_llm, mock_memory, base_state):
    """验证复合 JSON 不含"买入""卖出"字样。"""
    from tradingagents.agents.managers.research_manager import create_research_manager

    node = create_research_manager(mock_reasoning_llm, mock_memory)
    result = node(base_state)

    plan = result.get("investment_plan", "")
    assert "买入" not in plan
    assert "卖出" not in plan


def test_reasoning_output_no_trading_prices(mock_reasoning_llm, mock_memory, base_state):
    """验证不含具体交易价位字段。"""
    from tradingagents.agents.managers.research_manager import create_research_manager

    node = create_research_manager(mock_reasoning_llm, mock_memory)
    result = node(base_state)

    plan = result.get("investment_plan", "")
    forbidden = ["入场价", "止损价", "目标价", "持仓手数", "入场价位", "止损价位", "目标价位"]
    for word in forbidden:
        assert word not in plan, f"不应含'{word}'"


def test_reasoning_output_has_trigger_conditions(mock_reasoning_llm, mock_memory, base_state):
    """验证情景推演包含"触发条件"字段。"""
    from tradingagents.agents.managers.research_manager import create_research_manager

    node = create_research_manager(mock_reasoning_llm, mock_memory)
    result = node(base_state)

    plan = result.get("investment_plan", "")
    parsed = json.loads(plan)
    scenarios = parsed["三种情景推演"]
    for key in ("保守情景", "基准情景", "乐观情景"):
        assert "触发条件" in scenarios[key], f"{key} 缺少触发条件"
        assert isinstance(scenarios[key]["触发条件"], list), f"{key} 触发条件应为列表"


def test_reasoning_output_has_source_citations(mock_reasoning_llm, mock_memory, base_state):
    """验证维度含"数据来源"字段并引用了分析师 ID。"""
    from tradingagents.agents.managers.research_manager import create_research_manager

    node = create_research_manager(mock_reasoning_llm, mock_memory)
    result = node(base_state)

    plan = result.get("investment_plan", "")
    parsed = json.loads(plan)
    # 估值驱动矩阵的维度应含数据来源
    dims = parsed["估值驱动矩阵"]["维度"]
    for d in dims:
        assert "数据来源" in d
        sources = d["数据来源"]
        assert isinstance(sources, list) and len(sources) >= 1
        for ref in sources:
            assert ref.startswith("REF-"), f"引用 ID 应 REF- 开头: {ref}"
    # 情景推演也应含数据来源
    scenarios = parsed["三种情景推演"]
    for key in ("保守情景", "基准情景", "乐观情景"):
        assert "数据来源" in scenarios[key]
        assert len(scenarios[key]["数据来源"]) >= 1


def test_reasoning_stock_branch_unchanged(mock_llm, mock_memory, base_state):
    """stock 路径不受推理分析师改动影响。"""
    from tradingagents.agents.managers.research_manager import create_research_manager

    base_state["asset_type"] = "stock"
    base_state["company_of_interest"] = "AAPL"
    # stock 路径需要 debate history
    base_state["investment_debate_state"]["history"] = "Bull:看多\nBear:看空"
    base_state["investment_debate_state"]["count"] = 2

    node = create_research_manager(mock_llm, mock_memory)
    result = node(base_state)

    assert mock_llm.invoke.called
    call_args = mock_llm.invoke.call_args[0][0]
    prompt_str = str(call_args)
    assert "投资组合经理" in prompt_str or "买入" in prompt_str
    # 验证返回了完整的 investment_debate_state
    assert "investment_debate_state" in result
    assert "investment_plan" in result
    ids = result["investment_debate_state"]
    assert "bull_history" in ids
    assert "bear_history" in ids
    assert "current_response" in ids


def test_reasoning_commodity_prompt_placeholders():
    """新 prompt 的 string.Formatter().parse() 占位符完整性。"""
    from tradingagents.agents.managers.research_manager import COMMODITY_REASONING_PROMPT

    expected_placeholders = {
        "full_symbol", "variety_name", "analysis_date",
        "instrument_context", "analyst_registry_summary",
        "market_research_report", "fundamentals_report",
        "sentiment_report", "news_report", "past_memory_str",
    }
    import string
    formatter = string.Formatter()
    actual_placeholders = {
        fname for _, fname, _, _ in formatter.parse(COMMODITY_REASONING_PROMPT)
        if fname
    }
    assert actual_placeholders == expected_placeholders, (
        f"placeholder 不匹配。期望 {expected_placeholders}, 实际 {actual_placeholders}"
    )


# =============================================================================
# 保留测试：Research Manager Stock 分支
# =============================================================================

def test_research_manager_commodity(mock_llm, mock_memory, base_state):
    """确保 commodity 分支仍可调用。"""
    from tradingagents.agents.managers.research_manager import create_research_manager

    node = create_research_manager(mock_llm, mock_memory)
    result = node(base_state)

    assert mock_llm.invoke.called
    assert "investment_plan" in result
    assert "investment_debate_state" in result


# =============================================================================
# 风险辩论节点（6 个不变）
# =============================================================================

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


# =============================================================================
# 风险经理（4 个不变）
# =============================================================================

def test_risk_manager_commodity(mock_llm, mock_memory, base_state):
    from tradingagents.agents.managers.risk_manager import create_risk_manager

    node = create_risk_manager(mock_llm, mock_memory)
    result = node(base_state)

    assert mock_llm.invoke.called
    call_args = mock_llm.invoke.call_args[0][0]
    prompt_str = str(call_args)
    assert "期货" in prompt_str or "做多" in prompt_str or "做空" in prompt_str or "RB2501" in prompt_str
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


# =============================================================================
# Prompt 占位符完整性（风控辩论节点）
# =============================================================================

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


# =============================================================================
# 字段一致性
# =============================================================================

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
