"""Features 包入口(Phase 3b-ii 引入)。

提供:
  - 6 个 commodity features 函数的便捷导出(纯规则,零 LLM)
  - compute_all_features_from_provider(): 一键从任意已连接的
    BaseCommodityDataProvider 实例拉取 6 模块所需数据,产出统一结构

零 LLM、零状态;调用方只需要传入一个 connect() 过的 provider 即可。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from .commodity import _helpers  # noqa: F401  供内层模块 cross-import
from . import commodity as _commodity  # noqa: F401
from .commodity import _helpers as helpers  # noqa: F401  供 custom_data_adapter 等外部模块复用 zscore/slope/percentile_rank/data_quality/empty_result
from tradingagents.dataflows.providers.commodity.commodity_metadata import normalize_exchange_code
from tradingagents.utils.commodity_utils import CommodityUtils

# 便捷导出
from .commodity.technical import compute_technical_metrics, compute_technical_metrics_multi_contract
from .commodity.basis import compute_basis_metrics
from .commodity.inventory import compute_inventory_metrics
from .commodity.positioning import compute_positioning_metrics
from .commodity.term_structure import compute_term_structure_metrics
from .commodity.news_sentiment import compute_news_sentiment_metrics


def _safe(callable_, fallback_reason: str, errors: Dict[str, str], key: str):
    """调用单个 features 模块;失败不抛错,记录 errors 并返回 empty_result。"""
    try:
        return callable_()
    except Exception as e:  # noqa: BLE001
        errors[key] = repr(e)
        return _helpers.empty_result(fallback_reason)


async def _call_provider(provider, method_name, *args, **kwargs):
    """安全调用 provider 的异步方法,失败返回 None。"""
    try:
        method = getattr(provider, method_name, None)
        if method is None:
            return None
        result = await method(*args, **kwargs)
        return result
    except Exception as e:
        return None


async def _call_provider_with_timeout(
    provider, method_name: str, timeout: float, *args, **kwargs
):
    """安全调用 provider 异步方法,带单调用超时。

    超时后返回 None(不抛异常),保证一个慢调用不阻塞整个 features 流程。
    """
    import asyncio as _asyncio

    try:
        method = getattr(provider, method_name, None)
        if method is None:
            return None
        return await _asyncio.wait_for(
            method(*args, **kwargs), timeout=timeout,
        )
    except (_asyncio.TimeoutError, Exception):
        return None


def _resolve_technical_symbols(full_symbol: str, underlying: str) -> Dict[str, Optional[str]]:
    """解析技术分析所需的合约代码。

    Args:
        full_symbol: 完整合约代码, 如 ``CU2501.SHF`` 或主力连续码
        underlying: 品种代码, 如 ``CU``

    Returns:
        {"main_symbol": str, "index_symbol": str or None}
    """
    from tradingagents.dataflows.providers.commodity.commodity_metadata import get_index_symbol

    return {
        "main_symbol": full_symbol,
        "index_symbol": get_index_symbol(underlying),
    }


async def compute_all_features_from_provider(
    provider: Any,
    full_symbol: str,
    trade_date: Optional[str] = None,
) -> Dict[str, Any]:
    """从 provider 拉取数据并并行调用 6 个 features 模块。

    Args:
        provider:已 connect() 的 BaseCommodityDataProvider 实例。
                 如果 provider 提供的方法签名不同,本函数会捕获异常并跳过该模块。
        full_symbol:如 ``CU2501.SHF`` 或主力连续码。
        trade_date:YYYY-MM-DD,可选(None 表示最近一日)。

    Returns:
        {
          "success": bool,
          "full_symbol": str,
          "trade_date": str,
          "features": {
            "technical": {...},
            "basis": {...},
            "inventory": {...},
            "positioning": {...},
            "term_structure": {...},
            "news_sentiment": {...},
          },
          "errors": { module_name: "ExceptionType: msg", ... }
        }
    """
    result: Dict[str, Any] = {
        "success": True,
        "full_symbol": full_symbol,
        "trade_date": trade_date or "",
        "features": {},
        "errors": {},
    }

    underlying = CommodityUtils.get_underlying_symbol(full_symbol) or full_symbol.split(".")[0]

    # ---- 1. 并行拉取数据(每调用独立超时 20s) ----
    exchange_code = (
        normalize_exchange_code(full_symbol.split(".")[-1])
        if "." in full_symbol else "SHFE"
    )
    date_compact = trade_date.replace("-", "")[:8] if trade_date else "20260715"

    # AKShare 部分接口(futures_spot_price_daily / get_roll_yield)对超过
    # ~45 天的查询窗口直接返回空(实测 60d / 18m 均为 0;30d / 15d / 7d 正常)。
    # 详情页用 6d 窗口能拿到数据。把这两个查询限制在 30d 内。
    _basis_start = (
        (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=30)).strftime("%Y-%m-%d")
        if trade_date else "2026-06-20"
    )
    _roll_start = (
        (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=30)).strftime("%Y-%m-%d")
        if trade_date else "2026-06-20"
    )

    import asyncio as _asyncio

    results = await _asyncio.gather(
        # 历史 K 线
        _call_provider_with_timeout(
            provider, "get_historical_data", 20,
            full_symbol, start_date="2025-01-01", end_date=trade_date or "2026-07-16",
        ),
        # 指数合约数据
        _call_provider_with_timeout(
            provider, "get_historical_data_for_index", 20,
            underlying, start_date="2025-01-01", end_date=trade_date or "2026-07-16",
        ),
        # 基差历史
        _call_provider_with_timeout(
            provider, "get_basis_history", 20,
            _basis_start, trade_date or "2026-07-16", [underlying],
        ),
        # 现货价格(可能调 100ppi.com,单独超时)
        _call_provider_with_timeout(
            provider, "get_spot_price", 15,
            trade_date or "2026-07-15", underlying,
        ),
        # 库存
        _call_provider_with_timeout(
            provider, "get_inventory", 15, underlying,
        ),
        # 持仓排名(30 天历史,供 positioning 5d/60d 指标计算)
        _call_provider_with_timeout(
            provider, "get_position_rank_history", 60,
            exchange_code, date_compact, 30, None, underlying,
        ),
        # 展期收益率(最长等待 60s,DIY 计算需抓取日线全市场数据)
        _call_provider_with_timeout(
            provider, "get_roll_yield", 60,
            "date", var=underlying, start_day=_roll_start, end_day=date_compact,
        ),
        # 新闻
        _call_provider_with_timeout(
            provider, "get_futures_news", 15, "all", 100,
        ),
        return_exceptions=True,
    )

    (
        df_hist, index_df, basis_df, spot_df,
        inv_df, pos_data, roll_df, news_list,
    ) = results

    # 将异常转为 None
    def _unwrap(r):
        return None if isinstance(r, (BaseException, Exception)) else r

    df_hist = _unwrap(df_hist)
    index_df = _unwrap(index_df)
    basis_df = _unwrap(basis_df)
    spot_df = _unwrap(spot_df)
    inv_df = _unwrap(inv_df)
    pos_data = _unwrap(pos_data)
    roll_df = _unwrap(roll_df)
    news_list = _unwrap(news_list)

    if df_hist is None:
        result["errors"]["historical"] = "历史 K 线数据获取失败"

    # ---- 2. 调用 6 个 features 计算函数 ----
    features = result["features"]
    errors = result["errors"]

    features["technical"] = _safe(
        lambda: compute_technical_metrics_multi_contract(
            main_df=df_hist,
            index_df=index_df,
            include_weekly=True,
        ) if df_hist is not None
        else _helpers.empty_result("无历史 K 线"),
        "技术面计算失败",
        errors,
        "technical",
    )
    features["basis"] = _safe(
        lambda: compute_basis_metrics(basis_df if basis_df is not None else spot_df, underlying),
        "基差计算失败",
        errors,
        "basis",
    )
    features["inventory"] = _safe(
        lambda: compute_inventory_metrics(inv_df, underlying) if inv_df is not None
        else _helpers.empty_result("无库存数据"),
        "库存计算失败",
        errors,
        "inventory",
    )
    features["positioning"] = _safe(
        lambda: compute_positioning_metrics(pos_data, underlying) if pos_data is not None
        else _helpers.empty_result("无持仓数据"),
        "持仓计算失败",
        errors,
        "positioning",
    )
    features["term_structure"] = _safe(
        lambda: compute_term_structure_metrics(roll_df) if roll_df is not None
        else _helpers.empty_result("无期限结构数据"),
        "期限结构计算失败",
        errors,
        "term_structure",
    )
    features["news_sentiment"] = _safe(
        lambda: compute_news_sentiment_metrics(news_list) if news_list is not None
        else _helpers.empty_result("无新闻数据"),
        "新闻情感计算失败",
        errors,
        "news_sentiment",
    )

    # success 标记:6 模块中是否有任一报错
    module_errors = {k: v for k, v in errors.items() if k in {
        "technical", "basis", "inventory", "positioning",
        "term_structure", "news_sentiment"
    }}
    if module_errors:
        result["success"] = False

    return result


__all__ = [
    "compute_technical_metrics",
    "compute_technical_metrics_multi_contract",
    "compute_basis_metrics",
    "compute_inventory_metrics",
    "compute_positioning_metrics",
    "compute_term_structure_metrics",
    "compute_news_sentiment_metrics",
    "compute_all_features_from_provider",
]
