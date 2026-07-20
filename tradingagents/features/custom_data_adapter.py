"""
custom_data_adapter.py — 自定义数据适配层

将用户上传的数据文件解析为结构化摘要，注入 commodity_features["custom_data"]，
供 4 个 L1 分析师在 prompt 中引用。

用法:
    from tradingagents.features.custom_data_adapter import parse_custom_data
    features["custom_data"] = parse_custom_data(file_paths, skill_name, user_context)
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from tradingagents.agents.custom_data.readers import ReaderRegistry
from tradingagents.agents.custom_data.summarizers import SummarizerRegistry
from tradingagents.utils.logging_init import get_logger

logger = get_logger("default")


def parse_custom_data(
    file_paths: List[str],
    skill_name: str = "general-analysis",
    user_context: str = "",
    max_summary_chars: int = 8000,
) -> Dict[str, Any]:
    """解析上传数据文件，返回结构化摘要（无 LLM 调用）。

    Args:
        file_paths: 文件绝对路径列表
        skill_name: 技能名称（用于标注）
        user_context: 用户上下文描述
        max_summary_chars: summary 文本截断长度

    Returns:
        dict，形如:
        {
            "summary_text": "...",        # 格式化后的纯文本摘要
            "content_type": "tabular",    # 文件类型
            "file_count": 2,              # 文件数量
            "file_names": ["a.xlsx"],     # 文件名列表
            "skill_name": "inventory-analysis",
            "user_context": "...",
            "parsed": True,               # 是否成功解析
            "error": None,                # 错误信息
        }
        如果所有文件都解析失败，返回 {"parsed": False, "error": "..."}
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
                errors.append(f"{Path(fp).name}: 内容无效（空数据）")
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
        }

    # 生成摘要
    summaries: list = []
    for c in contents:
        s = SummarizerRegistry.summarize(c)
        summaries.append(s)

    # 格式化摘要文本（纯文本，供注入 prompt）
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
    }


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


__all__ = ["parse_custom_data"]