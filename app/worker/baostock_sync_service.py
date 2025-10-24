#!/usr/bin/env python3
"""
BaoStock数据同步服务
提供BaoStock数据的批量同步功能，集成到APScheduler调度系统
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from app.core.config import get_settings
from app.core.database import get_database
from app.services.historical_data_service import get_historical_data_service
from tradingagents.dataflows.providers.china.baostock import BaoStockProvider

logger = logging.getLogger(__name__)


@dataclass
class BaoStockSyncStats:
    """BaoStock同步统计"""
    basic_info_count: int = 0
    quotes_count: int = 0
    historical_records: int = 0
    financial_records: int = 0
    errors: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class BaoStockSyncService:
    """BaoStock数据同步服务"""
    
    def __init__(self, require_db: bool = True):
        """
        初始化同步服务

        Args:
            require_db: 是否需要数据库连接
        """
        try:
            self.settings = get_settings()
            self.provider = BaoStockProvider()
            self.historical_service = None  # 延迟初始化

            if require_db:
                self.db = get_database()
            else:
                self.db = None

            logger.info("✅ BaoStock同步服务初始化成功")
        except Exception as e:
            logger.error(f"❌ BaoStock同步服务初始化失败: {e}")
            raise

    async def initialize(self):
        """异步初始化服务"""
        try:
            # 初始化历史数据服务
            if self.historical_service is None:
                from app.services.historical_data_service import get_historical_data_service
                self.historical_service = await get_historical_data_service()

            logger.info("✅ BaoStock同步服务异步初始化完成")
        except Exception as e:
            logger.error(f"❌ BaoStock同步服务异步初始化失败: {e}")
            raise
    
    async def sync_stock_basic_info(self, batch_size: int = 100) -> BaoStockSyncStats:
        """
        同步股票基础信息
        
        Args:
            batch_size: 批处理大小
            
        Returns:
            同步统计信息
        """
        stats = BaoStockSyncStats()
        
        try:
            logger.info("🔄 开始BaoStock股票基础信息同步...")
            
            # 获取股票列表
            stock_list = await self.provider.get_stock_list()
            if not stock_list:
                logger.warning("⚠️ BaoStock股票列表为空")
                return stats
            
            logger.info(f"📋 获取到{len(stock_list)}只股票，开始批量同步...")
            
            # 批量处理
            for i in range(0, len(stock_list), batch_size):
                batch = stock_list[i:i + batch_size]
                batch_stats = await self._sync_basic_info_batch(batch)
                
                stats.basic_info_count += batch_stats.basic_info_count
                stats.errors.extend(batch_stats.errors)
                
                logger.info(f"📊 批次进度: {i + len(batch)}/{len(stock_list)}, "
                          f"成功: {batch_stats.basic_info_count}, "
                          f"错误: {len(batch_stats.errors)}")
                
                # 避免API限制
                await asyncio.sleep(0.1)
            
            logger.info(f"✅ BaoStock基础信息同步完成: {stats.basic_info_count}条记录")
            return stats
            
        except Exception as e:
            logger.error(f"❌ BaoStock基础信息同步失败: {e}")
            stats.errors.append(str(e))
            return stats
    
    async def _sync_basic_info_batch(self, stock_batch: List[Dict[str, Any]]) -> BaoStockSyncStats:
        """同步基础信息批次"""
        stats = BaoStockSyncStats()
        
        for stock in stock_batch:
            try:
                code = stock['code']
                basic_info = await self.provider.get_stock_basic_info(code)
                
                if basic_info:
                    # 更新数据库
                    await self._update_stock_basic_info(basic_info)
                    stats.basic_info_count += 1
                else:
                    stats.errors.append(f"获取{code}基础信息失败")
                    
            except Exception as e:
                stats.errors.append(f"处理{stock.get('code', 'unknown')}失败: {e}")
        
        return stats
    
    async def _update_stock_basic_info(self, basic_info: Dict[str, Any]):
        """更新股票基础信息到数据库"""
        try:
            collection = self.db.stock_basic_info
            
            # 使用upsert更新或插入
            await collection.update_one(
                {"code": basic_info["code"]},
                {"$set": basic_info},
                upsert=True
            )
            
        except Exception as e:
            logger.error(f"❌ 更新基础信息到数据库失败: {e}")
            raise
    
    async def sync_daily_quotes(self, batch_size: int = 50) -> BaoStockSyncStats:
        """
        同步日K线数据（最新交易日）

        注意：BaoStock不支持实时行情，此方法获取最新交易日的日K线数据

        Args:
            batch_size: 批处理大小

        Returns:
            同步统计信息
        """
        stats = BaoStockSyncStats()

        try:
            logger.info("🔄 开始BaoStock日K线同步（最新交易日）...")
            logger.info("ℹ️ 注意：BaoStock不支持实时行情，此任务同步最新交易日的日K线数据")

            # 从数据库获取股票列表
            collection = self.db.stock_basic_info
            cursor = collection.find({"data_source": "baostock"}, {"code": 1})
            stock_codes = [doc["code"] async for doc in cursor]

            if not stock_codes:
                logger.warning("⚠️ 数据库中没有BaoStock股票数据")
                return stats

            logger.info(f"📈 开始同步{len(stock_codes)}只股票的日K线数据...")

            # 批量处理
            for i in range(0, len(stock_codes), batch_size):
                batch = stock_codes[i:i + batch_size]
                batch_stats = await self._sync_quotes_batch(batch)

                stats.quotes_count += batch_stats.quotes_count
                stats.errors.extend(batch_stats.errors)

                logger.info(f"📊 批次进度: {i + len(batch)}/{len(stock_codes)}, "
                          f"成功: {batch_stats.quotes_count}, "
                          f"错误: {len(batch_stats.errors)}")

                # 避免API限制
                await asyncio.sleep(0.2)

            logger.info(f"✅ BaoStock日K线同步完成: {stats.quotes_count}条记录")
            return stats

        except Exception as e:
            logger.error(f"❌ BaoStock日K线同步失败: {e}")
            stats.errors.append(str(e))
            return stats
    
    async def _sync_quotes_batch(self, code_batch: List[str]) -> BaoStockSyncStats:
        """同步日K线批次"""
        stats = BaoStockSyncStats()

        for code in code_batch:
            try:
                # 注意：get_stock_quotes 实际返回的是最新日K线数据，不是实时行情
                quotes = await self.provider.get_stock_quotes(code)

                if quotes:
                    # 更新数据库
                    await self._update_stock_quotes(quotes)
                    stats.quotes_count += 1
                else:
                    stats.errors.append(f"获取{code}日K线失败")

            except Exception as e:
                stats.errors.append(f"处理{code}日K线失败: {e}")

        return stats

    async def _update_stock_quotes(self, quotes: Dict[str, Any]):
        """更新股票日K线到数据库"""
        try:
            collection = self.db.market_quotes

            # 确保 symbol 字段存在
            code = quotes.get("code", "")
            if code and "symbol" not in quotes:
                quotes["symbol"] = code

            # 使用upsert更新或插入
            await collection.update_one(
                {"code": code},
                {"$set": quotes},
                upsert=True
            )

        except Exception as e:
            logger.error(f"❌ 更新日K线到数据库失败: {e}")
            raise
    
    async def sync_historical_data(self, days: int = 30, batch_size: int = 20, period: str = "daily", incremental: bool = True) -> BaoStockSyncStats:
        """
        同步历史数据

        Args:
            days: 同步天数（如果>=3650则同步全历史，如果<0则使用增量模式）
            batch_size: 批处理大小
            period: 数据周期 (daily/weekly/monthly)
            incremental: 是否增量同步（每只股票从自己的最后日期开始）

        Returns:
            同步统计信息
        """
        stats = BaoStockSyncStats()

        try:
            period_name = {"daily": "日线", "weekly": "周线", "monthly": "月线"}.get(period, "日线")

            # 计算日期范围
            end_date = datetime.now().strftime('%Y-%m-%d')

            # 确定同步模式
            use_incremental = incremental or days < 0

            # 从数据库获取股票列表
            collection = self.db.stock_basic_info
            cursor = collection.find({"data_source": "baostock"}, {"code": 1})
            stock_codes = [doc["code"] async for doc in cursor]

            if not stock_codes:
                logger.warning("⚠️ 数据库中没有BaoStock股票数据")
                return stats

            if use_incremental:
                logger.info(f"🔄 开始BaoStock{period_name}历史数据同步 (增量模式: 各股票从最后日期到{end_date})...")
            elif days >= 3650:
                logger.info(f"🔄 开始BaoStock{period_name}历史数据同步 (全历史: 1990-01-01到{end_date})...")
            else:
                logger.info(f"🔄 开始BaoStock{period_name}历史数据同步 (最近{days}天到{end_date})...")

            logger.info(f"📊 开始同步{len(stock_codes)}只股票的历史数据...")

            # 批量处理
            for i in range(0, len(stock_codes), batch_size):
                batch = stock_codes[i:i + batch_size]
                batch_stats = await self._sync_historical_batch(batch, days, end_date, period, use_incremental)
                
                stats.historical_records += batch_stats.historical_records
                stats.errors.extend(batch_stats.errors)
                
                logger.info(f"📊 批次进度: {i + len(batch)}/{len(stock_codes)}, "
                          f"记录: {batch_stats.historical_records}, "
                          f"错误: {len(batch_stats.errors)}")
                
                # 避免API限制
                await asyncio.sleep(0.5)
            
            logger.info(f"✅ BaoStock历史数据同步完成: {stats.historical_records}条记录")
            return stats
            
        except Exception as e:
            logger.error(f"❌ BaoStock历史数据同步失败: {e}")
            stats.errors.append(str(e))
            return stats
    
    async def _sync_historical_batch(
        self,
        code_batch: List[str],
        days: int,
        end_date: str,
        period: str = "daily",
        incremental: bool = False
    ) -> BaoStockSyncStats:
        """同步历史数据批次"""
        stats = BaoStockSyncStats()

        for code in code_batch:
            try:
                # 确定该股票的起始日期
                if incremental:
                    # 增量同步：获取该股票的最后日期
                    start_date = await self._get_last_sync_date(code)
                    logger.debug(f"📅 {code}: 从 {start_date} 开始同步")
                elif days >= 3650:
                    # 全历史同步
                    start_date = "1990-01-01"
                else:
                    # 固定天数同步
                    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

                hist_data = await self.provider.get_historical_data(code, start_date, end_date, period)

                if hist_data is not None and not hist_data.empty:
                    # 更新数据库
                    records_count = await self._update_historical_data(code, hist_data, period)
                    stats.historical_records += records_count
                else:
                    stats.errors.append(f"获取{code}历史数据失败")

            except Exception as e:
                stats.errors.append(f"处理{code}历史数据失败: {e}")

        return stats

    async def _update_historical_data(self, code: str, hist_data, period: str = "daily") -> int:
        """更新历史数据到数据库"""
        try:
            if hist_data is None or hist_data.empty:
                logger.warning(f"⚠️ {code} 历史数据为空，跳过保存")
                return 0

            # 初始化历史数据服务
            if self.historical_service is None:
                self.historical_service = await get_historical_data_service()

            # 保存到统一历史数据集合
            saved_count = await self.historical_service.save_historical_data(
                symbol=code,
                data=hist_data,
                data_source="baostock",
                market="CN",
                period=period
            )

            # 同时更新market_quotes集合的元信息（保持兼容性）
            if self.db is not None:
                collection = self.db.market_quotes
                latest_record = hist_data.iloc[-1] if not hist_data.empty else None

                await collection.update_one(
                    {"code": code},
                    {"$set": {
                        "historical_data_updated": datetime.now(),
                        "latest_historical_date": latest_record.get('date') if latest_record is not None else None,
                        "historical_records_count": saved_count
                    }},
                    upsert=True
                )

            return saved_count

        except Exception as e:
            logger.error(f"❌ 更新历史数据到数据库失败: {e}")
            return 0
    
    async def _get_last_sync_date(self, symbol: str = None) -> str:
        """
        获取最后同步日期

        Args:
            symbol: 股票代码，如果提供则返回该股票的最后日期+1天

        Returns:
            日期字符串 (YYYY-MM-DD)
        """
        try:
            if self.historical_service is None:
                self.historical_service = await get_historical_data_service()

            if symbol:
                # 获取特定股票的最新日期
                latest_date = await self.historical_service.get_latest_date(symbol, "baostock")
                if latest_date:
                    # 返回最后日期的下一天（避免重复同步）
                    try:
                        last_date_obj = datetime.strptime(latest_date, '%Y-%m-%d')
                        next_date = last_date_obj + timedelta(days=1)
                        return next_date.strftime('%Y-%m-%d')
                    except ValueError:
                        # 如果日期格式不对，直接返回
                        return latest_date

            # 默认返回30天前（确保不漏数据）
            return (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

        except Exception as e:
            logger.error(f"❌ 获取最后同步日期失败 {symbol}: {e}")
            # 出错时返回30天前，确保不漏数据
            return (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

    async def check_service_status(self) -> Dict[str, Any]:
        """检查服务状态"""
        try:
            # 测试BaoStock连接
            connection_ok = await self.provider.test_connection()
            
            # 检查数据库连接
            db_ok = True
            try:
                await self.db.stock_basic_info.count_documents({})
            except Exception:
                db_ok = False
            
            # 统计数据
            basic_info_count = await self.db.stock_basic_info.count_documents({"data_source": "baostock"})
            quotes_count = await self.db.market_quotes.count_documents({"data_source": "baostock"})
            
            return {
                "service": "BaoStock同步服务",
                "baostock_connection": connection_ok,
                "database_connection": db_ok,
                "basic_info_count": basic_info_count,
                "quotes_count": quotes_count,
                "status": "healthy" if connection_ok and db_ok else "unhealthy",
                "last_check": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ BaoStock服务状态检查失败: {e}")
            return {
                "service": "BaoStock同步服务",
                "status": "error",
                "error": str(e),
                "last_check": datetime.now().isoformat()
            }


# APScheduler兼容的任务函数
async def run_baostock_basic_info_sync():
    """运行BaoStock基础信息同步任务"""
    try:
        service = BaoStockSyncService()
        stats = await service.sync_stock_basic_info()
        logger.info(f"🎯 BaoStock基础信息同步完成: {stats.basic_info_count}条记录, {len(stats.errors)}个错误")
    except Exception as e:
        logger.error(f"❌ BaoStock基础信息同步任务失败: {e}")


async def run_baostock_daily_quotes_sync():
    """运行BaoStock日K线同步任务（最新交易日）"""
    try:
        service = BaoStockSyncService()
        stats = await service.sync_daily_quotes()
        logger.info(f"🎯 BaoStock日K线同步完成: {stats.quotes_count}条记录, {len(stats.errors)}个错误")
    except Exception as e:
        logger.error(f"❌ BaoStock日K线同步任务失败: {e}")


async def run_baostock_historical_sync():
    """运行BaoStock历史数据同步任务"""
    try:
        service = BaoStockSyncService()
        stats = await service.sync_historical_data()
        logger.info(f"🎯 BaoStock历史数据同步完成: {stats.historical_records}条记录, {len(stats.errors)}个错误")
    except Exception as e:
        logger.error(f"❌ BaoStock历史数据同步任务失败: {e}")


async def run_baostock_status_check():
    """运行BaoStock状态检查任务"""
    try:
        service = BaoStockSyncService()
        status = await service.check_service_status()
        logger.info(f"🔍 BaoStock服务状态: {status['status']}")
    except Exception as e:
        logger.error(f"❌ BaoStock状态检查任务失败: {e}")
