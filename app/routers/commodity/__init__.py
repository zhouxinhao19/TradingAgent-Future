"""
大宗商品路由包入口
- Phase 1/3a: quotes + extended + news
- Phase 3b-ii: analysis (新增)
"""
from .quotes import router as quotes_router
from .extended import router as extended_router
from .news import router as news_router
from .analysis import router as analysis_router

__all__ = ["quotes_router", "extended_router", "news_router", "analysis_router"]

# 防止未使用警告
_ = (quotes_router, extended_router, news_router, analysis_router)
