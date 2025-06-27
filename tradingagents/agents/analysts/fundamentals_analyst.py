from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json


def create_fundamentals_analyst(llm, toolkit):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        company_name = state["company_of_interest"]

        if toolkit.config["online_tools"]:
            tools = [toolkit.get_fundamentals_openai]
        else:
            tools = [
                toolkit.get_finnhub_company_insider_sentiment,
                toolkit.get_finnhub_company_insider_transactions,
                toolkit.get_simfin_balance_sheet,
                toolkit.get_simfin_cashflow,
                toolkit.get_simfin_income_stmt,
            ]

        system_message = (
            "你是一位研究员，负责分析公司过去一周的基本面信息。请撰写一份关于公司基本面信息的综合报告，包括财务文件、公司概况、基本公司财务、公司财务历史、内部人情绪和内部人交易，以全面了解公司的基本面信息来为交易者提供信息。确保包含尽可能多的细节。不要简单地说趋势是混合的，提供详细和细粒度的分析和见解，可能帮助交易者做出决策。"
            + "确保在报告末尾附加一个Markdown表格来组织报告中的要点，使其有组织且易于阅读。请确保所有分析都使用中文。",
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是一位有用的AI助手，与其他助手协作。"
                    "使用提供的工具来回答问题。"
                    "如果你无法完全回答，没关系；另一位具有不同工具的助手"
                    "将从你停下的地方继续帮助。执行你能做的来取得进展。"
                    "如果你或任何其他助手有最终交易建议：**买入/持有/卖出**或可交付成果，"
                    "请在你的回复前加上'最终交易建议：**买入/持有/卖出**'，这样团队就知道要停止了。"
                    "你可以使用以下工具：{tool_names}。\n{system_message}"
                    "供你参考，当前日期是{current_date}。我们要分析的公司是{ticker}。请确保所有分析都使用中文。",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(ticker=ticker)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "fundamentals_report": report,
        }

    return fundamentals_analyst_node
