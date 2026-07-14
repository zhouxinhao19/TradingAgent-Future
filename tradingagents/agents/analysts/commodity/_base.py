"""
_base.py — Commodity analyst 公共逻辑 (Phase 3b-ii)

提供 4 个 commodity analyst 节点共享的工具:
  - load_features:从 state['commodity_features'] 读取 3b-i features 层输出
  - empty_report:features 缺失/数据不足时返回中性 Markdown 报告
  - truncate_snapshot:截断 snapshot 到 top-N 字段,降 LLM prompt 长度
  - quality_gate:根据 quality.rows 判断是否走空结果分支
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from tradingagents.utils.logging_init import get_logger

logger = get_logger("default")

# 数据稀疏阈值:日线 K 线 < 30 根视为不可信
MIN_ROWS_THRESHOLD = 30

# snapshot 截断上限:防止 LLM prompt 过长
SNAPSHOT_MAX_KEYS = 30


def load_features(state: dict) -> Dict[str, Any]:
    """从 state['commodity_features'] 读取 3b-i features 层结构化输出。

    Propagator 在初始 state 中预置该字段为空 dict;
    各 analyst 节点按需读取(假定 features 层已在更早节点一次性算好塞入)。

    Returns:
        dict,形如 {"technical": {...}, "basis": {...}, "inventory": {...}, ...}
        空时返回 {}
    """
    return state.get("commodity_features") or {}


def empty_report(direction: str = "neutral", reason: str = "") -> str:
    """降级返回:features 缺失或质量不足时返回简短 Markdown 报告。

    Args:
        direction: bullish/bearish/neutral,默认中性
        reason: 数据缺失的具体原因,会写进报告

    Returns:
        Markdown 字符串,适合直接落到 state['xxx_report']
    """
    if not reason:
        reason = "特征层数据为空"
    direction_cn = {"bullish": "看多", "bearish": "看空", "neutral": "中性"}.get(direction, direction)
    return (
        f"**{direction_cn} | 数据缺失**\n\n"
        f"{reason},跳过本分析师。\n\n"
        f"建议结合其他分析师(基本面/持仓/新闻)综合判断。\n"
    )


def truncate_snapshot(snap: Optional[Dict[str, Any]], max_keys: int = SNAPSHOT_MAX_KEYS) -> Dict[str, Any]:
    """截断 snapshot 到 top-N 字段,降低 LLM prompt 长度。

    - 非 dict 输入返回空 dict
    - 字段数 <= max_keys 原样返回
    - 字段数 > max_keys 只保留前 max_keys 项(假定 features 层已按重要性排序)
    """
    if not isinstance(snap, dict):
        return {}
    if len(snap) <= max_keys:
        return snap
    return dict(list(snap.items())[:max_keys])


def quality_gate(features_block: Optional[Dict[str, Any]], min_rows: int = MIN_ROWS_THRESHOLD) -> bool:
    """根据 quality.rows 判断是否走空结果分支。

    Args:
        features_block: features 层单个模块的输出(如 features['technical']),
                        可能为 None 或缺 quality 字段
        min_rows: 最低有效数据条数阈值

    Returns:
        True 表示数据可信,可继续走 LLM/降级报告;
        False 表示数据不足,应走 empty_report
    """
    if not isinstance(features_block, dict):
        return False
    quality = features_block.get("quality") or {}
    rows = quality.get("rows", 0)
    try:
        rows = int(rows)
    except (TypeError, ValueError):
        rows = 0
    return rows >= min_rows


def get_full_symbol(state: dict) -> str:
    """从 state 提取 full_symbol,兼容多种字段名。"""
    return (
        state.get("full_symbol")
        or state.get("company_of_interest")
        or ""
    )


__all__ = [
    "load_features",
    "empty_report",
    "truncate_snapshot",
    "quality_gate",
    "get_full_symbol",
    "MIN_ROWS_THRESHOLD",
    "SNAPSHOT_MAX_KEYS",
]