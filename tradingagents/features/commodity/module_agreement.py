"""
module_agreement.py — Feature 7: 模块方向投票（纯规则，零 LLM）

从 6 个 features 模块的 direction/consensus 字段聚合方向投票，
供 RM prompt 直接引用（省去逐份报告数方向的人力）。
"""
from __future__ import annotations

from typing import Any, Dict, List


def _extract_direction(module: Dict[str, Any], key: str = "direction") -> str:
    """从模块输出中提取方向。"""
    if not isinstance(module, dict):
        return "neutral"
    # 先找 snapshot 层
    snap = module.get("snapshot", {}) or {}
    if isinstance(snap, dict):
        d = snap.get(key)
        if d and isinstance(d, str) and d != "?":  # noqa: S105
            return _normalize(d)
    # 再找 latest
    latest = module.get("latest", {}) or {}
    if isinstance(latest, dict):
        d = latest.get(key)
        if d and isinstance(d, str) and d != "?":
            return _normalize(d)
    return "neutral"


def _normalize(d: str) -> str:
    text = str(d).strip().lower()
    if text in ("bullish", "long", "看多", "做多", "向上", "偏多"):
        return "bullish"
    if text in ("bearish", "short", "看空", "做空", "向下", "偏空"):
        return "bearish"
    return "neutral"


def compute_module_agreement(
    features: Dict[str, Any],
) -> Dict[str, Any]:
    """计算 6 模块方向投票聚合。

    Args:
        features: features 层 6 模块输出字典

    Returns:
        dict: {
            "votes": {模块名: 方向},
            "tally": {方向: 计数},
            "agreement_score": 多数方向占比(0~1),
            "consensus": "bullish|bearish|neutral|split",
            "conviction": "strong|moderate|weak",
            "dissenting": [偏离共识的模块列表]
        }
    """
    module_keys = [
        "technical", "basis", "inventory", "positioning",
        "term_structure", "news_sentiment",
    ]
    votes: Dict[str, str] = {}
    for key in module_keys:
        module = features.get(key, {}) or {}
        if not isinstance(module, dict):
            votes[key] = "neutral"
            continue
        d = _extract_direction(module)
        votes[key] = d

    tally: Dict[str, int] = {"bullish": 0, "bearish": 0, "neutral": 0}
    for d in votes.values():
        if d in tally:
            tally[d] += 1

    # 最高票方向
    sorted_tally = sorted(tally.items(), key=lambda x: -x[1])
    top_dir = sorted_tally[0][0] if sorted_tally else "neutral"
    top_count = sorted_tally[0][1] if sorted_tally else 0
    total_active = sum(tally.values())
    agreement_score = round(top_count / total_active, 2) if total_active > 0 else 0.0

    # consensus
    if top_count >= 5:
        consensus = top_dir
        conviction = "strong"
    elif top_count >= 4:
        consensus = top_dir
        conviction = "moderate"
    elif top_count >= 3:
        consensus = top_dir
        conviction = "weak"
    elif top_count == 2 and tally.get("neutral", 0) >= 3:
        consensus = "neutral"
        conviction = "weak"
    else:
        consensus = "split"
        conviction = "weak"

    # 偏离共识的模块
    dissenting: List[Dict[str, str]] = []
    for mod, d in votes.items():
        if d != consensus and d != "neutral":
            reason = _dissenting_reason(mod, features.get(mod, {}))
            dissenting.append({"module": mod, "direction": d, "reason": reason})

    return {
        "votes": votes,
        "tally": tally,
        "agreement_score": agreement_score,
        "consensus": consensus,
        "conviction": conviction,
        "dissenting": dissenting,
    }


def _dissenting_reason(module: str, feat: Dict[str, Any]) -> str:
    """给出偏离共识的简单理由。"""
    if not isinstance(feat, dict):
        return ""
    snap = feat.get("snapshot", {}) or {}
    if not isinstance(snap, dict):
        return ""
    if module == "positioning":
        c = snap.get("crowding_pctl_180d")
        if c is not None:
            return f"拥挤度{float(c):.0f}%分位"
    elif module == "technical":
        s = snap.get("composite_score")
        if s is not None:
            return f"综合评分{s}"
    elif module == "basis":
        r = snap.get("dom_basis_rate")
        if r is not None:
            return f"基差率{r}"
    elif module == "inventory":
        w = snap.get("wow_change")
        if w is not None:
            return f"库存周环比{w}"
    return ""
