from langchain_core.messages import AIMessage
import time
import json

# 导入统一日志系统
from tradingagents.utils.logging_init import get_logger
logger = get_logger("default")

# === Phase 3b-ii-B:Commodity prompt 注入(占位) ===
# 当 state['asset_type'] == "commodity" 时,使用此 prompt 替代 stock 默认 prompt
# 期货特定关注:基差/库存/期限结构/持仓/展期收益率/保证金率/涨跌停/合约到期/手数
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

可用资源:
- 技术面报告: {market_research_report}
- 持仓分析报告(主力加减仓/集中度/拥挤度): {sentiment_report}
- 新闻/产业事件: {news_report}
- 基本面报告(基差+库存+期限结构): {fundamentals_report}
- 辩论对话历史: {history}
- 最后的看跌论点: {current_response}
- 经验教训: {past_memory_str}

请构建有说服力的看涨论点,聚焦期货特定证据(基差/库存/期限结构/持仓),反驳看跌担忧。"""


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

        # === Phase 3b-ii-B:检测 asset_type ===
        asset_type = state.get("asset_type", "stock")

        # 使用统一的股票类型检测(仅 stock 路径需要)
        ticker = state.get('company_of_interest', 'Unknown')
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
                        logger.info(f"✅ [多头研究员] 成功获取中国股票名称: {ticker_code} -> {name}")
                        return name
                    else:
                        # 降级方案
                        try:
                            from tradingagents.dataflows.data_source_manager import get_china_stock_info_unified as get_info_dict
                            info_dict = get_info_dict(ticker_code)
                            if info_dict and info_dict.get('name'):
                                name = info_dict['name']
                                logger.info(f"✅ [多头研究员] 降级方案成功获取股票名称: {ticker_code} -> {name}")
                                return name
                        except Exception as e:
                            logger.error(f"❌ [多头研究员] 降级方案也失败: {e}")
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
                logger.error(f"❌ [多头研究员] 获取公司名称失败: {e}")
            return f"股票代码{ticker_code}"

        company_name = _get_company_name(ticker, market_info)
        is_hk = market_info['is_hk']
        is_us = market_info['is_us']

        currency = market_info['currency_name']
        currency_symbol = market_info['currency_symbol']

        logger.debug(f"🐂 [DEBUG] 接收到的报告:")
        logger.debug(f"🐂 [DEBUG] - 市场报告长度: {len(market_research_report)}")
        logger.debug(f"🐂 [DEBUG] - 持仓报告长度: {len(sentiment_report)}")
        logger.debug(f"🐂 [DEBUG] - 新闻报告长度: {len(news_report)}")
        logger.debug(f"🐂 [DEBUG] - 基本面报告长度: {len(fundamentals_report)}")
        logger.debug(f"🐂 [DEBUG] - 基本面报告前200字符: {fundamentals_report[:200]}...")
        logger.debug(f"🐂 [DEBUG] - 股票代码: {ticker}, 公司名称: {company_name}, 类型: {market_info['market_name']}, 货币: {currency}")
        logger.debug(f"🐂 [DEBUG] - 市场详情: 中国A股={is_china}, 港股={is_hk}, 美股={is_us}")

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
            prompt = COMMODITY_BULL_PROMPT.format(
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
            prompt = f"""你是一位看涨分析师，负责为股票 {company_name}（股票代码：{ticker}）的投资建立强有力的论证。

⚠️ 重要提醒：当前分析的是 {'中国A股' if is_china else '海外股票'}，所有价格和估值请使用 {currency}（{currency_symbol}）作为单位。
⚠️ 在你的分析中，请始终使用公司名称"{company_name}"而不是股票代码"{ticker}"来称呼这家公司。

你的任务是构建基于证据的强有力案例，强调增长潜力、竞争优势和积极的市场指标。利用提供的研究和数据来解决担忧并有效反驳看跌论点。

请用中文回答，重点关注以下几个方面：
- 增长潜力：突出公司的市场机会、收入预测和可扩展性
- 竞争优势：强调独特产品、强势品牌或主导市场地位等因素
- 积极指标：使用财务健康状况、行业趋势和最新积极消息作为证据
- 反驳看跌观点：用具体数据和合理推理批判性分析看跌论点，全面解决担忧并说明为什么看涨观点更有说服力
- 参与讨论：以对话风格呈现你的论点，直接回应看跌分析师的观点并进行有效辩论，而不仅仅是列举数据

可用资源：
市场研究报告：{market_research_report}
社交媒体情绪报告：{sentiment_report}
最新世界事务新闻：{news_report}
公司基本面报告：{fundamentals_report}
辩论对话历史：{history}
最后的看跌论点：{current_response}
类似情况的反思和经验教训：{past_memory_str}

请使用这些信息提供令人信服的看涨论点，反驳看跌担忧，并参与动态辩论，展示看涨立场的优势。你还必须处理反思并从过去的经验教训和错误中学习。

请确保所有回答都使用中文。
"""

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
