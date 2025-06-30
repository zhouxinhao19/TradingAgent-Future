# TradingAgents/graph/signal_processing.py

from langchain_openai import ChatOpenAI


class SignalProcessor:
    """Processes trading signals to extract actionable decisions."""

    def __init__(self, quick_thinking_llm: ChatOpenAI):
        """Initialize with an LLM for processing."""
        self.quick_thinking_llm = quick_thinking_llm

    def process_signal(self, full_signal: str, stock_symbol: str = None) -> dict:
        """
        Process a full trading signal to extract structured decision information.

        Args:
            full_signal: Complete trading signal text
            stock_symbol: Stock symbol to determine currency type

        Returns:
            Dictionary containing extracted decision information
        """

        # 检测股票类型和货币
        def is_china_stock(ticker_code):
            import re
            return re.match(r'^\d{6}$', str(ticker_code)) if ticker_code else False

        is_china = is_china_stock(stock_symbol)
        currency = "人民币" if is_china else "美元"
        currency_symbol = "¥" if is_china else "$"

        print(f"🔍 [SignalProcessor] 处理信号: 股票={stock_symbol}, 中国A股={is_china}, 货币={currency}")

        messages = [
            (
                "system",
                f"""您是一位专业的金融分析助手，负责从交易员的分析报告中提取结构化的投资决策信息。

请从提供的分析报告中提取以下信息，并以JSON格式返回：

{{
    "action": "买入/持有/卖出",
    "target_price": 数字({currency}价格，如果没有明确提及则为null),
    "confidence": 数字(0-1之间，如果没有明确提及则为0.7),
    "risk_score": 数字(0-1之间，如果没有明确提及则为0.5),
    "reasoning": "决策的主要理由摘要"
}}

请确保：
1. action字段必须是"买入"、"持有"或"卖出"之一
2. target_price应该是合理的{currency}价格数字（使用{currency_symbol}符号）
3. confidence和risk_score应该在0-1之间
4. reasoning应该是简洁的中文摘要

特别注意：
- 股票代码 {stock_symbol or '未知'} {'是中国A股，使用人民币计价' if is_china else '是美股/港股，使用美元计价'}
- 目标价格必须与股票的交易货币一致

如果某些信息在报告中没有明确提及，请使用合理的默认值。""",
            ),
            ("human", full_signal),
        ]

        try:
            response = self.quick_thinking_llm.invoke(messages).content
            print(f"🔍 [SignalProcessor] LLM响应: {response[:200]}...")

            # 尝试解析JSON响应
            import json
            import re

            # 提取JSON部分
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_text = json_match.group()
                print(f"🔍 [SignalProcessor] 提取的JSON: {json_text}")
                decision_data = json.loads(json_text)

                # 验证和标准化数据
                action = decision_data.get('action', '持有')
                if action not in ['买入', '持有', '卖出']:
                    # 尝试映射英文
                    action_map = {'buy': '买入', 'hold': '持有', 'sell': '卖出', 'BUY': '买入', 'HOLD': '持有', 'SELL': '卖出'}
                    action = action_map.get(action, '持有')

                # 处理目标价格，确保正确提取
                target_price = decision_data.get('target_price')
                if target_price is None or target_price == "null":
                    # 如果JSON中没有目标价格，尝试从reasoning中提取
                    reasoning = decision_data.get('reasoning', '')
                    price_patterns = [
                        r'目标价[位格]?[：:]?\s*\$?(\d+(?:\.\d+)?)',
                        r'目标价[位格]?[：:]?\s*¥?(\d+(?:\.\d+)?)',
                        r'\$(\d+(?:\.\d+)?)',
                        r'¥(\d+(?:\.\d+)?)',
                    ]
                    for pattern in price_patterns:
                        price_match = re.search(pattern, reasoning)
                        if price_match:
                            target_price = float(price_match.group(1))
                            break

                result = {
                    'action': action,
                    'target_price': target_price,
                    'confidence': float(decision_data.get('confidence', 0.7)),
                    'risk_score': float(decision_data.get('risk_score', 0.5)),
                    'reasoning': decision_data.get('reasoning', '基于综合分析的投资建议')
                }
                print(f"🔍 [SignalProcessor] 处理结果: {result}")
                return result
            else:
                # 如果无法解析JSON，使用简单的文本提取
                return self._extract_simple_decision(response)

        except Exception as e:
            print(f"信号处理错误: {e}")
            # 回退到简单提取
            return self._extract_simple_decision(full_signal)

    def _extract_simple_decision(self, text: str) -> dict:
        """简单的决策提取方法作为备用"""
        import re

        # 提取动作
        action = '持有'  # 默认
        if re.search(r'买入|BUY', text, re.IGNORECASE):
            action = '买入'
        elif re.search(r'卖出|SELL', text, re.IGNORECASE):
            action = '卖出'
        elif re.search(r'持有|HOLD', text, re.IGNORECASE):
            action = '持有'

        # 尝试提取目标价格
        target_price = None
        # 尝试多种格式的目标价格匹配
        price_patterns = [
            r'目标价[位格]?[：:]?\s*\$?(\d+(?:\.\d+)?)',  # 目标价位: $190
            r'目标价[位格]?[：:]?\s*¥?(\d+(?:\.\d+)?)',   # 目标价位: ¥45.50
            r'\*\*目标价[位格]?\*\*[：:]?\s*\$?(\d+(?:\.\d+)?)',  # **目标价位**: $190
            r'目标价[位格]?\s*\$?(\d+(?:\.\d+)?)',       # 目标价位 $190
        ]

        for pattern in price_patterns:
            price_match = re.search(pattern, text)
            if price_match:
                target_price = float(price_match.group(1))
                break

        return {
            'action': action,
            'target_price': target_price,
            'confidence': 0.7,
            'risk_score': 0.5,
            'reasoning': '基于综合分析的投资建议'
        }
