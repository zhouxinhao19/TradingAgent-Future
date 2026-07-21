"""
strategy_fitness.py — 纯规则策略适应性评估器

输入: commodity_features (6 模块 features) + risk_assessment
输出: List[StrategyFitnessResult] — 5 类策略的标准化评估矩阵

原则: 0 LLM 调用，纯条件判断。输出可被 LLM 在 research_brief 中引用但不可被覆盖。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from tradingagents.utils.logging_init import get_logger

logger = get_logger("default")


def _extract_safe(obj: Any, *keys: str, default: Any = None) -> Any:
    """安全地沿着 key 链提取嵌套 dict 的值。"""
    for key in keys:
        if not isinstance(obj, dict):
            return default
        obj = obj.get(key, {})
    return obj if obj != {} else default


def _present(value: Any) -> bool:
    """判断值是否适合进入计算，保留 0/False。"""
    if value is None:
        return False
    if isinstance(value, float) and value != value:
        return False
    return value != ""


# =============================================================================
# 主入口
# =============================================================================

def evaluate_strategy_fitness(
    commodity_features: Dict[str, Any],
    risk_assessment: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """纯规则策略适应性评估。

    Args:
        commodity_features: features 层 6 模块输出
        risk_assessment: compute_risk_assessment() 返回值

    Returns:
        List[Dict], 每项 { strategy, fitness, rationale, key_conditions }。
        fitness 取值 "推荐关注" / "谨慎推荐" / "不推荐"。
    """
    dims = risk_assessment.get("dimensions", {}) if isinstance(risk_assessment, dict) else {}
    composite = risk_assessment.get("composite_risk_level", "UNKNOWN")
    flags = risk_assessment.get("flags", []) if isinstance(risk_assessment, dict) else []

    results: List[Dict[str, Any]] = []

    # ---- 1. 单边趋势（Directional） ----
    try:
        results.append(_eval_directional(commodity_features, dims, composite, flags))
    except Exception as e:  # noqa: BLE001
        logger.warning("[StrategyFitness] directional 异常: %s", e)
        results.append({"strategy": "单边趋势", "fitness": "数据不足", "rationale": "判断异常", "key_conditions": []})

    # ---- 2. 展期收益（Roll Yield Capture） ----
    try:
        results.append(_eval_roll_yield(commodity_features, dims))
    except Exception as e:  # noqa: BLE001
        logger.warning("[StrategyFitness] roll_yield 异常: %s", e)
        results.append({"strategy": "展期收益", "fitness": "数据不足", "rationale": "判断异常", "key_conditions": []})

    # ---- 3. 跨期套利（Calendar Spread） ----
    try:
        results.append(_eval_calendar_spread(commodity_features, dims))
    except Exception as e:  # noqa: BLE001
        logger.warning("[StrategyFitness] calendar_spread 异常: %s", e)
        results.append({"strategy": "跨期套利", "fitness": "数据不足", "rationale": "判断异常", "key_conditions": []})

    # ---- 4. 波动率策略（Volatility） ----
    try:
        results.append(_eval_volatility(commodity_features, dims))
    except Exception as e:  # noqa: BLE001
        logger.warning("[StrategyFitness] volatility 异常: %s", e)
        results.append({"strategy": "波动率", "fitness": "数据不足", "rationale": "判断异常", "key_conditions": []})

    # ---- 5. 跨品种套利（Intermarket） ----
    try:
        results.append(_eval_intermarket(commodity_features, dims))
    except Exception as e:  # noqa: BLE001
        logger.warning("[StrategyFitness] intermarket 异常: %s", e)
        results.append({"strategy": "跨品种", "fitness": "数据不足", "rationale": "判断异常", "key_conditions": []})

    return results


# =============================================================================
# 各策略评估函数
# =============================================================================

def _risk_level_int(level_val: Any) -> int:
    """统一将风险等级转为 int，UNKNOWN/None 返回 5。"""
    if isinstance(level_val, int):
        return level_val
    if isinstance(level_val, str) and level_val.startswith("R"):
        try:
            return int(level_val[1:])
        except (IndexError, ValueError):
            return 5
    return 5


def _get_level(dims: Dict[str, Any], key: str) -> int:
    d = dims.get(key, {})
    return d.get("level", 0) if isinstance(d, dict) else 0


def _flag_names(flags: List[Any]) -> set:
    names: set = set()
    for f in flags:
        if isinstance(f, dict) and f.get("name"):
            names.add(f["name"])
    return names


def _eval_directional(
    features: Dict[str, Any],
    dims: Dict[str, Any],
    composite: Any,
    flags: List[Any],
) -> Dict[str, Any]:
    """单边趋势策略适应性。"""
    tech = features.get("technical", {}) if isinstance(features, dict) else {}
    combined = tech.get("combined", {}) if isinstance(tech, dict) else {}
    vol = combined.get("volatility", {}) if isinstance(combined, dict) else {}

    atr_pctl = vol.get("atr_ratio_pctl180")
    vol_regime = vol.get("regime")
    oi_div = combined.get("oi_divergence")

    crowd_level = _get_level(dims, "crowding")
    composite_r = _risk_level_int(composite)
    flag_names = _flag_names(flags)

    conditions: List[str] = []

    has_trend = isinstance(atr_pctl, (int, float)) and atr_pctl > 60
    conditions.append(f"趋势强度(ATR pctl)={atr_pctl}{' ✓' if has_trend else ' ✗'}")

    oi_ok = oi_div == "confirm" if isinstance(oi_div, str) else False
    conditions.append(f"价仓关系={oi_div}{' ✓' if oi_ok else ' ✗'}")

    crowd_ok = crowd_level in (2, 3)
    conditions.append(f"拥挤度=R{crowd_level}{' ✓' if crowd_ok else ' ⚠️'}")

    risk_ok = composite_r <= 3
    conditions.append(f"综合风险=R{composite_r}{' ✓' if risk_ok else ' ✗'}")

    has_reversal = bool(flag_names & {"vol_crowding", "oi_trap", "multi_extreme"})
    if has_reversal:
        conditions.append("强反向信号=有 ✗")

    if risk_ok and crowd_ok and oi_ok and has_trend and not has_reversal:
        return {
            "strategy": "单边趋势",
            "fitness": "推荐关注",
            "rationale": f"趋势明确(ATR pctl={atr_pctl})，价仓共振确认，综合风险 R{composite_r} 可控",
            "key_conditions": conditions,
        }
    if composite_r <= 3 and crowd_level < 5 and oi_div != "conflict":
        return {
            "strategy": "单边趋势",
            "fitness": "谨慎推荐",
            "rationale": "趋势尚可但需注意风险信号："
            + ", ".join(c for c in conditions if "✗" in c or "⚠" in c),
            "key_conditions": conditions,
        }
    return {
        "strategy": "单边趋势",
        "fitness": "不推荐",
        "rationale": "风险信号过多："
        + ", ".join(c for c in conditions if "✗" in c or "⚠" in c),
        "key_conditions": conditions,
    }


def _eval_roll_yield(features: Dict[str, Any], dims: Dict[str, Any]) -> Dict[str, Any]:
    """展期收益策略适应性。"""
    ts = features.get("term_structure", {}) if isinstance(features, dict) else {}
    snap = ts.get("snapshot", {}) if isinstance(ts, dict) else {}

    carry_score = snap.get("carry_score")
    structure = snap.get("structure")
    conditions: List[str] = []

    has_structure = isinstance(structure, str) and structure
    conditions.append(f"结构={structure}{' ✓' if has_structure else ' ✗'}")

    carry_ok = isinstance(carry_score, (int, float)) and carry_score > 0.3
    carry_neutral = isinstance(carry_score, (int, float)) and carry_score > -0.3
    conditions.append(f"carry_score={carry_score}{' ✓' if carry_ok else ' ✗'}")

    # 用 carry_score 的绝对值判断展期深度
    if has_structure and "backwardation" in structure.lower():
        if carry_ok:
            return {
                "strategy": "展期收益",
                "fitness": "推荐关注",
                "rationale": f"Backwardation 结构(carry={carry_score})，多头展期收益为正，适合持有近月并滚动",
                "key_conditions": conditions,
            }
        if carry_neutral:
            return {
                "strategy": "展期收益",
                "fitness": "谨慎推荐",
                "rationale": f"Backwardation 结构但 carry_score={carry_score} 中性偏弱，展期收益有限",
                "key_conditions": conditions,
            }
    if has_structure and "contango" in structure.lower():
        carry_bad = isinstance(carry_score, (int, float)) and carry_score < -0.3
        if carry_bad:
            return {
                "strategy": "展期收益",
                "fitness": "不推荐",
                "rationale": f"深度 Contango(carry={carry_score})，多头每年承担较大展期亏损，不适合持有近月多头",
                "key_conditions": conditions,
            }
        return {
            "strategy": "展期收益",
            "fitness": "谨慎推荐",
            "rationale": f"Contango 结构但 carry_score={carry_score} 尚可接受，关注是否转为 Backwardation",
            "key_conditions": conditions,
        }
    return {
        "strategy": "展期收益",
        "fitness": "数据不足",
        "rationale": "期限结构数据不可用，无法判断",
        "key_conditions": conditions,
    }


def _eval_calendar_spread(
    features: Dict[str, Any],
    dims: Dict[str, Any],
) -> Dict[str, Any]:
    """跨期套利策略适应性。"""
    basis = features.get("basis", {}) if isinstance(features, dict) else {}
    latest = basis.get("latest", {}) if isinstance(basis, dict) else {}
    conditions: List[str] = []

    near_rate = latest.get("near_basis_rate")
    dom_rate = latest.get("dom_basis_rate")
    conditions.append(f"近月基差率={near_rate}")
    conditions.append(f"远月基差率={dom_rate}")

    if _present(near_rate) and _present(dom_rate):
        try:
            nr = float(near_rate)  # type: ignore[arg-type]
            dr = float(dom_rate)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return {
                "strategy": "跨期套利",
                "fitness": "数据不足",
                "rationale": "基差率数值异常",
                "key_conditions": conditions,
            }
        # 符号相反 = 强烈跨期信号
        if nr * dr < 0:
            return {
                "strategy": "跨期套利",
                "fitness": "推荐关注",
                "rationale": f"近远月基差方向背离（近月={nr:.3f} 远月={dr:.3f}），跨期价差有收敛/扩张的交易机会",
                "key_conditions": conditions,
            }
        # 差值过大
        if abs(nr - dr) > 0.03:
            return {
                "strategy": "跨期套利",
                "fitness": "谨慎推荐",
                "rationale": f"近远月基差分化明显（差={abs(nr - dr):.3f}），关注跨期价差套利机会",
                "key_conditions": conditions,
            }
        return {
            "strategy": "跨期套利",
            "fitness": "不推荐",
            "rationale": f"近远月基差方向一致（近月={nr:.3f} 远月={dr:.3f}），跨期价差无明显偏离",
            "key_conditions": conditions,
        }
    return {
        "strategy": "跨期套利",
        "fitness": "数据不足",
        "rationale": "基差数据不完整，无法判断跨期机会",
        "key_conditions": conditions,
    }


def _eval_volatility(
    features: Dict[str, Any],
    dims: Dict[str, Any],
) -> Dict[str, Any]:
    """波动率策略适应性（期权波动率交易参考）。"""
    tech = features.get("technical", {}) if isinstance(features, dict) else {}
    combined = tech.get("combined", {}) if isinstance(tech, dict) else {}
    vol = combined.get("volatility", {}) if isinstance(combined, dict) else {}
    conditions: List[str] = []

    vol_regime = vol.get("regime")
    atr_pctl = vol.get("atr_ratio_pctl180")
    conditions.append(f"volatility_regime={vol_regime}")
    conditions.append(f"atr_ratio_pctl180={atr_pctl}")

    # ADX 近似判断：无 ATR pctl 低 + 无趋势 = 震荡
    has_regime = isinstance(vol_regime, str) and vol_regime
    has_atr = isinstance(atr_pctl, (int, float))

    if not has_regime and not has_atr:
        return {
            "strategy": "波动率",
            "fitness": "数据不足",
            "rationale": "波动率数据不可用，无法评估期权策略",
            "key_conditions": conditions,
        }

    regime_low = has_regime and vol_regime.lower() == "low"
    regime_high = has_regime and vol_regime.lower() == "high"

    if regime_high and has_atr and atr_pctl < 60:  # 高波动+无趋势→卖出跨式
        return {
            "strategy": "波动率",
            "fitness": "谨慎推荐",
            "rationale": f"波动率处于高位(regime={vol_regime})但趋势不明(ATR pctl={atr_pctl})，"
                         "适合卖出跨式期权（卖波动率）",
            "key_conditions": conditions,
        }
    if regime_low:  # 低波动→买入跨式（赌突破）
        return {
            "strategy": "波动率",
            "fitness": "谨慎推荐",
            "rationale": f"波动率处于低位(regime={vol_regime})，适合买入跨式期权（买波动率）布局突破行情",
            "key_conditions": conditions,
        }
    return {
        "strategy": "波动率",
        "fitness": "不推荐",
        "rationale": "当前波动率无明显极端特征，无明确的期权波动率交易信号",
        "key_conditions": conditions,
    }


def _eval_intermarket(
    features: Dict[str, Any],
    dims: Dict[str, Any],
) -> Dict[str, Any]:
    """跨品种套利策略适应性（占位符实现）。"""
    conditions: list[str] = []

    # 当前仅通过品种分类做存在性判断
    # 通过 category 字段判断（未来可从 features 或外部配置获取）
    ns = features.get("news_sentiment", {}) if isinstance(features, dict) else {}
    conditions.append(f"新闻情感可用={'✓' if isinstance(ns, dict) and ns else '✗'}")

    # TODO: 未来版本通过 custom_data 上传上下游数据来增强判断
    # 当前占位符：默认返回"数据不足"但允许 LLM 引用
    return {
        "strategy": "跨品种",
        "fitness": "数据不足",
        "rationale": "暂无跨品种/上下游对比数据，无法评估产业链套利机会。"
                     "如上传相关品种数据（如铜+铜箔库存），可启用此评估。",
        "key_conditions": conditions,
    }
