"""
tradingagents/agents/custom_data/ — 自定义数据文件分析师子包 (Phase Data Analyst)

可扩展的多模态架构:
  - content/: Content 类型系统（TabularContent / PDFContent / ImageContent）
  - readers/: 文件阅读器注册表（按扩展名派发）
  - summarizers/: 摘要器注册表（按 Content.type_name 派发）
  - engine.py: 模态无关的分析引擎
  - skills/: Skill .md 文件 -> 分析 prompt 模板

Phase 1: Tabular 支持 (.xlsx/.xls/.csv)
Phase 2+: PDF / 图片 / 音频（各需 3 个新文件 + 2 行注册）
"""

from .content import Content, TabularContent
from .engine import AnalysisResult, run_analysis
from .readers import ReaderRegistry, TabularReader, UnsupportedFormatError
from .skills import Skill, SkillsRegistry, load_skill_from_md
from .summarizers import SummarizerRegistry, TabularSummarizer

__all__ = [
    "Content",
    "TabularContent",
    "ReaderRegistry",
    "TabularReader",
    "UnsupportedFormatError",
    "SummarizerRegistry",
    "TabularSummarizer",
    "Skill",
    "SkillsRegistry",
    "load_skill_from_md",
    "AnalysisResult",
    "run_analysis",
]
