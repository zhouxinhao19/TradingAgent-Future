#!/usr/bin/env python3
"""
增强数据访问适配器
根据 TA_USE_APP_CACHE 配置，优先使用 MongoDB 中的同步数据
"""

import pandas as pd
from typing import Optional, Dict, Any, List, Union
from datetime import datetime, timedelta, timezone

# 导入日志模块
from tradingagents.utils.logging_manager import get_logger
logger = get_logger('agents')

# 导入配置
from tradingagents.config.runtime_settings import use_app_cache_enabled

class EnhancedDataAdapter:
    """增强数据访问适配器"""
    
    def __init__(self):
        self.use_app_cache = use_app_cache_enabled(False)
        self.mongodb_client = None
        self.db = None
        
        if self.use_app_cache:
            self._init_mongodb_connection()
            logger.info("🔄 增强数据适配器已启用 - 优先使用MongoDB数据")
        else:
            logger.info("📁 增强数据适配器使用传统缓存模式")
    
    def _init_mongodb_connection(self):
        """初始化MongoDB连接"""
        try:
            from tradingagents.config.database_manager import get_mongodb_client
            self.mongodb_client = get_mongodb_client()
            if self.mongodb_client:
                self.db = self.mongodb_client.get_database('tradingagents')
                logger.debug("✅ MongoDB连接初始化成功")
            else:
                logger.warning("⚠️ MongoDB客户端不可用，回退到传统模式")
                self.use_app_cache = False
        except Exception as e:
            logger.warning(f"⚠️ MongoDB连接初始化失败: {e}")
            self.use_app_cache = False
    
    def get_stock_basic_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取股票基础信息"""
        if not self.use_app_cache or self.db is None:
            return None
            
        try:
            code6 = str(symbol).zfill(6)
            collection = self.db.stock_basic_info
            
            doc = collection.find_one({"code": code6}, {"_id": 0})
            if doc:
                logger.debug(f"✅ 从MongoDB获取基础信息: {symbol}")
                return doc
            else:
                logger.debug(f"📊 MongoDB中未找到基础信息: {symbol}")
                return None
                
        except Exception as e:
            logger.warning(f"⚠️ 获取基础信息失败: {e}")
            return None
    
    def get_historical_data(self, symbol: str, start_date: str = None, end_date: str = None, 
                          period: str = "daily") -> Optional[pd.DataFrame]:
        """获取历史数据"""
        if not self.use_app_cache or self.db is None:
            return None
            
        try:
            code6 = str(symbol).zfill(6)
            collection = self.db.stock_daily_quotes
            
            # 构建查询条件
            query = {"symbol": code6}
            
            if start_date:
                query["trade_date"] = {"$gte": start_date}
            if end_date:
                if "trade_date" in query:
                    query["trade_date"]["$lte"] = end_date
                else:
                    query["trade_date"] = {"$lte": end_date}
            
            # 查询数据
            cursor = collection.find(query, {"_id": 0}).sort("trade_date", 1)
            data = list(cursor)
            
            if data:
                df = pd.DataFrame(data)
                logger.debug(f"✅ 从MongoDB获取历史数据: {symbol}, 记录数: {len(df)}")
                return df
            else:
                logger.debug(f"📊 MongoDB中未找到历史数据: {symbol}")
                return None
                
        except Exception as e:
            logger.warning(f"⚠️ 获取历史数据失败: {e}")
            return None
    
    def get_financial_data(self, symbol: str, report_period: str = None) -> Optional[Dict[str, Any]]:
        """获取财务数据"""
        if not self.use_app_cache or self.db is None:
            return None

        try:
            code6 = str(symbol).zfill(6)
            collection = self.db.stock_financial_data  # 修正集合名称
            
            # 构建查询条件
            query = {"symbol": code6}
            if report_period:
                query["report_period"] = report_period
            
            # 获取最新的财务数据
            doc = collection.find_one(query, {"_id": 0}, sort=[("report_period", -1)])
            
            if doc:
                logger.debug(f"✅ 从MongoDB获取财务数据: {symbol}")
                return doc
            else:
                logger.debug(f"📊 MongoDB中未找到财务数据: {symbol}")
                return None
                
        except Exception as e:
            logger.warning(f"⚠️ 获取财务数据失败: {e}")
            return None
    
    def get_news_data(self, symbol: str = None, hours_back: int = 24, limit: int = 20) -> Optional[List[Dict[str, Any]]]:
        """获取新闻数据"""
        if not self.use_app_cache or self.db is None:
            return None

        try:
            collection = self.db.stock_news  # 修正集合名称
            
            # 构建查询条件
            query = {}
            if symbol:
                code6 = str(symbol).zfill(6)
                query["symbol"] = code6
            
            # 时间范围
            if hours_back:
                start_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
                query["publish_time"] = {"$gte": start_time}
            
            # 查询数据
            cursor = collection.find(query, {"_id": 0}).sort("publish_time", -1).limit(limit)
            data = list(cursor)
            
            if data:
                logger.debug(f"✅ 从MongoDB获取新闻数据: {len(data)}条")
                return data
            else:
                logger.debug(f"📊 MongoDB中未找到新闻数据")
                return None
                
        except Exception as e:
            logger.warning(f"⚠️ 获取新闻数据失败: {e}")
            return None
    
    def get_social_media_data(self, symbol: str = None, hours_back: int = 24, limit: int = 20) -> Optional[List[Dict[str, Any]]]:
        """获取社媒数据"""
        if not self.use_app_cache or self.db is None:
            return None
            
        try:
            collection = self.db.social_media_messages
            
            # 构建查询条件
            query = {}
            if symbol:
                code6 = str(symbol).zfill(6)
                query["symbol"] = code6
            
            # 时间范围
            if hours_back:
                start_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
                query["publish_time"] = {"$gte": start_time}
            
            # 查询数据
            cursor = collection.find(query, {"_id": 0}).sort("publish_time", -1).limit(limit)
            data = list(cursor)
            
            if data:
                logger.debug(f"✅ 从MongoDB获取社媒数据: {len(data)}条")
                return data
            else:
                logger.debug(f"📊 MongoDB中未找到社媒数据")
                return None
                
        except Exception as e:
            logger.warning(f"⚠️ 获取社媒数据失败: {e}")
            return None
    
    def get_market_quotes(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取实时行情数据"""
        if not self.use_app_cache or self.db is None:
            return None
            
        try:
            code6 = str(symbol).zfill(6)
            collection = self.db.market_quotes
            
            # 获取最新行情
            doc = collection.find_one({"code": code6}, {"_id": 0}, sort=[("timestamp", -1)])
            
            if doc:
                logger.debug(f"✅ 从MongoDB获取行情数据: {symbol}")
                return doc
            else:
                logger.debug(f"📊 MongoDB中未找到行情数据: {symbol}")
                return None
                
        except Exception as e:
            logger.warning(f"⚠️ 获取行情数据失败: {e}")
            return None


# 全局实例
_enhanced_adapter = None

def get_enhanced_data_adapter() -> EnhancedDataAdapter:
    """获取增强数据适配器实例"""
    global _enhanced_adapter
    if _enhanced_adapter is None:
        _enhanced_adapter = EnhancedDataAdapter()
    return _enhanced_adapter


def get_stock_data_with_fallback(symbol: str, start_date: str = None, end_date: str = None, 
                                fallback_func=None) -> Union[pd.DataFrame, str, None]:
    """
    带降级的股票数据获取
    
    Args:
        symbol: 股票代码
        start_date: 开始日期
        end_date: 结束日期
        fallback_func: 降级函数
    
    Returns:
        优先返回MongoDB数据，失败时调用降级函数
    """
    adapter = get_enhanced_data_adapter()
    
    # 尝试从MongoDB获取
    if adapter.use_app_cache:
        df = adapter.get_historical_data(symbol, start_date, end_date)
        if df is not None and not df.empty:
            logger.info(f"📊 使用MongoDB历史数据: {symbol}")
            return df
    
    # 降级到传统方式
    if fallback_func:
        logger.info(f"🔄 降级到传统数据源: {symbol}")
        return fallback_func(symbol, start_date, end_date)
    
    return None


def get_financial_data_with_fallback(symbol: str, fallback_func=None) -> Union[Dict[str, Any], str, None]:
    """
    带降级的财务数据获取
    
    Args:
        symbol: 股票代码
        fallback_func: 降级函数
    
    Returns:
        优先返回MongoDB数据，失败时调用降级函数
    """
    adapter = get_enhanced_data_adapter()
    
    # 尝试从MongoDB获取
    if adapter.use_app_cache:
        data = adapter.get_financial_data(symbol)
        if data:
            logger.info(f"💰 使用MongoDB财务数据: {symbol}")
            return data
    
    # 降级到传统方式
    if fallback_func:
        logger.info(f"🔄 降级到传统数据源: {symbol}")
        return fallback_func(symbol)
    
    return None
