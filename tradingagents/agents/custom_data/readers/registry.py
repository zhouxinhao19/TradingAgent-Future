"""
registry.py — ReaderRegistry：按文件扩展名注册和派发 Reader

用法:
    ReaderRegistry.register(".xlsx", TabularReader)
    content = ReaderRegistry.read("/path/to/file.xlsx")

扩展: 新增 .pdf/.png 只需注册对应 Reader 类，不需改引擎。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Dict, Type

from tradingagents.utils.logging_init import get_logger

if TYPE_CHECKING:
    from tradingagents.agents.custom_data.content import Content

logger = get_logger("default")


class UnsupportedFormatError(ValueError):
    """不支持的扩展名错误。"""

    def __init__(self, ext: str):
        self.ext = ext
        super().__init__(f"不支持的文件格式: {ext}")


class ReaderRegistry:
    """文件阅读器注册表。单例模式，扩展名 → Reader 类映射。"""

    _readers: Dict[str, Type] = {}

    @classmethod
    def register(cls, extension: str, reader_cls: Type) -> None:
        """注册 reader 类到指定扩展名。

        Args:
            extension: 文件扩展名（含点号，如 ".xlsx"）
            reader_cls: Reader 类（需有 read(file_path) → Content 方法）
        """
        ext = extension.lower().strip()
        cls._readers[ext] = reader_cls
        logger.debug(f"ReaderRegistry: 注册 {ext} → {reader_cls.__name__}")

    @classmethod
    def read(cls, file_path: str) -> "Content":
        """读取文件，根据扩展名自动派发。

        Args:
            file_path: 文件绝对路径

        Returns:
            Content 子类实例

        Raises:
            UnsupportedFormatError: 扩展名未注册
        """
        ext = Path(file_path).suffix.lower()
        reader_cls = cls._readers.get(ext)
        if not reader_cls:
            raise UnsupportedFormatError(ext)
        logger.info(f"ReaderRegistry: 读取 {file_path} → {reader_cls.__name__}")
        return reader_cls().read(file_path)

    @classmethod
    def supported_extensions(cls) -> list[str]:
        """返回所有已注册的扩展名列表。"""
        return sorted(cls._readers.keys())

    @classmethod
    def clear(cls) -> None:
        """清空注册表（仅测试用）。"""
        cls._readers = {}


__all__ = ["ReaderRegistry", "UnsupportedFormatError"]
