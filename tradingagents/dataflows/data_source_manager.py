#!/usr/bin/env python3
"""
数据源管理器
统一管理中国股票数据源的选择和切换，支持Tushare、AKShare、BaoStock等
"""

import os
import time
from typing import Dict, List, Optional, Any
from enum import Enum
import warnings
import pandas as pd

# 导入日志模块
from tradingagents.utils.logging_manager import get_logger
logger = get_logger('agents')
warnings.filterwarnings('ignore')

# 导入统一日志系统
from tradingagents.utils.logging_init import setup_dataflow_logging
logger = setup_dataflow_logging()


class ChinaDataSource(Enum):
    """中国股票数据源枚举"""
    MONGODB = "mongodb"  # MongoDB数据库缓存（最高优先级）
    TUSHARE = "tushare"
    AKSHARE = "akshare"
    BAOSTOCK = "baostock"
    TDX = "tdx"  # 中国股票数据，将被逐步淘汰





class DataSourceManager:
    """数据源管理器"""

    def __init__(self):
        """初始化数据源管理器"""
        # 检查是否启用MongoDB缓存
        self.use_mongodb_cache = self._check_mongodb_enabled()

        self.default_source = self._get_default_source()
        self.available_sources = self._check_available_sources()
        self.current_source = self.default_source

        logger.info(f"📊 数据源管理器初始化完成")
        logger.info(f"   MongoDB缓存: {'✅ 已启用' if self.use_mongodb_cache else '❌ 未启用'}")
        logger.info(f"   默认数据源: {self.default_source.value}")
        logger.info(f"   可用数据源: {[s.value for s in self.available_sources]}")

    def _check_mongodb_enabled(self) -> bool:
        """检查是否启用MongoDB缓存"""
        from tradingagents.config.runtime_settings import use_app_cache_enabled
        return use_app_cache_enabled()

    def _get_default_source(self) -> ChinaDataSource:
        """获取默认数据源"""
        # 如果启用MongoDB缓存，MongoDB作为最高优先级数据源
        if self.use_mongodb_cache:
            return ChinaDataSource.MONGODB

        # 从环境变量获取，默认使用AKShare作为第一优先级数据源
        env_source = os.getenv('DEFAULT_CHINA_DATA_SOURCE', 'akshare').lower()

        # 映射到枚举
        source_mapping = {
            'tushare': ChinaDataSource.TUSHARE,
            'akshare': ChinaDataSource.AKSHARE,
            'baostock': ChinaDataSource.BAOSTOCK,
            'tdx': ChinaDataSource.TDX
        }

        return source_mapping.get(env_source, ChinaDataSource.AKSHARE)

    # ==================== Tushare数据接口 ====================

    def get_china_stock_data_tushare(self, symbol: str, start_date: str, end_date: str) -> str:
        """
        使用Tushare获取中国A股历史数据

        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            str: 格式化的股票数据报告
        """
        # 临时切换到Tushare数据源
        original_source = self.current_source
        self.current_source = ChinaDataSource.TUSHARE

        try:
            result = self._get_tushare_data(symbol, start_date, end_date)
            return result
        finally:
            # 恢复原始数据源
            self.current_source = original_source

    def search_china_stocks_tushare(self, keyword: str) -> str:
        """
        使用Tushare搜索中国股票

        Args:
            keyword: 搜索关键词

        Returns:
            str: 搜索结果
        """
        try:
            from .tushare_adapter import get_tushare_adapter

            logger.debug(f"🔍 [Tushare] 搜索股票: {keyword}")

            adapter = get_tushare_adapter()
            results = adapter.search_stocks(keyword)

            if results is not None and not results.empty:
                result = f"搜索关键词: {keyword}\n"
                result += f"找到 {len(results)} 只股票:\n\n"

                # 显示前10个结果
                for idx, row in results.head(10).iterrows():
                    result += f"代码: {row.get('symbol', '')}\n"
                    result += f"名称: {row.get('name', '未知')}\n"
                    result += f"行业: {row.get('industry', '未知')}\n"
                    result += f"地区: {row.get('area', '未知')}\n"
                    result += f"上市日期: {row.get('list_date', '未知')}\n"
                    result += "-" * 30 + "\n"

                return result
            else:
                return f"❌ 未找到匹配'{keyword}'的股票"

        except Exception as e:
            logger.error(f"❌ [Tushare] 搜索股票失败: {e}")
            return f"❌ 搜索股票失败: {e}"

    def get_fundamentals_data(self, symbol: str) -> str:
        """
        获取基本面数据，支持多数据源和自动降级
        优先级：MongoDB → Tushare → AKShare → 生成分析

        Args:
            symbol: 股票代码

        Returns:
            str: 基本面分析报告
        """
        logger.info(f"📊 [数据来源: {self.current_source.value}] 开始获取基本面数据: {symbol}",
                   extra={
                       'symbol': symbol,
                       'data_source': self.current_source.value,
                       'event_type': 'fundamentals_fetch_start'
                   })

        start_time = time.time()

        try:
            # 根据数据源调用相应的获取方法
            if self.current_source == ChinaDataSource.MONGODB:
                result = self._get_mongodb_fundamentals(symbol)
            elif self.current_source == ChinaDataSource.TUSHARE:
                result = self._get_tushare_fundamentals(symbol)
            elif self.current_source == ChinaDataSource.AKSHARE:
                result = self._get_akshare_fundamentals(symbol)
            else:
                # 其他数据源暂不支持基本面数据，生成基本分析
                result = self._generate_fundamentals_analysis(symbol)

            # 检查结果
            duration = time.time() - start_time
            result_length = len(result) if result else 0

            if result and "❌" not in result:
                logger.info(f"✅ [数据来源: {self.current_source.value}] 成功获取基本面数据: {symbol} ({result_length}字符, 耗时{duration:.2f}秒)",
                           extra={
                               'symbol': symbol,
                               'data_source': self.current_source.value,
                               'duration': duration,
                               'result_length': result_length,
                               'event_type': 'fundamentals_fetch_success'
                           })
                return result
            else:
                logger.warning(f"⚠️ [数据来源: {self.current_source.value}失败] 基本面数据质量异常，尝试降级: {symbol}",
                              extra={
                                  'symbol': symbol,
                                  'data_source': self.current_source.value,
                                  'event_type': 'fundamentals_fetch_fallback'
                              })
                return self._try_fallback_fundamentals(symbol)

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"❌ [数据来源: {self.current_source.value}异常] 获取基本面数据失败: {symbol} - {e}",
                        extra={
                            'symbol': symbol,
                            'data_source': self.current_source.value,
                            'duration': duration,
                            'error': str(e),
                            'event_type': 'fundamentals_fetch_exception'
                        }, exc_info=True)
            return self._try_fallback_fundamentals(symbol)

    def get_china_stock_fundamentals_tushare(self, symbol: str) -> str:
        """
        使用Tushare获取中国股票基本面数据（兼容旧接口）

        Args:
            symbol: 股票代码

        Returns:
            str: 基本面分析报告
        """
        # 重定向到统一接口
        return self._get_tushare_fundamentals(symbol)

    def get_news_data(self, symbol: str = None, hours_back: int = 24, limit: int = 20) -> List[Dict[str, Any]]:
        """
        获取新闻数据的统一接口，支持多数据源和自动降级
        优先级：MongoDB → Tushare → AKShare

        Args:
            symbol: 股票代码，为空则获取市场新闻
            hours_back: 回溯小时数
            limit: 返回数量限制

        Returns:
            List[Dict]: 新闻数据列表
        """
        logger.info(f"📰 [数据来源: {self.current_source.value}] 开始获取新闻数据: {symbol or '市场新闻'}, 回溯{hours_back}小时",
                   extra={
                       'symbol': symbol,
                       'hours_back': hours_back,
                       'limit': limit,
                       'data_source': self.current_source.value,
                       'event_type': 'news_fetch_start'
                   })

        start_time = time.time()

        try:
            # 根据数据源调用相应的获取方法
            if self.current_source == ChinaDataSource.MONGODB:
                result = self._get_mongodb_news(symbol, hours_back, limit)
            elif self.current_source == ChinaDataSource.TUSHARE:
                result = self._get_tushare_news(symbol, hours_back, limit)
            elif self.current_source == ChinaDataSource.AKSHARE:
                result = self._get_akshare_news(symbol, hours_back, limit)
            else:
                # 其他数据源暂不支持新闻数据
                logger.warning(f"⚠️ 数据源 {self.current_source.value} 不支持新闻数据")
                result = []

            # 检查结果
            duration = time.time() - start_time
            result_count = len(result) if result else 0

            if result and result_count > 0:
                logger.info(f"✅ [数据来源: {self.current_source.value}] 成功获取新闻数据: {symbol or '市场新闻'} ({result_count}条, 耗时{duration:.2f}秒)",
                           extra={
                               'symbol': symbol,
                               'data_source': self.current_source.value,
                               'news_count': result_count,
                               'duration': duration,
                               'event_type': 'news_fetch_success'
                           })
                return result
            else:
                logger.warning(f"⚠️ [数据来源: {self.current_source.value}] 未获取到新闻数据: {symbol or '市场新闻'}，尝试降级",
                              extra={
                                  'symbol': symbol,
                                  'data_source': self.current_source.value,
                                  'duration': duration,
                                  'event_type': 'news_fetch_fallback'
                              })
                return self._try_fallback_news(symbol, hours_back, limit)

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"❌ [数据来源: {self.current_source.value}异常] 获取新闻数据失败: {symbol or '市场新闻'} - {e}",
                        extra={
                            'symbol': symbol,
                            'data_source': self.current_source.value,
                            'duration': duration,
                            'error': str(e),
                            'event_type': 'news_fetch_exception'
                        }, exc_info=True)
            return self._try_fallback_news(symbol, hours_back, limit)

    def get_china_stock_info_tushare(self, symbol: str) -> str:
        """
        使用Tushare获取中国股票基本信息

        Args:
            symbol: 股票代码

        Returns:
            str: 股票基本信息
        """
        try:
            from .tushare_adapter import get_tushare_adapter

            logger.debug(f"📊 [Tushare] 获取{symbol}股票信息...")

            adapter = get_tushare_adapter()
            stock_info = adapter.get_stock_info(symbol)

            if stock_info:
                result = f"📊 {stock_info.get('name', '未知')}({symbol}) - 股票信息\n"
                result += f"股票代码: {stock_info.get('symbol', symbol)}\n"
                result += f"股票名称: {stock_info.get('name', '未知')}\n"
                result += f"所属行业: {stock_info.get('industry', '未知')}\n"
                result += f"所属地区: {stock_info.get('area', '未知')}\n"
                result += f"上市日期: {stock_info.get('list_date', '未知')}\n"
                result += f"市场类型: {stock_info.get('market', '未知')}\n"
                result += f"交易所: {stock_info.get('exchange', '未知')}\n"
                result += f"货币单位: {stock_info.get('curr_type', 'CNY')}\n"

                return result
            else:
                return f"❌ 未获取到{symbol}的股票信息"

        except Exception as e:
            logger.error(f"❌ [Tushare] 获取股票信息失败: {e}", exc_info=True)
            return f"❌ 获取{symbol}股票信息失败: {e}"

    def _check_available_sources(self) -> List[ChinaDataSource]:
        """检查可用的数据源"""
        available = []

        # 检查MongoDB（最高优先级）
        if self.use_mongodb_cache:
            try:
                from tradingagents.dataflows.enhanced_data_adapter import get_enhanced_data_adapter
                adapter = get_enhanced_data_adapter()
                if adapter.use_app_cache and adapter.db is not None:
                    available.append(ChinaDataSource.MONGODB)
                    logger.info("✅ MongoDB数据源可用（最高优先级）")
                else:
                    logger.warning("⚠️ MongoDB数据源不可用: 数据库未连接")
            except Exception as e:
                logger.warning(f"⚠️ MongoDB数据源不可用: {e}")

        # 检查Tushare
        try:
            import tushare as ts
            token = os.getenv('TUSHARE_TOKEN')
            if token:
                available.append(ChinaDataSource.TUSHARE)
                logger.info("✅ Tushare数据源可用")
            else:
                logger.warning("⚠️ Tushare数据源不可用: 未设置TUSHARE_TOKEN")
        except ImportError:
            logger.warning("⚠️ Tushare数据源不可用: 库未安装")

        # 检查AKShare
        try:
            import akshare as ak
            available.append(ChinaDataSource.AKSHARE)
            logger.info("✅ AKShare数据源可用")
        except ImportError:
            logger.warning("⚠️ AKShare数据源不可用: 库未安装")

        # 检查BaoStock
        try:
            import baostock as bs
            available.append(ChinaDataSource.BAOSTOCK)
            logger.info(f"✅ BaoStock数据源可用")
        except ImportError:
            logger.warning(f"⚠️ BaoStock数据源不可用: 库未安装")

        # 检查TDX (通达信)
        try:
            import pytdx
            available.append(ChinaDataSource.TDX)
            logger.warning(f"⚠️ TDX数据源可用 (将被淘汰)")
        except ImportError:
            logger.info(f"ℹ️ TDX数据源不可用: 库未安装")

        return available

    def get_current_source(self) -> ChinaDataSource:
        """获取当前数据源"""
        return self.current_source

    def set_current_source(self, source: ChinaDataSource) -> bool:
        """设置当前数据源"""
        if source in self.available_sources:
            self.current_source = source
            logger.info(f"✅ 数据源已切换到: {source.value}")
            return True
        else:
            logger.error(f"❌ 数据源不可用: {source.value}")
            return False

    def get_data_adapter(self):
        """获取当前数据源的适配器"""
        if self.current_source == ChinaDataSource.MONGODB:
            return self._get_mongodb_adapter()
        elif self.current_source == ChinaDataSource.TUSHARE:
            return self._get_tushare_adapter()
        elif self.current_source == ChinaDataSource.AKSHARE:
            return self._get_akshare_adapter()
        elif self.current_source == ChinaDataSource.BAOSTOCK:
            return self._get_baostock_adapter()
        elif self.current_source == ChinaDataSource.TDX:
            return self._get_tdx_adapter()
        else:
            raise ValueError(f"不支持的数据源: {self.current_source}")

    def _get_mongodb_adapter(self):
        """获取MongoDB适配器"""
        try:
            from tradingagents.dataflows.enhanced_data_adapter import get_enhanced_data_adapter
            return get_enhanced_data_adapter()
        except ImportError as e:
            logger.error(f"❌ MongoDB适配器导入失败: {e}")
            return None

    def _get_tushare_adapter(self):
        """获取Tushare适配器"""
        try:
            from .tushare_adapter import get_tushare_adapter
            return get_tushare_adapter()
        except ImportError as e:
            logger.error(f"❌ Tushare适配器导入失败: {e}")
            return None

    def _get_akshare_adapter(self):
        """获取AKShare适配器"""
        try:
            from .akshare_utils import get_akshare_provider
            return get_akshare_provider()
        except ImportError as e:
            logger.error(f"❌ AKShare适配器导入失败: {e}")
            return None

    def _get_baostock_adapter(self):
        """获取BaoStock适配器"""
        try:
            from .baostock_utils import get_baostock_provider
            return get_baostock_provider()
        except ImportError as e:
            logger.error(f"❌ BaoStock适配器导入失败: {e}")
            return None

    def _get_tdx_adapter(self):
        """获取TDX适配器 (已弃用)"""
        logger.warning(f"⚠️ 警告: TDX数据源已弃用，建议使用Tushare")
        try:
            from .tdx_utils import get_tdx_provider
            return get_tdx_provider()
        except ImportError as e:
            logger.error(f"❌ TDX适配器导入失败: {e}")
            return None

    def get_stock_data(self, symbol: str, start_date: str = None, end_date: str = None, period: str = "daily") -> str:
        """
        获取股票数据的统一接口，支持多周期数据

        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            period: 数据周期（daily/weekly/monthly），默认为daily

        Returns:
            str: 格式化的股票数据
        """
        # 记录详细的输入参数
        logger.info(f"📊 [数据来源: {self.current_source.value}] 开始获取{period}数据: {symbol}",
                   extra={
                       'symbol': symbol,
                       'start_date': start_date,
                       'end_date': end_date,
                       'period': period,
                       'data_source': self.current_source.value,
                       'event_type': 'data_fetch_start'
                   })

        # 添加详细的股票代码追踪日志
        logger.info(f"🔍 [股票代码追踪] DataSourceManager.get_stock_data 接收到的股票代码: '{symbol}' (类型: {type(symbol)})")
        logger.info(f"🔍 [股票代码追踪] 股票代码长度: {len(str(symbol))}")
        logger.info(f"🔍 [股票代码追踪] 股票代码字符: {list(str(symbol))}")
        logger.info(f"🔍 [股票代码追踪] 当前数据源: {self.current_source.value}")

        start_time = time.time()

        try:
            # 根据数据源调用相应的获取方法
            if self.current_source == ChinaDataSource.MONGODB:
                result = self._get_mongodb_data(symbol, start_date, end_date, period)
            elif self.current_source == ChinaDataSource.TUSHARE:
                logger.info(f"🔍 [股票代码追踪] 调用 Tushare 数据源，传入参数: symbol='{symbol}', period='{period}'")
                result = self._get_tushare_data(symbol, start_date, end_date, period)
            elif self.current_source == ChinaDataSource.AKSHARE:
                result = self._get_akshare_data(symbol, start_date, end_date, period)
            elif self.current_source == ChinaDataSource.BAOSTOCK:
                result = self._get_baostock_data(symbol, start_date, end_date, period)
            elif self.current_source == ChinaDataSource.TDX:
                result = self._get_tdx_data(symbol, start_date, end_date, period)
            else:
                result = f"❌ 不支持的数据源: {self.current_source.value}"

            # 记录详细的输出结果
            duration = time.time() - start_time
            result_length = len(result) if result else 0
            is_success = result and "❌" not in result and "错误" not in result

            if is_success:
                logger.info(f"✅ [数据来源: {self.current_source.value}] 成功获取股票数据: {symbol} ({result_length}字符, 耗时{duration:.2f}秒)",
                           extra={
                               'symbol': symbol,
                               'start_date': start_date,
                               'end_date': end_date,
                               'data_source': self.current_source.value,
                               'duration': duration,
                               'result_length': result_length,
                               'result_preview': result[:200] + '...' if result_length > 200 else result,
                               'event_type': 'data_fetch_success'
                           })
                return result
            else:
                logger.warning(f"⚠️ [数据来源: {self.current_source.value}失败] 数据质量异常，尝试降级到其他数据源: {symbol}",
                              extra={
                                  'symbol': symbol,
                                  'start_date': start_date,
                                  'end_date': end_date,
                                  'data_source': self.current_source.value,
                                  'duration': duration,
                                  'result_length': result_length,
                                  'result_preview': result[:200] + '...' if result_length > 200 else result,
                                  'event_type': 'data_fetch_warning'
                              })

                # 数据质量异常时也尝试降级到其他数据源
                fallback_result = self._try_fallback_sources(symbol, start_date, end_date)
                if fallback_result and "❌" not in fallback_result and "错误" not in fallback_result:
                    logger.info(f"✅ [数据来源: 备用数据源] 降级成功获取数据: {symbol}")
                    return fallback_result
                else:
                    logger.error(f"❌ [数据来源: 所有数据源失败] 所有数据源都无法获取有效数据: {symbol}")
                    return result  # 返回原始结果（包含错误信息）

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"❌ [数据获取] 异常失败: {e}",
                        extra={
                            'symbol': symbol,
                            'start_date': start_date,
                            'end_date': end_date,
                            'data_source': self.current_source.value,
                            'duration': duration,
                            'error': str(e),
                            'event_type': 'data_fetch_exception'
                        }, exc_info=True)
            return self._try_fallback_sources(symbol, start_date, end_date)

    def _get_mongodb_data(self, symbol: str, start_date: str, end_date: str, period: str = "daily") -> str:
        """从MongoDB获取多周期数据"""
        logger.debug(f"📊 [MongoDB] 调用参数: symbol={symbol}, start_date={start_date}, end_date={end_date}, period={period}")

        try:
            from tradingagents.dataflows.enhanced_data_adapter import get_enhanced_data_adapter
            adapter = get_enhanced_data_adapter()

            # 从MongoDB获取指定周期的历史数据
            df = adapter.get_historical_data(symbol, start_date, end_date, period=period)

            if df is not None and not df.empty:
                logger.info(f"✅ [数据来源: MongoDB-{period}] 成功获取数据: {symbol} ({len(df)}条记录)")
                # 转换为字符串格式返回
                return df.to_string()
            else:
                logger.warning(f"⚠️ [数据来源: MongoDB] 未找到{period}数据: {symbol}，降级到其他数据源")
                # MongoDB没有数据，降级到其他数据源
                return self._try_fallback_sources(symbol, start_date, end_date, period)

        except Exception as e:
            logger.error(f"❌ [数据来源: MongoDB异常] 获取失败: {e}")
            # MongoDB异常，降级到其他数据源
            return self._try_fallback_sources(symbol, start_date, end_date)

    def _get_tushare_data(self, symbol: str, start_date: str, end_date: str, period: str = "daily") -> str:
        """使用Tushare获取多周期数据 - 直接调用适配器，避免循环调用"""
        logger.debug(f"📊 [Tushare] 调用参数: symbol={symbol}, start_date={start_date}, end_date={end_date}, period={period}")

        # 添加详细的股票代码追踪日志
        logger.info(f"🔍 [股票代码追踪] _get_tushare_data 接收到的股票代码: '{symbol}' (类型: {type(symbol)})")
        logger.info(f"🔍 [股票代码追踪] 股票代码长度: {len(str(symbol))}")
        logger.info(f"🔍 [股票代码追踪] 股票代码字符: {list(str(symbol))}")
        logger.info(f"🔍 [DataSourceManager详细日志] _get_tushare_data 开始执行")
        logger.info(f"🔍 [DataSourceManager详细日志] 当前数据源: {self.current_source.value}")

        start_time = time.time()
        try:
            # 直接调用适配器，避免循环调用interface
            from .tushare_adapter import get_tushare_adapter
            logger.info(f"🔍 [股票代码追踪] 调用 tushare_adapter，传入参数: symbol='{symbol}'")
            logger.info(f"🔍 [DataSourceManager详细日志] 开始调用tushare_adapter...")

            adapter = get_tushare_adapter()
            data = adapter.get_stock_data(symbol, start_date, end_date)

            if data is not None and not data.empty:
                # 获取股票基本信息
                stock_info = adapter.get_stock_info(symbol)
                stock_name = stock_info.get('name', f'股票{symbol}') if stock_info else f'股票{symbol}'

                # 计算最新价格和涨跌幅
                latest_data = data.iloc[-1]
                latest_price = latest_data.get('close', 0)
                prev_close = data.iloc[-2].get('close', latest_price) if len(data) > 1 else latest_price
                change = latest_price - prev_close
                change_pct = (change / prev_close * 100) if prev_close != 0 else 0

                # 格式化数据报告
                result = f"📊 {stock_name}({symbol}) - Tushare数据\n"
                result += f"数据期间: {start_date} 至 {end_date}\n"
                result += f"数据条数: {len(data)}条\n\n"

                result += f"💰 最新价格: ¥{latest_price:.2f}\n"
                result += f"📈 涨跌额: {change:+.2f} ({change_pct:+.2f}%)\n\n"

                # 添加统计信息
                result += f"📊 价格统计:\n"
                result += f"   最高价: ¥{data['high'].max():.2f}\n"
                result += f"   最低价: ¥{data['low'].min():.2f}\n"
                result += f"   平均价: ¥{data['close'].mean():.2f}\n"
                # 防御性获取成交量数据
                volume_value = self._get_volume_safely(data)
                result += f"   成交量: {volume_value:,.0f}股\n"

                return result
            else:
                result = f"❌ 未获取到{symbol}的有效数据"

            duration = time.time() - start_time
            logger.info(f"🔍 [DataSourceManager详细日志] interface调用完成，耗时: {duration:.3f}秒")
            logger.info(f"🔍 [股票代码追踪] get_china_stock_data_tushare 返回结果前200字符: {result[:200] if result else 'None'}")
            logger.info(f"🔍 [DataSourceManager详细日志] 返回结果类型: {type(result)}")
            logger.info(f"🔍 [DataSourceManager详细日志] 返回结果长度: {len(result) if result else 0}")

            logger.debug(f"📊 [Tushare] 调用完成: 耗时={duration:.2f}s, 结果长度={len(result) if result else 0}")

            return result
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"❌ [Tushare] 调用失败: {e}, 耗时={duration:.2f}s", exc_info=True)
            logger.error(f"❌ [DataSourceManager详细日志] 异常类型: {type(e).__name__}")
            logger.error(f"❌ [DataSourceManager详细日志] 异常信息: {str(e)}")
            import traceback
            logger.error(f"❌ [DataSourceManager详细日志] 异常堆栈: {traceback.format_exc()}")
            raise

    def _get_akshare_data(self, symbol: str, start_date: str, end_date: str, period: str = "daily") -> str:
        """使用AKShare获取多周期数据"""
        logger.debug(f"📊 [AKShare] 调用参数: symbol={symbol}, start_date={start_date}, end_date={end_date}, period={period}")

        start_time = time.time()
        try:
            # 这里需要实现AKShare的统一接口
            from .akshare_utils import get_akshare_provider
            provider = get_akshare_provider()
            data = provider.get_stock_data(symbol, start_date, end_date)

            duration = time.time() - start_time

            if data is not None and not data.empty:
                result = f"股票代码: {symbol}\n"
                result += f"数据期间: {start_date} 至 {end_date}\n"
                result += f"数据条数: {len(data)}条\n\n"

                # 显示最新3天数据，确保在各种显示环境下都能完整显示
                display_rows = min(3, len(data))
                result += f"最新{display_rows}天数据:\n"

                # 使用pandas选项确保显示完整数据
                with pd.option_context('display.max_rows', None,
                                     'display.max_columns', None,
                                     'display.width', None,
                                     'display.max_colwidth', None):
                    result += data.tail(display_rows).to_string(index=False)

                # 如果数据超过3天，也显示一些统计信息
                if len(data) > 3:
                    latest_price = data.iloc[-1]['收盘'] if '收盘' in data.columns else data.iloc[-1].get('close', 'N/A')
                    first_price = data.iloc[0]['收盘'] if '收盘' in data.columns else data.iloc[0].get('close', 'N/A')
                    if latest_price != 'N/A' and first_price != 'N/A':
                        try:
                            change = float(latest_price) - float(first_price)
                            change_pct = (change / float(first_price)) * 100
                            result += f"\n\n📊 期间统计:\n"
                            result += f"期间涨跌: {change:+.2f} ({change_pct:+.2f}%)\n"
                            result += f"最高价: {data['最高'].max() if '最高' in data.columns else data.get('high', pd.Series()).max():.2f}\n"
                            result += f"最低价: {data['最低'].min() if '最低' in data.columns else data.get('low', pd.Series()).min():.2f}"
                        except (ValueError, TypeError):
                            pass

                logger.debug(f"📊 [AKShare] 调用成功: 耗时={duration:.2f}s, 数据条数={len(data)}, 结果长度={len(result)}")
                return result
            else:
                result = f"❌ 未能获取{symbol}的股票数据"
                logger.warning(f"⚠️ [AKShare] 数据为空: 耗时={duration:.2f}s")
                return result

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"❌ [AKShare] 调用失败: {e}, 耗时={duration:.2f}s", exc_info=True)
            return f"❌ AKShare获取{symbol}数据失败: {e}"

    def _get_baostock_data(self, symbol: str, start_date: str, end_date: str, period: str = "daily") -> str:
        """使用BaoStock获取多周期数据"""
        # 这里需要实现BaoStock的统一接口
        from .baostock_utils import get_baostock_provider
        provider = get_baostock_provider()
        data = provider.get_stock_data(symbol, start_date, end_date)

        if data is not None and not data.empty:
            result = f"股票代码: {symbol}\n"
            result += f"数据期间: {start_date} 至 {end_date}\n"
            result += f"数据条数: {len(data)}条\n\n"

            # 显示最新3天数据，确保在各种显示环境下都能完整显示
            display_rows = min(3, len(data))
            result += f"最新{display_rows}天数据:\n"

            # 使用pandas选项确保显示完整数据
            with pd.option_context('display.max_rows', None,
                                 'display.max_columns', None,
                                 'display.width', None,
                                 'display.max_colwidth', None):
                result += data.tail(display_rows).to_string(index=False)
            return result
        else:
            return f"❌ 未能获取{symbol}的股票数据"

    def _get_tdx_data(self, symbol: str, start_date: str, end_date: str, period: str = "daily") -> str:
        """使用TDX获取多周期数据 (已弃用)"""
        logger.warning(f"⚠️ 警告: 正在使用已弃用的TDX数据源")
        from .tdx_utils import get_china_stock_data
        return get_china_stock_data(symbol, start_date, end_date)

    def _get_volume_safely(self, data) -> float:
        """安全地获取成交量数据，支持多种列名"""
        try:
            # 支持多种可能的成交量列名
            volume_columns = ['volume', 'vol', 'turnover', 'trade_volume']

            for col in volume_columns:
                if col in data.columns:
                    logger.info(f"✅ 找到成交量列: {col}")
                    return data[col].sum()

            # 如果都没找到，记录警告并返回0
            logger.warning(f"⚠️ 未找到成交量列，可用列: {list(data.columns)}")
            return 0

        except Exception as e:
            logger.error(f"❌ 获取成交量失败: {e}")
            return 0

    def _try_fallback_sources(self, symbol: str, start_date: str, end_date: str, period: str = "daily") -> str:
        """尝试备用数据源 - 避免递归调用"""
        logger.error(f"🔄 {self.current_source.value}失败，尝试备用数据源获取{period}数据...")

        # 备用数据源优先级: AKShare > Tushare > BaoStock > TDX
        # 注意：不包含MongoDB，因为MongoDB是最高优先级，如果失败了就不再尝试
        fallback_order = [
            ChinaDataSource.AKSHARE,
            ChinaDataSource.TUSHARE,
            ChinaDataSource.BAOSTOCK,
            ChinaDataSource.TDX
        ]

        for source in fallback_order:
            if source != self.current_source and source in self.available_sources:
                try:
                    logger.info(f"🔄 尝试备用数据源获取{period}数据: {source.value}")

                    # 直接调用具体的数据源方法，避免递归
                    if source == ChinaDataSource.TUSHARE:
                        result = self._get_tushare_data(symbol, start_date, end_date, period)
                    elif source == ChinaDataSource.AKSHARE:
                        result = self._get_akshare_data(symbol, start_date, end_date, period)
                    elif source == ChinaDataSource.BAOSTOCK:
                        result = self._get_baostock_data(symbol, start_date, end_date, period)
                    elif source == ChinaDataSource.TDX:
                        result = self._get_tdx_data(symbol, start_date, end_date, period)
                    else:
                        logger.warning(f"⚠️ 未知数据源: {source.value}")
                        continue

                    if "❌" not in result:
                        logger.info(f"✅ [数据来源: 备用数据源] 降级成功获取{period}数据: {source.value}")
                        return result
                    else:
                        logger.warning(f"⚠️ 备用数据源{source.value}返回错误结果")

                except Exception as e:
                    logger.error(f"❌ 备用数据源{source.value}也失败: {e}")
                    continue

        return f"❌ 所有数据源都无法获取{symbol}的{period}数据"

    def get_stock_info(self, symbol: str) -> Dict:
        """
        获取股票基本信息，支持多数据源和自动降级
        优先级：MongoDB → Tushare → AKShare → BaoStock
        """
        logger.info(f"📊 [数据来源: {self.current_source.value}] 开始获取股票信息: {symbol}")

        # 优先使用 App Mongo 缓存（当 ta_use_app_cache=True）
        try:
            from tradingagents.config.runtime_settings import use_app_cache_enabled  # type: ignore
            use_cache = use_app_cache_enabled(False)
        except Exception:
            use_cache = False
        if use_cache:
            logger.info(f"🔧 [配置] ta_use_app_cache={use_cache}")

            try:
                from .app_cache_adapter import get_basics_from_cache, get_market_quote_dataframe
                doc = get_basics_from_cache(symbol)
                if doc:
                    name = doc.get('name') or doc.get('stock_name') or ''
                    # 规范化行业与板块（避免把“中小板/创业板”等板块值误作行业）
                    board_labels = {'主板', '中小板', '创业板', '科创板'}
                    raw_industry = (doc.get('industry') or doc.get('industry_name') or '').strip()
                    sec_or_cat = (doc.get('sec') or doc.get('category') or '').strip()
                    market_val = (doc.get('market') or '').strip()
                    industry_val = raw_industry or sec_or_cat or '未知'
                    changed = False
                    if raw_industry in board_labels:
                        # 若industry是板块名，则将其用于market；industry改用更细分类（sec/category）
                        if not market_val:
                            market_val = raw_industry
                            changed = True
                        if sec_or_cat:
                            industry_val = sec_or_cat
                            changed = True
                    if changed:
                        try:
                            logger.debug(f"🔧 [字段归一化] industry原值='{raw_industry}' → 行业='{industry_val}', 市场/板块='{market_val or doc.get('market', '未知')}'")
                        except Exception:
                            pass

                    result = {
                        'symbol': symbol,
                        'name': name or f'股票{symbol}',
                        'area': doc.get('area', '未知'),
                        'industry': industry_val or '未知',
                        'market': market_val or doc.get('market', '未知'),
                        'list_date': doc.get('list_date', '未知'),
                        'source': 'app_cache'
                    }
                    # 追加快照行情（若存在）
                    try:
                        df = get_market_quote_dataframe(symbol)
                        if df is not None and not df.empty:
                            row = df.iloc[-1]
                            result['current_price'] = row.get('close')
                            result['change_pct'] = row.get('pct_chg')
                            result['volume'] = row.get('volume')
                            result['quote_date'] = row.get('date')
                            result['quote_source'] = 'market_quotes'
                            logger.info(f"✅ [股票信息] 附加行情 | price={result['current_price']} pct={result['change_pct']} vol={result['volume']} code={symbol}")
                    except Exception as _e:
                        logger.debug(f"附加行情失败（忽略）：{_e}")

                    if name:
                        logger.info(f"✅ [数据来源: MongoDB-stock_basic_info] 成功获取: {symbol}")
                        return result
                    else:
                        logger.warning(f"⚠️ [数据来源: MongoDB] 未找到有效名称: {symbol}，降级到其他数据源")
            except Exception as e:
                logger.error(f"❌ [数据来源: MongoDB异常] 获取股票信息失败: {e}", exc_info=True)


        # 首先尝试当前数据源
        try:
            if self.current_source == ChinaDataSource.TUSHARE:
                from .interface import get_china_stock_info_tushare
                info_str = get_china_stock_info_tushare(symbol)
                result = self._parse_stock_info_string(info_str, symbol)

                # 检查是否获取到有效信息
                if result.get('name') and result['name'] != f'股票{symbol}':
                    logger.info(f"✅ [数据来源: Tushare-股票信息] 成功获取: {symbol}")
                    return result
                else:
                    logger.warning(f"⚠️ [数据来源: Tushare失败] 返回无效信息，尝试降级: {symbol}")
                    return self._try_fallback_stock_info(symbol)
            else:
                adapter = self.get_data_adapter()
                if adapter and hasattr(adapter, 'get_stock_info'):
                    result = adapter.get_stock_info(symbol)
                    if result.get('name') and result['name'] != f'股票{symbol}':
                        logger.info(f"✅ [数据来源: {self.current_source.value}-股票信息] 成功获取: {symbol}")
                        return result
                    else:
                        logger.warning(f"⚠️ [数据来源: {self.current_source.value}失败] 返回无效信息，尝试降级: {symbol}")
                        return self._try_fallback_stock_info(symbol)
                else:
                    logger.warning(f"⚠️ [数据来源: {self.current_source.value}] 不支持股票信息获取，尝试降级: {symbol}")
                    return self._try_fallback_stock_info(symbol)

        except Exception as e:
            logger.error(f"❌ [数据来源: {self.current_source.value}异常] 获取股票信息失败: {e}", exc_info=True)
            return self._try_fallback_stock_info(symbol)

    def _try_fallback_stock_info(self, symbol: str) -> Dict:
        """尝试使用备用数据源获取股票基本信息"""
        logger.error(f"🔄 {self.current_source.value}失败，尝试备用数据源获取股票信息...")

        # 获取所有可用数据源
        available_sources = self.available_sources.copy()

        # 移除当前数据源
        if self.current_source.value in available_sources:
            available_sources.remove(self.current_source.value)

        # 尝试所有备用数据源
        for source_name in available_sources:
            try:
                source = ChinaDataSource(source_name)
                logger.info(f"🔄 尝试备用数据源获取股票信息: {source_name}")

                # 根据数据源类型获取股票信息
                if source == ChinaDataSource.TUSHARE:
                    from .interface import get_china_stock_info_tushare
                    info_str = get_china_stock_info_tushare(symbol)
                    result = self._parse_stock_info_string(info_str, symbol)
                elif source == ChinaDataSource.AKSHARE:
                    result = self._get_akshare_stock_info(symbol)
                elif source == ChinaDataSource.BAOSTOCK:
                    result = self._get_baostock_stock_info(symbol)
                else:
                    # 尝试通用适配器
                    original_source = self.current_source
                    self.current_source = source
                    adapter = self.get_data_adapter()
                    self.current_source = original_source

                    if adapter and hasattr(adapter, 'get_stock_info'):
                        result = adapter.get_stock_info(symbol)
                    else:
                        logger.warning(f"⚠️ [股票信息] {source_name}不支持股票信息获取")
                        continue

                # 检查是否获取到有效信息
                if result.get('name') and result['name'] != f'股票{symbol}':
                    logger.info(f"✅ [数据来源: 备用数据源] 降级成功获取股票信息: {source_name}")
                    return result
                else:
                    logger.warning(f"⚠️ [数据来源: {source_name}] 返回无效信息")

            except Exception as e:
                logger.error(f"❌ 备用数据源{source_name}失败: {e}")
                continue

        # 所有数据源都失败，返回默认值
        logger.error(f"❌ 所有数据源都无法获取{symbol}的股票信息")
        return {'symbol': symbol, 'name': f'股票{symbol}', 'source': 'unknown'}

    def _get_akshare_stock_info(self, symbol: str) -> Dict:
        """使用AKShare获取股票基本信息"""
        try:
            import akshare as ak

            # 尝试获取个股信息
            stock_info = ak.stock_individual_info_em(symbol=symbol)

            if stock_info is not None and not stock_info.empty:
                # 转换为字典格式
                info = {'symbol': symbol, 'source': 'akshare'}

                # 提取股票名称
                name_row = stock_info[stock_info['item'] == '股票简称']
                if not name_row.empty:
                    info['name'] = name_row['value'].iloc[0]
                else:
                    info['name'] = f'股票{symbol}'

                # 提取其他信息
                info['area'] = '未知'  # AKShare没有地区信息
                info['industry'] = '未知'  # 可以通过其他API获取
                info['market'] = '未知'  # 可以根据股票代码推断
                info['list_date'] = '未知'  # 可以通过其他API获取

                return info
            else:
                return {'symbol': symbol, 'name': f'股票{symbol}', 'source': 'akshare'}

        except Exception as e:
            logger.error(f"❌ [股票信息] AKShare获取失败: {e}")
            return {'symbol': symbol, 'name': f'股票{symbol}', 'source': 'akshare', 'error': str(e)}

    def _get_baostock_stock_info(self, symbol: str) -> Dict:
        """使用BaoStock获取股票基本信息"""
        try:
            import baostock as bs

            # 转换股票代码格式
            if symbol.startswith('6'):
                bs_code = f"sh.{symbol}"
            else:
                bs_code = f"sz.{symbol}"

            # 登录BaoStock
            lg = bs.login()
            if lg.error_code != '0':
                logger.error(f"❌ [股票信息] BaoStock登录失败: {lg.error_msg}")
                return {'symbol': symbol, 'name': f'股票{symbol}', 'source': 'baostock'}

            # 查询股票基本信息
            rs = bs.query_stock_basic(code=bs_code)
            if rs.error_code != '0':
                bs.logout()
                logger.error(f"❌ [股票信息] BaoStock查询失败: {rs.error_msg}")
                return {'symbol': symbol, 'name': f'股票{symbol}', 'source': 'baostock'}

            # 解析结果
            data_list = []
            while (rs.error_code == '0') & rs.next():
                data_list.append(rs.get_row_data())

            # 登出
            bs.logout()

            if data_list:
                # BaoStock返回格式: [code, code_name, ipoDate, outDate, type, status]
                info = {'symbol': symbol, 'source': 'baostock'}
                info['name'] = data_list[0][1]  # code_name
                info['area'] = '未知'  # BaoStock没有地区信息
                info['industry'] = '未知'  # BaoStock没有行业信息
                info['market'] = '未知'  # 可以根据股票代码推断
                info['list_date'] = data_list[0][2]  # ipoDate

                return info
            else:
                return {'symbol': symbol, 'name': f'股票{symbol}', 'source': 'baostock'}

        except Exception as e:
            logger.error(f"❌ [股票信息] BaoStock获取失败: {e}")
            return {'symbol': symbol, 'name': f'股票{symbol}', 'source': 'baostock', 'error': str(e)}

    def _parse_stock_info_string(self, info_str: str, symbol: str) -> Dict:
        """解析股票信息字符串为字典"""
        try:
            info = {'symbol': symbol, 'source': self.current_source.value}
            lines = info_str.split('\n')

            for line in lines:
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip()

                    if '股票名称' in key:
                        info['name'] = value
                    elif '所属行业' in key:
                        info['industry'] = value
                    elif '所属地区' in key:
                        info['area'] = value
                    elif '上市市场' in key:
                        info['market'] = value
                    elif '上市日期' in key:
                        info['list_date'] = value

            return info

        except Exception as e:
            logger.error(f"⚠️ 解析股票信息失败: {e}")
            return {'symbol': symbol, 'name': f'股票{symbol}', 'source': self.current_source.value}

    # ==================== 基本面数据获取方法 ====================

    def _get_mongodb_fundamentals(self, symbol: str) -> str:
        """从 MongoDB 获取财务数据"""
        logger.debug(f"📊 [MongoDB] 调用参数: symbol={symbol}")

        try:
            from tradingagents.dataflows.enhanced_data_adapter import get_enhanced_data_adapter
            import pandas as pd
            adapter = get_enhanced_data_adapter()

            # 从 MongoDB 获取财务数据
            financial_data = adapter.get_financial_data(symbol)

            # 检查数据类型和内容
            if financial_data is not None:
                # 如果是 DataFrame，转换为字典列表
                if isinstance(financial_data, pd.DataFrame):
                    if not financial_data.empty:
                        logger.info(f"✅ [数据来源: MongoDB-财务数据] 成功获取: {symbol} ({len(financial_data)}条记录)")
                        # 转换为字典列表
                        financial_dict_list = financial_data.to_dict('records')
                        # 格式化财务数据为报告
                        return self._format_financial_data(symbol, financial_dict_list)
                    else:
                        logger.warning(f"⚠️ [数据来源: MongoDB] 财务数据为空: {symbol}，降级到其他数据源")
                        return self._try_fallback_fundamentals(symbol)
                # 如果是列表
                elif isinstance(financial_data, list) and len(financial_data) > 0:
                    logger.info(f"✅ [数据来源: MongoDB-财务数据] 成功获取: {symbol} ({len(financial_data)}条记录)")
                    return self._format_financial_data(symbol, financial_data)
                else:
                    logger.warning(f"⚠️ [数据来源: MongoDB] 未找到财务数据: {symbol}，降级到其他数据源")
                    return self._try_fallback_fundamentals(symbol)
            else:
                logger.warning(f"⚠️ [数据来源: MongoDB] 未找到财务数据: {symbol}，降级到其他数据源")
                # MongoDB 没有数据，降级到其他数据源
                return self._try_fallback_fundamentals(symbol)

        except Exception as e:
            logger.error(f"❌ [数据来源: MongoDB异常] 获取财务数据失败: {e}", exc_info=True)
            # MongoDB 异常，降级到其他数据源
            return self._try_fallback_fundamentals(symbol)

    def _get_tushare_fundamentals(self, symbol: str) -> str:
        """从 Tushare 获取基本面数据"""
        logger.debug(f"📊 [Tushare] 调用参数: symbol={symbol}")

        try:
            from .tushare_adapter import get_tushare_adapter
            adapter = get_tushare_adapter()
            fundamentals = adapter.get_fundamentals(symbol)

            if fundamentals and "❌" not in fundamentals:
                logger.info(f"✅ [数据来源: Tushare-基本面] 成功获取: {symbol}")
                return fundamentals
            else:
                logger.warning(f"⚠️ [数据来源: Tushare] 未找到基本面数据: {symbol}")
                return f"❌ 未获取到{symbol}的基本面数据"

        except Exception as e:
            logger.error(f"❌ [数据来源: Tushare异常] 获取基本面数据失败: {e}")
            return f"❌ 获取{symbol}基本面数据失败: {e}"

    def _get_akshare_fundamentals(self, symbol: str) -> str:
        """从 AKShare 生成基本面分析"""
        logger.debug(f"📊 [AKShare] 调用参数: symbol={symbol}")

        try:
            # AKShare 没有直接的基本面数据接口，使用生成分析
            logger.info(f"📊 [数据来源: AKShare-生成分析] 生成基本面分析: {symbol}")
            return self._generate_fundamentals_analysis(symbol)

        except Exception as e:
            logger.error(f"❌ [数据来源: AKShare异常] 生成基本面分析失败: {e}")
            return f"❌ 生成{symbol}基本面分析失败: {e}"

    def _format_financial_data(self, symbol: str, financial_data: List[Dict]) -> str:
        """格式化财务数据为报告"""
        try:
            if not financial_data or len(financial_data) == 0:
                return f"❌ 未找到{symbol}的财务数据"

            # 获取最新的财务数据
            latest = financial_data[0]

            # 构建报告
            report = f"📊 {symbol} 基本面数据（来自MongoDB）\n\n"

            # 基本信息
            report += f"📅 报告期: {latest.get('end_date', '未知')}\n"
            report += f"📈 数据来源: MongoDB财务数据库\n\n"

            # 财务指标
            report += "💰 财务指标:\n"
            if 'total_revenue' in latest:
                report += f"   营业总收入: {latest.get('total_revenue', 0):,.2f}\n"
            if 'net_profit' in latest:
                report += f"   净利润: {latest.get('net_profit', 0):,.2f}\n"
            if 'total_assets' in latest:
                report += f"   总资产: {latest.get('total_assets', 0):,.2f}\n"
            if 'total_liab' in latest:
                report += f"   总负债: {latest.get('total_liab', 0):,.2f}\n"

            # 估值指标
            report += "\n📊 估值指标:\n"
            if 'pe' in latest:
                report += f"   市盈率(PE): {latest.get('pe', 0):.2f}\n"
            if 'pb' in latest:
                report += f"   市净率(PB): {latest.get('pb', 0):.2f}\n"
            if 'ps' in latest:
                report += f"   市销率(PS): {latest.get('ps', 0):.2f}\n"

            # 盈利能力
            report += "\n💹 盈利能力:\n"
            if 'roe' in latest:
                report += f"   净资产收益率(ROE): {latest.get('roe', 0):.2f}%\n"
            if 'roa' in latest:
                report += f"   总资产收益率(ROA): {latest.get('roa', 0):.2f}%\n"
            if 'gross_margin' in latest:
                report += f"   毛利率: {latest.get('gross_margin', 0):.2f}%\n"
            if 'net_margin' in latest:
                report += f"   净利率: {latest.get('net_margin', 0):.2f}%\n"

            report += f"\n📝 共有 {len(financial_data)} 期财务数据\n"

            return report

        except Exception as e:
            logger.error(f"❌ 格式化财务数据失败: {e}")
            return f"❌ 格式化{symbol}财务数据失败: {e}"

    def _generate_fundamentals_analysis(self, symbol: str) -> str:
        """生成基本的基本面分析"""
        try:
            # 获取股票基本信息
            stock_info = self.get_stock_info(symbol)

            report = f"📊 {symbol} 基本面分析（生成）\n\n"
            report += f"📈 股票名称: {stock_info.get('name', '未知')}\n"
            report += f"🏢 所属行业: {stock_info.get('industry', '未知')}\n"
            report += f"📍 所属地区: {stock_info.get('area', '未知')}\n"
            report += f"📅 上市日期: {stock_info.get('list_date', '未知')}\n"
            report += f"🏛️ 交易所: {stock_info.get('exchange', '未知')}\n\n"

            report += "⚠️ 注意: 详细财务数据需要从数据源获取\n"
            report += "💡 建议: 启用MongoDB缓存以获取完整的财务数据\n"

            return report

        except Exception as e:
            logger.error(f"❌ 生成基本面分析失败: {e}")
            return f"❌ 生成{symbol}基本面分析失败: {e}"

    def _try_fallback_fundamentals(self, symbol: str) -> str:
        """基本面数据降级处理"""
        logger.error(f"🔄 {self.current_source.value}失败，尝试备用数据源获取基本面...")

        # 备用数据源优先级: Tushare > AKShare > 生成分析
        fallback_order = [
            ChinaDataSource.TUSHARE,
            ChinaDataSource.AKSHARE,
        ]

        for source in fallback_order:
            if source != self.current_source and source in self.available_sources:
                try:
                    logger.info(f"🔄 尝试备用数据源获取基本面: {source.value}")

                    # 直接调用具体的数据源方法，避免递归
                    if source == ChinaDataSource.TUSHARE:
                        result = self._get_tushare_fundamentals(symbol)
                    elif source == ChinaDataSource.AKSHARE:
                        result = self._get_akshare_fundamentals(symbol)
                    else:
                        continue

                    if result and "❌" not in result:
                        logger.info(f"✅ [数据来源: 备用数据源] 降级成功获取基本面: {source.value}")
                        return result
                    else:
                        logger.warning(f"⚠️ 备用数据源{source.value}返回错误结果")

                except Exception as e:
                    logger.error(f"❌ 备用数据源{source.value}异常: {e}")
                    continue

        # 所有数据源都失败，生成基本分析
        logger.warning(f"⚠️ [数据来源: 生成分析] 所有数据源失败，生成基本分析: {symbol}")
        return self._generate_fundamentals_analysis(symbol)

    def _get_mongodb_news(self, symbol: str, hours_back: int, limit: int) -> List[Dict[str, Any]]:
        """从MongoDB获取新闻数据"""
        try:
            from tradingagents.dataflows.enhanced_data_adapter import get_enhanced_data_adapter
            adapter = get_enhanced_data_adapter()

            # 从MongoDB获取新闻数据
            news_data = adapter.get_news_data(symbol, hours_back=hours_back, limit=limit)

            if news_data and len(news_data) > 0:
                logger.info(f"✅ [数据来源: MongoDB-新闻] 成功获取: {symbol or '市场新闻'} ({len(news_data)}条)")
                return news_data
            else:
                logger.warning(f"⚠️ [数据来源: MongoDB] 未找到新闻: {symbol or '市场新闻'}，降级到其他数据源")
                return self._try_fallback_news(symbol, hours_back, limit)

        except Exception as e:
            logger.error(f"❌ [数据来源: MongoDB] 获取新闻失败: {e}")
            return self._try_fallback_news(symbol, hours_back, limit)

    def _get_tushare_news(self, symbol: str, hours_back: int, limit: int) -> List[Dict[str, Any]]:
        """从Tushare获取新闻数据"""
        try:
            # Tushare新闻功能暂时不可用，返回空列表
            logger.warning(f"⚠️ [数据来源: Tushare] Tushare新闻功能暂时不可用")
            return []

        except Exception as e:
            logger.error(f"❌ [数据来源: Tushare] 获取新闻失败: {e}")
            return []

    def _get_akshare_news(self, symbol: str, hours_back: int, limit: int) -> List[Dict[str, Any]]:
        """从AKShare获取新闻数据"""
        try:
            # AKShare新闻功能暂时不可用，返回空列表
            logger.warning(f"⚠️ [数据来源: AKShare] AKShare新闻功能暂时不可用")
            return []

        except Exception as e:
            logger.error(f"❌ [数据来源: AKShare] 获取新闻失败: {e}")
            return []

    def _try_fallback_news(self, symbol: str, hours_back: int, limit: int) -> List[Dict[str, Any]]:
        """新闻数据降级处理"""
        logger.error(f"🔄 {self.current_source.value}失败，尝试备用数据源获取新闻...")

        # 备用数据源优先级: Tushare > AKShare
        fallback_order = [
            ChinaDataSource.TUSHARE,
            ChinaDataSource.AKSHARE,
        ]

        for source in fallback_order:
            if source != self.current_source and source in self.available_sources:
                try:
                    logger.info(f"🔄 尝试备用数据源获取新闻: {source.value}")

                    # 直接调用具体的数据源方法，避免递归
                    if source == ChinaDataSource.TUSHARE:
                        result = self._get_tushare_news(symbol, hours_back, limit)
                    elif source == ChinaDataSource.AKSHARE:
                        result = self._get_akshare_news(symbol, hours_back, limit)
                    else:
                        continue

                    if result and len(result) > 0:
                        logger.info(f"✅ [数据来源: 备用数据源] 降级成功获取新闻: {source.value}")
                        return result
                    else:
                        logger.warning(f"⚠️ 备用数据源{source.value}未返回新闻")

                except Exception as e:
                    logger.error(f"❌ 备用数据源{source.value}异常: {e}")
                    continue

        # 所有数据源都失败
        logger.warning(f"⚠️ [数据来源: 所有数据源失败] 无法获取新闻: {symbol or '市场新闻'}")
        return []


# 全局数据源管理器实例
_data_source_manager = None

def get_data_source_manager() -> DataSourceManager:
    """获取全局数据源管理器实例"""
    global _data_source_manager
    if _data_source_manager is None:
        _data_source_manager = DataSourceManager()
    return _data_source_manager


def get_china_stock_data_unified(symbol: str, start_date: str, end_date: str) -> str:
    """
    统一的中国股票数据获取接口
    自动使用配置的数据源，支持备用数据源

    Args:
        symbol: 股票代码
        start_date: 开始日期
        end_date: 结束日期

    Returns:
        str: 格式化的股票数据
    """
    from tradingagents.utils.logging_init import get_logger


    # 添加详细的股票代码追踪日志
    logger.info(f"🔍 [股票代码追踪] data_source_manager.get_china_stock_data_unified 接收到的股票代码: '{symbol}' (类型: {type(symbol)})")
    logger.info(f"🔍 [股票代码追踪] 股票代码长度: {len(str(symbol))}")
    logger.info(f"🔍 [股票代码追踪] 股票代码字符: {list(str(symbol))}")

    manager = get_data_source_manager()
    logger.info(f"🔍 [股票代码追踪] 调用 manager.get_stock_data，传入参数: symbol='{symbol}', start_date='{start_date}', end_date='{end_date}'")
    result = manager.get_stock_data(symbol, start_date, end_date)
    # 分析返回结果的详细信息
    if result:
        lines = result.split('\n')
        data_lines = [line for line in lines if '2025-' in line and symbol in line]
        logger.info(f"🔍 [股票代码追踪] 返回结果统计: 总行数={len(lines)}, 数据行数={len(data_lines)}, 结果长度={len(result)}字符")
        logger.info(f"🔍 [股票代码追踪] 返回结果前500字符: {result[:500]}")
        if len(data_lines) > 0:
            logger.info(f"🔍 [股票代码追踪] 数据行示例: 第1行='{data_lines[0][:100]}', 最后1行='{data_lines[-1][:100]}'")
    else:
        logger.info(f"🔍 [股票代码追踪] 返回结果: None")
    return result


def get_china_stock_info_unified(symbol: str) -> Dict:
    """
    统一的中国股票信息获取接口

    Args:
        symbol: 股票代码

    Returns:
        Dict: 股票基本信息
    """
    manager = get_data_source_manager()
    return manager.get_stock_info(symbol)


# 全局数据源管理器实例
_data_source_manager = None

def get_data_source_manager() -> DataSourceManager:
    """获取全局数据源管理器实例"""
    global _data_source_manager
    if _data_source_manager is None:
        _data_source_manager = DataSourceManager()
    return _data_source_manager
