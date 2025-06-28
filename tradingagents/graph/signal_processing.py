# TradingAgents/graph/signal_processing.py

from langchain_openai import ChatOpenAI


class SignalProcessor:
    """Processes trading signals to extract actionable decisions."""

    def __init__(self, quick_thinking_llm: ChatOpenAI):
        """Initialize with an LLM for processing."""
        self.quick_thinking_llm = quick_thinking_llm

    def process_signal(self, full_signal: str) -> dict:
        """
        Process a full trading signal to extract structured decision information.

        Args:
            full_signal: Complete trading signal text

        Returns:
            Dictionary containing extracted decision information
        """
        messages = [
            (
                "system",
                """您是一位专业的金融分析助手，负责从交易员的分析报告中提取结构化的投资决策信息。

请从提供的分析报告中提取以下信息，并以JSON格式返回：

{
    "action": "买入/持有/卖出",
    "target_price": 数字(美元价格，如果没有明确提及则为null),
    "confidence": 数字(0-1之间，如果没有明确提及则为0.7),
    "risk_score": 数字(0-1之间，如果没有明确提及则为0.5),
    "reasoning": "决策的主要理由摘要"
}

请确保：
1. action字段必须是"买入"、"持有"或"卖出"之一
2. target_price应该是合理的美元价格数字
3. confidence和risk_score应该在0-1之间
4. reasoning应该是简洁的中文摘要

如果某些信息在报告中没有明确提及，请使用合理的默认值。""",
            ),
            ("human", full_signal),
        ]

        try:
            response = self.quick_thinking_llm.invoke(messages).content

            # 尝试解析JSON响应
            import json
            import re

            # 提取JSON部分
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                decision_data = json.loads(json_match.group())

                # 验证和标准化数据
                action = decision_data.get('action', '持有')
                if action not in ['买入', '持有', '卖出']:
                    # 尝试映射英文
                    action_map = {'buy': '买入', 'hold': '持有', 'sell': '卖出', 'BUY': '买入', 'HOLD': '持有', 'SELL': '卖出'}
                    action = action_map.get(action, '持有')

                return {
                    'action': action,
                    'target_price': decision_data.get('target_price'),
                    'confidence': float(decision_data.get('confidence', 0.7)),
                    'risk_score': float(decision_data.get('risk_score', 0.5)),
                    'reasoning': decision_data.get('reasoning', '基于综合分析的投资建议')
                }
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
        price_match = re.search(r'目标价[位格]?[：:]?\s*\$?(\d+(?:\.\d+)?)', text)
        if price_match:
            target_price = float(price_match.group(1))

        return {
            'action': action,
            'target_price': target_price,
            'confidence': 0.7,
            'risk_score': 0.5,
            'reasoning': '基于综合分析的投资建议'
        }
