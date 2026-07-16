"""
technical.py — 商品期货技术面特征模块 (Phase 3b-i)

设计目标:
  - 输入 OHLCV DataFrame(由 `AkshareFuturesProvider.get_historical_data` 返回,
    列名中文: 日期/开盘价/最高价/最低价/收盘价/成交量/持仓量;
    也兼容英文: date/open/high/low/close/volume/open_interest)
  - 输出符合 Phase 3b 标准 schema 的 Dict:
      {
        "latest":   {指标名: float},          # 最新值(最常用 ~20 项)
        "stats":    {zscore_180d, slope_20d}, # 统计特征
        "signals":  [rule-based 信号文字],    # 触发条件
        "snapshot": {指标名: float, ...},     # 全量数值快照(供 LLM 消费,~50+ 项)
        "quality":  {data_freshness, coverage, rows},
      }
  - 多周期: 日 / 周(resample W-FRI)
  - 纯函数、零 LLM、零外部 API

复用:
  - `tradingagents.tools.analysis.indicators` 提供 MA/EMA/MACD/RSI/BOLL/ATR/KDJ
  - 本模块补充 indicators.py 未覆盖的高级指标(PSAR/Williams/CCI/StochRSI/Ichimoku/CMF/VPT/TSI/ADX/OBV)
    与期货特有指标(OI 变化、资金流向、综合评分)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from tradingagents.tools.analysis import indicators as ind_mod

# =============================================================================
# 1. 列名规范化:兼容中文(provider 默认输出)与英文(测试 / 其他 provider)
# =============================================================================

COLUMN_ALIASES: Dict[str, List[str]] = {
    "date": ["日期", "时间", "date", "trade_date", "datetime"],
    "open": ["开盘价", "开盘", "open"],
    "high": ["最高价", "最高", "high"],
    "low": ["最低价", "最低", "low"],
    "close": ["收盘价", "收盘", "close"],
    "volume": ["成交量", "volume", "vol"],
    "open_interest": ["持仓量", "open_interest", "oi"],
}

CANONICAL_COLUMNS: List[str] = list(COLUMN_ALIASES.keys())


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """将输入 DataFrame 的列名规范化为英文(date/open/high/low/close/volume/open_interest)。

    - 不在别名表中的列原样保留(如 `rollover_date`, `动态结算价`)
    - 缺失关键列(close)时抛 ValueError
    """
    if df is None or df.empty:
        return df.copy() if df is not None else pd.DataFrame()

    rename_map: Dict[str, str] = {}
    used: set = set()
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in df.columns and alias not in used and canonical not in df.columns:
                rename_map[alias] = canonical
                used.add(alias)
                break

    out = df.rename(columns=rename_map)
    if "close" not in out.columns:
        raise ValueError(
            f"DataFrame 缺少收盘价列(close/收盘价/收盘), 现有列: {list(df.columns)[:10]}"
        )
    # 日期列若存在,转为 datetime
    if "date" in out.columns and not pd.api.types.is_datetime64_any_dtype(out["date"]):
        try:
            out["date"] = pd.to_datetime(out["date"])
        except Exception:
            pass
    return out


# =============================================================================
# 2. 基础技术指标复用 indicators.py
# =============================================================================

def _ma(close: pd.Series, n: int) -> pd.Series:
    return ind_mod.ma(close, n, min_periods=1)


def _ema(close: pd.Series, n: int) -> pd.Series:
    return ind_mod.ema(close, n)


def _macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    df = ind_mod.macd(close, fast=fast, slow=slow, signal=signal)
    return df["dif"], df["dea"], df["macd_hist"]


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    return ind_mod.rsi(close, n, method="ema")


def _boll(close: pd.Series, n: int = 20, k: float = 2.0):
    df = ind_mod.boll(close, n=n, k=k, min_periods=1)
    return df["boll_mid"], df["boll_upper"], df["boll_lower"]


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    return ind_mod.atr(high, low, close, n=n)


def _kdj(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 9, m1: int = 3, m2: int = 3):
    df = ind_mod.kdj(high, low, close, n=n, m1=m1, m2=m2)
    return df["kdj_k"], df["kdj_d"], df["kdj_j"]


# =============================================================================
# 3. indicators.py 未覆盖的高级指标(本模块自补)
# =============================================================================

def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr1 = (high - low).abs()
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)


def _adx_dmi(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14):
    """ADX / +DI / -DI(14)。返回 (adx, plus_di, minus_di)。"""
    tr = _true_range(high, low, close)
    plus_dm = (high - high.shift(1)).clip(lower=0)
    minus_dm = (low.shift(1) - low).clip(lower=0)
    # 当 +DM 和 -DM 同时为正时取较大者(Wilder 标准)
    cond = plus_dm > minus_dm
    plus_dm = plus_dm.where(cond, 0.0)
    minus_dm = minus_dm.where(~cond, 0.0)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr.replace(0, np.nan))
    minus_di = 100 * (minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr.replace(0, np.nan))
    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)).fillna(0)
    adx = dx.ewm(alpha=1 / period, adjust=False).mean()
    return adx, plus_di, minus_di


def _obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """能量潮(On-Balance Volume)。"""
    if volume is None or volume.empty:
        return pd.Series(0.0, index=close.index)
    sign = close.diff().fillna(0).apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    return (sign * volume.fillna(0)).cumsum()


def _psar(high: pd.Series, low: pd.Series,
          af_start: float = 0.02, af_inc: float = 0.02, af_max: float = 0.2):
    """抛物线转向指标。返回 (psar, trend)。trend: 1=上升, -1=下降。"""
    length = len(high)
    psar = pd.Series(np.nan, index=high.index, dtype=float)
    trend = pd.Series(0, index=high.index, dtype=int)
    if length < 2:
        return psar, trend

    psar.iloc[0] = float(low.iloc[0])
    trend.iloc[0] = 1
    af = af_start
    ep = float(high.iloc[0])

    for i in range(1, length):
        prev_psar = float(psar.iloc[i - 1])
        prev_trend = int(trend.iloc[i - 1])
        new_psar = prev_psar + af * (ep - prev_psar)

        if prev_trend == 1:
            if float(low.iloc[i]) <= new_psar:
                trend.iloc[i] = -1
                psar.iloc[i] = ep
                af = af_start
                ep = float(low.iloc[i])
            else:
                trend.iloc[i] = 1
                max_low = float(low.iloc[i - 1]) if i >= 2 else float(low.iloc[i])
                psar.iloc[i] = max(new_psar, max_low)
                if float(high.iloc[i]) > ep:
                    ep = float(high.iloc[i])
                    af = min(af + af_inc, af_max)
        else:  # -1
            if float(high.iloc[i]) >= new_psar:
                trend.iloc[i] = 1
                psar.iloc[i] = ep
                af = af_start
                ep = float(high.iloc[i])
            else:
                trend.iloc[i] = -1
                min_high = float(high.iloc[i - 1]) if i >= 2 else float(high.iloc[i])
                psar.iloc[i] = min(new_psar, min_high)
                if float(low.iloc[i]) < ep:
                    ep = float(low.iloc[i])
                    af = min(af + af_inc, af_max)

    return psar, trend


def _williams_r(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    hh = high.rolling(period, min_periods=period).max()
    ll = low.rolling(period, min_periods=period).min()
    return -100 * (hh - close) / (hh - ll).replace(0, np.nan)


def _cci(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 20) -> pd.Series:
    tp = (high + low + close) / 3
    sma = tp.rolling(period, min_periods=period).mean()
    mad = tp.rolling(period, min_periods=period).apply(
        lambda x: float(np.mean(np.abs(x - x.mean()))), raw=True
    )
    return (tp - sma) / (0.015 * mad).replace(0, np.nan)


def _stoch_rsi(close: pd.Series, period: int = 14, k_period: int = 3, d_period: int = 3):
    rsi = _rsi(close, period)
    rsi_min = rsi.rolling(period, min_periods=period).min()
    rsi_max = rsi.rolling(period, min_periods=period).max()
    raw = (rsi - rsi_min) / (rsi_max - rsi_min).replace(0, np.nan)
    k = raw.rolling(k_period, min_periods=k_period).mean() * 100
    d = k.rolling(d_period, min_periods=d_period).mean()
    return raw * 100, k, d


def _ichimoku(high: pd.Series, low: pd.Series, close: pd.Series):
    tenkan = (high.rolling(9, min_periods=9).max() + low.rolling(9, min_periods=9).min()) / 2
    kijun = (high.rolling(26, min_periods=26).max() + low.rolling(26, min_periods=26).min()) / 2
    senkou_a = ((tenkan + kijun) / 2).shift(26)
    senkou_b = ((high.rolling(52, min_periods=52).max() + low.rolling(52, min_periods=52).min()) / 2).shift(26)
    chikou = close.shift(-26)
    return tenkan, kijun, senkou_a, senkou_b, chikou


def _cmf(high: pd.Series, low: pd.Series, close: pd.Series,
         volume: pd.Series, period: int = 20) -> pd.Series:
    mfm = ((close - low) - (high - close)) / (high - low).replace(0, np.nan)
    mfv = mfm * volume
    return mfv.rolling(period, min_periods=period).sum() / volume.rolling(period, min_periods=period).sum().replace(0, np.nan)


def _vpt(close: pd.Series, volume: pd.Series) -> pd.Series:
    pct = close.pct_change().fillna(0)
    return (pct * volume).cumsum()


def _tsi(close: pd.Series, long_period: int = 25, short_period: int = 13) -> pd.Series:
    pc = close.diff()
    first = pc.ewm(span=long_period, adjust=False).mean()
    second = first.ewm(span=short_period, adjust=False).mean()
    first_abs = pc.abs().ewm(span=long_period, adjust=False).mean()
    second_abs = first_abs.ewm(span=short_period, adjust=False).mean()
    return 100 * second / second_abs.replace(0, np.nan)


# =============================================================================
# 4. 期货特有指标(OI / 资金流 / 综合评分)
# =============================================================================

def _oi_indicators(close: pd.Series, volume: pd.Series, oi: pd.Series) -> pd.DataFrame:
    out = pd.DataFrame(index=close.index)
    if oi is None or oi.empty:
        for c in ["oi_change", "oi_change_pct", "oi_ma5", "oi_ma20", "oi_position",
                  "oi_price_bull_div", "oi_price_bear_div", "oi_rsi14"]:
            out[c] = np.nan
        return out
    oi = oi.astype(float)
    out["oi_change"] = oi.diff()
    out["oi_change_pct"] = oi.pct_change() * 100
    out["oi_ma5"] = oi.rolling(5, min_periods=5).mean()
    out["oi_ma20"] = oi.rolling(20, min_periods=20).mean()
    oi_max20 = oi.rolling(20, min_periods=20).max()
    oi_min20 = oi.rolling(20, min_periods=20).min()
    out["oi_position"] = (oi - oi_min20) / (oi_max20 - oi_min20).replace(0, np.nan) * 100
    pc5 = close.diff(5)
    oi5 = oi.diff(5)
    out["oi_price_bull_div"] = ((pc5 < 0) & (oi5 > 0)).astype(int)
    out["oi_price_bear_div"] = ((pc5 > 0) & (oi5 < 0)).astype(int)
    out["oi_rsi14"] = _rsi(oi, 14)
    return out


def _money_flow(close: pd.Series, oi: pd.Series) -> pd.Series:
    if oi is None or oi.empty:
        return pd.Series(0.0, index=close.index)
    pc = close.diff()
    oi_c = oi.diff()
    mf = pd.Series(0.0, index=close.index)
    mf[(pc > 0) & (oi_c > 0)] = 1.0    # 多头建仓
    mf[(pc < 0) & (oi_c > 0)] = -1.0   # 空头建仓
    mf[(pc > 0) & (oi_c < 0)] = -0.5   # 空头平仓
    mf[(pc < 0) & (oi_c < 0)] = 0.5    # 多头平仓
    return mf


def _vol_oi_metrics(close: pd.Series, volume: pd.Series, oi: pd.Series) -> pd.DataFrame:
    out = pd.DataFrame(index=close.index)
    if oi is None or oi.empty or volume is None or volume.empty:
        for c in ["vol_oi_ratio", "vol_oi_ratio_ma20", "composite_score",
                  "oi_momentum_5d", "price_momentum_5d", "volume_momentum_5d"]:
            out[c] = np.nan
        return out
    ratio = volume.astype(float) / oi.astype(float).replace(0, np.nan)
    out["vol_oi_ratio"] = ratio
    out["vol_oi_ratio_ma20"] = ratio.rolling(20, min_periods=20).mean()
    pc = close.pct_change(5) * 100
    vc = volume.pct_change(5) * 100
    oc = oi.pct_change(5) * 100
    out["price_momentum_5d"] = pc
    out["volume_momentum_5d"] = vc
    out["oi_momentum_5d"] = oc
    # Z-score 化再加权
    def _z(s):
        m = s.rolling(20).mean()
        sd = s.rolling(20).std()
        return (s - m) / sd.replace(0, np.nan)
    out["composite_score"] = _z(pc) * 0.4 + _z(vc) * 0.3 + _z(oc) * 0.3
    return out


# =============================================================================
# 5. 计算全部指标(内部)— 返回带指标列的 DataFrame
# =============================================================================

def _compute_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """对规范化后的 df 计算全部技术指标。返回新 DataFrame。"""
    out = df.copy()
    close = out["close"].astype(float)
    high = out["high"].astype(float)
    low = out["low"].astype(float)
    vol = out["volume"].astype(float) if "volume" in out.columns else pd.Series(dtype=float)
    oi = out["open_interest"].astype(float) if "open_interest" in out.columns else pd.Series(dtype=float)
    open_ = out["open"].astype(float) if "open" in out.columns else close

    # ---- 均线 / 通道 ----
    out["ma20"] = _ma(close, 20)
    out["ma60"] = _ma(close, 60)
    out["ema20"] = _ema(close, 20)
    out["atr14"] = _atr(high, low, close, 14)
    boll_mid, boll_up, boll_low = _boll(close, 20, 2.0)
    out["boll_mid"] = boll_mid
    out["boll_up"] = boll_up
    out["boll_low"] = boll_low
    out["boll_bw"] = boll_up - boll_low

    # ---- 突破 / 回撤 ----
    out["hhv20"] = close.rolling(20, min_periods=20).max()
    out["llv20"] = close.rolling(20, min_periods=20).min()
    out["breakout_long20"] = (close > out["hhv20"]).astype(int)
    out["breakout_short20"] = (close < out["llv20"]).astype(int)
    out["pullback20_pct"] = (close - out["hhv20"]) / out["hhv20"].replace(0, np.nan)

    # ---- MACD / RSI / KDJ ----
    dif, dea, hist = _macd(close)
    out["macd"] = dif
    out["macd_signal"] = dea
    out["macd_hist"] = hist
    out["rsi14"] = _rsi(close, 14)
    k, d, j = _kdj(high, low, close)
    out["kdj_k"] = k
    out["kdj_d"] = d
    out["kdj_j"] = j

    # ---- ADX / DMI ----
    adx, pdi, mdi = _adx_dmi(high, low, close, 14)
    out["adx14"] = adx
    out["plus_di14"] = pdi
    out["minus_di14"] = mdi

    # ---- OBV / 量能 ----
    if not vol.empty:
        out["obv"] = _obv(close, vol)
        out["vol_ma20"] = vol.rolling(20, min_periods=20).mean()
        vol_std = vol.rolling(20, min_periods=20).std()
        out["vol_z20"] = (vol - out["vol_ma20"]) / vol_std.replace(0, np.nan)
    # ---- VWAP20(典型价近似)----
    if not vol.empty:
        tp = (high + low + close) / 3
        vs20 = vol.rolling(20, min_periods=20).sum()
        out["vwap20"] = (tp * vol).rolling(20, min_periods=20).sum() / vs20.replace(0, np.nan)

    # ---- K线特征 ----
    prev_close = close.shift(1)
    out["gap_pct"] = (open_ - prev_close) / prev_close.replace(0, np.nan)
    body = (close - open_).abs()
    upper_shadow = (high - pd.concat([open_, close], axis=1).max(axis=1)).clip(lower=0)
    lower_shadow = (pd.concat([open_, close], axis=1).min(axis=1) - low).clip(lower=0)
    out["upper_shadow_ratio"] = upper_shadow / body.replace(0, np.nan)
    out["lower_shadow_ratio"] = lower_shadow / body.replace(0, np.nan)

    # ---- ATR 比率与 180 日分位 ----
    atr_ratio = out["atr14"] / close.replace(0, np.nan)
    out["atr_ratio"] = atr_ratio
    out["atr_ratio_pctl180"] = atr_ratio.rolling(180, min_periods=60).apply(
        lambda s: float((s.dropna() <= s.iloc[-1]).mean()) if s.notna().any() else np.nan,
        raw=False,
    )
    # ---- 箱体(20日)----
    mid_box = (out["hhv20"] + out["llv20"]) / 2
    out["box20_flag"] = ((out["hhv20"] - out["llv20"]) / mid_box.replace(0, np.nan) < 0.03).astype(int)

    # ---- 高级指标 ----
    psar, psar_trend = _psar(high, low)
    out["psar"] = psar
    out["psar_trend"] = psar_trend
    out["williams_r14"] = _williams_r(high, low, close, 14)
    out["cci20"] = _cci(high, low, close, 20)
    stoch_raw, stoch_k, stoch_d = _stoch_rsi(close, 14)
    out["stoch_rsi"] = stoch_raw
    out["stoch_k"] = stoch_k
    out["stoch_d"] = stoch_d
    tenkan, kijun, senkou_a, senkou_b, chikou = _ichimoku(high, low, close)
    out["tenkan_sen"] = tenkan
    out["kijun_sen"] = kijun
    out["senkou_span_a"] = senkou_a
    out["senkou_span_b"] = senkou_b
    out["chikou_span"] = chikou
    out["kumo_thickness"] = (senkou_a - senkou_b).abs()
    if not vol.empty:
        out["cmf20"] = _cmf(high, low, close, vol, 20)
        out["vpt"] = _vpt(close, vol)
    out["tsi"] = _tsi(close)

    # ---- ADXR(14)----
    if "adx14" in out.columns:
        out["adxr14"] = (out["adx14"] + out["adx14"].shift(14)) / 2

    # ---- 期货特有 ----
    oi_df = _oi_indicators(close, vol, oi)
    for c in oi_df.columns:
        out[c] = oi_df[c]
    if not oi.empty:
        out["money_flow"] = _money_flow(close, oi)
        out["money_flow_ma5"] = out["money_flow"].rolling(5, min_periods=5).mean()
    flow_df = _vol_oi_metrics(close, vol, oi)
    for c in flow_df.columns:
        out[c] = flow_df[c]
    # ---- 波动率(20 日)----
    ret = close.pct_change()
    out["volatility_20d"] = ret.rolling(20, min_periods=20).std() * 100
    return out


# =============================================================================
# 6. 聚合:从带指标的 DataFrame 输出标准 schema Dict
# =============================================================================

def _safe_float(x) -> Optional[float]:
    try:
        if x is None:
            return None
        v = float(x)
        if np.isnan(v) or np.isinf(v):
            return None
        return v
    except (TypeError, ValueError):
        return None


def _safe_int(x) -> int:
    """NaN / None → 0;其余安全转 int。用于无 OI 时仍存在的布尔标志列。"""
    try:
        if x is None:
            return 0
        v = float(x)
        if np.isnan(v):
            return 0
        return int(v)
    except (TypeError, ValueError):
        return 0


def _zscore(series: pd.Series, window: int = 180) -> Optional[float]:
    """最近一值在最近 window 日内的 z-score。"""
    if series is None or series.empty:
        return None
    tail = series.dropna().tail(window)
    if len(tail) < 20:
        return None
    last = tail.iloc[-1]
    mu = tail.mean()
    sd = tail.std(ddof=0)
    if sd == 0 or np.isnan(sd):
        return None
    return float((last - mu) / sd)


def _slope(series: pd.Series, window: int = 20) -> Optional[float]:
    """最近 window 期的线性回归斜率(单位: 原值/期)。"""
    if series is None or series.empty:
        return None
    tail = series.dropna().tail(window)
    if len(tail) < 5:
        return None
    y = tail.values
    x = np.arange(len(y), dtype=float)
    n = len(y)
    x_mean = x.mean()
    y_mean = y.mean()
    denom = ((x - x_mean) ** 2).sum()
    if denom == 0:
        return None
    slope = float(((x - x_mean) * (y - y_mean)).sum() / denom)
    return slope


def _percentile_rank(series: pd.Series, window: int = 180) -> Optional[float]:
    """最近一值在 window 期内的分位(0~1)。"""
    if series is None or series.empty:
        return None
    tail = series.dropna().tail(window)
    if len(tail) < 20:
        return None
    last = tail.iloc[-1]
    return float((tail <= last).mean())


def _infer_trend(df_ind: pd.DataFrame) -> Dict[str, Any]:
    """根据 EMA20 vs MA60 推断趋势方向和强度。"""
    if df_ind.empty or df_ind["close"].isna().all():
        return {"direction": "neutral", "strength": 0.0}
    last = df_ind.iloc[-1]
    ema20 = last.get("ema20")
    ma60 = last.get("ma60")
    if pd.isna(ema20) or pd.isna(ma60):
        return {"direction": "neutral", "strength": 0.0}
    if ema20 > ma60:
        direction = "long"
    elif ema20 < ma60:
        direction = "short"
    else:
        direction = "neutral"
    base = abs(float(ema20) - float(ma60)) / max(abs(float(ma60)), 1e-9)
    strength = float(max(0.0, min(1.0, base)))
    return {"direction": direction, "strength": round(strength, 3)}


def _volatility_regime(df_ind: pd.DataFrame) -> Dict[str, Any]:
    """波动率状态: ATR / close 比率 + 180 日分位。"""
    if df_ind.empty or df_ind["close"].isna().all():
        return {"atr": None, "regime": "low", "atr_ratio_pctl180": None}
    last = df_ind.iloc[-1]
    atr_val = _safe_float(last.get("atr14"))
    close_val = _safe_float(last.get("close"))
    pctl = _safe_float(last.get("atr_ratio_pctl180"))
    if atr_val is None or close_val is None or close_val == 0:
        return {"atr": atr_val, "regime": "low", "atr_ratio_pctl180": pctl}
    ratio = atr_val / close_val
    # 简化:ratio > 0.02 视为高波动(与参考项目一致)
    regime = "high" if ratio > 0.02 else "low"
    return {"atr": atr_val, "regime": regime, "atr_ratio_pctl180": pctl}


def _oi_divergence(df_ind: pd.DataFrame, window: int = 5) -> str:
    """5 日价格 vs OI 同向 / 反向 → confirm / conflict / neutral。"""
    if df_ind.empty or "open_interest" not in df_ind.columns:
        return "neutral"
    if len(df_ind) < window + 1:
        return "neutral"
    pc = df_ind["close"].astype(float).diff(window).iloc[-1]
    oi = df_ind["open_interest"].astype(float)
    if oi.isna().all():
        return "neutral"
    oi_chg = oi.diff(window).iloc[-1]
    if pd.isna(pc) or pd.isna(oi_chg):
        return "neutral"
    if pc > 0 and oi_chg > 0:
        return "confirm"
    if (pc > 0 and oi_chg < 0) or (pc < 0 and oi_chg > 0):
        return "conflict"
    return "neutral"


def _generate_triggers(df_ind: pd.DataFrame) -> List[str]:
    """基于最新一根 K 线 + 衍生指标生成可读信号列表。"""
    if df_ind.empty or df_ind["close"].isna().all():
        return []
    last = df_ind.iloc[-1]
    prev = df_ind.iloc[-2] if len(df_ind) >= 2 else None
    triggers: List[str] = []

    close = last.get("close")
    ma20 = last.get("ma20")
    ma60 = last.get("ma60")
    if pd.notna(close) and pd.notna(ma20) and pd.notna(ma60):
        if close > ma20 > ma60:
            triggers.append("价在MA20/MA60上方，趋势延续条件")
        if close < ma20 < ma60:
            triggers.append("价在MA20/MA60下方，空头延续条件")
    boll_up = last.get("boll_up")
    boll_low = last.get("boll_low")
    if pd.notna(close) and pd.notna(boll_up) and pd.notna(boll_low):
        if close > boll_up:
            triggers.append("收盘上穿BOLL上轨，动能偏强/警惕回归")
        if close < boll_low:
            triggers.append("收盘下穿BOLL下轨，动能偏弱/警惕反弹")

    if _safe_int(last.get("breakout_long20", 0)) == 1:
        triggers.append("突破20日新高")
    if _safe_int(last.get("breakout_short20", 0)) == 1:
        triggers.append("跌破20日新低")

    macd_v = last.get("macd")
    macd_s = last.get("macd_signal")
    if pd.notna(macd_v) and pd.notna(macd_s):
        if macd_v > macd_s:
            triggers.append("MACD金叉")
        elif macd_v < macd_s:
            triggers.append("MACD死叉")
    macd_h = last.get("macd_hist")
    if prev is not None and pd.notna(macd_h) and pd.notna(prev.get("macd_hist")):
        if macd_h > prev["macd_hist"]:
            triggers.append("MACD柱体放大")
        elif macd_h < prev["macd_hist"]:
            triggers.append("MACD柱体缩小")

    rsi_v = last.get("rsi14")
    if pd.notna(rsi_v):
        if rsi_v >= 70:
            triggers.append("RSI超买区间(>=70)")
        elif rsi_v <= 30:
            triggers.append("RSI超卖区间(<=30)")

    adx_v = last.get("adx14")
    pdi = last.get("plus_di14")
    mdi = last.get("minus_di14")
    if pd.notna(adx_v):
        if adx_v >= 25:
            triggers.append("趋势强（ADX>=25）")
        else:
            triggers.append("趋势弱（ADX<25）")
    if pd.notna(pdi) and pd.notna(mdi):
        if pdi > mdi:
            triggers.append("多头占优（+DI>-DI）")
        elif pdi < mdi:
            triggers.append("空头占优（+DI<-DI）")

    kdjk = last.get("kdj_k")
    kdjd = last.get("kdj_d")
    kdjj = last.get("kdj_j")
    if pd.notna(kdjk) and pd.notna(kdjd):
        if kdjk > kdjd:
            triggers.append("KDJ金叉")
        elif kdjk < kdjd:
            triggers.append("KDJ死叉")
    if pd.notna(kdjj):
        if kdjj >= 100:
            triggers.append("KDJ超买(J>=100)")
        elif kdjj <= 0:
            triggers.append("KDJ超卖(J<=0)")

    vol_z = last.get("vol_z20")
    if pd.notna(vol_z):
        if vol_z >= 2:
            triggers.append("放量（VOL_Z>=2）")
        elif vol_z <= -2:
            triggers.append("缩量（VOL_Z<=-2）")

    # 影线 / 缺口
    if pd.notna(last.get("upper_shadow_ratio")) and last.get("upper_shadow_ratio") >= 2:
        triggers.append("长上影（可能遇阻）")
    if pd.notna(last.get("lower_shadow_ratio")) and last.get("lower_shadow_ratio") >= 2:
        triggers.append("长下影（可能获支撑）")
    if pd.notna(last.get("gap_pct")):
        if last["gap_pct"] >= 0.01:
            triggers.append("向上跳空(>=1%)")
        elif last["gap_pct"] <= -0.01:
            triggers.append("向下跳空(<=-1%)")

    if _safe_int(last.get("box20_flag", 0)) == 1:
        triggers.append("箱体盘整(20日)")

    # PSAR
    psar_v = last.get("psar")
    psar_t = last.get("psar_trend")
    if pd.notna(psar_v) and pd.notna(psar_t) and pd.notna(close):
        if psar_t == 1 and close > psar_v:
            triggers.append("PSAR上升趋势确认")
        elif psar_t == -1 and close < psar_v:
            triggers.append("PSAR下降趋势确认")
        else:
            triggers.append("PSAR趋势反转信号")

    # Williams %R
    wr = last.get("williams_r14")
    if pd.notna(wr):
        if wr >= -20:
            triggers.append("Williams %R超买区间(>=-20)")
        elif wr <= -80:
            triggers.append("Williams %R超卖区间(<=-80)")

    # CCI
    cci = last.get("cci20")
    if pd.notna(cci):
        if cci >= 100:
            triggers.append("CCI超买区间(>=100)")
        elif cci <= -100:
            triggers.append("CCI超卖区间(<=-100)")

    # Stoch RSI
    sk = last.get("stoch_k")
    sd_ = last.get("stoch_d")
    if pd.notna(sk) and pd.notna(sd_):
        if sk > sd_:
            triggers.append("Stoch RSI金叉")
        elif sk < sd_:
            triggers.append("Stoch RSI死叉")
        if sk >= 80:
            triggers.append("Stoch RSI超买(>=80)")
        elif sk <= 20:
            triggers.append("Stoch RSI超卖(<=20)")

    # Ichimoku 云层
    senkou_a = last.get("senkou_span_a")
    senkou_b = last.get("senkou_span_b")
    if pd.notna(senkou_a) and pd.notna(senkou_b) and pd.notna(close):
        cloud_top = max(senkou_a, senkou_b)
        cloud_bottom = min(senkou_a, senkou_b)
        if close > cloud_top:
            triggers.append("价格在云层上方")
        elif close < cloud_bottom:
            triggers.append("价格在云层下方")
        else:
            triggers.append("价格在云层内部")

    # CMF
    cmf = last.get("cmf20")
    if pd.notna(cmf):
        if cmf > 0.1:
            triggers.append("CMF强势买入压力(>0.1)")
        elif cmf < -0.1:
            triggers.append("CMF强势卖出压力(<-0.1)")

    # TSI
    tsi = last.get("tsi")
    if pd.notna(tsi):
        if tsi > 25:
            triggers.append("TSI强势上升(>25)")
        elif tsi < -25:
            triggers.append("TSI强势下降(<-25)")

    # OI / 资金流
    oi_chg_pct = last.get("oi_change_pct")
    if pd.notna(oi_chg_pct):
        if oi_chg_pct > 5:
            triggers.append("持仓量大幅增加(>5%)")
        elif oi_chg_pct < -5:
            triggers.append("持仓量大幅减少(<-5%)")
    oi_pos = last.get("oi_position")
    if pd.notna(oi_pos):
        if oi_pos >= 80:
            triggers.append("持仓量处于高位(>=80%)")
        elif oi_pos <= 20:
            triggers.append("持仓量处于低位(<=20%)")
    if _safe_int(last.get("oi_price_bull_div", 0)) == 1:
        triggers.append("价格-持仓量看涨背离")
    if _safe_int(last.get("oi_price_bear_div", 0)) == 1:
        triggers.append("价格-持仓量看跌背离")

    mf_ma5 = last.get("money_flow_ma5")
    if pd.notna(mf_ma5):
        if mf_ma5 > 0.5:
            triggers.append("资金净流入(多头主导)")
        elif mf_ma5 < -0.5:
            triggers.append("资金净流出(空头主导)")

    comp = last.get("composite_score")
    if pd.notna(comp):
        if comp > 1.5:
            triggers.append("期货综合评分强势(>1.5)")
        elif comp < -1.5:
            triggers.append("期货综合评分弱势(<-1.5)")

    vol_oi_ratio = last.get("vol_oi_ratio")
    vol_oi_ma = last.get("vol_oi_ratio_ma20")
    if pd.notna(vol_oi_ratio) and pd.notna(vol_oi_ma):
        if vol_oi_ratio > vol_oi_ma * 1.5:
            triggers.append("换手率异常增高")
        elif vol_oi_ratio < vol_oi_ma * 0.5:
            triggers.append("换手率异常降低")

    return triggers


def _snapshot(df_ind: pd.DataFrame) -> Dict[str, Any]:
    """把最后一行的所有指标收集为 snapshot(LLM 友好)。"""
    if df_ind.empty or df_ind["close"].isna().all():
        return {}
    last = df_ind.iloc[-1]
    cols = [
        "close", "ma20", "ma60", "ema20", "atr14",
        "rsi14", "macd", "macd_signal", "macd_hist",
        "boll_up", "boll_mid", "boll_low", "boll_bw",
        "plus_di14", "minus_di14", "adx14", "adxr14",
        "kdj_k", "kdj_d", "kdj_j",
        "vol_z20", "vwap20", "obv",
        "atr_ratio", "atr_ratio_pctl180",
        "psar", "psar_trend", "williams_r14", "cci20",
        "stoch_rsi", "stoch_k", "stoch_d",
        "tenkan_sen", "kijun_sen", "senkou_span_a", "senkou_span_b",
        "cmf20", "vpt", "tsi",
        "oi_change_pct", "oi_ma20", "oi_position", "oi_rsi14",
        "money_flow_ma5", "vol_oi_ratio", "vol_oi_ratio_ma20",
        "composite_score", "volatility_20d", "gap_pct",
    ]
    out: Dict[str, Any] = {}
    for c in cols:
        if c not in df_ind.columns:
            continue
        v = last.get(c)
        if c in ("psar_trend",):
            out[c] = int(v) if pd.notna(v) else None
        elif c == "box20_flag":
            out[c] = int(v) if pd.notna(v) else 0
        else:
            out[c] = _safe_float(v)
    return out


def _quality(df: pd.DataFrame, lookback: Optional[int] = None) -> Dict[str, Any]:
    """数据质量:行数、缺失率、新鲜度(距今天的天数)。"""
    if df is None or df.empty or "date" not in df.columns:
        return {"rows": 0, "coverage": 0.0, "data_freshness_days": None}
    rows = int(len(df))
    coverage = float(df["close"].notna().mean()) if "close" in df.columns else 0.0
    last_date = df["date"].iloc[-1]
    freshness = None
    try:
        if pd.notna(last_date):
            today = pd.Timestamp(datetime.now().date())
            if isinstance(last_date, pd.Timestamp):
                freshness = int((today - last_date).days)
            else:
                freshness = int((today - pd.Timestamp(last_date)).days)
    except Exception:
        freshness = None
    return {"rows": rows, "coverage": round(coverage, 3), "data_freshness_days": freshness}


def _summarize_timeframe(df_ind: pd.DataFrame, df_raw: pd.DataFrame) -> Dict[str, Any]:
    """对单个时间周期的指标 DataFrame 输出标准 schema Dict。"""
    trend = _infer_trend(df_ind)
    vol = _volatility_regime(df_ind)
    oi_div = _oi_divergence(df_ind)
    triggers = _generate_triggers(df_ind)
    snap = _snapshot(df_ind)
    # latest: 简化版(只放最常用 ~20 项)
    latest_keys = ["close", "ma20", "ma60", "ema20", "atr14", "rsi14", "macd", "macd_signal",
                   "macd_hist", "boll_up", "boll_mid", "boll_low", "adx14", "kdj_k",
                   "kdj_d", "kdj_j", "oi_change_pct", "composite_score",
                   "atr_ratio_pctl180", "psar_trend"]
    latest = {k: snap[k] for k in latest_keys if k in snap}
    # stats: zscore_180d + slope_20d
    stats = {
        "close_zscore_180d": _zscore(df_ind["close"], 180) if "close" in df_ind.columns else None,
        "close_slope_20d": _slope(df_ind["close"], 20) if "close" in df_ind.columns else None,
        "volume_zscore_180d": _zscore(df_ind["volume"], 180) if "volume" in df_ind.columns else None,
        "oi_zscore_180d": _zscore(df_ind["open_interest"], 180) if "open_interest" in df_ind.columns else None,
    }
    return {
        "latest": latest,
        "stats": stats,
        "signals": triggers,
        "snapshot": snap,
        "quality": _quality(df_raw),
        "trend": trend,
        "volatility": vol,
        "oi_divergence": oi_div,
    }


def _resample_to_weekly(df: pd.DataFrame) -> pd.DataFrame:
    """日线 → 周线(OHLCV 聚合)。需先按 date 排序。"""
    if df is None or df.empty or "date" not in df.columns:
        return pd.DataFrame()
    tmp = df.copy()
    tmp["date"] = pd.to_datetime(tmp["date"])
    tmp = tmp.set_index("date").sort_index()
    agg: Dict[str, str] = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
    }
    if "volume" in tmp.columns:
        agg["volume"] = "sum"
    if "open_interest" in tmp.columns:
        agg["open_interest"] = "last"
    wk = tmp.resample("W-FRI").agg(agg)
    wk = wk.dropna(subset=["close"]).reset_index()
    return wk


# =============================================================================
# 7. 公开入口:compute_technical_metrics
# =============================================================================

def compute_technical_metrics(
    df: pd.DataFrame,
    include_weekly: bool = True,
    weekly_min_rows: int = 30,
) -> Dict[str, Any]:
    """商品期货技术面特征主入口。

    Args:
        df: OHLCV DataFrame(provider 输出或测试 fixture)。
            列名兼容中文(日期/开盘价/最高价/最低价/收盘价/成交量/持仓量)
            与英文(date/open/high/low/close/volume/open_interest)。
        include_weekly: 是否计算周线维度(默认 True)。
        weekly_min_rows: 周线计算所需的最少日线行数(默认 30)。

    Returns:
        标准输出 Dict:
        {
          "daily":   {latest, stats, signals, snapshot, quality, trend, volatility, oi_divergence},
          "weekly":  {同 daily; 若日线数据不足则为 None},
          "combined":{direction, strength, triggers, oi_divergence, volatility,
                      signals_multi_tf},
          "quality": {rows, coverage, data_freshness_days}
        }

    Notes:
        - 纯函数,无 LLM,无外部 API
        - 数据不足时返回 None 字段 + quality.rows < 60 时附带 warning
    """
    if df is None or df.empty:
        return _empty_result(reason="empty_input")
    try:
        df_norm = normalize_columns(df)
    except ValueError as e:
        return _empty_result(reason=str(e))
    if df_norm.empty:
        return _empty_result(reason="empty_after_normalize")
    # 按日期排序
    if "date" in df_norm.columns:
        df_norm = df_norm.sort_values("date").reset_index(drop=True)

    # ---- 日线 ----
    df_ind_d = _compute_all_indicators(df_norm)
    daily_summary = _summarize_timeframe(df_ind_d, df_norm)

    # ---- 周线 ----
    weekly_summary: Optional[Dict[str, Any]] = None
    if include_weekly and len(df_norm) >= weekly_min_rows:
        wk = _resample_to_weekly(df_norm)
        if not wk.empty and len(wk) >= 10:
            wk_ind = _compute_all_indicators(wk)
            weekly_summary = _summarize_timeframe(wk_ind, wk)

    combined = _combine(daily_summary, weekly_summary)
    return {
        "daily": daily_summary,
        "weekly": weekly_summary,
        "combined": combined,
        "quality": _quality(df_norm),
    }


def _combine(daily: Dict[str, Any], weekly: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """综合日 / 周两周期,给出最终方向、强度、信号。"""
    d_dir = daily["trend"]["direction"]
    w_dir = weekly["trend"]["direction"] if weekly else None
    # 方向取双方一致方向;不一致时为 conflict
    if w_dir is None:
        direction = d_dir
        strength = daily["trend"]["strength"]
    elif d_dir == w_dir:
        direction = d_dir
        # 取日 / 周强度中较大者,综合 0.5 倍日 + 1.0 倍周加权
        strength = round(min(1.0, daily["trend"]["strength"] * 0.5 + weekly["trend"]["strength"] * 1.0), 3)
    else:
        direction = "neutral"
        strength = round(min(daily["trend"]["strength"], weekly["trend"]["strength"]), 3)

    # 触发信号去重(保留出现顺序)
    seen = set()
    triggers: List[str] = []
    for src in (daily["signals"], weekly["signals"] if weekly else []):
        for s in src:
            if s not in seen:
                seen.add(s)
                triggers.append(s)

    # OI 背离:daily 为准,weekly 作修正
    oi_div = daily["oi_divergence"]
    if weekly and weekly["oi_divergence"] in ("confirm", "conflict"):
        if weekly["oi_divergence"] != oi_div:
            oi_div = "conflict" if oi_div == "neutral" else oi_div

    # 波动率:取较严格者
    vol_regime = daily["volatility"]["regime"]
    if weekly and weekly["volatility"]["regime"] == "high":
        vol_regime = "high"

    return {
        "direction": direction,
        "strength": strength,
        "signals": triggers,
        "oi_divergence": oi_div,
        "volatility": {
            "atr": daily["volatility"]["atr"],
            "regime": vol_regime,
            "atr_ratio_pctl180": daily["volatility"]["atr_ratio_pctl180"],
        },
        "signals_multi_tf": {
            "daily": daily["signals"],
            "weekly": weekly["signals"] if weekly else [],
        },
    }


def _empty_result(reason: str) -> Dict[str, Any]:
    empty_tf: Dict[str, Any] = {
        "latest": {}, "stats": {}, "signals": [], "snapshot": {}, "quality": {},
        "trend": {"direction": "neutral", "strength": 0.0},
        "volatility": {"atr": None, "regime": "low", "atr_ratio_pctl180": None},
        "oi_divergence": "neutral",
    }
    return {
        "daily": {**empty_tf, "signals": [f"无数据: {reason}"]},
        "weekly": None,
        "combined": {
            "direction": "neutral",
            "strength": 0.0,
            "signals": [f"无数据: {reason}"],
            "oi_divergence": "neutral",
            "volatility": {"atr": None, "regime": "low", "atr_ratio_pctl180": None},
            "signals_multi_tf": {"daily": [], "weekly": []},
        },
        "quality": {"rows": 0, "coverage": 0.0, "data_freshness_days": None, "reason": reason},
    }


# =============================================================================
# 8. 多合约入口: 主力连续 + 指数合约 + 移仓检测
# =============================================================================

def _compute_long_term_trend(index_df: pd.DataFrame) -> Dict[str, Any]:
    """从指数合约 DataFrame 计算长期趋势。

    Args:
        index_df: 指数合约 OHLCV DataFrame

    Returns:
        {
            "ma60": float or None,
            "ma120": float or None,
            "long_term_trend": "bullish|bearish|neutral",
            "quality": {rows, coverage, ...},
        }
    """
    if index_df is None or index_df.empty:
        return {
            "ma60": None,
            "ma120": None,
            "long_term_trend": "neutral",
            "quality": {"rows": 0, "coverage": 0.0, "data_freshness_days": None},
        }

    try:
        df_norm = normalize_columns(index_df)
    except ValueError:
        return {"ma60": None, "ma120": None, "long_term_trend": "neutral",
                "quality": {"rows": 0, "coverage": 0.0, "data_freshness_days": None}}

    if df_norm.empty or "close" not in df_norm.columns:
        return {"ma60": None, "ma120": None, "long_term_trend": "neutral",
                "quality": _quality(df_norm) if not df_norm.empty else {"rows": 0, "coverage": 0.0, "data_freshness_days": None}}

    close = df_norm["close"].astype(float)
    ma60 = _ma(close, 60).iloc[-1] if len(close) >= 60 else None
    ma120 = _ma(close, 120).iloc[-1] if len(close) >= 120 else None

    # 判断长期趋势: MA60 与 MA120 的位置关系
    if ma60 is not None and ma120 is not None:
        if pd.notna(ma60) and pd.notna(ma120):
            if ma60 > ma120:
                long_term_trend = "bullish"
            elif ma60 < ma120:
                long_term_trend = "bearish"
            else:
                long_term_trend = "neutral"
        else:
            long_term_trend = "neutral"
    else:
        long_term_trend = "neutral"

    return {
        "ma60": _safe_float(ma60),
        "ma120": _safe_float(ma120),
        "long_term_trend": long_term_trend,
        "quality": _quality(df_norm),
    }


def _compute_relative_strength(
    main_close: pd.Series,
    index_close: pd.Series,
    window: int = 20,
) -> Optional[float]:
    """主力合约相对指数合约的强弱。

    计算主力/指数比值在 window 期的 z-score。
    正值 = 主力比指数更强(涨得多/跌得少), 负值 = 主力更弱。

    Args:
        main_close: 主力连续合约收盘价序列
        index_close: 指数合约收盘价序列
        window: 计算窗口(默认 20 日)

    Returns:
        float(z-score) 或 None(数据不足)
    """
    if main_close is None or index_close is None:
        return None
    main_s = main_close.astype(float).dropna()
    index_s = index_close.astype(float).dropna()
    if main_s.empty or index_s.empty:
        return None
    # 对齐索引后取比值
    ratio = (main_s / index_s.reindex(main_s.index, method="ffill")) - 1.0
    ratio = ratio.dropna().tail(window)
    if len(ratio) < 5:
        return None
    last = float(ratio.iloc[-1])
    mu = float(ratio.mean())
    sd = float(ratio.std(ddof=0))
    if sd == 0 or np.isnan(sd):
        return None
    return round((last - mu) / sd, 3)


def _detect_rollover(df: pd.DataFrame) -> Dict[str, Any]:
    """从主力连续合约 DataFrame 检测移仓换月。

    Args:
        df: 主力连续合约 OHLCV DataFrame(已含 rollover_date 标记列)

    Returns:
        {
            "detected": bool,
            "description": str,
            "rollover_dates": List[str],  # 换月日期列表
            "recent_rollover": bool,       # 最近 5 天内是否有换月
        }
    """
    if df is None or df.empty:
        return {"detected": False, "description": "无数据", "rollover_dates": [], "recent_rollover": False}

    try:
        df_norm = normalize_columns(df)
    except ValueError:
        return {"detected": False, "description": "列名规范化失败", "rollover_dates": [], "recent_rollover": False}

    # 检查 rollover_date 列
    rollover_col = None
    for candidate in ("rollover_date", "rollover"):
        if candidate in df_norm.columns:
            rollover_col = candidate
            break

    if rollover_col is None:
        return {"detected": False, "description": "无换月标记列", "rollover_dates": [], "recent_rollover": False}

    dates = df_norm[df_norm[rollover_col].astype(bool)]
    if dates.empty:
        return {"detected": False, "description": "未检测到换月", "rollover_dates": [], "recent_rollover": False}

    rollover_dates = []
    if "date" in dates.columns:
        try:
            rollover_dates = [str(d.date()) if hasattr(d, "date") else str(d) for d in dates["date"].tolist()]
        except Exception:
            rollover_dates = []

    # 最近 5 天是否有换月
    recent_rollover = False
    if rollover_dates and "date" in df_norm.columns:
        try:
            last_date = df_norm["date"].iloc[-1]
            if pd.notna(last_date):
                last_dt = pd.Timestamp(last_date)
                for rd in rollover_dates:
                    try:
                        rd_dt = pd.Timestamp(rd)
                        if 0 <= (last_dt - rd_dt).days <= 5:
                            recent_rollover = True
                            break
                    except Exception:
                        continue
        except Exception:
            pass

    n = len(rollover_dates)
    if n == 1:
        description = f"检测到 1 次换月({rollover_dates[-1]})"
    else:
        description = f"检测到 {n} 次换月,最近一次: {rollover_dates[-1]}"

    return {
        "detected": True,
        "description": description,
        "rollover_dates": rollover_dates,
        "recent_rollover": recent_rollover,
    }


def _combine_multi_contract(
    main_combined: Dict[str, Any],
    index_trend: Dict[str, Any],
    rollover: Dict[str, Any],
) -> Dict[str, Any]:
    """综合主力连续 + 指数合约 + 移仓状态, 给出最终方向、强度、信号。

    Args:
        main_combined: compute_technical_metrics 返回的 combined dict
        index_trend: _compute_long_term_trend 返回的指数趋势
        rollover: _detect_rollover 返回的移仓状态

    Returns:
        {direction, strength, signals, oi_divergence, volatility,
         main_index_alignment, rollover_status, signals_multi_tf}
    """
    # 基础方向从主力连续继承
    direction = main_combined.get("direction", "neutral")
    strength = main_combined.get("strength", 0.0)
    signals = list(main_combined.get("signals", []) or [])

    # 主力-指数一致性判断
    main_dir = direction  # "long" / "short" / "neutral"
    index_dir = index_trend.get("long_term_trend", "neutral")  # "bullish" / "bearish" / "neutral"

    # 映射 index 方向到统一方向
    index_dir_mapped = {"bullish": "long", "bearish": "short"}.get(index_dir, "neutral")

    if main_dir != "neutral" and index_dir_mapped != "neutral":
        if main_dir == index_dir_mapped:
            main_index_alignment = "aligned"
        else:
            main_index_alignment = "divergent"
    else:
        main_index_alignment = "partial"

    # 若主力-指数背离, 追加信号说明
    if main_index_alignment == "divergent":
        signals.append(f"主力{main_dir} vs 指数{index_dir_mapped}, 方向背离, 需警惕")

    # 移仓追加信号
    if rollover.get("detected") and rollover.get("recent_rollover"):
        signals.append(f"近期换月({rollover.get('description','')}), 历史信号可能因换月而失真")

    # 去重
    seen = set()
    unique_signals = []
    for s in signals:
        if s not in seen:
            seen.add(s)
            unique_signals.append(s)

    return {
        "direction": direction,
        "strength": strength,
        "signals": unique_signals,
        "oi_divergence": main_combined.get("oi_divergence", "neutral"),
        "volatility": main_combined.get("volatility", {"atr": None, "regime": "low", "atr_ratio_pctl180": None}),
        "main_index_alignment": main_index_alignment,
        "rollover_status": {
            "detected": rollover.get("detected", False),
            "description": rollover.get("description", ""),
            "recent_rollover": rollover.get("recent_rollover", False),
        },
        "signals_multi_tf": main_combined.get("signals_multi_tf", {"daily": [], "weekly": []}),
    }


def compute_technical_metrics_multi_contract(
    main_df: pd.DataFrame,
    index_df: Optional[pd.DataFrame] = None,
    include_weekly: bool = True,
    weekly_min_rows: int = 30,
) -> Dict[str, Any]:
    """商品期货技术面多合约特征主入口。

    基于品种级分析, 内部自动处理:
      - 主力连续合约(primary): 全部技术指标基于此计算
      - 指数合约(auxiliary): 长期趋势验证(MA60/MA120), 可选
      - 移仓换月检测: 从主力连续换月标记提取

    Args:
        main_df: 主力连续合约 OHLCV DataFrame
        index_df: 指数合约 OHLCV DataFrame(可选, None 时跳过指数分析)
        include_weekly: 是否计算周线维度(默认 True)
        weekly_min_rows: 周线计算所需的最少日线行数(默认 30)

    Returns:
        {
            "main_continuous": {         # 主力连续合约全量指标
                "symbol": str or None,
                "daily": {...},
                "weekly": {...},
            },
            "index_contract": {           # 指数合约长期趋势(或 None)
                "symbol": str or None,
                "ma60": float or None,
                "ma120": float or None,
                "long_term_trend": "bullish|bearish|neutral",
                "relative_strength": float or None,
                "quality": {...},
            },
            "rollover": {                 # 移仓换月检测
                "detected": bool,
                "description": str,
                "rollover_dates": List[str],
                "recent_rollover": bool,
            },
            "combined": {                 # 综合判断(含 main-index alignment)
                "direction": "long|short|neutral",
                "strength": 0.0-1.0,
                "signals": [...],
                "oi_divergence": "confirm|conflict|neutral",
                "volatility": {...},
                "main_index_alignment": "aligned|divergent|partial",
                "rollover_status": {...},
                "signals_multi_tf": {...},
            },
            "quality": {                  # 数据质量
                "rows": int,
                "main_continuous_available": bool,
                "index_contract_available": bool,
            },
        }
    """
    # ---- 1. 主力连续合约分析 ----
    main_result = compute_technical_metrics(
        main_df,
        include_weekly=include_weekly,
        weekly_min_rows=weekly_min_rows,
    )

    # ---- 2. 指数合约长期趋势 ----
    index_trend = _compute_long_term_trend(index_df) if index_df is not None else {
        "ma60": None, "ma120": None, "long_term_trend": "neutral",
        "quality": {"rows": 0, "coverage": 0.0, "data_freshness_days": None},
    }

    # 相对强弱(主力 vs 指数)
    rel_strength = None
    if index_df is not None and not index_df.empty and not main_df.empty:
        try:
            main_norm = normalize_columns(main_df)
            index_norm = normalize_columns(index_df)
            if "close" in main_norm.columns and "close" in index_norm.columns:
                rel_strength = _compute_relative_strength(
                    main_norm["close"], index_norm["close"]
                )
        except Exception:
            pass

    # ---- 3. 移仓换月检测 ----
    rollover = _detect_rollover(main_df)

    # ---- 4. 综合判断 ----
    combined = _combine_multi_contract(
        main_result.get("combined", {}),
        index_trend,
        rollover,
    )

    # ---- 5. 质量汇总 ----
    main_quality = main_result.get("quality", {})
    index_quality = index_trend.get("quality", {})
    total_rows = (main_quality.get("rows", 0) or 0) + (index_quality.get("rows", 0) or 0)

    return {
        "main_continuous": {
            "daily": main_result.get("daily", {}),
            "weekly": main_result.get("weekly"),
        },
        "index_contract": {
            **index_trend,
            "relative_strength": rel_strength,
        },
        "rollover": rollover,
        "combined": combined,
        "quality": {
            "rows": total_rows,
            "main_continuous_available": bool(main_quality.get("rows", 0)),
            "index_contract_available": bool(index_quality.get("rows", 0)),
        },
    }


__all__ = [
    "compute_technical_metrics",
    "compute_technical_metrics_multi_contract",
    "normalize_columns",
]
