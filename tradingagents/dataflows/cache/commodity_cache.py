"""
CommodityCacheManager — 商品期货专用缓存管理器

三层架构:
  Layer 1: InMemoryTTLCache — 短效内存缓存(秒级/分级 TTL), 避免重复请求
  Layer 2: ParquetFileCache — 持久化 Parquet 文件缓存, 按数据类型+品种+日期范围组织
  Layer 3: IncrementalMerge — 增量合并工具(日频), 仿参考项目 modules/*_updater.py

不依赖股票缓存系统(tradingagents/dataflows/cache/*.py), 独立于 commodity 管道。
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from tradingagents.utils.logging_init import get_logger

logger = get_logger("default")

# =============================================================================
# Layer 1: 内存 TTL 缓存
# =============================================================================


class InMemoryTTLCache:
    """线程安全的内存 TTL 缓存, 用于短效高频重复查询。

    键约定:
      "quotes:{full_symbol}"          — 实时行情
      "basic:{full_symbol}"           — 基础信息
      "inventory:{symbol}"            — 库存全量
      "historical:{underlying}_{mkt}" — 历史 K 线(无精确日期范围)
      "basis:{var}_{start}_{end}"     — 基差序列
      "roll_yield:{type}"             — 展期收益率
      "spot_price:{date}"             — 现货快照
    """

    def __init__(self, default_ttl_sec: float = 300.0):
        self._default_ttl = default_ttl_sec
        self._store: Dict[str, _TTLEntry] = {}

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值, 已过期或不存在返回 None。"""
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.monotonic() - entry.ts > entry.ttl:
            del self._store[key]
            return None
        return entry.value

    def set(self, key: str, value: Any, ttl_sec: Optional[float] = None) -> None:
        """存入缓存。"""
        self._store[key] = _TTLEntry(
            value=value,
            ts=time.monotonic(),
            ttl=ttl_sec if ttl_sec is not None else self._default_ttl,
        )

    def invalidate(self, key_prefix: str) -> int:
        """删除所有以 key_prefix 开头的缓存键。返回删除的数量。"""
        before = len(self._store)
        self._store = {k: v for k, v in self._store.items() if not k.startswith(key_prefix)}
        return before - len(self._store)

    def clear_expired(self) -> int:
        """清理已过期条目, 返回清理数量。"""
        now = time.monotonic()
        expired = [k for k, v in self._store.items() if now - v.ts > v.ttl]
        for k in expired:
            del self._store[k]
        return len(expired)

    def stats(self) -> Dict[str, Any]:
        """缓存统计。"""
        now = time.monotonic()
        active = sum(1 for v in self._store.values() if now - v.ts <= v.ttl)
        expired = len(self._store) - active
        return {"total": len(self._store), "active": active, "expired": expired}


@dataclass
class _TTLEntry:
    value: Any
    ts: float
    ttl: float


# =============================================================================
# Layer 2: Parquet 文件缓存
# =============================================================================


class ParquetFileCache:
    """持久化 Parquet 缓存, 按数据类型分层归档。

    目录结构:
      {cache_root}/
        historical/       ← 历史 K 线
          SHFE/CU_20200101_20500101.parquet
        basis/            ← 基差序列
          CU/CU_20230101_20241231.parquet
        inventory/        ← 库存序列(全量)
          AL_inventory.parquet
        positioning/      ← 持仓排名
          SHFE_20240615.parquet
        roll_yield/       ← 展期收益率
          date_CU_20230101_20241231.parquet
        spot_price/       ← 单日基差快照
          20240615.parquet
    """

    def __init__(self, cache_root: Path):
        self._root = cache_root
        for sub in ("historical", "basis", "inventory", "positioning", "roll_yield", "spot_price", "delivery"):
            (cache_root / sub).mkdir(parents=True, exist_ok=True)

    # ---- historical ----

    def get_historical(self, underlying: str, start: str, end: str, market: str) -> Optional[pd.DataFrame]:
        path = self._historical_path(underlying, start, end, market)
        return self._read_parquet(path)

    def save_historical(self, underlying: str, start: str, end: str, market: str, df: pd.DataFrame) -> None:
        path = self._historical_path(underlying, start, end, market)
        self._write_parquet(path, df)

    def _historical_path(self, underlying: str, start: str, end: str, market: str) -> Path:
        mdir = self._root / "historical" / market.upper()
        mdir.mkdir(parents=True, exist_ok=True)
        return mdir / f"{underlying.upper()}_{start}_{end}.parquet"

    # ---- basis ----

    def get_basis(self, var: str, start_day: str, end_day: str) -> Optional[pd.DataFrame]:
        return self._read_parquet(self._basis_path(var, start_day, end_day))

    def save_basis(self, var: str, start_day: str, end_day: str, df: pd.DataFrame) -> None:
        self._write_parquet(self._basis_path(var, start_day, end_day), df)

    def delete_basis(self, var: str, start_day: str, end_day: str) -> bool:
        """删除 Parquet 文件级基差缓存(no_cache 旁路用)。"""
        path = self._basis_path(var, start_day, end_day)
        if path.exists():
            try:
                path.unlink()
                return True
            except OSError as e:
                logger.debug("Parquet 缓存删除失败 %s: %s", path, e)
                return False
        return False

    def _basis_path(self, var: str, start_day: str, end_day: str) -> Path:
        vdir = self._root / "basis" / var.upper()
        vdir.mkdir(parents=True, exist_ok=True)
        return vdir / f"{var.upper()}_{start_day}_{end_day}.parquet"

    # ---- inventory ----

    def get_inventory(self, symbol: str) -> Optional[pd.DataFrame]:
        return self._read_parquet(self._inventory_path(symbol))

    def save_inventory(self, symbol: str, df: pd.DataFrame) -> None:
        self._write_parquet(self._inventory_path(symbol), df)

    def delete_inventory(self, symbol: str) -> bool:
        """删除 Parquet 文件级库存缓存(no_cache 旁路用)。"""
        path = self._inventory_path(symbol)
        if path.exists():
            try:
                path.unlink()
                return True
            except OSError as e:
                logger.debug("Parquet 缓存删除失败 %s: %s", path, e)
                return False
        return False

    def _inventory_path(self, symbol: str) -> Path:
        return self._root / "inventory" / f"{symbol.upper()}_inventory.parquet"

    # ---- positioning ----

    def get_positioning(self, exchange: str, date_str: str) -> Optional[pd.DataFrame]:
        return self._read_parquet(self._root / "positioning" / f"{exchange.upper()}_{date_str}.parquet")

    def save_positioning(self, exchange: str, date_str: str, df: pd.DataFrame) -> None:
        self._write_parquet(self._root / "positioning" / f"{exchange.upper()}_{date_str}.parquet", df)

    # ---- roll_yield ----

    def get_roll_yield(self, key: str) -> Optional[pd.DataFrame]:
        return self._read_parquet(self._root / "roll_yield" / f"{key}.parquet")

    def save_roll_yield(self, key: str, df: pd.DataFrame) -> None:
        self._write_parquet(self._root / "roll_yield" / f"{key}.parquet", df)

    # ---- spot_price ----

    def get_spot_price(self, date_str: str) -> Optional[pd.DataFrame]:
        return self._read_parquet(self._root / "spot_price" / f"{date_str}.parquet")

    def save_spot_price(self, date_str: str, df: pd.DataFrame) -> None:
        self._write_parquet(self._root / "spot_price" / f"{date_str}.parquet", df)

    # ---- generic ----

    def clear_all(self) -> None:
        """清空所有 Parquet 缓存(重建空目录)。"""
        import shutil
        if self._root.exists():
            shutil.rmtree(self._root)
        self.__init__(self._root)

    def file_count(self) -> int:
        return sum(1 for _ in self._root.rglob("*.parquet"))

    @staticmethod
    def _read_parquet(path: Path) -> Optional[pd.DataFrame]:
        if not path.exists():
            return None
        try:
            return pd.read_parquet(path)
        except Exception as e:
            logger.debug("Parquet 缓存读取失败 %s: %s", path, e)
            return None

    @staticmethod
    def _write_parquet(path: Path, df: pd.DataFrame) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(path, index=False)
        except Exception as e:
            logger.debug("Parquet 缓存写入失败 %s: %s", path, e)


# =============================================================================
# CommodityCacheManager — 统一入口
# =============================================================================

# 默认缓存根目录
_DEFAULT_CACHE_ROOT = Path(__file__).resolve().parent.parent / "data_cache" / "commodity"

# 默认 TTL (秒): 数据类型 → ttl_sec
TTL_CONFIG: Dict[str, float] = {
    "quotes": 30,          # 实时行情, 30 秒
    "basic": 43200,        # 基础信息, 12 小时
    "historical": 3600,    # 历史 K 线, 1 小时
    "inventory": 21600,    # 库存, 6 小时
    "basis": 14400,        # 基差, 4 小时
    "positioning": 21600,  # 持仓, 6 小时
    "roll_yield": 21600,   # 展期, 6 小时
    "spot_price": 14400,   # 单日基差快照, 4 小时
    "news": 7200,          # 新闻, 2 小时
}


class CommodityCacheManager:
    """商品期货统一缓存管理器。

    用法:
        cache = CommodityCacheManager()
        # 写入缓存
        cache.save_inventory("CU", df)
        # 读取缓存
        cached = cache.get_inventory("CU")
        # 如果 cached is None, 则调 AKShare 获取后写入
    """

    def __init__(self, cache_root: Optional[Path] = None):
        self._root = cache_root or _DEFAULT_CACHE_ROOT
        self._root.mkdir(parents=True, exist_ok=True)
        self._mem = InMemoryTTLCache()
        self._file = ParquetFileCache(self._root)
        logger.info("✅ CommodityCacheManager 初始化, 缓存目录: %s", self._root)

    # ==================== 缓存套路助手 ====================

    async def get_or_fetch(
        self,
        key: str,
        fetcher: Callable[[], Any],
        ttl_sec: Optional[float] = None,
    ) -> Any:
        """短路模式: 查内存 → miss → fetcher → 存 → 返回。"""
        cached = self._mem.get(key)
        if cached is not None:
            return cached
        result = await fetcher() if asyncio.iscoroutinefunction(fetcher) else fetcher()
        if result is not None:
            self._mem.set(key, result, ttl_sec=ttl_sec or self._mem._default_ttl)
        return result

    def invalidate_mem(self, key_prefix: str) -> int:
        """按前缀清理内存缓存。"""
        return self._mem.invalidate(key_prefix)

    # ==================== Layer 2: Parquet 委托 ====================

    def get_historical(self, *args, **kwargs):
        return self._file.get_historical(*args, **kwargs)
    def save_historical(self, *args, **kwargs):
        self._file.save_historical(*args, **kwargs)

    def get_inventory(self, *args, **kwargs):
        return self._file.get_inventory(*args, **kwargs)
    def save_inventory(self, *args, **kwargs):
        self._file.save_inventory(*args, **kwargs)
    def delete_inventory(self, *args, **kwargs):
        return self._file.delete_inventory(*args, **kwargs)

    def get_basis(self, *args, **kwargs):
        return self._file.get_basis(*args, **kwargs)
    def save_basis(self, *args, **kwargs):
        self._file.save_basis(*args, **kwargs)
    def delete_basis(self, *args, **kwargs):
        return self._file.delete_basis(*args, **kwargs)

    def get_positioning(self, *args, **kwargs):
        return self._file.get_positioning(*args, **kwargs)
    def save_positioning(self, *args, **kwargs):
        self._file.save_positioning(*args, **kwargs)

    def get_roll_yield(self, *args, **kwargs):
        return self._file.get_roll_yield(*args, **kwargs)
    def save_roll_yield(self, *args, **kwargs):
        self._file.save_roll_yield(*args, **kwargs)

    def get_spot_price(self, *args, **kwargs):
        return self._file.get_spot_price(*args, **kwargs)
    def save_spot_price(self, *args, **kwargs):
        self._file.save_spot_price(*args, **kwargs)

    # ==================== Layer 3: 增量合并 ====================

    @staticmethod
    def incremental_merge(
        existing: Optional[pd.DataFrame],
        new_data: pd.DataFrame,
        on_columns: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """增量合并: concat → drop_duplicates → sort_values。"""
        if existing is None or existing.empty:
            if "date" in new_data.columns:
                return new_data.sort_values("date").reset_index(drop=True)
            return new_data
        if new_data is None or new_data.empty:
            return existing
        subset = on_columns or ["date"]
        merged = pd.concat([existing, new_data], ignore_index=True)
        merged = merged.drop_duplicates(subset=subset, keep="last")
        if "date" in merged.columns:
            merged = merged.sort_values("date").reset_index(drop=True)
        return merged

    # ==================== 管理 ====================

    def clear_all(self) -> None:
        self._mem = InMemoryTTLCache()
        self._file.clear_all()

    def stats(self) -> Dict[str, Any]:
        return {
            "memory": self._mem.stats(),
            "parquet_files": self._file.file_count(),
            "cache_root": str(self._root),
        }

    @property
    def mem(self) -> InMemoryTTLCache:
        return self._mem

    @property
    def file_cache(self) -> ParquetFileCache:
        return self._file


# 全局单例
_cache_instance: Optional[CommodityCacheManager] = None


def get_commodity_cache(cache_root: Optional[Path] = None) -> CommodityCacheManager:
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = CommodityCacheManager(cache_root=cache_root)
    return _cache_instance


__all__ = [
    "CommodityCacheManager",
    "InMemoryTTLCache",
    "ParquetFileCache",
    "get_commodity_cache",
    "TTL_CONFIG",
]
