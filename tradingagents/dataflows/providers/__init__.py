"""
统一数据源提供器包
"""
from .base_provider import BaseStockDataProvider

# 动态导入所有提供器
try:
    from .tushare_provider import TushareProvider
except ImportError:
    TushareProvider = None

try:
    from .akshare_provider import AKShareProvider  
except ImportError:
    AKShareProvider = None

try:
    from .baostock_provider import BaoStockProvider
except ImportError:
    BaoStockProvider = None

try:
    from .yahoo_provider import YahooProvider
except ImportError:
    YahooProvider = None

try:
    from .finnhub_provider import FinnhubProvider
except ImportError:
    FinnhubProvider = None

try:
    from .tdx_provider import TDXProvider
except ImportError:
    TDXProvider = None

__all__ = [
    'BaseStockDataProvider',
    'TushareProvider',
    'AKShareProvider', 
    'BaoStockProvider',
    'YahooProvider',
    'FinnhubProvider',
    'TDXProvider'
]
