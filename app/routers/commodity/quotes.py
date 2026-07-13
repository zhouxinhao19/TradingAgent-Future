"""
大宗商品行情路由
- GET /api/commodity/{full_symbol}/info
- GET /api/commodity/{full_symbol}/quotes
- GET /api/commodity/{full_symbol}/historical
- GET /api/commodity/categories
- GET /api/commodity/exchanges
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, status, Query
from pydantic import BaseModel

from app.services.commodity.unified_commodity_service import service
from app.core.response import ok

logger = logging.getLogger("webapi")
router = APIRouter(prefix="/commodity", tags=["commodity"])


# ==================== 响应模型 ====================

class CommodityInfoResponse(BaseModel):
    full_symbol: str
    code: str
    name: str
    exchange: str
    exchange_name: str
    category: str
    underlying: str
    currency: str
    unit: str
    contract_size: float
    is_china_futures: bool
    is_international: bool
    is_spot_cn: bool
    data_source: str
    data_version: int
    updated_at: str


class CommodityQuotesResponse(BaseModel):
    full_symbol: str
    code: str
    exchange: str
    name: str
    category: str
    currency: str
    unit: str
    contract_size: float
    open: float
    high: float
    low: float
    close: float
    pre_close: float
    current_price: float
    settlement_price: float
    change: float
    pct_chg: float
    volume: int
    open_interest: int
    trade_date: str
    data_source: str
    updated_at: str


# ==================== 端点 ====================

@router.get("/categories", response_model=dict, summary="商品品类列表")
async def get_categories():
    """返回所有商品品类(贵金属/有色金属/能源/化工/农产品/金融)"""
    return ok(data=await service.get_categories(), message="获取品类成功")


@router.get("/exchanges", response_model=dict, summary="交易所列表")
async def get_exchanges():
    """返回所有商品交易所"""
    return ok(data=await service.get_exchanges(), message="获取交易所成功")


@router.get("/{full_symbol}/info", response_model=dict, summary="商品基础信息")
async def get_commodity_info(full_symbol: str):
    """
    获取大宗商品基础信息

    Path: GET /api/commodity/CU2501.SHF/info
    """
    info = await service.get_basic_info(full_symbol)
    if not info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"商品不存在或无法识别: {full_symbol}",
        )
    return ok(data=info, message="获取基础信息成功")


@router.get("/{full_symbol}/quotes", response_model=dict, summary="商品实时行情")
async def get_commodity_quotes(full_symbol: str):
    """
    获取大宗商品实时行情(快照)

    Path: GET /api/commodity/AU2506.SHF/quotes
    """
    quote = await service.get_quotes(full_symbol)
    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"商品行情不可用: {full_symbol}",
        )
    return ok(data=quote, message="获取实时行情成功")


@router.get("/{full_symbol}/historical", response_model=dict, summary="商品历史 K 线")
async def get_commodity_historical(
    full_symbol: str,
    start_date: str = Query(..., description="起始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD(默认到最新)"),
):
    """
    获取大宗商品历史日线数据

    Path: GET /api/commodity/CU2501.SHF/historical?start_date=2024-01-01&end_date=2025-01-15
    """
    try:
        # 简单校验日期格式
        datetime.strptime(start_date, "%Y-%m-%d")
        if end_date:
            datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="日期格式必须为 YYYY-MM-DD",
        )

    data = await service.get_historical(full_symbol, start_date, end_date)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"商品历史数据不可用: {full_symbol}",
        )
    return ok(data=data, message="获取历史 K 线成功")
