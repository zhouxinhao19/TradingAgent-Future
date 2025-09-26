"""
Tushare data source adapter
"""
from typing import Optional, Dict
import logging
from datetime import datetime, timedelta
import pandas as pd

from .base import DataSourceAdapter

logger = logging.getLogger(__name__)


class TushareAdapter(DataSourceAdapter):
    """Tusharedata source adapter"""

    def __init__(self):
        self._provider = None
        self._initialize()

    def _initialize(self):
        """Initialize Tushare provider"""
        try:
            from tradingagents.dataflows.tushare_utils import get_tushare_provider
            self._provider = get_tushare_provider()
        except Exception as e:
            logger.warning(f"Failed to initialize Tushare provider: {e}")
            self._provider = None

    @property
    def name(self) -> str:
        return "tushare"

    @property
    def priority(self) -> int:
        return 1  # highest priority

    def is_available(self) -> bool:
        """Check whether Tushare is available"""
        return (
            self._provider is not None
            and getattr(self._provider, "connected", False)
            and self._provider.api is not None
        )

    def get_stock_list(self) -> Optional[pd.DataFrame]:
        """Get stock list"""
        if not self.is_available():
            return None
        try:
            df = self._provider.get_stock_list()
            if df is not None and not df.empty:
                logger.info(f"Tushare: Successfully fetched {len(df)} stocks")
                return df
        except Exception as e:
            logger.error(f"Tushare: Failed to fetch stock list: {e}")
        return None

    def get_daily_basic(self, trade_date: str) -> Optional[pd.DataFrame]:
        """Get daily basic financial data"""
        if not self.is_available():
            return None
        try:
            fields = "ts_code,total_mv,circ_mv,pe,pb,turnover_rate,volume_ratio,pe_ttm,pb_mrq"
            df = self._provider.api.daily_basic(trade_date=trade_date, fields=fields)
            if df is not None and not df.empty:
                logger.info(
                    f"Tushare: Successfully fetched daily data for {trade_date}, {len(df)} records"
                )
                return df
        except Exception as e:
            logger.error(f"Tushare: Failed to fetch daily data for {trade_date}: {e}")
        return None


    def get_realtime_quotes(self):
        """Get full-market near real-time quotes via Tushare rt_k fallback
        Returns dict keyed by 6-digit code: {'000001': {'close': ..., 'pct_chg': ..., 'amount': ...}}
        """
        if not self.is_available():
            return None
        try:
            df = self._provider.api.rt_k(ts_code='3*.SZ,6*.SH,0*.SZ,9*.BJ')  # type: ignore
            if df is None or getattr(df, 'empty', True):
                logger.warning('Tushare rt_k returned empty data')
                return None
            # Required columns
            if 'ts_code' not in df.columns or 'close' not in df.columns:
                logger.error(f'Tushare rt_k missing columns: {list(df.columns)}')
                return None
            result: Dict[str, Dict[str, Optional[float]]] = {}
            for _, row in df.iterrows():  # type: ignore
                ts_code = str(row.get('ts_code') or '')
                if not ts_code or '.' not in ts_code:
                    continue
                code6 = ts_code.split('.')[0].zfill(6)
                close = self._safe_float(row.get('close')) if hasattr(self, '_safe_float') else float(row.get('close')) if row.get('close') is not None else None
                pre_close = self._safe_float(row.get('pre_close')) if hasattr(self, '_safe_float') else (float(row.get('pre_close')) if row.get('pre_close') is not None else None)
                amount = self._safe_float(row.get('amount')) if hasattr(self, '_safe_float') else (float(row.get('amount')) if row.get('amount') is not None else None)
                # pct_chg may not be provided; compute if possible
                pct_chg = None
                if 'pct_chg' in df.columns and row.get('pct_chg') is not None:
                    try:
                        pct_chg = float(row.get('pct_chg'))
                    except Exception:
                        pct_chg = None
                if pct_chg is None and close is not None and pre_close is not None and pre_close not in (0, 0.0):
                    try:
                        pct_chg = (close / pre_close - 1.0) * 100.0
                    except Exception:
                        pct_chg = None
                # optional OHLC
                op = None
                hi = None
                lo = None
                try:
                    if 'open' in df.columns:
                        op = float(row.get('open')) if row.get('open') is not None else None
                    if 'high' in df.columns:
                        hi = float(row.get('high')) if row.get('high') is not None else None
                    if 'low' in df.columns:
                        lo = float(row.get('low')) if row.get('low') is not None else None
                except Exception:
                    op = op or None
                    hi = hi or None
                    lo = lo or None
                result[code6] = {'close': close, 'pct_chg': pct_chg, 'amount': amount, 'open': op, 'high': hi, 'low': lo, 'pre_close': pre_close}
            return result
        except Exception as e:
            logger.error(f'Failed to fetch realtime quotes from Tushare rt_k: {e}')
            return None

    def find_latest_trade_date(self) -> Optional[str]:
        """Find latest trade date by probing Tushare"""
        if not self.is_available():
            return None
        try:
            today = datetime.now()
            for delta in range(0, 10):  # up to 10 days back
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

