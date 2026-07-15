#!/usr/bin/env python3
"""
MongoDB 缓存适配器 (Phase 5: 已移除股票缓存逻辑，commodity 使用独立数据管道)
"""

import pandas as pd
from typing import Optional
import logging

logger = logging.getLogger("mongodb_cache_adapter")


class MongoDBCacheAdapter:
    """MongoDB 缓存适配器（简化版，仅保留通用接口）"""

    def __init__(self):
        self.use_app_cache = False
        self.db = None

    def get_historical_data(self, symbol: str, start_date: str = None, end_date: str = None,
                           period: str = "daily") -> Optional[pd.DataFrame]:
        """获取历史数据（占位，commodity 使用独立数据管道）"""
        return None


# 全局实例
_mongodb_cache_adapter = None


def get_mongodb_cache_adapter() -> MongoDBCacheAdapter:
    """获取 MongoDB 缓存适配器实例"""
    global _mongodb_cache_adapter
    if _mongodb_cache_adapter is None:
        _mongodb_cache_adapter = MongoDBCacheAdapter()
    return _mongodb_cache_adapter


# 向后兼容的别名
def get_enhanced_data_adapter() -> MongoDBCacheAdapter:
    """获取增强数据适配器实例（向后兼容）"""
    return get_mongodb_cache_adapter()
