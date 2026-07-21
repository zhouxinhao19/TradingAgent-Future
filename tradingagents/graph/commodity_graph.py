"""
commodity_graph.py — CommodityTradingAgentsGraph 子图 (Phase 3b-ii-C)

继承自 TradingAgentsGraph,复用 LLM/内存初始化,重写:
  1. GraphSetup — 注册 4 个 commodity analyst + 投研总监节点
  2. Propagator — 注入 commodity state (asset_type + full_symbol + commodity_features + latest_news)
  3. propagate() — 接受 full_symbol (非 ticker),commodity 默认参数

设计要点:
  - stock 路径零改动(继承父类初始化 + 父类 GraphSetup 保持不变)
  - commodity 路径独立:CommodityGraphSetup + CommodityPropagator
  - commodity 不需要 tool_nodes(4 analyst 读 features,LLM 必调但不调工具)
  - 决策链节点 commodity 化(3b-ii-B)已自动通过 state['asset_type'] 切换 prompt

Phase Agent 改造(2026-07-19):
  - Checkpointer 支持: MemorySaver(默认) / SqliteSaver(env CHECKPOINTER_BACKEND=sqlite),
    环境变量 CHECKPOINTER_BACKEND=sqlite 启用持久化断点续传
  - SafetyOverride: 风控硬约束二审
  - L2 Prompt 精简化: 结构化摘要替代完整 Markdown
  - L1 并行化: 4 个 analyst fan-out
"""
from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from tradingagents.agents.utils.agent_states import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
)
from tradingagents.agents.analysts.commodity import (
    create_fundamental_analyst,
    create_news_analyst,
    create_position_analyst,
    create_technical_analyst,
)
from tradingagents.agents.managers.investment_director import (
    create_investment_director,
    extract_decision_fields,
    normalize_direction,
)
from tradingagents.agents.managers.research_manager import create_research_manager

from tradingagents.utils.logging_init import get_logger

from .propagation import Propagator
from .setup import GraphSetup
from .trading_graph import TradingAgentsGraph

logger = get_logger("default")

# ---- retry 配置(环境变量) ----
_LLM_MAX_RETRIES = int(os.environ.get("LLM_MAX_RETRIES", "2"))
_LLM_L1_TIMEOUT = int(os.environ.get("LLM_L1_TIMEOUT", "60"))
_LLM_L2_TIMEOUT = int(os.environ.get("LLM_L2_TIMEOUT", "90"))
_LLM_L3_TIMEOUT = int(os.environ.get("LLM_L3_TIMEOUT", "90"))


def _wrap_llm_with_retry(llm, label: str = "LLM", default_timeout: int = 60):
    """给 LLM 对象的 invoke/ainvoke 方法加上超时和自动重试。

    Args:
        llm: LangChain LLM 对象
        label: 日志标签
        default_timeout: 默认超时秒数

    Returns:
        包装后的 LLM 对象（保留原接口，仅替换 invoke/ainvoke）
    """
    import asyncio
    from functools import wraps

    original_invoke = llm.invoke
    original_ainvoke = getattr(llm, "ainvoke", None)

    @wraps(original_invoke)
    def _invoke_with_retry(*args, **kwargs):
        max_retries = _LLM_MAX_RETRIES
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                return original_invoke(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    logger.warning(
                        f"⚠️ {label} LLM 调用失败(第{attempt+1}/{max_retries+1}次重试前): {e}"
                    )
                else:
                    logger.error(
                        f"❌ {label} LLM {max_retries+1}次重试均失败: {e}"
                    )
        raise last_error  # noqa: B018

    @wraps(original_ainvoke)
    async def _ainvoke_with_retry(*args, **kwargs):
        max_retries = _LLM_MAX_RETRIES
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                return await original_ainvoke(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    logger.warning(
                        f"⚠️ {label} Async LLM 调用失败(第{attempt+1}/{max_retries+1}次重试前): {e}"
                    )
                else:
                    logger.error(
                        f"❌ {label} Async LLM {max_retries+1}次重试均失败: {e}"
                    )
        raise last_error  # noqa: B018

    # NormalizedChatOpenAI 是 Pydantic v2 模型，直接属性赋值会触发字段校验失败
    # 使用 object.__setattr__ 绕过 Pydantic 的 __setattr__ 拦截
    object.__setattr__(llm, "invoke", _invoke_with_retry)
    if original_ainvoke is not None:
        object.__setattr__(llm, "ainvoke", _ainvoke_with_retry)
    return llm

def _create_checkpointer():
    """创建 Graph checkpointer 实例。

    环境变量 CHECKPOINTER_BACKEND=memory(默认)|sqlite|none
    - memory: MemorySaver，仅存进程内存，重启丢失
    - sqlite: SqliteSaver，持久化到文件，重启可恢复（需安装 langgraph-checkpoint-sqlite）
    - none: 不创建 checkpointer（适用于 E2E 测试，避免 numpy 类型 msgpack 序列化失败）
    """
    backend = os.environ.get("CHECKPOINTER_BACKEND", "memory").lower()
    if backend == "none":
        return None
    if backend == "sqlite":
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver
            return SqliteSaver.from_conn_string("checkpoints.sqlite")
        except ImportError:
            logger.warning("SqliteSaver 未安装，回退 MemorySaver")
            return MemorySaver()
    return MemorySaver()


def _compute_contract_expiry(full_symbol: str, trade_date_str: str) -> Dict[str, Any]:
    """从合约代码估算到期日，返回到期警告。

    Args:
        full_symbol: 如 CU2507.SHF, RB2510.SHF
        trade_date_str: 交易日期 "2026-07-19"

    Returns:
        dict: {"days_to_expiry": N, "warning": "..."}
        如果无法解析或距离到期>30天, warning为空字符串
    """
    import re
    from datetime import date, datetime

    default = {"days_to_expiry": None, "warning": ""}

    m = re.search(r'(\d{2})(\d{2})', full_symbol.split('.')[0])
    if not m:
        return default

    year = 2000 + int(m.group(1))
    month = int(m.group(2))
    if month < 1 or month > 12:
        return default

    try:
        trade_date = datetime.strptime(trade_date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        try:
            trade_date = date.fromisoformat(str(trade_date_str))
        except (ValueError, TypeError):
            return default

    # 假设交割日为该月 15 日（实际以交易所日历为准）
    try:
        delivery = date(year, month, 15)
    except ValueError:
        return default

    days_to_expiry = (delivery - trade_date).days

    warning = ""
    if days_to_expiry < 0:
        # 已到期：用主力连续数据重新分析可能更合适
        warning = f"⚠️ 合约 {full_symbol} 已于 {delivery.isoformat()} 到期（{-days_to_expiry} 天前），建议使用主力连续合约(-m 后缀)"
    elif days_to_expiry < 10:
        warning = f"⚠️ 合约 {full_symbol} 距到期仅 {days_to_expiry} 天（{delivery.isoformat()}），临近交割月流动性风险高，建议切换主力连续合约"
    elif days_to_expiry < 30:
        warning = f"⚠️ 合约 {full_symbol} 距到期 {days_to_expiry} 天，注意交割月限仓和保证金提高"

    return {"days_to_expiry": days_to_expiry, "warning": warning, "delivery_date": delivery.isoformat()}


# === Propagator ===

class CommodityPropagator(Propagator):
    """支持 asset_type='commodity' 的状态初始化。"""

    def create_initial_state(
        self,
        full_symbol: str,
        trade_date: str,
        asset_type: str = "commodity",
        commodity_features: Optional[Dict[str, Any]] = None,
        latest_news: Optional[List[Dict[str, Any]]] = None,
        variety_name: str = "",
        exchange: str = "",
        category: str = "",
        quote_unit: str = "",
    ) -> Dict[str, Any]:
        """构造 commodity 路径的初始 state。

        字段说明:
          - company_of_interest: 复用 stock 字段(决策链节点读这个字段)
          - full_symbol: 大宗商品专用字段(如 RB2501.SHF)
          - asset_type: 'commodity' 触发决策链 commodity prompt 分支
          - commodity_features: features 层 6 模块输出
          - latest_news: 来自 Propagator 调用 provider.get_futures_news()
        """
        from langchain_core.messages import HumanMessage

        analysis_request = (
            f"请对大宗商品期货 {full_symbol} 进行全面分析,交易日期为 {trade_date}。"
        )

        # 计算 news_summary(利多/利空/高重要度 条数统计,供 L1 分析师引用)
        news_summary = ""
        if latest_news:
            _pos = sum(1 for e in latest_news if e.get("llm_sentiment", e.get("sentiment")) == "positive")
            _neg = sum(1 for e in latest_news if e.get("llm_sentiment", e.get("sentiment")) == "negative")
            _high = sum(1 for e in latest_news if e.get("llm_importance") == "high")
            news_summary = f"当前新闻情感: 利多{_pos}条 利空{_neg}条 高重要度{_high}条。"

        # Phase Agent 改造: 合约到期风险检测
        contract_expiry_warning = _compute_contract_expiry(full_symbol, trade_date)

        return {
            "messages": [HumanMessage(content=analysis_request)],
            "company_of_interest": full_symbol,  # 复用 stock 字段
            "full_symbol": full_symbol,
            "asset_type": asset_type,
            "variety_name": variety_name or full_symbol,
            "exchange": exchange,
            "category": category,
            "quote_unit": quote_unit,
            "trade_date": str(trade_date),
            "investment_debate_state": InvestDebateState(
                {"history": "", "current_response": "", "count": 0}
            ),
            "risk_debate_state": RiskDebateState(
                {
                    "history": "",
                    "current_risky_response": "",
                    "current_safe_response": "",
                    "current_neutral_response": "",
                    "count": 0,
                }
            ),
            "market_report": "",
            "fundamentals_report": "",
            "fundamentals_structured": {},
            "sentiment_report": "",
            "position_report": "",
            "position_structured": {},
            "news_report": "",
            "commodity_features": commodity_features or {},
            "latest_news": latest_news or [],
            "analyst_registry": {},
            "news_summary": news_summary,
            "contract_expiry_warning": contract_expiry_warning,
        }


# === GraphSetup ===

class CommodityGraphSetup:
    """注册 4 个 commodity analyst + 决策链节点 + CIO。

    不需要 tool_nodes — commodity analyst 从 state['commodity_features'] 读取,
    决策链节点 commodity 化通过 state['asset_type'] 切换 prompt。
    """

    def __init__(
        self,
        quick_thinking_llm,
        deep_thinking_llm,
        invest_judge_memory,
        risk_manager_memory,
        conditional_logic,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.invest_judge_memory = invest_judge_memory
        self.risk_manager_memory = risk_manager_memory
        self.conditional_logic = conditional_logic
        self.config = config or {}

    def setup_graph(self):
        """构造并编译 commodity 子图。"""
        # === 创建 Checkpointer ===
        checkpointer = _create_checkpointer()

        # === 4 个 commodity analyst 节点 ===
        tech_analyst = create_technical_analyst(self.quick_thinking_llm)
        fund_analyst = create_fundamental_analyst(self.quick_thinking_llm)
        pos_analyst = create_position_analyst(self.quick_thinking_llm)
        news_analyst = create_news_analyst(self.quick_thinking_llm)

        # === 决策链节点(commodity 化通过 state['asset_type']) ===
        rm_node = create_research_manager(self.deep_thinking_llm, self.invest_judge_memory)

        # === Phase 4: 投研总监（替代 L3-L5 风控辩论 → 风控经理 → CIO） ===
        id_node = create_investment_director(self.deep_thinking_llm)

        # === 构造 StateGraph ===
        workflow = StateGraph(AgentState)

        # 注册 analyst 节点(命名跟 stock 一致,便于 SSE 兼容)
        workflow.add_node("Technical Analyst", tech_analyst)
        workflow.add_node("Fundamentals Analyst", fund_analyst)
        workflow.add_node("Sentiment Analyst", pos_analyst)  # 持仓→情绪字段
        workflow.add_node("News Analyst", news_analyst)

        # 注册决策链节点
        workflow.add_node("Research Manager", rm_node)

        # 注册投研总监（Phase 4，替代 L3-L5 共 5 节点 + 7 条边）
        workflow.add_node("Investment Director", id_node)

        # === 边(commodity 路径:4 个 L1 并行 fan-out + 汇聚到 Research Manager) ===
        # Phase Agent 改造: 4 个 L1 analyst 从 START 直接 fan-out(无依赖,各自读 commodity_features)
        workflow.add_edge(START, "Technical Analyst")
        workflow.add_edge(START, "Fundamentals Analyst")
        workflow.add_edge(START, "Sentiment Analyst")
        workflow.add_edge(START, "News Analyst")

        # 4 个 analyst 全部完成后汇聚到 Research Manager（推理分析师）
        # LangGraph 的 fan-in 自动等待所有前驱节点完成，无需手动 barrier
        workflow.add_edge("Technical Analyst", "Research Manager")
        workflow.add_edge("Fundamentals Analyst", "Research Manager")
        workflow.add_edge("Sentiment Analyst", "Research Manager")
        workflow.add_edge("News Analyst", "Research Manager")
        workflow.add_edge("Research Manager", "Investment Director")
        workflow.add_edge("Investment Director", END)

        return workflow.compile(checkpointer=checkpointer)


def _effective_research_conclusion(final_state: Dict[str, Any]) -> Dict[str, Any]:
    """从最终 state 提取研究结论，SafetyOverride 审计优先。

    返回包含策略约束语义的新结构，同时保留 action/confidence 向后兼容。
    """
    research_brief = final_state.get("research_brief", "") or final_state.get("final_decision", "")
    strategy_matrix = final_state.get("strategy_matrix", []) or []
    fact_cards = final_state.get("fact_cards", []) or []
    contradiction_map = final_state.get("contradiction_map", []) or []

    risk_card = final_state.get("risk_card", {}) or {}
    audit = risk_card.get("safety_override", {}) if isinstance(risk_card, dict) else {}
    effective_audit = isinstance(audit, dict) and audit.get("executed") is True

    # 从 SafetyOverride audit 读取策略约束（新语义）
    risk_tier = audit.get("risk_tier", "?") if effective_audit else "?"
    allowed = audit.get("allowed_strategies", []) if effective_audit else []
    forbidden = audit.get("forbidden_strategies", []) if effective_audit else []

    # 向后兼容：仍提取 action/confidence（旧 consumer 不崩溃）
    from tradingagents.agents.managers.investment_director import extract_decision_fields
    parsed = extract_decision_fields(research_brief)
    compat_action = parsed["action"]
    compat_confidence = parsed["confidence"]
    if effective_audit:
        compat_action = normalize_direction(
            audit.get("overridden_action", audit.get("action", compat_action))
        )
        try:
            compat_confidence = float(
                audit.get("overridden_confidence", audit.get("confidence", compat_confidence))
            )
            if not 0.0 <= compat_confidence <= 1.0:
                compat_confidence = 0.0
        except (TypeError, ValueError):
            compat_confidence = 0.0

    # 核心叙事：从 research_brief 提取第一段
    core_narrative = ""
    if research_brief:
        lines = research_brief.split("\n")
        for line in lines:
            stripped = line.strip().strip("#").strip()
            if stripped and len(stripped) > 10:
                core_narrative = stripped[:200]
                break

    conclusion = {
        "risk_tier": risk_tier,
        "allowed_strategies": allowed,
        "forbidden_strategies": forbidden,
        "strategy_matrix": strategy_matrix,
        "core_narrative": core_narrative,
        "research_brief_raw": research_brief[:500] if research_brief else "",
        "fact_cards": fact_cards,
        "contradiction_map": contradiction_map,
        # 向后兼容
        "action": compat_action,
        "confidence": compat_confidence,
        "reasoning": core_narrative or research_brief[:200] if research_brief else "(CIO 未输出)",
        "raw_text": research_brief[:500] if research_brief else "",
    }

    # Fail-closed：SafetyOverride 审计缺失时检测硬风险
    if not effective_audit:
        risk_assessment = final_state.get("risk_assessment", {}) or {}
        dimensions = risk_assessment.get("dimensions", {})
        if not isinstance(dimensions, dict):
            dimensions = {}
        has_r5 = any(
            isinstance(d, dict) and d.get("level") == 5
            for d in dimensions.values()
        )
        composite = risk_assessment.get("composite_risk_level")
        flags = risk_assessment.get("flags", [])
        near_delivery = any(
            isinstance(f, dict) and f.get("name") == "near_delivery"
            for f in (flags if isinstance(flags, list) else [])
        )
        if has_r5 or composite in (5, "R5") or near_delivery:
            logger.error(
                "[CommodityTradingAgentsGraph|OVERRIDE] SafetyOverride 审计缺失，"
                "检测到 R5/near_delivery，fail closed"
            )
            conclusion.update({
                "risk_tier": f"R{composite}" if isinstance(composite, int) else "R5",
                "allowed_strategies": [],
                "forbidden_strategies": ["单边趋势", "展期收益", "跨期套利", "波动率", "跨品种"],
                "action": "flat",
                "confidence": 0.0,
            })
        elif risk_assessment.get("data_insufficient"):
            conclusion.update({
                "risk_tier": "?",
                "allowed_strategies": ["展期收益", "跨期套利", "波动率", "跨品种"],
                "forbidden_strategies": ["单边趋势"],
                "action": "hold",
                "confidence": 0.0,
            })

    return conclusion


# =============================================================================
# 交易计划 / 最终交易决策派生（纯规则，零 LLM）
#
# commodity 决策链在 Phase 4 已简化为「4 分析师 → 推理经理 → 投研总监 → END」，
# 删除了 stock 路径里写 trader_investment_plan / final_trade_decision 的
# Trader / Risk Manager 节点。为避免报告出现永久空白模块，这里用投研总监已产出的
# research_brief / strategy_matrix / risk_card.safety_override / risk_assessment
# 派生出两份 Markdown（不新增任何 LLM 调用）。
#
# 注意：投研总监被 prompt 硬约束「禁止输出交易指令」，因此 final_trade_decision 的
# 方向/置信度/仓位一律取自规则引擎 SafetyOverride 审计，而非 LLM 文本。
# =============================================================================

_DERIVED_DISCLAIMER = (
    "> 本内容由规则引擎自投研总监的策略产出派生，非人工交易指令；"
    "仅供研究与教学，不构成投资建议。"
)

_FITNESS_ICON = {
    "推荐关注": "🟢 推荐关注",
    "谨慎推荐": "🟡 谨慎推荐",
    "不推荐": "🔴 不推荐",
    "数据不足": "⚪ 数据不足",
}


def _get_safety_override(final_state: Dict[str, Any]) -> Dict[str, Any]:
    """从 final_state 提取 SafetyOverride 审计（与 _effective_research_conclusion 同源）。"""
    risk_card = final_state.get("risk_card", {}) or {}
    if not isinstance(risk_card, dict):
        return {}
    audit = risk_card.get("safety_override", {})
    return audit if isinstance(audit, dict) else {}


def _render_strategy_matrix_table(strategy_matrix: List[Any]) -> str:
    """把 5 策略适应性矩阵渲染成 Markdown 管道表格。"""
    if not strategy_matrix or not isinstance(strategy_matrix, list):
        return "（策略适应性矩阵数据不可用）"
    lines = ["| 策略 | 适应性 | 核心判据 |", "| :--- | :--- | :--- |"]
    for item in strategy_matrix:
        if not isinstance(item, dict):
            continue
        name = str(item.get("strategy", "?"))
        fitness = str(item.get("fitness", "?"))
        fitness_disp = _FITNESS_ICON.get(fitness, fitness)
        rationale = str(item.get("rationale", "") or "")
        conditions = item.get("key_conditions", []) or []
        if isinstance(conditions, list) and conditions:
            cond_text = "；".join(str(c) for c in conditions)
            judge = f"{rationale}（{cond_text}）" if rationale else cond_text
        else:
            judge = rationale or "-"
        # 单元格内换行/竖线会破坏表格，做转义
        judge = judge.replace("\n", " ").replace("|", "/")
        lines.append(f"| {name} | {fitness_disp} | {judge} |")
    return "\n".join(lines)


def _render_risk_dimensions_table(risk_assessment: Dict[str, Any]) -> str:
    """把 6 维量化风险矩阵渲染成 Markdown 管道表格。"""
    if not isinstance(risk_assessment, dict):
        return ""
    dimensions = risk_assessment.get("dimensions", {})
    if not isinstance(dimensions, dict) or not dimensions:
        return ""
    lines = ["| 风险维度 | 等级 | 说明 |", "| :--- | :--- | :--- |"]
    for dim_name, dim in dimensions.items():
        if not isinstance(dim, dict):
            continue
        level = dim.get("level", "?")
        desc = str(dim.get("reason", dim.get("desc", "")) or "-")
        desc = desc.replace("\n", " ").replace("|", "/")
        lines.append(f"| {dim_name} | R{level} | {desc} |")
    return "\n".join(lines)


def _first_narrative_paragraph(research_brief: str) -> str:
    """取 research_brief 中第一段有效正文（跳过标题行），作为核心叙事。"""
    if not research_brief:
        return ""
    for block in research_brief.split("\n"):
        stripped = block.strip().lstrip("#").strip()
        if stripped and len(stripped) > 10 and not stripped.startswith("|"):
            return stripped[:300]
    return ""


def _compose_trader_plan(final_state: Dict[str, Any]) -> str:
    """派生「交易计划」Markdown：策略适应性报告全文 + 策略矩阵表 + 风险维度表 + 投研结论摘要。"""
    full_symbol = final_state.get("full_symbol", "") or "标的"
    research_brief = final_state.get("research_brief", "") or final_state.get("final_decision", "")
    strategy_matrix = final_state.get("strategy_matrix", []) or []
    risk_assessment = final_state.get("risk_assessment", {}) or {}
    investment_memo = final_state.get("investment_memo", {}) or {}

    parts: List[str] = [f"# {full_symbol} 交易计划", "", _DERIVED_DISCLAIMER, ""]

    # 主体：投研总监的策略适应性报告全文
    if research_brief:
        parts.append(research_brief.strip())
    else:
        parts.append("（投研总监未产出策略报告）")

    # 附录 A：策略适应性矩阵表
    parts.extend(["", "## 附录 A · 策略适应性矩阵", "", _render_strategy_matrix_table(strategy_matrix)])

    # 附录 B：量化风险维度
    risk_table = _render_risk_dimensions_table(risk_assessment)
    if risk_table:
        parts.extend(["", "## 附录 B · 量化风险维度", "", risk_table])

    # 附录 C：投研结论摘要
    conclusion = investment_memo.get("投研结论", {}) if isinstance(investment_memo, dict) else {}
    if isinstance(conclusion, dict) and conclusion:
        summary_lines: List[str] = []
        core_view = conclusion.get("核心观点")
        if core_view:
            summary_lines.append(f"- **核心观点**：{core_view}")
        for label, key in (("推荐关注策略", "推荐关注策略"), ("需规避策略", "需规避策略")):
            val = conclusion.get(key)
            if isinstance(val, list) and val:
                summary_lines.append(f"- **{label}**：{'、'.join(str(v) for v in val)}")
        signals = conclusion.get("风险信号")
        if isinstance(signals, list) and signals:
            summary_lines.append(f"- **风险信号**：{'；'.join(str(s) for s in signals)}")
        if summary_lines:
            parts.extend(["", "## 附录 C · 投研结论摘要", ""] + summary_lines)

    return "\n".join(parts).strip()


def _compose_final_decision(final_state: Dict[str, Any]) -> str:
    """派生「最终交易决策」Markdown：方向/置信度/最大仓位/风险等级 + 核心叙事 + 风险点 + 策略约束。

    方向/置信度/仓位一律取自规则引擎 SafetyOverride 审计（投研总监禁止输出交易指令）。
    """
    full_symbol = final_state.get("full_symbol", "") or "标的"
    audit = _get_safety_override(final_state)
    research_brief = final_state.get("research_brief", "") or final_state.get("final_decision", "")

    # 方向：overridden_action 优先，退回 action
    raw_action = audit.get("overridden_action", audit.get("action", "hold"))
    direction = normalize_direction(raw_action)
    direction_cn = {"long": "做多", "short": "做空", "hold": "持有", "flat": "平仓"}.get(direction, "持有")

    # 置信度：overridden_confidence 优先，退回 confidence
    try:
        confidence = float(audit.get("overridden_confidence", audit.get("confidence", 0.0)))
        if not 0.0 <= confidence <= 1.0:
            confidence = 0.0
    except (TypeError, ValueError):
        confidence = 0.0

    # 最大仓位
    max_pos_pct = audit.get("max_position_pct")
    if max_pos_pct is None:
        mp = audit.get("max_position")
        max_pos_pct = float(mp) * 100 if isinstance(mp, (int, float)) else None

    risk_tier = audit.get("risk_tier", "?") or "?"
    allowed = audit.get("allowed_strategies", []) or []
    forbidden = audit.get("forbidden_strategies", []) or []
    constraints = audit.get("strategy_constraints", "") or ""
    rules = audit.get("override_rules_triggered", []) or []

    parts: List[str] = [f"# {full_symbol} 最终交易决策", "", _DERIVED_DISCLAIMER, ""]

    # 核心决策要点
    parts.append("## 决策要点")
    parts.append("")
    parts.append(f"- **方向**：{direction_cn}")
    parts.append(f"- **置信度**：{confidence:.2f}")
    if max_pos_pct is not None:
        parts.append(f"- **建议最大仓位**：{max_pos_pct:.0f}%")
    parts.append(f"- **风险等级**：{risk_tier}")
    if isinstance(allowed, list) and allowed:
        parts.append(f"- **允许策略**：{'、'.join(str(s) for s in allowed)}")
    if isinstance(forbidden, list) and forbidden:
        parts.append(f"- **禁止策略**：{'、'.join(str(s) for s in forbidden)}")

    # 核心叙事
    narrative = _first_narrative_paragraph(research_brief)
    if narrative:
        parts.extend(["", "## 核心叙事", "", narrative])

    # 触发的风险规则
    if isinstance(rules, list) and rules:
        parts.extend(["", "## 触发的风险规则", ""])
        parts.extend(f"- {r}" for r in rules)

    # 策略约束说明
    if constraints and constraints not in ("无额外策略约束",):
        parts.extend(["", "## 策略约束说明", "", str(constraints)])

    if not audit:
        parts.extend(["", "> ⚠️ 未获得 SafetyOverride 审计，以上为安全默认值（持有/0 仓位倾向）。"])

    return "\n".join(parts).strip()


# === 主类 ===

class CommodityTradingAgentsGraph(TradingAgentsGraph):
    """大宗商品期货分析图主类。

    用法:
        graph = CommodityTradingAgentsGraph(debug=True, config=config)
        final_state, decision = graph.propagate(
            full_symbol="RB2501.SHF",
            trade_date="2026-07-14",
            commodity_features=features_dict,
            latest_news=news_list,
        )
    """

    def __init__(self, debug: bool = False, config: Optional[Dict[str, Any]] = None):
        # 用 ["market"] 占位避免父类 ValueError,然后立刻覆盖 graph
        super().__init__(selected_analysts=["market"], debug=debug, config=config)

        # 给 LLM 加超时和重试包装 (应用层防御, 不穿透到 LangChain 底层 client)
        self.quick_thinking_llm = _wrap_llm_with_retry(
            self.quick_thinking_llm, "快速", _LLM_L1_TIMEOUT
        )
        self.deep_thinking_llm = _wrap_llm_with_retry(
            self.deep_thinking_llm, "深度(L2/L3)", _LLM_L2_TIMEOUT
        )

        # 替换为 commodity setup + propagator
        self.graph_setup = CommodityGraphSetup(
            self.quick_thinking_llm,
            self.deep_thinking_llm,
            self.invest_judge_memory,
            self.risk_manager_memory,
            self.conditional_logic,
            self.config,
        )
        self.graph = self.graph_setup.setup_graph()
        self.propagator = CommodityPropagator()
        self.full_symbol = None

        logger.info("🌾 [CommodityTradingAgentsGraph] 初始化完成")

    # === 进度映射(覆盖父类,适配 commodity 节点名) ===
    _COMMODITY_NODE_MAPPING = {
        "Technical Analyst": "技术分析师",
        "Fundamentals Analyst": "产业分析师",
        "Sentiment Analyst": "持仓情绪分析师",
        "News Analyst": "新闻分析师",
        "Research Manager": "推理分析师",
        "Investment Director": "投研总监",
    }

    def _send_progress_update(self, chunk, progress_callback):
        """商品专用进度更新 — 覆盖父类同名方法。"""
        try:
            if not isinstance(chunk, dict):
                return
            node_name = next((k for k in chunk if not k.startswith("__")), None)
            if not node_name:
                return
            if "__end__" in chunk:
                progress_callback("📊 生成报告")
                return
            msg = self._COMMODITY_NODE_MAPPING.get(node_name)
            if msg is None:
                return  # 跳过未知节点(commodity 无 tools/MsgClear 节点, 但兼容)
            progress_callback(msg)
        except Exception:
            logger.warning(f"进度更新异常(commodity)", exc_info=True)

    def propagate(
        self,
        full_symbol: str,
        trade_date: str,
        commodity_features: Optional[Dict[str, Any]] = None,
        latest_news: Optional[List[Dict[str, Any]]] = None,
        variety_name: str = "",
        exchange: str = "",
        category: str = "",
        quote_unit: str = "",
        progress_callback: Optional[Callable] = None,
        task_id: Optional[str] = None,
        auto_features: bool = False,
        provider: Optional[Any] = None,
    ):
        """运行 commodity 分析图。

        Args:
            full_symbol: 完整合约代码(如 RB2501.SHF)
            trade_date: 交易日期
            commodity_features: features 层 6 模块输出(可选)
            latest_news: 新闻列表(可选,用于 news_analyst)
            variety_name: 品种中文名(如 螺纹钢)
            exchange: 交易所代码(SHF/DCE/CZCE/INE/GFEX/CFFEX)
            category: 行业分类
            quote_unit: 报价单位(元/吨 等)
            progress_callback: 进度回调
            task_id: 任务 ID
            auto_features: True 时从 provider 自动拉数据并填充 features/news。
                          仅补缺(用户已显式传入的参数不会被覆盖)。
            provider: 已 connect() 的 BaseCommodityDataProvider,
                      auto_features=True 时必传。

        Returns:
            (final_state, decision)
        """
        self.full_symbol = full_symbol
        logger.info(f"🌾 [CommodityTradingAgentsGraph] propagate: {full_symbol} @ {trade_date}")

        # ---- auto_features:从 provider 自动补 features/news ----
        if auto_features and provider is not None:
            try:
                import asyncio
                from tradingagents.features import compute_all_features_from_provider

                aggregated = asyncio.run(compute_all_features_from_provider(
                    provider, full_symbol, trade_date
                ))
                # 仅补缺,保留显式传入
                if commodity_features is None:
                    commodity_features = aggregated.get("features", {}) or {}
                if latest_news is None:
                    try:
                        latest_news = asyncio.run(provider.get_futures_news("all", 100)) or []
                    except Exception as e:  # noqa: BLE001
                        logger.warning(f"⚠️ provider.get_futures_news 失败: {e}")
                        latest_news = []
                logger.info(
                    f"✅ auto_features 加载完成 (success={aggregated.get('success')}, "
                    f"modules={list((aggregated.get('features') or {}).keys())})"
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"❌ auto_features 拉取失败: {e}", exc_info=True)

        # ---- 转换 numpy 类型为 Python 原生（MemorySaver msgpack 兼容） ----
        if commodity_features is not None:
            import numpy as np

            def _to_native(o):
                """递归将 numpy 类型转为 Python 原生类型（MemorySaver msgpack 兼容）。"""
                if isinstance(o, (np.integer,)):
                    return int(o)
                if isinstance(o, (np.floating,)):
                    return float(o)
                if isinstance(o, (np.ndarray,)):
                    return o.tolist()
                if isinstance(o, dict):
                    return {k: _to_native(v) for k, v in o.items()}
                if isinstance(o, (list, tuple)):
                    return [_to_native(v) for v in o]
                return o
            commodity_features = _to_native(commodity_features)

        init_state = self.propagator.create_initial_state(
            full_symbol=full_symbol,
            trade_date=trade_date,
            asset_type="commodity",
            commodity_features=commodity_features,
            latest_news=latest_news,
            variety_name=variety_name,
            exchange=exchange,
            category=category,
            quote_unit=quote_unit,
        )

        # 调用 stream 模式获取节点级进度(简化为仅 final state)
        args = self.propagator.get_graph_args(use_progress_callback=bool(progress_callback))
        trace: List[Dict[str, Any]] = []
        final_state: Optional[Dict[str, Any]] = None

        # 使用 task_id 或 symbol+date 构造 thread_id，供 Checkpointer 断点续传
        _thread_id = task_id or f"{full_symbol}_{trade_date}"
        stream_mode = args.get("stream_mode", "values")
        _run_config = {
            "configurable": {"thread_id": _thread_id},
            "recursion_limit": args.get("config", {}).get("recursion_limit", 100),
        }

        for chunk in self.graph.stream(init_state, config=_run_config, stream_mode=stream_mode):
            if progress_callback and args.get("stream_mode") == "updates":
                self._send_progress_update(chunk, progress_callback)
                if final_state is None:
                    final_state = init_state.copy()
                for node_name, node_update in chunk.items():
                    if not node_name.startswith("__"):
                        final_state.update(node_update)
            else:
                trace.append(chunk)
                final_state = chunk

        if not trace and final_state is None:
            final_state = init_state
        elif trace:
            final_state = trace[-1]

        # Step 10: 注入证据链(纯规则提取,零 LLM 调用)
        try:
            final_state["evidence_chain"] = build_evidence_chain(final_state)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"⚠️ build_evidence_chain 失败: {e}")
            final_state["evidence_chain"] = {"summary": {}, "layers": {}, "error": str(e)}

        # Step 10.5: 派生 交易计划 / 最终交易决策（纯规则，零 LLM）
        # commodity 链路无 Trader/Risk Manager 节点，用投研总监策略产出派生这两份 Markdown，
        # 避免报告出现永久空白模块。
        try:
            final_state["trader_investment_plan"] = _compose_trader_plan(final_state)
            final_state["final_trade_decision"] = _compose_final_decision(final_state)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"⚠️ 派生 trader_plan/final_decision 失败: {e}")

        # 构造决策摘要(CIO 输出在 state['final_decision'])
        decision = self._extract_decision(final_state)

        logger.info(f"✅ [CommodityTradingAgentsGraph] 完成: {full_symbol}")
        return final_state, decision

    def _extract_decision(self, final_state: Dict[str, Any]) -> Dict[str, Any]:
        """从最终 state 提取研究结论，SafetyOverride 审计优先。"""
        return _effective_research_conclusion(final_state)


# =============================================================================
# build_evidence_chain — 纯规则提取三层证据链 JSON（Step 10 证据链可视化）
# =============================================================================

def build_evidence_chain(final_state: Dict[str, Any]) -> Dict[str, Any]:
    """从最终 state 提取结构化三层证据链 JSON，供前端 Timeline 渲染。

    Args:
        final_state: propagate() 返回的最终 state dict

    Returns:
        dict，形如:
        {
            "summary": { "symbol", "variety", "date", "final_action", "confidence" },
            "layers": {
                "L1": [ {id, name, direction, confidence, calibrated_confidence, status, key_metrics, signals}, ... ],
                "L2": { "估值驱动矩阵": [...], "多空对照表": [...], "情景推演": {...}, "L1_conflict_summary": "..." },
                "L3": { "risk_assessment": {...}, "final_decision": "...", "safety_override": {...} },
            }
        }
    """
    import json
    import re

    symbol = final_state.get("full_symbol", "")
    variety = final_state.get("variety_name", "")
    trade_date = final_state.get("trade_date", "")
    registry = final_state.get("analyst_registry", {}) or {}
    features = final_state.get("commodity_features", {}) or {}
    final_decision = final_state.get("final_decision", "")
    research_brief = final_state.get("research_brief", "") or final_decision
    risk_assessment = final_state.get("risk_assessment", {}) or {}
    strategy_matrix = final_state.get("strategy_matrix", []) or []
    fact_cards = final_state.get("fact_cards", []) or []
    contradiction_map = final_state.get("contradiction_map", []) or []

    # --- 顶层摘要：使用新研究结论提取 ---
    conclusion = _effective_research_conclusion(final_state)

    summary = {
        "symbol": symbol,
        "variety": variety,
        "date": trade_date,
        "risk_tier": conclusion.get("risk_tier", "?"),
        "allowed_strategies": conclusion.get("allowed_strategies", []),
        "forbidden_strategies": conclusion.get("forbidden_strategies", []),
        "core_narrative": conclusion.get("core_narrative", ""),
        # 向后兼容
        "final_action": conclusion.get("action", "hold"),
        "confidence": conclusion.get("confidence", 0.0),
    }

    # --- L1: 4 个 analyst 结构化摘要 ---
    L1_entries = []
    analyst_configs = [
        ("tech", "技术分析师", "technical"),
        ("fund", "产业分析师", "fundamental"),
        ("pos", "持仓分析师", "position"),
        ("news", "新闻分析师", "news"),
    ]
    for prefix, cn_name, feat_key in analyst_configs:
        entry = None
        for k, v in registry.items():
            if k.startswith(f"REF-{prefix.upper()}") or k.startswith(prefix.upper()):
                entry = v if isinstance(v, dict) else None
                break
        if not entry:
            L1_entries.append({
                "id": f"REF-{prefix.upper()}-unknown",
                "name": cn_name,
                "direction": "skip",
                "confidence": 0.0,
                "calibrated_confidence": 0.0,
                "status": "skipped",
                "key_metrics": {},
                "signals": [],
            })
            continue

        # 置信度校准(复用 _data_quality_weight 逻辑)
        status = entry.get("status", "ok")
        raw_conf = entry.get("confidence", 0.0)
        weight = {"ok": 1.0, "degraded": 0.5, "skipped": 0.3, "": 0.5}.get(status, 0.5)
        if not isinstance(raw_conf, (int, float)):
            raw_conf = 0.0
        calibrated = round(raw_conf * weight, 2)

        # 关键指标
        key_metrics = {}
        feat_block = features.get(feat_key, {})
        if isinstance(feat_block, dict):
            daily = feat_block.get("daily", {}) if feat_key == "technical" else feat_block
            snap = daily.get("snapshot", {}) if isinstance(daily, dict) else {}
            if feat_key == "technical":
                key_metrics = {
                    "composite_score": snap.get("composite_score"),
                    "oi_divergence": snap.get("oi_divergence", snap.get("oi_position")),
                    "volatility": snap.get("volatility_20d"),
                    "boll_low": snap.get("boll_low"),
                    "boll_up": snap.get("boll_up"),
                }
            elif feat_key == "fundamental":
                basis = feat_block.get("basis", feat_block.get("latest", {}))
                inv = feat_block.get("inventory", {})
                term = feat_block.get("term_structure", {})
                key_metrics = {
                    "basis": basis.get("value", basis.get("basis")),
                    "basis_zscore": basis.get("zscore"),
                    "inventory_wow": inv.get("wow_change"),
                    "term_structure": term.get("structure"),
                    "roll_yield": term.get("roll_yield"),
                }
            elif feat_key == "position":
                latest = feat_block.get("latest", {}) if isinstance(feat_block.get("latest"), dict) else feat_block
                key_metrics = {
                    "net_long_change_5d": latest.get("net_long_change_5d"),
                    "long_short_ratio": latest.get("long_short_ratio"),
                    "crowding": latest.get("crowding_status"),
                }
            elif feat_key == "news":
                ns = feat_block.get("latest", {}) if isinstance(feat_block.get("latest"), dict) else feat_block
                key_metrics = {
                    "sentiment_score": ns.get("sentiment_score"),
                    "event_count": len(ns.get("recent_events", ns.get("events", []))) if isinstance(ns, dict) else 0,
                }

        L1_entries.append({
            "id": entry.get("id", f"REF-{prefix.upper()}-unknown"),
            "conclusion_id": entry.get("conclusion_id", ""),
            "name": cn_name,
            "direction": entry.get("direction", "?"),
            "confidence": raw_conf,
            "calibrated_confidence": calibrated,
            "status": status,
            "summary": entry.get("summary", ""),
            "key_metrics": {k: v for k, v in key_metrics.items() if v is not None},
            "signals": entry.get("signals", [])[:3],
        })

    # 自定义数据来源标注：追加独立条目而非污染系统分析师（F1）
    custom_data = features.get("custom_data", {})
    if isinstance(custom_data, dict) and custom_data.get("parsed"):
        _feature_dict = custom_data.get("feature_dict") if isinstance(custom_data.get("feature_dict"), dict) else None
        _cd_snapshot = _feature_dict.get("snapshot", {}) if _feature_dict else {}
        L1_entries.append({
            "id": "REF-CUSTOM-uploaded",
            "conclusion_id": "custom_conc_1",
            "name": "自定义数据",
            "direction": "neutral",
            "confidence": 0.0,
            "calibrated_confidence": 0.0,
            "status": "ok",
            "summary": custom_data.get("summary_text", "(用户上传数据)")[:80],
            "key_metrics": {
                "data_source": "用户上传文件",
                "file_count": custom_data.get("file_count", 0),
                "file_names": ", ".join(custom_data.get("file_names", [])),
                "matched_module": _feature_dict.get("_matched_module") if _feature_dict else None,
                "current_value": _cd_snapshot.get("current_value"),
                "as_of": _cd_snapshot.get("as_of"),
                "self_pctl_180d": _cd_snapshot.get("self_pctl_180d"),
            },
            "signals": _feature_dict.get("signals", [])[:3] if _feature_dict else [],
        })

    # --- L2: investment_plan 解析 + contradiction_map ---
    investment_plan = final_state.get("investment_plan", "")
    L2_data = {"raw": investment_plan[:500] if investment_plan else ""}
    if investment_plan:
        try:
            # 剥离 markdown 代码块包裹
            import re
            plan_text = investment_plan
            m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", plan_text, re.DOTALL)
            if m:
                plan_text = m.group(1).strip()
            parsed = json.loads(plan_text)
            L2_data = {
                "valuation_matrix": parsed.get("估值驱动矩阵", parsed.get("valuation_matrix", [])),
                "bull_bear_table": parsed.get("多空对照表", parsed.get("bull_bear_table", [])),
                "scenarios": parsed.get("三种情景推演", parsed.get("scenarios", {})),
                "contradiction_map": contradiction_map if isinstance(contradiction_map, list) else [],
            }
        except json.JSONDecodeError:
            # 不是标准 JSON（可能是 stock 路径的 Markdown），兜底
            L2_data = {"raw_summary": investment_plan[:300]}

    # --- L3: risk_assessment + safety_override + research_brief + CIO memo ---
    risk_card = final_state.get("risk_card", {})
    safety_override = risk_card.get("safety_override", {})

    # CIO 结构化输出已经由 Investment Director 写入最终 state。
    cio_memo = final_state.get("investment_memo", {}) or {}
    if not isinstance(cio_memo, dict):
        cio_memo = {}
    cio_risk_card = risk_card if isinstance(risk_card, dict) else {}

    L3_data = {
        "risk_assessment": risk_assessment if isinstance(risk_assessment, dict) else {},
        "risk_card": risk_card if isinstance(risk_card, dict) else {},
        "research_brief_raw": research_brief[:1000] if research_brief else "",
        "safety_override": safety_override if isinstance(safety_override, dict) else {},
        "cio_memo": cio_memo,
        "cio_risk_card": cio_risk_card,
        "strategy_matrix": strategy_matrix if isinstance(strategy_matrix, list) else [],
        "fact_cards": fact_cards if isinstance(fact_cards, list) else [],
        "contradiction_map": contradiction_map if isinstance(contradiction_map, list) else [],
        # 向后兼容
        "final_decision_raw": research_brief[:500] if research_brief else "",
    }

    return {
        "summary": summary,
        "layers": {
            "L1": L1_entries,
            "L2": L2_data,
            "L3": L3_data,
        },
    }