"""
engine.py — Custom Data Analyst 核心引擎

模态无关的文件分析引擎。核心流程:
  1. 读取文件 → Content 对象（通过 ReaderRegistry 派发）
  2. 生成摘要 → dict（通过 SummarizerRegistry 派发）
  3. 加载 Skill → prompt 模板
  4. 构造 prompt → 调 LLM 或降级
  5. 返回 AnalysisResult

引擎中没有任何特定模态的 import（不出现在 import 层的 pandas/pdf/...）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from tradingagents.agents.custom_data.content import Content
from tradingagents.agents.custom_data.readers import ReaderRegistry
from tradingagents.agents.custom_data.skills.registry import SkillsRegistry
from tradingagents.agents.custom_data.summarizers import SummarizerRegistry
from tradingagents.utils.logging_init import get_logger

logger = get_logger("default")


@dataclass
class AnalysisResult:
    """分析结果。"""

    success: bool = True
    skill_name: str = "general-analysis"
    file_count: int = 0
    content_types: List[str] = field(default_factory=list)
    data_summary: str = ""  # JSON string of summaries
    report: str = ""  # LLM 生成的 Markdown 报告
    fallback: bool = False  # 是否走了降级路径（无 LLM）
    error: Optional[str] = None


def run_analysis(
    file_paths: List[str],
    skill_name: str = "general-analysis",
    llm: Any = None,
    skills_dir: Optional[Path] = None,
    user_context: str = "",
    max_summary_chars: int = 20000,
) -> AnalysisResult:
    """运行自定义数据文件分析。

    核心流程完全与文件模态无关。

    Args:
        file_paths: 文件绝对路径列表
        skill_name: 技能名称，默认兜底 "general-analysis"
        llm: LangChain 兼容的 LLM 实例。None 时走降级路径（只输出摘要）
        skills_dir: Skill .md 文件所在目录，默认用内置 definitions/
        user_context: 用户额外上下文描述
        max_summary_chars: summary JSON 截断字符数，防止 prompt 过长

    Returns:
        AnalysisResult
    """
    # ---- 1. 读取所有文件 → Content 对象 ----
    contents: List[Content] = []
    errors: List[str] = []
    for fp in file_paths:
        try:
            content = ReaderRegistry.read(fp)
            if content.validate():
                contents.append(content)
                logger.info(f"engine: 读取成功 {fp} → {content.type_name}")
            else:
                errors.append(f"{fp}: 内容无效（空数据）")
                logger.warning(f"engine: 读取成功但内容无效 {fp}")
        except Exception as e:
            errors.append(f"{fp}: {e}")
            logger.error(f"engine: 读取失败 {fp}: {e}")

    if not contents:
        return AnalysisResult(
            success=False,
            error=f"所有文件读取失败: {'; '.join(errors)}",
        )

    # ---- 2. 生成摘要 ----
    summaries: List[Dict[str, Any]] = []
    for c in contents:
        s = SummarizerRegistry.summarize(c)
        summaries.append(s)

    # ---- 3. 加载 Skill ----
    skill = SkillsRegistry(skills_dir=skills_dir).load(skill_name)
    if skill is None:
        logger.warning(f"engine: Skill '{skill_name}' 未找到，使用兜底 general-analysis")
        skill = SkillsRegistry(skills_dir=skills_dir).load("general-analysis")

    # ---- 4. 构造 prompt ----
    data_summary_json = json.dumps(summaries, ensure_ascii=False, indent=2, default=str)
    if len(data_summary_json) > max_summary_chars:
        logger.warning(f"engine: summary 过长 ({len(data_summary_json)} 字符)，截断至 {max_summary_chars}")
        n = min(3, len(summaries))
        truncated = json.dumps(summaries[:n], ensure_ascii=False, indent=2, default=str)
        truncated = truncated[:max_summary_chars] + "\n...(截断)"
        data_summary_json = truncated

    if skill:
        prompt_text = skill.render(
            data_summary=data_summary_json,
            user_context=user_context,
            content_types=[c.type_name for c in contents],
        )
    else:
        # 连兜底都没有：直接拼摘要
        prompt_text = _fallback_prompt(data_summary_json)

    # ---- 5. 调 LLM 或降级 ----
    if llm:
        try:
            result = llm.invoke([("human", prompt_text)])
            if hasattr(result, "content"):
                report = result.content
                if not isinstance(report, str):
                    report = str(report) if report is not None else ""
            else:
                report = str(result) if result is not None else ""

            if not report.strip():
                report = _fallback_report(data_summary_json)
                return AnalysisResult(
                    skill_name=skill_name,
                    file_count=len(contents),
                    content_types=[c.type_name for c in contents],
                    data_summary=data_summary_json,
                    report=report,
                    fallback=True,
                    error="LLM 返回空内容",
                )

            return AnalysisResult(
                skill_name=skill_name,
                file_count=len(contents),
                content_types=[c.type_name for c in contents],
                data_summary=data_summary_json,
                report=str(report),
                fallback=False,
            )
        except Exception as e:
            logger.error(f"engine: LLM 调用失败: {e}")
            report = _fallback_report(data_summary_json)
            return AnalysisResult(
                skill_name=skill_name,
                file_count=len(contents),
                content_types=[c.type_name for c in contents],
                data_summary=data_summary_json,
                report=report,
                fallback=True,
                error=f"LLM 异常: {e}",
            )
    else:
        # 无 LLM：纯降级
        report = _fallback_report(data_summary_json)
        return AnalysisResult(
            skill_name=skill_name,
            file_count=len(contents),
            content_types=[c.type_name for c in contents],
            data_summary=data_summary_json,
            report=report,
            fallback=True,
        )


def run_analysis_from_summaries(
    summaries: List[Dict[str, Any]],
    skill_name: str = "general-analysis",
    llm: Any = None,
    skills_dir: Optional[Path] = None,
    user_context: str = "",
    max_summary_chars: int = 20000,
) -> AnalysisResult:
    """使用已有 summaries 运行 LLM 分析，跳过文件读取步骤。

    用于 graph 节点：后端已通过 parse_custom_data() 完成文件解析和摘要，
    graph 节点直接调用此函数生成可读的 Markdown 报告。

    Args:
        summaries: parse_custom_data() 产出的 raw_summaries 列表
        skill_name: 技能名称，默认兜底 "general-analysis"
        llm: LangChain 兼容的 LLM 实例。None 时走降级路径
        skills_dir: Skill .md 文件所在目录
        user_context: 用户额外上下文描述
        max_summary_chars: summary JSON 截断字符数

    Returns:
        AnalysisResult
    """
    if not summaries:
        return AnalysisResult(
            success=False,
            error="无数据摘要",
        )

    # 加载 Skill
    skill = SkillsRegistry(skills_dir=skills_dir).load(skill_name)
    if skill is None:
        skill = SkillsRegistry(skills_dir=skills_dir).load("general-analysis")

    # 构造 prompt
    data_summary_json = json.dumps(summaries, ensure_ascii=False, indent=2, default=str)
    if len(data_summary_json) > max_summary_chars:
        n = min(3, len(summaries))
        truncated = json.dumps(summaries[:n], ensure_ascii=False, indent=2, default=str)
        data_summary_json = truncated[:max_summary_chars] + "\n...(截断)"

    content_types = [s.get("type", "tabular") for s in summaries]

    if skill:
        prompt_text = skill.render(
            data_summary=data_summary_json,
            user_context=user_context,
            content_types=content_types,
        )
    else:
        prompt_text = _fallback_prompt(data_summary_json)

    # 调 LLM 或降级
    if llm:
        try:
            result = llm.invoke([("human", prompt_text)])
            if hasattr(result, "content"):
                report = result.content
                if not isinstance(report, str):
                    report = str(report) if report is not None else ""
            else:
                report = str(result) if result is not None else ""

            if not report.strip():
                report = _fallback_report(data_summary_json)
                return AnalysisResult(
                    skill_name=skill_name,
                    file_count=len(summaries),
                    content_types=content_types,
                    data_summary=data_summary_json,
                    report=report,
                    fallback=True,
                    error="LLM 返回空内容",
                )

            return AnalysisResult(
                skill_name=skill_name,
                file_count=len(summaries),
                content_types=content_types,
                data_summary=data_summary_json,
                report=report,
                fallback=False,
            )
        except Exception as e:
            logger.error(f"engine: run_analysis_from_summaries LLM 失败: {e}")
            report = _fallback_report(data_summary_json)
            return AnalysisResult(
                skill_name=skill_name,
                file_count=len(summaries),
                content_types=content_types,
                data_summary=data_summary_json,
                report=report,
                fallback=True,
                error=f"LLM 异常: {e}",
            )

    # 无 LLM：纯降级
    report = _fallback_report(data_summary_json)
    return AnalysisResult(
        skill_name=skill_name,
        file_count=len(summaries),
        content_types=content_types,
        data_summary=data_summary_json,
        report=report,
        fallback=True,
    )


def _fallback_prompt(data_summary: str) -> str:
    """无 skill 文件时的兜底 prompt。"""
    return (
        f"你是一个数据文件分析师。以下是一个或多个数据文件的结构化摘要。\n\n"
        f"请据此进行分析，输出包含：\n"
        f"1. **数据概览**：文件数量、类型、规模\n"
        f"2. **关键字段**：列名、数据类型、时间范围\n"
        f"3. **数值统计**：均值、极值、分布特征\n"
        f"4. **发现与洞察**：趋势、异常、模式\n"
        f"5. **风险提示**：缺失值、数据稀疏性\n\n"
        f"--- 数据摘要 ---\n{data_summary}"
    )


def _fallback_report(data_summary: str) -> str:
    """无 LLM 时的降级报告。"""
    try:
        parsed = json.loads(data_summary)
        parts = []
        for i, item in enumerate(parsed):
            overview = item.get("overview", {})
            cols = item.get("columns", [])
            stats = item.get("statistics", {})
            date_range = item.get("date_range", {})
            parts.append(
                f"### 文件 {i + 1} ({item.get('type', 'unknown')})\n"
                f"- 行数: {overview.get('rows', 'N/A')}, 列数: {overview.get('columns', 'N/A')}\n"
                f"- 缺失值: {overview.get('missing_cells', 'N/A')} ({overview.get('missing_ratio', 'N/A')})\n"
                f"- 列: {', '.join(c['name'] for c in cols[:10])}\n"
                f"- 时间范围: {date_range.get('min', 'N/A')} ~ {date_range.get('max', 'N/A')}\n"
                f"- 数值列数: {len(stats)}\n"
            )
        summary = "\n".join(parts)
    except (json.JSONDecodeError, TypeError, KeyError):
        summary = data_summary[:2000]

    return (
        f"# 自定义数据分析报告（降级版本 - 无 LLM）\n\n"
        f"---\n\n"
        f"## 数据摘要\n\n"
        f"{summary}\n\n"
        f"---\n"
        f"_本报告由引擎直接生成，未经 LLM 文字总结。_\n"
        f"_LLM 可用后可重新提交以获得完整分析。_\n"
    )


__all__ = ["run_analysis", "run_analysis_from_summaries", "AnalysisResult"]
