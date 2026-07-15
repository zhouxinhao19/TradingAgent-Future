# 导入日志模块
from tradingagents.utils.logging_manager import get_logger
logger = get_logger('agents')

# 导入新闻模块
try:
    from .news import getNewsData, fetch_top_from_category
except ImportError:
    getNewsData = None
    fetch_top_from_category = None

__all__ = [
    "getNewsData",
    "fetch_top_from_category",
]
