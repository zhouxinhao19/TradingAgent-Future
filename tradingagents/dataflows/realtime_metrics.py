"""
实时估值指标计算模块
基于实时行情和财务数据计算PE/PB等指标
"""
import logging
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


def calculate_realtime_pe_pb(
    symbol: str,
    db_client=None
) -> Optional[Dict[str, Any]]:
    """
    基于实时行情和财务数据计算PE/PB
    
    Args:
        symbol: 6位股票代码
        db_client: MongoDB客户端（可选，用于同步调用）
    
    Returns:
        {
            "pe": 22.5,              # 实时市盈率
            "pb": 3.2,               # 实时市净率
            "pe_ttm": 23.1,          # 实时市盈率（TTM）
            "price": 11.0,           # 当前价格
            "market_cap": 110.5,     # 实时市值（亿元）
            "updated_at": "2025-10-14T10:30:00",
            "source": "realtime_calculated",
            "is_realtime": True
        }
        如果计算失败返回 None
    """
    try:
        # 获取数据库连接（确保是同步客户端）
        if db_client is None:
            from tradingagents.config.database_manager import get_database_manager
            db_manager = get_database_manager()
            if not db_manager.is_mongodb_available():
                logger.debug("MongoDB不可用，无法计算实时PE/PB")
                return None
            db_client = db_manager.get_mongodb_client()

        # 检查是否是异步客户端（AsyncIOMotorClient）
        # 如果是异步客户端，需要转换为同步客户端
        client_type = type(db_client).__name__
        if 'AsyncIOMotorClient' in client_type or 'Motor' in client_type:
            # 这是异步客户端，创建同步客户端
            from pymongo import MongoClient
            from app.core.config import settings
            logger.debug(f"检测到异步客户端 {client_type}，转换为同步客户端")
            db_client = MongoClient(settings.MONGO_URI)

        db = db_client['tradingagents']
        code6 = str(symbol).zfill(6)

        # 1. 获取实时行情（market_quotes）
        quote = db.market_quotes.find_one({"code": code6})
        if not quote:
            logger.debug(f"未找到股票 {code6} 的实时行情")
            return None

        realtime_price = quote.get("close")
        if not realtime_price or realtime_price <= 0:
            logger.debug(f"股票 {code6} 的实时价格无效: {realtime_price}")
            return None

        # 2. 获取基础信息和财务数据（stock_basic_info）
        basic_info = db.stock_basic_info.find_one({"code": code6})
        if not basic_info:
            logger.debug(f"未找到股票 {code6} 的基础信息")
            return None
        
        # 获取财务数据
        total_shares = basic_info.get("total_share")  # 总股本（万股）
        net_profit = basic_info.get("net_profit")     # 净利润（万元）
        total_equity = basic_info.get("total_hldr_eqy_exc_min_int")  # 净资产（万元）
        
        if not total_shares or total_shares <= 0:
            logger.debug(f"股票 {code6} 的总股本无效: {total_shares}")
            return None
        
        # 3. 计算实时市值（万元）
        realtime_market_cap = realtime_price * total_shares
        
        # 4. 计算实时PE
        pe = None
        pe_ttm = None
        if net_profit and net_profit > 0:
            pe = realtime_market_cap / net_profit
            pe_ttm = pe  # 如果有TTM净利润，可以单独计算
        
        # 5. 计算实时PB
        pb = None
        pb_mrq = None
        if total_equity and total_equity > 0:
            pb = realtime_market_cap / total_equity
            pb_mrq = pb  # 如果有MRQ净资产，可以单独计算
        
        # 6. 构建返回结果
        result = {
            "pe": round(pe, 2) if pe else None,
            "pb": round(pb, 2) if pb else None,
            "pe_ttm": round(pe_ttm, 2) if pe_ttm else None,
            "pb_mrq": round(pb_mrq, 2) if pb_mrq else None,
            "price": round(realtime_price, 2),
            "market_cap": round(realtime_market_cap / 10000, 2),  # 转换为亿元
            "updated_at": quote.get("updated_at"),
            "source": "realtime_calculated",
            "is_realtime": True,
            "note": "基于实时价格和最新财报计算"
        }
        
        logger.debug(f"股票 {code6} 实时PE/PB计算成功: PE={result['pe']}, PB={result['pb']}")
        return result
        
    except Exception as e:
        logger.error(f"计算股票 {symbol} 的实时PE/PB失败: {e}", exc_info=True)
        return None


def validate_pe_pb(pe: Optional[float], pb: Optional[float]) -> bool:
    """
    验证PE/PB是否在合理范围内
    
    Args:
        pe: 市盈率
        pb: 市净率
    
    Returns:
        bool: 是否合理
    """
    # PE合理范围：-100 到 1000（允许负值，因为亏损企业PE为负）
    if pe is not None and (pe < -100 or pe > 1000):
        logger.warning(f"PE异常: {pe}")
        return False
    
    # PB合理范围：0.1 到 100
    if pb is not None and (pb < 0.1 or pb > 100):
        logger.warning(f"PB异常: {pb}")
        return False
    
    return True


def get_pe_pb_with_fallback(
    symbol: str,
    db_client=None
) -> Dict[str, Any]:
    """
    获取PE/PB，优先使用实时计算，失败时降级到静态数据
    
    Args:
        symbol: 6位股票代码
        db_client: MongoDB客户端（可选）
    
    Returns:
        {
            "pe": 22.5,
            "pb": 3.2,
            "pe_ttm": 23.1,
            "pb_mrq": 3.3,
            "source": "realtime_calculated" | "daily_basic",
            "is_realtime": True | False,
            "updated_at": "2025-10-14T10:30:00"
        }
    """
    # 1. 尝试实时计算
    realtime_metrics = calculate_realtime_pe_pb(symbol, db_client)
    if realtime_metrics:
        # 验证数据合理性
        if validate_pe_pb(realtime_metrics.get('pe'), realtime_metrics.get('pb')):
            return realtime_metrics
        else:
            logger.warning(f"股票 {symbol} 的实时PE/PB数据异常，降级到静态数据")
    
    # 2. 降级到静态数据
    try:
        if db_client is None:
            from tradingagents.config.database_manager import get_database_manager
            db_manager = get_database_manager()
            if not db_manager.is_mongodb_available():
                return {}
            db_client = db_manager.get_mongodb_client()

        # 检查是否是异步客户端
        client_type = type(db_client).__name__
        if 'AsyncIOMotorClient' in client_type or 'Motor' in client_type:
            # 这是异步客户端，创建同步客户端
            from pymongo import MongoClient
            from app.core.config import settings
            logger.debug(f"降级查询：检测到异步客户端 {client_type}，转换为同步客户端")
            db_client = MongoClient(settings.MONGO_URI)

        db = db_client['tradingagents']
        code6 = str(symbol).zfill(6)

        basic_info = db.stock_basic_info.find_one({"code": code6})
        if not basic_info:
            return {}

        return {
            "pe": basic_info.get("pe"),
            "pb": basic_info.get("pb"),
            "pe_ttm": basic_info.get("pe_ttm"),
            "pb_mrq": basic_info.get("pb_mrq"),
            "source": "daily_basic",
            "is_realtime": False,
            "updated_at": basic_info.get("updated_at"),
            "note": "使用最近一个交易日的数据"
        }

    except Exception as e:
        logger.error(f"获取股票 {symbol} 的静态PE/PB失败: {e}")
        return {}

