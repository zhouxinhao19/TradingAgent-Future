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
    基于实时行情和 Tushare TTM 数据计算动态 PE/PB

    计算逻辑：
    1. 从 stock_basic_info 获取 Tushare 的 pe_ttm（基于昨日收盘价）
    2. 反推 TTM 净利润 = 总市值 / pe_ttm
    3. 使用实时股价计算实时市值
    4. 计算动态 PE_TTM = 实时市值 / TTM 净利润

    Args:
        symbol: 6位股票代码
        db_client: MongoDB客户端（可选，用于同步调用）

    Returns:
        {
            "pe": 22.5,              # 动态市盈率（基于 TTM）
            "pb": 3.2,               # 动态市净率
            "pe_ttm": 23.1,          # 动态市盈率（TTM）
            "price": 11.0,           # 当前价格
            "market_cap": 110.5,     # 实时市值（亿元）
            "ttm_net_profit": 4.8,   # TTM 净利润（亿元，从 Tushare 反推）
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

        # 2. 获取基础信息（stock_basic_info）- 获取 Tushare 的 pe_ttm 和市值数据
        basic_info = db.stock_basic_info.find_one({"code": code6})
        if not basic_info:
            logger.warning(f"⚠️ [动态PE计算-失败] 未找到股票 {code6} 的基础信息")
            return None

        # 获取 Tushare 的 pe_ttm（基于昨日收盘价）
        pe_ttm_tushare = basic_info.get("pe_ttm")
        pe_tushare = basic_info.get("pe")
        pb_tushare = basic_info.get("pb")
        total_mv_yi = basic_info.get("total_mv")  # 总市值（亿元）

        logger.info(f"   ✓ Tushare PE_TTM: {pe_ttm_tushare}倍 (基于昨日收盘价)")
        logger.info(f"   ✓ Tushare PE: {pe_tushare}倍")
        logger.info(f"   ✓ Tushare 总市值: {total_mv_yi}亿元")

        # 3. 从 Tushare pe_ttm 反推 TTM 净利润
        if not pe_ttm_tushare or pe_ttm_tushare <= 0 or not total_mv_yi or total_mv_yi <= 0:
            logger.warning(f"⚠️ [动态PE计算-失败] 无法反推TTM净利润: pe_ttm={pe_ttm_tushare}, total_mv={total_mv_yi}")
            logger.warning(f"   💡 提示: 可能是亏损股票（PE为负或空）")
            return None

        # 反推 TTM 净利润（亿元）= 总市值 / PE_TTM
        ttm_net_profit_yi = total_mv_yi / pe_ttm_tushare
        logger.info(f"   ✓ 反推 TTM净利润: {total_mv_yi:.2f}亿元 / {pe_ttm_tushare:.2f}倍 = {ttm_net_profit_yi:.2f}亿元")

        # 4. 计算总股本（万股）= 总市值（亿元）* 10000 / 昨日收盘价（元）
        # 注意：这里使用 Tushare 的总市值，它是基于昨日收盘价的
        # 我们需要用实时股价重新计算总股本
        total_shares_wan = (total_mv_yi * 10000) / realtime_price
        logger.info(f"   ✓ 总股本: {total_shares_wan:.2f}万股 (由总市值/实时股价计算)")

        # 5. 计算实时市值（亿元）
        realtime_mv_yi = (realtime_price * total_shares_wan) / 10000
        logger.info(f"   ✓ 实时市值: {realtime_mv_yi:.2f}亿元")

        # 6. 计算动态 PE_TTM = 实时市值 / TTM净利润
        dynamic_pe_ttm = realtime_mv_yi / ttm_net_profit_yi
        logger.info(f"   ✓ 动态PE_TTM计算: {realtime_mv_yi:.2f}亿元 / {ttm_net_profit_yi:.2f}亿元 = {dynamic_pe_ttm:.2f}倍")

        # 7. 获取财务数据（用于计算 PB）
        financial_data = db.stock_financial_data.find_one({"code": code6}, sort=[("report_period", -1)])
        pb = None
        total_equity_yi = None

        if financial_data:
            total_equity = financial_data.get("total_equity")  # 净资产（元）
            if total_equity and total_equity > 0:
                total_equity_yi = total_equity / 100000000  # 转换为亿元
                pb = realtime_mv_yi / total_equity_yi
                logger.info(f"   ✓ 动态PB计算: {realtime_mv_yi:.2f}亿元 / {total_equity_yi:.2f}亿元 = {pb:.2f}倍")
            else:
                logger.warning(f"   ⚠️ PB计算失败: 净资产无效 ({total_equity})")
        else:
            logger.warning(f"   ⚠️ 未找到财务数据，无法计算PB")
            # 使用 Tushare 的 PB 作为降级
            if pb_tushare:
                pb = pb_tushare
                logger.info(f"   ✓ 使用 Tushare PB: {pb}倍")

        # 8. 构建返回结果
        result = {
            "pe": round(dynamic_pe_ttm, 2),  # 动态PE（基于TTM）
            "pb": round(pb, 2) if pb else None,
            "pe_ttm": round(dynamic_pe_ttm, 2),  # 动态PE_TTM
            "price": round(realtime_price, 2),
            "market_cap": round(realtime_mv_yi, 2),  # 实时市值（亿元）
            "ttm_net_profit": round(ttm_net_profit_yi, 2),  # TTM净利润（亿元）
            "updated_at": quote.get("updated_at"),
            "source": "realtime_calculated_from_tushare_ttm",
            "is_realtime": True,
            "note": "基于实时股价和Tushare TTM数据计算",
            "total_shares": round(total_shares_wan, 2),  # 总股本（万股）
            "tushare_pe_ttm": round(pe_ttm_tushare, 2),  # Tushare PE_TTM（参考）
            "tushare_pe": round(pe_tushare, 2) if pe_tushare else None,  # Tushare PE（参考）
        }

        logger.info(f"✅ [动态PE计算-成功] 股票 {code6}: 动态PE_TTM={result['pe_ttm']}倍, PB={result['pb']}倍")
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
    获取PE/PB，智能降级策略

    策略：
    1. 优先使用动态 PE（基于实时股价 + Tushare TTM 净利润）
    2. 如果动态计算失败，降级到 Tushare 静态 PE（基于昨日收盘价）

    优势：
    - 动态 PE 能反映实时股价变化
    - 使用 Tushare 官方 TTM 净利润（反推），避免单季度数据错误
    - 计算准确，日志详细

    Args:
        symbol: 6位股票代码
        db_client: MongoDB客户端（可选）

    Returns:
        {
            "pe": 22.5,              # 市盈率
            "pb": 3.2,               # 市净率
            "pe_ttm": 23.1,          # 市盈率（TTM）
            "pb_mrq": 3.3,           # 市净率（MRQ）
            "source": "realtime_calculated_from_tushare_ttm" | "daily_basic",
            "is_realtime": True | False,
            "updated_at": "2025-10-14T10:30:00",
            "ttm_net_profit": 4.8    # TTM净利润（亿元，仅动态计算时有）
        }
    """
    logger.info(f"🔄 [PE智能策略] 开始获取股票 {symbol} 的PE/PB")

    # 准备数据库连接
    try:
        if db_client is None:
            from tradingagents.config.database_manager import get_database_manager
            db_manager = get_database_manager()
            if not db_manager.is_mongodb_available():
                logger.error("❌ [PE智能策略-失败] MongoDB不可用")
                return {}
            db_client = db_manager.get_mongodb_client()

        # 检查是否是异步客户端
        client_type = type(db_client).__name__
        if 'AsyncIOMotorClient' in client_type or 'Motor' in client_type:
            from pymongo import MongoClient
            from app.core.config import settings
            logger.debug(f"检测到异步客户端 {client_type}，转换为同步客户端")
            db_client = MongoClient(settings.MONGO_URI)

    except Exception as e:
        logger.error(f"❌ [PE智能策略-失败] 数据库连接失败: {e}")
        return {}

    # 1. 优先使用动态 PE 计算（基于实时股价 + Tushare TTM）
    logger.info("   → 尝试方案1: 动态PE计算 (实时股价 + Tushare TTM净利润)")
    logger.info("   💡 说明: 使用实时股价和Tushare官方TTM净利润，准确反映当前估值")

    realtime_metrics = calculate_realtime_pe_pb(symbol, db_client)
    if realtime_metrics:
        # 验证数据合理性
        pe = realtime_metrics.get('pe')
        pb = realtime_metrics.get('pb')
        if validate_pe_pb(pe, pb):
            logger.info(f"✅ [PE智能策略-成功] 使用动态PE: PE={pe}, PB={pb}")
            logger.info(f"   └─ 数据来源: {realtime_metrics.get('source')}")
            logger.info(f"   └─ TTM净利润: {realtime_metrics.get('ttm_net_profit')}亿元 (从Tushare反推)")
            return realtime_metrics
        else:
            logger.warning(f"⚠️ [PE智能策略-方案1异常] 动态PE/PB超出合理范围 (PE={pe}, PB={pb})")

    # 2. 降级到 Tushare 静态 PE（基于昨日收盘价）
    logger.info("   → 尝试方案2: Tushare静态PE (基于昨日收盘价)")
    logger.info("   💡 说明: 使用Tushare官方PE_TTM，基于昨日收盘价")

    try:
        db = db_client['tradingagents']
        code6 = str(symbol).zfill(6)

        basic_info = db.stock_basic_info.find_one({"code": code6})
        if basic_info:
            pe_static = basic_info.get("pe")
            pb_static = basic_info.get("pb")
            pe_ttm = basic_info.get("pe_ttm")
            pb_mrq = basic_info.get("pb_mrq")
            updated_at = basic_info.get("updated_at", "N/A")

            if pe_ttm or pe_static or pb_static:
                logger.info(f"✅ [PE智能策略-成功] 使用Tushare静态PE: PE={pe_static}, PE_TTM={pe_ttm}, PB={pb_static}")
                logger.info(f"   └─ 数据来源: stock_basic_info (更新时间: {updated_at})")

                return {
                    "pe": pe_static,
                    "pb": pb_static,
                    "pe_ttm": pe_ttm,
                    "pb_mrq": pb_mrq,
                    "source": "daily_basic",
                    "is_realtime": False,
                    "updated_at": updated_at,
                    "note": "使用Tushare最近一个交易日的数据（基于TTM）"
                }

        logger.warning("⚠️ [PE智能策略-方案2失败] Tushare静态数据不可用")

    except Exception as e:
        logger.warning(f"⚠️ [PE智能策略-方案2异常] {e}")

    logger.error(f"❌ [PE智能策略-全部失败] 无法获取股票 {symbol} 的PE/PB")
    return {}

