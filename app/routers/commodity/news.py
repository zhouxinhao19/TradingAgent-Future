"""
大宗商品新闻路由(Phase 3a)
- GET /api/commodity/news?category=...&limit=...
- GET /api/commodity/news/categories
- POST /api/commodity/news/refresh  手动触发一次拉取+标注(worker 卡死时用)
- 数据由 UnifiedCommodityService.get_futures_news() 提供(Phase 2 已实现)
- 任何失败返 [],绝不抛 500
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Query, BackgroundTasks

from app.core.response import ok
from app.services.commodity.unified_commodity_service import service

logger = logging.getLogger("webapi")
router = APIRouter(prefix="/commodity/news", tags=["commodity-news"])


@router.get("/categories", response_model=dict, summary="新闻分类清单")
async def get_news_categories():
    """
    返回所有可用新闻分类(含 6 主类 + shmet 9 细分类 + global_macro)。

    Path: GET /api/commodity/news/categories
    """
    items = await service.get_news_categories()
    return ok(data={"items": items, "count": len(items)}, message="获取新闻分类成功")


@router.get("", response_model=dict, summary="期货新闻拉取")
async def get_news(
    category: str = Query("all", description="分类(见 /news/categories)"),
    limit: int = Query(50, ge=1, le=500, description="条目数 1-500,默认 50"),
    variety: Optional[str] = Query(None, description="品种代码(如 CU),按 relevant_varieties 筛选"),
):
    """
    获取期货新闻(支持按品种筛选)。

    Path: GET /api/commodity/news?category=metal&limit=30
    Path: GET /api/commodity/news?variety=CU&limit=20
    """
    items = await service.get_futures_news(category=category, limit=limit, variety=variety)
    return ok(
        data={"items": items, "count": len(items), "category": category, "limit": limit},
        message=f"获取 {category} 新闻成功",
    )


@router.post("/refresh", response_model=dict, summary="手动触发新闻拉取+标注")
async def refresh_news(background: BackgroundTasks):
    """手动触发一次新闻拉取+LLM标注(worker 周期任务卡死时备用)。

    Path: POST /api/commodity/news/refresh
    """
    from app.services.commodity.news_ingestion import _ingest_and_annotate

    async def _run():
        try:
            count = await _ingest_and_annotate()
            logger.info(f"✅ 手动刷新完成: {count} 条新标注")
        except Exception as e:
            logger.error(f"❌ 手动刷新失败: {e}")

    background.add_task(_run)
    return ok(message="已触发新闻刷新,稍后查询 /api/commodity/news 查看")
