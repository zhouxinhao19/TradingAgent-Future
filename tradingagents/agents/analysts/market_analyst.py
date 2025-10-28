from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
import traceback

# 导入分析模块日志装饰器
from tradingagents.utils.tool_logging import log_analyst_module

# 导入统一日志系统
from tradingagents.utils.logging_init import get_logger
logger = get_logger("default")

# 导入Google工具调用处理器
from tradingagents.agents.utils.google_tool_handler import GoogleToolCallHandler


def _get_company_name(ticker: str, market_info: dict) -> str:
    """
    根据股票代码获取公司名称

    Args:
        ticker: 股票代码
        market_info: 市场信息字典

    Returns:
        str: 公司名称
    """
    try:
        if market_info['is_china']:
            # 中国A股：使用统一接口获取股票信息
            from tradingagents.dataflows.interface import get_china_stock_info_unified
            stock_info = get_china_stock_info_unified(ticker)

            logger.debug(f"📊 [市场分析师] 获取股票信息返回: {stock_info[:200] if stock_info else 'None'}...")

            # 解析股票名称
            if stock_info and "股票名称:" in stock_info:
                company_name = stock_info.split("股票名称:")[1].split("\n")[0].strip()
                logger.info(f"✅ [市场分析师] 成功获取中国股票名称: {ticker} -> {company_name}")
                return company_name
            else:
                # 降级方案：尝试直接从数据源管理器获取
                logger.warning(f"⚠️ [市场分析师] 无法从统一接口解析股票名称: {ticker}，尝试降级方案")
                try:
                    from tradingagents.dataflows.data_source_manager import get_china_stock_info_unified as get_info_dict
                    info_dict = get_info_dict(ticker)
                    if info_dict and info_dict.get('name'):
                        company_name = info_dict['name']
                        logger.info(f"✅ [市场分析师] 降级方案成功获取股票名称: {ticker} -> {company_name}")
                        return company_name
                except Exception as e:
                    logger.error(f"❌ [市场分析师] 降级方案也失败: {e}")

                logger.error(f"❌ [市场分析师] 所有方案都无法获取股票名称: {ticker}")
                return f"股票代码{ticker}"

        elif market_info['is_hk']:
            # 港股：使用改进的港股工具
            try:
                from tradingagents.dataflows.improved_hk_utils import get_hk_company_name_improved
                company_name = get_hk_company_name_improved(ticker)
                logger.debug(f"📊 [DEBUG] 使用改进港股工具获取名称: {ticker} -> {company_name}")
                return company_name
            except Exception as e:
                logger.debug(f"📊 [DEBUG] 改进港股工具获取名称失败: {e}")
                # 降级方案：生成友好的默认名称
                clean_ticker = ticker.replace('.HK', '').replace('.hk', '')
                return f"港股{clean_ticker}"

        elif market_info['is_us']:
            # 美股：使用简单映射或返回代码
            us_stock_names = {
                'AAPL': '苹果公司',
                'TSLA': '特斯拉',
                'NVDA': '英伟达',
                'MSFT': '微软',
                'GOOGL': '谷歌',
                'AMZN': '亚马逊',
                'META': 'Meta',
                'NFLX': '奈飞'
            }

            company_name = us_stock_names.get(ticker.upper(), f"美股{ticker}")
            logger.debug(f"📊 [DEBUG] 美股名称映射: {ticker} -> {company_name}")
            return company_name

        else:
            return f"股票{ticker}"

    except Exception as e:
        logger.error(f"❌ [DEBUG] 获取公司名称失败: {e}")
        return f"股票{ticker}"


def create_market_analyst(llm, toolkit):

    def market_analyst_node(state):
        logger.debug(f"📈 [DEBUG] ===== 市场分析师节点开始 =====")

        current_date = state["trade_date"]
        ticker = state["company_of_interest"]

        logger.debug(f"📈 [DEBUG] 输入参数: ticker={ticker}, date={current_date}")
        logger.debug(f"📈 [DEBUG] 当前状态中的消息数量: {len(state.get('messages', []))}")
        logger.debug(f"📈 [DEBUG] 现有市场报告: {state.get('market_report', 'None')}")

        # 根据股票代码格式选择数据源
        from tradingagents.utils.stock_utils import StockUtils

        market_info = StockUtils.get_market_info(ticker)

        logger.debug(f"📈 [DEBUG] 股票类型检查: {ticker} -> {market_info['market_name']} ({market_info['currency_name']})")

        # 获取公司名称
        company_name = _get_company_name(ticker, market_info)
        logger.debug(f"📈 [DEBUG] 公司名称: {ticker} -> {company_name}")

        # 统一使用 get_stock_market_data_unified 工具
        # 该工具内部会自动识别股票类型（A股/港股/美股）并调用相应的数据源
        logger.info(f"📊 [市场分析师] 使用统一市场数据工具，自动识别股票类型")
        tools = [toolkit.get_stock_market_data_unified]

        # 安全地获取工具名称用于调试
        tool_names_debug = []
        for tool in tools:
            if hasattr(tool, 'name'):
                tool_names_debug.append(tool.name)
            elif hasattr(tool, '__name__'):
                tool_names_debug.append(tool.__name__)
            else:
                tool_names_debug.append(str(tool))
        logger.info(f"📊 [市场分析师] 绑定的工具: {tool_names_debug}")
        logger.info(f"📊 [市场分析师] 目标市场: {market_info['market_name']}")

        # 统一的系统提示，适用于所有股票类型
        system_message = (
            f"""你是一位专业的股票技术分析师。你必须对{company_name}（股票代码：{ticker}）进行详细的技术分析。

**股票信息：**
- 公司名称：{company_name}
- 股票代码：{ticker}
- 所属市场：{market_info['market_name']}
- 计价货币：{market_info['currency_name']}（{market_info['currency_symbol']}）

**工具调用指令：**
你有一个工具叫做get_stock_market_data_unified，你必须立即调用这个工具来获取{company_name}（{ticker}）的市场数据。
不要说你将要调用工具，直接调用工具。

**分析要求：**
1. 调用工具后，基于获取的真实数据进行技术分析
2. 分析移动平均线、MACD、RSI、布林带等技术指标
3. 考虑{market_info['market_name']}市场特点进行分析
4. 提供具体的数值和专业分析
5. 给出明确的投资建议
6. 所有价格数据使用{market_info['currency_name']}（{market_info['currency_symbol']}）表示

**输出格式：**
## 📊 股票基本信息
- 公司名称：{company_name}
- 股票代码：{ticker}
- 所属市场：{market_info['market_name']}

## 📈 技术指标分析
## 📉 价格趋势分析
## 💭 投资建议

请使用中文，基于真实数据进行分析。确保在分析中正确使用公司名称"{company_name}"和股票代码"{ticker}"。"""
        )


        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是一位专业的股票技术分析师，与其他分析师协作。"
                    "使用提供的工具来获取和分析股票数据。"
                    "⚠️ 重要工作流程："
                    "1. 如果消息历史中没有工具结果，立即调用 get_stock_market_data_unified 工具"
                    "2. 如果消息历史中已经有工具结果（ToolMessage），立即基于工具数据生成最终分析报告"
                    "3. 不要重复调用工具！一次工具调用就足够了！"
                    "4. 接收到工具数据后，必须立即生成完整的技术分析报告，不要再调用任何工具"
                    "如果你无法完全回答，没关系；其他分析师会从不同角度继续分析。"
                    "执行你能做的技术分析工作来取得进展。"
                    "如果你有明确的技术面投资建议：**买入/持有/卖出**，"
                    "请在你的回复中明确标注，但不要使用'最终交易建议'前缀，因为最终决策需要综合所有分析师的意见。"
                    "你可以使用以下工具：{tool_names}。\n{system_message}"
                    "供你参考，当前日期是{current_date}。"
                    "我们要分析的是{company_name}（股票代码：{ticker}）。"
                    "请确保所有分析都使用中文，并在分析中正确区分公司名称和股票代码。",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        # 安全地获取工具名称，处理函数和工具对象
        tool_names = []
        for tool in tools:
            if hasattr(tool, 'name'):
                tool_names.append(tool.name)
            elif hasattr(tool, '__name__'):
                tool_names.append(tool.__name__)
            else:
                tool_names.append(str(tool))

        prompt = prompt.partial(tool_names=", ".join(tool_names))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(ticker=ticker)
        prompt = prompt.partial(company_name=company_name)

        # 添加详细日志
        logger.info(f"📊 [市场分析师] LLM类型: {llm.__class__.__name__}")
        logger.info(f"📊 [市场分析师] LLM模型: {getattr(llm, 'model_name', 'unknown')}")
        logger.info(f"📊 [市场分析师] 消息历史数量: {len(state['messages'])}")
        logger.info(f"📊 [市场分析师] 公司名称: {company_name}")
        logger.info(f"📊 [市场分析师] 股票代码: {ticker}")

        # 打印完整的系统提示词
        logger.info(f"📊 [市场分析师] ========== 系统提示词开始 ==========")
        logger.info(f"{system_message}")
        logger.info(f"📊 [市场分析师] ========== 系统提示词结束 ==========")

        # 打印实际传递给LLM的消息
        logger.info(f"📊 [市场分析师] ========== 传递给LLM的消息 ==========")
        for i, msg in enumerate(state["messages"]):
            msg_type = type(msg).__name__
            msg_content = str(msg.content)[:200] if hasattr(msg, 'content') else str(msg)[:200]
            logger.info(f"📊 [市场分析师] 消息[{i}] 类型={msg_type}, 内容前200字符={msg_content}...")
        logger.info(f"📊 [市场分析师] ========== 消息列表结束 ==========")

        chain = prompt | llm.bind_tools(tools)

        logger.info(f"📊 [市场分析师] 开始调用LLM...")
        # 修复：传递字典而不是直接传递消息列表，以便 ChatPromptTemplate 能正确处理所有变量
        result = chain.invoke({"messages": state["messages"]})
        logger.info(f"📊 [市场分析师] LLM调用完成")

        # 打印LLM响应
        logger.info(f"📊 [市场分析师] ========== LLM响应开始 ==========")
        logger.info(f"📊 [市场分析师] 响应类型: {type(result).__name__}")
        logger.info(f"📊 [市场分析师] 响应内容: {str(result.content)[:1000]}...")
        if hasattr(result, 'tool_calls') and result.tool_calls:
            logger.info(f"📊 [市场分析师] 工具调用: {result.tool_calls}")
        logger.info(f"📊 [市场分析师] ========== LLM响应结束 ==========")

        # 使用统一的Google工具调用处理器
        if GoogleToolCallHandler.is_google_model(llm):
            logger.info(f"📊 [市场分析师] 检测到Google模型，使用统一工具调用处理器")
            
            # 创建分析提示词
            analysis_prompt_template = GoogleToolCallHandler.create_analysis_prompt(
                ticker=ticker,
                company_name=company_name,
                analyst_type="市场分析",
                specific_requirements="重点关注市场数据、价格走势、交易量变化等市场指标。"
            )
            
            # 处理Google模型工具调用
            report, messages = GoogleToolCallHandler.handle_google_tool_calls(
                result=result,
                llm=llm,
                tools=tools,
                state=state,
                analysis_prompt_template=analysis_prompt_template,
                analyst_name="市场分析师"
            )
            
            return {
                "messages": [result],
                "market_report": report,
            }
        else:
            # 非Google模型的处理逻辑
            logger.info(f"📊 [市场分析师] 非Google模型 ({llm.__class__.__name__})，使用标准处理逻辑")
            logger.info(f"📊 [市场分析师] 检查LLM返回结果...")
            logger.info(f"📊 [市场分析师] - 是否有tool_calls: {hasattr(result, 'tool_calls')}")
            if hasattr(result, 'tool_calls'):
                logger.info(f"📊 [市场分析师] - tool_calls数量: {len(result.tool_calls)}")
                if result.tool_calls:
                    for i, tc in enumerate(result.tool_calls):
                        logger.info(f"📊 [市场分析师] - tool_call[{i}]: {tc.get('name', 'unknown')}")

            # 处理市场分析报告
            if len(result.tool_calls) == 0:
                # 没有工具调用，直接使用LLM的回复
                report = result.content
                logger.info(f"📊 [市场分析师] ✅ 直接回复（无工具调用），长度: {len(report)}")
                logger.debug(f"📊 [DEBUG] 直接回复内容预览: {report[:200]}...")
            else:
                # 有工具调用，执行工具并生成完整分析报告
                logger.info(f"📊 [市场分析师] 🔧 检测到工具调用: {[call.get('name', 'unknown') for call in result.tool_calls]}")

                try:
                    # 执行工具调用
                    from langchain_core.messages import ToolMessage, HumanMessage

                    tool_messages = []
                    for tool_call in result.tool_calls:
                        tool_name = tool_call.get('name')
                        tool_args = tool_call.get('args', {})
                        tool_id = tool_call.get('id')

                        logger.debug(f"📊 [DEBUG] 执行工具: {tool_name}, 参数: {tool_args}")

                        # 找到对应的工具并执行
                        tool_result = None
                        for tool in tools:
                            # 安全地获取工具名称进行比较
                            current_tool_name = None
                            if hasattr(tool, 'name'):
                                current_tool_name = tool.name
                            elif hasattr(tool, '__name__'):
                                current_tool_name = tool.__name__

                            if current_tool_name == tool_name:
                                try:
                                    if tool_name == "get_china_stock_data":
                                        # 中国股票数据工具
                                        tool_result = tool.invoke(tool_args)
                                    else:
                                        # 其他工具
                                        tool_result = tool.invoke(tool_args)
                                    logger.debug(f"📊 [DEBUG] 工具执行成功，结果长度: {len(str(tool_result))}")
                                    break
                                except Exception as tool_error:
                                    logger.error(f"❌ [DEBUG] 工具执行失败: {tool_error}")
                                    tool_result = f"工具执行失败: {str(tool_error)}"

                        if tool_result is None:
                            tool_result = f"未找到工具: {tool_name}"

                        # 创建工具消息
                        tool_message = ToolMessage(
                            content=str(tool_result),
                            tool_call_id=tool_id
                        )
                        tool_messages.append(tool_message)

                    # 基于工具结果生成完整分析报告
                    analysis_prompt = f"""现在请基于上述工具获取的数据，生成详细的技术分析报告。

要求：
1. 报告必须基于工具返回的真实数据进行分析
2. 包含具体的技术指标数值和专业分析
3. 提供明确的投资建议和风险提示
4. 报告长度不少于800字
5. 使用中文撰写

请分析股票{ticker}的技术面情况，包括：
- 价格趋势分析
- 技术指标解读
- 支撑阻力位分析
- 成交量分析
- 投资建议"""

                    # 构建完整的消息序列
                    messages = state["messages"] + [result] + tool_messages + [HumanMessage(content=analysis_prompt)]

                    # 生成最终分析报告
                    final_result = llm.invoke(messages)
                    report = final_result.content

                    logger.info(f"📊 [市场分析师] 生成完整分析报告，长度: {len(report)}")

                    # 返回包含工具调用和最终分析的完整消息序列
                    return {
                        "messages": [result] + tool_messages + [final_result],
                        "market_report": report,
                    }

                except Exception as e:
                    logger.error(f"❌ [市场分析师] 工具执行或分析生成失败: {e}")
                    traceback.print_exc()

                    # 降级处理：返回工具调用信息
                    report = f"市场分析师调用了工具但分析生成失败: {[call.get('name', 'unknown') for call in result.tool_calls]}"

                    return {
                        "messages": [result],
                        "market_report": report,
                    }

            return {
                "messages": [result],
                "market_report": report,
            }

    return market_analyst_node
