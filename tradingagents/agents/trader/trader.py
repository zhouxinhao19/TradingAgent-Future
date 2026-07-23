import functools
import time
import json

# 导入统一日志系统
from tradingagents.utils.logging_init import get_logger
from tradingagents.agents.utils.instrument_utils import build_instrument_context
logger = get_logger("default")

# === Phase 3b-ii-B:Commodity prompt ===
COMMODITY_TRADER_SYSTEM_PROMPT = """您是一位专业的期货交易员,负责分析市场数据并做出投资决策。基于您的分析,请提供具体的做多、做空或平仓建议。

⚠️ 重要提醒:当前分析的标的是 {full_symbol}({variety_name}),交易所:{exchange},报价单位:{quote_unit}
{instrument_context}

🔴 严格要求:
- 标的代码 {full_symbol} 必须严格按照基本面报告中的真实数据
- 绝对禁止使用错误的品种名称或混淆不同的合约
- 所有分析必须基于提供的真实数据,不允许假设或编造
- **必须提供具体的目标价位和止损/止盈位,不允许设置为null或空值**

请在您的分析中包含以下关键信息:
1. **投资建议**: 明确的做多/做空/平仓决策 + 合约选择
2. **目标价位**: 基于分析的合理目标价格({quote_unit})
   - 做多建议:提供入场价位、目标位、止损位、预期涨幅
   - 做空建议:提供入场价位、目标位、止损位、预期跌幅
   - 平仓建议:提供合理平仓价格区间
3. **持仓手数**: 建议持仓数量 + 保证金占用估算(按 10% 保证金率)
4. **置信度**: 对决策的信心程度(0-1 之间)
5. **风险评分**: 投资风险等级(0-1 之间,0 为低风险,1 为高风险)
6. **持有周期**: 建议持仓时间(日内/短线/波段/趋势)
7. **详细推理**: 支持决策的具体理由(基差/库存/期限结构/持仓/技术面)

🎯 目标价位计算指导:
- 基于基本面分析的估值数据(基差/库存/期限结构)
- 参考技术分析的支撑位和阻力位
- 考虑行业平均估值水平和品种波动特性
- 结合市场情绪和新闻影响
- 即使市场情绪过热,也要基于合理估值给出目标价

特别注意:
- 必须使用基本面报告中提供的正确品种名称
- 期货价格单位:农产品元/吨、金属元/克、能源元/桶等(按交易所报价单位)
- 目标价位必须与当前合约的报价单位保持一致
- **绝对不允许说"无法确定目标价"或"需要更多信息"**

请用中文撰写分析内容,并始终以'最终交易建议: **做多/做空/平仓**'结束您的回应以确认您的建议。

请不要忘记利用过去决策的经验教训来避免重复错误。以下是类似情况下的交易反思和经验教训: {past_memory_str}"""


def create_trader(llm, memory):
    def trader_node(state, name):
        company_name = state["company_of_interest"]
        instrument_context = build_instrument_context(company_name)
        investment_plan = state["investment_plan"]
        market_research_report = state["market_report"]
        sentiment_report = state.get("position_report") or state.get("sentiment_report", "")
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        # === Phase 3b-ii-B:检测 asset_type ===
        full_symbol = state.get("full_symbol") or company_name
        variety_name = state.get("variety_name", full_symbol)
        exchange = state.get("exchange", "")
        quote_unit = state.get("quote_unit", "")

        logger.debug(f"💰 [DEBUG] ===== 交易员节点(商品)开始 =====")
        logger.debug(f"💰 [DEBUG] 交易员检测商品: {company_name}")

        logger.debug(f"💰 [DEBUG] 基本面报告长度: {len(fundamentals_report)}")
        logger.debug(f"💰 [DEBUG] 基本面报告前200字符: {fundamentals_report[:200]}...")

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"

        # 检查memory是否可用
        if memory is not None:
            logger.warning(f"⚠️ [DEBUG] memory可用，获取历史记忆")
            past_memories = memory.get_memories(curr_situation, n_matches=2)
            past_memory_str = ""
            for i, rec in enumerate(past_memories, 1):
                past_memory_str += rec["recommendation"] + "\n\n"
        else:
            logger.warning(f"⚠️ [DEBUG] memory为None，跳过历史记忆检索")
            past_memories = []
            past_memory_str = "暂无历史记忆数据可参考。"

        user_content = (
            f"Based on a comprehensive analysis by a team of analysts, here is an investment plan tailored for {full_symbol}. This plan incorporates insights from current technical market trends, macro fundamentals (basis/inventory/term-structure/positioning), and news sentiment. Use this plan as a foundation for evaluating your next trading decision.\n\nProposed Investment Plan: {investment_plan}\n\nLeverage these insights to make an informed and strategic decision."
        )
        system_content = COMMODITY_TRADER_SYSTEM_PROMPT.format(
            full_symbol=full_symbol,
            variety_name=variety_name,
            exchange=exchange,
            quote_unit=quote_unit or "—",
            instrument_context=instrument_context,
            past_memory_str=past_memory_str,
        )

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]

        result = llm.invoke(messages)

        logger.debug(f"💰 [DEBUG] LLM调用完成")
        logger.debug(f"💰 [DEBUG] 交易员回复长度: {len(result.content)}")
        logger.debug(f"💰 [DEBUG] 交易员回复前500字符: {result.content[:500]}...")
        logger.debug(f"💰 [DEBUG] ===== 交易员节点结束 =====")

        return {
            "messages": [result],
            "trader_investment_plan": result.content,
            "sender": name,
        }

    return functools.partial(trader_node, name="Trader")
