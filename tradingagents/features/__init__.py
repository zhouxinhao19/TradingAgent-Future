"""Features 包入口(Phase 3b-ii 引入)。

提供:
  - 6 个 commodity features 函数的便捷导出(纯规则,零 LLM)
  - compute_all_features_from_provider(): 一键从任意已连接的
    BaseCommodityDataProvider 实例拉取 6 模块所需数据,产出统一结构

零 LLM、零状态;调用方只需要传入一个 connect() 过的 provider 即可。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .commodity import _helpers  # noqa: F401  供内层模块 cross-import
from . import commodity as _commodity  # noqa: F401

# 便捷导出
from .commodity.technical import compute_technical_metrics
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


def compute_all_features_from_provider(
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

    # ---- 1. 拉取数据(逐模块独立 try) ----
    df_hist: Any = None
    try:
        df_hist = provider.get_historical_data(
            full_symbol, start_date="", end_date=trade_date or ""
        )
    except Exception as e:  # noqa: BLE001
        result["errors"]["historical"] = repr(e)

    basis_df: Any = None
    try:
        # 简化:只用近 180 天区间查询
        basis_df = provider.get_basis_history(
            vars_list=[full_symbol.split(".")[0]],
            start_day="",
            end_day=trade_date or "",
        )
    except Exception as e:  # noqa: BLE001
        result["errors"]["basis_history"] = repr(e)

    spot_df: Any = None
    try:
        spot_df = provider.get_spot_price(trade_date or "")
    except Exception as e:  # noqa: BLE001
        result["errors"]["spot_price"] = repr(e)

    inv_df: Any = None
    try:
        inv_df = provider.get_inventory(full_symbol.split(".")[0])
    except Exception as e:  # noqa: BLE001
        result["errors"]["inventory_data"] = repr(e)

    pos_df: Any = None
    try:
        pos_df = provider.get_position_rank(full_symbol.split(".")[0])
    except Exception as e:  # noqa: BLE001
        result["errors"]["position_rank"] = repr(e)

    roll_df: Any = None
    try:
        roll_df = provider.get_roll_yield(
            "date",
            {"var": full_symbol.split(".")[0], "date": trade_date or ""},
        )
    except Exception as e:  # noqa: BLE001
        result["errors"]["roll_yield"] = repr(e)

    news_list: Any = None
    try:
        news_list = provider.get_futures_news("all", 100)
    except Exception as e:  # noqa: BLE001
        result["errors"]["futures_news"] = repr(e)

    # ---- 2. 调用 6 个 features 计算函数 ----
    features = result["features"]
    errors = result["errors"]

    features["technical"] = _safe(
        lambda: compute_technical_metrics(df_hist) if df_hist is not None
        else _helpers.empty_result("无历史 K 线"),
        "技术面计算失败",
        errors,
        "technical",
    )
    features["basis"] = _safe(
        lambda: compute_basis_metrics(basis_df if basis_df is not None else spot_df, full_symbol),
        "基差计算失败",
        errors,
        "basis",
    )
    features["inventory"] = _safe(
        lambda: compute_inventory_metrics(inv_df, full_symbol) if inv_df is not None
        else _helpers.empty_result("无库存数据"),
        "库存计算失败",
        errors,
        "inventory",
    )
    features["positioning"] = _safe(
        lambda: compute_positioning_metrics(pos_df, full_symbol) if pos_df is not None
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
    "compute_basis_metrics",
    "compute_inventory_metrics",
    "compute_positioning_metrics",
    "compute_term_structure_metrics",
    "compute_news_sentiment_metrics",
    "compute_all_features_from_provider",
]
