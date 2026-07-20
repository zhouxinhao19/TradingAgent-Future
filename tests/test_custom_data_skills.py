"""
测试 skills 模块: loader (.md 解析) + registry (SkillsRegistry)
"""

from pathlib import Path
import tempfile
import os

import pytest

from tradingagents.agents.custom_data.skills.loader import Skill, load_skill_from_md
from tradingagents.agents.custom_data.skills.registry import SkillsRegistry


class TestLoadSkillFromMd:
    def test_valid_skill_md(self):
        """解析合法的 .md skill 文件"""
        md_content = """---
name: test-skill
title: 测试技能
description: 测试用
input:
  content_types: [tabular]
  suggested_columns: [date, value]
---

## 分析框架
数据摘要: {data_summary}
用户上下文: {user_context}
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(md_content)
            fpath = f.name
        try:
            skill = load_skill_from_md(Path(fpath))
            assert skill is not None
            assert skill.name == "test-skill"
            assert skill.title == "测试技能"
            assert skill.content_types == ["tabular"]
            assert skill.suggested_columns == ["date", "value"]
        finally:
            os.unlink(fpath)

    def test_missing_frontmatter(self):
        """缺少 frontmatter 返回 None"""
        md_content = "Just plain text\n{data_summary}"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(md_content)
            fpath = f.name
        try:
            skill = load_skill_from_md(Path(fpath))
            assert skill is None
        finally:
            os.unlink(fpath)

    def test_render_template(self):
        """渲染 prompt 模板"""
        skill = Skill(
            name="test",
            prompt_template="Data: {data_summary}\nCtx: {user_context}",
        )
        result = skill.render(data_summary="hello", user_context="world")
        assert "Data: hello" in result
        assert "Ctx: world" in result

    def test_render_with_content_types(self):
        """渲染时注入 content_types"""
        skill = Skill(
            name="test",
            prompt_template="Types: {content_types}",
        )
        result = skill.render(content_types=["tabular", "pdf"])
        assert "tabular, pdf" in result

    def test_matches_content_types_wildcard(self):
        """content_types=['*'] 匹配所有"""
        skill = Skill(name="test", content_types=["*"])
        assert skill.matches_content_types(["tabular", "pdf"])
        assert skill.matches_content_types(["image"])


class TestSkillsRegistry:
    def test_load_skill(self):
        """从 definitions 目录加载特定 skill"""
        registry = SkillsRegistry()
        skill = registry.load("general-analysis")
        assert skill is not None
        assert skill.name == "general-analysis"
        assert skill.title == "通用数据分析"

    def test_list_skills(self):
        """列出所有 skill"""
        registry = SkillsRegistry()
        skills = registry.list_skills()
        assert len(skills) >= 5
        names = [s["name"] for s in skills]
        assert "general-analysis" in names
        assert "inventory-analysis" in names
        assert "time-series" in names
        assert "seasonal" in names
        assert "benchmark" in names

    def test_load_nonexistent(self):
        """加载不存在的 skill 返回 None"""
        registry = SkillsRegistry()
        skill = registry.load("nonexistent-skill-123")
        assert skill is None

    def test_find_by_content_types(self):
        """按 content_types 匹配"""
        registry = SkillsRegistry()
        matched = registry.find_by_content_types(["tabular"])
        assert len(matched) >= 1
        # general-analysis 有 content_types=["*"] 应匹配所有
    def test_reload(self):
        """重新加载"""
        registry = SkillsRegistry()
        before = len(registry.list_skills())
        registry.reload()
        after = len(registry.list_skills())
        assert before == after
