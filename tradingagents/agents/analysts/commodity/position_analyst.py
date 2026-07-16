"""
position_analyst.py — 商品期货持仓分析师节点 (Phase 3b-ii + 增强版)

输入:state['commodity_features']['positioning'] (含多空双边/多空比/连续变化/价格对齐)
输出:state['sentiment_report'] / state['position_report'] / state['position_structured']

持仓分析关注:
  - 多头 vs 空头行为分离(主动加仓 vs 减仓)
  - 多空比(L/S ratio)变化
  - 连续净多变化天数(趋势持续性)
  - 前 20 名净多头 5 日变化(主力加减仓)
  - 持仓集中度(前 5 名占比)
  - 拥挤度 180d 分位(>0.9 视为极端反向风险)
  - 价格-持仓交叉验证(同向/背离)

输出字段名:
  - sentiment_report (旧字段,保持兼容)
  - position_report (新字段,Markdown)
  - position_structured (新字段,结构化 JSON dict)

LLM 调用失败降级为 features 直拼 Markdown + JSON。
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import AIMessage

from tradingagents.utils.logging_init import get_logger

from ._base import (
    empty_report,
    get_full_symbol,
    load_features,
    quality_gate,
)

logger = get_logger("default")

POSITION_SYSTEM_PROMPT = """你是一位资深的期货持仓分析师,解读主力席位持仓变化与拥挤度信号。

## 分析对象
- 标的代码:{full_symbol}
- 品种:{variety_name}
- 交易所:{exchange}
- 分析日期:{trade_date}
- 持仓数据来源:{contract_source}
## 特征层(已计算,直接消费)

### 多头持仓
- 前 20 名多头 5 日变化:{long_change_5d}

### 空头持仓
- 前 20 名空头 5 日变化:{short_change_5d}

### 净多与多空比
- 净多 5 日变化:{net_long_change_5d}
- 多空比(L/S):{long_short_ratio}
- 多空比 5 日变化:{lsr_change_5d}
- 连续净多变化天数:{consecutive_days}
- 20d 净多斜率:{slope_20d}

### 集中度与拥挤度
- 前 20 集中度:{concentration}
- 拥挤度 180d 分位:{crowding_pctl}

### 价格交叉验证
- 日线价格方向:{price_direction}
- 价格-持仓对齐:{price_position_alignment}

### 触发信号
{signals}

### 数据质量
- 数据条数:{quality_rows}

---

## 分析要求

1. **多头 vs 空头行为分离**:区分"多头主动加仓"vs"空头减仓"(两者对价格含义不同);
   "空头主动加仓"vs"多头减仓"(空头主动加仓更熊)
2. **净多趋势持续性**:连续变化天数 + 20d 斜率 → 判断是短期波动还是趋势性变化
3. **多空比**:L/S 比值变化是判断多空力量转换的关键指标,急剧变化预示趋势加速或反转
4. **集中度与拥挤度**:前 5 占比 > 60% 视为高集中;180d 分位 > 0.9 时持仓过度拥挤,
   反向风险加大;0.8~0.9 警惕但不极端
5. **价格-持仓交叉验证**:同向确认趋势,背离预警趋势可能逆转
6. **风险提示**:数据稀疏或信号矛盾时,降低 confidence 并明确标注

## 输出格式(必须为合法 JSON)

```json
{{
  "direction": {{
    "value": "long|short|neutral",
    "confidence": 0.0-1.0,
    "drivers": ["最大驱动因子1", "驱动因子2"]
  }},
  "long_side": {{
    "trend": "加仓|减仓|平稳",
    "change_5d": 数值或"null",
    "interpretation": "多头行为解读"
  }},
  "short_side": {{
    "trend": "加仓|减仓|平稳",
    "change_5d": 数值或"null",
    "interpretation": "空头行为解读"
  }},
  "concentration": {{
    "level": "高|中|低",
    "crowding_status": "拥挤|正常|冷清",
    "reversal_risk": true或false,
    "analysis": "集中度与拥挤度解读"
  }},
  "cross_validation": {{
    "alignment": "同向看多|同向看空|背离价涨仓减|背离价跌仓增|待定",
    "price_trend": "上涨|下跌|震荡|N/A",
    "position_trend": "净多增加|净多减少|平稳",
    "analysis": "价格-持仓交叉验证分析"
  }},
  "summary": "150字内综合研判",
  "risk_flags": ["风险点1", "风险点2"],
  "data_quality": "数据范围说明"
}}
```

请严格按照上述 JSON 结构输出,不要包含其他文本。"""


def _fmt(v: Any) -> str:
    if v is None:
        return "N/A"
    if isinstance(v, float):
        if v != v:
            return "N/A"
        return f"{v:.4f}".rstrip("0").rstrip(".")
    return str(v)


def _format_signals(signals: Any) -> str:
    if isinstance(signals, list):
        if not signals:
            return "- (无触发信号)"
        return "\n".join(f"- {s}" for s in signals[:8])
    return f"- {signals}" if signals else "- (无触发信号)"


def _derive_direction(
    net_long_change_5d: float,
    crowding_pctl: float,
    signals: list,
) -> str:
    """从持仓指标推导方向。"""
    bull = any(("净多增加" in s or "主力加多" in s or "净多头加仓" in s) for s in signals)
    bear = any(("净多减少" in s or "主力减多" in s or "空头加仓" in s) for s in signals)
    if net_long_change_5d is not None:
        if net_long_change_5d > 0.05:
            bull = True
        elif net_long_change_5d < -0.05:
            bear = True
    if crowding_pctl is not None and crowding_pctl > 0.9:
        if bull:
            return "看多(注意拥挤反向风险)"
        if bear:
            return "看空(注意拥挤反向风险)"
    if bull and not bear:
        return "看多"
    if bear and not bull:
        return "看空"
    return "中性"


def _structured_to_markdown(parsed: dict) -> str:
    """将结构化 JSON 转为 Markdown,供前端渲染和下游 prompt 注入。"""
    direction = parsed.get("direction", {}) or {}
    long_side = parsed.get("long_side", {}) or {}
    short_side = parsed.get("short_side", {}) or {}
    concentration = parsed.get("concentration", {}) or {}
    cross = parsed.get("cross_validation", {}) or {}
    summary = parsed.get("summary", "")
    risk_flags = parsed.get("risk_flags", [])
    data_quality = parsed.get("data_quality", "")

    md = f"# {direction.get('value','N/A')} | 持仓分析报告\n\n"
    md += f"## 综合判断\n{summary}\n\n"
    md += f"- **方向**:{direction.get('value','N/A')}(置信度{direction.get('confidence','N/A')})\n"

    md += f"- **多头行为**:{long_side.get('trend','N/A')}(变化:{_fmt(long_side.get('change_5d'))})\n"
    if long_side.get("interpretation"):
        md += f"  - {long_side.get('interpretation','')}\n"

    md += f"- **空头行为**:{short_side.get('trend','N/A')}(变化:{_fmt(short_side.get('change_5d'))})\n"
    if short_side.get("interpretation"):
        md += f"  - {short_side.get('interpretation','')}\n"

    md += f"- **集中度**:{concentration.get('level','N/A')} | 拥挤度:{concentration.get('crowding_status','N/A')}\n"
    if concentration.get("reversal_risk"):
        md += "- **⚠️ 拥挤反转风险**:需警惕\n"

    md += "## 价格-持仓交叉验证\n"
    md += f"- 对齐状态:{cross.get('alignment','N/A')}\n"
    md += f"- {cross.get('analysis','')}\n\n"

    md += "## 风险提示\n"
    if risk_flags:
        for flag in risk_flags:
            md += f"- {flag}\n"
    else:
        md += "- (无特定风险提示)\n"
    md += f"\n## 数据质量\n{data_quality}\n"

    drivers = direction.get("drivers", [])
    if drivers:
        md += f"\n**主要驱动因子**:{'、'.join(drivers)}\n"
    return md


def _build_fallback_structured(
    full_symbol: str,
    pos_block: Dict[str, Any],
) -> dict:
    """LLM 失败时,用 features 数据拼结构化 JSON(降级版本)。"""
    snapshot = pos_block.get("snapshot", {}) or {}
    latest = pos_block.get("latest", {}) or {}
    net_long_change = latest.get("net_long_change_5d") or snapshot.get("net_long_change_5d")
    concentration = snapshot.get("concentration")
    crowding_pctl = snapshot.get("crowding_pctl_180d")
    long_change = snapshot.get("long_top20_change_5d")
    short_change = snapshot.get("short_top20_change_5d")
    lsr_change = snapshot.get("long_short_ratio_change_5d")
    consec = snapshot.get("consecutive_net_long_days")
    slope_20d = snapshot.get("net_long_slope_20d")
    price_dir = snapshot.get("price_direction", "N/A")
    price_pos_alignment = snapshot.get("price_position_alignment", "N/A")

    if net_long_change is not None and net_long_change > 0 and (crowding_pctl is None or crowding_pctl < 0.9):
        dir_value = "long"
    elif net_long_change is not None and net_long_change < 0 and (crowding_pctl is None or crowding_pctl < 0.9):
        dir_value = "short"
    elif crowding_pctl is not None and crowding_pctl > 0.9:
        dir_value = "neutral"
    else:
        dir_value = "neutral"

    def _trend_label(val: Optional[float]) -> str:
        if val is None:
            return "平稳"
        return "加仓" if val > 0 else ("减仓" if val < 0 else "平稳")

    ret = {
        "direction": {
            "value": dir_value,
            "confidence": 0.6 if dir_value != "neutral" else 0.4,
            "drivers": [],
        },
        "long_side": {
            "trend": _trend_label(long_change),
            "change_5d": long_change,
            "interpretation": (
                f"多头前20{_trend_label(long_change)}({'主动' if (long_change or 0) > 0 else ''})"
                if long_change is not None else "多头数据不可得"
            ),
        },
        "short_side": {
            "trend": _trend_label(short_change),
            "change_5d": short_change,
            "interpretation": (
                f"空头前20{_trend_label(short_change)}({'主动' if (short_change or 0) > 0 else ''})"
                if short_change is not None else "空头数据不可得"
            ),
        },
        "concentration": {
            "level": "高" if (concentration or 0) >= 0.5 else ("低" if (concentration or 0) <= 0.2 else "中"),
            "crowding_status": "拥挤" if (crowding_pctl or 0) > 0.9 else ("冷清" if (crowding_pctl or 0) < 0.1 else "正常"),
            "reversal_risk": (crowding_pctl or 0) > 0.9,
            "analysis": f"集中度{_fmt(concentration)},拥挤度分位{_fmt(crowding_pctl)}",
        },
        "cross_validation": {
            "alignment": price_pos_alignment if price_pos_alignment != "N/A" else "待定(价格方向不可得)",
            "price_trend": price_dir.replace("bullish", "上涨").replace("bearish", "下跌") if price_dir != "N/A" else "N/A",
            "position_trend": "净多增加" if (net_long_change or 0) > 0 else ("净多减少" if (net_long_change or 0) < 0 else "平稳"),
            "analysis": f"净多变化{_fmt(net_long_change)},多空比变化{_fmt(lsr_change)}",
        },
        "summary": f"降级输出:持仓方向{dir_value},净多变化{_fmt(net_long_change)},集中度{_fmt(concentration)}",
        "risk_flags": [],
        "data_quality": f"降级模式(LLM不可用),条数={pos_block.get('quality', {}).get('rows', 0)}",
    }

    drivers = []
    if consec is not None and abs(consec) >= 2:
        drivers.append(f"连续{abs(consec)}日净多{'增加' if consec > 0 else '减少'}")
    if slope_20d is not None:
        drivers.append(f"20d斜率{'向上' if slope_20d > 0 else '向下'}({_fmt(slope_20d)})")
    if (crowding_pctl or 0) > 0.8:
        drivers.append("拥挤度高分位")
    ret["direction"]["drivers"] = drivers[:3]

    return ret


def _build_fallback_report(
    full_symbol: str,
    pos_block: Dict[str, Any],
    direction: str,
    signals: list,
    quality_rows: int,
) -> str:
    md = (
        f"# {full_symbol} 持仓分析报告(降级版本 — LLM 不可用)\n\n"
        f"## 综合判断\n方向:{direction}\n\n"
        f"## 关键指标\n"
        f"- 前 20 名净多头 5 日变化:{_fmt(pos_block.get('snapshot',{}).get('net_long_change_5d'))}\n"
        f"- 多头前20 5日变化:{_fmt(pos_block.get('snapshot',{}).get('long_top20_change_5d'))}\n"
        f"- 空头前20 5日变化:{_fmt(pos_block.get('snapshot',{}).get('short_top20_change_5d'))}\n"
        f"- 多空比:{_fmt(pos_block.get('latest',{}).get('long_short_ratio'))}\n"
        f"- 集中度:{_fmt(pos_block.get('snapshot',{}).get('concentration'))}\n"
        f"- 拥挤度 180d 分位:{_fmt(pos_block.get('snapshot',{}).get('crowding_pctl_180d'))}\n"
        f"- 价格-持仓对齐:{pos_block.get('snapshot',{}).get('price_position_alignment','N/A')}\n\n"
        f"## 触发信号\n{_format_signals(signals)}\n\n"
        f"## 数据质量\n- 数据条数:{quality_rows}\n\n"
        f"---\n_LLM 故障恢复后请重新提交任务以获得完整分析。_\n"
    )
    return md


def create_position_analyst(llm):
    """持仓分析师工厂函数。"""

    def _extract_price_direction(features: dict) -> Optional[str]:
        """从 technical features 提取日线价格方向。"""
        tech = features.get("technical") if isinstance(features, dict) else None
        if not isinstance(tech, dict):
            return None
        daily = tech.get("daily", {}) if isinstance(tech, dict) else {}
        if not isinstance(daily, dict):
            return None
        trend = daily.get("trend", {}) if isinstance(daily, dict) else {}
        if not isinstance(trend, dict):
            return None
        return trend.get("direction")

    def position_analyst_node(state: dict) -> dict:
        full_symbol = get_full_symbol(state)
        trade_date = state.get("trade_date", "")

        logger.info(f"🎯 [持仓分析师] 启动: {full_symbol} @ {trade_date}")

        features = load_features(state)
        pos_block = features.get("positioning")

        # --- 降级 1:features 缺失 ---
        if not isinstance(pos_block, dict):
            reason = "持仓 features 缺失(features['positioning'] 为空)"
            empty = empty_report("neutral", reason)
            return {
                "sentiment_report": empty,
                "position_report": empty,
                "position_structured": {},
                "messages": [],
                "sentiment_tool_call_count": 0,
            }

        # --- 降级 2:数据稀疏 ---
        if not quality_gate(pos_block):
            reason = "持仓数据稀疏"
            empty = empty_report("neutral", reason)
            return {
                "sentiment_report": empty,
                "position_report": empty,
                "position_structured": {},
                "messages": [],
                "sentiment_tool_call_count": 0,
            }

        # --- 从 technical features 注入价格方向 ---
        price_dir = _extract_price_direction(features)

        signals = pos_block.get("signals", []) or []
        snap = pos_block.get("snapshot", {}) or {}
        latest = pos_block.get("latest", {}) or {}
        net_long_change = snap.get("net_long_change_5d") or latest.get("net_long_change_5d")
        concentration = snap.get("concentration")
        crowding_pctl = snap.get("crowding_pctl_180d")
        direction = _derive_direction(net_long_change, crowding_pctl, signals)
        quality_rows = pos_block.get("quality", {}).get("rows", 0)

        variety_name = state.get("variety_name", full_symbol)
        exchange = state.get("exchange", "")

        # 数据来源:特征层中的实际合约代码(多合约时已选主力)
        features_symbol = pos_block.get("quality", {}).get("symbol") or latest.get("symbol", "")
        if features_symbol and "." not in full_symbol and features_symbol != full_symbol:
            contract_source = f"{features_symbol}(主力合约)"
        else:
            contract_source = full_symbol

        prompt_vars = dict(
            full_symbol=full_symbol,
            variety_name=variety_name,
            exchange=exchange,
            trade_date=trade_date,
            contract_source=contract_source,
            net_long_change_5d=_fmt(net_long_change),
            concentration=_fmt(concentration),
            crowding_pctl=_fmt(crowding_pctl),
            signals=_format_signals(signals),
            quality_rows=quality_rows,
            # 新字段
            long_change_5d=_fmt(snap.get("long_top20_change_5d")),
            short_change_5d=_fmt(snap.get("short_top20_change_5d")),
            long_short_ratio=_fmt(latest.get("long_short_ratio") or snap.get("long_short_ratio")),
            lsr_change_5d=_fmt(snap.get("long_short_ratio_change_5d")),
            consecutive_days=_fmt(snap.get("consecutive_net_long_days")),
            slope_20d=_fmt(snap.get("net_long_slope_20d")),
            price_direction=price_dir or "N/A",
            price_position_alignment=snap.get("price_position_alignment", "N/A"),
        )

        try:
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", POSITION_SYSTEM_PROMPT),
                    MessagesPlaceholder(variable_name="messages"),
                ]
            ).partial(**prompt_vars)

            messages_payload = prompt.format_messages(
                messages=state.get("messages", []) or []
            )

            logger.info(f"🎯 [持仓分析师] 调用 LLM,full_symbol={full_symbol}")
            result = llm.invoke(messages_payload)

            if hasattr(result, "content"):
                content = result.content
                if not isinstance(content, str):
                    content = str(content) if content is not None else ""
            else:
                content = str(result) if result is not None else ""

            # 解析 LLM 返回的 JSON
            try:
                cleaned = content.strip()
                if cleaned.startswith("```"):
                    lines = cleaned.splitlines()
                    start = 1 if lines[0].strip().startswith("```") else 0
                    end = -1 if lines[-1].strip() == "```" else len(lines)
                    cleaned = "\n".join(lines[start:end])
                parsed = json.loads(cleaned)
                structured_report = parsed
                report_md = _structured_to_markdown(parsed)
            except (json.JSONDecodeError, Exception) as parse_err:
                logger.warning(f"🎯 [持仓分析师] JSON 解析失败,回退原始内容: {parse_err}")
                structured_report = {"raw": content, "parse_error": str(parse_err)}
                report_md = content

            logger.info(f"✅ [持仓分析师] 报告生成: {len(report_md)} 字符")

            msg_out = result if hasattr(result, "content") else AIMessage(content=report_md)
            return {
                "sentiment_report": report_md,
                "position_report": report_md,
                "position_structured": structured_report,
                "messages": [msg_out],
                "sentiment_tool_call_count": 0,
            }

        except Exception as e:
            logger.error(f"❌ [持仓分析师] LLM 调用失败: {e}")
            try:
                structured = _build_fallback_structured(full_symbol, pos_block)
                fallback_md = _build_fallback_report(
                    full_symbol, pos_block, direction, signals, quality_rows
                )
            except Exception as inner_e:
                logger.error(f"❌ [持仓分析师] fallback 也失败: {inner_e}")
                fallback_md = empty_report("neutral", f"LLM 失败且 fallback 异常: {inner_e}")
                structured = {}

            return {
                "sentiment_report": fallback_md,
                "position_report": fallback_md,
                "position_structured": structured,
                "messages": [],
                "sentiment_tool_call_count": 0,
            }

    return position_analyst_node


__all__ = ["create_position_analyst"]
