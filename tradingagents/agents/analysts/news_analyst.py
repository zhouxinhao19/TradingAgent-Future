from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from datetime import datetime

# 导入统一日志系统和分析模块日志装饰器
from tradingagents.utils.logging_init import get_logger
from tradingagents.utils.tool_logging import log_analyst_module
# 导入统一新闻工具
from tradingagents.tools.unified_news_tool import create_unified_news_tool
# 导入股票工具类
from tradingagents.utils.stock_utils import StockUtils

logger = get_logger("analysts.news")


def create_news_analyst(llm, toolkit):
    @log_analyst_module("news")
    def news_analyst_node(state):
        start_time = datetime.now()
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        
        logger.info(f"[新闻分析师] 开始分析 {ticker} 的新闻，交易日期: {current_date}")
        session_id = state.get("session_id", "未知会话")
        logger.info(f"[新闻分析师] 会话ID: {session_id}，开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 获取市场信息
        market_info = StockUtils.get_market_info(ticker)
        logger.info(f"[新闻分析师] 股票类型: {market_info['market_name']}")
        
        # 🔧 使用统一新闻工具，简化工具调用
        logger.info(f"[新闻分析师] 使用统一新闻工具，自动识别股票类型并获取相应新闻")
   # 创建统一新闻工具
        unified_news_tool = create_unified_news_tool(toolkit)
        unified_news_tool.name = "get_stock_news_unified"
        
        tools = [unified_news_tool]
        logger.info(f"[新闻分析师] 已加载统一新闻工具: get_stock_news_unified")

        system_message = (
            """您是一位专业的财经新闻分析师，负责分析最新的市场新闻和事件对股票价格的潜在影响。

您的主要职责包括：
1. 获取和分析最新的实时新闻（优先15-30分钟内的新闻）
2. 评估新闻事件的紧急程度和市场影响
3. 识别可能影响股价的关键信息
4. 分析新闻的时效性和可靠性
5. 提供基于新闻的交易建议和价格影响评估

重点关注的新闻类型：
- 财报发布和业绩指导
- 重大合作和并购消息
- 政策变化和监管动态
- 突发事件和危机管理
- 行业趋势和技术突破
- 管理层变动和战略调整

分析要点：
- 新闻的时效性（发布时间距离现在多久）
- 新闻的可信度（来源权威性）
- 市场影响程度（对股价的潜在影响）
- 投资者情绪变化（正面/负面/中性）
- 与历史类似事件的对比

📊 价格影响分析要求：
- 评估新闻对股价的短期影响（1-3天）
- 分析可能的价格波动幅度（百分比）
- 提供基于新闻的价格调整建议
- 识别关键价格支撑位和阻力位
- 评估新闻对长期投资价值的影响
- 不允许回复'无法评估价格影响'或'需要更多信息'

请特别注意：
⚠️ 如果新闻数据存在滞后（超过2小时），请在分析中明确说明时效性限制
✅ 优先分析最新的、高相关性的新闻事件
📊 提供新闻对股价影响的量化评估和具体价格预期
💰 必须包含基于新闻的价格影响分析和调整建议

请撰写详细的中文分析报告，并在报告末尾附上Markdown表格总结关键发现。"""
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "您是一位专业的财经新闻分析师。"
                    "\n🚨 CRITICAL REQUIREMENT - 绝对强制要求："
                    "\n"
                    "\n❌ 禁止行为："
                    "\n- 绝对禁止在没有调用工具的情况下直接回答"
                    "\n- 绝对禁止基于推测或假设生成任何分析内容"
                    "\n- 绝对禁止跳过工具调用步骤"
                    "\n- 绝对禁止说'我无法获取实时数据'等借口"
                    "\n"
                    "\n✅ 强制执行步骤："
                    "\n1. 您的第一个动作必须是调用 get_stock_news_unified 工具"
                    "\n2. 该工具会自动识别股票类型（A股、港股、美股）并获取相应新闻"
                    "\n3. 只有在成功获取新闻数据后，才能开始分析"
                    "\n4. 您的回答必须基于工具返回的真实数据"
                    "\n"
                    "\n🔧 工具调用格式示例："
                    "\n调用: get_stock_news_unified(stock_code='{ticker}', max_news=10)"
                    "\n"
                    "\n⚠️ 如果您不调用工具，您的回答将被视为无效并被拒绝。"
                    "\n⚠️ 您必须先调用工具获取数据，然后基于数据进行分析。"
                    "\n⚠️ 没有例外，没有借口，必须调用工具。"
                    "\n"
                    "\n您可以访问以下工具：{tool_names}。"
                    "\n{system_message}"
                    "\n供您参考，当前日期是{current_date}。我们正在查看公司{ticker}。"
                    "\n请严格按照上述要求执行，用中文撰写所有分析内容。",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(ticker=ticker)
        
        logger.info(f"[新闻分析师] 准备调用LLM进行新闻分析，模型: {llm.__class__.__name__}")
        
        # 🚨 DashScope预处理：强制获取新闻数据
        pre_fetched_news = None
        if 'DashScope' in llm.__class__.__name__:
            logger.warning(f"[新闻分析师] 🚨 检测到DashScope模型，启动预处理强制新闻获取...")
            try:
                # 强制预先获取新闻数据
                logger.info(f"[新闻分析师] 🔧 预处理：强制调用统一新闻工具...")
                pre_fetched_news = unified_news_tool(stock_code=ticker, max_news=10)
                
                if pre_fetched_news and len(pre_fetched_news.strip()) > 100:
                    logger.info(f"[新闻分析师] ✅ 预处理成功获取新闻: {len(pre_fetched_news)} 字符")
                    
                    # 直接基于预获取的新闻生成分析，跳过工具调用
                    enhanced_prompt = f"""
您是一位专业的财经新闻分析师。请基于以下已获取的最新新闻数据，对股票 {ticker} 进行详细分析：

=== 最新新闻数据 ===
{pre_fetched_news}

=== 分析要求 ===
{system_message}

请基于上述真实新闻数据撰写详细的中文分析报告。注意：新闻数据已经提供，您无需再调用任何工具。
"""
                    
                    logger.info(f"[新闻分析师] 🔄 使用预获取新闻数据直接生成分析...")
                    llm_start_time = datetime.now()
                    result = llm.invoke([{"role": "user", "content": enhanced_prompt}])
                    
                    llm_end_time = datetime.now()
                    llm_time_taken = (llm_end_time - llm_start_time).total_seconds()
                    logger.info(f"[新闻分析师] LLM调用完成（预处理模式），耗时: {llm_time_taken:.2f}秒")
                    
                    # 直接返回结果，跳过后续的工具调用检测
                    if hasattr(result, 'content') and result.content:
                        report = result.content
                        logger.info(f"[新闻分析师] ✅ 预处理模式成功，报告长度: {len(report)} 字符")
                        
                        # 跳转到最终处理
                        state["messages"].append(result)
                        end_time = datetime.now()
                        time_taken = (end_time - start_time).total_seconds()
                        logger.info(f"[新闻分析师] 新闻分析完成，总耗时: {time_taken:.2f}秒")
                        return {
                            "messages": [result],
                            "news_report": report,
                        }
                    
                else:
                    logger.warning(f"[新闻分析师] ⚠️ 预处理获取新闻失败，回退到标准模式")
                    
            except Exception as e:
                logger.error(f"[新闻分析师] ❌ 预处理失败: {e}，回退到标准模式")
        
        # 标准模式：正常的LLM调用
        llm_start_time = datetime.now()
        chain = prompt | llm.bind_tools(tools)
        logger.info(f"[新闻分析师] 开始LLM调用，分析 {ticker} 的新闻")
        result = chain.invoke(state["messages"])
        
        llm_end_time = datetime.now()
        llm_time_taken = (llm_end_time - llm_start_time).total_seconds()
        logger.info(f"[新闻分析师] LLM调用完成，耗时: {llm_time_taken:.2f}秒")

        report = ""
        
        # 记录工具调用情况
        tool_call_count = len(result.tool_calls) if hasattr(result, 'tool_calls') else 0
        logger.info(f"[新闻分析师] LLM调用了 {tool_call_count} 个工具")
        
        # 🔧 工具调用失败检测和处理机制
        tool_call_failed = False
        used_tool_names = []
        
        if tool_call_count > 0 and hasattr(result, 'tool_calls'):
            # 记录使用了哪些工具
            # 处理 tool_calls 可能是字典对象的情况
            for call in result.tool_calls:
                if hasattr(call, 'name'):
                    used_tool_names.append(call.name)
                elif isinstance(call, dict) and 'name' in call:
                    used_tool_names.append(call['name'])
                else:
                    logger.warning(f"[新闻分析师] 无法识别的工具调用格式: {type(call)}")
            
            if used_tool_names:
                logger.info(f"[新闻分析师] 使用的工具: {', '.join(used_tool_names)}")
            else:
                logger.warning(f"[新闻分析师] 工具调用存在但无法提取工具名称")
                tool_call_failed = True
        else:
            # 没有工具调用，但对于新闻分析师来说这通常是不正常的
            logger.warning(f"[新闻分析师] ⚠️ LLM没有调用任何工具，这可能表示工具调用机制失败")
            tool_call_failed = True

        # 🔧 增强的DashScope工具调用失败检测和补救机制
        if 'DashScope' in llm.__class__.__name__:
            
            # 首先检查生成的内容是否包含真实新闻数据的特征
            content_has_real_news = False
            if hasattr(result, 'content') and result.content:
                content = result.content.lower()
                # 检查是否包含真实新闻的特征词汇
                news_indicators = ['发布时间', '新闻标题', '文章来源', '东方财富', '财联社', '证券时报', '上海证券报', '中国证券报']
                content_has_real_news = any(indicator in content for indicator in news_indicators)
                
                # 检查是否包含具体的时间信息（真实新闻的特征）
                import re
                time_pattern = r'20\d{2}-\d{2}-\d{2}'
                has_specific_dates = bool(re.search(time_pattern, content))
                content_has_real_news = content_has_real_news or has_specific_dates
            
            logger.info(f"[新闻分析师] 🔍 内容真实性检查: 包含真实新闻特征={content_has_real_news}")
            
            # 情况1：DashScope声称调用了工具但内容可能是虚假的
            if (tool_call_count > 0 and 'get_stock_news_unified' in used_tool_names):
                logger.info(f"[新闻分析师] 🔍 检测到DashScope调用了get_stock_news_unified，验证内容真实性...")
                
                # 如果内容不包含真实新闻特征，强制重新获取
                if not content_has_real_news:
                    logger.warning(f"[新闻分析师] ⚠️ 内容缺乏真实新闻特征，强制重新获取...")
                    
                    try:
                        logger.info(f"[新闻分析师] 🔧 强制调用统一新闻工具进行验证...")
                        fallback_news = unified_news_tool(stock_code=ticker, max_news=10)
                        
                        if fallback_news and len(fallback_news.strip()) > 100:
                            logger.info(f"[新闻分析师] ✅ 强制调用成功，获得新闻数据: {len(fallback_news)} 字符")
                            
                            # 重新生成分析，包含获取到的新闻数据
                            enhanced_prompt = f"""
基于以下最新获取的新闻数据，请对 {ticker} 进行详细的新闻分析：

=== 最新新闻数据 ===
{fallback_news}

=== 分析要求 ===
{system_message}

请基于上述新闻数据撰写详细的中文分析报告。
"""
                            
                            logger.info(f"[新闻分析师] 🔄 基于强制获取的新闻数据重新生成分析...")
                            enhanced_result = llm.invoke([{"role": "user", "content": enhanced_prompt}])
                            
                            if hasattr(enhanced_result, 'content') and enhanced_result.content:
                                report = enhanced_result.content
                                logger.info(f"[新闻分析师] ✅ 基于强制获取数据生成报告，长度: {len(report)} 字符")
                            else:
                                logger.warning(f"[新闻分析师] ⚠️ 重新生成分析失败，使用原始结果")
                                report = result.content
                        else:
                            logger.warning(f"[新闻分析师] ⚠️ 强制调用未获得有效新闻数据")
                            report = result.content
                            
                    except Exception as e:
                        logger.error(f"[新闻分析师] ❌ 强制调用失败: {e}")
                        report = result.content
                else:
                    logger.info(f"[新闻分析师] ✅ 内容包含真实新闻特征，使用原始结果")
                    report = result.content
            
            # 情况2：DashScope完全没有调用任何工具（最常见的问题）
            elif tool_call_count == 0:
                logger.warning(f"[新闻分析师] 🚨 DashScope没有调用任何工具，这是异常情况，启动强制补救...")
                
                try:
                    # 强制获取新闻数据
                    logger.info(f"[新闻分析师] 🔧 强制调用统一新闻工具获取新闻数据...")
                    forced_news = unified_news_tool(stock_code=ticker, max_news=10)
                    
                    if forced_news and len(forced_news.strip()) > 100:
                        logger.info(f"[新闻分析师] ✅ 强制获取新闻成功: {len(forced_news)} 字符")
                        
                        # 基于真实新闻数据重新生成分析
                        forced_prompt = f"""
您是一位专业的财经新闻分析师。请基于以下最新获取的新闻数据，对股票 {ticker} 进行详细的新闻分析：

=== 最新新闻数据 ===
{forced_news}

=== 分析要求 ===
{system_message}

请基于上述真实新闻数据撰写详细的中文分析报告，包含：
1. 新闻事件的关键信息提取
2. 对股价的潜在影响分析
3. 投资建议和风险评估
4. 价格影响的量化评估

请确保分析基于真实的新闻数据，而不是推测。
"""
                        
                        logger.info(f"[新闻分析师] 🔄 基于强制获取的新闻数据重新生成完整分析...")
                        forced_result = llm.invoke([{"role": "user", "content": forced_prompt}])
                        
                        if hasattr(forced_result, 'content') and forced_result.content:
                            report = forced_result.content
                            logger.info(f"[新闻分析师] ✅ 强制补救成功，生成基于真实数据的报告，长度: {len(report)} 字符")
                        else:
                            logger.warning(f"[新闻分析师] ⚠️ 强制补救失败，使用原始结果")
                            report = result.content
                    else:
                        logger.warning(f"[新闻分析师] ⚠️ 统一新闻工具获取失败，使用原始结果")
                        report = result.content
                        
                except Exception as e:
                    logger.error(f"[新闻分析师] ❌ 强制补救过程失败: {e}")
                    report = result.content
            
            # 情况3：调用了其他工具但没有调用主要工具
            elif tool_call_count > 0 and 'get_stock_news_unified' not in used_tool_names:
                logger.warning(f"[新闻分析师] ⚠️ DashScope调用了工具但未使用主要新闻工具，检查内容质量...")
                
                if not content_has_real_news:
                    logger.warning(f"[新闻分析师] ⚠️ 内容质量不佳，强制补充真实新闻...")
                    
                    try:
                        supplement_news = unified_news_tool(stock_code=ticker, max_news=10)
                        
                        if supplement_news and len(supplement_news.strip()) > 100:
                            logger.info(f"[新闻分析师] ✅ 补充新闻获取成功: {len(supplement_news)} 字符")
                            
                            # 将原始分析与真实新闻结合
                            combined_prompt = f"""
请将以下原始分析与最新新闻数据结合，生成更准确的分析报告：

=== 原始分析 ===
{result.content}

=== 最新新闻数据 ===
{supplement_news}

请基于真实新闻数据修正和增强分析内容。
"""
                            
                            combined_result = llm.invoke([{"role": "user", "content": combined_prompt}])
                            
                            if hasattr(combined_result, 'content') and combined_result.content:
                                report = combined_result.content
                                logger.info(f"[新闻分析师] ✅ 结合真实新闻生成增强报告，长度: {len(report)} 字符")
                            else:
                                report = result.content
                        else:
                            report = result.content
                            
                    except Exception as e:
                        logger.error(f"[新闻分析师] ❌ 补充新闻失败: {e}")
                        report = result.content
                else:
                    report = result.content
        else:
            # 非DashScope模型（如DeepSeek等），也需要工具调用失败检测和补救机制
            logger.info(f"[新闻分析师] 🔍 非DashScope模型 ({llm.__class__.__name__}) 工具调用检测...")
            
            # 检查是否成功调用了工具并获得了有效内容
            if tool_call_count == 0:
                logger.warning(f"[新闻分析师] ⚠️ {llm.__class__.__name__} 没有调用任何工具，启动补救机制...")
                
                try:
                    # 强制获取新闻数据
                    logger.info(f"[新闻分析师] 🔧 强制调用统一新闻工具获取新闻数据...")
                    forced_news = unified_news_tool(stock_code=ticker, max_news=10)
                    
                    if forced_news and len(forced_news.strip()) > 100:
                        logger.info(f"[新闻分析师] ✅ 强制获取新闻成功: {len(forced_news)} 字符")
                        
                        # 基于真实新闻数据重新生成分析
                        forced_prompt = f"""
您是一位专业的财经新闻分析师。请基于以下最新获取的新闻数据，对股票 {ticker} 进行详细的新闻分析：

=== 最新新闻数据 ===
{forced_news}

=== 分析要求 ===
{system_message}

请基于上述真实新闻数据撰写详细的中文分析报告，包含：
1. 新闻事件的关键信息提取
2. 对股价的潜在影响分析
3. 投资建议和风险评估
4. 价格影响的量化评估

请确保分析基于真实的新闻数据，而不是推测。
"""
                        
                        logger.info(f"[新闻分析师] 🔄 基于强制获取的新闻数据重新生成完整分析...")
                        forced_result = llm.invoke([{"role": "user", "content": forced_prompt}])
                        
                        if hasattr(forced_result, 'content') and forced_result.content:
                            report = forced_result.content
                            logger.info(f"[新闻分析师] ✅ 强制补救成功，生成基于真实数据的报告，长度: {len(report)} 字符")
                        else:
                            logger.warning(f"[新闻分析师] ⚠️ 强制补救失败，使用原始结果")
                            report = result.content
                    else:
                        logger.warning(f"[新闻分析师] ⚠️ 统一新闻工具获取失败，使用原始结果")
                        report = result.content
                        
                except Exception as e:
                    logger.error(f"[新闻分析师] ❌ 强制补救过程失败: {e}")
                    report = result.content
            else:
                # 有工具调用，检查内容质量
                content_has_real_news = False
                if hasattr(result, 'content') and result.content:
                    content = result.content.lower()
                    # 检查是否包含真实新闻的特征词汇
                    news_indicators = ['发布时间', '新闻标题', '文章来源', '东方财富', '财联社', '证券时报', '上海证券报', '中国证券报']
                    content_has_real_news = any(indicator in content for indicator in news_indicators)
                    
                    # 检查是否包含具体的时间信息（真实新闻的特征）
                    import re
                    time_pattern = r'20\d{2}-\d{2}-\d{2}'
                    has_specific_dates = bool(re.search(time_pattern, content))
                    content_has_real_news = content_has_real_news or has_specific_dates
                
                logger.info(f"[新闻分析师] 🔍 内容真实性检查: 包含真实新闻特征={content_has_real_news}")
                
                if not content_has_real_news:
                    logger.warning(f"[新闻分析师] ⚠️ 内容缺乏真实新闻特征，强制补充真实新闻...")
                    
                    try:
                        supplement_news = unified_news_tool(stock_code=ticker, max_news=10)
                        
                        if supplement_news and len(supplement_news.strip()) > 100:
                            logger.info(f"[新闻分析师] ✅ 补充新闻获取成功: {len(supplement_news)} 字符")
                            
                            # 将原始分析与真实新闻结合
                            combined_prompt = f"""
请将以下原始分析与最新新闻数据结合，生成更准确的分析报告：

=== 原始分析 ===
{result.content}

=== 最新新闻数据 ===
{supplement_news}

请基于真实新闻数据修正和增强分析内容。
"""
                            
                            combined_result = llm.invoke([{"role": "user", "content": combined_prompt}])
                            
                            if hasattr(combined_result, 'content') and combined_result.content:
                                report = combined_result.content
                                logger.info(f"[新闻分析师] ✅ 结合真实新闻生成增强报告，长度: {len(report)} 字符")
                            else:
                                report = result.content
                        else:
                            report = result.content
                            
                    except Exception as e:
                        logger.error(f"[新闻分析师] ❌ 补充新闻失败: {e}")
                        report = result.content
                else:
                    logger.info(f"[新闻分析师] ✅ 内容包含真实新闻特征，使用原始结果")
                    report = result.content
        
        # 最终检查：如果报告仍然为空或过短，进行最后的补救
        if not report or len(report.strip()) < 100:
            logger.warning(f"[新闻分析师] ⚠️ 最终报告过短或为空，进行最后补救...")
            
            # 如果是A股且内容很短，可能是工具调用失败导致的
            if market_info['is_china']:
                logger.warning(f"[新闻分析师] ⚠️ A股新闻报告异常，尝试最后的补救措施")
                
                # 尝试使用备用工具
                try:
                    logger.info(f"[新闻分析师] 🔄 最后尝试使用统一新闻工具获取新闻...")
                    backup_news = unified_news_tool(stock_code=ticker, max_news=10)
                    
                    if backup_news and len(backup_news.strip()) > 100:
                        logger.info(f"[新闻分析师] ✅ 最后补救获取成功: {len(backup_news)} 字符")
                        
                        # 如果原始报告有内容，合并；否则直接使用新闻数据
                        if report and len(report.strip()) > 0:
                            enhanced_report = f"{report}\n\n=== 补充新闻信息 ===\n{backup_news}"
                        else:
                            enhanced_report = f"=== {ticker} 最新新闻信息 ===\n{backup_news}"
                        
                        report = enhanced_report
                        logger.info(f"[新闻分析师] 📝 最后补救完成，最终报告长度: {len(report)} 字符")
                        
                except Exception as e:
                    logger.error(f"[新闻分析师] ❌ 最后补救失败: {e}")
                    # 如果所有补救都失败，至少确保有基本的报告内容
                    if not report or len(report.strip()) < 50:
                        report = result.content if hasattr(result, 'content') else f"无法获取 {ticker} 的新闻分析数据"
        
        total_time_taken = (datetime.now() - start_time).total_seconds()
        logger.info(f"[新闻分析师] 新闻分析完成，总耗时: {total_time_taken:.2f}秒")

        # 🔧 修复死循环问题：返回清洁的AIMessage，不包含tool_calls
        # 这确保工作流图能正确判断分析已完成，避免重复调用
        from langchain_core.messages import AIMessage
        clean_message = AIMessage(content=report)
        
        logger.info(f"[新闻分析师] ✅ 返回清洁消息，报告长度: {len(report)} 字符")

        return {
            "messages": [clean_message],
            "news_report": report,
        }

    return news_analyst_node
