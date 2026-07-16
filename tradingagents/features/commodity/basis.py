"""
basis.py — 商品期货基差特征模块 (Phase 3b-i)

输入: 来自 `AkshareFuturesProvider.get_basis_history()`(AKShare: futures_spot_price_daily)
      期望列(中文 / 英文):
        日期/date, 品种/symbol,
        现货价格/spot_price,
        近月合约/near_contract, 近月合约价/near_contract_price,
        主力合约/dominant_contract, 主力合约价/dominant_contract_price,
        近月基差/near_basis, 主力基差/dom_basis,
        近月基差率/near_basis_rate, 主力基差率/dom_basis_rate

输出: 标准 schema Dict:
  {
    "latest":   {spot_price, near_contract_price, dominant_contract_price,
                 near_basis, dom_basis, near_basis_rate, dom_basis_rate,
                 near_contract, dominant_contract},
    "stats":    {zscore_180d: {near_basis_rate, dom_basis_rate},
                 slope_20d:   {near_basis_rate, dom_basis_rate}},
    "signals":  [...rule-based],
    "snapshot": {...全量},
    "quality":  {rows, coverage, data_freshness_days},
  }
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from tradingagents.features.commodity import _helpers as h


# =============================================================================
# 1. 列名规范化(基差模块专用 — 在通用 _helpers 基础上覆盖)
# =============================================================================

_BASIS_REQUIRED = [
    "date",
    "spot_price",
    "near_contract_price",
    "dominant_contract_price",
    "near_basis",
    "dom_basis",
    "near_basis_rate",
    "dom_basis_rate",
]


def _prepare(df: pd.DataFrame, symbol: Optional[str]) -> pd.DataFrame:
    """规范化列名 + 数值化 + (可选)按品种过滤。"""
    if df is None or df.empty:
        return pd.DataFrame()
    out = h.normalize_columns(df)
    # 多品种时过滤(按 underlying symbol 匹配)
    if symbol and "symbol" in out.columns:
        from tradingagents.utils.commodity_utils import CommodityUtils
        sym_upper = symbol.upper()
        out = out[out["symbol"].astype(str).str.upper().apply(
            lambda s: (CommodityUtils.get_underlying_symbol(s) or "").upper() == sym_upper
        )].copy()
    # 缺失列补 NA
    out = h.ensure_columns(out, _BASIS_REQUIRED)
    # 数值化
    for c in [
        "spot_price", "near_contract_price", "dominant_contract_price",
        "near_basis", "dom_basis", "near_basis_rate", "dom_basis_rate",
    ]:
        out[c] = h.to_numeric(out[c])
    if "date" in out.columns:
        out = out.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    return out


# =============================================================================
# 2. 触发信号
# =============================================================================

def _signals(latest: Dict[str, Any], zscore_180d: Dict[str, float]) -> List[str]:
    sigs: List[str] = []
    nbr = latest.get("near_basis_rate")
    dbr = latest.get("dom_basis_rate")
    p_near = zscore_180d.get("near_basis_rate")
    p_dom = zscore_180d.get("dom_basis_rate")

    if nbr is not None:
        if nbr < 0 and (p_near is not None and p_near <= 0.2):
            sigs.append("近月贴水处低分位，存在反弹概率")
        elif nbr > 0 and (p_near is not None and p_near >= 0.8):
            sigs.append("近月升水处高分位，回归风险上升")
        elif abs(nbr) > 0.05:
            sigs.append(f"近月基差率偏离较大({nbr:.2%})")
    if dbr is not None:
        if dbr < 0 and (p_dom is not None and p_dom <= 0.2):
            sigs.append("主力贴水处低分位")
        elif dbr > 0 and (p_dom is not None and p_dom >= 0.8):
            sigs.append("主力升水处高分位")
    # 反向基差信号(主力贴水但近月升水)
    if (nbr is not None and dbr is not None
            and nbr > 0 and dbr < 0):
        sigs.append("近远月基差反向(Contango↔Backwardation)")
    return sigs


# =============================================================================
# 3. 公开入口
# =============================================================================

def compute_basis_metrics(df: pd.DataFrame, symbol: Optional[str] = None) -> Dict[str, Any]:
    """基差与期现关系指标。

    Args:
        df: 来自 `get_basis_history` 的 DataFrame(可含多品种)
        symbol: 可选,仅返回该品种的指标(列名 `symbol` / `品种`)
    """
    if df is None or df.empty:
        return h.empty_result("无基差数据")
    data = _prepare(df, symbol)
    if data.empty:
        return h.empty_result("目标品种无数据")
    if len(data) < 5:
        return h.empty_result(f"样本不足(仅 {len(data)} 行)")

    last = data.iloc[-1]
    latest: Dict[str, Any] = {
        "date": str(last.get("date")) if pd.notna(last.get("date")) else None,
        "symbol": last.get("symbol"),
        "spot_price": h.safe_float(last.get("spot_price")),
        "near_contract": last.get("near_contract"),
        "near_contract_price": h.safe_float(last.get("near_contract_price")),
        "dominant_contract": last.get("dominant_contract"),
        "dominant_contract_price": h.safe_float(last.get("dominant_contract_price")),
        "near_basis": h.safe_float(last.get("near_basis")),
        "dom_basis": h.safe_float(last.get("dom_basis")),
        "near_basis_rate": h.safe_float(last.get("near_basis_rate")),
        "dom_basis_rate": h.safe_float(last.get("dom_basis_rate")),
    }

    # 180 日分位
    tail = data.tail(180)
    zscore_180d = {
        "near_basis_rate": h.percentile_rank(tail["near_basis_rate"], 180),
        "dom_basis_rate": h.percentile_rank(tail["dom_basis_rate"], 180),
        "near_basis": h.percentile_rank(tail["near_basis"], 180),
        "dom_basis": h.percentile_rank(tail["dom_basis"], 180),
    }
    slope_20d = {
        "near_basis_rate": h.slope(data["near_basis_rate"], 20),
        "dom_basis_rate": h.slope(data["dom_basis_rate"], 20),
        "near_basis": h.slope(data["near_basis"], 20),
        "dom_basis": h.slope(data["dom_basis"], 20),
    }
    stats = {"zscore_180d": zscore_180d, "slope_20d": slope_20d}

    signals = _signals(latest, zscore_180d)
    snapshot = {
        **latest,
        "near_basis_rate_pctl_180d": zscore_180d["near_basis_rate"],
        "dom_basis_rate_pctl_180d": zscore_180d["dom_basis_rate"],
        "near_basis_rate_slope_20d": slope_20d["near_basis_rate"],
        "dom_basis_rate_slope_20d": slope_20d["dom_basis_rate"],
        # 偏离量(最新 - 180 日均值)
        "near_basis_rate_dev_180d": (
            float(last["near_basis_rate"] - tail["near_basis_rate"].mean())
            if pd.notna(last["near_basis_rate"]) else None
        ),
        "dom_basis_rate_dev_180d": (
            float(last["dom_basis_rate"] - tail["dom_basis_rate"].mean())
            if pd.notna(last["dom_basis_rate"]) else None
        ),
    }
    quality = h.data_quality(data, value_col="near_basis_rate")
    quality["symbol"] = symbol or latest.get("symbol")

    return {
        "latest": latest,
        "stats": stats,
        "signals": signals,
        "snapshot": snapshot,
        "quality": quality,
    }
