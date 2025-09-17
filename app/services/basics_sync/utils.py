"""
与 Tushare 相关的阻塞式工具函数：
- fetch_stock_basic_df：获取股票列表（确保 Tushare 已连接）
- find_latest_trade_date：探测最近可用交易日（YYYYMMDD）
- fetch_daily_basic_mv_map：根据交易日获取日度基础指标映射（市值/估值/交易）
"""
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Dict


def fetch_stock_basic_df():
    """
    从 Tushare 获取股票基础列表，要求已正确配置并连接。
    依赖环境变量：TUSHARE_ENABLED=true 且 .env 中提供 TUSHARE_TOKEN。
    """
    from tradingagents.dataflows.tushare_utils import get_tushare_provider

    provider = get_tushare_provider()
    if not getattr(provider, "connected", False):
        raise RuntimeError(
            "Tushare not connected. Set TUSHARE_ENABLED=true and TUSHARE_TOKEN in .env"
        )
    return provider.get_stock_list()


def find_latest_trade_date() -> str:
    """
    探测最近可用的交易日（YYYYMMDD）。
    - 从今天起回溯最多 5 天；
    - 如都不可用，回退为昨天日期。
    """
    from tradingagents.dataflows.tushare_utils import get_tushare_provider

    provider = get_tushare_provider()
    api = provider.api
    if api is None:
        raise RuntimeError("Tushare API unavailable")

    today = datetime.now()
    for delta in range(0, 6):
        d = (today - timedelta(days=delta)).strftime("%Y%m%d")
        try:
            db = api.daily_basic(trade_date=d, fields="ts_code,total_mv")
            if db is not None and not db.empty:
                return d
        except Exception:
            continue
    return (today - timedelta(days=1)).strftime("%Y%m%d")


def fetch_daily_basic_mv_map(trade_date: str) -> Dict[str, Dict[str, float]]:
    """
    根据交易日获取日度基础指标映射。
    覆盖字段：total_mv/circ_mv/pe/pb/turnover_rate/volume_ratio/pe_ttm/pb_mrq
    """
    from tradingagents.dataflows.tushare_utils import get_tushare_provider

    provider = get_tushare_provider()
    api = provider.api
    if api is None:
        raise RuntimeError("Tushare API unavailable")

    fields = "ts_code,total_mv,circ_mv,pe,pb,turnover_rate,volume_ratio,pe_ttm,pb_mrq"
    db = api.daily_basic(trade_date=trade_date, fields=fields)

    data_map: Dict[str, Dict[str, float]] = {}
    if db is not None and not db.empty:
        for _, row in db.iterrows():  # type: ignore
            ts_code = row.get("ts_code")
            if ts_code is not None:
                try:
                    metrics = {}
                    for field in [
                        "total_mv",
                        "circ_mv",
                        "pe",
                        "pb",
                        "turnover_rate",
                        "volume_ratio",
                        "pe_ttm",
                        "pb_mrq",
                    ]:
                        value = row.get(field)
                        if value is not None and str(value).lower() not in ["nan", "none", ""]:
                            metrics[field] = float(value)
                    if metrics:
                        data_map[str(ts_code)] = metrics
                except Exception:
                    pass
    return data_map

