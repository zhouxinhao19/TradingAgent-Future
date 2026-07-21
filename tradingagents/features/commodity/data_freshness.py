"""
data_freshness.py — Feature 9: 数据新鲜度校准（纯规则，零 LLM）

聚合 6 模块的 quality 字段，输出数据新鲜度评估和置信度修正建议，
供 RM prompt（下调滞后数据权重）和 ID prompt（风险卡数据质量部分）引用。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional


def _quality(module: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(module, dict):
        return {"rows": 0, "coverage": 0.0, "data_freshness_days": None}
    q = module.get("quality", {}) or {}
    return q if isinstance(q, dict) else {}


def _freshness_label(days: Optional[int]) -> str:
    if days is None:
        return "unknown"
    if days <= 1:
        return "fresh"
    if days <= 3:
        return "acceptable"
    if days <= 7:
        return "degraded"
    return "stale"


def compute_data_freshness(
    features: Dict[str, Any],
) -> Dict[str, Any]:
    """聚合 6 模块数据新鲜度，输出校准提示。

    Args:
        features: features 层 6 模块输出字典

    Returns:
        dict: {
            "overall": "fresh|acceptable|degraded|stale|unknown",
            "stalest_module": str,
            "stalest_days": int|None,
            "per_module": {
                "technical": {"freshness_days": int, "quality": str, "reason": str}, ...
            },
            "calibration_hints": [
                {"module": str, "signal_weight": "normal|downweight", "reason": str}
            ],
            "confidence_modifier": float (0~1 全局折扣因子)
        }
    """
    module_keys = [
        "technical", "basis", "inventory", "positioning",
        "term_structure", "news_sentiment",
    ]

    per_module: Dict[str, Dict[str, Any]] = {}
    for key in module_keys:
        module = features.get(key, {}) or {}
        if not isinstance(module, dict):
            per_module[key] = {
                "freshness_days": None,
                "quality": "unknown",
                "reason": "模块数据不可用",
            }
            continue
        q = _quality(module)
        days = q.get("data_freshness_days")
        if isinstance(days, (int, float)):
            days = int(days)
        else:
            days = None
        quality_label = _freshness_label(days)
        reason = _freshness_reason(key, days, q)
        per_module[key] = {
            "freshness_days": days,
            "quality": quality_label,
            "reason": reason,
        }

    # 寻找最滞后模块
    stalest_module: Optional[str] = None
    stalest_days: Optional[int] = None
    for key, info in per_module.items():
        d = info.get("freshness_days")
        if d is not None and (stalest_days is None or d > stalest_days):
            stalest_days = d
            stalest_module = key

    # 整体评级
    if stalest_days is None:
        overall = "unknown"
    elif stalest_days <= 1:
        overall = "fresh"
    elif stalest_days <= 3:
        overall = "acceptable"
    elif stalest_days <= 7:
        overall = "degraded"
    else:
        overall = "stale"

    # 校准提示：仅对 degraded/stale 模块建议下调权重
    calibration_hints: List[Dict[str, str]] = []
    for key, info in per_module.items():
        if info.get("quality") in ("degraded", "stale"):
            calibration_hints.append({
                "module": key,
                "signal_weight": "downweight",
                "reason": info["reason"],
            })

    # 全局置信度修正因子
    degraded_count = sum(
        1 for info in per_module.values() if info.get("quality") in ("degraded", "stale")
    )
    if degraded_count >= 3:
        confidence_modifier = 0.8
    elif degraded_count >= 1:
        confidence_modifier = 0.9
    else:
        confidence_modifier = 1.0

    return {
        "overall": overall,
        "stalest_module": stalest_module or "",
        "stalest_days": stalest_days,
        "per_module": per_module,
        "calibration_hints": calibration_hints,
        "confidence_modifier": confidence_modifier,
    }


def _freshness_reason(module: str, days: Optional[int], quality: Dict[str, Any]) -> str:
    if days is None:
        return "数据新鲜度未知"
    if days > 7:
        return f"数据滞后{days}天，当前价格可能已反映更新的{days_display(module)}状况"
    if days > 3:
        return f"数据滞后{days}天，参考价值下降"
    if days > 1:
        return f"数据为{days}天前"
    return "数据较新"


def days_display(module: str) -> str:
    mapping = {
        "inventory": "库存",
        "basis": "基差",
        "positioning": "持仓",
        "technical": "技术面",
        "term_structure": "期限结构",
        "news_sentiment": "新闻",
    }
    return mapping.get(module, module)
