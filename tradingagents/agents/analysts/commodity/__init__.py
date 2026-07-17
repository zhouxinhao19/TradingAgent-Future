"""
tradingagents/agents/analysts/commodity/__init__.py

Phase 3b-ii:商品期货分析师节点(技术/产业/持仓/新闻)

当前交付(2026-07-16):
  - reports.py:4 个 Report Pydantic 模型(PositionReport 含多空双边/趋势/价格交叉验证)
  - _base.py:共享工具(load_features / empty_report / quality_gate)
  - technical_analyst.py:技术分析师(完整 + LLM 降级)
  - fundamental_analyst.py:产业分析师(三因子矩阵 + LLM 降级)
  - position_analyst.py:持仓分析师(多空双边+集中度/拥挤度+价格交叉验证 + LLM 降级,结构化 JSON)
  - news_analyst.py:新闻分析师(必调 LLM,无 LLM 时仅返回情感统计)

输出字段映射:
  - create_technical_analyst  → state['market_report']
  - create_fundamental_analyst → state['fundamentals_report']
  - create_position_analyst   → state['sentiment_report'](旧)/state['position_report']+state['position_structured'](新)
  - create_news_analyst       → state['news_report']
"""
from ._base import (
    ANALYST_PREFIXES,
    extract_first_sentence,
    inject_analyst_id,
    make_analyst_id,
)
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
    "make_analyst_id",
    "inject_analyst_id",
    "extract_first_sentence",
    "ANALYST_PREFIXES",
    "AnalystSignal",
    "TechnicalReport",
    "FundamentalReport",
    "PositionReport",
    "NewsReport",
]