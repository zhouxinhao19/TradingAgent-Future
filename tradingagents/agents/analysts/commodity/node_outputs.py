"""
node_outputs.py — Commodity Analyst 节点输出版 Pydantic Schema（Phase P0）

设计原则（与 plan 一致）：
  1. 保留 reports.py 现有 AnalystSignal / TechnicalReport / FundamentalReport /
     PositionReport / NewsReport 作为"落库/前端契约"（向后兼容）
  2. 本文件新增 *NodeOutput 作为"LLM 输出硬约束契约"（节点内 Pydantic 校验用）
  3. NodeOutput → Report 的转换函数集中定义，避免字段不一致

与 reports.py 区别：
  - reports.py: extra="allow"（落库宽容）+ Literal direction（兼容现有 state 字段）
  - node_outputs.py: extra="forbid"（校验严格）+ validate_assignment 防止运行期漂移

字段约束策略：
  - 必填字段：direction / confidence / summary（缺一不可）
  - 可选字段：其余所有字段都 Optional 或 default 兜底
  - 数值范围：confidence ∈ [0, 1]，strength ∈ [0, 1]，composite_score ∈ [-1, 1]
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .reports import (
    AnalystSignal,
    FundamentalReport,
    NewsReport,
    PositionReport,
    TechnicalReport,
)


# 公共基类：LLM 输出硬约束
class BaseNodeOutput(BaseModel):
    """所有 NodeOutput 公共基类：extra="forbid" + 严格校验"""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )


class TechnicalNodeOutput(BaseNodeOutput):
    """LLM 输出硬约束 — 技术分析师

    设计意图：技术分析师主要输出 Markdown 报告 + 关键字段。
    Pydantic 校验宽松（多数字段 Optional），重点确保 direction/confidence 不缺失。
    """

    direction: Literal["bullish", "bearish", "neutral"]
    strength: float = Field(0.0, ge=0.0, le=1.0)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    summary: str = Field("", max_length=500)
    signals: List[str] = Field(default_factory=list, max_length=10)
    timeframe: Literal["daily", "daily+weekly", "weekly"] = "daily+weekly"
    volatility_regime: Optional[Literal["low", "medium", "high"]] = None
    atr: Optional[float] = None
    atr_ratio_pctl180: Optional[float] = Field(None, ge=0.0, le=1.0)
    composite_score: Optional[float] = Field(None, ge=-1.0, le=1.0)
    key_levels: Dict[str, float] = Field(default_factory=dict)
    oi_divergence: Optional[str] = None

    def to_report(self) -> TechnicalReport:
        """NodeOutput → TechnicalReport（落库/前端契约）"""
        return TechnicalReport(
            direction=self.direction,
            strength=self.strength,
            confidence=self.confidence,
            summary=self.summary,
            signals=self.signals,
            timeframe=self.timeframe,
            volatility_regime=self.volatility_regime,
            atr=self.atr,
            atr_ratio_pctl180=self.atr_ratio_pctl180,
            composite_score=self.composite_score,
            key_levels=self.key_levels,
            oi_divergence=self.oi_divergence,
        )


class FundamentalNodeOutput(BaseNodeOutput):
    """LLM 输出硬约束 — 产业分析师

    ⚠️ 重要：字段必须匹配 LLM prompt 输出契约（fundamental_analyst.py:129-153），
    不是落库契约（reports.py）。LLM 输出结构：
      {
        "valuation": {level, safety_margin, reasoning},
        "drive": {direction, strength, dominant_factor, reasoning},
        "consistency": {alignment, confidence, analysis, key_uncertainty},
        "summary": "...",
        "risk_flags": [...],
        "data_quality": "..."
      }
    LLM 不输出 direction/confidence（由 features 层推导），所以这俩设为 Optional。
    """

    # 顶层必填（与 prompt 输出格式一致,缺任一视为无效输出）
    valuation: Dict[str, Any]
    drive: Dict[str, Any]
    consistency: Dict[str, Any]
    summary: str
    # 宽容字段（prompt 要求但允许默认）
    risk_flags: List[str] = Field(default_factory=list, max_length=10)
    data_quality: str = Field("", max_length=500)

    # 派生字段（LLM 不输出,节点层从 features/summary 填充,默认 None）
    direction: Optional[Literal["bullish", "bearish", "neutral"]] = None
    strength: Optional[float] = Field(None, ge=0.0, le=1.0)
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    signals: List[str] = Field(default_factory=list, max_length=10)

    def to_report(self) -> FundamentalReport:
        """NodeOutput → FundamentalReport（落库/前端契约）

        注意：reports.py 的 snapshots 字段原本设计承载 features 层数据快照
        （{basis, inventory, term_structure}），与 LLM 推理层输出的
        {valuation, drive, consistency} 不同维度。为避免破坏现有契约且不丢
        LLM 数据，把 LLM 维度塞到 snapshots 的额外 key（llm_* 前缀）。
        """
        snapshots: Dict[str, Dict[str, Any]] = {
            "basis": {},
            "inventory": {},
            "term_structure": {},
            # LLM 推理维度（区别于 features snapshot）
            "llm_valuation": self.valuation,
            "llm_drive": self.drive,
            "llm_consistency": self.consistency,
        }
        return FundamentalReport(
            direction=self.direction or "neutral",
            strength=self.strength or 0.0,
            confidence=self.confidence or 0.0,
            summary=self.summary,
            signals=self.signals,
            basis_view=self.valuation.get("level", ""),
            inventory_view=self.drive.get("direction", ""),
            term_structure_view=self.consistency.get("alignment", ""),
            snapshots=snapshots,
        )


class PositionNodeOutput(BaseNodeOutput):
    """LLM 输出硬约束 — 持仓分析师

    ⚠️ 重要：字段必须匹配 LLM prompt 输出契约（position_analyst.py:159-206），
    不是落库契约（reports.py）。LLM 输出结构：
      {
        "direction": {value, confidence, drivers},
        "market_regime": {regime, price_trend, oi_trend, interpretation},
        "long_side": {trend, change_5d, interpretation},
        "short_side": {trend, change_5d, interpretation},
        "concentration": {level, crowding_status, reversal_risk, analysis},
        "cross_contract": {consistency, analysis},
        "rollover": {detected, analysis},
        "cross_validation": {alignment, volume_confirmation, analysis},
        "summary": "...",
        "risk_flags": [...],
        "data_quality": "..."
      }
    嵌套字段用 Dict[str, Any] 宽松承载（prompt 允许 "null" 字符串等）,顶层结构强约束。
    """

    # 顶层必填
    direction: Dict[str, Any]
    market_regime: Dict[str, Any] = Field(default_factory=dict)
    long_side: Dict[str, Any] = Field(default_factory=dict)
    short_side: Dict[str, Any] = Field(default_factory=dict)
    concentration: Dict[str, Any] = Field(default_factory=dict)
    cross_contract: Dict[str, Any] = Field(default_factory=dict)
    rollover: Dict[str, Any] = Field(default_factory=dict)
    cross_validation: Dict[str, Any] = Field(default_factory=dict)
    summary: str = Field("", max_length=500)
    risk_flags: List[str] = Field(default_factory=list, max_length=10)
    data_quality: str = Field("", max_length=500)

    # 派生字段（节点层从 direction dict 提取,默认 None）
    direction_value: Optional[Literal["long", "short", "neutral"]] = None

    def to_report(self) -> PositionReport:
        """NodeOutput → PositionReport（落库/前端契约）

        从 LLM 的 dict 结构映射到 reports.py 扁平结构。
        """
        direction_map = {"long": "bullish", "short": "bearish", "neutral": "neutral"}
        dir_value = self.direction_value or (self.direction or {}).get("value")
        direction = direction_map.get(dir_value, "neutral")
        confidence = (self.direction or {}).get("confidence")
        if isinstance(confidence, str):
            try:
                confidence = float(confidence)
            except (TypeError, ValueError):
                confidence = None

        # 多空双边映射（LLM long_side/short_side → reports 扁平字段）
        long_side = self.long_side or {}
        short_side = self.short_side or {}
        concentration = self.concentration or {}
        cross = self.cross_validation or {}
        regime = self.market_regime or {}

        return PositionReport(
            direction=direction,
            strength=0.0,
            confidence=float(confidence) if isinstance(confidence, (int, float)) else 0.0,
            summary=self.summary,
            signals=self.risk_flags,
            long_change_5d=_safe_float(long_side.get("change_5d")),
            short_change_5d=_safe_float(short_side.get("change_5d")),
            long_short_ratio=None,
            long_short_ratio_change_5d=None,
            long_side_trend=long_side.get("trend"),
            short_side_trend=short_side.get("trend"),
            consecutive_net_long_days=None,
            slope_20d=None,
            concentration=None,
            crowding_pctl_180d=None,
            crowding_status=concentration.get("crowding_status"),
            reversal_risk=bool(concentration.get("reversal_risk", False)),
            price_direction=regime.get("price_trend"),
            price_position_alignment=cross.get("alignment"),
        )


def _safe_float(value: Any) -> Optional[float]:
    """把 LLM 输出的数值或 "null" 字符串转 float,失败返回 None。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped in ("null", "", "None", "N/A"):
            return None
        try:
            return float(stripped)
        except (TypeError, ValueError):
            return None
    return None


class NewsNodeOutput(BaseNodeOutput):
    """LLM 输出硬约束 — 新闻分析师

    设计意图：news_analyst 输出主要是 Markdown 报告（macro_narrative + industry_narrative）。
    Pydantic 校验非常宽松：direction 可由 sentiment_ratio 推导，confidence 由 LLM 给定。
    """

    direction: Literal["bullish", "bearish", "neutral"] = "neutral"
    strength: float = Field(0.0, ge=0.0, le=1.0)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    summary: str = Field("", max_length=500)
    signals: List[str] = Field(default_factory=list, max_length=10)

    sentiment_ratio: Optional[float] = Field(None, ge=-1.0, le=1.0)
    positive_count: int = Field(0, ge=0)
    negative_count: int = Field(0, ge=0)
    neutral_count: int = Field(0, ge=0)
    macro_narrative: Optional[str] = Field(None, max_length=2000)
    industry_narrative: Optional[str] = Field(None, max_length=2000)
    key_events: List[str] = Field(default_factory=list, max_length=20)

    def to_report(self) -> NewsReport:
        """NodeOutput → NewsReport（落库/前端契约）"""
        return NewsReport(
            direction=self.direction,
            strength=self.strength,
            confidence=self.confidence,
            summary=self.summary,
            signals=self.signals,
            sentiment_ratio=self.sentiment_ratio,
            positive_count=self.positive_count,
            negative_count=self.negative_count,
            neutral_count=self.neutral_count,
            macro_narrative=self.macro_narrative,
            industry_narrative=self.industry_narrative,
            key_events=self.key_events,
        )


__all__ = [
    "FundamentalNodeOutput",
    "NewsNodeOutput",
    "PositionNodeOutput",
    "TechnicalNodeOutput",
]