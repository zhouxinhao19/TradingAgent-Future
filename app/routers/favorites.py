"""
自选品种统一 API 路由
前缀: /api/favorites
同时支持股票(stock)和商品期货(commodity)
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.routers.auth_db import get_current_user
from app.core.response import ok
from app.services.favorite_service import favorite_service
from app.models.favorite import FavoriteItem

logger = None
try:
    from tradingagents.utils.logging_manager import get_logger
    logger = get_logger('favorites')
except ImportError:
    import logging
    logger = logging.getLogger('favorites')

router = APIRouter(prefix="/favorites", tags=["自选品种"])


# ---- Request/Response 模型 ----

class AddFavoriteRequest(BaseModel):
    asset_type: str = Field(..., pattern="^(stock|commodity)$", description="资产类型")
    stock_code: Optional[str] = Field(default=None, description="股票代码")
    stock_name: Optional[str] = Field(default=None, description="股票名称")
    market: Optional[str] = Field(default=None, description="市场类型")
    full_symbol: Optional[str] = Field(default=None, description="商品合约代码")
    commodity_name: Optional[str] = Field(default=None, description="商品名称")
    exchange: Optional[str] = Field(default=None, description="交易所代码")
    category: Optional[str] = Field(default=None, description="品类")
    display_name: Optional[str] = Field(default=None, description="展示名称")
    tags: List[str] = Field(default_factory=list, description="标签")
    notes: str = Field(default="", description="备注")
    alert_price_high: Optional[float] = Field(default=None, description="价格上限提醒")
    alert_price_low: Optional[float] = Field(default=None, description="价格下限提醒")
    snapshot_price: Optional[float] = Field(default=None, description="添加时价格快照")


class UpdateFavoriteRequest(BaseModel):
    tags: Optional[List[str]] = Field(default=None, description="标签")
    notes: Optional[str] = Field(default=None, description="备注")
    alert_price_high: Optional[float] = Field(default=None, description="价格上限提醒")
    alert_price_low: Optional[float] = Field(default=None, description="价格下限提醒")
    display_name: Optional[str] = Field(default=None, description="展示名称")


class BatchRemoveRequest(BaseModel):
    ids: List[str] = Field(..., description="要删除的自选ID列表")


# ---- 端点 ----

@router.get("")
async def list_favorites(
    asset_type: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """获取当前用户自选列表。可选 ?asset_type=stock|commodity 过滤"""
    try:
        items = await favorite_service.list_favorites(
            user_id=current_user["id"],
            asset_type=asset_type,
        )
        return ok(items)
    except Exception as e:
        logger.error(f"获取自选列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", status_code=201)
async def add_favorite(
    payload: AddFavoriteRequest,
    current_user: dict = Depends(get_current_user),
):
    """添加自选品种"""
    try:
        item = FavoriteItem(
            user_id=current_user["id"],
            asset_type=payload.asset_type,  # type: ignore
            stock_code=payload.stock_code,
            stock_name=payload.stock_name,
            market=payload.market,
            full_symbol=payload.full_symbol,
            commodity_name=payload.commodity_name,
            exchange=payload.exchange,
            category=payload.category,
            display_name=payload.display_name or "",
            tags=payload.tags,
            notes=payload.notes,
            alert_price_high=payload.alert_price_high,
            alert_price_low=payload.alert_price_low,
            snapshot_price=payload.snapshot_price,
        )
        result = await favorite_service.add_favorite(
            user_id=current_user["id"], item=item
        )
        return ok(result, "添加成功")
    except Exception as e:
        err_msg = str(e)
        if "dup key" in err_msg or "duplicate" in err_msg.lower():
            raise HTTPException(status_code=409, detail="该品种已在自选列表中")
        logger.error(f"添加自选失败: {e}")
        raise HTTPException(status_code=400, detail=err_msg)


@router.delete("/{favorite_id}")
async def remove_favorite(
    favorite_id: str,
    current_user: dict = Depends(get_current_user),
):
    """删除自选品种"""
    success = await favorite_service.remove_favorite(
        favorite_id=favorite_id, user_id=current_user["id"]
    )
    if not success:
        raise HTTPException(status_code=404, detail="自选记录不存在")
    return ok(None, "删除成功")


@router.put("/{favorite_id}")
async def update_favorite(
    favorite_id: str,
    payload: UpdateFavoriteRequest,
    current_user: dict = Depends(get_current_user),
):
    """更新自选品种（标签/备注/价格提醒）"""
    updates = {k: v for k, v in payload.model_dump(exclude_none=True).items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="无更新内容")
    result = await favorite_service.update_favorite(
        favorite_id=favorite_id, user_id=current_user["id"], updates=updates
    )
    if not result:
        raise HTTPException(status_code=404, detail="自选记录不存在或无权操作")
    return ok(result, "更新成功")


@router.post("/batch-remove")
async def batch_remove_favorites(
    payload: BatchRemoveRequest,
    current_user: dict = Depends(get_current_user),
):
    """批量删除自选"""
    count = await favorite_service.batch_remove(
        user_id=current_user["id"], ids=payload.ids
    )
    return ok({"deleted": count}, f"已删除 {count} 条记录")
