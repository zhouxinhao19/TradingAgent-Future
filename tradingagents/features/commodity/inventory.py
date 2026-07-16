"""
inventory.py — 商品期货库存特征模块 (Phase 3b-i)

输入: 来自 `AkshareFuturesProvider.get_inventory(symbol, start_date, end_date)`
      (AKShare: futures_inventory_em / futures_inventory_99)
      期望列(中文 / 英文):
        日期/date, 库存/value, 增减/delta(可选),
        品种/symbol(可选,多品种时)

输出: 标准 schema Dict:
  {
    "latest":   {date, value},
    "stats":    {zscore_180d: float, slope_20d: float},
    "signals":  [...],
    "snapshot": {...全量 + wow_change / mom_change / jump_flag},
    "quality":  {...},
  }
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from tradingagents.features.commodity import _helpers as h


def _prepare(df: pd.DataFrame, symbol: Optional[str]) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = h.normalize_columns(df)
    if symbol and "symbol" in out.columns:
        from tradingagents.utils.commodity_utils import CommodityUtils
        sym_upper = symbol.upper()
        out = out[out["symbol"].astype(str).str.upper().apply(
            lambda s: (CommodityUtils.get_underlying_symbol(s) or "").upper() == sym_upper
        )].copy()
    out = h.ensure_columns(out, ["date", "value"])
    out["value"] = h.to_numeric(out["value"])
    if "delta" in out.columns:
        out["delta"] = h.to_numeric(out["delta"])
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"], errors="coerce")
        out = out.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    out = out.dropna(subset=["value"])
    return out


def _jump_flag(data: pd.DataFrame, window: int = 20) -> bool:
    """单日变化相对 20 日 rolling std 的 z-score,绝对值 >= 3 视为跳变。"""
    if data.empty or len(data) < window:
        return False
    diff = data["value"].diff()
    mu = diff.rolling(window, min_periods=5).mean()
    sd = diff.rolling(window, min_periods=5).std()
    if sd.iloc[-1] is None or sd.iloc[-1] == 0 or np.isnan(sd.iloc[-1]):
        return False
    z = (diff.iloc[-1] - mu.iloc[-1]) / sd.iloc[-1]
    return bool(pd.notna(z) and abs(float(z)) >= 3.0)


def _signals(
    wow_change: Optional[float],
    mom_change: Optional[float],
    zscore_180d: Optional[float],
    jump: bool,
    last_value: Optional[float],
    zscore_now: Optional[float],
) -> List[str]:
    sigs: List[str] = []
    if wow_change is not None:
        if wow_change > 0:
            sigs.append("库存环比上升")
        elif wow_change < 0:
            sigs.append("库存环比下降")
    if mom_change is not None:
        if mom_change > 0:
            sigs.append("库存月环比上升")
        elif mom_change < 0:
            sigs.append("库存月环比下降")
    if zscore_180d is not None:
        if zscore_180d >= 0.8:
            sigs.append("库存处高分位")
        elif zscore_180d <= 0.2:
            sigs.append("库存处低分位")
    if jump:
        sigs.append("库存变化异常(跳变)")
    # 最新值的标准化 z(相对 180 日均值)
    if zscore_now is not None and abs(zscore_now) >= 2:
        sigs.append(f"库存偏离均值({zscore_now:+.2f}σ)")
    return sigs


def compute_inventory_metrics(
    df: pd.DataFrame,
    symbol: Optional[str] = None,
    weeks_in_year: int = 52,
) -> Dict[str, Any]:
    """库存时序指标。

    Args:
        df: 来自 `get_inventory` 的 DataFrame
        symbol: 可选品种过滤
        weeks_in_year: 一年周数(用于 WoW/MoM 计算,默认 52)
    """
    if df is None or df.empty:
        return h.empty_result("无库存数据")
    data = _prepare(df, symbol)
    if data.empty:
        return h.empty_result("目标品种无库存数据")
    if len(data) < 5:
        return h.empty_result(f"样本不足(仅 {len(data)} 行)")

    last = data.iloc[-1]
    last_value = h.safe_float(last.get("value"))
    latest = {
        "date": str(last.get("date")) if pd.notna(last.get("date")) else None,
        "value": last_value,
        "delta": h.safe_float(last.get("delta")),
        "symbol": last.get("symbol"),
    }

    # WoW / MoM(按行数近似:周=5 个交易日,月=20)
    wow_ch = h.wow_change(data["value"], weeks=1)
    mom_ch = h.wow_change(data["value"], weeks=4)

    # 180 日分位 + 标准化 z
    zscore_180d = h.percentile_rank(data["value"], 180)
    zscore_now = h.zscore(data["value"], 180)
    slope_20d = h.slope(data["value"], 20)
    jump = _jump_flag(data)

    signals = _signals(wow_ch, mom_ch, zscore_180d, jump, last_value, zscore_now)
    snapshot = {
        **latest,
        "wow_change": wow_ch,
        "mom_change": mom_ch,
        "wow_change_pct": (
            float(wow_ch / last_value) if (wow_ch is not None and last_value not in (None, 0)) else None
        ),
        "mom_change_pct": (
            float(mom_ch / last_value) if (mom_ch is not None and last_value not in (None, 0)) else None
        ),
        "zscore_180d": zscore_180d,
        "zscore_value": zscore_now,
        "slope_20d": slope_20d,
        "jump_flag": jump,
        "min_180d": h.safe_float(data["value"].tail(180).min()),
        "max_180d": h.safe_float(data["value"].tail(180).max()),
        "mean_180d": h.safe_float(data["value"].tail(180).mean()),
    }
    quality = h.data_quality(data, value_col="value")
    quality["symbol"] = symbol or latest.get("symbol")
    return {
        "latest": latest,
        "stats": {"zscore_180d": zscore_180d, "slope_20d": slope_20d},
        "signals": signals,
        "snapshot": snapshot,
        "quality": quality,
    }
