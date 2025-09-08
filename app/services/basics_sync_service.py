"""
Stock basics synchronization service
- Fetches A-share stock basic info from Tushare
- Enriches with latest market cap (total_mv)
- Upserts into MongoDB collection `stock_basic_info`
- Persists status in collection `sync_status` with key `stock_basics`
- Provides a singleton accessor for reuse across routers/scheduler

This module is async-friendly and offloads blocking IO (Tushare/pandas) to a thread.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import UpdateOne

from app.core.database import get_mongo_db

logger = logging.getLogger(__name__)

STATUS_COLLECTION = "sync_status"
DATA_COLLECTION = "stock_basic_info"
JOB_KEY = "stock_basics"


@dataclass
class SyncStats:
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    status: str = "idle"  # idle|running|success|failed
    total: int = 0
    inserted: int = 0
    updated: int = 0
    errors: int = 0
    message: str = ""
    last_trade_date: Optional[str] = None  # YYYYMMDD


class BasicsSyncService:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._running = False
        self._last_status: Optional[Dict[str, Any]] = None

    async def get_status(self, db: Optional[AsyncIOMotorDatabase] = None) -> Dict[str, Any]:
        """Return last persisted status; falls back to in-memory snapshot."""
        try:
            db = db or get_mongo_db()
            doc = await db[STATUS_COLLECTION].find_one({"job": JOB_KEY})
            if doc:
                doc.pop("_id", None)
                return doc
        except Exception as e:
            logger.warning(f"Failed to load sync status from DB: {e}")
        return self._last_status or {"job": JOB_KEY, "status": "idle"}

    async def _persist_status(self, db: AsyncIOMotorDatabase, stats: Dict[str, Any]) -> None:
        stats["job"] = JOB_KEY
        await db[STATUS_COLLECTION].update_one({"job": JOB_KEY}, {"$set": stats}, upsert=True)
        self._last_status = {k: v for k, v in stats.items() if k != "_id"}

    async def run_full_sync(self, force: bool = False) -> Dict[str, Any]:
        """Run a full sync. If already running, return current status unless force."""
        async with self._lock:
            if self._running and not force:
                logger.info("Stock basics sync already running; skip start")
                return await self.get_status()
            self._running = True

        db = get_mongo_db()
        stats = SyncStats()
        stats.started_at = datetime.utcnow().isoformat()
        stats.status = "running"
        await self._persist_status(db, stats.__dict__.copy())

        try:
            # Step 1: Fetch stock basic list from Tushare (blocking -> thread)
            stock_df = await asyncio.to_thread(self._fetch_stock_basic_df)
            if stock_df is None or getattr(stock_df, "empty", True):
                raise RuntimeError("Tushare returned empty stock_basic list")

            # Step 2: Determine latest trade_date and fetch daily_basic for financial metrics (blocking -> thread)
            latest_trade_date = await asyncio.to_thread(self._find_latest_trade_date)
            stats.last_trade_date = latest_trade_date
            daily_data_map = await asyncio.to_thread(self._fetch_daily_basic_mv_map, latest_trade_date)

            # Step 3: Upsert into MongoDB (batched bulk writes)
            ops: List[UpdateOne] = []
            now_iso = datetime.utcnow().isoformat()
            for _, row in stock_df.iterrows():  # type: ignore
                name = row.get("name") or ""
                area = row.get("area") or ""
                industry = row.get("industry") or ""
                market = row.get("market") or ""
                list_date = row.get("list_date") or ""
                ts_code = row.get("ts_code") or ""

                # Extract 6-digit stock code from ts_code (e.g., "000001.SZ" -> "000001")
                if isinstance(ts_code, str) and "." in ts_code:
                    code = ts_code.split(".")[0]  # Keep the 6-digit format
                else:
                    # Fallback to symbol with zero-padding if ts_code is invalid
                    symbol = row.get("symbol") or ""
                    code = str(symbol).zfill(6) if symbol else ""

                sse = "sh" if (isinstance(ts_code, str) and ts_code.endswith(".SH")) else "sz"
                category = "stock_cn"

                # Extract daily financial metrics - use ts_code directly for matching
                daily_metrics = {}
                if isinstance(ts_code, str) and ts_code in daily_data_map:
                    daily_metrics = daily_data_map[ts_code]

                # Process market cap (convert from 万元 to 亿元)
                total_mv_yi = None
                circ_mv_yi = None
                if "total_mv" in daily_metrics:
                    try:
                        total_mv_yi = float(daily_metrics["total_mv"]) / 10000.0
                    except Exception:
                        pass
                if "circ_mv" in daily_metrics:
                    try:
                        circ_mv_yi = float(daily_metrics["circ_mv"]) / 10000.0
                    except Exception:
                        pass

                doc = {
                    "code": code,
                    "name": name,
                    "area": area,
                    "industry": industry,
                    "market": market,
                    "list_date": list_date,
                    "sse": sse,
                    "sec": category,
                    "source": "tushare",
                    "updated_at": now_iso,
                }

                # Add market cap fields
                if total_mv_yi is not None:
                    doc["total_mv"] = total_mv_yi
                if circ_mv_yi is not None:
                    doc["circ_mv"] = circ_mv_yi

                # Add financial ratios
                for field in ["pe", "pb", "pe_ttm", "pb_mrq"]:
                    if field in daily_metrics:
                        doc[field] = daily_metrics[field]

                # Add trading metrics
                for field in ["turnover_rate", "volume_ratio"]:
                    if field in daily_metrics:
                        doc[field] = daily_metrics[field]
                ops.append(
                    UpdateOne({"code": code}, {"$set": doc}, upsert=True)
                )

            inserted = 0
            updated = 0
            errors = 0
            # Execute in chunks to avoid oversized batches
            BATCH = 1000
            for i in range(0, len(ops), BATCH):
                batch = ops[i : i + BATCH]
                try:
                    result = await db[DATA_COLLECTION].bulk_write(batch, ordered=False)
                    # bulk_write returns inserted/upserted/modified counts
                    updated += (result.modified_count or 0)
                    # upserts are counted in upserted_ids
                    inserted += len(result.upserted_ids) if result.upserted_ids else 0
                except Exception as e:
                    errors += 1
                    logger.error(f"Bulk write error on batch {i//BATCH}: {e}")

            stats.total = len(ops)
            stats.inserted = inserted
            stats.updated = updated
            stats.errors = errors
            stats.status = "success" if errors == 0 else "success_with_errors"
            stats.finished_at = datetime.utcnow().isoformat()
            await self._persist_status(db, stats.__dict__.copy())
            logger.info(
                f"Stock basics sync finished: total={stats.total} inserted={inserted} updated={updated} errors={errors} trade_date={latest_trade_date}"
            )
            return stats.__dict__

        except Exception as e:
            stats.status = "failed"
            stats.message = str(e)
            stats.finished_at = datetime.utcnow().isoformat()
            await self._persist_status(db, stats.__dict__.copy())
            logger.exception(f"Stock basics sync failed: {e}")
            return stats.__dict__
        finally:
            async with self._lock:
                self._running = False

    # ---- Blocking helpers (run in thread) ----
    def _fetch_stock_basic_df(self):
        from tradingagents.dataflows.tushare_utils import get_tushare_provider
        provider = get_tushare_provider()
        if not getattr(provider, "connected", False):
            raise RuntimeError("Tushare not connected. Set TUSHARE_ENABLED=true and TUSHARE_TOKEN in .env")
        df = provider.get_stock_list()
        return df

    def _find_latest_trade_date(self) -> str:
        """Find the latest trade_date with daily_basic data (YYYYMMDD)."""
        from tradingagents.dataflows.tushare_utils import get_tushare_provider
        provider = get_tushare_provider()
        api = provider.api
        if api is None:
            raise RuntimeError("Tushare API unavailable")
        # Try today back to today-5
        today = datetime.now()
        for delta in range(0, 6):
            d = (today - timedelta(days=delta)).strftime("%Y%m%d")
            try:
                db = api.daily_basic(trade_date=d, fields="ts_code,total_mv")
                if db is not None and not db.empty:
                    return d
            except Exception:
                continue
        # Fallback: return yesterday
        return (today - timedelta(days=1)).strftime("%Y%m%d")

    def _fetch_daily_basic_mv_map(self, trade_date: str) -> Dict[str, Dict[str, float]]:
        """Fetch daily basic data including market cap, PE, PB, turnover rate, etc."""
        from tradingagents.dataflows.tushare_utils import get_tushare_provider
        provider = get_tushare_provider()
        api = provider.api
        if api is None:
            raise RuntimeError("Tushare API unavailable")

        # Expand fields to include more financial metrics
        fields = "ts_code,total_mv,circ_mv,pe,pb,turnover_rate,volume_ratio,pe_ttm,pb_mrq"
        db = api.daily_basic(trade_date=trade_date, fields=fields)

        data_map: Dict[str, Dict[str, float]] = {}
        if db is not None and not db.empty:
            for _, row in db.iterrows():  # type: ignore
                ts_code = row.get("ts_code")
                if ts_code is not None:
                    try:
                        # Extract all available metrics
                        metrics = {}
                        for field in ["total_mv", "circ_mv", "pe", "pb", "turnover_rate", "volume_ratio", "pe_ttm", "pb_mrq"]:
                            value = row.get(field)
                            if value is not None and str(value).lower() not in ['nan', 'none', '']:
                                metrics[field] = float(value)

                        if metrics:  # Only add if we have at least some data
                            data_map[str(ts_code)] = metrics
                    except Exception:
                        pass
        return data_map


# Singleton accessor
_basics_sync_service: Optional[BasicsSyncService] = None


def get_basics_sync_service() -> BasicsSyncService:
    global _basics_sync_service
    if _basics_sync_service is None:
        _basics_sync_service = BasicsSyncService()
    return _basics_sync_service

