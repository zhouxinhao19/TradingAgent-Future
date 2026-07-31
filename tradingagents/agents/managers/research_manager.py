import time
import json
import os

from typing import Any, Dict, List, Optional

# 导入统一日志系统
from tradingagents.utils.logging_init import get_logger
from tradingagents.agents.utils.instrument_utils import build_instrument_context
from tradingagents.agents.analysts.commodity import (
    build_custom_data_context,
    build_fact_cards,
    _build_contradiction_map,
)
from tradingagents.agents.managers.schemas import ManagerDecision
from tradingagents.llm_clients.json_parser import log_p0_validation, parse_and_validate

logger = get_logger("default")


def _use_schema_validation() -> bool:
    """P0: 开关控制是否启用 Pydantic 后置校验(运行时读取,便于测试 monkeypatch)。"""
    return os.environ.get("FEATURE_COMMODITY_SCHEMA_VALIDATION", "true").lower() == "true"


# =============================================================================
# _build_analyst_summary — 结构化摘要替代完整 Markdown（Phase Agent 改造）
# =============================================================================

def _nested(obj: Any, *keys: str, default: Any = None) -> Any:
    """安全读取嵌套字典；空字典视为缺失。"""
    for key in keys:
        if not isinstance(obj, dict):
            return default
        obj = obj.get(key)
    return default if obj in (None, {}) else obj


def _present(value: Any) -> bool:
    """判断值是否适合进入摘要，保留 0/False。"""
    if value is None:
        return False
    if isinstance(value, float) and value != value:
        return False
    return value != ""


def _normalize_direction(value: Any) -> str:
    """将 L1 的中英文方向归一化为 bullish/bearish/neutral/skip。"""
    text = str(value or "").strip().lower()
    if text in ("skip", "skipped", "?"):
        return "skip"
    if text in ("bullish", "long", "做多", "看多", "向上") or "看多" in text:
        return "bullish"
    if text in ("bearish", "short", "做空", "看空", "向下") or "看空" in text:
        return "bearish"
    if text in ("neutral", "hold", "中性", "持有"):
        return "neutral"
    return text or "neutral"


def _string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _append_metric_line(lines: List[str], label: str, metrics: List[tuple[str, Any]]) -> None:
    """只输出真实存在的指标；整块为空时才标记数据缺失。"""
    available = [f"{name}={value}" for name, value in metrics if _present(value)]
    if available:
        lines.append(f"{label}: " + ", ".join(available))
    else:
        lines.append(f"{label}: 整体不可用（数据缺失）")


_RISK_TERMS = (
    "风险提示", "警告", "高度拥挤", "极度拥挤", "拥挤度高", "高分位",
    "反转风险", "反转概率", "踩踏", "价仓背离", "诱多", "移仓", "换月",
    "流动性风险", "数据异常", "跳变", "极端",
)


def _collect_forced_risk_signals(
    features: Dict[str, Any],
    position_structured: Optional[Dict[str, Any]] = None,
    fundamentals_structured: Optional[Dict[str, Any]] = None,
    reports: Optional[List[str]] = None,
) -> List[str]:
    """确定性收集 L1 明示风险，避免普通信号截断时丢失最高风险。"""
    risks: List[str] = []

    position_structured = position_structured or {}
    fundamentals_structured = fundamentals_structured or {}
    concentration = position_structured.get("concentration", {})
    if isinstance(concentration, dict):
        if concentration.get("reversal_risk") is True:
            status = concentration.get("crowding_status", "高度拥挤")
            risks.append(f"持仓{status}，已明确标记反转风险")
        analysis = concentration.get("analysis")
        if _present(analysis) and any(term in str(analysis) for term in _RISK_TERMS):
            risks.append(str(analysis))

    for structured in (position_structured, fundamentals_structured):
        if isinstance(structured, dict):
            risks.extend(_string_list(structured.get("risk_flags")))

    for module_name in (
        "technical", "basis", "inventory", "positioning", "term_structure", "news_sentiment"
    ):
        block = features.get(module_name, {})
        if not isinstance(block, dict):
            continue
        signals = _string_list(block.get("signals"))
        if module_name == "technical":
            signals.extend(_string_list(_nested(block, "combined", "signals", default=[])))
        for signal in signals:
            if any(term in signal for term in _RISK_TERMS):
                risks.append(signal)

    for report in reports or []:
        if not isinstance(report, str):
            continue
        for raw_line in report.splitlines():
            line = raw_line.strip().lstrip("#-* ").strip()
            if not line or any(
                phrase in line for phrase in ("未检测到", "无风险", "暂无风险", "无特定风险")
            ):
                continue
            if any(term in line for term in _RISK_TERMS):
                risks.append(line)

    deduped: List[str] = []
    seen = set()
    for risk in risks:
        normalized = " ".join(str(risk).split())
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped.append(normalized)
    return deduped


def _build_analyst_summary(
    features: Dict[str, Any],
    registry: Dict[str, Any],
    news_summary: str = "",
    position_structured: Optional[Dict[str, Any]] = None,
    fundamentals_structured: Optional[Dict[str, Any]] = None,
    latest_news: Optional[List[Dict[str, Any]]] = None,
    reports: Optional[List[str]] = None,
) -> str:
    """按真实 L1 state/features schema 构建保真摘要。"""
    lines: List[str] = ["## L1 分析师结构化摘要"]
    position_structured = position_structured or {}
    fundamentals_structured = fundamentals_structured or {}

    # --- 技术分析师 ---
    tech = features.get("technical", {})
    tech_reg = _find_registry_entry(registry, "technical")
    tech_dir = _normalize_direction(tech_reg.get("direction") if tech_reg else "skip")
    tech_status = tech_reg.get("status", "ok") if tech_reg else "skipped"
    tech_snap = _nested(tech, "main_continuous", "daily", "snapshot", default={})
    if not isinstance(tech_snap, dict):
        tech_snap = _nested(tech, "daily", "snapshot", default={}) or {}
    tech_combined = tech.get("combined", {}) if isinstance(tech, dict) else {}
    tech_signals = _string_list(_nested(tech, "combined", "signals", default=[]))
    if not tech_signals:
        tech_signals = _string_list(_nested(tech, "main_continuous", "daily", "signals", default=[]))
    lines.append(f"\n### 技术分析师 | {tech_dir} | status={tech_status}")
    if tech_signals:
        lines.append(f"信号: {'; '.join(tech_signals[:3])}")
    _append_metric_line(lines, "技术面", [
        ("composite_score", tech_snap.get("composite_score")),
        ("direction", tech_combined.get("direction") if isinstance(tech_combined, dict) else None),
        ("oi_divergence", tech_combined.get("oi_divergence") if isinstance(tech_combined, dict) else None),
        ("volatility_regime", _nested(tech_combined, "volatility", "regime")),
        ("atr_ratio_pctl180", _nested(tech_combined, "volatility", "atr_ratio_pctl180")),
        ("支撑", tech_snap.get("boll_low")),
        ("阻力", tech_snap.get("boll_up")),
    ])

    # --- 产业分析师（基差 + 库存 + 期限结构） ---
    fund_reg = _find_registry_entry(registry, "fundamental")
    fund_dir = _normalize_direction(fund_reg.get("direction") if fund_reg else "skip")
    fund_status = fund_reg.get("status", "ok") if fund_reg else "skipped"
    basis = features.get("basis", {})
    inventory = features.get("inventory", {})
    term = features.get("term_structure", {})
    fund_signals: List[str] = []
    for block in (basis, inventory, term):
        if isinstance(block, dict):
            fund_signals.extend(_string_list(block.get("signals")))
    lines.append(f"\n### 产业分析师 | {fund_dir} | status={fund_status}")
    if fund_signals:
        lines.append(f"信号: {'; '.join(fund_signals[:3])}")
    _append_metric_line(lines, "基差", [
        ("spot_price", _nested(basis, "latest", "spot_price")),
        ("near_basis", _nested(basis, "latest", "near_basis")),
        ("dom_basis", _nested(basis, "latest", "dom_basis")),
        ("dom_basis_rate", _nested(basis, "latest", "dom_basis_rate")),
        ("dom_basis_rate_pctl180", _nested(basis, "stats", "zscore_180d", "dom_basis_rate")),
    ])
    _append_metric_line(lines, "库存", [
        ("value", _nested(inventory, "latest", "value")),
        ("wow_change", _nested(inventory, "snapshot", "wow_change")),
        ("mom_change", _nested(inventory, "snapshot", "mom_change")),
        ("jump_flag", _nested(inventory, "snapshot", "jump_flag")),
    ])
    _append_metric_line(lines, "期限结构", [
        ("structure", _nested(term, "snapshot", "structure")),
        ("carry_score", _nested(term, "snapshot", "carry_score")),
        ("metric", _nested(term, "latest", "metric")),
    ])

    # --- 持仓分析师 ---
    pos_reg = _find_registry_entry(registry, "position")
    pos_dir = _normalize_direction(pos_reg.get("direction") if pos_reg else "skip")
    pos_status = pos_reg.get("status", "ok") if pos_reg else "skipped"
    pos_conf = _nested(position_structured, "direction", "confidence")
    positioning = features.get("positioning", {})
    pos_snap = positioning.get("snapshot", {}) if isinstance(positioning, dict) else {}
    pos_signals = _string_list(positioning.get("signals")) if isinstance(positioning, dict) else []
    pos_header = f"\n### 持仓分析师 | {pos_dir} | status={pos_status}"
    if isinstance(pos_conf, (int, float)):
        pos_header += f" | 置信度={pos_conf}"
    lines.append(pos_header)
    if pos_signals:
        lines.append(f"信号: {'; '.join(pos_signals[:3])}")
    _append_metric_line(lines, "持仓", [
        ("net_long_change_5d", pos_snap.get("net_long_change_5d") if isinstance(pos_snap, dict) else None),
        ("long_short_ratio", pos_snap.get("long_short_ratio") if isinstance(pos_snap, dict) else None),
        ("crowding_pctl_180d", pos_snap.get("crowding_pctl_180d") if isinstance(pos_snap, dict) else None),
        ("price_oi_regime", pos_snap.get("price_oi_regime") if isinstance(pos_snap, dict) else None),
        ("cross_contract_consistency", pos_snap.get("cross_contract_consistency") if isinstance(pos_snap, dict) else None),
        ("rollover_detected", pos_snap.get("rollover_detected") if isinstance(pos_snap, dict) else None),
    ])

    # --- 新闻分析师 ---
    news_reg = _find_registry_entry(registry, "news")
    news_dir = _normalize_direction(news_reg.get("direction") if news_reg else "skip")
    news_status = news_reg.get("status", "ok") if news_reg else "skipped"
    lines.append(f"\n### 新闻分析师 | {news_dir} | status={news_status}")
    news_sent = features.get("news_sentiment", {})
    news_signals = _string_list(news_sent.get("signals")) if isinstance(news_sent, dict) else []
    if news_signals:
        lines.append(f"信号: {'; '.join(news_signals[:3])}")

    events = [event for event in (latest_news or []) if isinstance(event, dict)]
    if events:
        positive = sum(1 for event in events if event.get("llm_sentiment", event.get("sentiment")) == "positive")
        negative = sum(1 for event in events if event.get("llm_sentiment", event.get("sentiment")) == "negative")
        high_titles = [
            str(event.get("title") or event.get("summary") or "")[:60]
            for event in events
            if event.get("llm_importance") == "high" and (event.get("title") or event.get("summary"))
        ]
        lines.append(f"新闻情感: pos={positive}, neg={negative}, total={len(events)}")
        if high_titles:
            lines.append(f"高重要度事件: {'; '.join(high_titles[:5])}")
    else:
        sentiment = _nested(news_sent, "snapshot", "sentiment", default={})
        if isinstance(sentiment, dict) and sentiment:
            _append_metric_line(lines, "新闻情感", [
                ("bullish", sentiment.get("bullish")),
                ("bearish", sentiment.get("bearish")),
                ("ratio", sentiment.get("ratio")),
            ])
        else:
            lines.append(f"新闻情感: {news_summary[:120] if news_summary else '整体不可用（数据缺失）'}")

    custom_data = features.get("custom_data", {})
    custom_data_context = build_custom_data_context(features)
    if isinstance(custom_data, dict) and custom_data.get("parsed") and custom_data_context:
        lines.append(
            f"\n### 用户上传数据\n已上传 {custom_data.get('file_count', 0)} 个文件:\n"
            f"{custom_data_context}"
        )

    active_dirs = [direction for direction in (tech_dir, fund_dir, pos_dir, news_dir) if direction != "skip"]
    bullish_count = sum(1 for direction in active_dirs if direction == "bullish")
    bearish_count = sum(1 for direction in active_dirs if direction == "bearish")
    lines.append(f"\nL1 冲突: 看多={bullish_count}, 看空={bearish_count}, 活跃分析师={len(active_dirs)}")

    forced_risks = _collect_forced_risk_signals(
        features,
        position_structured=position_structured,
        fundamentals_structured=fundamentals_structured,
        reports=reports,
    )
    if forced_risks:
        lines.append("\n## 强制保留风险信号（L2 不得遗漏）")
        lines.extend(f"- {risk}" for risk in forced_risks)

    return "\n".join(lines)


def _find_registry_entry(registry: Dict[str, Any], analyst_key: str) -> Dict[str, Any]:
    """优先按 analyst 字段精确匹配，ID 前缀仅作旧数据兼容。"""
    prefix = {
        "technical": "TECH",
        "fundamental": "FUND",
        "position": "POSN",
        "news": "NEWS",
    }.get(analyst_key, analyst_key.upper())
    for entry in registry.values():
        if isinstance(entry, dict) and entry.get("analyst") == analyst_key:
            return entry
    for key, entry in registry.items():
        if isinstance(entry, dict) and (
            key.startswith(f"REF-{prefix}") or key.startswith(prefix)
        ):
            return entry
    return {}


def _extract_json_safe(text: str) -> Optional[str]:
    """从 LLM 输出中尽力提取 JSON 字符串。

    依次尝试:
    1. 直接 json.loads
    2. 剥离 ```json/fence 包裹后 json.loads
    3. 寻找第一个 { 和最后一个 } 截取后 json.loads
    4. 寻找第一个 [ 和最后一个 ] 截取后 json.loads
    返回可解析的 JSON 字符串，或 None。
    """
    import re
    if not text:
        return None

    candidates = [text]

    # 剥离 markdown fence
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        candidates.append(m.group(1).strip())

    # 尝试找 {…} 片段
    brace_start = text.find("{")
    if brace_start >= 0:
        brace_end = text.rfind("}")
        if brace_end > brace_start:
            candidates.append(text[brace_start:brace_end + 1].strip())

    # 尝试找 […] 片段
    bracket_start = text.find("[")
    if bracket_start >= 0:
        bracket_end = text.rfind("]")
        if bracket_end > bracket_start:
            candidates.append(text[bracket_start:bracket_end + 1].strip())

    for candidate in candidates:
        try:
            json.loads(candidate)
            return candidate
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def _ensure_forced_risks_in_plan(content: str, forced_risks: List[str]) -> str:
    """对合法 L2 JSON 做确定性保底，避免 LLM 再次遗漏 L1 明示风险。

    当 LLM 未生成合理的「多空对照表」数组或「三种情景推演」对象时，
    基于 forced_risks 自动生成 fallback 条目，确保前端有内容展示。
    """
    if not forced_risks:
        return content
    safe_json = _extract_json_safe(content)
    if safe_json is None:
        return content
    try:
        parsed = json.loads(safe_json)
    except (json.JSONDecodeError, TypeError):
        return content
    except (json.JSONDecodeError, TypeError):
        return content
    if not isinstance(parsed, dict):
        return content

    forced_deduped = list(dict.fromkeys(forced_risks))

    # ---- 多空对照表 ----
    bull_bear = parsed.get("多空对照表")
    if isinstance(bull_bear, dict):
        # 只有强制风险信号 key → LLM 未生成实际内容，fallback
        non_forced_keys = [k for k in bull_bear if k != "强制风险信号"]
        if not non_forced_keys:
            parsed["多空对照表"] = _generate_fallback_bull_bear(forced_deduped)
        else:
            existing = _string_list(bull_bear.get("强制风险信号"))
            parsed["多空对照表"]["强制风险信号"] = list(dict.fromkeys(existing + forced_deduped))
    elif isinstance(bull_bear, list):
        bull_bear.append({
            "分歧点": "系统强制风险信号",
            "看跌逻辑": "；".join(forced_deduped),
            "看涨逻辑": "（无——系统标记的不可忽视风险）",
            "数据来源": ["系统"],
        })
    else:
        # 缺失或格式异常 → fallback
        parsed["多空对照表"] = _generate_fallback_bull_bear(forced_deduped)

    # ---- 三种情景推演 ----
    scenarios = parsed.get("三种情景推演")
    if isinstance(scenarios, dict):
        scenario_keys = {"保守情景", "基准情景", "乐观情景"}
        if not scenario_keys.intersection(scenarios.keys()):
            # LLM 未生成实际情景 → fallback
            parsed["三种情景推演"] = _generate_fallback_scenarios(forced_deduped)
        else:
            scenarios["强制风险情景输入"] = _string_list(
                dict.fromkeys(
                    _string_list(scenarios.get("强制风险情景输入")) + forced_deduped
                )
            )
    elif isinstance(scenarios, list):
        # LLM 把情景推演也输出成了数组 → 转为对象 + fallback
        parsed["三种情景推演"] = _generate_fallback_scenarios(forced_deduped)
    else:
        # 缺失 → fallback
        parsed["三种情景推演"] = _generate_fallback_scenarios(forced_deduped)

    return json.dumps(parsed, ensure_ascii=False)


# =============================================================================
# Fallback 生成：当 LLM 未产生合理内容时，由规则引擎兜底
# =============================================================================

_BB_CATEGORIES = [
    ("crowding", "拥挤度", "拥挤度"),
    ("carry", "期限结构", "carry"),
    ("inventory", "库存", "库存"),
    ("basis", "基差", "基差"),
    ("position", "持仓", "持仓|净多|空头"),
    ("roll", "换月", "换月|移仓"),
    ("volatility", "波动率", "波动率|ATR"),
    ("signal", "信号冲突", "矛盾|冲突|分歧"),
]


def _categorize_risk(risk: str) -> str:
    """将风险信号归类到主题。"""
    for cat_name, cat_label, keywords in _BB_CATEGORIES:
        import re
        if re.search(keywords, risk, re.IGNORECASE):
            return cat_label
    return "其他"


def _generate_fallback_bull_bear(forced_risks: List[str]) -> List[Dict[str, Any]]:
    """从强制风险信号自动生成多空对照表条目。"""
    # 按类别分组
    groups: Dict[str, List[str]] = {}
    for r in forced_risks:
        cat = _categorize_risk(r)
        groups.setdefault(cat, []).append(r)

    entries: List[Dict[str, Any]] = []
    for cat, risks in groups.items():
        entries.append({
            "分歧点": f"{cat}相关的多空分歧",
            "看涨逻辑": "（系统标记）市场存在支撑因素，但需结合具体维度数据评估",
            "看跌逻辑": "；".join(risks[:3]),
            "数据来源": ["系统"],
        })

    if not entries:
        entries.append({
            "分歧点": "多空分歧",
            "看涨逻辑": "（系统标记）暂无明确利空信号",
            "看跌逻辑": "；".join(forced_risks[:3]),
            "数据来源": ["系统"],
        })

    return entries


def _generate_fallback_scenarios(forced_risks: List[str]) -> Dict[str, Any]:
    """从强制风险信号自动生成三种情景推演。"""
    # 分类风险类型
    bullish_risks = [r for r in forced_risks if any(kw in r for kw in ("库存去化", "贴水", "偏多", "利多", "供需"))]
    bearish_risks = [r for r in forced_risks if any(kw in r for kw in ("拥挤", "反转", "carry", "空头", "净多减少", "净空"))]
    neutral_risks = [r for r in forced_risks if r not in bullish_risks and r not in bearish_risks]
    # 如果分类不充分，混合使用
    if not bearish_risks:
        bearish_risks = forced_risks[:3]
    if not bullish_risks:
        bullish_risks = forced_risks[-2:] if len(forced_risks) >= 2 else forced_risks

    return {
        "保守情景": {
            "推演方向": "中性偏空",
            "触发条件": bearish_risks[:3],
            "关注焦点": "风险信号是否兑现",
            "风险节点": "；".join(bearish_risks[:3]),
            "置信度": 0.6,
            "数据来源": ["系统"],
        },
        "基准情景": {
            "推演方向": "中性",
            "触发条件": ["市场按当前逻辑运行"],
            "关注焦点": "多空力量对比变化",
            "风险节点": "；".join(neutral_risks[:2]) if neutral_risks else "等待新催化剂",
            "置信度": 0.5,
            "数据来源": ["系统"],
        },
        "乐观情景": {
            "推演方向": "偏多",
            "触发条件": bullish_risks[:3],
            "关注焦点": "利多因素能否持续",
            "风险节点": "；".join(bearish_risks[:2]),
            "置信度": 0.4,
            "数据来源": ["系统"],
        },
        "综合情景判断": "多空信号交织，建议等待方向性突破确认",
    }


def _data_quality_weight(status: str) -> float:
    """置信度权重校准：基于数据质量。"""
    return {
        "ok": 1.0,
        "degraded": 0.5,
        "skipped": 0.3,
        "": 0.5,
    }.get(status, 0.5)


def _strip_markdown_fence(text: str) -> str:
    """剥离 LLM 输出中可能的 markdown 代码块包裹（```json ... ``` 或 ``` ... ```）。"""
    import re
    if not text:
        return text
    # ```json ... ``` 或 ``` ... ```
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text


# =============================================================================
# COMMODITY_REASONING_PROMPT — 精简版（结构化摘要替代完整 Markdown）
# =============================================================================

COMMODITY_REASONING_PROMPT = """你是期货推理分析师。在单次分析中完成多空双向推理，输出结构化分析报告。

⚠️ 本报告是投研辅助工具，**不是交易指令**。严禁输出具体交易价位。

## 分析对象
- 合约: {full_symbol}
- 品种: {variety_name}
- 分析日期: {analysis_date}

## 标的约束
{instrument_context}

## L1 分析师结构化摘要（含校准置信度 + 关键数据）
{structured_summary}

## L1 分析师报告引用 ID
{analyst_registry_summary}

## 历史经验教训
{past_memory_str}

## 多空辩论历史
{debate_history}

## 模块方向投票
{module_agreement}

## 信号共振/背离
{signal_convergence}

## 矛盾地图

系统基于各模块数据提取了以下矛盾信号对。在"多空对照表"中必须逐对讨论——"哪种逻辑在当前时点更有说服力"并陈述理由：

{contradiction_map_text}

---

## 输出要求

输出包含以下三大模块的复合 JSON。

**JSON 顶级 key 必须严格使用以下名称（不要用"模块A/B/C"作为 key）：**

### 估值驱动矩阵

评估以下维度的当前状态、估值判断和驱动方向：
1. 基差（估值）
2. 库存（驱动）
3. 期限结构（估值+驱动）
4. 技术面（择时信号）
5. 持仓情绪（验证信号）
6. 宏观/新闻（外部驱动）

每个维度必须包含：
- "维度": 维度名称
- "当前状态": 简练描述
- "估值判断": 低估/合理/高估
- "驱动方向": bullish/bearish/neutral
- "驱动因素": 关键驱动列表
- "置信度": 0~1 浮点数
- "数据来源": [引用至少 1 个分析师报告 ID，如 "REF-TECH-a1b2c3d4"]

### 多空对照表

输出数组，每个元素代表一个关键分歧：

- “分歧点”: 多空矛盾的焦点描述
- “看涨逻辑”: 多头方论据，末尾标注引用 ID
- “看跌逻辑”: 空头方论据，末尾标注引用 ID
- “数据来源”: [引用至少 2 个不同分析师报告 ID]

必须识别 ≥1 个分歧。如果矛盾地图中有信号对，必须逐对讨论。

示例（仅作格式参考，不要照抄内容）：
```
[
  {{
    “分歧点”: “库存去化 vs 拥挤度高位”,
    “看涨逻辑”: “库存周环比-8758吨，处于0.01分位极低水平【REF-FUND-xxx】”,
    “看跌逻辑”: “拥挤度95.24%分位，一致性过强易反转【REF-POSN-xxx】”,
    “数据来源”: [“REF-FUND-xxx”, “REF-POSN-xxx”]
  }}
]
```

### 三种情景推演

输出对象，key 为”保守情景”、”基准情景”、”乐观情景”，每个 value 包含：

- “推演方向”: 做多/做空/中性
- “触发条件”: 可观测的市场信号列表
- “关注焦点”: 应关注的关键变量
- “风险节点”: 情景失效条件；必须覆盖输入中的”强制保留风险信号”
- “置信度”: 0~1 浮点数
- “数据来源”: [引用至少 2 个不同分析师报告 ID]

示例（仅作格式参考，不要照抄内容）：
```
{{
  “保守情景”: {{
    “推演方向”: “中性”,
    “触发条件”: [“库存缓慢去化”],
    “关注焦点”: “远月合约期限结构”,
    “风险节点”: “拥挤度反转风险”,
    “置信度”: 0.70,
    “数据来源”: [“REF-FUND-xxx”, “REF-POSN-xxx”]
  }}
}}
```

已给出具体数值或明确状态的维度不得被标为“数据缺失”；无法压缩时保留关键数值和状态原文。

### 禁止项
- ❌ 禁止 "买入"/"卖出"，统一用 "做多"/"做空"
- ❌ 禁止具体交易价位（入场价/止损价/目标价/手数）
- ❌ 禁止保证金占用比例
- ❌ 禁止虚构未提供的分析师报告 ID

### 允许项
- ✅ 三种情景允许方向不同（如保守=做多、基准=中性、乐观=做空）
- ✅ 方向不同时须在"综合情景判断"中标注核心分歧
- ✅ 触发条件必须是可观测、可验证的市场信号

请输出**纯 JSON**（无 Markdown 代码块包裹），包含以上三大模块。"""


def create_research_manager(llm, memory):
    def research_manager_node(state) -> dict:
        ticker = state["company_of_interest"]
        instrument_context = build_instrument_context(ticker)
        market_research_report = state["market_report"]
        sentiment_report = state.get("position_report") or state.get("sentiment_report", "")
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        # === Phase 3b-ii-B:检测 asset_type ===
        asset_type = state.get("asset_type", "commodity")

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"

        # 安全检查：确保memory不为None
        # Phase Agent: 降级策略 — ChromaDB 连接失败时静默降级
        past_memories = []
        if memory is not None:
            try:
                past_memories = memory.get_memories(curr_situation, n_matches=2)
            except Exception as e:
                logger.warning(
                    f"⚠️ [Memory] ChromaDB 检索失败，静默降级: {e}"
                )
                past_memories = []
        else:
            logger.warning(f"⚠️ [DEBUG] memory为None，跳过历史记忆检索")
            past_memories = []

        past_memory_str = ""
        if past_memories:
            for i, rec in enumerate(past_memories, 1):
                past_memory_str += rec["recommendation"] + "\n\n"
        else:
            # 冷启动处理：无历史记忆时提示
            past_memory_str = "（历史相似情景：无（首次分析或记忆服务暂不可用，暂无历史参考））"

        if asset_type == "commodity":
            # ===== 新推理分析师路径 =====
            full_symbol = state.get("full_symbol") or ticker
            variety_name = state.get("variety_name", "")
            trade_date = state.get("trade_date", "")

            features = state.get("commodity_features", {}) or {}
            news_summary = state.get("news_summary", "")
            # 提前读取 registry（第 322 行需此变量）
            registry = state.get("analyst_registry", {}) or {}
            # Phase Agent: 结构化摘要替代 4 份完整 Markdown
            reports = [
                market_research_report,
                fundamentals_report,
                sentiment_report,
                news_report,
            ]
            position_structured = state.get("position_structured", {}) or {}
            fundamentals_structured = state.get("fundamentals_structured", {}) or {}
            latest_news = state.get("latest_news", []) or []
            structured_summary = _build_analyst_summary(
                features,
                registry,
                news_summary,
                position_structured=position_structured,
                fundamentals_structured=fundamentals_structured,
                latest_news=latest_news,
                reports=reports,
            )
            forced_risks = _collect_forced_risk_signals(
                features,
                position_structured=position_structured,
                fundamentals_structured=fundamentals_structured,
                reports=reports,
            )
            logger.info(
                f"[推理分析师] 结构化摘要={len(structured_summary)} 字符, "
                f"报告数={len(registry)}"
            )
            # 构建 analyst_registry_summary (短引用列表,供 LLM 输出引用)
            if registry:
                registry_lines = []
                for ref_id, entry in registry.items():
                    cn_name = entry.get("cn_name", entry.get("analyst", "?"))
                    direction = entry.get("direction", "?")
                    summary = entry.get("summary", "")
                    registry_lines.append(f"- [{ref_id}] {cn_name}: {direction} — {summary}")
                analyst_registry_summary = "\n".join(registry_lines)
            else:
                analyst_registry_summary = "(暂无分析师报告索引)"

            # ---- 事实卡片 + 矛盾地图 ----
            fact_cards = build_fact_cards(features, position_structured)
            contradiction_map = _build_contradiction_map(fact_cards)
            contradiction_map_text = json.dumps(
                contradiction_map, ensure_ascii=False, indent=2
            ) if contradiction_map else "（无显著矛盾信号）"

            # ---- 辩论历史 + 派生 feature 注入 ----
            debate_state = state.get("investment_debate_state", {}) or {}
            debate_history = debate_state.get("history", "") or "（无辩论历史）"
            module_agreement = json.dumps(
                features.get("module_agreement", {}), ensure_ascii=False, indent=2
            )
            signal_convergence = json.dumps(
                features.get("signal_convergence", {}), ensure_ascii=False, indent=2
            )

            prompt = COMMODITY_REASONING_PROMPT.format(
                full_symbol=full_symbol,
                variety_name=variety_name,
                analysis_date=trade_date,
                instrument_context=instrument_context,
                structured_summary=structured_summary,
                analyst_registry_summary=analyst_registry_summary,
                debate_history=debate_history,
                module_agreement=module_agreement,
                signal_convergence=signal_convergence,
                contradiction_map_text=contradiction_map_text,
                past_memory_str=past_memory_str,
            )
            # 直接调用 llm（不做 chain）
            response = llm.invoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)
            # 剥离 markdown 代码块包裹，避免 json.loads 失败
            content = _strip_markdown_fence(content)
            content = _ensure_forced_risks_in_plan(content, forced_risks)

            # ===== P0: Pydantic 后置校验（ManagerDecision） =====
            research_plan_validation_status = "skipped"
            if _use_schema_validation():
                parsed_plan, plan_validation_error = parse_and_validate(
                    content, ManagerDecision
                )
                if parsed_plan is not None:
                    research_plan_validation_status = "passed"
                    log_p0_validation(
                        "research_manager", "passed",
                        elapsed_ms=getattr(parsed_plan, "_p0_elapsed_ms", None),
                    )
                    logger.info(
                        f"[推理分析师] Pydantic 校验通过: "
                        f"主要风险={len(parsed_plan.主要风险)} 条"
                    )
                else:
                    research_plan_validation_status = "failed"
                    log_p0_validation("research_manager", "failed", error=plan_validation_error)
                    logger.warning(
                        f"[推理分析师] Pydantic 校验失败,保留原输出: "
                        f"{plan_validation_error}"
                    )
            else:
                research_plan_validation_status = "legacy"

            # 写入：保留辩论历史（修复覆写 bug）
            debate_state = state.get("investment_debate_state", {}) or {}
            return {
                "investment_debate_state": {
                    "judge_decision": content,
                    "history": debate_state.get("history", ""),
                    "bull_history": debate_state.get("bull_history", ""),
                    "bear_history": debate_state.get("bear_history", ""),
                    "current_response": debate_state.get("current_response", ""),
                    "count": debate_state.get("count", 0),
                },
                "investment_plan": content,
                "fact_cards": fact_cards,
                "contradiction_map": contradiction_map,
                "research_plan_validation_status": research_plan_validation_status,
            }
        else:
            history = state["investment_debate_state"].get("history", "")
            investment_debate_state = state["investment_debate_state"]

            prompt = f"""作为投资组合经理和辩论主持人，您的职责是批判性地评估这轮辩论并做出明确决策：支持看跌分析师、看涨分析师，或者仅在基于所提出论点有强有力理由时选择持有。

简洁地总结双方的关键观点，重点关注最有说服力的证据或推理。您的建议——买入、卖出或持有——必须明确且可操作。避免仅仅因为双方都有有效观点就默认选择持有；要基于辩论中最强有力的论点做出承诺。

此外，为交易员制定详细的投资计划。这应该包括：

您的建议：基于最有说服力论点的明确立场。
理由：解释为什么这些论点导致您的结论。
战略行动：实施建议的具体步骤。
📊 目标价格分析：基于所有可用报告（基本面、新闻、情绪），提供全面的目标价格区间和具体价格目标。考虑：
- 基本面报告中的基本估值
- 新闻对价格预期的影响
- 情绪驱动的价格调整
- 技术支撑/阻力位
- 风险调整价格情景（保守、基准、乐观）
- 价格目标的时间范围（1个月、3个月、6个月）
💰 您必须提供具体的目标价格 - 不要回复"无法确定"或"需要更多信息"。

考虑您在类似情况下的过去错误。利用这些见解来完善您的决策制定，确保您在学习和改进。以对话方式呈现您的分析，就像自然说话一样，不使用特殊格式。

以下是您对错误的过去反思：
\"{past_memory_str}\"

标的约束：
{instrument_context}

以下是综合分析报告：
市场研究：{market_research_report}

持仓分析：{sentiment_report}

新闻分析：{news_report}

基本面分析：{fundamentals_report}

以下是辩论：
辩论历史：
{history}

请用中文撰写所有分析内容和建议。"""

        # 📊 统计 prompt 大小
        prompt_length = len(prompt)
        estimated_tokens = int(prompt_length / 1.8)

        logger.info(f"📊 [Research Manager] Prompt 统计:")
        logger.info(f"   - 辩论历史长度: {len(history)} 字符")
        logger.info(f"   - 总 Prompt 长度: {prompt_length} 字符")
        logger.info(f"   - 估算输入 Token: ~{estimated_tokens} tokens")

        # ⏱️ 记录开始时间
        start_time = time.time()

        response = llm.invoke(prompt)

        # ⏱️ 记录结束时间
        elapsed_time = time.time() - start_time

        # 📊 统计响应信息
        response_length = len(response.content) if response and hasattr(response, 'content') else 0
        estimated_output_tokens = int(response_length / 1.8)

        logger.info(f"⏱️ [Research Manager] LLM调用耗时: {elapsed_time:.2f}秒")
        logger.info(f"📊 [Research Manager] 响应统计: {response_length} 字符, 估算~{estimated_output_tokens} tokens")

        new_investment_debate_state = {
            "judge_decision": response.content,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": response.content,
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": response.content,
        }

    return research_manager_node
