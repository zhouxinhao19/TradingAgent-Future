"""
term_structure.py — 商品期货期限结构 / 展期收益特征模块 (Phase 3b-i)

输入: 来自 `AkshareFuturesProvider.get_roll_yield(type_method="date", var, start_day, end_day)`
      (AKShare: get_roll_yield_bar)
      期望列(中文 / 英文):
        日期/date, 品种/var,
        近月合约/near_contract, 主力合约/dominant_contract,
        展期收益率/roll_yield(主要度量),
        价差/spread(可选),
        近月价格/near_price, 主力价格/dominant_price(可选)

      也可仅接受 `roll_yield` / `spread` / `main_minus_second` 之一作为主度量。

输出: 标准 schema Dict + 结构判定(structure) + carry_score(-1,1)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from tradingagents.features.commodity import _helpers as h


_METRIC_CANDIDATES = [
    "roll_yield", "rollYield", "roll", "yield", "展期收益率",
    "spread", "price_spread", "main_minus_second", "价差",
]


def _pick_metric(df: pd.DataFrame) -> Optional[str]:
    for c in _METRIC_CANDIDATES:
        if c in df.columns:
            return c
    return None


def _derive_spread(df: pd.DataFrame) -> Optional[str]:
    """若无 spread / roll_yield,从主力价 - 次主价推导 spread。"""
    if {"main_price", "second_price"}.issubset(df.columns):
        df["spread"] = pd.to_numeric(df["main_price"], errors="coerce") - pd.to_numeric(df["second_price"], errors="coerce")
        return "spread"
    if {"near_price", "dominant_price"}.issubset(df.columns):
        df["spread"] = pd.to_numeric(df["dominant_price"], errors="coerce") - pd.to_numeric(df["near_price"], errors="coerce")
        return "spread"
    if {"dominant_price", "near_price"}.issubset(df.columns):
        df["spread"] = pd.to_numeric(df["dominant_price"], errors="coerce") - pd.to_numeric(df["near_price"], errors="coerce")
        return "spread"
    return None


def _prepare(df: pd.DataFrame, var: Optional[str]) -> tuple[pd.DataFrame, Optional[str]]:
    if df is None or df.empty:
        return pd.DataFrame(), None
    out = h.normalize_columns(df)
    if var and "var" in out.columns:
        out = out[out["var"].astype(str).str.upper() == var.upper()].copy()
    metric = _pick_metric(out)
    if metric is None:
        metric = _derive_spread(out)
    if metric is None:
        return out, None
    out[metric] = h.to_numeric(out[metric])
    out = out.dropna(subset=[metric])
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"], errors="coerce")
        out = out.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    return out, metric


def _structure(val: Optional[float]) -> Optional[str]:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    if val > 0:
        return "contango"      # 远月>近月,正展期
    if val < 0:
        return "backwardation"  # 近月>远月,负展期
    return "flat"


def _carry_score(pctl: Optional[float], structure: Optional[str]) -> Optional[float]:
    """carry_score ∈ [-1, 1]:越高越利好多头。
    逻辑:
      - 分位 0.5 = 中性 → 0;0 = 极度 backwardation → +1;1 = 极度 contango → -1
      - backwardation 加成 +0.2;contango 减 -0.2
    """
    if pctl is None or (isinstance(pctl, float) and np.isnan(pctl)):
        return None
    carry = (pctl - 0.5) * 2.0
    if structure == "backwardation":
        carry += 0.2
    elif structure == "contango":
        carry -= 0.2
    return float(max(-1.0, min(1.0, carry)))


def _signals(structure: Optional[str], carry: Optional[float], slope_20d: Optional[float]) -> List[str]:
    sigs: List[str] = []
    if structure == "backwardation":
        sigs.append("期限结构偏多(Backwardation)")
    elif structure == "contango":
        sigs.append("期限结构偏空(Contango)")
    elif structure == "flat":
        sigs.append("期限结构平坦(Flat)")
    if carry is not None:
        if carry >= 0.5:
            sigs.append("carry 友好(多头)")
        elif carry <= -0.5:
            sigs.append("carry 不友好(空头友好)")
    if slope_20d is not None:
        if slope_20d > 0:
            sigs.append("期限结构走陡(向 Contango)")
        elif slope_20d < 0:
            sigs.append("期限结构走平(向 Backwardation)")
    return sigs


def compute_term_structure_metrics(
    df: pd.DataFrame,
    var: Optional[str] = None,
) -> Dict[str, Any]:
    """期限结构 / 展期收益指标。

    Args:
        df: 来自 `get_roll_yield(type_method="date", ...)` 的 DataFrame
        var: 品种过滤(可选,列名 `var` / `symbol` / `品种`)
    """
    if df is None or df.empty:
        return h.empty_result("无期限结构数据")
    data, metric = _prepare(df, var)
    if data.empty:
        return h.empty_result("目标品种无期限结构数据")
    if metric is None:
        return h.empty_result("未识别可用的展期/价差列(roll_yield / spread)")
    if len(data) < 5:
        return h.empty_result(f"样本不足(仅 {len(data)} 行)")

    last = data.iloc[-1]
    latest = {
        "date": str(last.get("date")) if pd.notna(last.get("date")) else None,
        "var": last.get("var") or last.get("symbol"),
        "metric": metric,
        metric: h.safe_float(last.get(metric)),
        "near_contract": last.get("near_contract"),
        "dominant_contract": last.get("dominant_contract"),
        "near_price": h.safe_float(last.get("near_price")),
        "dominant_price": h.safe_float(last.get("dominant_price")),
    }
    structure = _structure(latest[metric])
    zscore_180d = h.percentile_rank(data[metric], 180)
    slope_20d = h.slope(data[metric], 20)
    carry = _carry_score(zscore_180d, structure)
    signals = _signals(structure, carry, slope_20d)

    snapshot = {
        **latest,
        "structure": structure,
        "carry_score": carry,
        f"{metric}_pctl_180d": zscore_180d,
        f"{metric}_slope_20d": slope_20d,
        f"{metric}_zscore_180d": h.zscore(data[metric], 180),
        f"{metric}_mean_180d": h.safe_float(data[metric].tail(180).mean()),
        f"{metric}_std_180d": h.safe_float(data[metric].tail(180).std()),
        f"{metric}_min_180d": h.safe_float(data[metric].tail(180).min()),
        f"{metric}_max_180d": h.safe_float(data[metric].tail(180).max()),
    }
    quality = h.data_quality(data, value_col=metric)
    quality["var"] = var or latest.get("var")
    quality["metric"] = metric

    return {
        "latest": latest,
        "stats": {"zscore_180d": zscore_180d, "slope_20d": slope_20d},
        "signals": signals,
        "snapshot": snapshot,
        "quality": quality,
    }
