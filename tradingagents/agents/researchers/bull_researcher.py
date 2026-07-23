from langchain_core.messages import AIMessage
import time
import json

# 导入统一日志系统
from tradingagents.utils.logging_init import get_logger
logger = get_logger("default")

# === Phase 3b-ii-B:Commodity prompt ===
COMMODITY_BULL_PROMPT = """你是一位看涨期货研究员,负责为标的 {full_symbol} 的做多机会建立强有力的论证。

⚠️ 重要:这是大宗商品期货分析(非股票),关注以下期货特定维度:
- **基差与期限结构**:现货升贴水、Contango/Backwardation、展期收益率(carry)
- **库存与持仓**:库存去化速率、前 20 名净多头变化、拥挤度
- **波动率与杠杆**:ATR 百分位、保证金率(通常 8-15%)、涨跌停板
- **合约生命周期**:主力合约换月、最后交易日、限仓规则
- **季节性**:农产品有强季节性,能源/金属有需求淡旺季

请用中文构建看涨论证,重点关注:
- **基本面驱动**:库存去化 + 现货升水 + Backwardation 三角共振是最强看多信号
- **技术面配合**:日/周双周期同向 + OI 背离支持 + 突破关键位
- **资金面与持仓**:前 20 名净多头增加 + 主力加多
- **宏观与产业**:全球宏观(美联储/OPEC+/地缘) + 产业事件(产能/限产/天气)
- **反驳看跌观点**:用具体数据(库存/基差/持仓)批判性分析

## 分析师报告索引(ID引用规则)

以下是各分析师报告的编号ID。在论证中引用具体数据时,必须使用对应的ID标注来源:

{analyst_registry_summary}

引用格式示例:
  - "根据技术分析报告[TECH-a1b2c3d4],MACD金叉确认..."
  - "持仓数据[POSN-x9y8z7w6]显示净多增加..."

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
- 最后的看跌论点: {current_response}
- 经验教训: {past_memory_str}

请构建有说服力的看涨论点,聚焦期货特定证据(基差/库存/期限结构/持仓),反驳看跌担忧。每个论点必须引用分析师报告ID。"""


def create_bull_researcher(llm, memory):
    def bull_node(state) -> dict:
        logger.debug(f"🐂 [DEBUG] ===== 看涨研究员节点开始 =====")

        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

        current_response = investment_debate_state.get("current_response", "")
        market_research_report = state["market_report"]
        sentiment_report = state.get("position_report") or state.get("sentiment_report", "")
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        ticker = state.get('company_of_interest', 'Unknown')
        company_name = state.get('company_of_interest', 'Unknown')

        logger.debug(f"🐂 [DEBUG] 接收到的报告:")
        logger.debug(f"🐂 [DEBUG] - 市场报告长度: {len(market_research_report)}")
        logger.debug(f"🐂 [DEBUG] - 持仓报告长度: {len(sentiment_report)}")
        logger.debug(f"🐂 [DEBUG] - 新闻报告长度: {len(news_report)}")
        logger.debug(f"🐂 [DEBUG] - 基本面报告长度: {len(fundamentals_report)}")
        logger.debug(f"🐂 [DEBUG] - 基本面报告前200字符: {fundamentals_report[:200]}...")
        logger.debug(f"🐂 [DEBUG] - 标的: {ticker}")

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

        prompt = COMMODITY_BULL_PROMPT.format(
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

        argument = f"Bull Analyst: {response.content}"

        new_count = investment_debate_state["count"] + 1
        logger.info(f"🐂 [多头研究员] 发言完成，计数: {investment_debate_state['count']} -> {new_count}")

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "count": new_count,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bull_node
