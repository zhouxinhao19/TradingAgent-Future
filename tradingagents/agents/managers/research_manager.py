import time
import json

# 导入统一日志系统
from tradingagents.utils.logging_init import get_logger
from tradingagents.agents.utils.instrument_utils import build_instrument_context
logger = get_logger("default")

COMMODITY_REASONING_PROMPT = """你是期货推理分析师。在单次分析中完成多空双向推理，输出结构化分析报告。

⚠️ 本报告是投研辅助工具，**不是交易指令**。严禁输出具体交易价位。

## 分析对象
- 合约: {full_symbol}
- 品种: {variety_name}
- 分析日期: {analysis_date}

## 标的约束
{instrument_context}

## L1 分析师报告索引（证据链 — 每个结论必须引用至少 1 个 ID）
{analyst_registry_summary}

## 输入报告

### 技术面报告
{market_research_report}

### 基本面报告（基差+库存+期限结构）
{fundamentals_report}

### 持仓情绪报告
{sentiment_report}

### 新闻/产业事件报告
{news_report}

## 历史经验教训
{past_memory_str}

---

## 输出要求

输出包含以下三大模块的复合 JSON。

**JSON 顶级 key 必须严格使用以下名称（不要用"模块A/B/C"作为 key）：**

### 估值驱动矩阵

评估以下维度的当前状态、估值判断和驱动方向：
1. 基差（估值）
2. 库存（驱动）
3. 期限结构（估值+驱动）
4. 技术面（驱动+择时）
5. 持仓情绪（验证）
6. 宏观/新闻（驱动）

每个维度必须包含：
- "维度": 维度名称
- "当前状态": 简练描述
- "估值判断": 低估/合理/高估
- "驱动方向": bullish/bearish/neutral
- "驱动因素": 关键驱动列表
- "置信度": 0~1 浮点数
- "数据来源": [引用至少 1 个分析师报告 ID，如 "REF-TECH-a1b2c3d4"]

### 多空对照表

每个关键分歧包含看涨/看跌双方逻辑，每个逻辑后标注引用 ID。

### 三种情景推演

三种情景（保守/基准/乐观），每个包含：
- "推演方向": 做多/做空/中性
- "触发条件": 可观测的市场信号列表
- "关注焦点": 应关注的关键变量
- "风险节点": 情景失效条件
- "置信度": 0~1 浮点数
- "数据来源": [引用至少 2 个不同分析师报告 ID]

### 禁止项
- ❌ 禁止 "买入"/"卖出"，统一用 "做多"/"做空"
- ❌ 禁止具体交易价位（入场价/止损价/目标价/手数）
- ❌ 禁止保证金占用比例
- ❌ 禁止虚构未提供的分析师报告 ID

### 允许项
- ✅ 三种情景允许方向不同（如保守=做多、基准=中性、乐观=做空）
- ✅ 方向不同时须在"综合情景判断"中标注核心分歧
- ✅ 触发条件必须是可观测、可验证的市场信号

请输出**纯 JSON**（无 Markdown 代码块包裹），包含以上三大模块。"""


def create_research_manager(llm, memory):
    def research_manager_node(state) -> dict:
        ticker = state["company_of_interest"]
        instrument_context = build_instrument_context(ticker)
        market_research_report = state["market_report"]
        sentiment_report = state.get("position_report") or state.get("sentiment_report", "")
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        # === Phase 3b-ii-B:检测 asset_type ===
        asset_type = state.get("asset_type", "stock")

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
            # ===== 新推理分析师路径 =====
            full_symbol = state.get("full_symbol") or ticker
            variety_name = state.get("variety_name", "")
            trade_date = state.get("trade_date", "")

            # 构建 analyst_registry_summary
            registry = state.get("analyst_registry", {}) or {}
            if registry:
                registry_lines = []
                for ref_id, entry in registry.items():
                    cn_name = entry.get("cn_name", entry.get("analyst", "?"))
                    direction = entry.get("direction", "?")
                    summary = entry.get("summary", "")
                    registry_lines.append(f"- {cn_name} | {direction} | {summary} | ID:{ref_id}")
                analyst_registry_summary = "\n".join(registry_lines)
            else:
                analyst_registry_summary = "(暂无分析师报告索引)"

            prompt = COMMODITY_REASONING_PROMPT.format(
                full_symbol=full_symbol,
                variety_name=variety_name,
                analysis_date=trade_date,
                instrument_context=instrument_context,
                market_research_report=market_research_report,
                fundamentals_report=fundamentals_report,
                sentiment_report=sentiment_report,
                news_report=news_report,
                analyst_registry_summary=analyst_registry_summary,
                past_memory_str=past_memory_str,
            )
            # 直接调用 llm（不做 chain）
            response = llm.invoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)

            # 写入：简化 investment_debate_state（无辩论历史）
            return {
                "investment_debate_state": {
                    "judge_decision": content,
                    "history": "",
                    "count": 0,
                },
                "investment_plan": content,
            }
        else:
            history = state["investment_debate_state"].get("history", "")
            investment_debate_state = state["investment_debate_state"]

            prompt = f"""作为投资组合经理和辩论主持人，您的职责是批判性地评估这轮辩论并做出明确决策：支持看跌分析师、看涨分析师，或者仅在基于所提出论点有强有力理由时选择持有。

简洁地总结双方的关键观点，重点关注最有说服力的证据或推理。您的建议——买入、卖出或持有——必须明确且可操作。避免仅仅因为双方都有有效观点就默认选择持有；要基于辩论中最强有力的论点做出承诺。

此外，为交易员制定详细的投资计划。这应该包括：

您的建议：基于最有说服力论点的明确立场。
理由：解释为什么这些论点导致您的结论。
战略行动：实施建议的具体步骤。
📊 目标价格分析：基于所有可用报告（基本面、新闻、情绪），提供全面的目标价格区间和具体价格目标。考虑：
- 基本面报告中的基本估值
- 新闻对价格预期的影响
- 情绪驱动的价格调整
- 技术支撑/阻力位
- 风险调整价格情景（保守、基准、乐观）
- 价格目标的时间范围（1个月、3个月、6个月）
💰 您必须提供具体的目标价格 - 不要回复"无法确定"或"需要更多信息"。

考虑您在类似情况下的过去错误。利用这些见解来完善您的决策制定，确保您在学习和改进。以对话方式呈现您的分析，就像自然说话一样，不使用特殊格式。

以下是您对错误的过去反思：
\"{past_memory_str}\"

标的约束：
{instrument_context}

以下是综合分析报告：
市场研究：{market_research_report}

持仓分析：{sentiment_report}

新闻分析：{news_report}

基本面分析：{fundamentals_report}

以下是辩论：
辩论历史：
{history}

请用中文撰写所有分析内容和建议。"""

        # 📊 统计 prompt 大小
        prompt_length = len(prompt)
        estimated_tokens = int(prompt_length / 1.8)

        logger.info(f"📊 [Research Manager] Prompt 统计:")
        logger.info(f"   - 辩论历史长度: {len(history)} 字符")
        logger.info(f"   - 总 Prompt 长度: {prompt_length} 字符")
        logger.info(f"   - 估算输入 Token: ~{estimated_tokens} tokens")

        # ⏱️ 记录开始时间
        start_time = time.time()

        response = llm.invoke(prompt)

        # ⏱️ 记录结束时间
        elapsed_time = time.time() - start_time

        # 📊 统计响应信息
        response_length = len(response.content) if response and hasattr(response, 'content') else 0
        estimated_output_tokens = int(response_length / 1.8)

        logger.info(f"⏱️ [Research Manager] LLM调用耗时: {elapsed_time:.2f}秒")
        logger.info(f"📊 [Research Manager] 响应统计: {response_length} 字符, 估算~{estimated_output_tokens} tokens")

        new_investment_debate_state = {
            "judge_decision": response.content,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": response.content,
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": response.content,
        }

    return research_manager_node
