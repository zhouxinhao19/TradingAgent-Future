"""
Multi-source synchronization API routes
Provides endpoints for multi-source stock data synchronization
"""
import logging
from typing import Dict, List, Optional, Any, Union
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.multi_source_basics_sync_service import get_multi_source_sync_service
from app.services.data_sources.manager import DataSourceManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sync/multi-source", tags=["Multi-Source Sync"])


class SyncRequest(BaseModel):
    """同步请求模型"""
    force: bool = False
    preferred_sources: Optional[List[str]] = None


class SyncResponse(BaseModel):
    """同步响应模型"""
    success: bool
    message: str
    data: Union[Dict[str, Any], List[Any], Any]


class DataSourceStatus(BaseModel):
    """数据源状态模型"""
    name: str
    priority: int
    available: bool
    description: str


@router.get("/sources/status")
async def get_data_sources_status():
    """获取所有数据源的状态"""
    try:
        manager = DataSourceManager()
        available_adapters = manager.get_available_adapters()
        all_adapters = manager.adapters

        status_list = []
        for adapter in all_adapters:
            is_available = adapter in available_adapters

            # 根据数据源类型提供描述
            descriptions = {
                "tushare": "专业金融数据API，提供高质量的A股数据和财务指标",
                "akshare": "开源金融数据库，提供基础的股票信息",
                "baostock": "免费开源的证券数据平台，提供历史数据"
            }

            status_list.append({
                "name": adapter.name,
                "priority": adapter.priority,
                "available": is_available,
                "description": descriptions.get(adapter.name, f"{adapter.name}数据源")
            })

        return SyncResponse(
            success=True,
            message="Data sources status retrieved successfully",
            data=status_list
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get data sources status: {str(e)}")


@router.get("/status")
async def get_sync_status():
    """获取多数据源同步状态"""
    try:
        service = get_multi_source_sync_service()
        status = await service.get_status()
        
        return SyncResponse(
            success=True,
            message="Status retrieved successfully",
            data=status
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get sync status: {str(e)}")


@router.post("/stock_basics/run")
async def run_stock_basics_sync(
    force: bool = Query(False, description="是否强制运行同步"),
    preferred_sources: Optional[str] = Query(None, description="优先使用的数据源，用逗号分隔")
):
    """运行多数据源股票基础信息同步"""
    try:
        service = get_multi_source_sync_service()
        
        # 解析优先数据源
        sources_list = None
        if preferred_sources and isinstance(preferred_sources, str):
            sources_list = [s.strip() for s in preferred_sources.split(",") if s.strip()]
        
        # 运行同步
        result = await service.run_full_sync(force=force, preferred_sources=sources_list)
        
        # 判断是否成功
        success = result.get("status") in ["success", "success_with_errors"]
        message = "Synchronization completed successfully"
        
        if result.get("status") == "success_with_errors":
            message = f"Synchronization completed with {result.get('errors', 0)} errors"
        elif result.get("status") == "failed":
            message = f"Synchronization failed: {result.get('message', 'Unknown error')}"
            success = False
        elif result.get("status") == "running":
            message = "Synchronization is already running"
        
        return SyncResponse(
            success=success,
            message=message,
            data=result
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to run synchronization: {str(e)}")


@router.post("/test-sources")
async def test_data_sources():
    """测试所有数据源的连接和数据获取能力"""
    try:
        manager = DataSourceManager()
        available_adapters = manager.get_available_adapters()
        
        test_results = []
        
        for adapter in available_adapters:
            result = {
                "name": adapter.name,
                "priority": adapter.priority,
                "available": True,
                "tests": {}
            }
            
            # 测试股票列表获取
            try:
                df = adapter.get_stock_list()
                if df is not None and not df.empty:
                    result["tests"]["stock_list"] = {
                        "success": True,
                        "count": len(df),
                        "message": f"Successfully fetched {len(df)} stocks"
                    }
                else:
                    result["tests"]["stock_list"] = {
                        "success": False,
                        "count": 0,
                        "message": "No stock data returned"
                    }
            except Exception as e:
                result["tests"]["stock_list"] = {
                    "success": False,
                    "count": 0,
                    "message": f"Error: {str(e)}"
                }
            
            # 测试最新交易日期查找
            try:
                trade_date = adapter.find_latest_trade_date()
                if trade_date:
                    result["tests"]["trade_date"] = {
                        "success": True,
                        "date": trade_date,
                        "message": f"Found latest trade date: {trade_date}"
                    }
                else:
                    result["tests"]["trade_date"] = {
                        "success": False,
                        "date": None,
                        "message": "No trade date found"
                    }
            except Exception as e:
                result["tests"]["trade_date"] = {
                    "success": False,
                    "date": None,
                    "message": f"Error: {str(e)}"
                }
            
            # 测试每日基础数据获取（如果支持）
            try:
                trade_date = result["tests"]["trade_date"].get("date")
                if trade_date:
                    df = adapter.get_daily_basic(trade_date)
                    if df is not None and not df.empty:
                        result["tests"]["daily_basic"] = {
                            "success": True,
                            "count": len(df),
                            "message": f"Successfully fetched daily data for {len(df)} stocks"
                        }
                    else:
                        result["tests"]["daily_basic"] = {
                            "success": False,
                            "count": 0,
                            "message": "No daily basic data available or not supported"
                        }
                else:
                    result["tests"]["daily_basic"] = {
                        "success": False,
                        "count": 0,
                        "message": "Cannot test without valid trade date"
                    }
            except Exception as e:
                result["tests"]["daily_basic"] = {
                    "success": False,
                    "count": 0,
                    "message": f"Error: {str(e)}"
                }
            
            test_results.append(result)
        
        return SyncResponse(
            success=True,
            message=f"Tested {len(test_results)} data sources",
            data={"test_results": test_results}
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to test data sources: {str(e)}")


@router.get("/recommendations")
async def get_sync_recommendations():
    """获取数据源使用建议"""
    try:
        manager = DataSourceManager()
        available_adapters = manager.get_available_adapters()
        
        recommendations = {
            "primary_source": None,
            "fallback_sources": [],
            "suggestions": [],
            "warnings": []
        }
        
        if available_adapters:
            # 推荐优先级最高的可用数据源作为主数据源
            primary = available_adapters[0]
            recommendations["primary_source"] = {
                "name": primary.name,
                "priority": primary.priority,
                "reason": "Highest priority available data source"
            }
            
            # 其他可用数据源作为备用
            for adapter in available_adapters[1:]:
                recommendations["fallback_sources"].append({
                    "name": adapter.name,
                    "priority": adapter.priority
                })
        
        # 生成建议
        if not available_adapters:
            recommendations["warnings"].append("No data sources are available. Please check your configuration.")
        elif len(available_adapters) == 1:
            recommendations["suggestions"].append("Consider configuring additional data sources for redundancy.")
        else:
            recommendations["suggestions"].append(f"You have {len(available_adapters)} data sources available, which provides good redundancy.")
        
        # 特定数据源的建议
        tushare_available = any(a.name == "tushare" for a in available_adapters)
        if not tushare_available:
            recommendations["suggestions"].append("Consider configuring Tushare for the most comprehensive financial data.")
        
        return SyncResponse(
            success=True,
            message="Recommendations generated successfully",
            data=recommendations
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate recommendations: {str(e)}")


@router.get("/history")
async def get_sync_history(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=50, description="每页大小"),
    status: Optional[str] = Query(None, description="状态筛选")
):
    """获取同步历史记录"""
    try:
        from app.core.database import get_mongo_db
        db = get_mongo_db()

        # 构建查询条件
        query = {"job": "stock_basics_multi_source"}
        if status:
            query["status"] = status

        # 计算跳过的记录数
        skip = (page - 1) * page_size

        # 查询历史记录
        cursor = db.sync_status.find(query).sort("started_at", -1).skip(skip).limit(page_size)
        history_records = await cursor.to_list(length=page_size)

        # 获取总数
        total = await db.sync_status.count_documents(query)

        # 清理记录中的 _id 字段
        for record in history_records:
            record.pop("_id", None)

        return SyncResponse(
            success=True,
            message="History retrieved successfully",
            data={
                "records": history_records,
                "total": total,
                "page": page,
                "page_size": page_size,
                "has_more": skip + len(history_records) < total
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get sync history: {str(e)}")


@router.delete("/cache")
async def clear_sync_cache():
    """清空同步相关的缓存"""
    try:
        service = get_multi_source_sync_service()

        # 清空同步状态缓存
        cleared_items = 0

        # 1. 清空同步状态
        try:
            from app.core.database import get_mongo_db
            db = get_mongo_db()

            # 删除同步状态记录
            result = await db.sync_status.delete_many({"job": "stock_basics_multi_source"})
            cleared_items += result.deleted_count

            # 重置服务状态
            service._running = False

        except Exception as e:
            logger.warning(f"Failed to clear sync status cache: {e}")

        # 2. 清空数据源缓存（如果有的话）
        try:
            manager = DataSourceManager()
            # 这里可以添加数据源特定的缓存清理逻辑
            # 目前数据源适配器没有持久化缓存，所以跳过
        except Exception as e:
            logger.warning(f"Failed to clear data source cache: {e}")

        return SyncResponse(
            success=True,
            message=f"Cache cleared successfully, {cleared_items} items removed",
            data={"cleared": True, "items_cleared": cleared_items}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")
