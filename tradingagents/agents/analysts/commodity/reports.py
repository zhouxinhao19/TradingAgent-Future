"""
reports.py — 商品期货分析师 Pydantic Report 模型 (Phase 3b-ii)

设计原则:
  - 每个 Report 同时是 AgentState 字段值(dict 落进 state)与 Pydantic schema(便于校验/前端展示)
  - LLM 通过 prompt 生成 Markdown 后,Markdown 字符串直接落到 state["xxx_report"]
  - Pydantic 模型仅在落 MongoDB 与前端展示前做二次校验,不在节点内强制
  - direction 严格限制为 Literal,避免下游分类枚举失配
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# 公共基类:所有 analyst report 共有的字段
class AnalystSignal(BaseModel):
    """所有 analyst report 的公共基类。"""

    model_config = ConfigDict(extra="allow", validate_assignment=True)

    direction: Literal["bullish", "bearish", "neutral"]
    strength: float = Field(0.0, ge=0.0, le=1.0, description="0-1,信号强度")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="0-1,置信度")
    summary: str = Field("", description="一句话总结(英文或中文均可)")
    signals: List[str] = Field(default_factory=list, description="触发的 rule-based 信号文字")


class TechnicalReport(AnalystSignal):
    """技术分析师输出。"""

    timeframe: str = Field("daily+weekly", description="分析的时间框架")
    snapshot: Dict[str, Any] = Field(default_factory=dict, description="features.technical.daily.snapshot")
    oi_divergence: Optional[str] = Field(None, description="持仓量背离方向:confirm/conflict/neutral/OI↑价↓看空背离等")
    volatility_regime: Optional[str] = Field(None, description="low/medium/high")
    atr: Optional[float] = Field(None, description="ATR 数值")
    atr_ratio_pctl180: Optional[float] = Field(None, ge=0.0, le=1.0, description="ATR/价格 比率的 180d 分位")
    composite_score: Optional[float] = Field(None, ge=-1.0, le=1.0, description="综合评分 -1~+1")
    key_levels: Dict[str, float] = Field(default_factory=dict, description="支撑/阻力位")


class FundamentalReport(AnalystSignal):
    """基本面分析师输出(基差+库存+期限结构三因子)。"""

    basis_view: str = Field("", description="基差解读,如'贴水/升水/Contango/Backwardation/Flat'")
    inventory_view: str = Field("", description="库存解读,如'累库/去库/平稳'")
    term_structure_view: str = Field("", description="期限结构解读")
    snapshots: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="{basis: features.basis.snapshot, inventory: features.inventory.snapshot, term_structure: features.term_structure.snapshot}",
    )


class PositionReport(AnalystSignal):
    """持仓分析师输出。"""

    net_long_change_5d: Optional[float] = Field(None, description="前 20 名净多头 5 日变化")
    crowding_pctl_180d: Optional[float] = Field(None, ge=0.0, le=1.0, description="拥挤度 180d 分位")
    concentration: Optional[float] = Field(None, ge=0.0, le=1.0, description="前 5 名持仓占比")
    snapshot: Dict[str, Any] = Field(default_factory=dict)


class NewsReport(AnalystSignal):
    """新闻分析师输出(LLM 必调,生成宏观叙事 + 产业叙事)。"""

    sentiment_ratio: Optional[float] = Field(None, ge=-1.0, le=1.0, description="情感比:positive/(positive+negative)")
    positive_count: int = Field(0, ge=0)
    negative_count: int = Field(0, ge=0)
    neutral_count: int = Field(0, ge=0)
    macro_narrative: Optional[str] = Field(None, description="全球宏观叙事摘要(LLM 输出)")
    industry_narrative: Optional[str] = Field(None, description="产业叙事摘要(LLM 输出)")
    key_events: List[str] = Field(default_factory=list, description="重要事件卡片")
    snapshot: Dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "AnalystSignal",
    "TechnicalReport",
    "FundamentalReport",
    "PositionReport",
    "NewsReport",
]