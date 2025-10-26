#!/usr/bin/env python3
"""
同步股票财务数据

功能：
1. 从 AKShare 获取股票财务指标
2. 更新 stock_basic_info 集合的财务字段
3. 创建/更新 stock_financial_data 集合

使用方法：
    python scripts/sync_financial_data.py 600036  # 同步单只股票
    python scripts/sync_financial_data.py --all   # 同步所有股票
    python scripts/sync_financial_data.py --batch 100  # 批量同步前100只
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
from tradingagents.dataflows.providers.china.akshare import AKShareProvider
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


async def sync_single_stock_financial_data(
    code: str,
    provider: AKShareProvider,
    db
) -> bool:
    """
    同步单只股票的财务数据
    
    Returns:
        bool: 是否成功
    """
    code6 = str(code).zfill(6)
    
    try:
        logger.info(f"🔄 同步 {code6} 的财务数据...")
        
        # 1. 获取财务指标数据
        import akshare as ak

        def fetch_financial_indicator():
            return ak.stock_financial_analysis_indicator(symbol=code6)

        try:
            df = await asyncio.to_thread(fetch_financial_indicator)

            if df is None or df.empty:
                logger.warning(f"⚠️  {code6} 未获取到财务指标数据")
                return False

            # 获取最新一期数据
            latest = df.iloc[-1].to_dict()

            logger.info(f"   获取到 {len(df)} 期财务数据，最新期: {latest.get('报告期', 'N/A')}")

            # 计算 TTM（最近12个月）营业收入
            ttm_revenue = _calculate_ttm_revenue(df)
            if ttm_revenue:
                logger.info(f"   TTM营业收入: {ttm_revenue:.2f} 万元")

        except Exception as e:
            logger.error(f"❌ {code6} 获取财务指标失败: {e}")
            return False
        
        # 2. 解析财务数据
        financial_data = {
            "code": code6,
            "symbol": code6,
            "report_period": latest.get('报告期', ''),
            "data_source": "akshare",
            "updated_at": datetime.utcnow(),

            # 盈利能力指标
            "roe": _safe_float(latest.get('净资产收益率')),  # ROE
            "roa": _safe_float(latest.get('总资产净利率')),  # ROA
            "gross_margin": _safe_float(latest.get('销售毛利率')),  # 毛利率
            "netprofit_margin": _safe_float(latest.get('销售净利率')),  # 净利率

            # 财务数据（万元）
            "revenue": _safe_float(latest.get('营业收入')),  # 营业收入（单期）
            "revenue_ttm": ttm_revenue,  # TTM营业收入（最近12个月）
            "net_profit": _safe_float(latest.get('净利润')),  # 净利润
            "total_assets": _safe_float(latest.get('总资产')),  # 总资产
            "total_hldr_eqy_exc_min_int": _safe_float(latest.get('股东权益合计')),  # 净资产

            # 每股指标
            "basic_eps": _safe_float(latest.get('基本每股收益')),  # 每股收益
            "bps": _safe_float(latest.get('每股净资产')),  # 每股净资产

            # 偿债能力指标
            "debt_to_assets": _safe_float(latest.get('资产负债率')),  # 资产负债率
            "current_ratio": _safe_float(latest.get('流动比率')),  # 流动比率

            # 运营能力指标
            "total_asset_turnover": _safe_float(latest.get('总资产周转率')),  # 总资产周转率
        }
        
        # 3. 获取股本数据
        try:
            def fetch_stock_info():
                return ak.stock_individual_info_em(symbol=code6)
            
            stock_info_df = await asyncio.to_thread(fetch_stock_info)
            
            if stock_info_df is not None and not stock_info_df.empty:
                # 提取总股本
                total_share_row = stock_info_df[stock_info_df['item'] == '总股本']
                if not total_share_row.empty:
                    total_share_str = str(total_share_row['value'].iloc[0])
                    # 解析总股本（可能是 "193.78亿" 这种格式）
                    total_share = _parse_share_value(total_share_str)
                    financial_data['total_share'] = total_share
                    logger.info(f"   总股本: {total_share} 万股")
                
                # 提取流通股本
                float_share_row = stock_info_df[stock_info_df['item'] == '流通股']
                if not float_share_row.empty:
                    float_share_str = str(float_share_row['value'].iloc[0])
                    float_share = _parse_share_value(float_share_str)
                    financial_data['float_share'] = float_share
        
        except Exception as e:
            logger.warning(f"⚠️  {code6} 获取股本数据失败: {e}")
        
        # 4. 计算市值和估值指标（如果有实时价格）
        quote = await db.market_quotes.find_one(
            {"$or": [{"code": code6}, {"symbol": code6}]}
        )
        
        if quote and financial_data.get('total_share'):
            price = quote.get('close')
            if price:
                # 计算市值（万元）
                market_cap = price * financial_data['total_share']
                financial_data['money_cap'] = market_cap
                
                # 计算 PE
                if financial_data.get('net_profit') and financial_data['net_profit'] > 0:
                    pe = market_cap / financial_data['net_profit']
                    financial_data['pe'] = round(pe, 2)
                    logger.info(f"   PE: {pe:.2f}")
                
                # 计算 PB
                if financial_data.get('total_hldr_eqy_exc_min_int') and financial_data['total_hldr_eqy_exc_min_int'] > 0:
                    pb = market_cap / financial_data['total_hldr_eqy_exc_min_int']
                    financial_data['pb'] = round(pb, 2)
                    logger.info(f"   PB: {pb:.2f}")
        
        # 5. 更新 stock_basic_info 集合
        await db.stock_basic_info.update_one(
            {"code": code6},
            {"$set": {
                "total_share": financial_data.get('total_share'),
                "float_share": financial_data.get('float_share'),
                "net_profit": financial_data.get('net_profit'),
                "total_hldr_eqy_exc_min_int": financial_data.get('total_hldr_eqy_exc_min_int'),
                "money_cap": financial_data.get('money_cap'),
                "pe": financial_data.get('pe'),
                "pb": financial_data.get('pb'),
                "roe": financial_data.get('roe'),
                "updated_at": datetime.utcnow()
            }},
            upsert=False  # 不创建新文档，只更新已存在的
        )
        
        # 6. 更新 stock_financial_data 集合
        await db.stock_financial_data.update_one(
            {"code": code6, "report_period": financial_data['report_period']},
            {"$set": financial_data},
            upsert=True
        )
        
        logger.info(f"✅ {code6} 财务数据同步成功")
        return True
        
    except Exception as e:
        logger.error(f"❌ {code6} 财务数据同步失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def _safe_float(value) -> Optional[float]:
    """安全转换为浮点数"""
    if value is None or value == '' or str(value) == 'nan' or value == '--':
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _calculate_ttm_revenue(df) -> Optional[float]:
    """
    计算 TTM（最近12个月）营业收入

    策略：
    1. 如果最新期是年报（12月31日），直接使用年报营业收入
    2. 如果最新期是中报/季报，计算 TTM = 最新年报 + (本期 - 去年同期)
    3. 如果数据不足，返回 None

    Args:
        df: AKShare 返回的财务指标 DataFrame，包含 '报告期' 和 '营业收入' 列

    Returns:
        TTM 营业收入（万元），如果无法计算则返回 None
    """
    try:
        if df is None or df.empty or len(df) < 1:
            return None

        # 确保有必要的列
        if '报告期' not in df.columns or '营业收入' not in df.columns:
            return None

        # 按报告期排序（升序）
        df_sorted = df.sort_values('报告期', ascending=True).reset_index(drop=True)

        # 获取最新一期
        latest = df_sorted.iloc[-1]
        latest_period = str(latest['报告期'])
        latest_revenue = _safe_float(latest['营业收入'])

        if latest_revenue is None:
            return None

        # 判断最新期是否是年报（报告期以1231结尾）
        if latest_period.endswith('1231'):
            # 年报，直接使用
            logger.debug(f"   使用年报数据作为TTM: {latest_revenue:.2f} 万元")
            return latest_revenue

        # 非年报，需要计算 TTM
        # 提取年份和月份
        try:
            year = int(latest_period[:4])
            month_day = latest_period[4:]
        except:
            return None

        # 查找最近的年报（上一年的1231）
        last_year = year - 1
        last_annual_period = f"{last_year}1231"

        # 查找去年同期
        last_same_period = f"{last_year}{month_day}"

        # 在 DataFrame 中查找
        last_annual_row = df_sorted[df_sorted['报告期'] == last_annual_period]
        last_same_row = df_sorted[df_sorted['报告期'] == last_same_period]

        if not last_annual_row.empty and not last_same_row.empty:
            last_annual_revenue = _safe_float(last_annual_row.iloc[0]['营业收入'])
            last_same_revenue = _safe_float(last_same_row.iloc[0]['营业收入'])

            if last_annual_revenue is not None and last_same_revenue is not None:
                # TTM = 最近年报 + (本期 - 去年同期)
                ttm_revenue = last_annual_revenue + (latest_revenue - last_same_revenue)
                logger.debug(f"   计算TTM: {last_annual_revenue:.2f} + ({latest_revenue:.2f} - {last_same_revenue:.2f}) = {ttm_revenue:.2f} 万元")
                return ttm_revenue if ttm_revenue > 0 else None

        # 如果无法计算 TTM，尝试简单年化（不推荐，但总比没有好）
        if latest_period.endswith('0630'):
            # 中报，简单 * 2
            ttm_revenue = latest_revenue * 2
            logger.debug(f"   使用中报简单年化: {latest_revenue:.2f} * 2 = {ttm_revenue:.2f} 万元")
            return ttm_revenue
        elif latest_period.endswith('0331'):
            # 一季报，简单 * 4
            ttm_revenue = latest_revenue * 4
            logger.debug(f"   使用一季报简单年化: {latest_revenue:.2f} * 4 = {ttm_revenue:.2f} 万元")
            return ttm_revenue
        elif latest_period.endswith('0930'):
            # 三季报，简单 * 4/3
            ttm_revenue = latest_revenue * 4 / 3
            logger.debug(f"   使用三季报简单年化: {latest_revenue:.2f} * 4/3 = {ttm_revenue:.2f} 万元")
            return ttm_revenue

        # 无法计算
        return None

    except Exception as e:
        logger.warning(f"   计算TTM营业收入失败: {e}")
        return None


def _parse_share_value(value_str: str) -> Optional[float]:
    """解析股本数值（支持 "193.78亿" 这种格式）"""
    try:
        value_str = str(value_str).strip()
        
        # 移除单位并转换
        if '亿' in value_str:
            num = float(value_str.replace('亿', ''))
            return num * 10000  # 亿 -> 万
        elif '万' in value_str:
            return float(value_str.replace('万', ''))
        else:
            # 假设是股数，转换为万股
            return float(value_str) / 10000
    except:
        return None


async def main(code: Optional[str] = None, sync_all: bool = False, batch: Optional[int] = None):
    """主函数"""
    logger.info("=" * 80)
    logger.info("🚀 同步股票财务数据")
    logger.info("=" * 80)
    
    # 连接数据库
    client = AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.MONGO_DB]
    
    # 初始化 Provider
    provider = AKShareProvider()
    await provider.connect()
    
    try:
        if code:
            # 同步单只股票
            await sync_single_stock_financial_data(code, provider, db)
        
        elif sync_all or batch:
            # 批量同步
            cursor = db.stock_basic_info.find({}, {"code": 1, "name": 1})
            stocks = await cursor.to_list(length=batch if batch else None)
            
            total = len(stocks)
            logger.info(f"📊 准备同步 {total} 只股票的财务数据")
            
            success_count = 0
            failed_count = 0
            
            for i, stock in enumerate(stocks, 1):
                stock_code = stock.get('code')
                stock_name = stock.get('name', 'N/A')
                
                logger.info(f"\n[{i}/{total}] {stock_code} ({stock_name})")
                
                success = await sync_single_stock_financial_data(stock_code, provider, db)
                
                if success:
                    success_count += 1
                else:
                    failed_count += 1
                
                # 延迟，避免API限流
                if i < total:
                    await asyncio.sleep(0.5)
            
            logger.info(f"\n" + "=" * 80)
            logger.info(f"📊 同步完成统计")
            logger.info(f"=" * 80)
            logger.info(f"   总计: {total} 只")
            logger.info(f"   成功: {success_count} 只")
            logger.info(f"   失败: {failed_count} 只")
            logger.info(f"=" * 80)
        
        else:
            logger.error("❌ 请指定股票代码、--all 或 --batch 参数")
    
    finally:
        client.close()
    
    logger.info("")
    logger.info("✅ 同步完成！")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="同步股票财务数据",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "code",
        nargs="?",
        type=str,
        help="股票代码（6位）"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="同步所有股票"
    )
    parser.add_argument(
        "--batch",
        type=int,
        help="批量同步前N只股票"
    )
    
    args = parser.parse_args()
    
    asyncio.run(main(
        code=args.code,
        sync_all=args.all,
        batch=args.batch
    ))

