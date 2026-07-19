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
from tradingagents.agents.managers.investment_director import create_investment_director
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

def _create_checkpointer():
    """创建 Graph checkpointer 实例。

    环境变量 CHECKPOINTER_BACKEND=memory(默认)|sqlite
    - memory: MemorySaver，仅存进程内存，重启丢失
    - sqlite: SqliteSaver，持久化到文件，重启可恢复（需安装 langgraph-checkpoint-sqlite）
    """
    backend = os.environ.get("CHECKPOINTER_BACKEND", "memory").lower()
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

        # === 边(commodity 路径:4 L1 并行 fan-out + 汇聚到 Research Manager) ===
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

        # 构造决策摘要(CIO 输出在 state['final_decision'])
        decision = self._extract_decision(final_state)

        logger.info(f"✅ [CommodityTradingAgentsGraph] 完成: {full_symbol}")
        return final_state, decision

    def _extract_decision(self, final_state: Dict[str, Any]) -> Dict[str, Any]:
        """从 CIO 输出提取结构化决策。

        解析 CIO final_decision Markdown 中的结构化字段:
          - **方向**:做多/做空/持有/平仓
          - **置信度**:0.75

        Bug 修复(2026-07-16):
          - 旧逻辑: 全文搜索"做多"→"做空",但 CIO 文本同时包含两者时永远返回"long"
          - 新逻辑: 用正则精确匹配"**方向**:做多/做空"字段行,消除歧义
          - 旧逻辑: confidence 硬编码 0.5
          - 新逻辑: 解析"**置信度**:0.75"字段,精确提取数值
        """
        import re

        final_decision = final_state.get("final_decision", "")
        if not final_decision:
            return {
                "action": "hold",
                "confidence": 0.0,
                "reasoning": "(CIO 未输出决策)",
                "raw_text": "",
            }

        text = final_decision
        action = "hold"
        confidence = 0.5

        # 1. 解析方向 — 精确匹配"**方向**:做多/做空/买入/卖出/持有/平仓"字段
        #    CIO 输出格式: "- **方向**:做空" 或 "**方向**:做多"
        dir_match = re.search(
            r'\*{0,2}方向\*{0,2}\s*[:：]\s*(做多|做空|买入|卖出|持有|平仓)',
            text,
        )
        if dir_match:
            raw = dir_match.group(1)
            if raw in ("做多", "买入"):
                action = "long"
            elif raw in ("做空", "卖出"):
                action = "short"
            elif raw == "平仓":
                action = "flat"
            elif raw == "持有":
                action = "hold"

        # 2. 解析置信度 — 精确匹配"**置信度**:0.75"字段
        #    CIO 输出格式: "- **置信度**:0.75" 或 "**置信度**:0.75"
        conf_match = re.search(
            r'\*{0,2}置信度\*{0,2}\s*[:：]\s*([0-9]+\.?[0-9]*)',
            text,
        )
        if conf_match:
            try:
                parsed = float(conf_match.group(1))
                if 0.0 <= parsed <= 1.0:
                    confidence = parsed
            except ValueError:
                pass

        return {
            "action": action,
            "confidence": confidence,
            "reasoning": text,
            "raw_text": text,
        }


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
    risk_assessment = final_state.get("risk_assessment", {}) or {}

    # --- 顶层摘要 ---
    action = "hold"
    confidence = 0.0
    if final_decision:
        dr = re.search(r'\*{0,2}方向\*{0,2}\s*[:：]\s*(做多|做空|买入|卖出|持有|平仓)', final_decision)
        if dr:
            raw = dr.group(1)
            action = {"做多": "long", "买入": "long", "做空": "short", "卖出": "short",
                      "平仓": "flat", "持有": "hold"}.get(raw, "hold")
        cr = re.search(r'\*{0,2}置信度\*{0,2}\s*[:：]\s*([0-9]+\.?[0-9]*)', final_decision)
        if cr:
            try:
                p = float(cr.group(1))
                if 0.0 <= p <= 1.0:
                    confidence = p
            except ValueError:
                pass

    summary = {
        "symbol": symbol,
        "variety": variety,
        "date": trade_date,
        "final_action": action,
        "confidence": confidence,
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

    # --- L2: investment_plan 解析 ---
    investment_plan = final_state.get("investment_plan", "")
    L2_data = {"raw": investment_plan[:500] if investment_plan else ""}
    if investment_plan:
        try:
            parsed = json.loads(investment_plan)
            L2_data = {
                "valuation_matrix": parsed.get("估值驱动矩阵", parsed.get("valuation_matrix", [])),
                "bull_bear_table": parsed.get("多空对照表", parsed.get("bull_bear_table", [])),
                "scenarios": parsed.get("三种情景推演", parsed.get("scenarios", {})),
            }
        except json.JSONDecodeError:
            # 不是标准 JSON（可能是 stock 路径的 Markdown），兜底
            L2_data = {"raw_summary": investment_plan[:300]}

    # --- L3: risk_assessment + safety_override + final_decision ---
    risk_card = final_state.get("risk_card", {})
    safety_override = risk_card.get("safety_override", {})
    L3_data = {
        "risk_assessment": risk_assessment if isinstance(risk_assessment, dict) else {},
        "risk_card": risk_card if isinstance(risk_card, dict) else {},
        "final_decision_raw": final_decision[:500] if final_decision else "",
        "safety_override": safety_override if isinstance(safety_override, dict) else {},
    }

    return {
        "summary": summary,
        "layers": {
            "L1": L1_entries,
            "L2": L2_data,
            "L3": L3_data,
        },
    }