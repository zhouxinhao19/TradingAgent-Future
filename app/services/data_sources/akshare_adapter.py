"""
AKShare data source adapter
"""
from typing import Optional, Dict
import logging
from datetime import datetime, timedelta
import pandas as pd

from .base import DataSourceAdapter

logger = logging.getLogger(__name__)


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
            import akshare as ak  # noqa: F401
            return True
        except ImportError:
            return False

    def get_stock_list(self) -> Optional[pd.DataFrame]:
        """获取股票列表（基于已知规则生成，避免外部接口不稳定）"""
        if not self.is_available():
            return None
        try:
            import akshare as ak  # noqa: F401
            logger.info("AKShare: Generating stock list from known patterns...")

            stock_data = []
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
            # 科创板 688001-688099（前100个）
            for i in range(688001, 688100):
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
        """获取每日基础财务数据（快速版）"""
        if not self.is_available():
            return None
        try:
            import akshare as ak  # noqa: F401
            logger.info(f"AKShare: Attempting to get basic financial data for {trade_date}")

            stock_df = self.get_stock_list()
            if stock_df is None or stock_df.empty:
                logger.warning("AKShare: No stock list available")
                return None

            max_stocks = 10
            stock_list = stock_df.head(max_stocks)

            basic_data = []
            processed_count = 0
            import time
            start_time = time.time()
            timeout_seconds = 30

            for _, stock in stock_list.iterrows():
                if time.time() - start_time > timeout_seconds:
                    logger.warning(f"AKShare: Timeout reached, processed {processed_count} stocks")
                    break
                try:
                    symbol = stock.get('symbol', '')
                    name = stock.get('name', '')
                    ts_code = stock.get('ts_code', '')
                    if not symbol:
                        continue
                    info_data = ak.stock_individual_info_em(symbol=symbol)
                    if info_data is not None and not info_data.empty:
                        info_dict = {}
                        for _, row in info_data.iterrows():
                            item = row.get('item', '')
                            value = row.get('value', '')
                            info_dict[item] = value
                        latest_price = self._safe_float(info_dict.get('最新', 0))
                        total_mv = self._safe_float(info_dict.get('总市值', 0))
                        basic_data.append({
                            'ts_code': ts_code,
                            'trade_date': trade_date,
                            'name': name,
                            'close': latest_price,
                            'total_mv': total_mv,
                            'turnover_rate': None,
                            'pe': None,
                            'pb': None,
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
        try:
            if value is None or value == '' or value == 'None':
                return None
            return float(value)
        except (ValueError, TypeError):
            return None


    def get_realtime_quotes(self):
        """获取全市场实时快照，返回以6位代码为键的字典"""
        if not self.is_available():
            return None
        try:
            import akshare as ak  # type: ignore
            df = ak.stock_zh_a_spot_em()
            if df is None or getattr(df, "empty", True):
                logger.warning("AKShare spot 返回空数据")
                return None
            # 列名兼容
            code_col = next((c for c in ["代码", "代码code", "symbol", "股票代码"] if c in df.columns), None)
            price_col = next((c for c in ["最新价", "现价", "最新价(元)", "price", "最新"] if c in df.columns), None)
            pct_col = next((c for c in ["涨跌幅", "涨跌幅(%)", "涨幅", "pct_chg"] if c in df.columns), None)
            amount_col = next((c for c in ["成交额", "成交额(元)", "amount", "成交额(万元)"] if c in df.columns), None)
            open_col = next((c for c in ["今开", "开盘", "open", "今开(元)"] if c in df.columns), None)
            high_col = next((c for c in ["最高", "high"] if c in df.columns), None)
            low_col = next((c for c in ["最低", "low"] if c in df.columns), None)
            pre_close_col = next((c for c in ["昨收", "昨收(元)", "pre_close", "昨收价"] if c in df.columns), None)
            if not code_col or not price_col:
                logger.error(f"AKShare spot 缺少必要列: code={code_col}, price={price_col}")
                return None
            result: Dict[str, Dict[str, Optional[float]]] = {}
            for _, row in df.iterrows():  # type: ignore
                code_raw = row.get(code_col)
                if not code_raw:
                    continue
                code = str(code_raw).zfill(6)
                close = self._safe_float(row.get(price_col))
                pct = self._safe_float(row.get(pct_col)) if pct_col else None
                amt = self._safe_float(row.get(amount_col)) if amount_col else None
                op = self._safe_float(row.get(open_col)) if open_col else None
                hi = self._safe_float(row.get(high_col)) if high_col else None
                lo = self._safe_float(row.get(low_col)) if low_col else None
                pre = self._safe_float(row.get(pre_close_col)) if pre_close_col else None
                result[code] = {"close": close, "pct_chg": pct, "amount": amt, "open": op, "high": hi, "low": lo, "pre_close": pre}
            return result
        except Exception as e:
            logger.error(f"获取AKShare实时快照失败: {e}")
            return None

    def find_latest_trade_date(self) -> Optional[str]:
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        logger.info(f"AKShare: Using yesterday as trade date: {yesterday}")
        return yesterday

