"""
tradingagents/agents/analysts/commodity/__init__.py

Phase 3b-ii:商品期货分析师节点(技术/基本面/持仓/新闻)

当前交付(2026-07-14):
  - reports.py:4 个 Report Pydantic 模型
  - _base.py:共享工具(load_features / empty_report / quality_gate)
  - technical_analyst.py:技术分析师(完整 + LLM 降级)
  - fundamental_analyst.py:基本面分析师(三因子矩阵 + LLM 降级)
  - position_analyst.py:持仓分析师(集中度/拥挤度 + LLM 降级)
  - news_analyst.py:新闻分析师(必调 LLM,无 LLM 时仅返回情感统计)

输出字段映射(复用 stock AgentState 字段名,决策链节点零改动):
  - create_technical_analyst  → state['market_report']
  - create_fundamental_analyst → state['fundamentals_report']
  - create_position_analyst   → state['sentiment_report']
  - create_news_analyst       → state['news_report']
"""
from .fundamental_analyst import create_fundamental_analyst
from .news_analyst import create_news_analyst
from .position_analyst import create_position_analyst
from .reports import (
    AnalystSignal,
    FundamentalReport,
    NewsReport,
    PositionReport,
    TechnicalReport,
)
from .technical_analyst import create_technical_analyst

__all__ = [
    "create_technical_analyst",
    "create_fundamental_analyst",
    "create_position_analyst",
    "create_news_analyst",
    "AnalystSignal",
    "TechnicalReport",
    "FundamentalReport",
    "PositionReport",
    "NewsReport",
]