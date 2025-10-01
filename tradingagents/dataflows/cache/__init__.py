"""
缓存管理模块
提供统一的缓存接口，支持多种缓存策略
"""

# 导入文件缓存
try:
    from .file_cache import StockDataCache
    FILE_CACHE_AVAILABLE = True
except ImportError:
    StockDataCache = None
    FILE_CACHE_AVAILABLE = False

# 导入数据库缓存
try:
    from .db_cache import DatabaseCacheManager
    DB_CACHE_AVAILABLE = True
except ImportError:
    DatabaseCacheManager = None
    DB_CACHE_AVAILABLE = False

# 导入自适应缓存
try:
    from .adaptive import AdaptiveCacheSystem
    ADAPTIVE_CACHE_AVAILABLE = True
except ImportError:
    AdaptiveCacheSystem = None
    ADAPTIVE_CACHE_AVAILABLE = False

# 导入集成缓存
try:
    from .integrated import IntegratedCacheManager
    INTEGRATED_CACHE_AVAILABLE = True
except ImportError:
    IntegratedCacheManager = None
    INTEGRATED_CACHE_AVAILABLE = False

# 导入应用缓存适配器
try:
    from .app_adapter import AppCacheAdapter
    APP_CACHE_AVAILABLE = True
except ImportError:
    AppCacheAdapter = None
    APP_CACHE_AVAILABLE = False


# 向后兼容：保留旧的导入路径
# 这样旧代码仍然可以使用 from tradingagents.dataflows.cache_manager import StockDataCache
__all__ = [
    # 文件缓存
    'StockDataCache',
    'FILE_CACHE_AVAILABLE',
    
    # 数据库缓存
    'DatabaseCacheManager',
    'DB_CACHE_AVAILABLE',
    
    # 自适应缓存
    'AdaptiveCacheSystem',
    'ADAPTIVE_CACHE_AVAILABLE',
    
    # 集成缓存
    'IntegratedCacheManager',
    'INTEGRATED_CACHE_AVAILABLE',
    
    # 应用缓存适配器
    'AppCacheAdapter',
    'APP_CACHE_AVAILABLE',
]

