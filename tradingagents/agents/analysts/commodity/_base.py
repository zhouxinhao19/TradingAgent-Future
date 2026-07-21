"""
_base.py — Commodity analyst 公共逻辑 (Phase 3b-ii)

提供 4 个 commodity analyst 节点共享的工具:
  - load_features:从 state['commodity_features'] 读取 3b-i features 层输出
  - empty_report:features 缺失/数据不足时返回中性 Markdown 报告
  - truncate_snapshot:截断 snapshot 到 top-N 字段,降 LLM prompt 长度
  - quality_gate:根据 quality.rows 判断是否走空结果分支
"""
from __future__ import annotations

from typing import Any, Dict, Optional

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

    Returns:
        dict, 单键值对: {analyst_id: {id, conclusion_id, prefix, analyst, cn_name, report_key, direction, summary, status}}
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
    """提取用户数据摘要，并明确限制历史时序数据的可推断范围。

    上传解析器当前只提供全量统计、时间范围和前几行样本；这些信息不能
    证明当前时点的数值或趋势。只有未来 schema 同时提供 latest_observation
    （或 current_value）与 as_of 时，才允许据此判断当前状态。
    """
    custom_data = features.get("custom_data", {})
    if not isinstance(custom_data, dict) or not custom_data.get("parsed"):
        return ""

    summary_text = custom_data.get("summary_text", "")
    if not summary_text:
        return ""

    raw_summaries = custom_data.get("raw_summaries")
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

    return f"{guardrail}\n{summary_text}\n"


def _has_nonempty_value(value: Any) -> bool:
    """判断结构化最新值字段是否真实存在，保留数值 0。"""
    if value is None or value == "":
        return False
    if isinstance(value, (dict, list, tuple, set)):
        return bool(value)
    return True


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
    "ANALYST_PREFIXES",
    "ANALYST_CN_NAMES",
]