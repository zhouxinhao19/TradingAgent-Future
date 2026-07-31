"""
_base.py — Commodity analyst 公共逻辑 (Phase 3b-ii)

提供 4 个 commodity analyst 节点共享的工具:
  - load_features:从 state['commodity_features'] 读取 3b-i features 层输出
  - empty_report:features 缺失/数据不足时返回中性 Markdown 报告
  - truncate_snapshot:截断 snapshot 到 top-N 字段,降 LLM prompt 长度
  - quality_gate:根据 quality.rows 判断是否走空结果分支
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import re

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


def empty_report(direction: str = "neutral", reason: str = "", custom_data_context: str = "") -> str:
    """降级返回:features 缺失或质量不足时返回简短 Markdown 报告。

    Args:
        direction: bullish/bearish/neutral,默认中性
        reason: 数据缺失的具体原因,会写进报告
        custom_data_context: 保留参数(不再追加到 skip 报告中,避免 skip 时数据噪音)

    Returns:
        Markdown 字符串,适合直接落到 state['xxx_report']
    """
    if not reason:
        reason = "特征层数据为空"
    direction_cn = {"bullish": "看多", "bearish": "看空", "neutral": "中性"}.get(direction, direction)
    report = (
        f"**{direction_cn} | 数据缺失**\n\n"
        f"{reason},跳过本分析师。\n\n"
        f"建议结合其他分析师(基本面/持仓/新闻)综合判断。\n"
    )
    return report


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


# Analyst ID 前缀常量
ANALYST_PREFIXES = {
    "technical": "TECH",
    "fundamental": "FUND",
    "position": "POSN",
    "news": "NEWS",
}


def make_analyst_id(prefix: str, full_symbol: str, trade_date: str, seed: str = "") -> str:
    """生成稳定、可追溯的 analyst 报告 ID。

    ID 格式: REF-{PREFIX}-{sha256前缀8位}
    确定性: 相同 full_symbol + trade_date + seed 产生相同 ID。

    Args:
        prefix: TECH / FUND / POSN / NEWS
        full_symbol: 合约代码(如 RB2501.SHF)
        trade_date: 交易日期
        seed: 额外种子,默认空; fallback/empty 路径传入区分

    Returns:
        str, 形如 "REF-TECH-a1b2c3d4"
    """
    import hashlib

    raw = f"{full_symbol}|{trade_date}|{prefix}|{seed}"
    h = hashlib.sha256(raw.encode()).hexdigest()[:8]
    return f"REF-{prefix}-{h}"


def inject_analyst_id(report_md: str, analyst_id: str) -> str:
    """在 Markdown 报告头部注入 HTML 注释形式的 ID 标记。

    Args:
        report_md: 原始 Markdown 报告
        analyst_id: 形如 REF-TECH-a1b2c3d4

    Returns:
        注入 ID 标记后的 Markdown
    """
    return f"<!-- ANALYST-ID: {analyst_id} -->\n\n{report_md}"


ANALYST_CN_NAMES = {
    "technical": "技术分析师",
    "fundamental": "基本面分析师",
    "position": "持仓分析师",
    "news": "新闻分析师",
}


def make_conclusion_id(prefix: str, index: int = 1) -> str:
    """生成简短结论 ID，格式: {prefix_lower}_conc_{index}

    示例: "tech_conc_1", "fund_conc_1"

    Args:
        prefix: TECH / FUND / POSN / NEWS
        index: 结论序号，同一 analyst 有多条结论时递增

    Returns:
        str, 形如 "tech_conc_1"
    """
    return f"{prefix.lower()}_conc_{index}"


def make_registry_entry(
    analyst_id: str,
    conclusion_id: str,
    prefix: str,
    analyst_key: str,
    report_key: str,
    direction: str,
    summary: str,
    status: str = "ok",
    validation_status: Optional[str] = None,
) -> dict:
    """构造标准化的 analyst registry entry。

    Args:
        analyst_id: make_analyst_id() 生成的 hash ID (REF-TECH-xxx)
        conclusion_id: make_conclusion_id() 生成的结论 ID (tech_conc_1)
        prefix: TECH / FUND / POSN / NEWS
        analyst_key: "technical" / "fundamental" / "position" / "news"
        report_key: "market_report" / "fundamentals_report" / "position_report" / "news_report"
        direction: 方向信号
        summary: 摘要文本
        status: "ok" | "degraded" | "skipped" — Phase Agent 改造(2026-07-19)
        validation_status: P0 字段（Day 5 接入）— Pydantic 校验结果
            None | "skipped" | "passed" | "failed" | "legacy" | "degraded"
            - None/"skipped": 主路径未启用校验（feature flag off 或 fallback 跳过）
            - "passed": 校验通过，标准化产物落库
            - "failed": 校验失败，降级 legacy 路径
            - "legacy": feature flag off，走原 _extract_json_safe 路径
            - "degraded": LLM 不可用 / 数据缺失等非 schema 问题

    Returns:
        dict, 单键值对: {analyst_id: {id, conclusion_id, prefix, analyst, cn_name,
                                     report_key, direction, summary, status, validation_status}}
    """
    cn_name = ANALYST_CN_NAMES.get(analyst_key, analyst_key)
    return {
        analyst_id: {
            "id": analyst_id,
            "conclusion_id": conclusion_id,
            "prefix": prefix,
            "analyst": analyst_key,
            "cn_name": cn_name,
            "report_key": report_key,
            "direction": direction,
            "summary": summary,
            "status": status,
            "validation_status": validation_status,
        }
    }


def extract_first_sentence(text: str) -> str:
    """从 Markdown 报告中提取第一句有意义的句子作摘要。"""
    # 去掉 ID 标记行
    cleaned = re.sub(r'<!--.*?-->', '', text).strip()
    # 取第一个有意义的行,最多 80 字
    for line in cleaned.split("\n"):
        line = line.strip()
        line = line.lstrip("#").strip()
        if line and len(line) > 3:
            return line[:80]
    return "(无摘要)"


def build_custom_data_context(features: dict) -> str:
    """提取用户数据摘要，按 feature_dict 是否有切换注入方式（低权重 + 交叉验证）。

    三态分支:
      ① parsed=False → ""
      ② feature_dict 存在 → 新 prompt（"低权重参考 + 交叉验证 + [USER_DATA_CONFLICT] 标注"）
      ③ 仅 raw_summaries 存在 → 老 guardrail（无结构化观测时的历史序列护栏）
    """
    custom_data = features.get("custom_data", {})
    if not isinstance(custom_data, dict) or not custom_data.get("parsed"):
        return ""

    feature_dict = custom_data.get("feature_dict")
    summary_text = custom_data.get("summary_text", "")
    raw_summaries = custom_data.get("raw_summaries")

    if feature_dict:
        return _build_feature_dict_context(feature_dict, custom_data)
    if raw_summaries or summary_text:
        return _build_legacy_context(summary_text, raw_summaries, features)
    return ""


def _build_feature_dict_context(feature_dict: dict, custom_data: dict) -> str:
    """feature_dict 存在时的 prompt 注入：低权重 + 交叉验证 + 矛盾标注。"""
    latest = feature_dict.get("latest", {}) or {}
    snapshot = feature_dict.get("snapshot", {}) or {}
    quality = feature_dict.get("quality", {}) or {}
    signals = feature_dict.get("signals", []) or []

    header = (
        "【用户上传数据 · 低权重参考】\n"
        "本数据为用户提供，系统对来源/口径/时点不做保证。引用规则:\n"
        "  1) 必须与系统 features 中至少 1 个模块交叉验证，方向一致才可引用；\n"
        "  2) 不得单独作为决策依据；不得仅据此声称当前趋势；\n"
        "  3) 若与系统数据方向冲突，需在结论中标注 [USER_DATA_CONFLICT]；\n"
        "  4) 若无 as_of 或 LLM 解析失败，仅可作为背景描述。\n"
    )

    body_parts: List[str] = []
    cv = snapshot.get("current_value")
    if cv is not None:
        label = snapshot.get("current_value_label") or "值"
        as_of = snapshot.get("as_of") or "未知"
        body_parts.append(f"用户提供当前观测 [{label}]={cv} (as_of={as_of})")
    sp = snapshot.get("self_pctl_180d")
    if sp is not None:
        body_parts.append(f"自身历史分位(180d)={float(sp):.0f}%")
    sm = snapshot.get("system_pctl_180d")
    if sm is not None:
        mm = snapshot.get("matched_module") or "?"
        delta = snapshot.get("delta_pctl")
        delta_text = f" (差={float(delta):.0f}%)" if delta is not None else ""
        body_parts.append(
            f"对应系统模块 [{mm}] 分位={float(sm):.0f}%{delta_text}"
        )

    body = "\n".join(f"- {line}" for line in body_parts) or "- (无可用观测)"

    signal_text = ""
    if signals:
        signal_text = "\n系统解读:\n" + "\n".join(f"  · {s}" for s in signals[:3])

    quality_text = ""
    reason = quality.get("reason")
    if reason:
        quality_text = f"\n数据质量提示: {reason}"
    if not quality.get("has_as_of", True):
        quality_text += "\n⚠️ 缺少 as_of, 本数据仅可作背景, 不可作当前趋势依据。"

    return f"{header}\n当前观测:\n{body}{signal_text}{quality_text}"


def _build_legacy_context(
    summary_text: str,
    raw_summaries: Any,
    features: dict,
) -> str:
    """老 guardrail 行为（无结构化观测，沿用历史时序护栏）。"""
    has_verified_current = False
    is_historical_series = False
    if isinstance(raw_summaries, list):
        for summary in raw_summaries:
            if not isinstance(summary, dict):
                continue
            time_columns = summary.get("time_columns")
            date_range = summary.get("date_range")
            if (isinstance(time_columns, list) and time_columns) or (
                isinstance(date_range, dict)
                and (date_range.get("min") or date_range.get("max"))
            ):
                is_historical_series = True
            has_current_value = (
                _has_nonempty_value(summary.get("latest_observation"))
                or _has_nonempty_value(summary.get("current_value"))
            )
            if has_current_value and _has_nonempty_value(summary.get("as_of")):
                has_verified_current = True

    if has_verified_current:
        guardrail = (
            "【用户上传数据使用约束】仅可把带 as_of 的 latest_observation/"
            "current_value 视为对应时点观测；不得把全局统计或样本行冒充当前值。"
        )
    elif is_historical_series:
        guardrail = (
            "【用户上传数据使用约束】该文件是历史时间序列，但摘要只包含历史统计、"
            "时间范围和前几行样本。无法获取当前时点数值，无法判断趋势。只能引用"
            "历史均值、极值、分位数和样本区间；禁止据此声称当前去库/补库、当前上升/"
            "下降或趋势将延续。"
        )
    else:
        guardrail = (
            "【用户上传数据使用约束】摘要未提供可验证的当前时点值及 as_of，"
            "不得推断当前趋势；只能引用摘要中明确给出的统计特征。"
        )

    comparison_lines = _build_cross_market_comparison(features, raw_summaries)
    comparison_text = (
        "\n【跨市场比价】\n" + "\n".join(comparison_lines) + "\n"
    ) if comparison_lines else ""

    return f"{guardrail}\n{summary_text}\n{comparison_text}"


def _has_nonempty_value(value: Any) -> bool:
    """判断结构化最新值字段是否真实存在，保留数值 0。"""
    if value is None or value == "":
        return False
    if isinstance(value, (dict, list, tuple, set)):
        return bool(value)
    return True


# =============================================================================
# 自定义数据跨市场对比（修改点 5）
# =============================================================================


def _match_system_module(summary: Dict[str, Any]) -> Optional[str]:
    """根据上传文件列名/标签推断对应的系统模块。

    返回: "inventory" / "basis" / "positioning" / None
    """
    label = str(summary.get("label", "")).lower()
    columns = [str(c).lower() for c in summary.get("columns", [])]
    text = f"{label} {' '.join(columns)}"
    if any(kw in text for kw in ("库存", "inventory", "stock", "warehouse", "仓单")):
        return "inventory"
    if any(kw in text for kw in ("价格", "price", "现货", "spot", "基差", "basis")):
        return "basis"
    if any(kw in text for kw in ("持仓", "position", "oi", "open_interest", "净多", "净空")):
        return "positioning"
    return None


def _estimate_percentile_from_summary(latest_obs: Any, summary: Dict[str, Any]) -> Optional[float]:
    """从摘要的 min/max/mean 估算自定义数据当前值在自身历史中的分位。"""
    try:
        val = float(latest_obs)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    stats = summary.get("statistics", {}) if isinstance(summary.get("statistics"), dict) else {}
    lo = stats.get("min")
    hi = stats.get("max")
    try:
        lo_f = float(lo) if lo is not None else None
        hi_f = float(hi) if hi is not None else None
    except (TypeError, ValueError):
        return None
    if lo_f is not None and hi_f is not None and hi_f > lo_f:
        return (val - lo_f) / (hi_f - lo_f) * 100
    return None


def _get_system_latest(features: Dict[str, Any], module: str) -> Any:
    """从 features 中取系统模块的最新值（不做方向判断，只取原始数值）。"""
    block = features.get(module, {})
    if not isinstance(block, dict):
        return None
    snap = block.get("snapshot", {})
    if not isinstance(snap, dict):
        return None
    if module == "inventory":
        return snap.get("inventory_value")
    if module == "basis":
        return snap.get("near_basis_rate") or snap.get("basis_pctl_180d")
    if module == "positioning":
        return snap.get("crowding_pctl_180d")
    return None


def _get_system_percentile(features: Dict[str, Any], module: str) -> Optional[float]:
    """从 features 中取系统模块的分位数（0-100）。"""
    block = features.get(module, {})
    if not isinstance(block, dict):
        return None
    snap = block.get("snapshot", {})
    if not isinstance(snap, dict):
        return None
    if module == "inventory":
        return snap.get("inventory_pctl_180d")
    if module == "positioning":
        return snap.get("crowding_pctl_180d")
    if module == "basis":
        return snap.get("basis_pctl_180d")
    return None


def _build_cross_market_comparison(
    features: Dict[str, Any],
    raw_summaries: List[Any],
) -> List[str]:
    """构建自定义数据与系统数据的跨市场比价行。"""
    lines: List[str] = []
    for summary in (raw_summaries or []):
        if not isinstance(summary, dict):
            continue
        latest_obs = summary.get("latest_observation") or summary.get("current_value")
        as_of = summary.get("as_of")
        if not (_has_nonempty_value(latest_obs) and _has_nonempty_value(as_of)):
            continue

        matched = _match_system_module(summary)
        if not matched:
            continue

        custom_pctl = _estimate_percentile_from_summary(latest_obs, summary)
        sys_pctl = _get_system_percentile(features, matched)

        label = summary.get("label") or summary.get("name", "自定义数据")
        pct_str = ""
        if custom_pctl is not None and sys_pctl is not None:
            diff = custom_pctl - sys_pctl
            relative = "高位" if diff > 20 else "低位" if diff < -20 else "一致"
            pct_str = (
                f"自身历史分位={custom_pctl:.0f}%, "
                f"系统{matched}分位={sys_pctl:.0f}%, "
                f"跨数据比价: 自定义数据处于相对{relative}"
            )
        elif custom_pctl is not None:
            pct_str = f"自身历史分位={custom_pctl:.0f}% (无系统分位对比)"

        line = (
            f"[FACT-CUSTOM] {label} 最新值={latest_obs}"
            f"({'  ' + pct_str if pct_str else '无可用分位'})"
        )
        lines.append(line)
    return lines


# =============================================================================
# 事实卡片 — 从 features 提取关键数值事实
# =============================================================================


def _nested(obj: Any, *keys: str, default: Any = None) -> Any:
    """安全嵌套取值，不存在返回 default。"""
    for key in keys:
        if not isinstance(obj, dict):
            return default
        obj = obj.get(key)
        if obj is None:
            return default
    return obj


def _fmt(val: Any, unit: str = "") -> str:
    """格式化数值用于陈述。"""
    if val is None:
        return "N/A"
    try:
        f = float(val)
        if abs(f) >= 1e4:
            return f"{f:.0f}{unit}"
        if abs(f) >= 1:
            return f"{f:.2f}{unit}"
        return f"{f:.4f}{unit}"
    except (TypeError, ValueError):
        return str(val)


def build_fact_cards(
    features: Dict[str, Any],
    position_structured: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """从 commodity_features 各模块中提取关键数值事实。

    每个模块提取 1-3 个可验证的事实卡片，格式:
    {
        "id": "FACT-INV-001",
        "module": "inventory",
        "statement": "SHFE铜库存周降 8,758吨，处于 1.5% 历史分位",
        "metric": "inventory_value",
        "value": 89000,
        "unit": "吨",
        "percentile": 1.5,
        "source": "AKShare",
        "direction": "bullish",
    }
    """
    cards: List[Dict[str, Any]] = []
    counter: Dict[str, int] = {
        "technical": 0, "basis": 0, "inventory": 0,
        "positioning": 0, "term_structure": 0, "news_sentiment": 0,
    }
    seq = 0

    if not isinstance(features, dict):
        return cards

    # ---- 1. Technical ----
    tech = features.get("technical", {})
    if isinstance(tech, dict):
        snap = _nested(tech, "main_continuous", "daily", "snapshot")
        combined = tech.get("combined", {})
        if isinstance(snap, dict):
            score = snap.get("composite_score")
            trend = snap.get("trend")
            if score is not None:
                seq += 1
                counter["technical"] += 1
                cards.append({
                    "id": f"FACT-TECH-{seq:03d}",
                    "module": "technical",
                    "statement": f"技术综合评分={_fmt(score)}，趋势={trend or '未知'}",
                    "metric": "composite_score",
                    "value": score,
                    "unit": "",
                    "source": "features.technical",
                    "direction": "bullish" if isinstance(score, (int, float)) and score > 0 else "bearish" if isinstance(score, (int, float)) and score < 0 else "neutral",
                })
            vol = combined.get("volatility", {})
            if isinstance(vol, dict):
                atr = vol.get("atr_ratio_pctl180")
                regime = vol.get("regime")
                if atr is not None:
                    seq += 1
                    direction = ("bearish" if isinstance(regime, str) and regime.lower() == "high"
                                  else "neutral")
                    cards.append({
                        "id": f"FACT-TECH-{seq:03d}",
                        "module": "technical",
                        "statement": f"ATR比率分位={_fmt(atr, '%')}，波动率区间={regime or '未知'}",
                        "metric": "atr_ratio_pctl180",
                        "value": atr,
                        "unit": "%",
                        "source": "features.technical",
                        "direction": direction,
                    })

        oi_div = combined.get("oi_divergence")
        if oi_div:
            seq += 1
            direction = "bullish" if oi_div == "confirm" else "bearish"
            cards.append({
                "id": f"FACT-TECH-{seq:03d}",
                "module": "technical",
                "statement": f"价仓关系={oi_div}",
                "metric": "oi_divergence",
                "value": oi_div,
                "unit": "",
                "source": "features.technical",
                "direction": direction,
            })

    # ---- 2. Basis ----
    basis = features.get("basis", {})
    if isinstance(basis, dict):
        latest = basis.get("latest", {})
        if isinstance(latest, dict):
            near_rate = latest.get("near_basis_rate")
            if near_rate is not None:
                seq += 1
                direction = ("bullish" if isinstance(near_rate, (int, float)) and near_rate > 0
                              else "bearish")
                cards.append({
                    "id": f"FACT-BASIS-{seq:03d}",
                    "module": "basis",
                    "statement": f"近月基差率={_fmt(near_rate)}",
                    "metric": "near_basis_rate",
                    "value": near_rate,
                    "unit": "",
                    "source": "features.basis",
                    "direction": direction,
                })
            dom_rate = latest.get("dom_basis_rate")
            if dom_rate is not None:
                seq += 1
                cards.append({
                    "id": f"FACT-BASIS-{seq:03d}",
                    "module": "basis",
                    "statement": f"远月基差率={_fmt(dom_rate)}",
                    "metric": "dom_basis_rate",
                    "value": dom_rate,
                    "unit": "",
                    "source": "features.basis",
                    "direction": "neutral",
                })
        snap = basis.get("snapshot", {})
        if isinstance(snap, dict):
            pctl = snap.get("basis_pctl_180d")
            if pctl is not None:
                seq += 1
                direction = ("bullish" if isinstance(pctl, (int, float)) and pctl > 50
                              else "bearish")
                cards.append({
                    "id": f"FACT-BASIS-{seq:03d}",
                    "module": "basis",
                    "statement": f"基差历史分位(180d)={_fmt(pctl, '%')}",
                    "metric": "basis_pctl_180d",
                    "value": pctl,
                    "unit": "%",
                    "source": "features.basis",
                    "direction": direction,
                })

    # ---- 3. Inventory ----
    inv = features.get("inventory", {})
    if isinstance(inv, dict):
        snap = inv.get("snapshot", {})
        if isinstance(snap, dict):
            value = snap.get("inventory_value")
            change = snap.get("weekly_change")
            pctl = snap.get("inventory_pctl_180d")
            if value is not None:
                seq += 1
                direction = ("bullish" if isinstance(pctl, (int, float)) and pctl < 30
                              else "bearish" if isinstance(pctl, (int, float)) and pctl > 70
                              else "neutral")
                change_text = f"，周变化={_fmt(change)}" if change is not None else ""
                cards.append({
                    "id": f"FACT-INV-{seq:03d}",
                    "module": "inventory",
                    "statement": f"库存={_fmt(value)}万{change_text}，分位={_fmt(pctl, '%') if pctl is not None else 'N/A'}",
                    "metric": "inventory_value",
                    "value": value,
                    "unit": "万",
                    "percentile": pctl,
                    "source": "features.inventory",
                    "direction": direction,
                })

    # ---- 4. Positioning ----
    pos = features.get("positioning", {})
    if isinstance(pos, dict):
        snap = pos.get("snapshot", {})
        top_positions = pos.get("top_positions", [])
        if isinstance(snap, dict):
            long_pct = snap.get("long_pct")
            short_pct = snap.get("short_pct")
            pctl = snap.get("crowding_pctl_180d")
            if long_pct is not None and short_pct is not None:
                seq += 1
                long_f = float(long_pct)
                short_f = float(short_pct)
                direction = "bullish" if long_f > short_f else "bearish"
                cards.append({
                    "id": f"FACT-POSN-{seq:03d}",
                    "module": "positioning",
                    "statement": f"多空比={long_f:.1f}%/{short_f:.1f}%，拥挤分位={_fmt(pctl, '%') if pctl is not None else 'N/A'}",
                    "metric": "long_pct",
                    "value": long_f,
                    "unit": "%",
                    "percentile": pctl,
                    "source": "features.positioning",
                    "direction": direction,
                })
        if isinstance(top_positions, list) and top_positions:
            seq += 1
            top_str = "; ".join(
                f"{p.get('rank','?')}:{p.get('long_pct',0):.0f}%" if isinstance(p, dict) else str(p)
                for p in top_positions[:3]
            )
            cards.append({
                "id": f"FACT-POSN-{seq:03d}",
                "module": "positioning",
                "statement": f"前{len(top_positions[:3])}席位: {top_str}",
                "metric": "top_positions",
                "value": top_positions[:3] if isinstance(top_positions, list) else [],
                "unit": "",
                "source": "features.positioning",
                "direction": "neutral",
            })

    # ---- 5. Term Structure ----
    ts = features.get("term_structure", {})
    if isinstance(ts, dict):
        snap = ts.get("snapshot", {})
        if isinstance(snap, dict):
            structure = snap.get("structure")
            carry = snap.get("carry_score")
            if structure:
                seq += 1
                direction = ("bullish" if isinstance(structure, str) and "backwardation" in structure.lower()
                              else "bearish" if isinstance(structure, str) and "contango" in structure.lower()
                              else "neutral")
                cards.append({
                    "id": f"FACT-TS-{seq:03d}",
                    "module": "term_structure",
                    "statement": f"期限结构={structure}，carry_score={_fmt(carry) if carry is not None else 'N/A'}",
                    "metric": "structure",
                    "value": structure,
                    "unit": "",
                    "source": "features.term_structure",
                    "direction": direction,
                })

    # ---- 6. News Sentiment ----
    ns = features.get("news_sentiment", {})
    if isinstance(ns, dict):
        composite_score = ns.get("composite_score")
        if composite_score is not None:
            seq += 1
            direction = ("bullish" if isinstance(composite_score, (int, float)) and composite_score > 0
                          else "bearish" if isinstance(composite_score, (int, float)) and composite_score < 0
                          else "neutral")
            cards.append({
                "id": f"FACT-NEWS-{seq:03d}",
                "module": "news_sentiment",
                "statement": f"新闻情感综合评分={_fmt(composite_score)}",
                "metric": "composite_score",
                "value": composite_score,
                "unit": "",
                "source": "features.news_sentiment",
                "direction": direction,
            })

    # ---- 7. Custom Data（用户上传数据，低权重参考） ----
    custom_data = features.get("custom_data", {}) if isinstance(features, dict) else {}
    feature_dict = custom_data.get("feature_dict") if isinstance(custom_data, dict) else None
    if isinstance(feature_dict, dict):
        seq += 1
        snapshot = feature_dict.get("snapshot", {}) or {}
        cards.append({
            "id": f"FACT-CUSTOM-{seq:03d}",
            "module": "custom_data",
            "statement": (
                f"用户上传数据 [{snapshot.get('current_value_label', '值')}]"
                f"={snapshot.get('current_value', 'N/A')}, "
                f"as_of={snapshot.get('as_of', '未知')}, "
                f"自身分位={snapshot.get('self_pctl_180d', 'N/A')}%"
            ),
            "metric": "current_value",
            "value": snapshot.get("current_value"),
            "unit": "",
            "percentile": snapshot.get("self_pctl_180d"),
            "source": "features.custom_data",
            "direction": feature_dict.get("_direction", "neutral"),
        })

    # ---- 8. Cross-validation（用户上传数据与系统 features 定量对比） ----
    for _cv_module in ("inventory", "basis", "positioning"):
        _cv_block = features.get(_cv_module) if isinstance(features, dict) else None
        if not isinstance(_cv_block, dict):
            continue
        _cv = _cv_block.get("cross_validation")
        if not isinstance(_cv, dict):
            continue
        _cv_val = _cv.get("value")
        if _cv_val is None:
            continue
        seq += 1
        _cv_label = _cv.get("label") or "值"
        _cv_as_of = _cv.get("as_of") or "未知"
        _cv_files = ", ".join(_cv.get("file_names", []))
        _cv_pctl = _cv.get("percentile")
        _cv_pctl_str = f"，自身分位={float(_cv_pctl):.0f}%" if _cv_pctl is not None else ""
        cards.append({
            "id": f"FACT-CROSS-{seq:03d}",
            "module": _cv_module,
            "statement": (
                f"用户上传 [{_cv_label}]={_cv_val}{_cv_pctl_str}"
                f" (as_of={_cv_as_of}, 文件: {_cv_files})"
            ),
            "metric": f"cross_validation.{_cv_label}",
            "value": _cv_val,
            "unit": "",
            "percentile": _cv_pctl,
            "source": "features.custom_data",
            "direction": _cv.get("direction", "neutral"),
        })

    return cards


def _build_contradiction_map(
    fact_cards: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    """基于事实卡片的方向对立关系自动构建矛盾地图。

    规则：只有同属不同模块、方向相反（bullish vs bearish）的事实卡片对才构成矛盾。
    至少需要矛盾双方各有 ≥1 个事实。
    """
    bullish = [c for c in fact_cards if c.get("direction") == "bullish"]
    bearish = [c for c in fact_cards if c.get("direction") == "bearish"]

    contradictions: List[Dict[str, str]] = []
    seen_pairs: set = set()
    for b_card in bullish:
        for br_card in bearish:
            if b_card["module"] == br_card["module"]:
                continue
            pair_key = f"{b_card['module']}|{br_card['module']}"
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            contradictions.append({
                "利多": f"{b_card['id']}: {b_card['statement']} [{b_card['module']}]",
                "利空": f"{br_card['id']}: {br_card['statement']} [{br_card['module']}]",
                "矛盾": f"{br_card['module']}偏空 vs {b_card['module']}偏多",
            })
    return contradictions[:6]


__all__ = [
    "load_features",
    "empty_report",
    "truncate_snapshot",
    "quality_gate",
    "get_full_symbol",
    "MIN_ROWS_THRESHOLD",
    "SNAPSHOT_MAX_KEYS",
    "make_analyst_id",
    "make_conclusion_id",
    "make_registry_entry",
    "inject_analyst_id",
    "extract_first_sentence",
    "build_custom_data_context",
    "build_fact_cards",
    "_build_contradiction_map",
    "ANALYST_PREFIXES",
    "ANALYST_CN_NAMES",
]