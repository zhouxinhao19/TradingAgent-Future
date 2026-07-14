"""
tradingagents/agents/analysts/commodity/__init__.py

Phase 3b-ii:商品期货分析师节点(技术/基本面/持仓/新闻)

当前交付(2026-07-14):
  - reports.py:4 个 Report Pydantic 模型
  - _base.py:共享工具(load_features / empty_report / quality_gate)
  - technical_analyst.py:技术分析师节点(完整实现 + LLM 失败降级)

后续 3b-ii-A 扩展:
  - fundamental_analyst.py:基本面(基差+库存+期限结构)
  - position_analyst.py:持仓(前 20 名 + 集中度 + 拥挤度)
  - news_analyst.py:新闻(必调 LLM)
"""
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
    "AnalystSignal",
    "TechnicalReport",
    "FundamentalReport",
    "PositionReport",
    "NewsReport",
]