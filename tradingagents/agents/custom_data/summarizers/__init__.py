"""
summarizers/__init__.py — 导出 SummarizerRegistry + 内置注册
"""

from .registry import SummarizerRegistry
from .tabular_summarizer import TabularSummarizer

# 内置注册
SummarizerRegistry.register("tabular", TabularSummarizer)

__all__ = ["SummarizerRegistry", "TabularSummarizer"]
