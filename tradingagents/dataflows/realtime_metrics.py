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

        logger.info(f"🔍 [实时PE计算] 开始计算股票 {code6}")

        # 1. 获取实时行情（market_quotes）
        quote = db.market_quotes.find_one({"code": code6})
        if not quote:
            logger.warning(f"⚠️ [实时PE计算-失败] 未找到股票 {code6} 的实时行情数据")
            return None

        realtime_price = quote.get("close")
        quote_updated_at = quote.get("updated_at", "N/A")

        if not realtime_price or realtime_price <= 0:
            logger.warning(f"⚠️ [实时PE计算-失败] 股票 {code6} 的实时价格无效: {realtime_price}")
            return None

        logger.info(f"   ✓ 实时股价: {realtime_price}元 (更新时间: {quote_updated_at})")

        # 2. 获取基础信息和财务数据（stock_basic_info）
        basic_info = db.stock_basic_info.find_one({"code": code6})
        if not basic_info:
            logger.warning(f"⚠️ [实时PE计算-失败] 未找到股票 {code6} 的基础信息")
            return None

        # 获取财务数据
        total_shares = basic_info.get("total_share")  # 总股本（万股）
        net_profit = basic_info.get("net_profit")     # 净利润（万元）
        total_equity = basic_info.get("total_hldr_eqy_exc_min_int")  # 净资产（万元）

        logger.info(f"   ✓ 总股本: {total_shares}万股")
        logger.info(f"   ✓ 净利润: {net_profit}万元")
        logger.info(f"   ✓ 净资产: {total_equity}万元")

        if not total_shares or total_shares <= 0:
            logger.warning(f"⚠️ [实时PE计算-失败] 股票 {code6} 的总股本无效: {total_shares}")
            return None

        # 3. 计算实时市值（万元）
        realtime_market_cap = realtime_price * total_shares
        logger.info(f"   ✓ 实时市值: {realtime_market_cap:.2f}万元 ({realtime_market_cap/10000:.2f}亿元)")

        # 4. 计算实时PE
        pe = None
        pe_ttm = None
        if net_profit and net_profit > 0:
            pe = realtime_market_cap / net_profit
            pe_ttm = pe  # 如果有TTM净利润，可以单独计算
            logger.info(f"   ✓ PE计算: {realtime_market_cap:.2f}万元 / {net_profit:.2f}万元 = {pe:.2f}倍")
        else:
            logger.warning(f"   ⚠️ PE计算失败: 净利润无效或为负 ({net_profit})")

        # 5. 计算实时PB
        pb = None
        pb_mrq = None
        if total_equity and total_equity > 0:
            pb = realtime_market_cap / total_equity
            pb_mrq = pb  # 如果有MRQ净资产，可以单独计算
            logger.info(f"   ✓ PB计算: {realtime_market_cap:.2f}万元 / {total_equity:.2f}万元 = {pb:.2f}倍")
        else:
            logger.warning(f"   ⚠️ PB计算失败: 净资产无效或为负 ({total_equity})")

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

        logger.info(f"✅ [实时PE计算-成功] 股票 {code6}: PE={result['pe']}倍, PB={result['pb']}倍")
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
    logger.info(f"🔄 [PE降级策略] 开始获取股票 {symbol} 的PE/PB")

    # 1. 尝试实时计算
    logger.info(f"   → 尝试方案1: 实时计算 (market_quotes + stock_basic_info)")
    realtime_metrics = calculate_realtime_pe_pb(symbol, db_client)
    if realtime_metrics:
        # 验证数据合理性
        pe = realtime_metrics.get('pe')
        pb = realtime_metrics.get('pb')
        if validate_pe_pb(pe, pb):
            logger.info(f"✅ [PE降级策略-成功] 使用实时计算: PE={pe}, PB={pb}")
            return realtime_metrics
        else:
            logger.warning(f"⚠️ [PE降级策略-数据异常] 实时PE/PB超出合理范围 (PE={pe}, PB={pb})，降级到静态数据")
    
    # 2. 降级到静态数据
    logger.info("   → 尝试方案2: 静态数据 (stock_basic_info)")
    try:
        if db_client is None:
            from tradingagents.config.database_manager import get_database_manager
            db_manager = get_database_manager()
            if not db_manager.is_mongodb_available():
                logger.error("❌ [PE降级策略-失败] MongoDB不可用")
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
            logger.error(f"❌ [PE降级策略-失败] 未找到股票 {code6} 的基础信息")
            return {}

        pe_static = basic_info.get("pe")
        pb_static = basic_info.get("pb")
        pe_ttm = basic_info.get("pe_ttm")
        pb_mrq = basic_info.get("pb_mrq")
        updated_at = basic_info.get("updated_at", "N/A")

        logger.info(f"✅ [PE降级策略-成功] 使用静态数据: PE={pe_static}, PB={pb_static}")
        logger.info(f"   └─ 数据来源: stock_basic_info (更新时间: {updated_at})")

        return {
            "pe": pe_static,
            "pb": pb_static,
            "pe_ttm": pe_ttm,
            "pb_mrq": pb_mrq,
            "source": "daily_basic",
            "is_realtime": False,
            "updated_at": updated_at,
            "note": "使用最近一个交易日的数据"
        }

    except Exception as e:
        logger.error(f"❌ [PE降级策略-失败] 获取股票 {symbol} 的静态PE/PB失败: {e}")
        return {}

