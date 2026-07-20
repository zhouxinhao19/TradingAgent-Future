"""
readers/__init__.py — 导出 ReaderRegistry + 内置注册
"""

from .registry import ReaderRegistry, UnsupportedFormatError
from .tabular_reader import TabularReader

# 内置注册
ReaderRegistry.register(".xlsx", TabularReader)
ReaderRegistry.register(".xls", TabularReader)
ReaderRegistry.register(".csv", TabularReader)

__all__ = ["ReaderRegistry", "UnsupportedFormatError", "TabularReader"]
