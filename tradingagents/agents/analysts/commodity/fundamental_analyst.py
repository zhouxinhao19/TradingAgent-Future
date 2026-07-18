"""
fundamental_analyst.py — 商品期货产业分析师节点 (Phase 3b-ii → 估值+驱动 方法论)

聚合 features 层三个模块:
  - basis:基差(现货 - 期货主力)
  - inventory:库存(周/月变化 + 180d 分位)
  - term_structure:期限结构(contango/backwardation/flat + carry_score)

分析框架:永安期货"估值+驱动"方法论
  1. 估值维度:基差分位 + 期限结构类型 → 低估/合理/高估
  2. 驱动维度:库存边际变化 + carry_score → 向上/中性/向下
  3. 交叉验证:估值与驱动是否同向

输出:
  - state['fundamentals_report'] = Markdown 字符串(下游消费者兼容)
  - state['fundamentals_structured'] = 结构化估值+驱动 JSON dict

LLM 调用失败降级为规则直出报告。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import AIMessage

from tradingagents.utils.logging_init import get_logger

from ._base import (
    empty_report,
    extract_first_sentence,
    get_full_symbol,
    inject_analyst_id,
    load_features,
    make_analyst_id,
    make_conclusion_id,
    make_registry_entry,
    quality_gate,
    truncate_snapshot,
)

logger = get_logger("default")

FUNDAMENTAL_SYSTEM_PROMPT = """你是一位永安期货体系下的产业分析师,聚焦产业链研究,运用"估值+驱动"框架.

## 分析对象
- 标的代码:{full_symbol}
- 品种:{variety_name}
- 交易所:{exchange}
- 分析日期:{trade_date}

## 特征层原始数据

### 基差(用于估值判断)
- 最新近月基差率:{basis_latest}
- 主力基差率 180d 分位:{basis_zscore}
- 20d 斜率:{basis_slope}
- 信号:{basis_signals}

### 库存(用于驱动判断)
- 最新库存值:{inventory_latest}
- 周环比:{inventory_wow}
- 180d 分位:{inventory_zscore}
- 信号:{inventory_signals}

### 期限结构(辅助估值与驱动)
- 结构:{term_structure_type}
- Carry Score:{carry_score}
- 180d 分位:{term_zscore}
- 信号:{term_signals}

## 规则预判(估值+驱动框架)

### 估值维度
- 规则预判结果:**{valuation_position}**
- 安全边际判断:**{safety_margin}**

### 驱动维度
- 规则预判方向:**{drive_direction}**
- 驱动强度判断:**{drive_strength}**

### 一致性
- 估值与驱动一致性:**{consistency}**
  {conflict_note}

## 新闻摘要(跨分析师参考)
{news_summary}

## 分析要求(三段式)

### 第一步:估值分析
基于基差(贴水/升水程度)和期限结构(Backwardation/Contango/Flat),判断当前合约价格是否合理.
- 深度贴水+Backwardation → 低估,做多安全边际高
- 升水+Contango → 高估,做空性价比高
- 必须引用{valuation_position}和{safety_margin}做具体解读,引用具体的基差率和分位数

### 第二步:驱动分析
基于库存边际变化(WoW/MoM,180d 分位)和 Carry Score,判断产业驱动方向.
- 库存下降+Carry 正 → 驱动向上(供需收紧)
- 库存累积+Carry 负 → 驱动向下(供需宽松)
- 必须引用{drive_direction}和{drive_strength}做具体解读,指出当前最强的驱动因子

### 第三步:交叉验证
将估值与驱动结合,判断交易信号:
- 同向:估值和驱动指向同一方向 → 高置信度信号
- 强背离:估值与驱动方向冲突,且两边信号都极端 → 警惕趋势反转,高赔率机会
- 弱背离:估值与驱动方向冲突,但信号强度有限 → 降低置信度,等待确认
- 待定:至少一方为中性(信号模糊) → 低置信度,等待数据确认
{conflict_note}

## 强制证据规则
1. 所有数值引用必须与输入数据一致(基差率,分位数,WoW,Carry Score 等)
2. 缺失数据必须标注"数据不可得",禁止凭空编造
3. 不得引入输入数据中未提供的外部信息

## 输出格式(必须为合法 JSON)

```json
{{
  "valuation": {{
    "level": "低估|合理|高估",
    "safety_margin": "充足|一般|不足",
    "reasoning": "基于基差和期限结构数据的具体分析,必须引用输入数据中的具体数值"
  }},
  "drive": {{
    "direction": "向上|中性|向下",
    "strength": "强|中|弱",
    "dominant_factor": "一句话指出当前最强的驱动因子",
    "reasoning": "基于库存数据的具体分析,解释边际变化背后的供需含义"
  }},
  "consistency": {{
    "alignment": "同向|强背离|弱背离|待定",
    "confidence": "高|中|低",
    "analysis": "同向/背离/待定的具体逻辑分析",
    "key_uncertainty": "当前最大的不确定性来源"
  }},
  "summary": "150字内综合研判",
  "risk_flags": ["风险点1", "风险点2"],
  "data_quality": "数据范围说明"
}}
```

请严格按照上述 JSON 结构输出,不要包含其他文本."""


def _fmt(v: Any) -> str:
    """数值安全格式化。"""
    if v is None:
        return "N/A"
    if isinstance(v, float):
        if v != v:
            return "N/A"
        return f"{v:.4f}".rstrip("0").rstrip(".")
    return str(v)


def _format_signal_list(signals: Any) -> str:
    """把 list[str] 格式化为多行 markdown,非 list 转 str。"""
    if isinstance(signals, list):
        if not signals:
            return "- (无触发信号)"
        return "\n".join(f"- {s}" for s in signals[:8])
    if signals is None:
        return "- (无触发信号)"
    return f"- {signals}"


def _valuation_drive_assessment(
    basis_block: dict,
    inventory_block: dict,
    term_structure_block: dict,
) -> dict:
    """三因子 → 估值+驱动映射(纯规则,不调LLM)。

    Args:
        basis_block: features['basis'] dict
        inventory_block: features['inventory'] dict
        term_structure_block: features['term_structure'] dict

    Returns:
        {
            "valuation_position": "低估|合理|高估",
            "safety_margin": "充足|一般|不足",
            "drive_direction": "向上|中性|向下",
            "drive_strength": "强|中|弱",
            "consistency": "同向|背离",
            "conflict_note": str or None,
        }
    """
    # --- 估值维度:基差分位 + 期限结构类型 ---
    dom_pctl = None
    if isinstance(basis_block, dict):
        dom_pctl = (((basis_block.get("stats") or {}).get("zscore_180d") or {}).get("dom_basis_rate"))
    term_structure = None
    if isinstance(term_structure_block, dict):
        term_structure = (term_structure_block.get("snapshot") or {}).get("structure")

    if dom_pctl is not None and dom_pctl < 0.3 and term_structure == "backwardation":
        valuation_position = "低估"
    elif dom_pctl is not None and dom_pctl > 0.7 and term_structure == "contango":
        valuation_position = "高估"
    else:
        valuation_position = "合理"

    # 安全边际
    if dom_pctl is not None and dom_pctl < 0.1:
        safety_margin = "充足"
    elif dom_pctl is not None and dom_pctl > 0.9:
        safety_margin = "不足"
    else:
        safety_margin = "一般"

    # --- 驱动维度:库存 WoW + carry_score ---
    inv_wow = None
    carry = None
    jump = False
    if isinstance(inventory_block, dict):
        inv_wow = (inventory_block.get("snapshot") or {}).get("wow_change")
        jump = (inventory_block.get("snapshot") or {}).get("jump_flag", False)
    if isinstance(term_structure_block, dict):
        carry = (term_structure_block.get("snapshot") or {}).get("carry_score")

    if inv_wow is not None and inv_wow < 0 and carry is not None and carry > 0:
        drive_direction = "向上"
    elif inv_wow is not None and inv_wow > 0 and carry is not None and carry < 0:
        drive_direction = "向下"
    else:
        drive_direction = "中性"

    # 驱动强度
    score = abs((inv_wow if inv_wow is not None else 0) * 0.01) + abs((carry if carry is not None else 0) * 0.5)
    if jump or score > 0.05:
        drive_strength = "强"
    elif score > 0.02:
        drive_strength = "中"
    else:
        drive_strength = "弱"

    # --- 一致性(四态):同向/强背离/弱背离/待定 ---
    # 同向:估值与驱动指向同一方向 → 高置信度
    if (valuation_position == "低估" and drive_direction == "向上") or \
       (valuation_position == "高估" and drive_direction == "向下"):
        consistency = "同向"
        conflict_note = None

    # 背离:估值与驱动方向冲突 → 降低置信度
    #   强背离:安全边际极端 + 驱动强 → 两边都极端,冲突剧烈,警惕趋势反转
    #   弱背离:安全边际一般或驱动弱 → 冲突信号不尖锐,需等待确认
    elif (valuation_position == "低估" and drive_direction == "向下") or \
         (valuation_position == "高估" and drive_direction == "向上"):
        if safety_margin in ("充足", "不足") and drive_strength == "强":
            consistency = "强背离"
            conflict_note = (
                f"估值{valuation_position}(安全边际{safety_margin})但驱动{drive_direction}(强度{drive_strength}),"
                "方向冲突剧烈,基本面与技术面严重背离,需警惕趋势反转风险"
            )
        else:
            consistency = "弱背离"
            conflict_note = (
                f"估值{valuation_position}但驱动{drive_direction},方向存在一定冲突,"
                f"但信号强度有限(安全边际{safety_margin}/驱动强度{drive_strength}),"
                "建议等驱动信号更明确后再决策"
            )

    # 待定:至少一方为中性 → 信号模糊,需更多数据确认
    else:
        consistency = "待定"
        if valuation_position == "合理" and drive_direction == "中性":
            conflict_note = "估值合理且驱动中性,无明确方向性信号,建议观望或等库存/基差数据更新后重新判断"
        elif valuation_position == "合理":
            conflict_note = (
                f"估值合理,驱动{drive_direction}不够强,"
                "需确认驱动能否持续或估值是否会因驱动变化而调整"
            )
        else:
            conflict_note = (
                f"估值{valuation_position}但驱动中性(数据不足或信号模糊),"
                "需补充库存/Carry数据后再确认驱动方向"
            )

    return {
        "valuation_position": valuation_position,
        "safety_margin": safety_margin,
        "drive_direction": drive_direction,
        "drive_strength": drive_strength,
        "consistency": consistency,
        "conflict_note": conflict_note,
    }


def _structured_to_markdown(parsed: dict) -> str:
    """将结构化 JSON 转为 Markdown,供前端渲染和下游 prompt 注入。"""
    val = parsed.get("valuation", {})
    drv = parsed.get("drive", {})
    cns = parsed.get("consistency", {})
    summary = parsed.get("summary", "")
    risk_flags = parsed.get("risk_flags", [])
    data_quality = parsed.get("data_quality", "")

    md = f"# 永安期货估值+驱动分析\n\n"
    md += f"## 综合判断\n{summary}\n\n"
    md += f"- **估值**:{val.get('level','N/A')} | 安全边际:{val.get('safety_margin','N/A')}\n"
    md += f"- **驱动**:{drv.get('direction','N/A')}({drv.get('strength','N/A')}) | 主导因子:{drv.get('dominant_factor','N/A')}\n"
    md += f"- **一致性**:{cns.get('alignment','N/A')} | 置信度:{cns.get('confidence','N/A')}\n\n"
    md += f"## 估值分析\n{val.get('reasoning','')}\n\n"
    md += f"## 驱动分析\n{drv.get('reasoning','')}\n\n"
    md += f"## 交叉验证\n{cns.get('analysis','')}\n"
    if cns.get("key_uncertainty"):
        md += f"\n**关键不确定性**:{cns['key_uncertainty']}\n"
    md += "\n## 风险提示\n"
    if risk_flags:
        for flag in risk_flags:
            md += f"- {flag}\n"
    else:
        md += "- (无特定风险提示)\n"
    md += f"\n## 数据质量\n{data_quality}\n"
    return md


def _build_fallback_structured(assessment: dict) -> str:
    """LLM 失败时,用规则评估结果拼 Markdown(降级版本)。"""
    md = (
        f"# 永安期货估值+驱动分析(降级版本 — LLM 不可用)\n\n"
        f"## 综合判断\n估值{assessment['valuation_position']} / 驱动{assessment['drive_direction']} / "
        f"一致性{assessment['consistency']}\n\n"
        f"## 估值维度\n- 估值位置:{assessment['valuation_position']}\n"
        f"- 安全边际:{assessment['safety_margin']}\n\n"
        f"## 驱动维度\n- 方向:{assessment['drive_direction']}\n"
        f"- 强度:{assessment['drive_strength']}\n\n"
        f"## 一致性判断\n{assessment['consistency']}\n"
    )
    if assessment.get("conflict_note"):
        md += f"\n{assessment['conflict_note']}\n"
    md += "\n---\n_LLM 故障恢复后请重新提交任务以获得完整分析。_\n"
    return md


def create_fundamental_analyst(llm):
    """产业分析师工厂函数。"""

    def fundamental_analyst_node(state: dict) -> dict:
        full_symbol = get_full_symbol(state)
        trade_date = state.get("trade_date", "")

        logger.info(f"💼 [产业分析师] 启动: {full_symbol} @ {trade_date}")

        features = load_features(state)

        basis_block = features.get("basis")
        inventory_block = features.get("inventory")
        term_block = features.get("term_structure")

        # --- 降级 1:三个模块全部缺失 ---
        if not any(isinstance(b, dict) for b in [basis_block, inventory_block, term_block]):
            reason = "基差/库存/期限结构三因子 features 全部缺失"
            report_md = empty_report("neutral", reason)
            analyst_id = make_analyst_id("FUND", full_symbol, trade_date, seed="empty")
            conclusion_id = make_conclusion_id("FUND", 1)
            tagged_report = inject_analyst_id(report_md, analyst_id)
            registry_entry = make_registry_entry(analyst_id, conclusion_id, "FUND", "fundamental", "fundamentals_report", "neutral", "(数据缺失: 跳过)")
            return {
                "fundamentals_report": tagged_report,
                "fundamentals_structured": {},
                "messages": [],
                "fundamentals_tool_call_count": 0,
                "analyst_registry": registry_entry,
            }

        # --- 数据稀疏判断(三个模块加起来 rows < 30) ---
        total_rows = sum(
            int((b or {}).get("quality", {}).get("rows", 0) or 0)
            for b in [basis_block, inventory_block, term_block]
            if isinstance(b, dict)
        )
        if total_rows < 30:
            reason = f"三因子数据稀疏(total_rows={total_rows} < 30)"
            report_md = empty_report("neutral", reason)
            analyst_id = make_analyst_id("FUND", full_symbol, trade_date, seed="sparse")
            conclusion_id = make_conclusion_id("FUND", 1)
            tagged_report = inject_analyst_id(report_md, analyst_id)
            registry_entry = make_registry_entry(analyst_id, conclusion_id, "FUND", "fundamental", "fundamentals_report", "neutral", "(数据稀疏: 跳过)")
            return {
                "fundamentals_report": tagged_report,
                "fundamentals_structured": {},
                "messages": [],
                "fundamentals_tool_call_count": 0,
                "analyst_registry": registry_entry,
            }

        # --- 估值+驱动评估(纯规则) ---
        assessment = _valuation_drive_assessment(basis_block or {}, inventory_block or {}, term_block or {})

        # --- 准备 prompt 变量 ---
        basis_signals = (basis_block or {}).get("signals", []) if isinstance(basis_block, dict) else []
        inventory_signals = (inventory_block or {}).get("signals", []) if isinstance(inventory_block, dict) else []
        term_signals = (term_block or {}).get("signals", []) if isinstance(term_block, dict) else []

        # 取 quality(任一模块)
        quality_rows = (
            (basis_block or inventory_block or term_block or {}).get("quality", {}).get("rows", 0)
        )

        basis_latest = _fmt(((basis_block or {}).get("latest") or {}).get("dom_basis_rate"))
        basis_zscore = _fmt((((basis_block or {}).get("stats") or {}).get("zscore_180d") or {}).get("dom_basis_rate"))
        basis_slope = _fmt((((basis_block or {}).get("stats") or {}).get("slope_20d") or {}).get("dom_basis_rate"))

        inv_latest = _fmt(((inventory_block or {}).get("latest") or {}).get("value"))
        inv_wow = _fmt(((inventory_block or {}).get("snapshot") or {}).get("wow_change"))
        inv_zscore = _fmt(((inventory_block or {}).get("stats") or {}).get("zscore_180d"))

        term_type = ((term_block or {}).get("snapshot") or {}).get("structure", "N/A")
        carry_score = _fmt(((term_block or {}).get("snapshot") or {}).get("carry_score"))
        term_zscore = _fmt(((term_block or {}).get("stats") or {}).get("zscore_180d"))

        variety_name = state.get("variety_name", full_symbol)
        exchange = state.get("exchange", "")

        prompt_vars = dict(
            full_symbol=full_symbol,
            variety_name=variety_name,
            exchange=exchange,
            trade_date=trade_date,
            basis_latest=basis_latest,
            basis_zscore=basis_zscore,
            basis_slope=basis_slope,
            basis_signals=_format_signal_list(basis_signals),
            inventory_latest=inv_latest,
            inventory_wow=inv_wow,
            inventory_zscore=inv_zscore,
            inventory_signals=_format_signal_list(inventory_signals),
            term_structure_type=term_type,
            carry_score=carry_score,
            term_zscore=term_zscore,
            term_signals=_format_signal_list(term_signals),
            # 估值+驱动新增字段
            valuation_position=assessment["valuation_position"],
            safety_margin=assessment["safety_margin"],
            drive_direction=assessment["drive_direction"],
            drive_strength=assessment["drive_strength"],
            consistency=assessment["consistency"],
            conflict_note=assessment.get("conflict_note", "无"),
            quality_rows=quality_rows,
            quality_coverage=_fmt((basis_block or {}).get("quality", {}).get("coverage")),
            news_summary=state.get("news_summary", ""),
        )

        # --- 主路径:LLM 调用 ---
        try:
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", FUNDAMENTAL_SYSTEM_PROMPT),
                    MessagesPlaceholder(variable_name="messages"),
                ]
            ).partial(**prompt_vars)

            messages_payload = prompt.format_messages(
                messages=state.get("messages", []) or []
            )

            logger.info(f"💼 [产业分析师] 调用 LLM,full_symbol={full_symbol}")
            result = llm.invoke(messages_payload)

            if hasattr(result, "content"):
                content = result.content
                if not isinstance(content, str):
                    content = str(content) if content is not None else ""
            else:
                content = str(result) if result is not None else ""

            # 解析 LLM 返回的 JSON
            try:
                # 尝试从 Markdown 代码块或纯 JSON 中提取
                cleaned = content.strip()
                if cleaned.startswith("```"):
                    lines = cleaned.splitlines()
                    # 去掉首尾 ```json 和 ``` 行
                    start = 1 if lines[0].strip().startswith("```") else 0
                    end = -1 if lines[-1].strip() == "```" else len(lines)
                    cleaned = "\n".join(lines[start:end])
                parsed = json.loads(cleaned)
                structured_report = parsed
                report_md = _structured_to_markdown(parsed)
            except (json.JSONDecodeError, Exception) as parse_err:
                logger.warning(f"💼 [产业分析师] JSON 解析失败,回退原始内容: {parse_err}")
                structured_report = {"raw": content, "parse_error": str(parse_err)}
                report_md = content

            logger.info(f"✅ [产业分析师] 报告生成: {len(report_md)} 字符")

            msg_out = result if hasattr(result, "content") else AIMessage(content=report_md)
            direction = assessment.get("drive_direction", "neutral") or "neutral"
            analyst_id = make_analyst_id("FUND", full_symbol, trade_date)
            conclusion_id = make_conclusion_id("FUND", 1)
            tagged_report = inject_analyst_id(report_md, analyst_id)
            registry_entry = make_registry_entry(analyst_id, conclusion_id, "FUND", "fundamental", "fundamentals_report", direction, extract_first_sentence(report_md))
            return {
                "fundamentals_report": tagged_report,
                "fundamentals_structured": structured_report,
                "messages": [msg_out],
                "fundamentals_tool_call_count": 0,
                "analyst_registry": registry_entry,
            }

        except Exception as e:
            logger.error(f"❌ [产业分析师] LLM 调用失败: {e}")
            try:
                fallback_md = _build_fallback_structured(assessment)
            except Exception as inner_e:
                logger.error(f"❌ [产业分析师] fallback 也失败: {inner_e}")
                fallback_md = empty_report("neutral", f"LLM 失败且 fallback 异常: {inner_e}")

            fallback_direction = assessment.get("drive_direction", "neutral") or "neutral"
            analyst_id = make_analyst_id("FUND", full_symbol, trade_date, seed="fallback")
            conclusion_id = make_conclusion_id("FUND", 1)
            tagged_report = inject_analyst_id(fallback_md, analyst_id)
            registry_entry = make_registry_entry(analyst_id, conclusion_id, "FUND", "fundamental", "fundamentals_report", fallback_direction, "(降级: LLM 不可用)")
            return {
                "fundamentals_report": tagged_report,
                "fundamentals_structured": {
                    "valuation": {"level": assessment["valuation_position"], "safety_margin": assessment["safety_margin"]},
                    "drive": {"direction": assessment["drive_direction"], "strength": assessment["drive_strength"]},
                    "consistency": {"alignment": assessment["consistency"]},
                    "summary": f"降级输出:估值{assessment['valuation_position']},驱动{assessment['drive_direction']}",
                    "risk_flags": [],
                    "data_quality": f"降级模式(LLM不可用),条数={total_rows}",
                },
                "messages": [],
                "fundamentals_tool_call_count": 0,
                "analyst_registry": registry_entry,
            }

    return fundamental_analyst_node


__all__ = ["create_fundamental_analyst"]
