"""
investment_director.py — 投研总监节点 (Phase 4 改造)

替代 commodity 决策链的 L3-L5（风控辩论 → 风控经理 → CIO），
使用 1 个量化检查器（纯规则）+ 1 次 LLM 调用完成风险评估与最终决策。

数据流:
  L1(4) → L2 推理分析师 → 量化检查器(纯规则) → 投研总监(1xLLM) → END

关键原则：量化数据永不丢失——即使 LLM 挂了，风险矩阵和 flags 仍然基于纯规则产出。
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Optional

from tradingagents.utils.logging_init import get_logger

from tradingagents.agents.analysts.commodity import build_custom_data_context
from tradingagents.agents.managers.strategy_fitness import evaluate_strategy_fitness

logger = get_logger("default")


# =============================================================================
# 常量
# =============================================================================

RISK_LEVEL_LABELS = {
    1: "极低风险(R1)",
    2: "低风险(R2)",
    3: "中等风险(R3)",
    4: "高风险(R4)",
    5: "极高风险(R5)",
}

_DIRECTION_PATTERN = re.compile(
    r'\*{0,2}方向\*{0,2}\s*[:：]\s*(做多|做空|买入|卖出|持有|平仓)'
)
_CONFIDENCE_PATTERN = re.compile(
    r'\*{0,2}置信度\*{0,2}\s*[:：]\s*([0-9]+\.?[0-9]*)'
)
_DIRECTION_CN_TO_CANONICAL = {
    "做多": "long", "买入": "long", "做空": "short", "卖出": "short",
    "持有": "hold", "平仓": "flat",
}
_DIRECTION_CANONICAL_TO_CN = {
    "long": "做多", "short": "做空", "hold": "持有", "flat": "平仓",
}


def normalize_direction(value: Any) -> str:
    """将中英文方向归一化为 long/short/hold/flat；未知值 fail closed。"""
    text = str(value or "").strip().lower()
    if text in ("long", "bullish", "做多", "买入", "看多", "向上"):
        return "long"
    if text in ("short", "bearish", "做空", "卖出", "看空", "向下"):
        return "short"
    if text in ("flat", "平仓"):
        return "flat"
    return "hold"


def extract_decision_fields(text: Any) -> Dict[str, Any]:
    """解析 CIO Markdown；字段缺失时安全默认为 hold/0。"""
    raw_text = str(text or "")
    direction_match = _DIRECTION_PATTERN.search(raw_text)
    confidence_match = _CONFIDENCE_PATTERN.search(raw_text)
    action = "hold"
    confidence = 0.0
    if direction_match:
        action = _DIRECTION_CN_TO_CANONICAL.get(direction_match.group(1), "hold")
    if confidence_match:
        try:
            parsed = float(confidence_match.group(1))
            if 0.0 <= parsed <= 1.0:
                confidence = parsed
        except ValueError:
            pass
    return {
        "action": action,
        "confidence": confidence,
        "direction_match": direction_match,
        "confidence_match": confidence_match,
    }


_RESEARCH_DIRECTION_PATTERN = re.compile(
    r'研究结论方向\s*[:：]\s*(看多|看空|中性)'
)
_RESEARCH_CONFIDENCE_PATTERN = re.compile(
    r'置信度\s*[:：]\s*([0-9]+\.?[0-9]*)'
)


def _extract_research_direction(text: str) -> str:
    """从 research_brief 提取研究结论方向。"""
    m = _RESEARCH_DIRECTION_PATTERN.search(str(text))
    if m:
        return {"看多": "long", "看空": "short", "中性": "hold"}.get(m.group(1), "hold")
    return "hold"


def _extract_research_confidence(text: str) -> float:
    """从 research_brief 提取置信度。"""
    m = _RESEARCH_CONFIDENCE_PATTERN.search(str(text))
    if m:
        try:
            return max(0.0, min(1.0, float(m.group(1))))
        except ValueError:
            pass
    return 0.0


def rewrite_decision_markdown(text: Any, action: str, confidence: float) -> str:
    """用标准字段改写最终决策，兼容全角冒号和不同小数格式。"""
    raw_text = str(text or "")
    direction_cn = _DIRECTION_CANONICAL_TO_CN.get(normalize_direction(action), "持有")
    confidence = max(0.0, min(float(confidence), 1.0))
    direction_line = f"**方向**:{direction_cn}"
    confidence_line = f"**置信度**:{confidence:.2f}"

    if _DIRECTION_PATTERN.search(raw_text):
        raw_text = _DIRECTION_PATTERN.sub(direction_line, raw_text, count=1)
    else:
        raw_text = f"- {direction_line}\n{raw_text}".strip()
    if _CONFIDENCE_PATTERN.search(raw_text):
        raw_text = _CONFIDENCE_PATTERN.sub(confidence_line, raw_text, count=1)
    else:
        raw_text = f"- {confidence_line}\n{raw_text}".strip()
    return raw_text


def _merge_llm_risk_card(rule_card: Dict[str, Any], llm_card: Any) -> Dict[str, Any]:
    """只合并 LLM 定性字段，纯规则矩阵和数据质量永不被覆盖。

    风险裁定字段从 LLM 获取策略约束语义（允许策略/禁止策略/约束说明）。
    """
    merged = dict(rule_card)
    if not isinstance(llm_card, dict):
        return merged
    for key in ("三方视角", "风险提示"):
        if key in llm_card:
            merged[key] = llm_card[key]
    llm_verdict = llm_card.get("风险裁定")
    if isinstance(llm_verdict, dict):
        verdict = dict(merged.get("风险裁定", {}))
        for key in ("允许策略", "禁止策略", "策略约束说明"):
            if key in llm_verdict:
                verdict[key] = llm_verdict[key]
        merged["风险裁定"] = verdict
    return merged


def _l1_direction_counts(registry: Dict[str, Any]) -> Dict[str, int]:
    counts = {"long": 0, "short": 0, "neutral": 0, "active": 0}
    for entry in registry.values():
        if not isinstance(entry, dict) or entry.get("status") == "skipped":
            continue
        raw = str(entry.get("direction") or "").strip().lower()
        if raw in ("skip", "skipped", "?"):
            continue
        counts["active"] += 1
        direction = normalize_direction(raw)
        if direction in ("long", "short"):
            counts[direction] += 1
        else:
            counts["neutral"] += 1
    return counts


def _extract_counter_signal_explanation(investment_memo: Any) -> str:
    if not isinstance(investment_memo, dict):
        return ""
    conclusion = investment_memo.get("投研结论")
    if not isinstance(conclusion, dict):
        return ""
    value = conclusion.get("逆向信号处理") or conclusion.get("反向信号处理")
    return str(value or "").strip()


def _apply_override_to_memo(
    investment_memo: Any,
    override: Dict[str, Any],
) -> Dict[str, Any]:
    """让备忘录结论与最终安全裁定保持一致，并解释命中的硬约束。"""
    memo = dict(investment_memo) if isinstance(investment_memo, dict) else {}
    conclusion = memo.get("投研结论")
    conclusion = dict(conclusion) if isinstance(conclusion, dict) else {}
    rules = override.get("override_rules_triggered", [])
    conclusion["风险等级"] = override.get("risk_tier", "?")
    conclusion["推荐关注策略"] = override.get("allowed_strategies", [])
    conclusion["需规避策略"] = override.get("forbidden_strategies", [])
    conclusion["策略约束说明"] = override.get("strategy_constraints", "")
    if any(rule in ("R5_REJECT", "NEAR_DELIVERY_REJECT") for rule in rules):
        conclusion["核心观点"] = (
            "安全硬约束已触发：" + str(override.get("override_reason", ""))
        )
    memo["投研结论"] = conclusion
    return memo


def _sum_fitness(matrix: List[Dict[str, Any]], value: str) -> str:
    """从策略矩阵统计某 fitness 的策略名列表。"""
    names = [m["strategy"] for m in matrix if m.get("fitness") == value]
    return ", ".join(names)


_ALL_STRATEGIES = ["单边趋势", "展期收益", "跨期套利", "波动率", "跨品种"]


def _constraint_allowed(action: str, triggered: List[str]) -> List[str]:
    """根据规则引擎状态计算允许的策略列表。"""
    if action == "flat":
        return []
    if "DATA_INSUFFICIENT" in triggered:
        return [s for s in _ALL_STRATEGIES if s != "单边趋势"]
    if any(r in triggered for r in ("R5_REJECT", "NEAR_DELIVERY_REJECT")):
        return []
    # 允许所有未被禁止的策略
    forbidden = _constraint_forbidden(action, triggered)
    return [s for s in _ALL_STRATEGIES if s not in forbidden]


def _constraint_forbidden(action: str, triggered: List[str]) -> List[str]:
    """根据规则引擎状态计算禁止的策略列表。"""
    if action == "flat":
        return list(_ALL_STRATEGIES)
    forbidden = []
    if "DATA_INSUFFICIENT" in triggered:
        forbidden.append("单边趋势")
    if any(r in triggered for r in (
        "CROWDING_REVERSAL_RISK", "STRONG_REVERSE_FLAG",
        "POSITION_REVERSAL_RISK", "CARRY_COST_CONFLICT_LONG",
        "COUNTER_SIGNAL_EXPLANATION_REQUIRED", "NO_L1_DIRECTION_SUPPORT",
    )):
        if "单边趋势" not in forbidden:
            forbidden.append("单边趋势")
    return forbidden


def _constraint_text(action: str, triggered: List[str], reason: str) -> str:
    """生成人类可读的策略约束说明。"""
    if action == "flat":
        return f"硬约束触发，禁止所有策略。{reason}"
    if "DATA_INSUFFICIENT" in triggered:
        return f"数据不足，不能支持单边趋势判断。{reason}"
    if any(r in triggered for r in (
        "CROWDING_REVERSAL_RISK", "STRONG_REVERSE_FLAG",
    )):
        return f"存在强反向风险信号，不适合单边趋势策略。{reason}"
    return reason or "无额外策略约束"


# =============================================================================
# 量化检查器：纯规则引擎，0 LLM
# =============================================================================

def _extract_safe(obj: Any, *keys: str, default: Any = None) -> Any:
    """安全地沿着 key 链提取嵌套 dict 的值。"""
    for key in keys:
        if not isinstance(obj, dict):
            return default
        obj = obj.get(key, {})
    return obj if obj != {} else default


def _rate_zscore(z: float) -> int:
    """z-score 到风险等级的通用映射。"""
    abs_z = abs(z)
    if abs_z < 1:
        return 2
    elif abs_z < 2:
        return 3
    elif abs_z < 3:
        return 4
    else:
        return 5


def _rate_percentile(pctl: float, thresholds) -> int:
    """将百分位值映射到 R1-R5 等级。

    Args:
        pctl: 百分位值 0-100
        thresholds: 边界值列表 [(upper, level), ...]，第一个匹配的返回对应 level

    Returns:
        int: 1-5 风险等级
    """
    for upper, level in thresholds:
        if pctl < upper:
            return level
    return 5


def _rate_crowding(pctl: float) -> int:
    """拥挤度双向风险映射：过高（踩踏）和过低（流动性枯竭）均极端。

    pctl 是 0-100 的百分位值。
    """
    if pctl > 90 or pctl < 10:
        return 5  # R5 极端拥挤/冷清
    if pctl > 80 or pctl < 20:
        return 4  # R4 高拥挤/冷清
    if pctl > 65 or pctl < 35:
        return 3  # R3 略偏离均衡
    return 2         # R2 正常


def compute_risk_assessment(commodity_features: Dict[str, Any]) -> Dict[str, Any]:
    """量化检查器：从 commodity_features 提取各维度指标并计算风险等级。

    这是一个纯函数，无副作用，不调用 LLM。

    Args:
        commodity_features: features 层 6 模块输出

    Returns:
        dict: 结构化风险评估
    """
    from datetime import datetime

    if not commodity_features:
        return {
            "composite_risk_level": "UNKNOWN",
            "data_insufficient": True,
            "data_quality": {
                "total_modules": 0,
                "available_modules": 0,
                "details": {},
            },
            "dimensions": {},
            "flags": [],
            "timestamp": datetime.now().isoformat(),
        }

    # ---- 数据质量前置检查 ----
    data_quality: Dict[str, Any] = {}
    for module_name in [
        "technical",
        "basis",
        "inventory",
        "positioning",
        "term_structure",
        "news_sentiment",
    ]:
        module = commodity_features.get(module_name, {})
        if not isinstance(module, dict):
            module = {}
        quality = module.get("quality", {})
        if not isinstance(quality, dict):
            quality = {}
        rows = quality.get("rows", 0)
        coverage = quality.get("coverage", 1.0)
        freshness = quality.get("data_freshness_days", 0)

        is_available = (
            isinstance(rows, (int, float)) and rows > 0
            and isinstance(coverage, (int, float)) and coverage >= 0.3
        )

        data_quality[module_name] = {
            "available": bool(is_available),
            "rows": int(rows) if isinstance(rows, (int, float)) else 0,
            "coverage": float(coverage) if isinstance(coverage, (int, float)) else 1.0,
            "freshness_days": int(freshness) if isinstance(freshness, (int, float)) else 0,
        }

    available_count = sum(1 for v in data_quality.values() if v["available"])
    total_count = len(data_quality)

    # ---- 单维度评级 ----
    dimensions: Dict[str, Any] = {}
    flags: list = []

    # 1. 波动率
    vol_pctl = _extract_safe(
        commodity_features, "technical", "combined", "volatility", "atr_ratio_pctl180"
    )
    if isinstance(vol_pctl, (int, float)) and data_quality["technical"]["available"]:
        vol_level = _rate_percentile(float(vol_pctl), [
            (20, 1),
            (50, 2),
            (80, 3),
            (95, 4),
        ])
        dimensions["volatility"] = {
            "value": float(vol_pctl),
            "level": vol_level,
            "tier": RISK_LEVEL_LABELS[vol_level],
            "source": "technical.combined.volatility.atr_ratio_pctl180",
            "interpretation": {
                1: "波动率极低，市场过于平静",
                2: "波动率正常偏低，趋势延续概率高",
                3: "波动率正常偏高，趋势可能加速",
                4: "波动率高，市场分歧加大",
                5: "波动率极高，市场恐慌或狂热",
            }[vol_level],
        }
    else:
        dimensions["volatility"] = {"level": 0, "tier": "unknown", "available": False}

    # 2. 基差偏离
    basis_z = _extract_safe(
        commodity_features, "basis", "stats", "zscore_180d", "dom_basis_rate"
    )
    if isinstance(basis_z, (int, float)) and data_quality["basis"]["available"]:
        basis_level = _rate_zscore(float(basis_z))
        dimensions["basis"] = {
            "value": float(basis_z),
            "level": basis_level,
            "tier": RISK_LEVEL_LABELS[basis_level],
            "source": "basis.stats.zscore_180d.dom_basis_rate",
            "interpretation": {
                2: "基差在正常范围内波动",
                3: "基差偏离适中，均值回归力量中等",
                4: "基差偏离较大，均值回归力量强",
                5: "基差处于3sigma极端区间，均值回归力量极强",
            }[basis_level],
        }
        if basis_level >= 5:
            flags.append({
                "name": "basis_extreme",
                "flag": "基差处于 3sigma 极端区间，均值回归力量强",
                "severity": "high",
            })
    else:
        dimensions["basis"] = {"level": 0, "tier": "unknown", "available": False}

    # 3. 持仓拥挤度（双向风险：过高和过低均极端）
    crowding = _extract_safe(
        commodity_features, "positioning", "snapshot", "crowding_pctl_180d"
    )
    if isinstance(crowding, (int, float)) and data_quality["positioning"]["available"]:
        crowd_level = _rate_crowding(float(crowding))
        dimensions["crowding"] = {
            "value": float(crowding),
            "level": crowd_level,
            "tier": RISK_LEVEL_LABELS[crowd_level],
            "source": "positioning.snapshot.crowding_pctl_180d",
            "interpretation": {
                2: "持仓分布正常，多空相对均衡",
                3: "持仓略偏离均衡",
                4: "持仓处于高拥挤区间，一致性预期过强，反转风险显著",
                5: "市场一致性预期极端，存在极高的反向踩踏风险",
            }[crowd_level],
        }
    else:
        dimensions["crowding"] = {"level": 0, "tier": "unknown", "available": False}

    # 4. 库存偏离
    inv_z = _extract_safe(commodity_features, "inventory", "stats", "zscore_180d")
    if isinstance(inv_z, (int, float)) and data_quality["inventory"]["available"]:
        inv_level = _rate_zscore(float(inv_z))
        dimensions["inventory"] = {
            "value": float(inv_z),
            "level": inv_level,
            "tier": RISK_LEVEL_LABELS[inv_level],
            "source": "inventory.stats.zscore_180d",
            "interpretation": {
                2: "库存水平在正常范围内波动",
                3: "库存偏离适中",
                4: "库存偏离较大，可能存在供需冲击",
                5: "库存处于3sigma极端区间，供需严重失衡",
            }[inv_level],
        }
    else:
        dimensions["inventory"] = {"level": 0, "tier": "unknown", "available": False}

    # 5. 期限结构
    carry = _extract_safe(
        commodity_features, "term_structure", "snapshot", "carry_score"
    )
    if isinstance(carry, (int, float)) and data_quality["term_structure"]["available"]:
        carry_val = float(carry)
        if carry_val > 0.3:
            carry_level = 2
        elif carry_val > -0.3:
            carry_level = 3
        elif carry_val > -0.6:
            carry_level = 4
        else:
            carry_level = 5
        dimensions["term_structure"] = {
            "value": carry_val,
            "level": carry_level,
            "tier": RISK_LEVEL_LABELS[carry_level],
            "source": "term_structure.snapshot.carry_score",
            "interpretation": {
                2: "期限结构有利于多头持仓",
                3: "期限结构中性",
                4: "期限结构不利于多头持仓",
                5: "极端期限结构",
            }[carry_level],
        }
        # carry_cost flag: carry_score<-0.5 AND structure=="contango"
        structure = _extract_safe(
            commodity_features, "term_structure", "snapshot", "structure", default=""
        )
        if carry_val < -0.5 and (
            isinstance(structure, str) and "contango" in structure.lower()
        ):
            flags.append({
                "name": "carry_cost",
                "flag": "深度 Contango 结构，多头展期成本高",
                "severity": "medium",
            })
    else:
        dimensions["term_structure"] = {"level": 0, "tier": "unknown", "available": False}

    # 6. 价仓关系
    oi_div = _extract_safe(
        commodity_features, "technical", "combined", "oi_divergence"
    )
    if isinstance(oi_div, str) and data_quality["technical"]["available"]:
        if oi_div == "confirm":
            oi_level = 2
        elif oi_div == "neutral":
            oi_level = 3
        else:
            oi_level = 4
        dimensions["oi_divergence"] = {
            "value": oi_div,
            "level": oi_level,
            "tier": RISK_LEVEL_LABELS.get(oi_level, str(oi_level)),
            "source": "technical.combined.oi_divergence",
            "interpretation": {
                2: "价格与持仓共振，趋势可信度高",
                3: "价格与持仓关系中性",
                4: "价格与持仓背离，警惕趋势反转",
            }[oi_level],
        }
    else:
        dimensions["oi_divergence"] = {"level": 0, "tier": "unknown", "available": False}

    # 7. 新闻情绪（参考，不参与等级计算）
    sentiment_ratio = _extract_safe(
        commodity_features, "news_sentiment", "snapshot", "sentiment", "ratio"
    )
    if isinstance(sentiment_ratio, (int, float)) and data_quality["news_sentiment"]["available"]:
        sent_val = float(sentiment_ratio)
        if sent_val > 0.6:
            sent_label = "偏多"
        elif sent_val >= 0.4:
            sent_label = "中性"
        else:
            sent_label = "偏空"
        dimensions["news_sentiment"] = {
            "value": sent_val,
            "label": sent_label,
            "level": 0,
            "tier": "参考",
            "interpretation": f"情感: {sent_label}",
            "source": "news_sentiment.snapshot.sentiment.ratio",
        }
    else:
        dimensions["news_sentiment"] = {"level": 0, "tier": "unknown", "available": False}

    # ---- 交叉硬拦截条件 ----
    vol_level_val = dimensions.get("volatility", {}).get("level", 0)
    crowd_level_val = dimensions.get("crowding", {}).get("level", 0)
    oi_level_val = dimensions.get("oi_divergence", {}).get("level", 0)

    if isinstance(vol_level_val, int) and isinstance(crowd_level_val, int):
        if vol_level_val >= 4 and crowd_level_val >= 4:
            flags.append({
                "name": "vol_crowding",
                "flag": "高波动+高拥挤双重风险，反转概率显著升高",
                "severity": "high",
            })

    jump_flag = _extract_safe(commodity_features, "inventory", "jump_flag", default=False)
    if jump_flag:
        flags.append({
            "name": "inventory_jump",
            "flag": "库存数据发生跳变，可能存在突发供需冲击或数据异常",
            "severity": "medium",
        })

    # oi_trap: 价仓背离 + 高拥挤
    if oi_div == "conflict" and isinstance(crowd_level_val, int) and crowd_level_val >= 4:
        flags.append({
            "name": "oi_trap",
            "flag": "价格与持仓背离+高拥挤：警惕主力出货/诱多陷阱",
            "severity": "high",
        })

    # multi_extreme: 多维度 R4+
    r4_dims = [
        name
        for name in ["volatility", "basis", "crowding", "inventory", "term_structure"]
        if isinstance(dimensions.get(name, {}).get("level"), int)
        and dimensions[name]["level"] >= 4
    ]
    if len(r4_dims) >= 3:
        flags.append({
            "name": "multi_extreme",
            "flag": "多维度共振高风险，单一方向交易面临系统性不确定性",
            "severity": "critical",
        })

    # ---- 综合风险等级 ----
    available_levels = [
        dimensions[name]["level"]
        for name in ["volatility", "basis", "crowding", "inventory",
                      "term_structure", "oi_divergence"]
        if isinstance(dimensions.get(name, {}).get("level"), int) and dimensions[name]["level"] > 0
    ]

    if not available_levels:
        composite_level: Any = "UNKNOWN"
        data_insufficient = True
    else:
        data_insufficient = False
        r4_count = sum(1 for lvl in available_levels if lvl >= 4)
        r3_count = sum(1 for lvl in available_levels if lvl == 3)
        has_high_flags = any(
            f.get("severity") in ("high", "critical") for f in flags
        )

        if r4_count >= 3:
            composite_level = 5
        elif r4_count >= 2:
            composite_level = 4
        elif r4_count == 1 or r3_count >= 3:
            composite_level = 3
            if has_high_flags:
                composite_level = 4
        elif r3_count >= 1:
            composite_level = 2
            if has_high_flags:
                composite_level = 3
        else:
            composite_level = 1

    return {
        "composite_risk_level": composite_level,
        "data_insufficient": data_insufficient,
        "data_quality": {
            "total_modules": total_count,
            "available_modules": available_count,
            "details": data_quality,
        },
        "dimensions": dimensions,
        "flags": flags,
        "timestamp": datetime.now().isoformat(),
    }


# =============================================================================
# SafetyOverride — 纯规则硬约束二审（0 LLM）
# =============================================================================

def safety_override(
    risk_assessment: Dict[str, Any],
    llm_direction: str,
    llm_confidence: float,
    llm_raw: str = "",
    *,
    analyst_registry: Optional[Dict[str, Any]] = None,
    position_structured: Optional[Dict[str, Any]] = None,
    counter_signal_explanation: str = "",
    custom_data_feature_dict: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """在 LLM 输出后执行不可协商的纯规则二审,并返回完整审计记录。

    Args:
        custom_data_feature_dict: 商品 features 中 custom_data.feature_dict(可选),
            用于私有数据矛盾检测(与 LLM 方向相反时压制置信度)。
    """
    composite = risk_assessment.get("composite_risk_level", "UNKNOWN")
    flags = risk_assessment.get("flags", [])
    if not isinstance(flags, list):
        flags = []
    dimensions = risk_assessment.get("dimensions", {})
    if not isinstance(dimensions, dict):
        dimensions = {}
    data_insufficient = bool(risk_assessment.get("data_insufficient", False))

    original_action = normalize_direction(llm_direction)
    try:
        original_confidence = float(llm_confidence)
    except (TypeError, ValueError):
        original_confidence = 0.0
    if not 0.0 <= original_confidence <= 1.0:
        original_confidence = 0.0

    action = original_action
    confidence = original_confidence
    max_position = 1.0
    triggered: List[str] = []

    r5_dimensions = [
        name for name, detail in dimensions.items()
        if isinstance(detail, dict) and detail.get("level") == 5
    ]
    near_delivery = any(
        isinstance(flag, dict) and flag.get("name") == "near_delivery"
        for flag in flags
    )
    hard_flat = composite in (5, "R5") or bool(r5_dimensions) or near_delivery

    # 最高优先级：任一维度 R5 / 综合 R5 / 临近交割均强制平仓。
    if composite in (5, "R5") or r5_dimensions:
        triggered.append("R5_REJECT")
    if near_delivery:
        triggered.append("NEAR_DELIVERY_REJECT")
    if hard_flat:
        action = "flat"
        confidence = 0.0
        max_position = 0.0

    # 数据不足禁止生成新的方向性决策，但不得覆盖更高优先级 flat。
    if data_insufficient:
        triggered.append("DATA_INSUFFICIENT")
        if not hard_flat:
            if original_action in ("long", "short"):
                action = "hold"
            confidence = min(confidence, 0.2)
            max_position = min(max_position, 0.3)

    # 方向冲突和强反向风险：置信度封顶；未解释则禁止单边决策。
    contradiction_rules: List[str] = []
    if original_action in ("long", "short"):
        counts = _l1_direction_counts(analyst_registry or {})
        if analyst_registry is not None and counts[original_action] == 0:
            contradiction_rules.append("NO_L1_DIRECTION_SUPPORT")

        crowding_level = _extract_safe(dimensions, "crowding", "level", default=0)
        if isinstance(crowding_level, int) and crowding_level >= 4:
            contradiction_rules.append("CROWDING_REVERSAL_RISK")

        flag_names = {
            flag.get("name") for flag in flags if isinstance(flag, dict)
        }
        if flag_names.intersection({"vol_crowding", "oi_trap", "multi_extreme"}):
            contradiction_rules.append("STRONG_REVERSE_FLAG")
        if original_action == "long" and "carry_cost" in flag_names:
            contradiction_rules.append("CARRY_COST_CONFLICT_LONG")

        position_structured = position_structured or {}
        concentration = position_structured.get("concentration", {})
        risk_flags = position_structured.get("risk_flags", [])
        reversal_risk = (
            isinstance(concentration, dict)
            and concentration.get("reversal_risk") is True
        ) or any(
            keyword in str(risk)
            for risk in (risk_flags if isinstance(risk_flags, list) else [])
            for keyword in ("拥挤", "反转", "踩踏")
        )
        if reversal_risk:
            contradiction_rules.append("POSITION_REVERSAL_RISK")

        # ---- 私有数据矛盾检测:custom_data.direction 与 LLM 方向相反 ----
        fdict = custom_data_feature_dict or {}
        if isinstance(fdict, dict):
            custom_dir = fdict.get("_direction", "neutral")
            if custom_dir in ("bullish", "bearish"):
                llm_dir_norm = "bullish" if original_action == "long" else "bearish"
                if custom_dir != llm_dir_norm:
                    contradiction_rules.append("CUSTOM_DATA_CONTRADICTION")

    for rule in contradiction_rules:
        if rule not in triggered:
            triggered.append(rule)
    if contradiction_rules and not hard_flat and action in ("long", "short"):
        confidence = min(confidence, 0.3)
        max_position = min(max_position, 0.5)
        if not str(counter_signal_explanation or "").strip():
            triggered.append("COUNTER_SIGNAL_EXPLANATION_REQUIRED")
            action = "hold"

    # R4 风险继续限制仓位；warning-only 也进入审计但不强制改方向。
    high_or_critical = any(
        isinstance(flag, dict) and flag.get("severity") in ("high", "critical")
        for flag in flags
    )
    if not hard_flat and composite == 4 and high_or_critical:
        triggered.append("R4_FLAG_HALF_POSITION")
        max_position = min(max_position, 0.5)
    elif not hard_flat and composite == 4:
        triggered.append("R4_WARN_ONLY")

    vol_level = _extract_safe(dimensions, "volatility", "level", default=0)
    if (
        not hard_flat
        and isinstance(vol_level, int) and vol_level >= 4
        and isinstance(composite, int) and composite >= 4
    ):
        if "R4_FLAG_HALF_POSITION" not in triggered:
            triggered.append("R4_PLUS_HIGH_VOL")
        max_position = min(max_position, 0.5)

    # 保序去重，便于日志与证据链稳定。
    triggered = list(dict.fromkeys(triggered))
    overridden = (
        action != original_action
        or abs(confidence - original_confidence) > 1e-12
        or max_position < 1.0
    )

    rule_descriptions = {
        "R5_REJECT": "任一维度或综合风险达到 R5，强制平仓",
        "NEAR_DELIVERY_REJECT": "合约临近交割，强制平仓",
        "DATA_INSUFFICIENT": "数据不足，禁止新的方向性决策",
        "NO_L1_DIRECTION_SUPPORT": "没有 L1 分析师明确支持该方向",
        "CROWDING_REVERSAL_RISK": "持仓达到高拥挤区，反转风险显著",
        "STRONG_REVERSE_FLAG": "存在拥挤/价仓背离/多维极端强反向风险",
        "CARRY_COST_CONFLICT_LONG": "深度 Contango 展期成本与做多方向冲突",
        "POSITION_REVERSAL_RISK": "持仓分析明确标记拥挤反转风险",
        "COUNTER_SIGNAL_EXPLANATION_REQUIRED": "未解释为何忽略强反向信号，禁止单边方向",
        "R4_FLAG_HALF_POSITION": "综合 R4 且存在高风险标志，仓位上限减半",
        "R4_WARN_ONLY": "综合 R4，仅记录风险警告",
        "R4_PLUS_HIGH_VOL": "高波动与综合高风险并存，仓位上限减半",
        "CUSTOM_DATA_CONTRADICTION": "私有数据方向与 LLM 决策方向相反，需解释",
        "CUSTOM_DATA_OVERRELIANCE": "CIO 论点过度依赖用户上传数据(>50%)，仅记录审计",
    }
    override_reason = "；".join(
        rule_descriptions.get(rule, rule) for rule in triggered
    )

    # ---- 私有数据过度依赖检测(仅 audit warning,不改决策) ----
    _OVERRELIANCE_KEYWORDS = (
        "用户上传", "自定义数据", "用户提供", "用户数据",
        "user-uploaded", "user data", "用户文件",
    )
    _llm_raw = llm_raw or ""
    user_data_mentions = sum(_llm_raw.count(kw) for kw in _OVERRELIANCE_KEYWORDS)
    total_paragraphs = max(
        1,
        len([p for p in _llm_raw.split("\n\n") if p.strip()]),
    )
    overreliance_ratio = user_data_mentions / total_paragraphs
    if overreliance_ratio > 0.5 and user_data_mentions >= 3:
        triggered.append("CUSTOM_DATA_OVERRELIANCE")

    audit = {
        "executed": True,
        # 内部保留决策语义供 rule engine 使用
        "action": action,
        "confidence": confidence,
        "max_position": max_position,
        # 审计字段
        "overridden": overridden,
        "override_reason": override_reason,
        "override_rules_triggered": triggered,
        "original_llm_direction": original_action,
        "original_llm_confidence": original_confidence,
        "overridden_action": action,
        "overridden_confidence": confidence,
        "r5_dimensions": r5_dimensions,
        # 策略约束语义（对外输出）
        "risk_tier": f"R{composite}" if isinstance(composite, int) else str(composite),
        "allowed_strategies": _constraint_allowed(action, triggered),
        "forbidden_strategies": _constraint_forbidden(action, triggered),
        "strategy_constraints": _constraint_text(action, triggered, override_reason),
        # ---- 私有数据审计字段(Phase 自定义数据升级) ----
        "custom_data_direction": (custom_data_feature_dict or {}).get("_direction", "neutral"),
        "custom_data_conflict": "CUSTOM_DATA_CONTRADICTION" in triggered,
        "custom_data_overreliance": {
            "ratio": round(overreliance_ratio, 2),
            "mentions": user_data_mentions,
            "total_paragraphs": total_paragraphs,
            "warning_only": True,
        },
        "custom_data_as_of": (custom_data_feature_dict or {}).get("snapshot", {}).get("as_of"),
    }
    log_message = (
        "[投研总监|OVERRIDE] executed=True "
        f"input={original_action}/{original_confidence:.2f} composite={composite} "
        f"r5_dimensions={r5_dimensions} rules={triggered} "
        f"final={action}/{confidence:.2f} max_position={max_position:.2f} "
        f"overridden={overridden} "
        f"forbidden={audit['forbidden_strategies']}"
    )
    if overridden:
        logger.warning(log_message)
    else:
        logger.info(log_message)
    return audit


# =============================================================================
# 投研总监 LLM Prompt（使用 LangChain .partial() 替换变量）
# =============================================================================

INVESTMENT_DIRECTOR_SYSTEM_PROMPT = """你是大宗商品期货的**投研总监**。

你的职责是综合**推理分析师（L2）的研究报告**、**量化风险评估**和**策略适应性矩阵**，输出**策略适应性研究报告**而非交易指令。

⚠️ 你的角色是投研辅助——解释和连接，不是替用户做交易决策。**禁止输出具体交易价位**（入场价、止损价、目标价、仓位比例等）。
但你应基于多空证据的权重给出**研究结论方向**（看多/看空/中性）和**置信度**(0-1)，这是风控审计的必要输入。

---

## 输入材料

### 1. 推理分析师报告（L2）
{investment_plan}

推理分析师的 investment_plan 是结构化 JSON，包含估值矩阵、多空对照表和情景推演。

### 2. 量化风险评估
{risk_assessment_json}

纯规则引擎输出（0 LLM），包括：
- 维度风险矩阵：6 维度 R1-R5 等级
- 硬拦截标志：跨维度交叉风险
- 数据质量：各模块数据可用性

### 3. 策略适应性矩阵（量化规则）
{strategy_matrix_json}

纯规则引擎输出（0 LLM），5 类策略的适应性评估结果（推荐关注/谨慎推荐/不推荐）。
**引用时不得改变 fitness 等级**，但可补充上下文解释。

### 4. L1 分析师注册表
{analyst_registry_summary}

### 5. 标的信息
- 合约: {full_symbol}
- 品种: {variety_name}
- 交易所: {exchange}
- 报价单位: {quote_unit}
- 交易日期: {trade_date}

### 6. 用户上传数据参考
{custom_data_context}

---

## 输出要求

输出可直接被 json.loads() 解析的 JSON（不要额外 markdown 包裹）。

### 顶层结构

你必须输出包含以下三个顶级 key 的 JSON：

1. **投研备忘录** (dict) — 对 L2 报告的审核与裁决
2. **风险评估卡** (dict) — 综合量化 + 定性风险评估
3. **research_brief** (str) — 策略适应性研究报告 Markdown

### key 1: 投研备忘录 的详细结构

- 估值审核 (dict): 逐维度审核，每个维度的值是 {{
    "判断": "同意" 或 "修正",
    "理由": "具体理由，引用 L1/L2 证据 ID",
    "引用ID": "REF-TECH-xxx"
  }}
  需要的维度：波动率、基差、库存、持仓、期限结构、新闻情绪

- 情景裁决 (dict):
  - "选定情景": "保守情景/基准情景/乐观情景"
  - "排除理由": "未选情景的排除原因"
  - "触发条件满足度": "高/中/低"
  - "核心分歧处理": "对 L2 主要分歧的裁决"

- 投研结论 (dict):
  - "风险等级": "引用量化综合风险等级 R1-R5"
  - "核心观点": "2-3 句话概括多空核心矛盾和关键数据信号"
  - "风险信号": ["信号1", "信号2"]  — 客观罗列风险信号，不做方向性推荐
  - "推荐关注策略": []  — 从策略适应性矩阵中选 1-2 个推荐关注的策略
  - "需规避策略": []  — 从策略适应性矩阵中选不推荐的策略

### key 2: 风险评估卡 的详细结构

⚠️ 量化风险矩阵由系统纯规则唯一产出，LLM 不需要重新输出。
LLM 仅负责以下定性维度：

- 三方视角 (dict):
  - "激进": {{"概率权重": 0.3, "条件": "..."}}
  - "保守": {{"概率权重": 0.2, "条件": "..."}}
  - "中性": {{"概率权重": 0.5, "条件": "..."}}

- 风险裁定 (dict):
  - "允许策略": []  — 量化和情景维度均允许的策略列表
  - "禁止策略": []  — 约束条件明确禁止的策略列表
  - "策略约束说明": "..."  — 人类可读的策略约束解释

- 风险提示 (list): 2-3 条主要风险

### key 3: research_brief（替代 final_decision_markdown）

必须包含以下 Markdown 章节：

```
# {full_symbol} 策略适应性报告

## 核心矛盾与叙事
（2-3 句话概括当前的多空逻辑冲突点 + 关键数据信号）

## 策略适应性矩阵
| 策略 | 适应性 | 核心判据 |
| ... | ... | ... |

（从量化策略矩阵引用数据，不可改变适应性评级）

## 三方情景推演
（保留情景描述、触发条件、关注焦点，每项增加"推荐策略"）

## 关键待验证假设
- [ ] 待验证假设列表（可观察、可量化的数据信号）
```

---

## 严格约束

1. 估值审核各维度必须用"同意"或"修正"开头，引用证据 ID（REF-TECH-xxx 格式）
2. 情景裁决必须给出排除理由，不能只写选定不写排除
3. research_brief 必须包含 4 个章节（核心矛盾、策略矩阵、情景推演、待验证假设）+ 末尾标注「研究结论方向: 看多/看空/中性, 置信度: X.XX」；禁止输出入场价、止损价、目标价、仓位
4. 【硬约束】任一量化风险维度为 R5，或综合风险为 R5：禁止策略=[全部禁止]，策略约束说明必须明确列出触发的 R5 维度
5. 【硬约束】存在 near_delivery 标志：禁止策略=[全部禁止]；策略约束说明必须提及临近交割
6. 【硬约束】data_insufficient=true 时禁止策略必须包含"单边趋势"
7. 策略适应性矩阵中 fitness="不推荐"的策略必须出现在"禁止策略"中；fitness="推荐关注"的策略不得出现在"禁止策略"中
8. 策略矩阵的适应性评级（推荐关注/谨慎推荐/不推荐）不得改变，只可补充解释
9. 用户上传的历史时间序列若明确提示无法获取当前值，禁止将其写成当前趋势依据
10. 【硬约束】输出纯 JSON，禁止使用 ```json 代码块包裹，否则解析失败将视为系统降级。直接以 `{{` 开头，`}}` 结尾
11. 全文中文
"""


# =============================================================================
# 工厂函数
# =============================================================================

def _build_risk_card(risk_assessment: Dict[str, Any]) -> Dict[str, Any]:
    """从量化检查器结果构建风险评估卡（纯规则，0 LLM）。"""
    dimensions = risk_assessment.get("dimensions", {})
    composite = risk_assessment.get("composite_risk_level", "UNKNOWN")
    flags = risk_assessment.get("flags", [])

    risk_label = (
        RISK_LEVEL_LABELS.get(composite, f"等级{composite}")
        if isinstance(composite, int)
        else "未知"
    )

    def _dim_to_card(name: str, display: str, val_key: str = "value") -> dict:
        d = dimensions.get(name, {})
        level = d.get("level", "?")
        return {
            "等级": f"R{level}" if isinstance(level, int) and level > 0 else "N/A",
            "值": d.get(val_key),
            "解读": d.get("interpretation", d.get("label", "")),
        }

    return {
        "量化风险矩阵": {
            "波动率": _dim_to_card("volatility", "波动率"),
            "基差": _dim_to_card("basis", "基差"),
            "持仓拥挤": _dim_to_card("crowding", "持仓拥挤"),
            "库存": _dim_to_card("inventory", "库存"),
            "期限结构": _dim_to_card("term_structure", "期限结构"),
            "价仓关系": _dim_to_card("oi_divergence", "价仓关系"),
        },
        "硬拦截标志": [
            {"名称": f["name"], "消息": f["flag"], "严重程度": f.get("severity", "info")}
            for f in flags
        ],
        "风险裁定": {
            "总体风险等级": risk_label,
            "数据充分": not risk_assessment.get("data_insufficient", False),
            "数据质量": risk_assessment.get("data_quality", {}),
        },
    }


def _build_fallback_memo(risk_assessment: Dict[str, Any]) -> Dict[str, Any]:
    """LLM 不可用时的 fallback 备忘录。"""
    composite = risk_assessment.get("composite_risk_level", "UNKNOWN")
    composite_str = f"R{composite}" if isinstance(composite, int) else str(composite)
    return {
        "估值审核": (
            "（LLM 不可用，量化检查器已完成维度评级，详见风险评估卡）"
        ),
        "情景裁决": "（LLM 不可用，无法裁决）",
        "投研结论": {
            "风险等级": composite_str,
            "核心观点": f"系统降级：LLM 不可用，量化风险等级 {composite_str}，无法生成策略建议",
            "风险信号": [f"系统降级：量化风险 {composite_str}"],
            "推荐关注策略": [],
            "需规避策略": ["单边趋势", "展期收益", "跨期套利", "波动率", "跨品种"],
        },
    }


def _build_fallback_research_brief(full_symbol: str, risk_assessment: Dict[str, Any]) -> str:
    """LLM 不可用时的 fallback 研究简报。"""
    composite = risk_assessment.get("composite_risk_level", "UNKNOWN")
    risk_label = (
        RISK_LEVEL_LABELS.get(composite, f"等级{composite}")
        if isinstance(composite, int)
        else "未知"
    )
    flags = risk_assessment.get("flags", [])
    flag_lines = "\n".join(
        f"{i+1}. {f.get('flag', '')}" for i, f in enumerate(flags[:3])
    )
    flag_section = f"\n## 量化风险提示\n{flag_lines}\n" if flag_lines else ""

    return (
        f"# {full_symbol} 策略适应性报告（系统降级）\n\n"
        f"## 核心矛盾与叙事\n"
        f"系统降级：LLM 不可用，量化风险等级 {risk_label}。"
        f"无法进行深度多空逻辑判断，以下信息仅供参考。\n"
        f"{flag_section}\n"
        f"## 策略适应性矩阵\n"
        f"（LLM 不可用，无法生成）\n\n"
        f"## 三方情景推演\n"
        f"（LLM 不可用，无法裁决）\n\n"
        f"## 关键待验证假设\n"
        f"- [ ] 等待 LLM 服务恢复后重新生成完整分析\n"
    )


def create_investment_director(deep_thinking_llm):
    """投研总监工厂函数。

    Args:
        deep_thinking_llm: 用于深入推理的 LLM 实例

    Returns:
        callable: LangGraph 节点函数
    """

    def _to_native(o):
        """递归将 numpy 类型转为 Python 原生类型（MemorySaver msgpack 兼容）。"""
        import numpy as np
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, (np.ndarray,)):
            return o.tolist()
        if isinstance(o, dict):
            return {k: _to_native(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [_to_native(v) for v in o]
        return o

    def investment_director_node(state: Dict[str, Any]) -> Dict[str, Any]:
        """投研总监节点函数。"""
        from langchain_core.messages import AIMessage
        from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

        full_symbol = state.get("full_symbol") or state.get("company_of_interest", "Unknown")
        asset_type = state.get("asset_type", "stock")

        if asset_type != "commodity":
            logger.warning("[投研总监] 非 commodity 路径，跳过")
            return {}

        logger.info(f"[投研总监] 启动: {full_symbol}")

        # ---- Step 1: 量化检查器（纯规则，0 LLM） ----
        commodity_features = state.get("commodity_features", {})
        risk_assessment = _to_native(compute_risk_assessment(commodity_features))

        # 合并合约到期警告到 risk_assessment.flags
        contract_expiry = state.get("contract_expiry_warning", {}) or {}
        expiry_warning = contract_expiry.get("warning", "")
        if expiry_warning:
            risk_assessment.setdefault("flags", []).append({
                "name": "near_delivery",
                "flag": expiry_warning,
                "severity": "high",
            })
            risk_assessment["composite_risk_level"] = max(
                risk_assessment.get("composite_risk_level", 0) if isinstance(risk_assessment.get("composite_risk_level"), int) else 0,
                4
            )
            logger.warning(f"[投研总监] 合约到期风险注入: {expiry_warning}")

        composite = risk_assessment.get("composite_risk_level", "UNKNOWN")
        logger.info(
            f"[投研总监] 量化检查: 综合等级={composite}, "
            f"flags={len(risk_assessment.get('flags', []))}, "
            f"可用模块={risk_assessment.get('data_quality', {}).get('available_modules', 0)}"
        )

        # ---- Step 2: 构建风险卡（纯规则，永不丢失） ----
        rule_risk_card = _build_risk_card(risk_assessment)
        risk_card = dict(rule_risk_card)

        # ---- Step 2.5: 策略适应性评估（纯规则，0 LLM） ----
        strategy_matrix = evaluate_strategy_fitness(commodity_features, risk_assessment)
        strategy_matrix_json = json.dumps(
            strategy_matrix, ensure_ascii=False, indent=2, default=str
        )
        logger.info(
            f"[投研总监] 策略矩阵: {len(strategy_matrix)} 项, "
            f"推荐=[{_sum_fitness(strategy_matrix, '推荐关注')}], "
            f"谨慎=[{_sum_fitness(strategy_matrix, '谨慎推荐')}], "
            f"不推荐=[{_sum_fitness(strategy_matrix, '不推荐')}]"
        )

        # ---- Step 3: 准备 LLM prompt ----
        investment_plan = state.get("investment_plan", "{}")
        analyst_registry = state.get("analyst_registry", {})

        registry_lines = []
        for ref_id, info in analyst_registry.items():
            if isinstance(info, dict):
                cn_name = info.get("cn_name") or info.get("analyst", "?")
                direction = info.get("direction", "?")
                summary = (info.get("summary") or "")[:120]
                registry_lines.append(f"- {cn_name} [{ref_id}]: {direction} — {summary}")
        analyst_registry_summary = "\n".join(registry_lines) or "(无)"

        variety_name = state.get("variety_name", "")
        exchange = state.get("exchange", "")
        quote_unit = state.get("quote_unit", "")
        trade_date = state.get("trade_date", "")

        risk_assessment_json = json.dumps(
            risk_assessment, ensure_ascii=False, indent=2, default=str
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", INVESTMENT_DIRECTOR_SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="messages"),
        ]).partial(
            full_symbol=full_symbol,
            variety_name=variety_name,
            exchange=exchange,
            quote_unit=quote_unit,
            trade_date=trade_date,
            investment_plan=investment_plan,
            risk_assessment_json=risk_assessment_json,
            strategy_matrix_json=strategy_matrix_json,
            analyst_registry_summary=analyst_registry_summary,
            custom_data_context=build_custom_data_context(commodity_features),
        )

        messages_payload = prompt.format_messages(
            messages=state.get("messages", []) or []
        )

        # ---- Step 4: LLM 调用（3 次重试） ----
        content: Optional[str] = None
        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.info(
                    f"[投研总监] LLM 调用 (尝试 {attempt + 1}/{max_retries})"
                )
                start_t = time.time()
                result = deep_thinking_llm.invoke(messages_payload)
                elapsed = time.time() - start_t

                if hasattr(result, "content"):
                    rc = result.content
                    content = str(rc) if rc is not None else ""
                else:
                    content = str(result) if result is not None else ""

                if content and len(content) >= 50:
                    logger.info(
                        f"[投研总监] LLM 成功: {len(content)} 字符 ({elapsed:.1f}s)"
                    )
                    break
                else:
                    logger.warning(
                        f"[投研总监] LLM 内容过短: {len(content or '')} 字符"
                    )
                    content = None

            except Exception as e:
                elapsed = time.time() - start_t if "start_t" in dir() else 0
                logger.error(
                    f"[投研总监] LLM 失败 (尝试 {attempt + 1}): {e} ({elapsed:.1f}s)"
                )
                content = None

        # ---- Step 5: 解析 LLM 输出或 fallback ----
        if content:
            investment_memo: Any = {}
            research_brief = content
            try:
                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    llm_memo = parsed.get("投研备忘录")
                    if isinstance(llm_memo, dict):
                        investment_memo = llm_memo
                    llm_risk = parsed.get("风险评估卡")
                    risk_card = _merge_llm_risk_card(rule_risk_card, llm_risk)
                    llm_brief = parsed.get("research_brief")
                    if isinstance(llm_brief, str) and len(llm_brief) > 20:
                        research_brief = llm_brief
            except (json.JSONDecodeError, TypeError):
                logger.warning("[投研总监] LLM 输出非 JSON，使用 raw 文本")
                investment_memo = {}

            msg_out = AIMessage(content=research_brief)
        else:
            investment_memo = _build_fallback_memo(risk_assessment)
            research_brief = _build_fallback_research_brief(full_symbol, risk_assessment)
            msg_out = AIMessage(content="(系统降级)")
            logger.warning("[投研总监] 使用 fallback 输出")

        # ---- Step 6: SafetyOverride 纯规则二审（0 LLM） ----
        # 从 research_brief 提取方向/置信度，替代硬编码 hold/0.0
        llm_direction = _extract_research_direction(research_brief)
        llm_confidence = _extract_research_confidence(research_brief)
        custom_data = (
            (commodity_features or {}).get("custom_data", {}) or {}
        ) if isinstance(commodity_features, dict) else {}
        override = safety_override(
            risk_assessment,
            llm_direction,
            llm_confidence,
            research_brief,
            analyst_registry=analyst_registry,
            position_structured=state.get("position_structured", {}) or {},
            counter_signal_explanation="",
            custom_data_feature_dict=custom_data.get("feature_dict"),
        )

        investment_memo = _apply_override_to_memo(investment_memo, override)
        msg_out = AIMessage(content=research_brief)
        risk_card["safety_override"] = {
            **override,
            "max_position_pct": override["max_position"] * 100,
        }

        return {
            "investment_memo": investment_memo,
            "risk_card": risk_card,
            "risk_assessment": risk_assessment,
            "final_decision": research_brief,
            "research_brief": research_brief,
            "strategy_matrix": strategy_matrix,
            "messages": [msg_out],
            "cio_decision_timestamp": "now",
        }

    return investment_director_node
