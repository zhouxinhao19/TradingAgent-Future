from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# 导入日志模块
from tradingagents.utils.logging_manager import get_logger
logger = get_logger('default')


# Create a custom config
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "google"  # Use a different model
config["backend_url"] = "https://generativelanguage.googleapis.com/v1beta"  # Use a different backend
config["deep_think_llm"] = "gemini-2.0-flash"  # Use a different model
config["quick_think_llm"] = "gemini-2.0-flash"  # Use a different model
config["max_debate_rounds"] = 1  # Increase debate rounds
config["online_tools"] = True  # Increase debate rounds

# Initialize with custom config
ta = TradingAgentsGraph(debug=True, config=config)

# forward propagate — 大宗商品期货示例（注意：请替换为实际品种代码）
# _, decision = ta.propagate("CU2608.SHF", "2026-07-24")
# print(decision)

print("TradingAgent-Future 大宗商品期货多智能体分析平台已就绪。")
print("使用方法: ta.propagate(\"CU2608.SHF\", \"2026-07-24\")")

# Memorize mistakes and reflect
# ta.reflect_and_remember(1000) # parameter is the position returns
