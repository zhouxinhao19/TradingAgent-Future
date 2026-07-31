"""
schemas.py — Manager & CIO 节点输出版 Pydantic Schema（Phase P0）

与 node_outputs.py 同源设计：
  - ManagerDecision: research_manager 输出（投资计划）
  - InvestmentMemo: investment_director 输出（CIO 决策）

设计意图：
  1. 研究经理（research_manager）输出含大量中文 JSON key（估值驱动矩阵 / 多空对照表 /
     三种情景推演），Pydantic 校验用 Dict[str, Any] 兜住嵌套字段
  2. 投研总监（investment_director）输出有 3 个固定顶级 key：
     投研备忘录 / 风险评估卡 / research_brief
     最外层结构硬约束，内部 Dict 兜住
  3. research_brief 上限 2000 字（plan 写 1500，实测 LLM 2000-3000 字常见，2000 平衡）
"""
from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field


class BaseManagerSchema(BaseModel):
    """公共基类：extra="forbid" + 严格校验"""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )


class ManagerDecision(BaseManagerSchema):
    """LLM 输出硬约束 — research_manager（投资计划）

    字段映射（参考 research_manager.py:COMMODITY_REASONING_PROMPT）：
      - 估值驱动矩阵: {分析时间, 合约, 维度: [...], 综合估值判断, 核心驱动, 主要风险}
      - 多空对照表: {关键分歧: [...], 看涨核心逻辑, 看跌核心逻辑, 综合判断}
      - 三种情景推演: {保守情景, 基准情景, 乐观情景}
    """

    估值驱动矩阵: Dict[str, Any] = Field(default_factory=dict)
    多空对照表: Dict[str, Any] = Field(default_factory=dict)
    三种情景推演: Dict[str, Any] = Field(default_factory=dict)
    主要风险: List[str] = Field(default_factory=list, max_length=20)


class InvestmentMemo(BaseManagerSchema):
    """LLM 输出硬约束 — investment_director（CIO 决策）

    字段映射（参考 investment_director.py:INVESTMENT_DIRECTOR_SYSTEM_PROMPT）：
      - 投研备忘录: {估值审核, 情景裁决, 投研结论}
      - 风险评估卡: {三方视角, 风险裁定, 风险提示}
      - research_brief: Markdown 字符串（2000 字以内，平衡 plan 1500 与 LLM 实际输出）
    """

    投研备忘录: Dict[str, Any] = Field(default_factory=dict)
    风险评估卡: Dict[str, Any] = Field(default_factory=dict)
    research_brief: str = Field("", max_length=2000)


__all__ = [
    "InvestmentMemo",
    "ManagerDecision",
]