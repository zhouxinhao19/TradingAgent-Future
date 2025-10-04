"""
Multi-source stock basics synchronization service
- Supports multiple data sources with fallback mechanism
- Priority: Tushare > AKShare > BaoStock > TDX
- Fetches A-share stock basic info with extended financial metrics
- Upserts into MongoDB collection `stock_basic_info`
- Provides unified interface for different data sources
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import UpdateOne

from app.core.database import get_mongo_db
from app.services.basics_sync import add_financial_metrics as _add_financial_metrics_util


logger = logging.getLogger(__name__)

# Collection names
COLLECTION_NAME = "stock_basic_info"
STATUS_COLLECTION = "sync_status"
JOB_KEY = "stock_basics_multi_source"


class DataSourcePriority(Enum):
    """数据源优先级枚举"""
    TUSHARE = 1
    AKSHARE = 2
    BAOSTOCK = 3
    TDX = 4


@dataclass
class SyncStats:
    """同步统计信息"""
    job: str = JOB_KEY
    status: str = "idle"
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    total: int = 0
    inserted: int = 0
    updated: int = 0
    errors: int = 0
    last_trade_date: Optional[str] = None
    data_sources_used: List[str] = field(default_factory=list)
    source_stats: Dict[str, Dict[str, int]] = field(default_factory=dict)
    message: Optional[str] = None


class MultiSourceBasicsSyncService:
    """多数据源股票基础信息同步服务"""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._running = False
        self._last_status: Optional[Dict[str, Any]] = None

    async def get_status(self) -> Dict[str, Any]:
        """获取同步状态"""
        if self._last_status:
            return self._last_status

        db = get_mongo_db()
        doc = await db[STATUS_COLLECTION].find_one({"job": JOB_KEY})
        if doc:
            # 移除MongoDB的_id字段以避免序列化问题
            doc.pop("_id", None)
            return doc
        return {"job": JOB_KEY, "status": "never_run"}

    async def _persist_status(self, db: AsyncIOMotorDatabase, stats: Dict[str, Any]) -> None:
        """持久化同步状态"""
        stats["job"] = JOB_KEY

        # 如果是开始状态，创建新记录
        if stats.get("status") == "running":
            # 插入新的历史记录
            await db[STATUS_COLLECTION].insert_one(stats.copy())
        else:
            # 更新最新的记录（按started_at排序的最新一条）
            latest_record = await db[STATUS_COLLECTION].find_one(
                {"job": JOB_KEY},
                sort=[("started_at", -1)]
            )
            if latest_record:
                await db[STATUS_COLLECTION].update_one(
                    {"_id": latest_record["_id"]},
                    {"$set": stats}
                )
            else:
                # 如果没有找到记录，插入新记录
                await db[STATUS_COLLECTION].insert_one(stats.copy())

        self._last_status = {k: v for k, v in stats.items() if k != "_id"}

    async def run_full_sync(self, force: bool = False, preferred_sources: List[str] = None) -> Dict[str, Any]:
        """
        运行完整同步

        Args:
            force: 是否强制运行（即使已在运行中）
            preferred_sources: 优先使用的数据源列表
        """
        async with self._lock:
            if self._running and not force:
                logger.info("Multi-source stock basics sync already running; skip start")
                return await self.get_status()
            self._running = True

        db = get_mongo_db()
        stats = SyncStats()
        stats.started_at = datetime.now().isoformat()
        stats.status = "running"
        await self._persist_status(db, stats.__dict__.copy())

        try:
            # Step 1: 获取数据源管理器
            from app.services.data_source_adapters import DataSourceManager
            manager = DataSourceManager()
            available_adapters = manager.get_available_adapters()

            if not available_adapters:
                raise RuntimeError("No available data sources found")

            logger.info(f"Available data sources: {[adapter.name for adapter in available_adapters]}")

            # Step 2: 尝试从数据源获取股票列表
            stock_df, source_used = await asyncio.to_thread(manager.get_stock_list_with_fallback)
            if stock_df is None or getattr(stock_df, "empty", True):
                raise RuntimeError("All data sources failed to provide stock list")

            stats.data_sources_used.append(f"stock_list:{source_used}")
            logger.info(f"Successfully fetched {len(stock_df)} stocks from {source_used}")

            # Step 3: 获取最新交易日期和财务数据
            latest_trade_date = await asyncio.to_thread(manager.find_latest_trade_date_with_fallback)
            stats.last_trade_date = latest_trade_date

            daily_data_map = {}
            daily_source = ""
            if latest_trade_date:
                daily_df, daily_source = await asyncio.to_thread(
                    manager.get_daily_basic_with_fallback, latest_trade_date
                )
                if daily_df is not None and not daily_df.empty:
                    for _, row in daily_df.iterrows():
                        ts_code = row.get("ts_code")
                        if ts_code:
                            daily_data_map[ts_code] = row.to_dict()
                    stats.data_sources_used.append(f"daily_data:{daily_source}")

            # Step 5: 处理和更新数据
            ops = []
            inserted = updated = errors = 0

            for _, row in stock_df.iterrows():
                try:
                    # 提取基础信息
                    name = row.get("name") or ""
                    area = row.get("area") or ""
                    industry = row.get("industry") or ""
                    market = row.get("market") or ""
                    list_date = row.get("list_date") or ""
                    ts_code = row.get("ts_code") or ""

                    # 提取6位股票代码
                    if isinstance(ts_code, str) and "." in ts_code:
                        code = ts_code.split(".")[0]
                    else:
                        symbol = row.get("symbol") or ""
                        code = str(symbol).zfill(6) if symbol else ""

                    # 根据 ts_code 判断交易所
                    if isinstance(ts_code, str):
                        if ts_code.endswith(".SH"):
                            sse = "上海证券交易所"
                        elif ts_code.endswith(".SZ"):
                            sse = "深圳证券交易所"
                        elif ts_code.endswith(".BJ"):
                            sse = "北京证券交易所"
                        else:
                            sse = "未知"
                    else:
                        sse = "未知"

                    category = "stock_cn"

                    # 获取财务数据
                    daily_metrics = {}
                    if isinstance(ts_code, str) and ts_code in daily_data_map:
                        daily_metrics = daily_data_map[ts_code]

                    # 构建文档
                    doc = {
                        "code": code,
                        "name": name,
                        "area": area,
                        "industry": industry,
                        "market": market,
                        "list_date": list_date,
                        "sse": sse,
                        "category": category,
                        "source": "multi_source",
                        "updated_at": datetime.now(),
                    }

                    # 添加财务指标
                    self._add_financial_metrics(doc, daily_metrics)

                    # 创建更新操作
                    ops.append(UpdateOne({"code": code}, {"$set": doc}, upsert=True))

                except Exception as e:
                    logger.error(f"Error processing stock {row.get('ts_code', 'unknown')}: {e}")
                    errors += 1

            # Step 6: 批量执行数据库操作
            if ops:
                result = await db[COLLECTION_NAME].bulk_write(ops, ordered=False)
                inserted = result.upserted_count
                updated = result.modified_count

            # Step 7: 更新统计信息
            stats.total = len(ops)
            stats.inserted = inserted
            stats.updated = updated
            stats.errors = errors
            stats.status = "success" if errors == 0 else "success_with_errors"
            stats.finished_at = datetime.now().isoformat()

            await self._persist_status(db, stats.__dict__.copy())
            logger.info(
                f"Multi-source sync finished: total={stats.total} inserted={inserted} "
                f"updated={updated} errors={errors} sources={stats.data_sources_used}"
            )
            return stats.__dict__

        except Exception as e:
            stats.status = "failed"
            stats.message = str(e)
            stats.finished_at = datetime.now().isoformat()
            await self._persist_status(db, stats.__dict__.copy())
            logger.exception(f"Multi-source sync failed: {e}")
            return stats.__dict__
        finally:
            async with self._lock:
                self._running = False



    def _add_financial_metrics(self, doc: Dict, daily_metrics: Dict) -> None:
        """委托到 basics_sync.processing.add_financial_metrics"""
        return _add_financial_metrics_util(doc, daily_metrics)


# 全局服务实例
_multi_source_sync_service = None

def get_multi_source_sync_service() -> MultiSourceBasicsSyncService:
    """获取多数据源同步服务实例"""
    global _multi_source_sync_service
    if _multi_source_sync_service is None:
        _multi_source_sync_service = MultiSourceBasicsSyncService()
    return _multi_source_sync_service
