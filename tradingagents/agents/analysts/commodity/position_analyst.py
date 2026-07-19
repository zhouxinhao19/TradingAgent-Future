"""
position_analyst.py — 商品期货持仓分析师节点 (Phase 3b-ii + 品种级多合约增强)

输入:state['commodity_features']['positioning'] (含多空双边/多空比/连续变化/价格对齐/多合约聚合)
输出:state['sentiment_report'] / state['position_report'] / state['position_structured']

持仓分析三层递进框架:
  第一层:总量判断 — 品种级总 OI + 价格 → 四象限价仓配合(多头强势/空头回补/空头强势/多头止损)
  第二层:结构分析 — 多空行为分离、跨合约一致性、移仓换月、集中度与拥挤度
  第三层:交叉验证 — 成交量确认、OI背离、跨维度印证

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
    extract_first_sentence,
    get_full_symbol,
    inject_analyst_id,
    load_features,
    make_analyst_id,
    make_conclusion_id,
    make_registry_entry,
    quality_gate,
)

logger = get_logger("default")

POSITION_SYSTEM_PROMPT = """你是一位资深的期货持仓分析师,擅长"总量判断→结构分析→交叉验证"三层递进框架。

## 分析对象
- 标的代码:{full_symbol}
- 品种:{variety_name}
- 交易所:{exchange}
- 分析日期:{trade_date}
- 持仓数据来源:{contract_source}

---

## 第一层:总量判断 — 看懂市场主要矛盾

### 品种级总持仓(聚合所有活跃合约)
- 品种总 OI:{total_oi_variety}
- 活跃合约数:{active_contracts}
- 品种总净多:{total_net_long_variety}
- 主力合约 OI 5日变化:{oi_change_pct_5d}

### 四象限价仓配合
- 日线价格方向:{price_direction}
- 价格-OI状态: **{price_oi_regime}**

经典框架解读:
| 价仓组合 | 含义 | 趋势强度 |
|:---|:---|:---:|
| 价涨+仓增=多头强势 | 新多资金入场,趋势延续 | ★★★ |
| 价涨+仓减=空头回补 | 空头平仓推动,新多无意入场 | ★ |
| 价跌+仓增=空头强势 | 新空资金入场,趋势延续 | ★★★ |
| 价跌+仓减=多头止损 | 多头离场,卖压衰竭 | ★ |

---

## 第二层:结构分析 — 看清多空双方与跨合约格局

### 各合约明细
{contracts_table}

### 跨合约方向一致性
- 状态:**{cross_contract_consistency}**
- 同向=全合约方向一致,趋势共识强;分化=近远月方向冲突,需警惕

### 移仓换月检测
{rollover_status}

### 主力合约持仓细节
| 指标 | 数值 |
|------|------|
| 前20多头 5日变化 | {long_change_5d} |
| 前20空头 5日变化 | {short_change_5d} |
| 净多 5日变化 | {net_long_change_5d} |
| 多空比(L/S) | {long_short_ratio} |
| 多空比 5日变化 | {lsr_change_5d} |
| 连续净多变化天数 | {consecutive_days} |
| 20d 净多斜率 | {slope_20d} |
| 前20集中度 | {concentration} |
| 拥挤度 180d 分位 | {crowding_pctl} |

### 触发信号
{signals}

---

## 第三层:交叉验证 — 捕捉拐点信号

### 成交量确认
- 成交量 Z 值:{vol_z20}
- 成交量状态:{vol_regime}

### OI 背离
- 价仓背离状态:{oi_divergence}
  - confirm = 价格与持仓同向,趋势可靠
  - conflict = 价格与持仓背离,趋势存疑
  - neutral = 无明显背离

### 数据质量
- 数据条数:{quality_rows}

---

## 新闻摘要(跨分析师参考)
{news_summary}

## 分析要求

### 第一层:总量判断
基于四象限价仓配合,判断当前趋势的强度和性质:
- 多头强势(价涨仓增):确认趋势,可顺势做多
- 空头回补(价涨仓减):怀疑趋势强度,警惕反转
- 空头强势(价跌仓增):确认趋势,可顺势做空
- 多头止损(价跌仓减):关注衰竭信号,可能见底

### 第二层:结构分析
1. **跨合约一致性**:全合约同向→趋势共识强,近远月分化→市场分歧大
2. **移仓换月**:资金从近月转移到远月是否体现远期看涨/看空预期
3. **多头 vs 空头行为分离**:区分主动加仓 vs 被动减仓
4. **净多趋势持续性**:连续变化天数 + 20d 斜率 → 短期波动还是趋势性变化
5. **多空比**:L/S 比值变化是多空力量转换的关键指标
6. **集中度与拥挤度**:前 5 占比 > 60% 高集中;180d 分位 > 0.9 过度拥挤

### 第三层:交叉验证
- 成交量放大+价仓同向=趋势强化;成交量放大+价仓背离=分歧加大
- 数据稀疏或信号矛盾时,降低 confidence 并明确标注

## 输出格式(必须为合法 JSON)

```json
{{
  "direction": {{
    "value": "long|short|neutral",
    "confidence": 0.0-1.0,
    "drivers": ["最大驱动因子1", "驱动因子2"]
  }},
  "market_regime": {{
    "regime": "多头强势|空头回补|空头强势|多头止损|震荡待判",
    "price_trend": "上涨|下跌|震荡",
    "oi_trend": "增仓|减仓|平稳",
    "interpretation": "第一层总量解读:四象限价仓配合的含义"
  }},
  "long_side": {{
    "trend": "加仓|减仓|平稳",
    "change_5d": 数值或"null",
    "interpretation": "多头行为解读(主动加仓/减仓)"
  }},
  "short_side": {{
    "trend": "加仓|减仓|平稳",
    "change_5d": 数值或"null",
    "interpretation": "空头行为解读(主动加仓/减仓)"
  }},
  "concentration": {{
    "level": "高|中|低",
    "crowding_status": "拥挤|正常|冷清",
    "reversal_risk": true或false,
    "analysis": "集中度与拥挤度解读"
  }},
  "cross_contract": {{
    "consistency": "同向看多|同向看空|分化|待定",
    "analysis": "跨合约一致性分析,包括各合约方向差异和含义"
  }},
  "rollover": {{
    "detected": true或false,
    "analysis": "移仓状态分析(如有)"
  }},
  "cross_validation": {{
    "alignment": "同向看多|同向看空|背离价涨仓减|背离价跌仓增|待定",
    "volume_confirmation": "放量共振|缩量背离|正常",
    "analysis": "价格-持仓-成交量三维交叉验证分析"
  }},
  "summary": "150字内综合研判(包含三层框架的核心结论)",
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
        return "\n".join(f"- {s}" for s in signals[:10])
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
    regime = parsed.get("market_regime", {}) or {}
    long_side = parsed.get("long_side", {}) or {}
    short_side = parsed.get("short_side", {}) or {}
    concentration = parsed.get("concentration", {}) or {}
    cross_contract = parsed.get("cross_contract", {}) or {}
    rollover = parsed.get("rollover", {}) or {}
    cross = parsed.get("cross_validation", {}) or {}
    summary = parsed.get("summary", "")
    risk_flags = parsed.get("risk_flags", [])
    data_quality = parsed.get("data_quality", "")

    md = f"# {direction.get('value','N/A')} | 持仓分析报告\n\n"
    md += "## 第一层:总量判断\n"
    md += f"**市场状态**:{regime.get('regime','N/A')}\n"
    md += f"- {regime.get('interpretation','')}\n\n"

    md += "## 第二层:结构分析\n"
    md += f"### 综合判断\n{summary}\n\n"
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

    md += "### 跨合约分析\n"
    md += f"- 方向一致性:{cross_contract.get('consistency','N/A')}\n"
    if cross_contract.get("analysis"):
        md += f"  - {cross_contract.get('analysis','')}\n"
    if rollover.get("detected"):
        md += f"- **移仓信号**:{rollover.get('analysis','')}\n"

    md += "## 第三层:交叉验证\n"
    md += f"- 价仓对齐:{cross.get('alignment','N/A')}\n"
    md += f"- 成交量确认:{cross.get('volume_confirmation','N/A')}\n"
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
    price_oi_regime = snapshot.get("price_oi_regime", "N/A")
    cross_consistency = snapshot.get("cross_contract_consistency", "N/A")
    rollover_detected = snapshot.get("rollover_detected", False)
    rollover_desc = snapshot.get("rollover_description", "")
    total_oi = snapshot.get("total_oi_variety", "N/A")
    active_contracts = snapshot.get("active_contracts", 0)
    oi_change_pct = snapshot.get("oi_change_pct_5d")

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

    # 四象限 regime 解读
    regime_interpretation = {
        "多头强势(价涨仓增)": "新多资金入场确认上涨趋势,趋势延续概率大,可顺势做多",
        "空头回补(价涨仓减)": "上涨由空头平仓而非新多入场推动,上涨动力存疑,警惕反弹结束",
        "空头强势(价跌仓增)": "新空资金入场确认下跌趋势,趋势延续概率大,可顺势做空",
        "多头止损(价跌仓减)": "下跌由多头止损而非新空入场导致,卖压可能衰竭,关注底部信号",
        "震荡待判": "价格或持仓方向不明,需更多数据确认",
    }.get(price_oi_regime, "待观察")

    ret = {
        "direction": {
            "value": dir_value,
            "confidence": 0.6 if dir_value != "neutral" else 0.4,
            "drivers": [],
        },
        "market_regime": {
            "regime": price_oi_regime if price_oi_regime != "N/A" else "待定",
            "price_trend": price_dir.replace("bullish", "上涨").replace("bearish", "下跌") if price_dir != "N/A" else "N/A",
            "oi_trend": "增仓" if (oi_change_pct or 0) > 0 else ("减仓" if (oi_change_pct or 0) < 0 else "平稳"),
            "interpretation": regime_interpretation,
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
        "cross_contract": {
            "consistency": cross_consistency if cross_consistency != "N/A" else "待定",
            "analysis": f"跨合约{_fmt(cross_consistency)},活跃合约{_fmt(active_contracts)}个"
            if active_contracts else "跨合约数据不可得",
        },
        "rollover": {
            "detected": rollover_detected,
            "analysis": rollover_desc if rollover_detected else "未检测到移仓换月",
        },
        "cross_validation": {
            "alignment": price_pos_alignment if price_pos_alignment != "N/A" else "待定(价格方向不可得)",
            "volume_confirmation": "待定(降级模式)",
            "analysis": f"总量OI变化{_fmt(oi_change_pct)},净多变化{_fmt(net_long_change)},多空比变化{_fmt(lsr_change)}",
        },
        "summary": f"降级输出:持仓方向{dir_value},四象限{price_oi_regime},净多变化{_fmt(net_long_change)}",
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
    if price_oi_regime and "多头强势" in price_oi_regime:
        drivers.append("多头强势(价涨仓增)")
    elif price_oi_regime and "空头强势" in price_oi_regime:
        drivers.append("空头强势(价跌仓增)")
    ret["direction"]["drivers"] = drivers[:3]

    return ret


def _build_fallback_report(
    full_symbol: str,
    pos_block: Dict[str, Any],
    direction: str,
    signals: list,
    quality_rows: int,
) -> str:
    snapshot = pos_block.get("snapshot", {}) or {}
    price_oi_regime = snapshot.get("price_oi_regime", "N/A")
    cross_consistency = snapshot.get("cross_contract_consistency", "N/A")
    rollover_detected = snapshot.get("rollover_detected", False)
    rollover_desc = snapshot.get("rollover_description", "")
    total_oi = snapshot.get("total_oi_variety", "N/A")
    active_contracts = snapshot.get("active_contracts", 0)
    oi_change_pct = snapshot.get("oi_change_pct_5d")

    md = (
        f"# {full_symbol} 持仓分析报告(降级版本 — LLM 不可用)\n\n"
        f"## 第一层:总量判断\n"
        f"- **市场状态**:{price_oi_regime}\n"
        f"- 品种总OI:{total_oi} | 活跃合约:{active_contracts}\n"
        f"- OI 5日变化:{_fmt(oi_change_pct)}\n\n"
        f"## 第二层:结构分析\n"
        f"- **方向**:{direction}\n"
        f"- 前20名净多头5日变化:{_fmt(snapshot.get('net_long_change_5d'))}\n"
        f"- 多头前20 5日变化:{_fmt(snapshot.get('long_top20_change_5d'))}\n"
        f"- 空头前20 5日变化:{_fmt(snapshot.get('short_top20_change_5d'))}\n"
        f"- 多空比:{_fmt(snapshot.get('long_short_ratio'))}\n"
        f"- 集中度:{_fmt(snapshot.get('concentration'))}\n"
        f"- 拥挤度 180d 分位:{_fmt(snapshot.get('crowding_pctl_180d'))}\n"
        f"- 跨合约一致性:{cross_consistency}\n"
        f"- 移仓:{rollover_desc if rollover_detected else '未检测到'}\n\n"
        f"## 触发信号\n{_format_signals(signals)}\n\n"
        f"## 数据质量\n- 数据条数:{quality_rows}\n\n"
        f"---\n_LLM 故障恢复后请重新提交任务以获得完整分析。_\n"
    )
    return md


def _extract_context_from_technical(features: dict) -> Dict[str, str]:
    """从 technical features 提取价格方向、成交量、OI 背离等上下文。"""
    tech = features.get("technical") if isinstance(features, dict) else None
    if not isinstance(tech, dict):
        return {"price_direction": "N/A", "vol_z20": "N/A", "vol_regime": "N/A", "oi_divergence": "N/A"}

    combined = tech.get("combined", {}) if isinstance(tech, dict) else {}
    daily = tech.get("daily", {}) if isinstance(tech, dict) else {}
    snap = daily.get("snapshot", {}) if isinstance(daily, dict) else {}

    # 价格方向
    trend = (combined if isinstance(combined, dict) else {}).get("direction", "neutral")
    price_dir = {"long": "bullish", "short": "bearish"}.get(str(trend).lower(), "neutral")

    # 成交量状态
    vol_z = None
    if isinstance(snap, dict):
        vol_z = snap.get("vol_z20")
    vol_regime = "正常"
    if vol_z is not None:
        if vol_z >= 2.0:
            vol_regime = "放量"
        elif vol_z <= -2.0:
            vol_regime = "缩量"

    # OI 背离
    oi_div = (combined if isinstance(combined, dict) else {}).get("oi_divergence", "neutral")
    oi_div_cn = {"confirm": "confirm(价仓同向)", "conflict": "conflict(价仓背离)", "neutral": "neutral"}.get(str(oi_div), "neutral")

    return {
        "price_direction": price_dir,
        "vol_z20": _fmt(vol_z) if vol_z is not None else "N/A",
        "vol_regime": vol_regime,
        "oi_divergence": oi_div_cn,
    }


def create_position_analyst(llm):
    """持仓分析师工厂函数。"""

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
            analyst_id = make_analyst_id("POSN", full_symbol, trade_date, seed="empty")
            conclusion_id = make_conclusion_id("POSN", 1)
            tagged_empty = inject_analyst_id(empty, analyst_id)
            registry_entry = make_registry_entry(analyst_id, conclusion_id, "POSN", "position", "position_report", "skip", "(数据缺失: 跳过)", status="skipped")
            return {
                "sentiment_report": empty,  # 保持纯净(stock 兼容)
                "position_report": tagged_empty,
                "position_structured": {},
                "messages": [],
                "sentiment_tool_call_count": 0,
                "analyst_registry": registry_entry,
            }

        # --- 降级 2:数据稀疏 ---
        if not quality_gate(pos_block):
            reason = "持仓数据稀疏"
            empty = empty_report("neutral", reason)
            analyst_id = make_analyst_id("POSN", full_symbol, trade_date, seed="sparse")
            conclusion_id = make_conclusion_id("POSN", 1)
            tagged_empty = inject_analyst_id(empty, analyst_id)
            registry_entry = make_registry_entry(analyst_id, conclusion_id, "POSN", "position", "position_report", "skip", "(数据稀疏: 跳过)", status="skipped")
            return {
                "sentiment_report": empty,  # 保持纯净
                "position_report": tagged_empty,
                "position_structured": {},
                "messages": [],
                "sentiment_tool_call_count": 0,
                "analyst_registry": registry_entry,
            }

        # --- 从 technical features 提取上下文 ---
        tech_ctx = _extract_context_from_technical(features)

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

        # 数据来源
        features_symbol = pos_block.get("quality", {}).get("symbol") or latest.get("symbol", "")
        if features_symbol and "." not in full_symbol and features_symbol != full_symbol:
            contract_source = f"{features_symbol}(主力合约)"
        else:
            contract_source = full_symbol

        # 多合约数据
        contracts = pos_block.get("contracts", [])
        variety_agg = pos_block.get("variety_aggregate", {})
        rollover = pos_block.get("rollover", {})
        cross_contract = pos_block.get("cross_contract", {})
        contracts_table = pos_block.get("contracts_table", "(无合约数据)")

        # 移仓状态描述
        rollover_status = rollover.get("description", "未检测到移仓换月") if rollover else "未检测到移仓换月"

        prompt_vars = dict(
            full_symbol=full_symbol,
            variety_name=variety_name,
            exchange=exchange,
            trade_date=trade_date,
            contract_source=contract_source,
            # 第一层:总量判断
            total_oi_variety=_fmt(variety_agg.get("total_oi")),
            total_net_long_variety=_fmt(variety_agg.get("total_net_long")),
            active_contracts=_fmt(variety_agg.get("active_contracts", 0)),
            oi_change_pct_5d=_fmt(snap.get("oi_change_pct_5d")),
            price_oi_regime=snap.get("price_oi_regime", "N/A"),
            # 第二层:结构分析
            contracts_table=contracts_table,
            cross_contract_consistency=cross_contract.get("consistency", "待定"),
            rollover_status=rollover_status,
            net_long_change_5d=_fmt(net_long_change),
            concentration=_fmt(concentration),
            crowding_pctl=_fmt(crowding_pctl),
            signals=_format_signals(signals),
            quality_rows=quality_rows,
            long_change_5d=_fmt(snap.get("long_top20_change_5d")),
            short_change_5d=_fmt(snap.get("short_top20_change_5d")),
            long_short_ratio=_fmt(latest.get("long_short_ratio") or snap.get("long_short_ratio")),
            lsr_change_5d=_fmt(snap.get("long_short_ratio_change_5d")),
            consecutive_days=_fmt(snap.get("consecutive_net_long_days")),
            slope_20d=_fmt(snap.get("net_long_slope_20d")),
            price_direction=tech_ctx["price_direction"],
            price_position_alignment=snap.get("price_position_alignment", "N/A"),
            # 第三层:交叉验证
            vol_z20=tech_ctx["vol_z20"],
            vol_regime=tech_ctx["vol_regime"],
            oi_divergence=tech_ctx["oi_divergence"],
            news_summary=state.get("news_summary", ""),
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
            analyst_id = make_analyst_id("POSN", full_symbol, trade_date)
            conclusion_id = make_conclusion_id("POSN", 1)
            tagged_report = inject_analyst_id(report_md, analyst_id)
            registry_entry = make_registry_entry(analyst_id, conclusion_id, "POSN", "position", "position_report", direction or "neutral", extract_first_sentence(report_md))
            return {
                "sentiment_report": report_md,  # 保持纯净
                "position_report": tagged_report,
                "position_structured": structured_report,
                "messages": [msg_out],
                "sentiment_tool_call_count": 0,
                "analyst_registry": registry_entry,
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

            analyst_id = make_analyst_id("POSN", full_symbol, trade_date, seed="fallback")
            conclusion_id = make_conclusion_id("POSN", 1)
            tagged_fallback = inject_analyst_id(fallback_md, analyst_id)
            registry_entry = make_registry_entry(analyst_id, conclusion_id, "POSN", "position", "position_report", direction or "neutral", "(降级: LLM 不可用)", status="degraded")
            return {
                "sentiment_report": fallback_md,  # 保持纯净
                "position_report": tagged_fallback,
                "position_structured": structured,
                "messages": [],
                "sentiment_tool_call_count": 0,
                "analyst_registry": registry_entry,
            }

    return position_analyst_node


__all__ = ["create_position_analyst"]