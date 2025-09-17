"""
Tushare data source adapter
"""
from typing import Optional
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

