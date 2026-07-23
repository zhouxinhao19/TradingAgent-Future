from langchain_core.messages import AIMessage
import time
import json

# 导入统一日志系统
from tradingagents.utils.logging_init import get_logger
logger = get_logger("default")

# === Phase 3b-ii-B:Commodity prompt ===
COMMODITY_BEAR_PROMPT = """你是一位看跌期货研究员,负责论证放弃做多或做空标的 {full_symbol} 的理由。

⚠️ 重要:这是大宗商品期货分析(非股票),关注以下期货特定风险:
- **基差与期限结构**:Contango + 现货贴水 + 库存累积是最强看空信号
- **库存与持仓**:库存累积 + 仓单增加 + 净空头集中
- **杠杆风险**:期货保证金率 8-15%,亏损可能超过本金
- **合约换月风险**:主力合约换月跳空、展期成本(contango 时为负 carry)
- **涨跌停与流动性**:单日涨跌停无法平仓、小品种流动性差
- **产业周期**:产能投放/季节性累库/限产解除/替代品冲击

请用中文构建看跌论证,重点关注:
- **基本面恶化**:库存累积 + 现货贴水 + Contango + 净空头集中共振
- **技术面破位**:跌破关键支撑 + OI 减少 + 波动率放大
- **资金面撤离**:前 20 名净多头大幅减少、主力翻空
- **宏观与产业**:美联储紧缩 + OPEC+ 增产 + 库存高企 + 需求疲软
- **反驳看涨观点**:用具体数据(库存/基差/持仓)批判看涨的过度乐观

## 分析师报告索引(ID引用规则)

以下是各分析师报告的编号ID。在论证中引用具体数据时,必须使用对应的ID标注来源:

{analyst_registry_summary}

引用格式示例:
  - "根据技术分析报告[TECH-a1b2c3d4],MACD死叉确认..."
  - "基本面数据[FUND-x9y8z7w6]显示库存累积..."

强制规则:
  1. 每个论证要点必须引用至少 2 个不同的分析师报告ID。
  2. 引用格式为 [PREFIX-hash8],如 [TECH-a1b2c3d4]。
  3. 不得凭空编造未提供的ID。如果某方面无对应ID,注明"无分析师索引"。

可用资源:
- 技术面报告(编号如上): {market_research_report}
- 持仓分析报告(主力加减仓/集中度/拥挤度): {sentiment_report}
- 新闻/产业事件: {news_report}
- 基本面报告(基差+库存+期限结构): {fundamentals_report}
- 辩论对话历史: {history}
- 最后的看涨论点: {current_response}
- 经验教训: {past_memory_str}

请构建有说服力的看跌论点,聚焦期货特定风险证据(基差/库存/期限结构/持仓/保证金),反驳看涨担忧。每个论点必须引用分析师报告ID。"""


def create_bear_researcher(llm, memory):
    def bear_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")

        current_response = investment_debate_state.get("current_response", "")
        market_research_report = state["market_report"]
        sentiment_report = state.get("position_report") or state.get("sentiment_report", "")
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        ticker = state.get('company_of_interest', 'Unknown')
        company_name = state.get('company_of_interest', 'Unknown')

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"

        # 安全检查：确保memory不为None
        if memory is not None:
            past_memories = memory.get_memories(curr_situation, n_matches=2)
        else:
            logger.warning(f"⚠️ [DEBUG] memory为None，跳过历史记忆检索")
            past_memories = []

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        # 构造 analyst_registry_summary
        analyst_registry = state.get("analyst_registry", {})
        if analyst_registry:
            registry_lines = []
            for aid, entry in analyst_registry.items():
                summary = entry.get("summary", "") or ""
                direction = entry.get("direction", "neutral") or "neutral"
                analyst_name = entry.get("analyst", "unknown")
                registry_lines.append(
                    f"  - {aid}: {analyst_name}分析师, 方向={direction}, {summary}"
                )
            analyst_registry_summary = "\n".join(registry_lines)
        else:
            analyst_registry_summary = "(暂无分析师报告索引)"

        prompt = COMMODITY_BEAR_PROMPT.format(
            full_symbol=state.get("full_symbol") or ticker,
            analyst_registry_summary=analyst_registry_summary,
            market_research_report=market_research_report,
            sentiment_report=sentiment_report,
            news_report=news_report,
            fundamentals_report=fundamentals_report,
            history=history,
            current_response=current_response,
            past_memory_str=past_memory_str,
        )

        response = llm.invoke(prompt)

        argument = f"Bear Analyst: {response.content}"

        new_count = investment_debate_state["count"] + 1
        logger.info(f"🐻 [空头研究员] 发言完成，计数: {investment_debate_state['count']} -> {new_count}")

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": argument,
            "count": new_count,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bear_node
