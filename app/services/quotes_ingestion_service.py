import logging
from datetime import datetime, time as dtime
from typing import Dict, Optional
from zoneinfo import ZoneInfo

from pymongo import UpdateOne

from app.core.config import settings
from app.core.database import get_mongo_db
from app.services.data_sources.manager import DataSourceManager

logger = logging.getLogger(__name__)


class QuotesIngestionService:
    """
    定时从数据源适配层获取全市场近实时行情，入库到 MongoDB 集合 `market_quotes`。
    - 调度频率：由 settings.QUOTES_INGEST_INTERVAL_SECONDS 控制（默认30秒）
    - 休市时间：跳过任务，保持上次收盘数据；必要时执行一次性兜底补数
    - 字段：code(6位)、close、pct_chg、amount、open、high、low、pre_close、trade_date、updated_at
    """

    def __init__(self, collection_name: str = "market_quotes") -> None:
        self.collection_name = collection_name
        self.tz = ZoneInfo(settings.TIMEZONE)

    async def ensure_indexes(self) -> None:
        db = get_mongo_db()
        coll = db[self.collection_name]
        try:
            await coll.create_index("code", unique=True)
            await coll.create_index("updated_at")
        except Exception as e:
            logger.warning(f"创建行情表索引失败（忽略）: {e}")

    def _is_trading_time(self, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now(self.tz)
        # 工作日 Mon-Fri
        if now.weekday() > 4:
            return False
        t = now.time()
        # 上交所/深交所常规交易时段
        morning = dtime(9, 30)
        noon = dtime(11, 30)
        afternoon_start = dtime(13, 0)
        afternoon_end = dtime(15, 0)
        return (morning <= t <= noon) or (afternoon_start <= t <= afternoon_end)

    async def _collection_empty(self) -> bool:
        db = get_mongo_db()
        coll = db[self.collection_name]
        try:
            count = await coll.estimated_document_count()
            return count == 0
        except Exception:
            return True

    async def _collection_stale(self, latest_trade_date: Optional[str]) -> bool:
        if not latest_trade_date:
            return False
        db = get_mongo_db()
        coll = db[self.collection_name]
        try:
            cursor = coll.find({}, {"trade_date": 1}).sort("trade_date", -1).limit(1)
            docs = await cursor.to_list(length=1)
            if not docs:
                return True
            doc_td = str(docs[0].get("trade_date") or "")
            return doc_td < str(latest_trade_date)
        except Exception:
            return True

    async def _bulk_upsert(self, quotes_map: Dict[str, Dict], trade_date: str, source: Optional[str] = None) -> None:
        db = get_mongo_db()
        coll = db[self.collection_name]
        ops = []
        updated_at = datetime.now(self.tz)
        for code, q in quotes_map.items():
            if not code:
                continue
            ops.append(
                UpdateOne(
                    {"code": str(code).zfill(6)},
                    {"$set": {
                        "code": str(code).zfill(6),
                        "close": q.get("close"),
                        "pct_chg": q.get("pct_chg"),
                        "amount": q.get("amount"),
                        "open": q.get("open"),
                        "high": q.get("high"),
                        "low": q.get("low"),
                        "pre_close": q.get("pre_close"),
                        "trade_date": trade_date,
                        "updated_at": updated_at,
                    }},
                    upsert=True,
                )
            )
        if not ops:
            logger.info("无可写入的数据，跳过")
            return
        result = await coll.bulk_write(ops, ordered=False)
        logger.info(
            f"✅ 行情入库完成 source={source}, matched={result.matched_count}, upserted={len(result.upserted_ids) if result.upserted_ids else 0}, modified={result.modified_count}"
        )

    async def backfill_last_close_snapshot(self) -> None:
        """一次性补齐上一笔收盘快照（用于冷启动或数据陈旧）。允许在休市期调用。"""
        try:
            manager = DataSourceManager()
            # 使用近实时快照作为兜底，休市期返回的即为最后收盘数据
            quotes_map, source = manager.get_realtime_quotes_with_fallback()
            if not quotes_map:
                logger.warning("backfill: 未获取到行情数据，跳过")
                return
            try:
                trade_date = manager.find_latest_trade_date_with_fallback() or datetime.now(self.tz).strftime("%Y%m%d")
            except Exception:
                trade_date = datetime.now(self.tz).strftime("%Y%m%d")
            await self._bulk_upsert(quotes_map, trade_date, source)
        except Exception as e:
            logger.error(f"❌ backfill 行情补数失败: {e}")

    async def backfill_last_close_snapshot_if_needed(self) -> None:
        """若集合为空或 trade_date 落后于最新交易日，则执行一次 backfill"""
        try:
            manager = DataSourceManager()
            latest_td = manager.find_latest_trade_date_with_fallback()
            if await self._collection_empty() or await self._collection_stale(latest_td):
                logger.info("🔁 触发休市期/启动期 backfill 以填充最新收盘数据")
                await self.backfill_last_close_snapshot()
        except Exception as e:
            logger.warning(f"backfill 触发检查失败（忽略）: {e}")

    async def run_once(self) -> None:
        """执行一次采集与入库。休市期仅在需要时进行一次性补数。"""
        if not self._is_trading_time():
            if settings.QUOTES_BACKFILL_ON_OFFHOURS:
                await self.backfill_last_close_snapshot_if_needed()
            else:
                logger.info("⏭️ 非交易时段，跳过行情采集")
            return
        try:
            manager = DataSourceManager()
            quotes_map, source = manager.get_realtime_quotes_with_fallback()
            if not quotes_map:
                logger.warning("未获取到行情数据，跳过本次入库")
                return
            # 获取交易日（若失败不阻断）
            try:
                trade_date = manager.find_latest_trade_date_with_fallback() or datetime.now(self.tz).strftime("%Y%m%d")
            except Exception:
                trade_date = datetime.now(self.tz).strftime("%Y%m%d")
            await self._bulk_upsert(quotes_map, trade_date, source)
        except Exception as e:
            logger.error(f"❌ 行情入库失败: {e}")

