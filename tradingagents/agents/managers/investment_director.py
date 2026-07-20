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
import time
from typing import Any, Dict, Optional

from tradingagents.utils.logging_init import get_logger

from tradingagents.agents.analysts.commodity import build_custom_data_context

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

    # 3. 持仓拥挤度
    crowding = _extract_safe(
        commodity_features, "positioning", "snapshot", "crowding_pctl_180d"
    )
    if isinstance(crowding, (int, float)) and data_quality["positioning"]["available"]:
        crowd_level = _rate_percentile(float(crowding), [
            (20, 1),
            (50, 2),
            (80, 3),
            (95, 4),
        ])
        dimensions["crowding"] = {
            "value": float(crowding),
            "level": crowd_level,
            "tier": RISK_LEVEL_LABELS[crowd_level],
            "source": "positioning.snapshot.crowding_pctl_180d",
            "interpretation": {
                1: "持仓冷清，市场关注度低",
                2: "持仓正常，多空相对均衡",
                3: "持仓略拥挤，需关注反转风险",
                4: "持仓拥挤，反转概率显著升高",
                5: "持仓极度拥挤，警惕踩踏风险",
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
            "source": "news_sentiment.snapshot.sentiment.ratio",
        }
    else:
        dimensions["news_sentiment"] = {"available": False}

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
) -> Dict[str, Any]:
    """纯规则风控硬约束二审。

    在 LLM 输出之后强制执行，不可协商。

    Args:
        risk_assessment: compute_risk_assessment() 的返回值
        llm_direction: LLM 输出的方向 ("long"/"short"/"hold"/"flat")
        llm_confidence: LLM 输出的置信度 (0-1)
        llm_raw: LLM 原始输出文本

    Returns:
        dict: {
            "action": 覆盖后的最终方向,
            "confidence": 覆盖后的置信度,
            "max_position": 仓位上限(0-1，0=禁止开仓),
            "overridden": bool,
            "override_reason": str,  # 人类可读的覆盖原因
            "override_rules_triggered": List[str],
        }
    """
    composite = risk_assessment.get("composite_risk_level", "UNKNOWN")
    flags = risk_assessment.get("flags", [])
    dimensions = risk_assessment.get("dimensions", {})
    data_insufficient = risk_assessment.get("data_insufficient", False)

    # ---- 检测触发规则 ----
    triggered: list[str] = []
    max_position = 1.0  # 仓位上限 0-1
    action = llm_direction
    confidence = llm_confidence

    # --- 强制规则（不可协商） ---

    # R5 极端风险 → 拒绝开仓
    if composite == 5 or composite == "R5":
        triggered.append("R5_REJECT")
        action = "hold"
        confidence = 0.0
        max_position = 0.0

    # R4 + 至少一个 high 级 flag → 仓位上限减半
    if composite == 4 and any(f.get("severity") == "high" for f in flags):
        triggered.append("R4_FLAG_HALF_POSITION")

    # R4 但无 high flag → 警告但允许
    if composite == 4 and not any(f.get("severity") in ("high", "critical") for f in flags):
        triggered.append("R4_WARN_ONLY")

    # 数据不足 → 禁止激进方向
    if data_insufficient:
        triggered.append("DATA_INSUFFICIENT")
        if action in ("long", "short"):
            action = "hold"
            confidence = min(confidence, 0.2)
            max_position = min(max_position, 0.3)

    # near_delivery flag → 仅观望
    if any(f.get("name") == "near_delivery" for f in flags):
        triggered.append("NEAR_DELIVERY_REJECT")
        action = "hold"
        confidence = 0.0
        max_position = 0.0

    # R4 且 R1(波动率)也高 → 仓位上限减半 (与 LLM 方向无关)
    vol_level = dimensions.get("volatility", {}).get("level", 0)
    if isinstance(vol_level, int) and vol_level >= 4 and composite >= 4:
        if "R4_FLAG_HALF_POSITION" not in triggered:
            triggered.append("R4_PLUS_HIGH_VOL")
        max_position = min(max_position, 0.5)

    # --- 最终 verdict ---
    overridden = len(triggered) > 0 and action != llm_direction

    # 构造人类可读的覆盖原因
    if overridden:
        rule_descriptions = {
            "R5_REJECT": "综合风险等级 R5（极端风险），触发强制拒绝开仓规则",
            "R4_FLAG_HALF_POSITION": "综合风险等级 R4 + 高风险标志，仓位上限减半",
            "R4_WARN_ONLY": "综合风险等级 R4，仅警告仍按 LLM 决策",
            "DATA_INSUFFICIENT": "数据不足，禁止激进方向交易，仓位上限降至 30%",
            "NEAR_DELIVERY_REJECT": "合约临近交割（<10天），仅观望禁止开仓",
            "R4_PLUS_HIGH_VOL": "波动率维度 R4+ 且综合风险 R4+，仓位上限减半",
        }
        reasons = [rule_descriptions.get(r, r) for r in triggered if r != "R4_WARN_ONLY"]
        override_reason = "；".join(reasons) if reasons else "触发风控规则，覆盖 LLM 决策"
    else:
        override_reason = ""

    return {
        "action": action,
        "confidence": confidence,
        "max_position": max_position,
        "overridden": overridden,
        "override_reason": override_reason,
        "override_rules_triggered": triggered,
    }


# =============================================================================
# 投研总监 LLM Prompt（使用 LangChain .partial() 替换变量）
# =============================================================================

INVESTMENT_DIRECTOR_SYSTEM_PROMPT = """你是大宗商品期货的**投研总监**。

你的职责是综合**推理分析师（L2）的研究报告**和**量化风险评估**，形成最终投资决策。

---

## 输入材料

### 1. 推理分析师报告（L2）
{investment_plan}

推理分析师的 investment_plan 是三模块结构化 JSON：
- 估值驱动矩阵：按维度（基差/库存/期限结构/持仓/技术面/新闻）的状态/判断/驱动
- 多空对照表：看涨/看跌核心逻辑、证据强度、关键分歧
- 三种情景推演：保守/基准/乐观，含触发条件和置信度

### 2. 量化风险评估
{risk_assessment_json}

纯规则引擎输出（0 LLM），包括：
- 维度风险矩阵：6 维度 R1-R5 等级
- 硬拦截标志：跨维度交叉风险
- 数据质量：各模块数据可用性

### 3. L1 分析师注册表
{analyst_registry_summary}

### 4. 标的信息
- 合约: {full_symbol}
- 品种: {variety_name}
- 交易所: {exchange}
- 报价单位: {quote_unit}
- 交易日期: {trade_date}

### 5. 用户上传数据参考
{custom_data_context}

---

## 输出要求

输出可直接被 json.loads() 解析的 JSON（不要额外 markdown 包裹）。

### 顶层结构

你必须输出包含以下三个顶级 key 的 JSON：

1. **投研备忘录** (dict) — 对 L2 报告的审核与裁决
2. **风险评估卡** (dict) — 综合量化 + 定性风险评估
3. **final_decision_markdown** (str) — 兼容现有决策解析格式的 Markdown

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
  - "方向倾向": "做多/做空/持有"
  - "置信度": 0.0-1.0 之间的数值
  - "核心逻辑": "1-2 句话"
  - "反向信号": ["信号1", "信号2"]

### key 2: 风险评估卡 的详细结构

⚠️ 量化风险矩阵由系统纯规则唯一产出，LLM 不需要重新输出。
LLM 仅负责以下定性维度：

- 三方视角 (dict):
	- 三方视角 (dict):
	  - "激进": {{"概率权重": 0.3, "条件": "..."}}
	  - "保守": {{"概率权重": 0.2, "条件": "..."}}
	  - "中性": {{"概率权重": 0.5, "条件": "..."}}

- 风险裁定 (dict):
  - "建议动作": "开仓" | "观望" | "减仓" | "平仓"
  - "仓位上限": "账户30%"
  - "杠杆上限": "3倍"

- 风险提示 (list): 2-3 条主要风险

### key 3: final_decision_markdown

必须包含以下 Markdown 字段（兼容现有 _extract_decision() 解析）：

- **方向**: 做多/做空/持有/平仓
- **置信度**: 0.75（数值）
- 可选：合约、入场、止损、目标、持仓、持有周期、风险敞口

---

## 严格约束

1. 估值审核各维度必须用"同意"或"修正"开头，引用证据 ID（REF-TECH-xxx 格式）
2. 情景裁决必须给出排除理由，不能只写选定不写排除
3. 建议动作必须是"开仓"|"观望"|"减仓"|"平仓"之一，仓位上限仅在"开仓"时给出
4. final_decision_markdown 必须包含 **方向** 和 **置信度** 字段
5. 【硬约束】输出纯 JSON，禁止使用 ```json 代码块包裹，否则解析失败将视为系统降级。直接以 `{{` 开头，`}}` 结尾
6. 全文中文
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
    return {
        "估值审核": (
            "（LLM 不可用，量化检查器已完成维度评级，详见风险评估卡）"
        ),
        "情景裁决": "（LLM 不可用，无法裁决）",
        "投研结论": {
            "方向倾向": "持有",
            "置信度": 0.0,
            "核心逻辑": f"系统降级：LLM 不可用，量化风险等级 {composite}，默认持有",
            "反向信号": [f"系统降级：量化风险 {composite}"],
        },
    }


def _build_fallback_decision(full_symbol: str, risk_assessment: Dict[str, Any]) -> str:
    """LLM 不可用时的 fallback 决策 markdown。"""
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
        f"# {full_symbol} 投研总监决策（系统降级）\n\n"
        f"## 决策摘要\n"
        f"- **方向**:持有\n"
        f"- **合约**:—\n"
        f"- **入场**:—\n"
        f"- **止损**:—\n"
        f"- **目标**:—\n"
        f"- **持仓**:0 手\n"
        f"- **持有周期**:—\n"
        f"- **置信度**:0.00\n"
        f"- **风险敞口**:0%\n\n"
        f"## 决策理由\n"
        f"系统降级：LLM 不可用，量化风险等级 {risk_label}。"
        f"基于风险控制原则默认持有不建仓。\n"
        f"{flag_section}\n"
        f"## 风险提示\n"
        f"1. 系统降级状态，所有决策参考价值有限\n"
        f"2. 量化风险等级仅供参考\n"
        f"3. 建议等待 LLM 服务恢复后重新生成完整决策\n"
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
        risk_card = _build_risk_card(risk_assessment)

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
            final_decision = content
            try:
                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    llm_memo = parsed.get("投研备忘录")
                    if isinstance(llm_memo, dict):
                        investment_memo = llm_memo
                    llm_risk = parsed.get("风险评估卡")
                    if isinstance(llm_risk, dict):
                        risk_card = llm_risk
                    llm_fd = parsed.get("final_decision_markdown")
                    if isinstance(llm_fd, str) and len(llm_fd) > 20:
                        final_decision = llm_fd
            except (json.JSONDecodeError, TypeError):
                logger.warning("[投研总监] LLM 输出非 JSON，使用 raw 文本")
                investment_memo = {}

            msg_out = AIMessage(content=final_decision)
        else:
            investment_memo = _build_fallback_memo(risk_assessment)
            final_decision = _build_fallback_decision(full_symbol, risk_assessment)
            msg_out = AIMessage(content="(系统降级)")
            logger.warning("[投研总监] 使用 fallback 输出")

        # ---- Step 6: SafetyOverride 纯规则二审（0 LLM） ----
        # 提取 LLM 输出的方向用于二审
        _llm_dir = "hold"
        _llm_conf = 0.0
        _raw_text = final_decision or ""
        import re as _re
        _dm = _re.search(r'[*]{0,2}方向[*]{0,2}\s*[:：]\s*(做多|做空|买入|卖出|持有|平仓)', _raw_text)
        if _dm:
            _raw_dir = _dm.group(1)
            if _raw_dir in ("做多", "买入"): _llm_dir = "long"
            elif _raw_dir in ("做空", "卖出"): _llm_dir = "short"
            elif _raw_dir == "平仓": _llm_dir = "flat"
            elif _raw_dir == "持有": _llm_dir = "hold"
        _cm = _re.search(r'[*]{0,2}置信度[*]{0,2}\s*[:：]\s*([0-9]+\.?[0-9]*)', _raw_text)
        if _cm:
            try:
                _parsed = float(_cm.group(1))
                if 0.0 <= _parsed <= 1.0: _llm_conf = _parsed
            except ValueError: pass

        _override = safety_override(risk_assessment, _llm_dir, _llm_conf, _raw_text)

        if _override["overridden"]:
            logger.warning(
                f"[投研总监] SafetyOverride 触发: {_override['override_reason']}"
            )
            # 如果方向被覆盖，修改 final_decision
            if _override["action"] != _llm_dir:
                new_dir_map = {"long": "做多", "short": "做空", "hold": "持有", "flat": "平仓"}
                new_dir_cn = new_dir_map.get(_override["action"], "持有")
                _raw_text_new = _raw_text
                if _dm:
                    _raw_text_new = _raw_text[:_dm.start()] + f"**方向**:{new_dir_cn}" + _raw_text[_dm.end():]
                if _override["confidence"] != _llm_conf:
                    _raw_text_new = _raw_text_new.replace(f"**置信度**:{_llm_conf}", f"**置信度**:{_override['confidence']}")
                final_decision = _raw_text_new
                msg_out = AIMessage(content=final_decision)

            # 注入 override_info 到 risk_card
            risk_card["safety_override"] = {
                "overridden": True,
                "override_reason": _override["override_reason"],
                "override_rules_triggered": _override["override_rules_triggered"],
                "original_llm_direction": _llm_dir,
                "overridden_action": _override["action"],
                "max_position_pct": _override["max_position"] * 100,
            }

        return {
            "investment_memo": investment_memo,
            "risk_card": risk_card,
            "risk_assessment": risk_assessment,
            "final_decision": final_decision,
            "messages": [msg_out],
            "cio_decision_timestamp": "now",
        }

    return investment_director_node
