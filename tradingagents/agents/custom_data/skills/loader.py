"""
loader.py — Skill .md 文件加载器

解析 .md 文件的 frontmatter (YAML) + body，返回 Skill 对象。

Skill .md 格式:
---
name: inventory-analysis
title: 库存数据分析
description: 分析库存数据，判断累库/去库趋势
input:
  content_types: [tabular]
  suggested_columns: [date, 库存]
---

## 分析框架
...
{data_summary}
{user_context}
...
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from tradingagents.utils.logging_init import get_logger

logger = get_logger("default")


@dataclass
class Skill:
    """技能定义。"""

    name: str
    title: str = ""
    description: str = ""
    content_types: List[str] = field(default_factory=lambda: ["tabular"])
    suggested_columns: List[str] = field(default_factory=list)
    prompt_template: str = ""
    frontmatter: Dict[str, Any] = field(default_factory=dict)

    def render(
        self,
        data_summary: str = "",
        user_context: str = "",
        content_types: Optional[List[str]] = None,
    ) -> str:
        """渲染 prompt 模板，注入变量。

        Args:
            data_summary: 数据摘要 JSON 字符串
            user_context: 用户额外上下文
            content_types: 实际 Content 类型列表

        Returns:
            渲染后的完整 prompt 字符串
        """
        text = self.prompt_template
        text = text.replace("{data_summary}", data_summary)
        text = text.replace("{user_context}", user_context)

        if content_types:
            text = text.replace(
                "{content_types}",
                ", ".join(content_types),
            )
        if "{skill_name}" in text:
            text = text.replace("{skill_name}", self.name)
        if "{title}" in text:
            text = text.replace("{title}", self.title)

        return text

    def matches_content_types(self, content_types: List[str]) -> bool:
        """检查该 skill 是否匹配给定的内容类型。"""
        if not self.content_types or self.content_types == ["*"]:
            return True
        return any(ct in self.content_types for ct in content_types)


_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n(.*)",
    re.DOTALL,
)


def load_skill_from_md(file_path: Path) -> Optional[Skill]:
    """从 .md 文件解析 Skill。

    Args:
        file_path: .md 文件路径

    Returns:
        Skill 对象，解析失败返回 None
    """
    if not file_path.exists():
        logger.warning(f"Skill 文件不存在: {file_path}")
        return None
    if file_path.suffix.lower() != ".md":
        logger.warning(f"Skill 文件扩展名不是 .md: {file_path}")
        return None

    raw = file_path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(raw)
    if not match:
        logger.warning(f"Skill 文件缺少 frontmatter: {file_path}")
        return None

    frontmatter_raw = match.group(1)
    body = match.group(2).strip()

    try:
        frontmatter = yaml.safe_load(frontmatter_raw) or {}
    except yaml.YAMLError as e:
        logger.warning(f"Skill 文件 frontmatter YAML 解析失败: {file_path}: {e}")
        return None

    name = frontmatter.get("name", "")
    if not name:
        logger.warning(f"Skill 文件缺少 name 字段: {file_path}")
        return None

    input_config = frontmatter.get("input", {}) or {}

    return Skill(
        name=name,
        title=frontmatter.get("title", name),
        description=frontmatter.get("description", ""),
        content_types=input_config.get("content_types", ["*"]),
        suggested_columns=input_config.get("suggested_columns", []),
        prompt_template=body,
        frontmatter=frontmatter,
    )


__all__ = ["Skill", "load_skill_from_md"]
