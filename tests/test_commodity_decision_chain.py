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
        "structured_summary", "past_memory_str",
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
# 量化检查器测试（compute_risk_assessment — 纯规则，0 LLM）
# =============================================================================

def _make_features(**overrides):
    """生成完整的 commodity_features dict，允许 override 特定模块。"""
    base = {
        "technical": {
            "quality": {"rows": 100, "coverage": 0.95, "data_freshness_days": 0},
            "combined": {
                "volatility": {"atr_ratio_pctl180": 35.0},
                "oi_divergence": "confirm",
            },
        },
        "basis": {
            "quality": {"rows": 100, "coverage": 0.90, "data_freshness_days": 0},
            "stats": {"zscore_180d": {"dom_basis_rate": 0.5}},
        },
        "inventory": {
            "quality": {"rows": 80, "coverage": 0.85, "data_freshness_days": 0},
            "stats": {"zscore_180d": 0.3},
            "jump_flag": False,
        },
        "positioning": {
            "quality": {"rows": 60, "coverage": 0.80, "data_freshness_days": 1},
            "snapshot": {"crowding_pctl_180d": 45.0},
        },
        "term_structure": {
            "quality": {"rows": 50, "coverage": 0.75, "data_freshness_days": 1},
            "snapshot": {"carry_score": 0.2, "structure": "backwardation"},
        },
        "news_sentiment": {
            "quality": {"rows": 20, "coverage": 0.70, "data_freshness_days": 0},
            "snapshot": {"sentiment": {"ratio": 0.55}},
        },
    }
    # Apply overrides at top level
    for key, val in overrides.items():
        base[key] = val
    return base


class TestComputeRiskAssessment:

    def test_empty_features(self):
        """空 features → UNKNOWN + data_insufficient。"""
        from tradingagents.agents.managers.investment_director import compute_risk_assessment

        result = compute_risk_assessment({})
        assert result["composite_risk_level"] == "UNKNOWN"
        assert result["data_insufficient"] is True

    def test_none_features(self):
        """None features → UNKNOWN。"""
        from tradingagents.agents.managers.investment_director import compute_risk_assessment

        result = compute_risk_assessment(None)
        assert result["composite_risk_level"] == "UNKNOWN"

    def test_normal_features_risk_level_2(self):
        """所有维度正常 → composite R2（carry_score=0.2 属于 R3）。"""
        from tradingagents.agents.managers.investment_director import compute_risk_assessment

        result = compute_risk_assessment(_make_features())
        assert result["composite_risk_level"] == 2
        assert result["data_insufficient"] is False

    def test_volatility_thresholds(self):
        """波动率百分位阈值边界。"""
        from tradingagents.agents.managers.investment_director import compute_risk_assessment

        # R1: < 20
        r1 = compute_risk_assessment(_make_features(technical={
            "quality": {"rows": 100, "coverage": 0.95, "data_freshness_days": 0},
            "combined": {"volatility": {"atr_ratio_pctl180": 15.0}, "oi_divergence": "confirm"},
        }))
        assert r1["dimensions"]["volatility"]["level"] == 1

        # R3 boundary: exactly 50 → < 50 is R2, >= 50 is R3
        r3 = compute_risk_assessment(_make_features(technical={
            "quality": {"rows": 100, "coverage": 0.95, "data_freshness_days": 0},
            "combined": {"volatility": {"atr_ratio_pctl180": 50.0}, "oi_divergence": "confirm"},
        }))
        assert r3["dimensions"]["volatility"]["level"] == 3  # >= 50 → R3

        # R4: 80-95
        r4 = compute_risk_assessment(_make_features(technical={
            "quality": {"rows": 100, "coverage": 0.95, "data_freshness_days": 0},
            "combined": {"volatility": {"atr_ratio_pctl180": 85.0}, "oi_divergence": "confirm"},
        }))
        assert r4["dimensions"]["volatility"]["level"] == 4

        # R5: >= 95
        r5 = compute_risk_assessment(_make_features(technical={
            "quality": {"rows": 100, "coverage": 0.95, "data_freshness_days": 0},
            "combined": {"volatility": {"atr_ratio_pctl180": 99.0}, "oi_divergence": "confirm"},
        }))
        assert r5["dimensions"]["volatility"]["level"] == 5

    def test_basis_zscore_thresholds(self):
        """基差 z-score 阈值边界。"""
        from tradingagents.agents.managers.investment_director import compute_risk_assessment

        # |z| < 1 → R2
        r2 = compute_risk_assessment(_make_features(basis={
            "quality": {"rows": 100, "coverage": 0.90, "data_freshness_days": 0},
            "stats": {"zscore_180d": {"dom_basis_rate": 0.5}},
        }))
        assert r2["dimensions"]["basis"]["level"] == 2

        # 1 <= |z| < 2 → R3
        r3 = compute_risk_assessment(_make_features(basis={
            "quality": {"rows": 100, "coverage": 0.90, "data_freshness_days": 0},
            "stats": {"zscore_180d": {"dom_basis_rate": 1.5}},
        }))
        assert r3["dimensions"]["basis"]["level"] == 3

        # |z| >= 3 → R5 + basis_extreme flag
        r5 = compute_risk_assessment(_make_features(basis={
            "quality": {"rows": 100, "coverage": 0.90, "data_freshness_days": 0},
            "stats": {"zscore_180d": {"dom_basis_rate": 3.5}},
        }))
        assert r5["dimensions"]["basis"]["level"] == 5
        assert any(f["name"] == "basis_extreme" for f in r5["flags"])

    def test_crowding_thresholds(self):
        """持仓拥挤度阈值边界。"""
        from tradingagents.agents.managers.investment_director import compute_risk_assessment

        # < 20 → R1
        r1 = compute_risk_assessment(_make_features(positioning={
            "quality": {"rows": 60, "coverage": 0.80, "data_freshness_days": 1},
            "snapshot": {"crowding_pctl_180d": 10.0},
        }))
        assert r1["dimensions"]["crowding"]["level"] == 1

        # >= 95 → R5
        r5 = compute_risk_assessment(_make_features(positioning={
            "quality": {"rows": 60, "coverage": 0.80, "data_freshness_days": 1},
            "snapshot": {"crowding_pctl_180d": 98.0},
        }))
        assert r5["dimensions"]["crowding"]["level"] == 5

    def test_hard_interceptor_vol_crowding(self):
        """高波动 + 高拥挤 → vol_crowding flag。"""
        from tradingagents.agents.managers.investment_director import compute_risk_assessment

        features = _make_features(
            technical={
                "quality": {"rows": 100, "coverage": 0.95, "data_freshness_days": 0},
                "combined": {"volatility": {"atr_ratio_pctl180": 90.0}, "oi_divergence": "confirm"},
            },
            positioning={
                "quality": {"rows": 60, "coverage": 0.80, "data_freshness_days": 1},
                "snapshot": {"crowding_pctl_180d": 90.0},
            },
        )
        result = compute_risk_assessment(features)
        assert any(f["name"] == "vol_crowding" for f in result["flags"])

    def test_hard_interceptor_multi_extreme(self):
        """≥3 维度 R4+ → multi_extreme flag + R5。"""
        from tradingagents.agents.managers.investment_director import compute_risk_assessment

        features = _make_features(
            technical={
                "quality": {"rows": 100, "coverage": 0.95, "data_freshness_days": 0},
                "combined": {"volatility": {"atr_ratio_pctl180": 90.0}, "oi_divergence": "confirm"},
            },
            basis={
                "quality": {"rows": 100, "coverage": 0.90, "data_freshness_days": 0},
                "stats": {"zscore_180d": {"dom_basis_rate": 3.5}},
            },
            positioning={
                "quality": {"rows": 60, "coverage": 0.80, "data_freshness_days": 1},
                "snapshot": {"crowding_pctl_180d": 90.0},
            },
            term_structure={
                "quality": {"rows": 50, "coverage": 0.75, "data_freshness_days": 1},
                "snapshot": {"carry_score": -0.7, "structure": "contango"},
            },
        )
        result = compute_risk_assessment(features)
        assert any(f["name"] == "multi_extreme" for f in result["flags"])
        # 3+ R4 dimensions → R5
        assert result["composite_risk_level"] == 5

    def test_inventory_jump_flag(self):
        """inventory.jump_flag==True → inventory_jump flag。"""
        from tradingagents.agents.managers.investment_director import compute_risk_assessment

        features = _make_features(inventory={
            "quality": {"rows": 80, "coverage": 0.85, "data_freshness_days": 0},
            "stats": {"zscore_180d": 0.3},
            "jump_flag": True,
        })
        result = compute_risk_assessment(features)
        assert any(f["name"] == "inventory_jump" for f in result["flags"])

    def test_data_quality_missing_module(self):
        """模块 rows==0 → 标记不可用，不参与综合评级。"""
        from tradingagents.agents.managers.investment_director import compute_risk_assessment

        features = _make_features(basis={
            "quality": {"rows": 0, "coverage": 0.0, "data_freshness_days": 99},
            "stats": {"zscore_180d": {"dom_basis_rate": 0.5}},
        })
        result = compute_risk_assessment(features)
        assert result["data_quality"]["details"]["basis"]["available"] is False
        assert result["dimensions"]["basis"]["level"] == 0
        # Other dimensions still calculate properly
        assert result["dimensions"]["volatility"]["level"] >= 1

    def test_carry_cost_flag_contango(self):
        """carry_score<-0.5 + structure=contango → carry_cost flag。"""
        from tradingagents.agents.managers.investment_director import compute_risk_assessment

        features = _make_features(term_structure={
            "quality": {"rows": 50, "coverage": 0.75, "data_freshness_days": 1},
            "snapshot": {"carry_score": -0.6, "structure": "contango"},
        })
        result = compute_risk_assessment(features)
        assert any(f["name"] == "carry_cost" for f in result["flags"])


# =============================================================================
# 投研总监节点测试
# =============================================================================

def make_commodity_state(overrides=None):
    """生成 commodity 状态用于投研总监测试。"""
    state = {
        "asset_type": "commodity",
        "full_symbol": "RB2501.SHF",
        "variety_name": "螺纹钢",
        "exchange": "SHF",
        "quote_unit": "元/吨",
        "trade_date": "2026-07-14",
        "company_of_interest": "RB2501.SHF",
        "commodity_features": _make_features(),
        "investment_plan": json.dumps({
            "估值驱动矩阵": {"综合估值判断": "偏多"},
            "多空对照表": {"综合判断": "短期看涨略占优"},
            "三种情景推演": {"综合情景判断": "偏多基调"},
        }, ensure_ascii=False),
        "analyst_registry": {
            "REF-TECH-a1b2c3": {
                "id": "REF-TECH-a1b2c3", "analyst": "technical",
                "cn_name": "技术分析师", "direction": "bullish",
                "summary": "日线突破 3500",
            },
        },
        "messages": [],
    }
    if overrides:
        state.update(overrides)
    return state


def make_stock_state():
    """生成 stock 状态（验证跳过逻辑）。"""
    return {
        "asset_type": "stock",
        "company_of_interest": "AAPL",
        "full_symbol": "AAPL",
        "messages": [],
    }


class TestInvestmentDirectorNode:

    def test_commodity_path(self):
        """commodity 路径正常返回所有字段。"""
        from tradingagents.agents.managers.investment_director import create_investment_director

        mock_llm = MagicMock()
        mock_llm.invoke = MagicMock(return_value=MagicMock(content=json.dumps({
            "投研备忘录": {"投研结论": {"方向倾向": "做多", "置信度": 0.7}},
            "风险评估卡": {"风险裁定": {"总体风险等级": "R2"}},
            "final_decision_markdown": "# RB2501.SHF 决策\n- **方向**:做多\n- **置信度**:0.70",
        }, ensure_ascii=False)))

        director = create_investment_director(mock_llm)
        result = director(make_commodity_state())

        assert mock_llm.invoke.called
        assert "risk_assessment" in result
        assert "risk_card" in result
        assert "investment_memo" in result
        assert "final_decision" in result
        assert "cio_decision_timestamp" in result
        # Verify quant data is never lost
        assert result["risk_assessment"]["composite_risk_level"] == 2
        assert "做多" in result["final_decision"]

    def test_stock_path_skips(self):
        """stock 路径直接跳过。"""
        from tradingagents.agents.managers.investment_director import create_investment_director

        mock_llm = MagicMock()
        director = create_investment_director(mock_llm)
        result = director(make_stock_state())

        assert result == {}
        assert not mock_llm.invoke.called

    def test_llm_fallback(self):
        """LLM 3 次重试失败 → fallback（量化数据不丢失）。"""
        from tradingagents.agents.managers.investment_director import create_investment_director

        mock_failing_llm = MagicMock()
        mock_failing_llm.invoke = MagicMock(side_effect=RuntimeError("LLM 不可用"))

        director = create_investment_director(mock_failing_llm)
        result = director(make_commodity_state())

        assert "risk_assessment" in result  # 量化数据永不丢失
        assert result["risk_assessment"]["composite_risk_level"] == 2
        assert "investment_memo" in result
        assert "risk_card" in result
        assert "持有" in result["final_decision"]  # fallback 方向
        assert "置信度" in result["final_decision"]  # 兼容 _extract_decision 解析
        assert mock_failing_llm.invoke.call_count == 3  # 确实重试了 3 次

    def test_llm_short_content_triggers_retry(self):
        """LLM 返回内容过短 → 应触发重试。"""
        from tradingagents.agents.managers.investment_director import create_investment_director

        mock_llm = MagicMock()
        mock_llm.invoke = MagicMock(return_value=MagicMock(content="短"))

        director = create_investment_director(mock_llm)
        result = director(make_commodity_state())

        # Should fallback (short content rejected)
        assert "持有" in result["final_decision"]
        assert mock_llm.invoke.call_count == 3

    def test_graph_wiring(self):
        """CommodityGraphSetup 正确注册 Investment Director 节点。"""
        from tradingagents.graph.commodity_graph import CommodityGraphSetup

        # Simulate minimal mock params
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

        # Verify the graph has the correct node names
        graph_nodes = list(compiled.nodes.keys())
        assert "Investment Director" in graph_nodes
        assert "Research Manager" in graph_nodes

        # Old L3-L5 nodes should not exist
        assert "Risky Analyst" not in graph_nodes
        assert "Safe Analyst" not in graph_nodes
        assert "Neutral Analyst" not in graph_nodes
        assert "Risk Judge" not in graph_nodes
        assert "CIO" not in graph_nodes

        # Verify edges: Research Manager → Investment Director
        # LangGraph's get_graph() returns edges; check adjacency
        graph = compiled.get_graph()
        edges = [(e.source, e.target) for e in graph.edges]
        assert ("Research Manager", "Investment Director") in edges
        assert ("Investment Director", "__end__") in edges
