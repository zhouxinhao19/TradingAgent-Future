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
        "contradiction_map_text",
        "debate_history", "module_agreement", "signal_convergence",
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
                "volatility": {"atr_ratio_pctl180": 0.35},
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
            "snapshot": {"crowding_pctl_180d": 0.45},
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
            "combined": {"volatility": {"atr_ratio_pctl180": 0.15}, "oi_divergence": "confirm"},
        }))
        assert r1["dimensions"]["volatility"]["level"] == 1

        # R3 boundary: exactly 50 → < 50 is R2, >= 50 is R3
        r3 = compute_risk_assessment(_make_features(technical={
            "quality": {"rows": 100, "coverage": 0.95, "data_freshness_days": 0},
            "combined": {"volatility": {"atr_ratio_pctl180": 0.50}, "oi_divergence": "confirm"},
        }))
        assert r3["dimensions"]["volatility"]["level"] == 3  # >= 50 → R3

        # R4: 80-95
        r4 = compute_risk_assessment(_make_features(technical={
            "quality": {"rows": 100, "coverage": 0.95, "data_freshness_days": 0},
            "combined": {"volatility": {"atr_ratio_pctl180": 0.85}, "oi_divergence": "confirm"},
        }))
        assert r4["dimensions"]["volatility"]["level"] == 4

        # R5: >= 95
        r5 = compute_risk_assessment(_make_features(technical={
            "quality": {"rows": 100, "coverage": 0.95, "data_freshness_days": 0},
            "combined": {"volatility": {"atr_ratio_pctl180": 0.99}, "oi_divergence": "confirm"},
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

        # < 20 → R4（U 型风险：低拥挤度也属于高风险区间）
        r1 = compute_risk_assessment(_make_features(positioning={
            "quality": {"rows": 60, "coverage": 0.80, "data_freshness_days": 1},
            "snapshot": {"crowding_pctl_180d": 0.10},
        }))
        assert r1["dimensions"]["crowding"]["level"] == 4

        # >= 95 → R5
        r5 = compute_risk_assessment(_make_features(positioning={
            "quality": {"rows": 60, "coverage": 0.80, "data_freshness_days": 1},
            "snapshot": {"crowding_pctl_180d": 0.98},
        }))
        assert r5["dimensions"]["crowding"]["level"] == 5

    def test_hard_interceptor_vol_crowding(self):
        """高波动 + 高拥挤 → vol_crowding flag。"""
        from tradingagents.agents.managers.investment_director import compute_risk_assessment

        features = _make_features(
            technical={
                "quality": {"rows": 100, "coverage": 0.95, "data_freshness_days": 0},
                "combined": {"volatility": {"atr_ratio_pctl180": 0.90}, "oi_divergence": "confirm"},
            },
            positioning={
                "quality": {"rows": 60, "coverage": 0.80, "data_freshness_days": 1},
                "snapshot": {"crowding_pctl_180d": 0.90},
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
                "combined": {"volatility": {"atr_ratio_pctl180": 0.90}, "oi_divergence": "confirm"},
            },
            basis={
                "quality": {"rows": 100, "coverage": 0.90, "data_freshness_days": 0},
                "stats": {"zscore_180d": {"dom_basis_rate": 3.5}},
            },
            positioning={
                "quality": {"rows": 60, "coverage": 0.80, "data_freshness_days": 1},
                "snapshot": {"crowding_pctl_180d": 0.90},
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
        assert "策略适应性报告" in result["final_decision"]  # fallback 研究简报
        assert "系统降级" in result["final_decision"]
        assert mock_failing_llm.invoke.call_count == 3  # 确实重试了 3 次

    def test_llm_short_content_triggers_retry(self):
        """LLM 返回内容过短 → 应触发重试。"""
        from tradingagents.agents.managers.investment_director import create_investment_director

        mock_llm = MagicMock()
        mock_llm.invoke = MagicMock(return_value=MagicMock(content="短"))

        director = create_investment_director(mock_llm)
        result = director(make_commodity_state())

        # Should fallback (short content rejected)
        assert "策略适应性报告" in result["final_decision"]
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


# =============================================================================
# 系统性逻辑修复回归测试
# =============================================================================


def test_research_summary_preserves_real_metrics_and_risks():
    from tradingagents.agents.managers.research_manager import _build_analyst_summary

    features = {
        "technical": {
            "main_continuous": {"daily": {"snapshot": {
                "composite_score": 0.62, "boll_low": 3400, "boll_up": 3650,
            }}},
            "combined": {
                "direction": "short", "oi_divergence": "conflict",
                "volatility": {"regime": "high", "atr_ratio_pctl180": 0.91},
                "signals": ["价仓背离，警惕趋势反转"],
            },
        },
        "basis": {
            "latest": {"spot_price": 3600, "near_basis": 80, "dom_basis_rate": 0.023},
            "stats": {"zscore_180d": {"dom_basis_rate": 92}},
            "signals": ["基差进入高分位，警惕均值回归"],
        },
        "inventory": {
            "latest": {"value": 88},
            "snapshot": {"wow_change": -5, "mom_change": -12, "jump_flag": False},
            "signals": ["库存历史低位"],
        },
        "term_structure": {
            "latest": {"metric": "spread"},
            "snapshot": {"structure": "contango", "carry_score": -0.7},
            "signals": ["期限结构极端，展期风险高"],
        },
        "positioning": {
            "snapshot": {
                "net_long_change_5d": 0.08, "long_short_ratio": 1.3,
                "crowding_pctl_180d": 0.98, "price_oi_regime": "多头强势(价涨仓增)",
                "cross_contract_consistency": "分化", "rollover_detected": True,
            },
            "signals": ["拥挤度处高分位，警惕反转风险"],
        },
        "news_sentiment": {
            "snapshot": {"sentiment": {"bullish": 2, "bearish": 4, "ratio": -0.33}},
            "signals": ["高重要度政策风险提示"],
        },
    }
    registry = {
        "REF-TECH-1": {"analyst": "technical", "direction": "bearish", "status": "ok"},
        "REF-FUND-1": {"analyst": "fundamental", "direction": "向下", "status": "ok"},
        "REF-POSN-1": {"analyst": "position", "direction": "看多(注意拥挤反向风险)", "status": "ok"},
        "REF-NEWS-1": {"analyst": "news", "direction": "neutral", "status": "ok"},
    }
    summary = _build_analyst_summary(
        features,
        registry,
        position_structured={
            "direction": {"confidence": 0.72},
            "concentration": {"crowding_status": "拥挤", "reversal_risk": True},
            "risk_flags": ["高度拥挤，反转风险高"],
        },
        fundamentals_structured={"risk_flags": ["需求下行警告"]},
        latest_news=[{"title": "限产政策变化", "llm_importance": "high", "llm_sentiment": "negative"}],
        reports=["## 风险提示\n- 拥挤度极高分位，反转风险高"],
    )

    for expected in (
        "composite_score=0.62", "oi_divergence=conflict", "spot_price=3600",
        "value=88", "carry_score=-0.7", "crowding_pctl_180d=0.98",
        "高重要度事件: 限产政策变化", "强制保留风险信号",
        "高度拥挤，反转风险高", "需求下行警告",
        "拥挤度极高分位，反转风险高", "L1 冲突: 看多=1, 看空=2",
    ):
        assert expected in summary
    assert "原始置信度 0.0" not in summary
    assert "技术面: 整体不可用（数据缺失）" not in summary


def test_l2_json_postprocess_keeps_forced_risks():
    from tradingagents.agents.managers.research_manager import _ensure_forced_risks_in_plan

    # 输入空 dict → fallback 生成数组和情景对象
    content = json.dumps({
        "估值驱动矩阵": {}, "多空对照表": {}, "三种情景推演": {},
    }, ensure_ascii=False)
    result = json.loads(_ensure_forced_risks_in_plan(
        content, ["高度拥挤，反转风险高"]
    ))

    # 多空对照表现在是数组（fallback 生成）
    assert isinstance(result["多空对照表"], list), "应为数组格式"
    assert len(result["多空对照表"]) > 0, "应有至少一条 fallback 条目"

    # 三种情景推演现在是标准情景对象（fallback 生成）
    assert isinstance(result["三种情景推演"], dict)
    assert "保守情景" in result["三种情景推演"]
    assert "基准情景" in result["三种情景推演"]
    assert "乐观情景" in result["三种情景推演"]


class TestSafetyOverrideHardConstraints:
    @staticmethod
    def _risk(composite=2, dimensions=None, flags=None, data_insufficient=False):
        return {
            "composite_risk_level": composite,
            "dimensions": dimensions or {},
            "flags": flags or [],
            "data_insufficient": data_insufficient,
        }

    def test_any_r5_dimension_forces_flat(self):
        from tradingagents.agents.managers.investment_director import safety_override

        result = safety_override(
            self._risk(composite=3, dimensions={"term_structure": {"level": 5}}),
            "long", 0.7,
        )
        assert result["action"] == "flat"
        assert result["confidence"] == 0.0
        assert result["max_position"] == 0.0
        assert result["r5_dimensions"] == ["term_structure"]
        assert "R5_REJECT" in result["override_rules_triggered"]

    @pytest.mark.parametrize("condition", ["composite", "delivery"])
    def test_composite_r5_and_near_delivery_force_flat(self, condition):
        from tradingagents.agents.managers.investment_director import safety_override

        risk = self._risk(
            composite=5 if condition == "composite" else 4,
            flags=[{"name": "near_delivery", "severity": "high"}]
            if condition == "delivery" else [],
        )
        result = safety_override(risk, "short", 0.8)
        assert (result["action"], result["confidence"], result["max_position"]) == ("flat", 0.0, 0.0)

    def test_data_insufficient_caps_direction_and_existing_hold(self):
        from tradingagents.agents.managers.investment_director import safety_override

        directional = safety_override(
            self._risk(composite="UNKNOWN", data_insufficient=True), "long", 0.8,
        )
        assert directional["action"] == "hold"
        assert directional["confidence"] == 0.2
        assert directional["max_position"] == 0.3

        existing_hold = safety_override(
            self._risk(composite="UNKNOWN", data_insufficient=True), "hold", 0.8,
        )
        assert existing_hold["action"] == "hold"
        assert existing_hold["confidence"] == 0.2
        assert existing_hold["overridden"] is True

    def test_no_l1_support_requires_explanation(self):
        from tradingagents.agents.managers.investment_director import safety_override

        registry = {"REF-TECH-1": {"direction": "bearish", "status": "ok"}}
        no_explanation = safety_override(
            self._risk(), "long", 0.8, analyst_registry=registry,
        )
        assert no_explanation["action"] == "hold"
        assert no_explanation["confidence"] == 0.3
        assert "COUNTER_SIGNAL_EXPLANATION_REQUIRED" in no_explanation["override_rules_triggered"]

        explained = safety_override(
            self._risk(), "long", 0.8, analyst_registry=registry,
            counter_signal_explanation="技术偏空，但库存与基差共振更强，故仅低置信度做多",
        )
        assert explained["action"] == "long"
        assert explained["confidence"] == 0.3

    def test_position_reversal_risk_caps_confidence(self):
        from tradingagents.agents.managers.investment_director import safety_override

        result = safety_override(
            self._risk(), "long", 0.7,
            analyst_registry={"REF-POSN-1": {"direction": "bullish", "status": "ok"}},
            position_structured={
                "concentration": {"reversal_risk": True},
                "risk_flags": ["高度拥挤，反转风险高"],
            },
            counter_signal_explanation="已识别拥挤风险，因此置信度降至 0.3",
        )
        assert result["action"] == "long"
        assert result["confidence"] == 0.3
        assert "POSITION_REVERSAL_RISK" in result["override_rules_triggered"]

    def test_r4_position_cap_counts_as_override(self):
        from tradingagents.agents.managers.investment_director import safety_override

        result = safety_override(
            self._risk(composite=4, flags=[{"name": "risk", "severity": "high"}]),
            "long", 0.6,
        )
        assert result["action"] == "long"
        assert result["max_position"] == 0.5
        assert result["overridden"] is True

    def test_already_flat_still_records_execution_and_rule(self, caplog):
        from tradingagents.agents.managers.investment_director import safety_override

        with caplog.at_level("INFO"):
            result = safety_override(
                self._risk(composite=5), "flat", 0.0,
            )
        assert result["executed"] is True
        assert result["action"] == "flat"
        assert "R5_REJECT" in result["override_rules_triggered"]
        assert any("[投研总监|OVERRIDE] executed=True" in record.message for record in caplog.records)


def test_investment_director_preserves_rule_card_and_audit():
    from tradingagents.agents.managers.investment_director import create_investment_director

    mock_llm = MagicMock()
    mock_llm.invoke = MagicMock(return_value=MagicMock(content=json.dumps({
        "投研备忘录": {"投研结论": {
            "方向倾向": "做多", "置信度": 0.7, "逆向信号处理": "无",
        }},
        "风险评估卡": {
            "量化风险矩阵": {"伪造": "应被忽略"},
            "风险裁定": {"建议动作": "开仓", "仓位上限": "账户30%"},
            "风险提示": ["定性提示"],
        },
        "final_decision_markdown": "- **方向**：做多\n- **置信度**：0.7",
    }, ensure_ascii=False)))
    result = create_investment_director(mock_llm)(make_commodity_state())

    assert "波动率" in result["risk_card"]["量化风险矩阵"]
    assert "伪造" not in result["risk_card"]["量化风险矩阵"]
    assert result["risk_card"]["风险提示"] == ["定性提示"]
    assert result["risk_card"]["safety_override"]["executed"] is True
    # final_decision 现在包含 research_brief（raw JSON），不再含方向/置信度标记
    assert result["final_decision"] is not None and len(str(result["final_decision"])) > 0
    assert result["research_brief"] is not None and len(str(result["research_brief"])) > 0
    # SafetyOverride 包含策略约束语义（allowed_strategies / forbidden_strategies）
    assert "allowed_strategies" in result["risk_card"]["safety_override"]
    assert "forbidden_strategies" in result["risk_card"]["safety_override"]


def test_investment_director_r5_dimension_syncs_memo_and_markdown():
    from tradingagents.agents.managers.investment_director import create_investment_director

    mock_llm = MagicMock()
    mock_llm.invoke = MagicMock(return_value=MagicMock(content=json.dumps({
        "投研备忘录": {"投研结论": {
            "方向倾向": "做多", "置信度": 0.7,
            "核心逻辑": "需求改善", "逆向信号处理": "已评估反向信号",
        }},
        "风险评估卡": {"风险裁定": {"建议动作": "开仓"}},
        "final_decision_markdown": "- **方向**:做多\n- **置信度**:0.70",
    }, ensure_ascii=False)))
    state = make_commodity_state({
        "commodity_features": _make_features(term_structure={
            "quality": {"rows": 50, "coverage": 0.75, "data_freshness_days": 1},
            "snapshot": {"carry_score": -0.7, "structure": "contango"},
        }),
    })
    result = create_investment_director(mock_llm)(state)

    assert result["risk_assessment"]["composite_risk_level"] == 3
    assert result["risk_assessment"]["dimensions"]["term_structure"]["level"] == 5
    assert result["risk_card"]["safety_override"]["overridden_action"] == "flat"
    # 新备忘录格式：风险等级/推荐关注策略/需规避策略 替代 方向倾向/置信度
    assert result["investment_memo"]["投研结论"]["风险等级"] == "R3"
    assert result["investment_memo"]["投研结论"]["推荐关注策略"] == []
    assert result["investment_memo"]["投研结论"]["需规避策略"] == [
        "单边趋势", "展期收益", "跨期套利", "波动率", "跨品种"
    ]
    # R5 约束反映在策略约束说明或核心观点中
    memo_text = str(result["investment_memo"]["投研结论"].get("策略约束说明", ""))
    memo_text += str(result["investment_memo"]["投研结论"].get("核心观点", ""))
    assert "R5" in memo_text
    # final_decision 已迁移为 research_brief 格式，不包含方向/置信度标记
    assert result["final_decision"] is not None and len(str(result["final_decision"])) > 0


def test_investment_director_missing_fields_are_safely_added():
    from tradingagents.agents.managers.investment_director import create_investment_director

    mock_llm = MagicMock()
    mock_llm.invoke = MagicMock(return_value=MagicMock(content=json.dumps({
        "投研备忘录": {}, "风险评估卡": {},
        "final_decision_markdown": "这段内容缺少标准方向和置信度字段，但长度足够触发正常解析。",
    }, ensure_ascii=False)))
    result = create_investment_director(mock_llm)(make_commodity_state())

    # final_decision 现在包含 research_brief（raw JSON），不再自动补全方向/置信度
    assert result["final_decision"] is not None and len(str(result["final_decision"])) > 0
    assert result["risk_card"]["safety_override"]["executed"] is True
    assert "allowed_strategies" in result["risk_card"]["safety_override"]


def test_investment_director_fallback_also_has_safety_audit():
    from tradingagents.agents.managers.investment_director import create_investment_director

    mock_llm = MagicMock()
    mock_llm.invoke = MagicMock(side_effect=RuntimeError("LLM 不可用"))
    result = create_investment_director(mock_llm)(make_commodity_state())

    assert result["risk_card"]["safety_override"]["executed"] is True
    assert result["risk_card"]["safety_override"]["original_llm_direction"] == "hold"
    # fallback 时 final_decision 是系统降级的研究简报，不含方向标记
    assert result["final_decision"] is not None and len(str(result["final_decision"])) > 0
    assert "策略适应性报告" in str(result["final_decision"])
    # research_brief 同步输出同一份 fallback 内容
    assert result["research_brief"] is not None and len(str(result["research_brief"])) > 0


class TestSafetyOverrideCustomData:
    """Phase 自定义数据升级: SafetyOverride 私有数据矛盾 + 过度依赖规则。"""

    @staticmethod
    def _risk(composite=2, dimensions=None, flags=None, data_insufficient=False):
        return {
            "composite_risk_level": composite,
            "dimensions": dimensions or {},
            "flags": flags or [],
            "data_insufficient": data_insufficient,
        }

    def test_custom_data_contradiction_caps_confidence(self):
        from tradingagents.agents.managers.investment_director import safety_override
        fdict = {
            "_direction": "bearish",
            "_direction_confidence": 0.7,
            "snapshot": {"as_of": "2026-07-20"},
        }
        result = safety_override(
            self._risk(), "long", 0.8, "",
            custom_data_feature_dict=fdict,
            counter_signal_explanation="用户数据滞后,可忽略",
        )
        assert "CUSTOM_DATA_CONTRADICTION" in result["override_rules_triggered"]
        assert result["confidence"] == 0.3
        assert result["max_position"] == 0.5
        assert result["custom_data_conflict"] is True
        assert result["custom_data_direction"] == "bearish"
        assert result["custom_data_as_of"] == "2026-07-20"

    def test_custom_data_contradiction_without_explanation_forces_hold(self):
        from tradingagents.agents.managers.investment_director import safety_override
        fdict = {"_direction": "bearish", "snapshot": {"as_of": "2026-07-20"}}
        result = safety_override(
            self._risk(), "long", 0.8, "",
            custom_data_feature_dict=fdict,
            counter_signal_explanation="",
        )
        assert "COUNTER_SIGNAL_EXPLANATION_REQUIRED" in result["override_rules_triggered"]
        assert result["action"] == "hold"
        assert result["confidence"] == 0.3

    def test_custom_data_aligned_does_not_trigger_contradiction(self):
        from tradingagents.agents.managers.investment_director import safety_override
        fdict = {"_direction": "bullish", "snapshot": {"as_of": "2026-07-20"}}
        result = safety_override(
            self._risk(), "long", 0.8, "",
            custom_data_feature_dict=fdict,
        )
        assert "CUSTOM_DATA_CONTRADICTION" not in result["override_rules_triggered"]
        assert result["action"] == "long"
        assert result["confidence"] == 0.8

    def test_custom_data_neutral_never_triggers_contradiction(self):
        from tradingagents.agents.managers.investment_director import safety_override
        fdict = {"_direction": "neutral", "snapshot": {"as_of": "2026-07-20"}}
        result = safety_override(
            self._risk(), "long", 0.8, "",
            custom_data_feature_dict=fdict,
        )
        assert "CUSTOM_DATA_CONTRADICTION" not in result["override_rules_triggered"]
        assert result["action"] == "long"

    def test_custom_data_overreliance_warning_only(self):
        from tradingagents.agents.managers.investment_director import safety_override
        brief = (
            "## 核心观点\n\n"
            "根据用户上传数据,看多。\n\n"
            "用户上传数据显示库存低。\n\n"
            "用户数据表明方向偏多。\n\n"
            "用户上传的数据强化了判断。\n"
        )
        result = safety_override(
            self._risk(), "long", 0.7, brief,
        )
        assert "CUSTOM_DATA_OVERRELIANCE" in result["override_rules_triggered"]
        # 不改决策
        assert result["action"] == "long"
        assert result["confidence"] == 0.7
        assert result["max_position"] == 1.0
        assert result["custom_data_overreliance"]["warning_only"] is True
        assert result["custom_data_overreliance"]["mentions"] >= 3

    def test_custom_data_overreliance_low_mentions_no_trigger(self):
        from tradingagents.agents.managers.investment_director import safety_override
        brief = (
            "技术面偏多。\n\n"
            "库存中性。\n\n"
            "基差略偏弱。\n\n"
            "用户上传数据仅作参考。\n"
        )
        result = safety_override(
            self._risk(), "long", 0.7, brief,
        )
        assert "CUSTOM_DATA_OVERRELIANCE" not in result["override_rules_triggered"]

    def test_no_custom_data_feature_dict_no_conflict_audit(self):
        """不传 custom_data_feature_dict 时 audit 字段全部为安全默认值。"""
        from tradingagents.agents.managers.investment_director import safety_override
        result = safety_override(self._risk(), "long", 0.8, "")
        assert result["custom_data_direction"] == "neutral"
        assert result["custom_data_conflict"] is False
        assert result["custom_data_overreliance"]["warning_only"] is True
        assert result["custom_data_overreliance"]["mentions"] == 0
        assert result["custom_data_as_of"] is None
        assert "CUSTOM_DATA_CONTRADICTION" not in result["override_rules_triggered"]
        assert "CUSTOM_DATA_OVERRELIANCE" not in result["override_rules_triggered"]
