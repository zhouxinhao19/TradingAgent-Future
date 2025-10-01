"""
港股数据提供器
"""

# 导入改进的港股工具
try:
    from .improved_hk import (
        ImprovedHKStockProvider,
        get_improved_hk_provider,
        get_hk_stock_info_improved
    )
    HK_PROVIDER_AVAILABLE = True
except ImportError:
    ImprovedHKStockProvider = None
    get_improved_hk_provider = None
    get_hk_stock_info_improved = None
    HK_PROVIDER_AVAILABLE = False

__all__ = [
    'ImprovedHKStockProvider',
    'get_improved_hk_provider',
    'get_hk_stock_info_improved',
    'HK_PROVIDER_AVAILABLE',
]

