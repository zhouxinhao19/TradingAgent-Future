"""
大宗商品新闻路由(Phase 3a)
- GET /api/commodity/news?category=...&limit=...
- GET /api/commodity/news/categories
- 数据由 UnifiedCommodityService.get_futures_news() 提供(Phase 2 已实现)
- 任何失败返 [],绝不抛 500
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Query

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
):
    """
    获取期货新闻(聚合多源)。

    Path: GET /api/commodity/news?category=metal&limit=30
    Path: GET /api/commodity/news?category=global_macro&limit=100

    字段统一:
      - published_at: ISO 字符串
      - title: 新闻标题(shmet 解析【标题】)
      - content: 正文
      - category: 标准化分类
      - sentiment: positive/negative/neutral
      - sentiment_score: -1.0 ~ 1.0
      - source: shmet / akshare_synth / macro_news_em / ...
      - url: 可选(仅 global_macro 才有)
    """
    items = await service.get_futures_news(category=category, limit=limit)
    return ok(
        data={"items": items, "count": len(items), "category": category, "limit": limit},
        message=f"获取 {category} 新闻成功",
    )
