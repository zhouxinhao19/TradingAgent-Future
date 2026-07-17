"""
[DEPRECATED — commodity 路径]

该文件中的 commodity 分支（Phase 3b-ii-B）已被 Phase 4 投研总监节点替代。
commodity 决策链不再经过风控辩论，改为：
  L1(4 分析师) → L2 推理分析师 → 量化检查器(纯规则) → 投研总监(1xLLM) → END

stock 路径仍通过 asset_type 分支使用此文件，请勿删除。
"""
from langchain_core.messages import AIMessage
import time
import json

# 导入统一日志系统
from tradingagents.utils.logging_init import get_logger
logger = get_logger("default")

# === Phase 3b-ii-B:Commodity prompt 注入(占位) ===
COMMODITY_CONSERVATIVE_PROMPT = """作为保守期货风险分析师,您认为期货高杠杆会放大亏损,必须严格控制风险敞口。重点强调:

⚠️ 这是大宗商品期货(非股票):
- **杠杆反向放大**:期货 8-15 倍杠杆,做错方向时亏损放大同样倍数
- **穿仓风险**:极端行情下,保证金不足会被强平甚至穿仓(倒欠交易所)
- **涨跌停无法平仓**:单日反向停板,无法止损出场,次日跳空继续亏损
- **Contango 损耗**:做多远月合约在 Contango 结构下,每次展期都亏损(carry 为负)
- **流动性与滑点**:小品种或主力换月时流动性差,实际成交价远差于预期
- **库存与基差突变**:现货升水突然转贴水,基差反转会瞬间抹去浮盈
- **品种波动差异**:农产品季节性单日 3-5%,能源单日可达 5-10%,金属 2-4%

以下是交易员的决策:
{trader_decision}

积极反驳激进和中性分析师,强调保守策略的稳健性:
- 市场研究(趋势确认 + 突破有效性): {market_research_report}
- 持仓分析报告(拥挤度 + 主力翻空): {sentiment_report}
- 新闻/产业事件(供给过剩 + 需求疲软): {news_report}
- 基本面报告(基差走弱 + 库存累积 + Contango): {fundamentals_report}
- 当前对话历史: {history}
- 激进分析师的最后论点: {current_risky_response}
- 中性分析师的最后论点: {current_neutral_response}

保守策略应包括:严格止损位(单笔不超过 1-2% 账户)、低杠杆(保证金占用 ≤ 20%)、主力合约而非远月、流动性充足的品种。请用中文以对话方式输出。"""


def create_safe_debator(llm):
    def safe_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        safe_history = risk_debate_state.get("safe_history", "")

        current_risky_response = risk_debate_state.get("current_risky_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state.get("position_report") or state.get("sentiment_report", "")
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        trader_decision = state.get("investment_plan", "")

        # === Phase 3b-ii-B:检测 asset_type ===
        asset_type = state.get("asset_type", "stock")

        # 📊 记录输入数据长度
        logger.info(f"📊 [Safe Analyst] 输入数据长度统计:")
        logger.info(f"  - market_report: {len(market_research_report):,} 字符")
        logger.info(f"  - sentiment_report: {len(sentiment_report):,} 字符")
        logger.info(f"  - news_report: {len(news_report):,} 字符")
        logger.info(f"  - fundamentals_report: {len(fundamentals_report):,} 字符")
        logger.info(f"  - trader_decision: {len(trader_decision):,} 字符")
        logger.info(f"  - history: {len(history):,} 字符")
        total_length = (len(market_research_report) + len(sentiment_report) +
                       len(news_report) + len(fundamentals_report) +
                       len(trader_decision) + len(history) +
                       len(current_risky_response) + len(current_neutral_response))
        logger.info(f"  - 总Prompt长度: {total_length:,} 字符 (~{total_length//4:,} tokens)")

        if asset_type == "commodity":
            prompt = COMMODITY_CONSERVATIVE_PROMPT.format(
                trader_decision=trader_decision,
                market_research_report=market_research_report,
                sentiment_report=sentiment_report,
                news_report=news_report,
                fundamentals_report=fundamentals_report,
                history=history,
                current_risky_response=current_risky_response,
                current_neutral_response=current_neutral_response,
            )
        else:
            prompt = f"""作为安全/保守风险分析师，您的主要目标是保护资产、最小化波动性，并确保稳定、可靠的增长。您优先考虑稳定性、安全性和风险缓解，仔细评估潜在损失、经济衰退和市场波动。在评估交易员的决策或计划时，请批判性地审查高风险要素，指出决策可能使公司面临不当风险的地方，以及更谨慎的替代方案如何能够确保长期收益。以下是交易员的决策：

{trader_decision}

您的任务是积极反驳激进和中性分析师的论点，突出他们的观点可能忽视的潜在威胁或未能优先考虑可持续性的地方。直接回应他们的观点，利用以下数据来源为交易员决策的低风险方法调整建立令人信服的案例：

市场研究报告：{market_research_report}
社交媒体情绪报告：{sentiment_report}
最新世界事务报告：{news_report}
公司基本面报告：{fundamentals_report}
以下是当前对话历史：{history} 以下是激进分析师的最后回应：{current_risky_response} 以下是中性分析师的最后回应：{current_neutral_response}。如果其他观点没有回应，请不要虚构，只需提出您的观点。

通过质疑他们的乐观态度并强调他们可能忽视的潜在下行风险来参与讨论。解决他们的每个反驳点，展示为什么保守立场最终是公司资产最安全的道路。专注于辩论和批评他们的论点，证明低风险策略相对于他们方法的优势。请用中文以对话方式输出，就像您在说话一样，不使用任何特殊格式。"""

        logger.info(f"⏱️ [Safe Analyst] 开始调用LLM...")
        llm_start_time = time.time()

        response = llm.invoke(prompt)

        llm_elapsed = time.time() - llm_start_time
        logger.info(f"⏱️ [Safe Analyst] LLM调用完成，耗时: {llm_elapsed:.2f}秒")

        argument = f"Safe Analyst: {response.content}"

        new_count = risk_debate_state["count"] + 1
        logger.info(f"🛡️ [保守风险分析师] 发言完成，计数: {risk_debate_state['count']} -> {new_count}")

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "risky_history": risk_debate_state.get("risky_history", ""),
            "safe_history": safe_history + "\n" + argument,
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Safe",
            "current_risky_response": risk_debate_state.get(
                "current_risky_response", ""
            ),
            "current_safe_response": argument,
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": new_count,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return safe_node
