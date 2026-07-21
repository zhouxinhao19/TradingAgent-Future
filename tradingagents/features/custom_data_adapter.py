"""
custom_data_adapter.py — 自定义数据适配层

将用户上传的数据文件解析为结构化摘要,注入 commodity_features["custom_data"],
供 4 个 L1 分析师在 prompt 中引用。

两阶段解析(Phase 自定义数据升级):
  1) 同步阶段:读文件 + 纯统计摘要(零 LLM, 行为兼容 parse_custom_data)
  2) 异步阶段(可选):quick-thinking LLM 调用,识别表格类型 + 提取当前观测 + 推断方向,
     产出与 inventory/basis 同级的标准 feature dict(latest/stats/signals/snapshot/quality)

用法:
    # 旧接口(同步, 无 LLM)
    features["custom_data"] = parse_custom_data(file_paths, skill_name, user_context)

    # 新接口(异步, 含 LLM 调用, 推荐生产路径)
    features["custom_data"] = await parse_custom_data_async(file_paths, llm, skill_name, user_context)
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, List, Optional

from tradingagents.agents.custom_data.readers import ReaderRegistry
from tradingagents.agents.custom_data.summarizers import SummarizerRegistry
from tradingagents.utils.logging_init import get_logger

logger = get_logger("default")


# =============================================================================
# 同步入口(向后兼容, 零 LLM)
# =============================================================================


def parse_custom_data(
    file_paths: List[str],
    skill_name: str = "general-analysis",
    user_context: str = "",
    max_summary_chars: int = 8000,
) -> Dict[str, Any]:
    """同步解析上传数据文件,返回结构化摘要(无 LLM 调用)。

    向后兼容入口:老调用方/老测试继续可用;新生产路径应改用 parse_custom_data_async
    以获得标准 feature_dict。

    Args:
        file_paths: 文件绝对路径列表
        skill_name: 技能名称(用于标注)
        user_context: 用户上下文描述
        max_summary_chars: summary 文本截断长度

    Returns:
        dict,形如:
        {
            "parsed": True,
            "summary_text": "...",        # 格式化后的纯文本摘要
            "content_type": "tabular",
            "file_count": 2,
            "file_names": ["a.xlsx"],
            "skill_name": "inventory-analysis",
            "user_context": "...",
            "feature_dict": None,          # 同步版本恒为 None
            ...
        }
        如果所有文件都解析失败,返回 {"parsed": False, "error": "..."}
    """
    from pathlib import Path

    contents: list = []
    errors: list = []
    file_names: list = []

    for fp in file_paths:
        try:
            content = ReaderRegistry.read(fp)
            if content.validate():
                contents.append(content)
                file_names.append(Path(fp).name)
                logger.info(f"[custom_data_adapter] 读取成功: {fp}")
            else:
                errors.append(f"{Path(fp).name}: 内容无效(空数据)")
        except Exception as e:
            errors.append(f"{Path(fp).name}: {e}")
            logger.warning(f"[custom_data_adapter] 读取失败: {fp}: {e}")

    if not contents:
        error_msg = f"所有文件读取失败: {'; '.join(errors)}"
        logger.warning(f"[custom_data_adapter] {error_msg}")
        return {
            "parsed": False,
            "error": error_msg,
            "file_count": len(file_paths),
            "file_names": [],
            "summary_text": "",
            "content_type": "",
            "skill_name": skill_name,
            "user_context": user_context,
            "feature_dict": None,
        }

    # 生成摘要
    summaries: list = []
    for c in contents:
        s = SummarizerRegistry.summarize(c)
        summaries.append(s)

    # 格式化摘要文本(纯文本, 供注入 prompt)
    summary_text = _format_summaries(summaries, file_names, user_context, max_summary_chars)

    content_types = list({s.get("type", "unknown") for s in summaries})

    return {
        "parsed": True,
        "error": None,
        "file_count": len(contents),
        "file_names": file_names,
        "content_type": content_types[0] if content_types else "unknown",
        "skill_name": skill_name,
        "user_context": user_context,
        "summary_text": summary_text,
        "raw_summaries": summaries,
        "feature_dict": None,  # 同步版本无 LLM, 不生成 feature_dict
    }


# =============================================================================
# 异步入口(含 LLM, 推荐生产路径)
# =============================================================================


async def parse_custom_data_async(
    file_paths: List[str],
    llm: Any,
    skill_name: str = "general-analysis",
    user_context: str = "",
    max_summary_chars: int = 8000,
    llm_timeout_s: float = 20.0,
) -> Dict[str, Any]:
    """异步解析上传数据文件,调用 1 次 quick-thinking LLM 提取观测值。

    Args:
        file_paths: 文件绝对路径列表
        llm: LangChain chat model(已 _wrap_llm_with_retry);若为 None 则降级为同步版本
        skill_name: 技能名称(用于标注)
        user_context: 用户上下文描述
        max_summary_chars: summary 文本截断长度
        llm_timeout_s: LLM 调用超时(秒)

    Returns:
        dict,包含原有字段 + 新增 feature_dict 字段(标准 feature 模块 schema)
        feature_dict 为 None 表示 LLM 失败/超时/无 LLM,调用方应走老 guardrail 路径
    """
    # 1) 同步解析(读文件 + 统计摘要)
    base_result = parse_custom_data(
        file_paths=file_paths,
        skill_name=skill_name,
        user_context=user_context,
        max_summary_chars=max_summary_chars,
    )

    # 解析失败或无文件:不调用 LLM
    if not base_result.get("parsed"):
        base_result["feature_dict"] = None
        return base_result

    # 无 LLM 或调用方显式传 None:降级为同步版本
    if llm is None:
        base_result["feature_dict"] = None
        base_result["_llm_skipped"] = True
        return base_result

    # 2) 调用 LLM(带超时)
    summaries = base_result.get("raw_summaries", [])
    llm_response, llm_ok = await _call_llm_for_observation(
        llm=llm,
        summaries=summaries,
        user_context=user_context,
        timeout=llm_timeout_s,
    )

    # 3) 构建标准 feature dict;仅在 LLM 真正成功且有有效方向/观测时产出
    if llm_ok and llm_response.get("matched_module") not in (None, "other", ""):
        feature_dict = _build_feature_dict(
            summaries=summaries,
            llm_response=llm_response,
            user_context=user_context,
        )
    elif llm_ok:
        # matched_module=other 但 LLM 调用本身成功:仍生成最小可用 feature_dict
        feature_dict = _build_feature_dict(
            summaries=summaries,
            llm_response=llm_response,
            user_context=user_context,
        )
    else:
        feature_dict = None

    base_result["feature_dict"] = feature_dict
    base_result["_llm_response"] = llm_response if llm_ok else None
    return base_result


# =============================================================================
# LLM 调用
# =============================================================================


_LLM_SYSTEM_PROMPT = """你是大宗商品数据观察助手。任务是识别用户上传表格的结构并提取"当前时点"的客观观测。
你只输出 JSON,不要额外解释,不要预测未来,不要给出方向建议。

输出 JSON Schema(严格遵守):
{
  "interpretation_type": "tabular_timeseries | tabular_snapshot | text_table | unknown",
  "matched_module": "inventory | basis | positioning | news | other",
  "current_observation": {<列名>: <数值>, ...},   // 当前时点观测,可空对象
  "as_of": "YYYY-MM-DD | null",                    // 与 current_observation 对应的时点
  "direction": "bullish | bearish | neutral",      // 仅根据 current_observation 与自身历史对比的客观方向
  "direction_confidence": 0.0,                     // 0-1,无法判断时填 0
  "reasoning": "1-2 句中文, 说明识别结果",         // 不超过 80 字
  "warning": ""                                    // 数据异常/缺 as_of/无法识别时填原因
}

注意:
- direction 必须与 current_observation 客观一致, 不引入外部判断
- 若数据没有明确时点或样本不足, direction=neutral, warning 解释
- 若无法识别为已知模块, matched_module=other, direction=neutral
- matched_module=other 时, 不要尝试从 LLM 推导方向"""


async def _call_llm_for_observation(
    llm: Any,
    summaries: List[Dict[str, Any]],
    user_context: str,
    timeout: float = 20.0,
) -> tuple:
    """调用 quick-thinking LLM 提取观测值;失败/超时时返回 (fallback, False)。

    Returns:
        (response_dict, success_flag) — success=False 时 response 是 fallback,
        调用方应将 feature_dict 置 None。
    """
    fallback = {
        "interpretation_type": "unknown",
        "matched_module": "other",
        "current_observation": {},
        "as_of": None,
        "direction": "neutral",
        "direction_confidence": 0.0,
        "reasoning": "",
        "warning": "LLM 调用失败, 使用中性 fallback",
    }

    if not summaries:
        fallback["warning"] = "无文件摘要"
        return fallback, False

    payload = _format_llm_prompt_payload(summaries, user_context)
    messages = _build_llm_messages(payload)

    content: Any = None
    try:
        # 优先用 ainvoke;若无则降级到 invoke(同线程阻塞)再交 asyncio.wait_for 截断
        if hasattr(llm, "ainvoke"):
            coro = llm.ainvoke(messages)
            content = await asyncio.wait_for(coro, timeout=timeout)
        elif callable(getattr(llm, "invoke", None)):
            content = await asyncio.wait_for(
                asyncio.to_thread(llm.invoke, messages),
                timeout=timeout,
            )
        else:
            logger.warning("[custom_data_adapter] LLM 既无 ainvoke 也无 invoke, fallback")
            fallback["warning"] = "LLM 接口不可用"
            return fallback, False
    except asyncio.TimeoutError:
        logger.warning(f"[custom_data_adapter] LLM 调用超时(>{timeout}s), fallback")
        fallback["warning"] = f"LLM 超时(>{timeout}s)"
        return fallback, False
    except Exception as e:
        logger.warning(f"[custom_data_adapter] LLM 调用异常: {e}, fallback")
        fallback["warning"] = f"LLM 异常: {type(e).__name__}"
        return fallback, False

    # 安全提取 content
    if hasattr(content, "content"):
        text = content.content
        if not isinstance(text, str):
            text = str(text) if text is not None else ""
    else:
        text = str(content) if content is not None else ""

    parsed = _parse_llm_json(text)
    if parsed is None:
        fallback["warning"] = "LLM 输出非 JSON"
        return fallback, False

    # 字段规范化
    direction = parsed.get("direction", "neutral")
    if direction not in ("bullish", "bearish", "neutral"):
        direction = "neutral"
    return (
        {
            "interpretation_type": parsed.get("interpretation_type", "unknown"),
            "matched_module": parsed.get("matched_module", "other"),
            "current_observation": parsed.get("current_observation", {}) or {},
            "as_of": parsed.get("as_of"),
            "direction": direction,
            "direction_confidence": _safe_float(parsed.get("direction_confidence", 0.0)) or 0.0,
            "reasoning": str(parsed.get("reasoning", ""))[:200],
            "warning": str(parsed.get("warning", ""))[:200],
        },
        True,
    )


def _build_llm_messages(payload: str) -> List[Dict[str, str]]:
    """构造 LangChain ChatPromptTemplate 兼容的 messages 列表。"""
    return [
        {"role": "system", "content": _LLM_SYSTEM_PROMPT},
        {"role": "user", "content": payload},
    ]


def _format_llm_prompt_payload(summaries: List[Dict[str, Any]], user_context: str) -> str:
    """构造 LLM 输入 payload(结构化 JSON, 节省 token)。"""
    file_meta: List[Dict[str, Any]] = []
    for s in summaries:
        if not isinstance(s, dict):
            continue
        cols = [c.get("name", "?") for c in (s.get("columns") or []) if isinstance(c, dict)]
        sample = s.get("sample") or []
        last_rows = sample[-5:] if isinstance(sample, list) else []
        stats = s.get("statistics") or {}
        stats_compact = {
            k: {
                "min": v.get("min"),
                "max": v.get("max"),
                "mean": v.get("mean"),
                "last": v.get("last"),
            }
            for k, v in list(stats.items())[:6]
            if isinstance(v, dict)
        }
        file_meta.append({
            "name": s.get("source", "unknown"),
            "rows": (s.get("overview") or {}).get("rows", 0),
            "cols": len(cols),
            "columns": cols[:15],
            "date_range": s.get("date_range") or {},
            "last_rows": last_rows,
            "statistics": stats_compact,
        })
    return json.dumps(
        {"file_meta": file_meta, "user_context": user_context or ""},
        ensure_ascii=False,
        default=str,
    )


def _parse_llm_json(text: str) -> Optional[Dict[str, Any]]:
    """解析 LLM 输出 JSON;允许 markdown 包裹和宽松匹配。"""
    if not text:
        return None
    text = text.strip()
    # 剥离 markdown 包裹
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except (json.JSONDecodeError, ValueError):
        pass
    # 抓首个 { ... } 块
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            obj = json.loads(brace_match.group(0))
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError):
            pass
    return None


# =============================================================================
# feature_dict 构建
# =============================================================================


def _build_feature_dict(
    summaries: List[Dict[str, Any]],
    llm_response: Dict[str, Any],
    user_context: str,
) -> Dict[str, Any]:
    """把 LLM 输出 + summaries 转成与 inventory/basis 同级的标准 feature dict。

    Returns:
        标准 schema dict,包含:
          latest / stats / signals / snapshot / quality
        + 私有字段 _direction / _direction_confidence / _interpretation_type / _llm_warning
    """
    from tradingagents.features import helpers

    current_obs = llm_response.get("current_observation") or {}
    as_of = llm_response.get("as_of")
    direction = llm_response.get("direction", "neutral")
    matched_module = llm_response.get("matched_module", "other")
    interpretation = llm_response.get("interpretation_type", "unknown")
    warning = llm_response.get("warning", "")
    reasoning = llm_response.get("reasoning", "")

    # 构造 latest
    latest: Dict[str, Any] = {}
    for k, v in current_obs.items():
        if v is None:
            continue
        latest[str(k)] = _safe_float(v)
    if as_of:
        latest["_as_of"] = str(as_of)

    # 找 summaries 中第一个数值列(用于 stats)
    stats: Dict[str, Any] = {"zscore_180d": None, "slope_20d": None, "percentile_180d": None}
    snapshot: Dict[str, Any] = {}
    quality: Dict[str, Any] = {
        "rows": 0,
        "coverage": 0.0,
        "data_freshness_days": None,
        "reason": "",
        "has_as_of": bool(as_of),
    }

    if summaries:
        first = summaries[0]
        if isinstance(first, dict):
            overview = first.get("overview") or {}
            quality["rows"] = overview.get("rows", 0) if isinstance(overview, dict) else 0
            missing_ratio = overview.get("missing_ratio", 0) if isinstance(overview, dict) else 0
            try:
                quality["coverage"] = 1.0 - float(missing_ratio)
            except (TypeError, ValueError):
                quality["coverage"] = 0.0

            # 尝试用 sample + statistics 构造 pandas Series 算 stats
            statistics = first.get("statistics") or {}
            value_col = None
            for k in statistics:
                if k in current_obs:
                    value_col = k
                    break
            if value_col is None and statistics:
                value_col = next(iter(statistics.keys()))

            if value_col and isinstance(statistics.get(value_col), dict):
                col_stats = statistics[value_col]
                # zscore / percentile: 用 min/max/mean 估(精度有限, 但足够定性)
                mn = _safe_float(col_stats.get("min"))
                mx = _safe_float(col_stats.get("max"))
                mean = _safe_float(col_stats.get("mean"))
                last_val = _safe_float(col_stats.get("last")) or _safe_float(current_obs.get(value_col))
                if mn is not None and mx is not None and mean is not None and last_val is not None:
                    # 用 min/max/mean 估算 std(range/4 近似)
                    approx_std = (mx - mn) / 4.0 if mx > mn else 0.0
                    if approx_std > 0:
                        stats["zscore_180d"] = (last_val - mean) / approx_std
                    # percentile_rank: 用 (last - min) / (max - min) 近似
                    if mx > mn:
                        stats["percentile_180d"] = (last_val - mn) / (mx - mn)

                snapshot["current_value"] = last_val
                snapshot["current_value_label"] = value_col

    # F2: as_of fallback — LLM 未提取出 as_of 时从摘要的 date_range.max 推断
    if not as_of and summaries:
        _first = summaries[0]
        if isinstance(_first, dict):
            _dr = _first.get("date_range") or {}
            _max = _dr.get("max") if isinstance(_dr, dict) else None
            if _max:
                as_of = str(_max)
                quality["has_as_of"] = True
                quality["reason"] = "as_of 从时间范围最大值推断"
                # 尝试计算 data_freshness_days
                import datetime as _dt  # noqa: PLC0415
                try:
                    _asof = _dt.date.fromisoformat(as_of)
                    quality["data_freshness_days"] = (_dt.date.today() - _asof).days
                except (ValueError, TypeError):
                    pass

    if as_of:
        snapshot["as_of"] = str(as_of)
    snapshot["matched_module"] = matched_module
    if stats.get("percentile_180d") is not None:
        try:
            snapshot["self_pctl_180d"] = round(float(stats["percentile_180d"]) * 100.0, 1)
        except (TypeError, ValueError):
            pass

    # signals: 1-2 条中文信号
    signals: List[str] = []
    if snapshot.get("current_value") is not None and snapshot.get("self_pctl_180d") is not None:
        pctl = snapshot["self_pctl_180d"]
        label = snapshot.get("current_value_label", "值")
        val = snapshot["current_value"]
        dir_cn = {"bullish": "偏多", "bearish": "偏空", "neutral": "中性"}.get(direction, "中性")
        signals.append(
            f"用户提供: {label}={val:.2f}, 处于自身历史 {pctl:.0f}% 分位({dir_cn})"
        )
    if reasoning:
        signals.append(f"用户数据 LLM 解读: {reasoning}")

    if not quality.get("has_as_of"):
        quality["reason"] = "缺少 as_of, 仅作背景参考"
    if warning:
        quality["reason"] = (quality.get("reason", "") + "; " + warning).strip("; ")

    return {
        "latest": latest,
        "stats": stats,
        "signals": signals,
        "snapshot": snapshot,
        "quality": quality,
        # 私有字段: 供 SafetyOverride 与 build_custom_data_context 使用
        "_direction": direction if direction in ("bullish", "bearish", "neutral") else "neutral",
        "_direction_confidence": float(llm_response.get("direction_confidence", 0.0) or 0.0),
        "_interpretation_type": interpretation,
        "_matched_module": matched_module,
        "_llm_warning": warning,
        "_user_context": user_context,
    }


def _safe_float(v: Any) -> Optional[float]:
    """安全转换为 float, 失败/None/NaN 返回 None。"""
    if v is None or v == "":
        return None
    try:
        f = float(v)
        import math
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


# =============================================================================
# 内部: 摘要格式化(原 parse_custom_data 依赖, 保留)
# =============================================================================


def _format_summaries(
    summaries: List[Dict[str, Any]],
    file_names: List[str],
    user_context: str = "",
    max_chars: int = 8000,
) -> str:
    """将结构化摘要列表格式化为纯文本段落。"""
    parts = ["【用户上传的自定义数据文件摘要】"]

    if user_context:
        parts.append(f"用户描述: {user_context}")

    if file_names:
        parts.append(f"文件: {', '.join(file_names)}")

    parts.append(f"文件数: {len(summaries)}")

    for i, s in enumerate(summaries):
        parts.append(f"\n--- 文件 {i + 1} ---")
        overview = s.get("overview", {})
        if overview:
            parts.append(f"行数: {overview.get('rows', 'N/A')} | "
                         f"列数: {overview.get('columns', 'N/A')} | "
                         f"缺失值: {overview.get('missing_cells', 'N/A')} "
                         f"({overview.get('missing_ratio', 'N/A')})")

        # 列信息
        columns = s.get("columns", [])
        col_names = [c.get("name", "?") for c in columns[:20]]
        parts.append(f"列: {', '.join(col_names)}")
        if len(columns) > 20:
            parts.append(f"... 共 {len(columns)} 列")

        # 时间范围
        date_range = s.get("date_range", {})
        if date_range.get("min") and date_range.get("max"):
            parts.append(f"时间范围: {date_range['min']} ~ {date_range['max']}")

        # 数值统计
        stats = s.get("statistics", {})
        if stats:
            stat_lines = []
            for col_name, col_stats in list(stats.items())[:8]:
                stat_lines.append(
                    f"{col_name}: mean={col_stats.get('mean', 'N/A')}, "
                    f"std={col_stats.get('std', 'N/A')}, "
                    f"min={col_stats.get('min', 'N/A')}, "
                    f"max={col_stats.get('max', 'N/A')}"
                )
            parts.append("关键统计:\n  " + "\n  ".join(stat_lines))
            if len(stats) > 8:
                parts.append(f"  ... 共 {len(stats)} 个数值列")

        # 警告
        warnings = s.get("warnings", [])
        if warnings:
            parts.append(f"数据质量警告: {'; '.join(warnings[:3])}")

        # 样本数据
        sample = s.get("sample", [])
        if sample:
            sample_str = json.dumps(sample[:3], ensure_ascii=False, default=str)
            parts.append(f"数据样例: {sample_str[:300]}")

    # 截断
    text = "\n".join(parts)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n...(摘要已截断)"
        logger.warning(f"[custom_data_adapter] 摘要截断至 {max_chars} 字符")

    return text


__all__ = [
    "parse_custom_data",
    "parse_custom_data_async",
    "_format_summaries",
    "_call_llm_for_observation",
    "_build_feature_dict",
]