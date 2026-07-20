"""
registry.py — SkillsRegistry：管理所有 Skill .md 文件

- 从 definitions/ 目录加载所有 .md skill 文件
- 按 name 查找
- 支持 content_type 匹配过滤
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .loader import Skill, load_skill_from_md
from tradingagents.utils.logging_init import get_logger

logger = get_logger("default")

# 内置 skill 定义目录
_DEFAULT_SKILLS_DIR = Path(__file__).resolve().parent / "definitions"


class SkillsRegistry:
    """Skill 注册表。从目录加载所有 .md 并缓存。"""

    def __init__(self, skills_dir: Optional[Path] = None):
        self._skills_dir = skills_dir or _DEFAULT_SKILLS_DIR
        self._skills: Dict[str, Skill] = {}
        self._loaded = False

    def _ensure_loaded(self):
        if self._loaded:
            return
        self._skills = {}
        if not self._skills_dir.exists():
            logger.warning(f"Skills 目录不存在: {self._skills_dir}")
            self._loaded = True
            return

        # 按 __index__.json 的顺序加载（如果存在）
        index_file = self._skills_dir / "__index__.json"
        ordered_names: List[str] = []
        if index_file.exists():
            try:
                index_data = json.loads(index_file.read_text(encoding="utf-8"))
                ordered_names = index_data if isinstance(index_data, list) else []
            except (json.JSONDecodeError, Exception):
                ordered_names = []

        # 先按 index 顺序
        for name in ordered_names:
            md_path = self._skills_dir / f"{name}.md"
            skill = load_skill_from_md(md_path)
            if skill:
                self._skills[skill.name] = skill

        # 再扫目录补全（index 未列出的）
        for md_path in sorted(self._skills_dir.glob("*.md")):
            if md_path.name == "__index__.md":
                continue
            skill = load_skill_from_md(md_path)
            if skill and skill.name not in self._skills:
                self._skills[skill.name] = skill

        logger.info(f"SkillsRegistry: 加载 {len(self._skills)} 个 skill 从 {self._skills_dir}")
        self._loaded = True

    def load(self, name: str) -> Optional[Skill]:
        """按名称加载 Skill。

        Args:
            name: skill 名称（如 "inventory-analysis"）

        Returns:
            Skill 对象，不存在返回 None
        """
        self._ensure_loaded()
        return self._skills.get(name)

    def list_skills(self) -> List[Dict[str, Any]]:
        """列出所有 skill 的基本信息。"""
        self._ensure_loaded()
        return [
            {
                "name": s.name,
                "title": s.title,
                "description": s.description,
                "content_types": s.content_types,
            }
            for s in self._skills.values()
        ]

    def find_by_content_types(self, content_types: List[str]) -> List[Skill]:
        """根据内容类型匹配 skill。"""
        self._ensure_loaded()
        return [
            s for s in self._skills.values()
            if s.matches_content_types(content_types)
        ]

    def reload(self):
        """重新加载（清空缓存）。"""
        self._skills = {}
        self._loaded = False
        self._ensure_loaded()

    @property
    def skill_names(self) -> List[str]:
        self._ensure_loaded()
        return list(self._skills.keys())


__all__ = ["SkillsRegistry"]
