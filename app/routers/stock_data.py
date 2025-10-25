"""
股票数据API路由 - 基于扩展数据模型
提供标准化的股票数据访问接口
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status

from app.routers.auth_db import get_current_user
from app.services.stock_data_service import get_stock_data_service
from app.models import (
    StockBasicInfoResponse,
    MarketQuotesResponse,
    StockListResponse,
    StockBasicInfoExtended,
    MarketQuotesExtended,
    MarketType
)

router = APIRouter(prefix="/api/stock-data", tags=["股票数据"])


@router.get("/basic-info/{symbol}", response_model=StockBasicInfoResponse)
async def get_stock_basic_info(
    symbol: str,
    current_user: dict = Depends(get_current_user)
):
    """
    获取股票基础信息

    Args:
        symbol: 股票代码 (支持6位A股代码)

    Returns:
        StockBasicInfoResponse: 包含扩展字段的股票基础信息
    """
    try:
        service = get_stock_data_service()
        stock_info = await service.get_stock_basic_info(symbol)

        if not stock_info:
            return StockBasicInfoResponse(
                success=False,
                message=f"未找到股票代码 {symbol} 的基础信息"
            )

        return StockBasicInfoResponse(
            success=True,
            data=stock_info,
            message="获取成功"
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取股票基础信息失败: {str(e)}"
        )


@router.get("/quotes/{symbol}", response_model=MarketQuotesResponse)
async def get_market_quotes(
    symbol: str,
    current_user: dict = Depends(get_current_user)
):
    """
    获取实时行情数据

    Args:
        symbol: 股票代码 (支持6位A股代码)

    Returns:
        MarketQuotesResponse: 包含扩展字段的实时行情数据
    """
    try:
        service = get_stock_data_service()
        quotes = await service.get_market_quotes(symbol)

        if not quotes:
            return MarketQuotesResponse(
                success=False,
                message=f"未找到股票代码 {symbol} 的行情数据"
            )

        return MarketQuotesResponse(
            success=True,
            data=quotes,
            message="获取成功"
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取实时行情失败: {str(e)}"
        )


@router.get("/list", response_model=StockListResponse)
async def get_stock_list(
    market: Optional[str] = Query(None, description="市场筛选"),
    industry: Optional[str] = Query(None, description="行业筛选"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页大小"),
    current_user: dict = Depends(get_current_user)
):
    """
    获取股票列表
    
    Args:
        market: 市场筛选 (可选)
        industry: 行业筛选 (可选)
        page: 页码 (从1开始)
        page_size: 每页大小 (1-100)
        
    Returns:
        StockListResponse: 股票列表数据
    """
    try:
        service = get_stock_data_service()
        stock_list = await service.get_stock_list(
            market=market,
            industry=industry,
            page=page,
            page_size=page_size
        )
        
        # 计算总数 (简化实现，实际应该单独查询)
        total = len(stock_list)
        
        return StockListResponse(
            success=True,
            data=stock_list,
            total=total,
            page=page,
            page_size=page_size,
            message="获取成功"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取股票列表失败: {str(e)}"
        )


@router.get("/combined/{symbol}")
async def get_combined_stock_data(
    symbol: str,
    current_user: dict = Depends(get_current_user)
):
    """
    获取股票综合数据 (基础信息 + 实时行情)

    Args:
        symbol: 股票代码

    Returns:
        dict: 包含基础信息和实时行情的综合数据
    """
    try:
        service = get_stock_data_service()

        # 并行获取基础信息和行情数据
        import asyncio
        basic_info_task = service.get_stock_basic_info(symbol)
        quotes_task = service.get_market_quotes(symbol)

        basic_info, quotes = await asyncio.gather(
            basic_info_task,
            quotes_task,
            return_exceptions=True
        )

        # 处理异常
        if isinstance(basic_info, Exception):
            basic_info = None
        if isinstance(quotes, Exception):
            quotes = None

        if not basic_info and not quotes:
            return {
                "success": False,
                "message": f"未找到股票代码 {symbol} 的任何数据"
            }

        return {
            "success": True,
            "data": {
                "basic_info": basic_info.dict() if basic_info else None,
                "quotes": quotes.dict() if quotes else None,
                "symbol": symbol,
                "timestamp": quotes.updated_at if quotes else None
            },
            "message": "获取成功"
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取股票综合数据失败: {str(e)}"
        )


@router.get("/search")
async def search_stocks(
    keyword: str = Query(..., min_length=1, description="搜索关键词"),
    limit: int = Query(10, ge=1, le=50, description="返回数量限制"),
    current_user: dict = Depends(get_current_user)
):
    """
    搜索股票
    
    Args:
        keyword: 搜索关键词 (股票代码或名称)
        limit: 返回数量限制
        
    Returns:
        dict: 搜索结果
    """
    try:
        from app.core.database import get_mongo_db
        
        db = get_mongo_db()
        collection = db.stock_basic_info
        
        # 构建搜索条件
        search_conditions = []

        # 如果是6位数字，按代码精确匹配
        if keyword.isdigit() and len(keyword) == 6:
            search_conditions.append({"symbol": keyword})
        else:
            # 按名称模糊匹配
            search_conditions.append({"name": {"$regex": keyword, "$options": "i"}})
            # 如果包含数字，也尝试代码匹配
            if any(c.isdigit() for c in keyword):
                search_conditions.append({"symbol": {"$regex": keyword}})
        
        # 执行搜索
        cursor = collection.find(
            {"$or": search_conditions},
            {"_id": 0}
        ).limit(limit)
        
        results = await cursor.to_list(length=limit)
        
        # 数据标准化
        service = get_stock_data_service()
        standardized_results = []
        for doc in results:
            standardized_doc = service._standardize_basic_info(doc)
            standardized_results.append(standardized_doc)
        
        return {
            "success": True,
            "data": standardized_results,
            "total": len(standardized_results),
            "keyword": keyword,
            "message": "搜索完成"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"搜索股票失败: {str(e)}"
        )


@router.get("/markets")
async def get_market_summary(
    current_user: dict = Depends(get_current_user)
):
    """
    获取市场概览
    
    Returns:
        dict: 各市场的股票数量统计
    """
    try:
        from app.core.database import get_mongo_db
        
        db = get_mongo_db()
        collection = db.stock_basic_info
        
        # 统计各市场股票数量
        pipeline = [
            {
                "$group": {
                    "_id": "$market",
                    "count": {"$sum": 1}
                }
            },
            {
                "$sort": {"count": -1}
            }
        ]
        
        cursor = collection.aggregate(pipeline)
        market_stats = await cursor.to_list(length=None)
        
        # 总数统计
        total_count = await collection.count_documents({})
        
        return {
            "success": True,
            "data": {
                "total_stocks": total_count,
                "market_breakdown": market_stats,
                "supported_markets": ["CN"],  # 当前支持的市场
                "last_updated": None  # 可以从数据中获取最新更新时间
            },
            "message": "获取成功"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取市场概览失败: {str(e)}"
        )
