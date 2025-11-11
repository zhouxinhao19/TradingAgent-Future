"""
美股数据源管理器

参考 A股数据源管理器实现，支持：
- 从数据库读取数据源配置和优先级
- 多数据源自动降级
- 数据源健康检查
- 统一的错误处理

支持的数据源：
- yfinance: 股票价格和技术指标
- alpha_vantage: 基本面和新闻数据
- finnhub: 备用数据源
"""

import os
from enum import Enum
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

# 导入日志模块
from tradingagents.utils.logging_manager import get_logger
logger = get_logger('agents')

# 导入数据源代码常量
from tradingagents.constants.data_sources import DataSourceCode


class USDataSource(Enum):
    """美股数据源枚举"""
    YFINANCE = "yfinance"
    ALPHA_VANTAGE = "alpha_vantage"
    FINNHUB = "finnhub"
    MONGODB = "mongodb"  # 缓存


class USDataSourceManager:
    """
    美股数据源管理器
    
    参考 A股数据源管理器 (tradingagents/dataflows/data_source_manager.py) 实现
    """
    
    def __init__(self):
        """初始化美股数据源管理器"""
        # 检查是否启用 MongoDB 缓存
        self.use_mongodb_cache = self._check_mongodb_enabled()
        
        # 检查可用的数据源
        self.available_sources = self._check_available_sources()
        
        # 设置默认数据源
        self.default_source = self._get_default_source()
        self.current_source = self.default_source
        
        logger.info(f"📊 美股数据源管理器初始化完成")
        logger.info(f"   MongoDB缓存: {'✅ 已启用' if self.use_mongodb_cache else '❌ 未启用'}")
        logger.info(f"   默认数据源: {self.default_source.value}")
        logger.info(f"   可用数据源: {[s.value for s in self.available_sources]}")
    
    def _check_mongodb_enabled(self) -> bool:
        """检查是否启用MongoDB缓存"""
        try:
            from tradingagents.config.runtime_settings import use_app_cache_enabled
            return use_app_cache_enabled()
        except Exception as e:
            logger.debug(f"无法检查MongoDB缓存状态: {e}")
            return False
    
    def _get_data_source_priority_order(self, symbol: Optional[str] = None) -> List[USDataSource]:
        """
        从数据库获取美股数据源优先级顺序（用于降级）
        
        参考 A股实现：tradingagents/dataflows/data_source_manager.py::_get_data_source_priority_order
        
        Args:
            symbol: 股票代码（用于识别市场类型）
            
        Returns:
            按优先级排序的数据源列表（不包含MongoDB）
        """
        try:
            # 从数据库读取数据源配置
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()
            
            # 方法1: 从 datasource_groupings 集合读取（推荐）
            groupings_collection = db.datasource_groupings
            groupings = list(groupings_collection.find({
                "market_category_id": "us_stocks",
                "enabled": True
            }).sort("priority", -1))  # 降序排序，优先级高的在前
            
            if groupings:
                # 转换为 USDataSource 枚举
                source_mapping = {
                    DataSourceCode.YFINANCE: USDataSource.YFINANCE,
                    DataSourceCode.ALPHA_VANTAGE: USDataSource.ALPHA_VANTAGE,
                    DataSourceCode.FINNHUB: USDataSource.FINNHUB,
                }
                
                result = []
                for grouping in groupings:
                    ds_name = grouping.get('data_source_name', '').lower()
                    if ds_name in source_mapping:
                        source = source_mapping[ds_name]
                        # 排除 MongoDB（MongoDB 是最高优先级，不参与降级）
                        if source != USDataSource.MONGODB and source in self.available_sources:
                            result.append(source)
                
                if result:
                    logger.info(f"✅ [美股数据源优先级] 从数据库读取: {[s.value for s in result]}")
                    return result
            
            # 方法2: 从 system_configs 集合读取（兼容旧版）
            config_collection = db.system_configs
            config_data = config_collection.find_one(
                {"is_active": True},
                sort=[("version", -1)]
            )
            
            if config_data and config_data.get('data_source_configs'):
                data_source_configs = config_data.get('data_source_configs', [])
                
                # 过滤出美股数据源
                enabled_sources = []
                for ds in data_source_configs:
                    if not ds.get('enabled', True):
                        continue
                    
                    # 检查是否支持美股市场
                    market_categories = ds.get('market_categories', [])
                    if market_categories and 'us_stocks' not in market_categories:
                        continue
                    
                    enabled_sources.append(ds)
                
                # 按优先级排序
                enabled_sources.sort(key=lambda x: x.get('priority', 0), reverse=True)
                
                # 转换为 USDataSource 枚举
                source_mapping = {
                    DataSourceCode.YFINANCE: USDataSource.YFINANCE,
                    DataSourceCode.ALPHA_VANTAGE: USDataSource.ALPHA_VANTAGE,
                    DataSourceCode.FINNHUB: USDataSource.FINNHUB,
                }
                
                result = []
                for ds in enabled_sources:
                    ds_type = ds.get('type', '').lower()
                    if ds_type in source_mapping:
                        source = source_mapping[ds_type]
                        if source != USDataSource.MONGODB and source in self.available_sources:
                            result.append(source)
                
                if result:
                    logger.info(f"✅ [美股数据源优先级] 从数据库读取: {[s.value for s in result]}")
                    return result
            
            logger.warning("⚠️ [美股数据源优先级] 数据库中没有配置，使用默认顺序")
            
        except Exception as e:
            logger.warning(f"⚠️ [美股数据源优先级] 从数据库读取失败: {e}，使用默认顺序")
        
        # 回退到默认顺序
        # 默认优先级：yfinance > Alpha Vantage > Finnhub
        default_order = [
            USDataSource.YFINANCE,
            USDataSource.ALPHA_VANTAGE,
            USDataSource.FINNHUB,
        ]
        
        # 只返回可用的数据源
        return [s for s in default_order if s in self.available_sources]
    
    def _get_default_source(self) -> USDataSource:
        """获取默认数据源"""
        # 如果启用MongoDB缓存，MongoDB作为最高优先级数据源
        if self.use_mongodb_cache:
            return USDataSource.MONGODB
        
        # 从环境变量获取，默认使用 yfinance
        env_source = os.getenv('DEFAULT_US_DATA_SOURCE', DataSourceCode.YFINANCE).lower()
        
        # 映射到枚举
        source_mapping = {
            DataSourceCode.YFINANCE: USDataSource.YFINANCE,
            DataSourceCode.ALPHA_VANTAGE: USDataSource.ALPHA_VANTAGE,
            DataSourceCode.FINNHUB: USDataSource.FINNHUB,
        }
        
        return source_mapping.get(env_source, USDataSource.YFINANCE)
    
    def _check_available_sources(self) -> List[USDataSource]:
        """
        检查可用的数据源
        
        参考 A股实现：tradingagents/dataflows/data_source_manager.py::_check_available_sources
        """
        available = []
        
        # 从数据库读取数据源配置，获取启用状态
        enabled_sources_in_db = set()
        try:
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()
            
            # 方法1: 从 datasource_groupings 读取
            groupings = list(db.datasource_groupings.find({
                "market_category_id": "us_stocks",
                "enabled": True
            }))
            
            if groupings:
                for grouping in groupings:
                    ds_name = grouping.get('data_source_name', '').lower()
                    enabled_sources_in_db.add(ds_name)
                logger.info(f"✅ [美股数据源配置] 从数据库读取到已启用的数据源: {enabled_sources_in_db}")
            else:
                # 方法2: 从 system_configs 读取
                config_data = db.system_configs.find_one(
                    {"is_active": True},
                    sort=[("version", -1)]
                )
                
                if config_data and config_data.get('data_source_configs'):
                    for ds in config_data.get('data_source_configs', []):
                        if ds.get('enabled', True):
                            market_categories = ds.get('market_categories', [])
                            if not market_categories or 'us_stocks' in market_categories:
                                ds_type = ds.get('type', '').lower()
                                enabled_sources_in_db.add(ds_type)
                    logger.info(f"✅ [美股数据源配置] 从数据库读取到已启用的数据源: {enabled_sources_in_db}")
                else:
                    # 默认所有数据源都启用
                    enabled_sources_in_db = {'mongodb', 'yfinance', 'alpha_vantage', 'finnhub'}
                    logger.warning("⚠️ [美股数据源配置] 数据库中没有配置，默认启用所有数据源")
        except Exception as e:
            logger.warning(f"⚠️ [美股数据源配置] 从数据库读取失败: {e}，默认启用所有数据源")
            enabled_sources_in_db = {'mongodb', 'yfinance', 'alpha_vantage', 'finnhub'}
        
        # 检查 MongoDB
        if 'mongodb' in enabled_sources_in_db and self.use_mongodb_cache:
            available.append(USDataSource.MONGODB)
            logger.info("✅ MongoDB缓存可用且已启用")
        
        # 检查 yfinance
        if 'yfinance' in enabled_sources_in_db:
            try:
                import yfinance as yf
                available.append(USDataSource.YFINANCE)
                logger.info("✅ yfinance数据源可用且已启用")
            except ImportError:
                logger.warning("⚠️ yfinance数据源不可用: 库未安装")
        else:
            logger.info("ℹ️ yfinance数据源已在数据库中禁用")
        
        # 检查 Alpha Vantage
        if 'alpha_vantage' in enabled_sources_in_db:
            try:
                # 检查 API Key 是否配置
                api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
                if api_key:
                    available.append(USDataSource.ALPHA_VANTAGE)
                    logger.info("✅ Alpha Vantage数据源可用且已启用")
                else:
                    logger.warning("⚠️ Alpha Vantage数据源不可用: API Key未配置")
            except Exception as e:
                logger.warning(f"⚠️ Alpha Vantage数据源检查失败: {e}")
        else:
            logger.info("ℹ️ Alpha Vantage数据源已在数据库中禁用")
        
        # 检查 Finnhub
        if 'finnhub' in enabled_sources_in_db:
            try:
                # 检查 API Key 是否配置
                api_key = os.getenv("FINNHUB_API_KEY")
                if api_key:
                    available.append(USDataSource.FINNHUB)
                    logger.info("✅ Finnhub数据源可用且已启用")
                else:
                    logger.warning("⚠️ Finnhub数据源不可用: API Key未配置")
            except Exception as e:
                logger.warning(f"⚠️ Finnhub数据源检查失败: {e}")
        else:
            logger.info("ℹ️ Finnhub数据源已在数据库中禁用")
        
        return available
    
    def get_current_source(self) -> USDataSource:
        """获取当前数据源"""
        return self.current_source
    
    def set_current_source(self, source: USDataSource) -> bool:
        """设置当前数据源"""
        if source in self.available_sources:
            self.current_source = source
            logger.info(f"✅ 美股数据源已切换到: {source.value}")
            return True
        else:
            logger.error(f"❌ 美股数据源不可用: {source.value}")
            return False


# 全局单例
_us_data_source_manager = None


def get_us_data_source_manager() -> USDataSourceManager:
    """获取美股数据源管理器单例"""
    global _us_data_source_manager
    if _us_data_source_manager is None:
        _us_data_source_manager = USDataSourceManager()
    return _us_data_source_manager

