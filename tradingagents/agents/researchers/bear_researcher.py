from langchain_core.messages import AIMessage
import time
import json

# 导入统一日志系统
from tradingagents.utils.logging_init import get_logger
logger = get_logger("default")

# === Phase 3b-ii-B:Commodity prompt 注入(占位) ===
# 当 state['asset_type'] == "commodity" 时,使用此 prompt 替代 stock 默认 prompt
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

可用资源:
- 技术面报告: {market_research_report}
- 持仓/情绪报告: {sentiment_report}
- 新闻/产业事件: {news_report}
- 基本面报告(基差+库存+期限结构): {fundamentals_report}
- 辩论对话历史: {history}
- 最后的看涨论点: {current_response}
- 经验教训: {past_memory_str}

请构建有说服力的看跌论点,聚焦期货特定风险证据(基差/库存/期限结构/持仓/保证金),反驳看涨担忧。"""


def create_bear_researcher(llm, memory):
    def bear_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")

        current_response = investment_debate_state.get("current_response", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        # 使用统一的股票类型检测(仅 stock 路径需要)
        ticker = state.get('company_of_interest', 'Unknown')
        asset_type = state.get("asset_type", "stock")
        if asset_type == "commodity":
            # commodity 路径:跳过 StockUtils,提供默认值
            is_china = False
            market_info = {
                'is_china': False,
                'is_hk': False,
                'is_us': False,
                'market_name': '大宗商品期货',
                'currency_name': 'CNY',
                'currency_symbol': '¥',
            }
        else:
            try:
                from tradingagents.utils.stock_utils import StockUtils
                market_info = StockUtils.get_market_info(ticker)
                is_china = market_info['is_china']
            except ImportError:
                logger.warning(f"StockUtils 不可用,使用默认市场信息")
                is_china = False
                market_info = {
                    'is_china': False,
                    'is_hk': False,
                    'is_us': False,
                    'market_name': '未知',
                    'currency_name': 'CNY',
                    'currency_symbol': '¥',
                }



        # 获取公司名称
        def _get_company_name(ticker_code: str, market_info_dict: dict) -> str:
            """根据股票代码获取公司名称"""
            try:
                if market_info_dict['is_china']:
                    from tradingagents.dataflows.interface import get_china_stock_info_unified
                    stock_info = get_china_stock_info_unified(ticker_code)
                    if stock_info and "股票名称:" in stock_info:
                        name = stock_info.split("股票名称:")[1].split("\n")[0].strip()
                        logger.info(f"✅ [空头研究员] 成功获取中国股票名称: {ticker_code} -> {name}")
                        return name
                    else:
                        # 降级方案
                        try:
                            from tradingagents.dataflows.data_source_manager import get_china_stock_info_unified as get_info_dict
                            info_dict = get_info_dict(ticker_code)
                            if info_dict and info_dict.get('name'):
                                name = info_dict['name']
                                logger.info(f"✅ [空头研究员] 降级方案成功获取股票名称: {ticker_code} -> {name}")
                                return name
                        except Exception as e:
                            logger.error(f"❌ [空头研究员] 降级方案也失败: {e}")
                elif market_info_dict['is_hk']:
                    try:
                        from tradingagents.dataflows.providers.hk.improved_hk import get_hk_company_name_improved
                        name = get_hk_company_name_improved(ticker_code)
                        return name
                    except Exception:
                        clean_ticker = ticker_code.replace('.HK', '').replace('.hk', '')
                        return f"港股{clean_ticker}"
                elif market_info_dict['is_us']:
                    us_stock_names = {
                        'AAPL': '苹果公司', 'TSLA': '特斯拉', 'NVDA': '英伟达',
                        'MSFT': '微软', 'GOOGL': '谷歌', 'AMZN': '亚马逊',
                        'META': 'Meta', 'NFLX': '奈飞'
                    }
                    return us_stock_names.get(ticker_code.upper(), f"美股{ticker_code}")
            except Exception as e:
                logger.error(f"❌ [空头研究员] 获取公司名称失败: {e}")
            return f"股票代码{ticker_code}"

        company_name = _get_company_name(ticker, market_info)
        is_hk = market_info['is_hk']
        is_us = market_info['is_us']

        currency = market_info['currency_name']
        currency_symbol = market_info['currency_symbol']

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

        if asset_type == "commodity":
            prompt = COMMODITY_BEAR_PROMPT.format(
                full_symbol=state.get("full_symbol") or ticker,
                market_research_report=market_research_report,
                sentiment_report=sentiment_report,
                news_report=news_report,
                fundamentals_report=fundamentals_report,
                history=history,
                current_response=current_response,
                past_memory_str=past_memory_str,
            )
        else:
            prompt = f"""你是一位看跌分析师，负责论证不投资股票 {company_name}（股票代码：{ticker}）的理由。

⚠️ 重要提醒：当前分析的是 {market_info['market_name']}，所有价格和估值请使用 {currency}（{currency_symbol}）作为单位。
⚠️ 在你的分析中，请始终使用公司名称"{company_name}"而不是股票代码"{ticker}"来称呼这家公司。

你的目标是提出合理的论证，强调风险、挑战和负面指标。利用提供的研究和数据来突出潜在的不利因素并有效反驳看涨论点。

请用中文回答，重点关注以下几个方面：

- 风险和挑战：突出市场饱和、财务不稳定或宏观经济威胁等可能阻碍股票表现的因素
- 竞争劣势：强调市场地位较弱、创新下降或来自竞争对手威胁等脆弱性
- 负面指标：使用财务数据、市场趋势或最近不利消息的证据来支持你的立场
- 反驳看涨观点：用具体数据和合理推理批判性分析看涨论点，揭露弱点或过度乐观的假设
- 参与讨论：以对话风格呈现你的论点，直接回应看涨分析师的观点并进行有效辩论，而不仅仅是列举事实

可用资源：

市场研究报告：{market_research_report}
社交媒体情绪报告：{sentiment_report}
最新世界事务新闻：{news_report}
公司基本面报告：{fundamentals_report}
辩论对话历史：{history}
最后的看涨论点：{current_response}
类似情况的反思和经验教训：{past_memory_str}

请使用这些信息提供令人信服的看跌论点，反驳看涨声明，并参与动态辩论，展示投资该股票的风险和弱点。你还必须处理反思并从过去的经验教训和错误中学习。

请确保所有回答都使用中文。
"""

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
