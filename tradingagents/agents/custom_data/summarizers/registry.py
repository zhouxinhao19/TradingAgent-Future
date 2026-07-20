"""
registry.py — SummarizerRegistry：按 Content.type_name 注册和派发 Summarizer

用法:
    SummarizerRegistry.register("tabular", TabularSummarizer)
    summary = SummarizerRegistry.summarize(content_object)

扩展: 新增 PDFContent 只需注册 PDFSummarizer，不需改引擎。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Type

from tradingagents.utils.logging_init import get_logger

if TYPE_CHECKING:
    from tradingagents.agents.custom_data.content import Content

logger = get_logger("default")


class SummarizerRegistry:
    """内容摘要器注册表。Content.type_name → Summarizer 类。"""

    _summarizers: Dict[str, Type] = {}

    @classmethod
    def register(cls, content_type: str, summarizer_cls: Type) -> None:
        """注册 summarizer 到指定 Content 类型。

        Args:
            content_type: Content.type_name（如 "tabular"）
            summarizer_cls: Summarizer 类（需有 summarize(content) → dict 方法）
        """
        cls._summarizers[content_type] = summarizer_cls
        logger.debug(f"SummarizerRegistry: 注册 {content_type} → {summarizer_cls.__name__}")

    @classmethod
    def summarize(cls, content: "Content") -> dict:
        """对 Content 对象生成结构化摘要 dict。

        Args:
            content: Content 子类实例

        Returns:
            dict，含基本信息 + 摘要字段
        """
        summarizer_cls = cls._summarizers.get(content.type_name)
        if not summarizer_cls:
            logger.warning(f"SummarizerRegistry: {content.type_name} 无注册摘要器，返回基础信息")
            return {
                "type": content.type_name,
                "summary": "(无摘要器)",
                "source": content.source_path,
            }
        try:
            return summarizer_cls().summarize(content)
        except Exception as e:
            logger.error(f"SummarizerRegistry: {content.type_name} 摘要异常: {e}")
            return {
                "type": content.type_name,
                "summary": f"(摘要异常: {e})",
                "source": content.source_path,
            }

    @classmethod
    def supported_types(cls) -> list[str]:
        """返回所有已注册的 Content 类型。"""
        return sorted(cls._summarizers.keys())

    @classmethod
    def clear(cls) -> None:
        """清空注册表（仅测试用）。"""
        cls._summarizers = {}


__all__ = ["SummarizerRegistry"]
