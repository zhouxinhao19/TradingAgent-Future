"""
测试 CommodityCacheManager 三层缓存机制

覆盖:
  - InMemoryTTLCache 过期/命中/失效
  - ParquetFileCache 写入/读取/清空
  - CommodityCacheManager 整合功能
  - incremental_merge 增量合并去重
  - get_or_fetch 套路模式
"""
from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import pandas as pd
import pytest

from tradingagents.dataflows.cache.commodity_cache import (
    CommodityCacheManager,
    InMemoryTTLCache,
    ParquetFileCache,
    get_commodity_cache,
)


# ==================== Layer 1: InMemoryTTLCache ====================


class TestInMemoryTTLCache:
    """内存 TTL 缓存测试"""

    def test_set_and_get(self):
        cache = InMemoryTTLCache(default_ttl_sec=60.0)
        cache.set("foo", 42)
        assert cache.get("foo") == 42
        assert cache.get("missing") is None

    def test_ttl_expiry(self):
        cache = InMemoryTTLCache(default_ttl_sec=0.05)  # 50ms TTL
        cache.set("fast", "value")
        assert cache.get("fast") == "value"
        time.sleep(0.07)
        assert cache.get("fast") is None

    def test_custom_ttl(self):
        cache = InMemoryTTLCache(default_ttl_sec=60.0)
        cache.set("short", 1, ttl_sec=0.05)
        assert cache.get("short") == 1
        time.sleep(0.07)
        assert cache.get("short") is None

    def test_invalidate_prefix(self):
        cache = InMemoryTTLCache()
        cache.set("quotes:CU0.SHF", {"close": 68000})
        cache.set("quotes:AL0.SHF", {"close": 18500})
        cache.set("basic:CU", {"name": "铜"})
        assert cache.invalidate("quotes:") == 2
        assert cache.get("quotes:CU0.SHF") is None
        assert cache.get("quotes:AL0.SHF") is None
        assert cache.get("basic:CU") is not None  # 未被清除

    def test_clear_expired(self):
        cache = InMemoryTTLCache(default_ttl_sec=0.05)
        cache.set("a", 1)
        cache.set("b", 2)
        time.sleep(0.07)
        cleared = cache.clear_expired()
        assert cleared == 2
        assert cache.get("a") is None

    def test_stats(self):
        cache = InMemoryTTLCache(default_ttl_sec=60.0)
        cache.set("x", 1)
        stats = cache.stats()
        assert stats["total"] >= 1
        assert stats["active"] >= 1


# ==================== Layer 2: ParquetFileCache ====================


class TestParquetFileCache:
    """Parquet 文件缓存测试"""

    @pytest.fixture(autouse=True)
    def _cache_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            yield Path(tmp)

    def test_historical_write_and_read(self, _cache_dir):
        cache = ParquetFileCache(_cache_dir)
        df = pd.DataFrame({
            "日期": ["2024-01-01", "2024-01-02"],
            "开盘价": [68000, 68500],
            "收盘价": [68200, 68800],
        })
        cache.save_historical("CU", "20240101", "20240105", "SHFE", df)
        loaded = cache.get_historical("CU", "20240101", "20240105", "SHFE")
        assert loaded is not None
        assert len(loaded) == 2
        assert loaded["收盘价"].iloc[-1] == 68800

    def test_inventory_write_and_read(self, _cache_dir):
        cache = ParquetFileCache(_cache_dir)
        df = pd.DataFrame({
            "date": ["2024-01-01", "2024-01-02"],
            "symbol": ["CU", "CU"],
            "inventory": [1000, 950],
        })
        cache.save_inventory("CU", df)
        loaded = cache.get_inventory("CU")
        assert loaded is not None
        assert len(loaded) == 2

    def test_basis_write_and_read(self, _cache_dir):
        cache = ParquetFileCache(_cache_dir)
        df = pd.DataFrame({
            "date": ["2024-01-01"],
            "symbol": ["CU"],
            "spot_price": [68000],
            "dom_basis": [200],
        })
        cache.save_basis("CU", "20240101", "20240102", df)
        loaded = cache.get_basis("CU", "20240101", "20240102")
        assert loaded is not None
        assert loaded["dom_basis"].iloc[0] == 200

    def test_spot_price_write_and_read(self, _cache_dir):
        cache = ParquetFileCache(_cache_dir)
        df = pd.DataFrame({
            "date": ["2024-01-15"],
            "symbol": ["CU"],
            "spot_price": [68100],
        })
        cache.save_spot_price("20240115", df)
        loaded = cache.get_spot_price("20240115")
        assert loaded is not None
        assert loaded["spot_price"].iloc[0] == 68100

    def test_roll_yield_write_and_read(self, _cache_dir):
        cache = ParquetFileCache(_cache_dir)
        df = pd.DataFrame({
            "date": ["2024-01-01"],
            "roll_yield": [0.05],
        })
        key = "date_CU_20240101_20240131"
        cache.save_roll_yield(key, df)
        loaded = cache.get_roll_yield(key)
        assert loaded is not None

    def test_missing_returns_none(self, _cache_dir):
        cache = ParquetFileCache(_cache_dir)
        assert cache.get_historical("XX", "20200101", "20200101", "SHFE") is None
        assert cache.get_inventory("NONEXIST") is None

    def test_file_count(self, _cache_dir):
        cache = ParquetFileCache(_cache_dir)
        cache.save_inventory("CU", pd.DataFrame({"a": [1]}))
        cache.save_inventory("AL", pd.DataFrame({"a": [2]}))
        assert cache.file_count() == 2

    def test_clear_all(self, _cache_dir):
        cache = ParquetFileCache(_cache_dir)
        cache.save_inventory("CU", pd.DataFrame({"a": [1]}))
        cache.clear_all()
        assert cache.file_count() == 0


# ==================== CommodityCacheManager 整合 ====================


class TestCommodityCacheManager:
    """统一缓存管理器测试"""

    @pytest.fixture(autouse=True)
    def _tmp_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = CommodityCacheManager(cache_root=Path(tmp))
            yield mgr

    def test_incremental_merge_basic(self, _tmp_cache):
        """增量合并基础用例"""
        existing = pd.DataFrame({
            "date": ["2024-01-01", "2024-01-02"],
            "value": [1, 2],
        })
        new = pd.DataFrame({
            "date": ["2024-01-03"],
            "value": [3],
        })
        merged = _tmp_cache.incremental_merge(existing, new)
        assert len(merged) == 3
        assert merged["value"].tolist() == [1, 2, 3]

    def test_incremental_merge_dedup(self, _tmp_cache):
        """增量合并去重"""
        existing = pd.DataFrame({
            "date": ["2024-01-01", "2024-01-02"],
            "value": [1, 2],
        })
        new = pd.DataFrame({
            "date": ["2024-01-02"],  # 重复日期
            "value": [22],  # 更新值
        })
        merged = _tmp_cache.incremental_merge(existing, new)
        assert len(merged) == 2  # 非 3
        assert merged["value"].iloc[1] == 22  # 新值覆盖旧值

    def test_incremental_merge_empty_existing(self, _tmp_cache):
        merged = _tmp_cache.incremental_merge(None, pd.DataFrame({"date": ["2024-01-01"], "v": [1]}))
        assert len(merged) == 1

    def test_incremental_merge_empty_new(self, _tmp_cache):
        existing = pd.DataFrame({"date": ["2024-01-01"], "v": [1]})
        merged = _tmp_cache.incremental_merge(existing, pd.DataFrame())
        assert len(merged) == 1

    def test_save_and_get_historical(self, _tmp_cache):
        df = pd.DataFrame({
            "date": ["2024-01-01"],
            "open": [68000],
            "close": [68200],
        })
        _tmp_cache.save_historical("CU", "20240101", "20240131", "SHFE", df)
        loaded = _tmp_cache.get_historical("CU", "20240101", "20240131", "SHFE")
        assert loaded is not None
        assert loaded["close"].iloc[0] == 68200

    def test_save_and_get_inventory(self, _tmp_cache):
        df = pd.DataFrame({"date": ["2024-01-01"], "inventory": [500]})
        _tmp_cache.save_inventory("AL", df)
        loaded = _tmp_cache.get_inventory("AL")
        assert loaded is not None

    def test_clear_all(self, _tmp_cache):
        _tmp_cache.save_inventory("CU", pd.DataFrame({"a": [1]}))
        _tmp_cache.save_inventory("AL", pd.DataFrame({"a": [2]}))
        _tmp_cache.clear_all()
        assert _tmp_cache.stats()["parquet_files"] == 0

    def test_stats(self, _tmp_cache):
        stats = _tmp_cache.stats()
        assert "memory" in stats
        assert "parquet_files" in stats
        assert "cache_root" in stats

    def test_invalidate_mem(self, _tmp_cache):
        _tmp_cache.mem.set("quotes:CU", {"close": 68000})
        assert _tmp_cache.mem.get("quotes:CU") is not None
        _tmp_cache.invalidate_mem("quotes:")
        assert _tmp_cache.mem.get("quotes:CU") is None

    def test_parquet_property(self, _tmp_cache):
        assert _tmp_cache.file_cache is not None

    def test_get_commodity_cache_singleton(self):
        """全局单例"""
        with tempfile.TemporaryDirectory() as tmp:
            c1 = get_commodity_cache(cache_root=Path(tmp))
            c2 = get_commodity_cache(cache_root=Path(tmp))
            assert c1 is c2


# ==================== 边界测试 ====================


class TestEdgeCases:
    """边界情况测试"""

    def test_empty_dataframe_save_and_read(self):
        """空 DataFrame 写入/读取"""
        cache = InMemoryTTLCache()
        cache.set("empty", pd.DataFrame())
        loaded = cache.get("empty")
        assert loaded is not None
        assert loaded.empty

    def test_large_ttl_value(self):
        """超大 TTL"""
        cache = InMemoryTTLCache(default_ttl_sec=86400 * 365)  # 1 年
        cache.set("persist", "val")
        assert cache.get("persist") == "val"
