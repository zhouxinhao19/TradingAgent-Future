"""
commodity_graph.py — CommodityTradingAgentsGraph 子图 (Phase 3b-ii-C)

继承自 TradingAgentsGraph,复用 LLM/内存初始化,重写:
  1. GraphSetup — 注册 4 个 commodity analyst + 决策链节点 + CIO
  2. Propagator — 注入 commodity state (asset_type + full_symbol + commodity_features + latest_news)
  3. propagate() — 接受 full_symbol (非 ticker),commodity 默认参数

设计要点:
  - stock 路径零改动(继承父类初始化 + 父类 GraphSetup 保持不变)
  - commodity 路径独立:CommodityGraphSetup + CommodityPropagator
  - commodity 不需要 tool_nodes(4 analyst 读 features,LLM 必调但不调工具)
  - 决策链节点 commodity 化(3b-ii-B)已自动通过 state['asset_type'] 切换 prompt
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

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
from tradingagents.agents.managers.executive_decision_maker import (
    create_executive_decision_maker,
)
from tradingagents.agents.managers.research_manager import create_research_manager
from tradingagents.agents.managers.risk_manager import create_risk_manager
from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
from tradingagents.agents.risk_mgmt.aggresive_debator import create_risky_debator
from tradingagents.agents.risk_mgmt.conservative_debator import create_safe_debator
from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator
from tradingagents.agents.trader.trader import create_trader

from tradingagents.utils.logging_init import get_logger

from .propagation import Propagator
from .setup import GraphSetup
from .trading_graph import TradingAgentsGraph

logger = get_logger("default")


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
            "sentiment_report": "",
            "news_report": "",
            "commodity_features": commodity_features or {},
            "latest_news": latest_news or [],
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
        bull_memory,
        bear_memory,
        trader_memory,
        invest_judge_memory,
        risk_manager_memory,
        conditional_logic,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.bull_memory = bull_memory
        self.bear_memory = bear_memory
        self.trader_memory = trader_memory
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
        bull_node = create_bull_researcher(self.quick_thinking_llm, self.bull_memory)
        bear_node = create_bear_researcher(self.quick_thinking_llm, self.bear_memory)
        rm_node = create_research_manager(self.deep_thinking_llm, self.invest_judge_memory)
        trader_node = create_trader(self.quick_thinking_llm, self.trader_memory)

        risky_node = create_risky_debator(self.quick_thinking_llm)
        safe_node = create_safe_debator(self.quick_thinking_llm)
        neutral_node = create_neutral_debator(self.quick_thinking_llm)
        risk_mgr_node = create_risk_manager(self.deep_thinking_llm, self.risk_manager_memory)

        # === CIO 最终决策(新节点) ===
        cio_node = create_executive_decision_maker(self.deep_thinking_llm)

        # === 构造 StateGraph ===
        workflow = StateGraph(AgentState)

        # 注册 analyst 节点(命名跟 stock 一致,便于 SSE 兼容)
        workflow.add_node("Technical Analyst", tech_analyst)
        workflow.add_node("Fundamentals Analyst", fund_analyst)
        workflow.add_node("Sentiment Analyst", pos_analyst)  # 持仓→情绪字段
        workflow.add_node("News Analyst", news_analyst)

        # 注册决策链节点
        workflow.add_node("Bull Researcher", bull_node)
        workflow.add_node("Bear Researcher", bear_node)
        workflow.add_node("Research Manager", rm_node)
        workflow.add_node("Trader", trader_node)

        # 注册风控辩论节点
        workflow.add_node("Risky Analyst", risky_node)
        workflow.add_node("Safe Analyst", safe_node)
        workflow.add_node("Neutral Analyst", neutral_node)
        workflow.add_node("Risk Judge", risk_mgr_node)

        # 注册 CIO(新)
        workflow.add_node("CIO", cio_node)

        # === 边(commodity 路径:analyst 不调工具,直接决策链) ===
        # START → Technical Analyst → Fundamentals Analyst → Sentiment Analyst → News Analyst
        workflow.add_edge(START, "Technical Analyst")
        workflow.add_edge("Technical Analyst", "Fundamentals Analyst")
        workflow.add_edge("Fundamentals Analyst", "Sentiment Analyst")
        workflow.add_edge("Sentiment Analyst", "News Analyst")

        # News Analyst → Bull Researcher → Bear/Research Manager(debate 循环)
        workflow.add_edge("News Analyst", "Bull Researcher")

        workflow.add_conditional_edges(
            "Bull Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bear Researcher": "Bear Researcher",
                "Research Manager": "Research Manager",
            },
        )
        workflow.add_conditional_edges(
            "Bear Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bull Researcher": "Bull Researcher",
                "Research Manager": "Research Manager",
            },
        )

        # Research Manager → Trader → Risky Analyst → (辩论循环) → Risk Judge → CIO → END
        workflow.add_edge("Research Manager", "Trader")
        workflow.add_edge("Trader", "Risky Analyst")

        workflow.add_conditional_edges(
            "Risky Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Safe Analyst": "Safe Analyst",
                "Risk Judge": "Risk Judge",
            },
        )
        workflow.add_conditional_edges(
            "Safe Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Neutral Analyst": "Neutral Analyst",
                "Risk Judge": "Risk Judge",
            },
        )
        workflow.add_conditional_edges(
            "Neutral Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Risky Analyst": "Risky Analyst",
                "Risk Judge": "Risk Judge",
            },
        )

        workflow.add_edge("Risk Judge", "CIO")
        workflow.add_edge("CIO", END)

        return workflow.compile()


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

        # 替换为 commodity setup + propagator
        self.graph_setup = CommodityGraphSetup(
            self.quick_thinking_llm,
            self.deep_thinking_llm,
            self.bull_memory,
            self.bear_memory,
            self.trader_memory,
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
        "Technical Analyst": "📈 技术分析师",
        "Fundamentals Analyst": "💼 基本面分析师",
        "Sentiment Analyst": "🧠 持仓情绪分析师",
        "News Analyst": "📰 新闻分析师",
        "Bull Researcher": "🐂 看涨研究员",
        "Bear Researcher": "🐻 看跌研究员",
        "Research Manager": "👔 研究经理",
        "Trader": "💼 交易员决策",
        "Risky Analyst": "🔥 激进风险评估",
        "Safe Analyst": "🛡️ 保守风险评估",
        "Neutral Analyst": "⚖️ 中性风险评估",
        "Risk Judge": "🎯 风险经理",
        "CIO": "🏛️ 首席投资官决策",
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

        Returns:
            (final_state, decision)
        """
        self.full_symbol = full_symbol
        logger.info(f"🌾 [CommodityTradingAgentsGraph] propagate: {full_symbol} @ {trade_date}")

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

        for chunk in self.graph.stream(init_state, **args):
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

        # 构造决策摘要(CIO 输出在 state['final_decision'])
        decision = self._extract_decision(final_state)

        logger.info(f"✅ [CommodityTradingAgentsGraph] 完成: {full_symbol}")
        return final_state, decision

    def _extract_decision(self, final_state: Dict[str, Any]) -> Dict[str, Any]:
        """从 CIO 输出提取结构化决策。"""
        final_decision = final_state.get("final_decision", "")
        if not final_decision:
            return {
                "action": "hold",
                "confidence": 0.0,
                "reasoning": "(CIO 未输出决策)",
                "raw_text": "",
            }

        # 简化解析 — 从 Markdown 文本提取方向
        text = final_decision
        action = "hold"
        if "做多" in text or "买入" in text:
            action = "long"
        elif "做空" in text or "卖出" in text:
            action = "short"
        elif "平仓" in text:
            action = "flat"

        return {
            "action": action,
            "confidence": 0.5,  # 占位,可由 CIO prompt 输出 -1-1 范围后解析
            "reasoning": text,
            "raw_text": text,
        }