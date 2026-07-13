"""
大宗商品路由包入口
- 统一导出 quotes router(Phase 1 最小)
- 主入口在 main.py 中按 feature flag 条件 include
"""
from .quotes import router as quotes_router

# Phase 1:只导出 quotes router(包含 info / quotes / historical / categories / exchanges)
# 后续 Phase 增加:
# - from .analysis import router as analysis_router   # Phase 2
# - from .paper_rules import router as paper_rules_router  # Phase 4

__all__ = ["quotes_router"]
