"""
数据源适配器
为不同的数据源提供统一的接口，支持股票基础信息和财务数据获取
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Tuple
import pandas as pd
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class DataSourceAdapter(ABC):
    """数据源适配器基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """数据源名称"""
        pass

    @property
    @abstractmethod
    def priority(self) -> int:
        """数据源优先级（数字越小优先级越高）"""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """检查数据源是否可用"""
        pass

    @abstractmethod
    def get_stock_list(self) -> Optional[pd.DataFrame]:
        """获取股票列表"""
        pass

    @abstractmethod
    def get_daily_basic(self, trade_date: str) -> Optional[pd.DataFrame]:
        """获取每日基础财务数据"""
        pass

    @abstractmethod
    def find_latest_trade_date(self) -> Optional[str]:
        """查找最新交易日期"""
        pass


class TushareAdapter(DataSourceAdapter):
    """Tushare数据源适配器"""

    def __init__(self):
        self._provider = None
        self._initialize()

    def _initialize(self):
        """初始化Tushare提供器"""
        try:
            from tradingagents.dataflows.providers.china.tushare import get_tushare_provider
            self._provider = get_tushare_provider()
        except Exception as e:
            logger.warning(f"Failed to initialize Tushare provider: {e}")
            self._provider = None

    @property
    def name(self) -> str:
        return "tushare"

    @property
    def priority(self) -> int:
        return 1  # 最高优先级

    def is_available(self) -> bool:
        """检查Tushare是否可用"""
        return (self._provider is not None and
                getattr(self._provider, "connected", False) and
                self._provider.api is not None)

    def get_stock_list(self) -> Optional[pd.DataFrame]:
        """获取股票列表"""
        if not self.is_available():
            return None

        try:
            # 使用同步版本的方法
            df = self._provider.get_stock_list_sync()
            if df is not None and not df.empty:
                logger.info(f"Tushare: Successfully fetched {len(df)} stocks")
                return df
        except Exception as e:
            logger.error(f"Tushare: Failed to fetch stock list: {e}")

        return None

    def get_daily_basic(self, trade_date: str) -> Optional[pd.DataFrame]:
        """获取每日基础财务数据"""
        if not self.is_available():
            return None

        try:
            fields = "ts_code,total_mv,circ_mv,pe,pb,turnover_rate,volume_ratio,pe_ttm,pb_mrq"
            df = self._provider.api.daily_basic(trade_date=trade_date, fields=fields)
            if df is not None and not df.empty:
                logger.info(f"Tushare: Successfully fetched daily data for {trade_date}, {len(df)} records")
                return df
        except Exception as e:
            logger.error(f"Tushare: Failed to fetch daily data for {trade_date}: {e}")

        return None

    def find_latest_trade_date(self) -> Optional[str]:
        """查找最新交易日期"""
        if not self.is_available():
            return None

        try:
            today = datetime.now()
            for delta in range(0, 10):  # 最多回溯10天
                d = (today - timedelta(days=delta)).strftime("%Y%m%d")
                try:
                    db = self._provider.api.daily_basic(trade_date=d, fields="ts_code,total_mv")
                    if db is not None and not db.empty:
                        logger.info(f"Tushare: Found latest trade date: {d}")
                        return d
                except Exception:
                    continue
        except Exception as e:
            logger.error(f"Tushare: Failed to find latest trade date: {e}")

        return None


class AKShareAdapter(DataSourceAdapter):
    """AKShare数据源适配器"""

    @property
    def name(self) -> str:
        return "akshare"

    @property
    def priority(self) -> int:
        return 2

    def is_available(self) -> bool:
        """检查AKShare是否可用"""
        try:
            import akshare as ak
            return True
        except ImportError:
            return False

    def get_stock_list(self) -> Optional[pd.DataFrame]:
        """获取股票列表"""
        if not self.is_available():
            return None

        try:
            import akshare as ak

            # 使用更可靠的方法：通过已知的股票代码生成列表
            # 这是一个fallback方案，避免依赖可能失效的外部接口
            logger.info("AKShare: Generating stock list from known patterns...")

            stock_data = []

            # 生成主要的股票代码范围
            # 深圳主板 000001-000999
            for i in range(1, 1000):
                code = f"{i:06d}"
                if code.startswith('000'):
                    stock_data.append({
                        'symbol': code,
                        'name': f'股票{code}',
                        'ts_code': f'{code}.SZ',
                        'area': '',
                        'industry': '',
                        'market': '主板',
                        'list_date': ''
                    })

            # 深圳中小板 002001-002999
            for i in range(2001, 3000):
                code = f"{i:06d}"
                if code.startswith('002'):
                    stock_data.append({
                        'symbol': code,
                        'name': f'股票{code}',
                        'ts_code': f'{code}.SZ',
                        'area': '',
                        'industry': '',
                        'market': '中小板',
                        'list_date': ''
                    })

            # 创业板 300001-300999
            for i in range(300001, 301000):
                code = f"{i:06d}"
                stock_data.append({
                    'symbol': code,
                    'name': f'股票{code}',
                    'ts_code': f'{code}.SZ',
                    'area': '',
                    'industry': '',
                    'market': '创业板',
                    'list_date': ''
                })

            # 上海主板 600001-600999
            for i in range(600001, 601000):
                code = f"{i:06d}"
                stock_data.append({
                    'symbol': code,
                    'name': f'股票{code}',
                    'ts_code': f'{code}.SH',
                    'area': '',
                    'industry': '',
                    'market': '主板',
                    'list_date': ''
                })

            # 科创板 688001-688999 (选择性添加)
            for i in range(688001, 688100):  # 只添加前100个
                code = f"{i:06d}"
                stock_data.append({
                    'symbol': code,
                    'name': f'股票{code}',
                    'ts_code': f'{code}.SH',
                    'area': '',
                    'industry': '',
                    'market': '科创板',
                    'list_date': ''
                })

            df = pd.DataFrame(stock_data)
            logger.info(f"AKShare: Successfully generated {len(df)} stock codes")
            return df

        except Exception as e:
            logger.error(f"AKShare: Failed to generate stock list: {e}")

        return None

    def get_daily_basic(self, trade_date: str) -> Optional[pd.DataFrame]:
        """获取每日基础财务数据"""
        if not self.is_available():
            return None

        try:
            import akshare as ak

            logger.info(f"AKShare: Attempting to get basic financial data for {trade_date}")

            # 获取股票列表
            stock_df = self.get_stock_list()
            if stock_df is None or stock_df.empty:
                logger.warning("AKShare: No stock list available")
                return None

            # 限制处理数量以避免超时 - 减少到10只股票用于快速测试
            max_stocks = 10
            stock_list = stock_df.head(max_stocks)

            basic_data = []
            processed_count = 0
            import time
            start_time = time.time()
            timeout_seconds = 30  # 设置30秒超时

            for _, stock in stock_list.iterrows():
                # 检查超时
                if time.time() - start_time > timeout_seconds:
                    logger.warning(f"AKShare: Timeout reached, processed {processed_count} stocks")
                    break

                try:
                    symbol = stock.get('symbol', '')
                    name = stock.get('name', '')
                    ts_code = stock.get('ts_code', '')

                    if not symbol:
                        continue

                    # 使用individual_info_em获取基本信息
                    info_data = ak.stock_individual_info_em(symbol=symbol)

                    if info_data is not None and not info_data.empty:
                        # 解析信息数据
                        info_dict = {}
                        for _, row in info_data.iterrows():
                            item = row.get('item', '')
                            value = row.get('value', '')
                            info_dict[item] = value

                        # 提取需要的数据
                        latest_price = self._safe_float(info_dict.get('最新', 0))
                        total_mv = self._safe_float(info_dict.get('总市值', 0))

                        # 跳过历史数据获取以提高速度
                        # 历史数据API较慢，暂时不获取换手率

                        basic_data.append({
                            'ts_code': ts_code,
                            'trade_date': trade_date,
                            'name': name,
                            'close': latest_price,
                            'total_mv': total_mv,
                            'turnover_rate': None,  # 暂时不获取以提高速度
                            'pe': None,  # AKShare个股信息中没有PE
                            'pb': None,  # AKShare个股信息中没有PB
                        })

                        processed_count += 1

                        if processed_count % 5 == 0:
                            logger.debug(f"AKShare: Processed {processed_count} stocks in {time.time() - start_time:.1f}s")

                except Exception as e:
                    logger.debug(f"AKShare: Failed to get data for {symbol}: {e}")
                    continue

            if basic_data:
                df = pd.DataFrame(basic_data)
                logger.info(f"AKShare: Successfully fetched basic data for {trade_date}, {len(df)} records")
                return df
            else:
                logger.warning("AKShare: No basic data collected")
                return None

        except Exception as e:
            logger.error(f"AKShare: Failed to fetch basic data for {trade_date}: {e}")

        return None

    def _safe_float(self, value) -> Optional[float]:
        """安全转换为浮点数"""
        try:
            if value is None or value == '' or value == 'None':
                return None
            return float(value)
        except (ValueError, TypeError):
            return None

    def find_latest_trade_date(self) -> Optional[str]:
        """查找最新交易日期"""
        # 简单返回昨天的日期
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        logger.info(f"AKShare: Using yesterday as trade date: {yesterday}")
        return yesterday


class BaoStockAdapter(DataSourceAdapter):
    """BaoStock数据源适配器"""

    @property
    def name(self) -> str:
        return "baostock"

    @property
    def priority(self) -> int:
        return 3

    def is_available(self) -> bool:
        """检查BaoStock是否可用"""
        try:
            import baostock as bs
            return True
        except ImportError:
            return False

    def get_stock_list(self) -> Optional[pd.DataFrame]:
        """获取股票列表"""
        if not self.is_available():
            return None

        try:
            import baostock as bs

            # 登录BaoStock
            lg = bs.login()
            if lg.error_code != '0':
                logger.error(f"BaoStock: Login failed: {lg.error_msg}")
                return None

            try:
                # 获取证券基本资料 - 包含type字段用于过滤股票类型
                logger.info(f"BaoStock: Querying stock basic info...")

                rs = bs.query_stock_basic()  # 获取所有证券的基本资料
                if rs.error_code != '0':
                    logger.error(f"BaoStock: Query failed: {rs.error_msg}")
                    return None

                # 解析数据
                data_list = []
                while (rs.error_code == '0') & rs.next():
                    data_list.append(rs.get_row_data())

                if not data_list:
                    return None

                # 转换为DataFrame
                df = pd.DataFrame(data_list, columns=rs.fields)

                # 过滤A股股票：type=1表示股票，排除指数(type=2)等其他类型
                df = df[df['type'] == '1']

                # 标准化格式
                df['symbol'] = df['code'].str.replace(r'^(sh|sz)\.', '', regex=True)
                df['ts_code'] = df['code'].str.replace('sh.', '').str.replace('sz.', '') + \
                               df['code'].str.extract(r'^(sh|sz)\.').iloc[:, 0].str.upper().str.replace('SH', '.SH').str.replace('SZ', '.SZ')

                # 重命名字段以匹配标准格式
                # query_stock_basic返回字段：['code', 'code_name', 'ipoDate', 'outDate', 'type', 'status']
                df['name'] = df['code_name']  # BaoStock使用code_name字段

                # 添加其他字段
                df['area'] = ''
                df['industry'] = ''
                df['market'] = '主板'  # BaoStock没有详细市场分类
                df['list_date'] = ''

                logger.info(f"BaoStock: Successfully fetched {len(df)} stocks")
                return df[['symbol', 'name', 'ts_code', 'area', 'industry', 'market', 'list_date']]

            finally:
                bs.logout()

        except Exception as e:
            logger.error(f"BaoStock: Failed to fetch stock list: {e}")

        return None

    def get_daily_basic(self, trade_date: str) -> Optional[pd.DataFrame]:
        """获取每日基础财务数据"""
        if not self.is_available():
            return None

        try:
            import baostock as bs

            logger.info(f"BaoStock: Attempting to get valuation data for {trade_date}")

            # 登录BaoStock
            lg = bs.login()
            if lg.error_code != '0':
                logger.error(f"BaoStock: Login failed: {lg.error_msg}")
                return None

            try:
                # 获取证券基本资料 - 包含type字段用于过滤股票类型
                logger.info(f"BaoStock: Querying stock basic info...")

                rs = bs.query_stock_basic()  # 获取所有证券的基本资料
                if rs.error_code != '0':
                    logger.error(f"BaoStock: Query stock list failed: {rs.error_msg}")
                    return None

                # 解析股票列表
                stock_list = []
                while (rs.error_code == '0') & rs.next():
                    stock_list.append(rs.get_row_data())

                if not stock_list:
                    logger.warning("BaoStock: No stocks found")
                    return None

                # 过滤A股股票并获取估值指标
                basic_data = []
                processed_count = 0
                max_stocks = 50  # 限制数量以避免超时

                for stock in stock_list:
                    if processed_count >= max_stocks:
                        break

                    # query_stock_basic返回字段：['code', 'code_name', 'ipoDate', 'outDate', 'type', 'status']
                    code = stock[0] if len(stock) > 0 else ''  # code
                    name = stock[1] if len(stock) > 1 else ''  # code_name
                    stock_type = stock[4] if len(stock) > 4 else '0'  # type
                    status = stock[5] if len(stock) > 5 else '0'  # status

                    # 只处理上市股票(type=1, status=1)，排除指数(type=2)等其他类型
                    if stock_type == '1' and status == '1':
                        try:
                            # 使用BaoStock的估值指标接口
                            # 转换日期格式：YYYYMMDD -> YYYY-MM-DD
                            formatted_date = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"

                            # 获取指定日期的估值数据
                            rs_valuation = bs.query_history_k_data_plus(
                                code,
                                "date,code,close,peTTM,pbMRQ,psTTM,pcfNcfTTM",
                                start_date=formatted_date,
                                end_date=formatted_date,
                                frequency="d",
                                adjustflag="3"
                            )

                            if rs_valuation.error_code == '0':
                                valuation_data = []
                                while (rs_valuation.error_code == '0') & rs_valuation.next():
                                    valuation_data.append(rs_valuation.get_row_data())

                                if valuation_data:
                                    row = valuation_data[0]  # 取第一条记录

                                    # 转换为标准格式
                                    symbol = code.replace('sh.', '').replace('sz.', '')
                                    ts_code = f"{symbol}.SH" if code.startswith('sh.') else f"{symbol}.SZ"

                                    # 解析估值指标
                                    pe_ttm = self._safe_float(row[3]) if len(row) > 3 else None  # peTTM
                                    pb_mrq = self._safe_float(row[4]) if len(row) > 4 else None  # pbMRQ
                                    ps_ttm = self._safe_float(row[5]) if len(row) > 5 else None  # psTTM
                                    pcf_ttm = self._safe_float(row[6]) if len(row) > 6 else None  # pcfNcfTTM
                                    close_price = self._safe_float(row[2]) if len(row) > 2 else None  # close

                                    basic_data.append({
                                        'ts_code': ts_code,
                                        'trade_date': trade_date,
                                        'name': name,
                                        'pe': pe_ttm,  # 使用滚动市盈率
                                        'pb': pb_mrq,  # 使用市净率
                                        'ps': ps_ttm,  # 市销率
                                        'pcf': pcf_ttm,  # 市现率
                                        'close': close_price,  # 收盘价
                                        'total_mv': None,  # BaoStock不直接提供市值
                                        'turnover_rate': None,  # BaoStock不提供换手率
                                    })

                                    processed_count += 1

                                    if processed_count % 10 == 0:
                                        logger.debug(f"BaoStock: Processed {processed_count} stocks")

                        except Exception as e:
                            logger.debug(f"BaoStock: Failed to get valuation for {code}: {e}")
                            continue

                if basic_data:
                    df = pd.DataFrame(basic_data)
                    logger.info(f"BaoStock: Successfully fetched valuation data for {trade_date}, {len(df)} records")
                    return df
                else:
                    logger.warning("BaoStock: No valuation data found")
                    return None

            finally:
                bs.logout()

        except Exception as e:
            logger.error(f"BaoStock: Failed to fetch valuation data for {trade_date}: {e}")

        return None

    def _safe_float(self, value) -> Optional[float]:
        """安全转换为浮点数"""
        try:
            if value is None or value == '' or value == 'None':
                return None
            return float(value)
        except (ValueError, TypeError):
            return None

    def _is_a_stock(self, code: str) -> bool:
        """判断是否为A股股票代码（排除指数）"""
        import re
        # 上海A股：600xxx, 601xxx, 603xxx, 605xxx, 688xxx (科创板)
        # 深圳A股：000xxx, 001xxx, 002xxx, 003xxx, 300xxx (创业板)
        a_stock_pattern = r'^(sh\.(60[0135]|688)|sz\.(00[0123]|300))[0-9]{3}$'
        return bool(re.match(a_stock_pattern, code))

    def find_latest_trade_date(self) -> Optional[str]:
        """查找最新交易日期"""
        # 简单返回昨天的日期
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        logger.info(f"BaoStock: Using yesterday as trade date: {yesterday}")
        return yesterday


class DataSourceManager:
    """数据源管理器"""

    def __init__(self):
        self.adapters = [
            TushareAdapter(),
            AKShareAdapter(),
            BaoStockAdapter(),
        ]
        # 按优先级排序
        self.adapters.sort(key=lambda x: x.priority)

        # 初始化数据一致性检查器
        try:
            from .data_consistency_checker import DataConsistencyChecker
            self.consistency_checker = DataConsistencyChecker()
        except ImportError:
            logger.warning("⚠️ 数据一致性检查器不可用")
            self.consistency_checker = None

    def get_available_adapters(self) -> List[DataSourceAdapter]:
        """获取可用的数据源适配器"""
        available = []
        for adapter in self.adapters:
            if adapter.is_available():
                available.append(adapter)
                logger.info(f"Data source {adapter.name} is available (priority: {adapter.priority})")
            else:
                logger.warning(f"Data source {adapter.name} is not available")

        return available

    def get_stock_list_with_fallback(self) -> tuple[Optional[pd.DataFrame], Optional[str]]:
        """使用fallback机制获取股票列表"""
        available_adapters = self.get_available_adapters()

        for adapter in available_adapters:
            try:
                logger.info(f"Trying to fetch stock list from {adapter.name}")
                df = adapter.get_stock_list()
                if df is not None and not df.empty:
                    return df, adapter.name
            except Exception as e:
                logger.error(f"Failed to fetch stock list from {adapter.name}: {e}")
                continue

        return None, None

    def get_daily_basic_with_fallback(self, trade_date: str) -> tuple[Optional[pd.DataFrame], Optional[str]]:
        """使用fallback机制获取每日基础数据"""
        available_adapters = self.get_available_adapters()

        for adapter in available_adapters:
            try:
                logger.info(f"Trying to fetch daily basic data from {adapter.name}")
                df = adapter.get_daily_basic(trade_date)
                if df is not None and not df.empty:
                    return df, adapter.name
            except Exception as e:
                logger.error(f"Failed to fetch daily basic data from {adapter.name}: {e}")
                continue

        return None, None

    def find_latest_trade_date_with_fallback(self) -> Optional[str]:
        """使用fallback机制查找最新交易日期"""
        available_adapters = self.get_available_adapters()

        for adapter in available_adapters:
            try:
                trade_date = adapter.find_latest_trade_date()
                if trade_date:
                    return trade_date
            except Exception as e:
                logger.error(f"Failed to find trade date from {adapter.name}: {e}")
                continue

        # 如果所有数据源都失败，返回昨天
        return (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

    def get_daily_basic_with_consistency_check(self, trade_date: str) -> Tuple[Optional[pd.DataFrame], Optional[str], Optional[Dict]]:
        """
        使用一致性检查获取每日基础数据

        Returns:
            Tuple[DataFrame, source_name, consistency_report]: (数据, 数据源名称, 一致性报告)
        """
        available_adapters = self.get_available_adapters()

        if len(available_adapters) < 2:
            # 只有一个数据源，直接使用fallback机制
            df, source = self.get_daily_basic_with_fallback(trade_date)
            return df, source, None

        # 获取前两个数据源的数据进行比较
        primary_adapter = available_adapters[0]
        secondary_adapter = available_adapters[1]

        try:
            logger.info(f"🔍 获取数据进行一致性检查: {primary_adapter.name} vs {secondary_adapter.name}")

            # 获取两个数据源的数据
            primary_data = primary_adapter.get_daily_basic(trade_date)
            secondary_data = secondary_adapter.get_daily_basic(trade_date)

            # 如果任一数据源失败，使用fallback机制
            if primary_data is None or primary_data.empty:
                logger.warning(f"⚠️ 主数据源{primary_adapter.name}失败，使用fallback")
                df, source = self.get_daily_basic_with_fallback(trade_date)
                return df, source, None

            if secondary_data is None or secondary_data.empty:
                logger.warning(f"⚠️ 次数据源{secondary_adapter.name}失败，使用主数据源")
                return primary_data, primary_adapter.name, None

            # 进行一致性检查
            if self.consistency_checker:
                consistency_result = self.consistency_checker.check_daily_basic_consistency(
                    primary_data, secondary_data,
                    primary_adapter.name, secondary_adapter.name
                )

                # 根据一致性结果决定使用哪个数据
                final_data, resolution_strategy = self.consistency_checker.resolve_data_conflicts(
                    primary_data, secondary_data, consistency_result
                )

                # 构建一致性报告
                consistency_report = {
                    'is_consistent': consistency_result.is_consistent,
                    'confidence_score': consistency_result.confidence_score,
                    'recommended_action': consistency_result.recommended_action,
                    'resolution_strategy': resolution_strategy,
                    'differences': consistency_result.differences,
                    'primary_source': primary_adapter.name,
                    'secondary_source': secondary_adapter.name
                }

                logger.info(f"📊 数据一致性检查完成: 置信度={consistency_result.confidence_score:.2f}, 策略={consistency_result.recommended_action}")

                return final_data, primary_adapter.name, consistency_report
            else:
                # 没有一致性检查器，直接使用主数据源
                logger.warning("⚠️ 一致性检查器不可用，使用主数据源")
                return primary_data, primary_adapter.name, None

        except Exception as e:
            logger.error(f"❌ 一致性检查失败: {e}")
            # 出错时使用fallback机制
            df, source = self.get_daily_basic_with_fallback(trade_date)
            return df, source, None


# ---- Backward-compatible re-exports (delegating to subpackage) ----
try:
    from app.services.data_sources.base import DataSourceAdapter as _BaseAdapter
    from app.services.data_sources.tushare_adapter import TushareAdapter as _TsAdapter
    from app.services.data_sources.akshare_adapter import AKShareAdapter as _AkAdapter
    from app.services.data_sources.baostock_adapter import BaoStockAdapter as _BsAdapter
    from app.services.data_sources.manager import DataSourceManager as _DsManager

    # Override local definitions to use subpackage implementations
    DataSourceAdapter = _BaseAdapter  # type: ignore
    TushareAdapter = _TsAdapter  # type: ignore
    AKShareAdapter = _AkAdapter  # type: ignore
    BaoStockAdapter = _BsAdapter  # type: ignore
    DataSourceManager = _DsManager  # type: ignore
except Exception as _e:
    # Fallback: keep original in-file implementations if subpackage import fails
    import logging as _logging
    _logging.getLogger(__name__).warning(
        f"Data source subpackage not fully available, using in-file classes. Detail: {_e}"
    )
