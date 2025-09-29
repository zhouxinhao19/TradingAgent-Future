"""
数据源提供器配置管理
"""
import os
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class DataSourceConfig:
    """数据源配置管理器"""
    
    def __init__(self):
        self._configs = {}
        self._load_configs()
    
    def _load_configs(self):
        """加载所有数据源配置"""
        # Tushare配置
        self._configs["tushare"] = {
            "enabled": self._get_bool_env("TUSHARE_ENABLED", True),
            "token": os.getenv("TUSHARE_TOKEN", ""),
            "timeout": self._get_int_env("TUSHARE_TIMEOUT", 30),
            "rate_limit": self._get_float_env("TUSHARE_RATE_LIMIT", 0.1),
            "max_retries": self._get_int_env("TUSHARE_MAX_RETRIES", 3),
            "cache_enabled": self._get_bool_env("TUSHARE_CACHE_ENABLED", True),
            "cache_ttl": self._get_int_env("TUSHARE_CACHE_TTL", 3600),
        }
        
        # AKShare配置
        self._configs["akshare"] = {
            "enabled": self._get_bool_env("AKSHARE_ENABLED", True),
            "timeout": self._get_int_env("AKSHARE_TIMEOUT", 30),
            "rate_limit": self._get_float_env("AKSHARE_RATE_LIMIT", 0.2),
            "max_retries": self._get_int_env("AKSHARE_MAX_RETRIES", 3),
            "cache_enabled": self._get_bool_env("AKSHARE_CACHE_ENABLED", True),
            "cache_ttl": self._get_int_env("AKSHARE_CACHE_TTL", 1800),
        }
        
        # BaoStock配置
        self._configs["baostock"] = {
            "enabled": self._get_bool_env("BAOSTOCK_ENABLED", True),
            "timeout": self._get_int_env("BAOSTOCK_TIMEOUT", 30),
            "rate_limit": self._get_float_env("BAOSTOCK_RATE_LIMIT", 0.1),
            "max_retries": self._get_int_env("BAOSTOCK_MAX_RETRIES", 3),
            "cache_enabled": self._get_bool_env("BAOSTOCK_CACHE_ENABLED", True),
            "cache_ttl": self._get_int_env("BAOSTOCK_CACHE_TTL", 1800),
        }
        
        # Yahoo Finance配置
        self._configs["yahoo"] = {
            "enabled": self._get_bool_env("YAHOO_ENABLED", False),
            "timeout": self._get_int_env("YAHOO_TIMEOUT", 30),
            "rate_limit": self._get_float_env("YAHOO_RATE_LIMIT", 0.5),
            "max_retries": self._get_int_env("YAHOO_MAX_RETRIES", 3),
            "cache_enabled": self._get_bool_env("YAHOO_CACHE_ENABLED", True),
            "cache_ttl": self._get_int_env("YAHOO_CACHE_TTL", 300),
        }
        
        # Finnhub配置
        self._configs["finnhub"] = {
            "enabled": self._get_bool_env("FINNHUB_ENABLED", False),
            "api_key": os.getenv("FINNHUB_API_KEY", ""),
            "timeout": self._get_int_env("FINNHUB_TIMEOUT", 30),
            "rate_limit": self._get_float_env("FINNHUB_RATE_LIMIT", 1.0),
            "max_retries": self._get_int_env("FINNHUB_MAX_RETRIES", 3),
            "cache_enabled": self._get_bool_env("FINNHUB_CACHE_ENABLED", True),
            "cache_ttl": self._get_int_env("FINNHUB_CACHE_TTL", 300),
        }
        
        # 通达信配置
        self._configs["tdx"] = {
            "enabled": self._get_bool_env("TDX_ENABLED", False),
            "timeout": self._get_int_env("TDX_TIMEOUT", 30),
            "rate_limit": self._get_float_env("TDX_RATE_LIMIT", 0.1),
            "max_retries": self._get_int_env("TDX_MAX_RETRIES", 3),
            "cache_enabled": self._get_bool_env("TDX_CACHE_ENABLED", True),
            "cache_ttl": self._get_int_env("TDX_CACHE_TTL", 300),
        }
        
        logger.info("✅ 数据源配置加载完成")
    
    def get_provider_config(self, provider_name: str) -> Dict[str, Any]:
        """
        获取指定提供器的配置
        
        Args:
            provider_name: 提供器名称
            
        Returns:
            配置字典
        """
        config = self._configs.get(provider_name.lower(), {})
        if not config:
            logger.warning(f"⚠️ 未找到 {provider_name} 的配置")
        return config
    
    def is_provider_enabled(self, provider_name: str) -> bool:
        """检查提供器是否启用"""
        config = self.get_provider_config(provider_name)
        return config.get("enabled", False)
    
    def get_all_enabled_providers(self) -> list:
        """获取所有启用的提供器名称"""
        enabled = []
        for name, config in self._configs.items():
            if config.get("enabled", False):
                enabled.append(name)
        return enabled
    
    def _get_bool_env(self, key: str, default: bool) -> bool:
        """获取布尔型环境变量"""
        value = os.getenv(key, str(default)).lower()
        return value in ("true", "1", "yes", "on")
    
    def _get_int_env(self, key: str, default: int) -> int:
        """获取整型环境变量"""
        try:
            return int(os.getenv(key, str(default)))
        except ValueError:
            return default
    
    def _get_float_env(self, key: str, default: float) -> float:
        """获取浮点型环境变量"""
        try:
            return float(os.getenv(key, str(default)))
        except ValueError:
            return default


# 全局配置实例
_config_instance = None

def get_data_source_config() -> DataSourceConfig:
    """获取全局数据源配置实例"""
    global _config_instance
    if _config_instance is None:
        _config_instance = DataSourceConfig()
    return _config_instance

def get_provider_config(provider_name: str) -> Dict[str, Any]:
    """获取指定提供器配置的便捷函数"""
    config = get_data_source_config()
    return config.get_provider_config(provider_name)


class DataSourceManager:
    """数据源管理器"""
    
    def __init__(self):
        self.config = get_data_source_config()
        self.providers = {}
        self.logger = logging.getLogger(__name__)
    
    async def initialize_providers(self):
        """初始化所有启用的数据源提供器"""
        enabled_providers = self.config.get_all_enabled_providers()
        
        for provider_name in enabled_providers:
            try:
                provider = await self._create_provider(provider_name)
                if provider and await provider.connect():
                    self.providers[provider_name] = provider
                    self.logger.info(f"✅ {provider_name} 提供器初始化成功")
                else:
                    self.logger.warning(f"⚠️ {provider_name} 提供器初始化失败")
            except Exception as e:
                self.logger.error(f"❌ {provider_name} 提供器初始化异常: {e}")
    
    async def _create_provider(self, provider_name: str):
        """创建指定的数据源提供器"""
        try:
            if provider_name == "tushare":
                from .providers.tushare_provider import TushareProvider
                return TushareProvider()
            elif provider_name == "akshare":
                from .providers.akshare_provider import AKShareProvider
                return AKShareProvider()
            elif provider_name == "baostock":
                from .providers.baostock_provider import BaoStockProvider
                return BaoStockProvider()
            elif provider_name == "yahoo":
                from .providers.yahoo_provider import YahooProvider
                return YahooProvider()
            elif provider_name == "finnhub":
                from .providers.finnhub_provider import FinnhubProvider
                return FinnhubProvider()
            elif provider_name == "tdx":
                from .providers.tdx_provider import TDXProvider
                return TDXProvider()
            else:
                self.logger.error(f"❌ 未知的提供器类型: {provider_name}")
                return None
        except ImportError as e:
            self.logger.warning(f"⚠️ {provider_name} 提供器导入失败: {e}")
            return None
    
    def get_provider(self, provider_name: str):
        """获取指定的数据源提供器"""
        return self.providers.get(provider_name.lower())
    
    def get_available_providers(self) -> list:
        """获取所有可用的提供器"""
        return list(self.providers.keys())
    
    def get_primary_provider(self):
        """获取主要提供器（优先级最高）"""
        # 按优先级顺序返回第一个可用的提供器
        priority_order = ["tushare", "akshare", "baostock", "yahoo", "finnhub", "tdx"]
        
        for provider_name in priority_order:
            provider = self.providers.get(provider_name)
            if provider and provider.is_available():
                return provider
        
        return None
    
    async def cleanup(self):
        """清理所有提供器连接"""
        for provider_name, provider in self.providers.items():
            try:
                await provider.disconnect()
                self.logger.info(f"✅ {provider_name} 提供器已断开连接")
            except Exception as e:
                self.logger.error(f"❌ {provider_name} 提供器断开连接失败: {e}")
        
        self.providers.clear()


# 全局管理器实例
_manager_instance = None

async def get_data_source_manager() -> DataSourceManager:
    """获取全局数据源管理器实例"""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = DataSourceManager()
        await _manager_instance.initialize_providers()
    return _manager_instance
