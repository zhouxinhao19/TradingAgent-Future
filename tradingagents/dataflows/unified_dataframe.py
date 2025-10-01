from __future__ import annotations

from typing import Optional, Tuple
import pandas as pd
import numpy as np

from tradingagents.utils.logging_manager import get_logger
logger = get_logger('agents')

# Data source manager (priority and availability)
from .data_source_manager import get_data_source_manager

# Providers / adapters
try:
    from .tushare_adapter import get_tushare_adapter
    TUSHARE_ADAPTER_AVAILABLE = True
except Exception:
    TUSHARE_ADAPTER_AVAILABLE = False

try:
    from .providers.china.akshare import get_akshare_provider
    AKSHARE_PROVIDER_AVAILABLE = True
except Exception:
    AKSHARE_PROVIDER_AVAILABLE = False

try:
    from .baostock_utils import get_baostock_provider
    BAOSTOCK_PROVIDER_AVAILABLE = True
except Exception:
    BAOSTOCK_PROVIDER_AVAILABLE = False


def _std_lower_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Standardize OHLCV columns to lower snake_case: open, high, low, close, vol, amount, date(index optional)."""
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    colmap = {
        # English
        'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close',
        'Volume': 'vol', 'Amount': 'amount', 'symbol': 'code', 'Symbol': 'code',
        # Already lower
        'open': 'open', 'high': 'high', 'low': 'low', 'close': 'close',
        'vol': 'vol', 'volume': 'vol', 'amount': 'amount', 'code': 'code',
        'date': 'date', 'trade_date': 'date',
        # Chinese (AKShare common)
        '日期': 'date', '开盘': 'open', '最高': 'high', '最低': 'low', '收盘': 'close',
        '成交量': 'vol', '成交额': 'amount', '涨跌幅': 'pct_change', '涨跌额': 'change',
    }
    out = out.rename(columns={c: colmap.get(c, c) for c in out.columns})

    # Ensure datetime sort by date if exists
    if 'date' in out.columns:
        try:
            out['date'] = pd.to_datetime(out['date'])
            out = out.sort_values('date')
        except Exception:
            pass

    # Derive pct_change if missing
    if 'pct_change' not in out.columns and 'close' in out.columns:
        out['pct_change'] = out['close'].pct_change() * 100.0
    return out


def _try_tushare(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    if not TUSHARE_ADAPTER_AVAILABLE:
        return pd.DataFrame()
    try:
        adapter = get_tushare_adapter()
        df = adapter.get_stock_data(symbol, start_date, end_date, data_type="daily")
        return _std_lower_cols(df)
    except Exception as e:
        logger.warning(f"[unified_df] Tushare adapter failed: {e}")
        return pd.DataFrame()


def _try_akshare(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    if not AKSHARE_PROVIDER_AVAILABLE:
        return pd.DataFrame()
    try:
        provider = get_akshare_provider()
        df = provider.get_stock_data(symbol, start_date, end_date)
        return _std_lower_cols(df)
    except Exception as e:
        logger.warning(f"[unified_df] AKShare provider failed: {e}")
        return pd.DataFrame()


def _try_baostock(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    if not BAOSTOCK_PROVIDER_AVAILABLE:
        return pd.DataFrame()
    try:
        provider = get_baostock_provider()
        df = provider.get_stock_data(symbol, start_date, end_date)
        return _std_lower_cols(df)
    except Exception as e:
        logger.warning(f"[unified_df] BaoStock provider failed: {e}")
        return pd.DataFrame()


def get_china_daily_df_unified(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    统一返回 A股日线 DataFrame（多数据源按优先级，自动降级）。
    列标准：open, high, low, close, vol, amount, pct_change[, date, code]
    """
    dsm = get_data_source_manager()

    # 优先当前选择的数据源，再按既定 fallback 顺序尝试
    # data_source_manager 对字符串接口的优先顺序已定义，这里等价实现为具体 DF 尝试
    order = []
    try:
        # 获取当前&可用源；构造一个以当前为首的尝试序列
        current = dsm.current_source
        available = getattr(dsm, 'available_sources', [])
        if current:
            order.append(current.value.lower())
        for s in available:
            val = getattr(s, 'value', str(s)).lower()
            if val not in order:
                order.append(val)
    except Exception:
        # 兜底顺序（与文档一致，可根据环境变量改变默认）
        order = ["tushare", "akshare", "baostock", "tdx"]

    # 尝试依次数据源
    for src in order:
        if src == "tushare":
            df = _try_tushare(symbol, start_date, end_date)
        elif src == "akshare":
            df = _try_akshare(symbol, start_date, end_date)
        elif src == "baostock":
            df = _try_baostock(symbol, start_date, end_date)
        else:
            df = pd.DataFrame()
        if df is not None and not df.empty:
            logger.info(f"[unified_df] got data from {src}: shape={getattr(df,'shape',None)}")
            return df

    # 兜底：再尝试一个固定顺序（去掉tdx）
    for src in ["tushare", "akshare", "baostock"]:
        df = pd.DataFrame()
        if src == "tushare":
            df = _try_tushare(symbol, start_date, end_date)
        elif src == "akshare":
            df = _try_akshare(symbol, start_date, end_date)
        elif src == "baostock":
            df = _try_baostock(symbol, start_date, end_date)
        if df is not None and not df.empty:
            logger.info(f"[unified_df] fallback got data from {src}: shape={getattr(df,'shape',None)}")
            return df

    logger.error(f"[unified_df] all sources failed for {symbol}")
    return pd.DataFrame()

