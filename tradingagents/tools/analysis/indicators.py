from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class IndicatorSpec:
    name: str
    params: Optional[Dict[str, Any]] = None


SUPPORTED = {"ma", "ema", "macd", "rsi", "boll", "atr", "kdj"}


def _require_cols(df: pd.DataFrame, cols: Iterable[str]):
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"DataFrame缺少必要列: {missing}, 现有列: {list(df.columns)[:10]}...")


def ma(close: pd.Series, n: int) -> pd.Series:
    return close.rolling(window=int(n), min_periods=int(n)).mean()


def ema(close: pd.Series, n: int) -> pd.Series:
    return close.ewm(span=int(n), adjust=False).mean()


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    dif = ema(close, fast) - ema(close, slow)
    dea = dif.ewm(span=int(signal), adjust=False).mean()
    hist = dif - dea
    return pd.DataFrame({"dif": dif, "dea": dea, "macd_hist": hist})


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / float(n), adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / float(n), adjust=False).mean()
    rs = avg_gain / (avg_loss.replace(0, np.nan))
    rsi_val = 100 - (100 / (1 + rs))
    return rsi_val


def boll(close: pd.Series, n: int = 20, k: float = 2.0) -> pd.DataFrame:
    mid = close.rolling(window=int(n), min_periods=int(n)).mean()
    std = close.rolling(window=int(n), min_periods=int(n)).std()
    upper = mid + k * std
    lower = mid - k * std
    return pd.DataFrame({"boll_mid": mid, "boll_upper": upper, "boll_lower": lower})


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low).abs(),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(window=int(n), min_periods=int(n)).mean()


def kdj(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 9, m1: int = 3, m2: int = 3) -> pd.DataFrame:
    lowest_low = low.rolling(window=int(n), min_periods=int(n)).min()
    highest_high = high.rolling(window=int(n), min_periods=int(n)).max()
    rsv = (close - lowest_low) / (highest_high - lowest_low) * 100
    # 处理除零与起始NaN
    rsv = rsv.replace([np.inf, -np.inf], np.nan)

    # 按经典公式递推（初始化 50）
    k = pd.Series(np.nan, index=close.index)
    d = pd.Series(np.nan, index=close.index)
    alpha_k = 1 / float(m1)
    alpha_d = 1 / float(m2)
    last_k = 50.0
    last_d = 50.0
    for i in range(len(close)):
        rv = rsv.iloc[i]
        if np.isnan(rv):
            k.iloc[i] = np.nan
            d.iloc[i] = np.nan
            continue
        curr_k = (1 - alpha_k) * last_k + alpha_k * rv
        curr_d = (1 - alpha_d) * last_d + alpha_d * curr_k
        k.iloc[i] = curr_k
        d.iloc[i] = curr_d
        last_k, last_d = curr_k, curr_d
    j = 3 * k - 2 * d
    return pd.DataFrame({"kdj_k": k, "kdj_d": d, "kdj_j": j})


def compute_indicator(df: pd.DataFrame, spec: IndicatorSpec) -> pd.DataFrame:
    name = spec.name.lower()
    params = spec.params or {}
    out = df.copy()

    if name == "ma":
        _require_cols(df, ["close"])
        n = int(params.get("n", params.get("period", 20)))
        out[f"ma{n}"] = ma(df["close"], n)
        return out

    if name == "ema":
        _require_cols(df, ["close"])
        n = int(params.get("n", params.get("period", 20)))
        out[f"ema{n}"] = ema(df["close"], n)
        return out

    if name == "macd":
        _require_cols(df, ["close"])
        fast = int(params.get("fast", 12))
        slow = int(params.get("slow", 26))
        signal = int(params.get("signal", 9))
        macd_df = macd(df["close"], fast=fast, slow=slow, signal=signal)
        for c in macd_df.columns:
            out[c] = macd_df[c]
        return out

    if name == "rsi":
        _require_cols(df, ["close"])
        n = int(params.get("n", params.get("period", 14)))
        out[f"rsi{n}"] = rsi(df["close"], n)
        return out

    if name == "boll":
        _require_cols(df, ["close"])
        n = int(params.get("n", 20))
        k = float(params.get("k", 2.0))
        boll_df = boll(df["close"], n=n, k=k)
        for c in boll_df.columns:
            out[c] = boll_df[c]
        return out

    if name == "atr":
        _require_cols(df, ["high", "low", "close"])
        n = int(params.get("n", 14))
        out[f"atr{n}"] = atr(df["high"], df["low"], df["close"], n=n)
        return out

    if name == "kdj":
        _require_cols(df, ["high", "low", "close"])
        n = int(params.get("n", 9))
        m1 = int(params.get("m1", 3))
        m2 = int(params.get("m2", 3))
        kdj_df = kdj(df["high"], df["low"], df["close"], n=n, m1=m1, m2=m2)
        for c in kdj_df.columns:
            out[c] = kdj_df[c]
        return out

    raise ValueError(f"不支持的指标: {name}")


def compute_many(df: pd.DataFrame, specs: List[IndicatorSpec]) -> pd.DataFrame:
    if not specs:
        return df.copy()
    # 粗略去重（按 name+sorted(params)）
    def key(s: IndicatorSpec):
        p = s.params or {}
        items = tuple(sorted(p.items()))
        return (s.name.lower(), items)

    unique_specs: List[IndicatorSpec] = []
    seen = set()
    for s in specs:
        k = key(s)
        if k not in seen:
            seen.add(k)
            unique_specs.append(s)

    out = df.copy()
    for s in unique_specs:
        out = compute_indicator(out, s)
    return out


def last_values(df: pd.DataFrame, columns: List[str]) -> Dict[str, Any]:
    if df.empty:
        return {c: None for c in columns}
    last = df.iloc[-1]
    return {c: (None if c not in df.columns else (None if pd.isna(last.get(c)) else last.get(c))) for c in columns}

