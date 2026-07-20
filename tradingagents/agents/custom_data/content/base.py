"""
base.py — Content 抽象基类 (Custom Data Analyst Phase 1)

所有文件模态的抽象基类。新增一种模态只需继承 Content 并实现 validate()。
引擎(content/readers/summarizers)完全通过 Content.type_name 调度，无需改动。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class Content(ABC):
    """所有文件模态的抽象基类。

    Attributes:
        type_name: 模态标识，如 "tabular" | "pdf" | "image" | "audio"
        source_path: 原始文件路径
        metadata: 通用元数据，如 {"filename", "size", "ext", "uploaded_at"}
    """

    type_name: str = "unknown"
    source_path: str = ""
    metadata: Dict[str, Any] = {}

    @abstractmethod
    def validate(self) -> bool:
        """检查内容是否有效加载。子类必须实现。"""

    def to_dict(self) -> Dict[str, Any]:
        """序列化为 dict，供 skill prompt 注入。"""
        return {
            "type_name": self.type_name,
            "source_path": self.source_path,
            "metadata": self.metadata.copy(),
        }

    def __repr__(self) -> str:
        return f"<{self.type_name}({self.metadata.get('filename', self.source_path)})>"


__all__ = ["Content"]
