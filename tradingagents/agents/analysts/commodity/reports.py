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
    """持仓分析师输出(增强版:多空双边+趋势+价格交叉验证)."""

    # 多空双边
    long_change_5d: Optional[float] = Field(None, description="前 20 名多头 5 日变化")
    short_change_5d: Optional[float] = Field(None, description="前 20 名空头 5 日变化")
    net_long_change_5d: Optional[float] = Field(None, description="前 20 名净多头 5 日变化")
    long_short_ratio: Optional[float] = Field(None, description="多空比(long_top20/short_top20)")
    long_short_ratio_change_5d: Optional[float] = Field(None, description="多空比 5 日变化")
    long_side_trend: Optional[str] = Field(None, description="多头趋势:加仓/减仓/平稳")
    short_side_trend: Optional[str] = Field(None, description="空头趋势:加仓/减仓/平稳")

    # 趋势
    consecutive_net_long_days: Optional[int] = Field(None, description="连续净多变化天数(正=增加,负=减少)")
    slope_20d: Optional[float] = Field(None, description="20d 净多斜率")

    # 集中度/拥挤度
    concentration: Optional[float] = Field(None, ge=0.0, le=1.0, description="前 20 集中度")
    crowding_pctl_180d: Optional[float] = Field(None, ge=0.0, le=1.0, description="拥挤度 180d 分位")
    crowding_status: Optional[str] = Field(None, description="拥挤度:拥挤/正常/冷清")
    reversal_risk: bool = Field(False, description="是否触发拥挤反转风险")

    # 价格交叉
    price_direction: Optional[str] = Field(None, description="日线价格方向:bullish/bearish/neutral")
    price_position_alignment: Optional[str] = Field(None, description="价格-持仓对齐:同向/背离/待定")

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