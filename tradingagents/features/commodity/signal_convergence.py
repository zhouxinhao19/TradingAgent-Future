"""
signal_convergence.py — Feature 8: 信号共振/背离检测（纯规则，零 LLM）

从 6 模块 signals + snapshot 中匹配预定义的期货信号模式，
产出共振和背离条目供 Bull/Bear prompt 和 RM prompt 直接引用。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


# 已知信号模式定义
_CONVERGENCE_PATTERNS = [
    {
        "id": "CONV-001",
        "pattern": "库存去化+现货升水+Backwardation三角共振",
        "modules": ["inventory", "basis", "term_structure"],
        "direction": "bullish",
        "strength": "strong",
        "check": lambda f: (
            _inv_bullish(f.get("inventory", {}))
            and _basis_bullish(f.get("basis", {}))
            and _term_bullish(f.get("term_structure", {}))
        ),
    },
    {
        "id": "CONV-002",
        "pattern": "库存累积+现货贴水+Contango三角共振",
        "modules": ["inventory", "basis", "term_structure"],
        "direction": "bearish",
        "strength": "strong",
        "check": lambda f: (
            _inv_bearish(f.get("inventory", {}))
            and _basis_bearish(f.get("basis", {}))
            and _term_bearish(f.get("term_structure", {}))
        ),
    },
    {
        "id": "CONV-003",
        "pattern": "价仓共振确认趋势",
        "modules": ["technical"],
        "direction": "bullish",  # dynamic, depends on oi_divergence
        "strength": "moderate",
        "check": lambda f: _oi_confirm(f.get("technical", {})),
    },
    {
        "id": "CONV-004",
        "pattern": "持仓净多增加+库存去化+Backwardation",
        "modules": ["positioning", "inventory", "term_structure"],
        "direction": "bullish",
        "strength": "moderate",
        "check": lambda f: (
            _pos_bullish(f.get("positioning", {}))
            and _inv_bullish(f.get("inventory", {}))
            and _term_bullish(f.get("term_structure", {}))
        ),
    },
]

_DIVERGENCE_PATTERNS = [
    {
        "id": "DIV-001",
        "pattern": "高拥挤+价量背离",
        "modules": ["positioning", "technical"],
        "direction": "bearish",
        "type": "reversal_risk",
        "check": lambda f: (
            _crowding_high(f.get("positioning", {}))
            and _oi_conflict(f.get("technical", {}))
        ),
    },
    {
        "id": "DIV-002",
        "pattern": "库存去化vs价格疲软",
        "modules": ["inventory", "technical"],
        "direction": "bearish",
        "type": "divergence",
        "check": lambda f: (
            _inv_bullish(f.get("inventory", {}))
            and _price_bearish(f.get("technical", {}))
        ),
    },
    {
        "id": "DIV-003",
        "pattern": "Contango+深度负carry做多成本高",
        "modules": ["term_structure"],
        "direction": "bearish",
        "type": "carry_cost",
        "check": lambda f: _term_bearish(f.get("term_structure", {})),
    },
    {
        "id": "DIV-004",
        "pattern": "高波动+高拥挤双重风险",
        "modules": ["technical", "positioning"],
        "direction": "bearish",
        "type": "reversal_risk",
        "check": lambda f: (
            _vol_high(f.get("technical", {}))
            and _crowding_high(f.get("positioning", {}))
        ),
    },
    {
        "id": "DIV-005",
        "pattern": "现货升水vs远月Contango期限结构矛盾",
        "modules": ["basis", "term_structure"],
        "direction": "neutral",
        "type": "divergence",
        "check": lambda f: (
            _basis_bullish(f.get("basis", {}))
            and _term_bearish(f.get("term_structure", {}))
        ),
    },
]

_WARNINGS = [
    {
        "id": "WARN-001",
        "type": "contract_lifecycle",
        "trigger": "合约临近交割(<30天)",
        "action": "关注移仓换月节奏",
    },
    {
        "id": "WARN-002",
        "type": "data_staleness",
        "trigger": "库存数据滞后超过5天",
        "action": "价格可能已反映更新的库存状况",
    },
]


def _safe_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _snap(module: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(module, dict):
        return {}
    s = module.get("snapshot", {}) or {}
    return s if isinstance(s, dict) else {}


def _inv_bullish(module: Dict[str, Any]) -> bool:
    v = _safe_float(_snap(module).get("wow_change"))
    return v is not None and v < 0


def _inv_bearish(module: Dict[str, Any]) -> bool:
    v = _safe_float(_snap(module).get("wow_change"))
    return v is not None and v > 0


def _basis_bullish(module: Dict[str, Any]) -> bool:
    r = _safe_float(_snap(module).get("dom_basis_rate"))
    return r is not None and r > 0


def _basis_bearish(module: Dict[str, Any]) -> bool:
    r = _safe_float(_snap(module).get("dom_basis_rate"))
    return r is not None and r < 0


def _term_bullish(module: Dict[str, Any]) -> bool:
    s = _snap(module).get("structure", "")
    return isinstance(s, str) and "backwardation" in s.lower()


def _term_bearish(module: Dict[str, Any]) -> bool:
    s = _snap(module).get("structure", "")
    return isinstance(s, str) and "contango" in s.lower()


def _pos_bullish(module: Dict[str, Any]) -> bool:
    c = _safe_float(_snap(module).get("net_long_change_5d"))
    return c is not None and c > 0


def _crowding_high(module: Dict[str, Any]) -> bool:
    p = _safe_float(_snap(module).get("crowding_pctl_180d"))
    return p is not None and p > 90


def _oi_confirm(module: Dict[str, Any]) -> bool:
    combined = module.get("combined", {}) if isinstance(module, dict) else {}
    div = combined.get("oi_divergence", "") if isinstance(combined, dict) else ""
    return div == "confirm"


def _oi_conflict(module: Dict[str, Any]) -> bool:
    combined = module.get("combined", {}) if isinstance(module, dict) else {}
    div = combined.get("oi_divergence", "") if isinstance(combined, dict) else ""
    return div == "conflict"


def _price_bearish(module: Dict[str, Any]) -> bool:
    combined = module.get("combined", {}) if isinstance(module, dict) else {}
    d = combined.get("direction", "") if isinstance(combined, dict) else ""
    return str(d).strip().lower() in ("short", "bearish", "看空")


def _vol_high(module: Dict[str, Any]) -> bool:
    combined = module.get("combined", {}) if isinstance(module, dict) else {}
    vol = combined.get("volatility", {}) if isinstance(combined, dict) else {}
    regime = vol.get("regime", "") if isinstance(vol, dict) else ""
    return str(regime).strip().lower() == "high"


def _check_conditions(features: Dict[str, Any]) -> Dict[str, List[str]]:
    """返回模式中各模块 conditions_met 的文本描述。"""
    result: Dict[str, Dict[str, str]] = {}
    for pat in _CONVERGENCE_PATTERNS + _DIVERGENCE_PATTERNS:
        for mod in pat.get("modules", []):
            if mod not in result:
                result[mod] = {}
    # inventory
    inv = features.get("inventory", {})
    wow = _safe_float(_snap(inv).get("wow_change"))
    if wow is not None:
        result.setdefault("inventory", {})["wow_change"] = (
            f"wow={'%.1f' % wow}" if abs(wow) < 100 else f"wow={'%.0f' % wow}"
        )
    # basis
    basis = features.get("basis", {})
    br = _safe_float(_snap(basis).get("dom_basis_rate"))
    if br is not None:
        result.setdefault("basis", {})["dom_basis_rate"] = f"basis={'%.4f' % br}"
    # term
    term = features.get("term_structure", {})
    ts = _snap(term).get("structure", "")
    if ts:
        result.setdefault("term_structure", {})["structure"] = f"{ts}"
    # positioning
    pos = features.get("positioning", {})
    cp = _safe_float(_snap(pos).get("crowding_pctl_180d"))
    if cp is not None:
        result.setdefault("positioning", {})["crowding"] = f"crowding={'%.0f%%' % cp}"
    # technical
    tech = features.get("technical", {})
    combined = tech.get("combined", {}) if isinstance(tech, dict) else {}
    div = combined.get("oi_divergence", "") if isinstance(combined, dict) else ""
    if div:
        result.setdefault("technical", {})["oi_divergence"] = f"oi={div}"
    return result  # type: ignore[return-value]


def detect_signal_convergence(
    features: Dict[str, Any],
    contract_warning: Optional[str] = None,
    data_staleness: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """检测信号共振、背离和警告。

    Args:
        features: features 层 6 模块输出字典
        contract_warning: _compute_contract_expiry 返回的 warning 字符串(可选)
        data_staleness: data_freshness 输出的 stalest 信息(可选)

    Returns:
        dict: {
            "convergences": [已检测到的共振模式],
            "divergences": [已检测到的背离模式],
            "warnings": [系统警告],
        }
    """
    conditions = _check_conditions(features)

    convergences: List[Dict[str, Any]] = []
    for pat in _CONVERGENCE_PATTERNS:
        try:
            if pat["check"](features):
                entry = {
                    "id": pat["id"],
                    "pattern": pat["pattern"],
                    "modules": pat["modules"],
                    "direction": pat["direction"],
                    "strength": pat["strength"],
                    "conditions_met": {
                        m: conditions.get(m, {}) for m in pat["modules"]
                    },
                    "statement": _build_conv_statement(pat),
                }
                convergences.append(entry)
        except Exception:
            continue

    divergences: List[Dict[str, Any]] = []
    for pat in _DIVERGENCE_PATTERNS:
        try:
            if pat["check"](features):
                entry = {
                    "id": pat["id"],
                    "pattern": pat["pattern"],
                    "modules": pat["modules"],
                    "direction": pat["direction"],
                    "type": pat["type"],
                    "conditions_met": {
                        m: conditions.get(m, {}) for m in pat["modules"]
                    },
                    "statement": _build_div_statement(pat),
                }
                divergences.append(entry)
        except Exception:
            continue

    warnings: List[Dict[str, Any]] = []
    for w in _WARNINGS:
        entry = dict(w)
        if w["type"] == "contract_lifecycle" and contract_warning:
            entry["triggered"] = bool(contract_warning)
        elif w["type"] == "data_staleness" and data_staleness:
            entry["triggered"] = bool(data_staleness)
        else:
            entry["triggered"] = False
        warnings.append(entry)

    return {
        "convergences": convergences,
        "divergences": divergences,
        "warnings": warnings,
    }


def _build_conv_statement(pat: Dict[str, Any]) -> str:
    return f"{pat['pattern']}，方向{'看多' if pat['direction']=='bullish' else '看空'}，强度{pat['strength']}"


def _build_div_statement(pat: Dict[str, Any]) -> str:
    type_label = {"reversal_risk": "反转风险", "divergence": "背离", "carry_cost": "展期成本"}.get(
        pat.get("type", ""), "背离"
    )
    return f"{pat['pattern']}，{type_label}，方向{'看空' if pat['direction']=='bearish' else '中性'}"
