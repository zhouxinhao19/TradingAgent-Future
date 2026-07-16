"""
positioning.py — 商品期货持仓/拥挤度特征模块 (Phase 3b-i)

输入: 来自 `AkshareFuturesProvider.get_position_rank(exchange, date)` 或
      `app/services/commodity/unified_commodity_service` 聚合后的 DataFrame。
      期望列(中文 / 英文):
        日期/date, 品种/symbol,
        long_top20 / long_open_interest_top20,
        short_top20 / short_open_interest_top20,
        total_oi / total_open_interest(可选),
        net_long_top20(可选,缺则 long_top20 - short_top20)

      也接受 Dict[symbol, DataFrame] 形式(provider 原始返回),此时传入 `symbol` 选择品种。

输出: 标准 schema Dict(含多空双边/多空比/连续变化/价格对齐)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

import numpy as np
import pandas as pd

from tradingagents.features.commodity import _helpers as h


def _coerce_input(
    df_or_dict: Union[pd.DataFrame, Dict[str, pd.DataFrame], None],
    symbol: Optional[str],
) -> pd.DataFrame:
    """统一输入: DataFrame 直接用;Dict 按 symbol 匹配品种,多合约时选数据最多的(主力合约);否则返回空。"""
    if df_or_dict is None:
        return pd.DataFrame()
    if isinstance(df_or_dict, dict):
        if not df_or_dict:
            return pd.DataFrame()
        if symbol is None:
            symbol = next(iter(df_or_dict.keys()))
        # 优先精确匹配 key
        if symbol in df_or_dict:
            return df_or_dict[symbol]
        # 按 underlying symbol 模糊匹配(如 'au2612' → 'AU')
        from tradingagents.utils.commodity_utils import CommodityUtils
        sym_upper = symbol.upper()
        candidates = []
        for key, val in df_or_dict.items():
            underlying = (CommodityUtils.get_underlying_symbol(key) or "").upper()
            if underlying == sym_upper:
                candidates.append((key, val))
        if not candidates:
            return pd.DataFrame()
        if len(candidates) == 1:
            return candidates[0][1]
        # 多合约匹配:选数据行数最多的(主力合约数据最丰富)
        candidates.sort(key=lambda kv: len(kv[1]) if kv[1] is not None else 0, reverse=True)
        best_key, best_df = candidates[0]
        if len(candidates) > 1:
            from tradingagents.utils.logging_init import get_logger
            get_logger("default").info(
                f"📊 _coerce_input: 品种 {symbol} 有 {len(candidates)} 个合约匹配,"
                f"选主力 {best_key}({len(best_df)} 行)"
            )
        return best_df
    if isinstance(df_or_dict, pd.DataFrame):
        return df_or_dict
    return pd.DataFrame()


def _prepare(df: pd.DataFrame, symbol: Optional[str]) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = h.normalize_columns(df)
    if symbol and "symbol" in out.columns:
        # 用 underlying symbol 匹配(如 'AU2612' → 'AU')
        from tradingagents.utils.commodity_utils import CommodityUtils
        sym_upper = symbol.upper()
        out = out[out["symbol"].astype(str).str.upper().apply(
            lambda s: (CommodityUtils.get_underlying_symbol(s) or "").upper() == sym_upper
        )].copy()
    out = h.ensure_columns(
        out,
        ["date", "long_top20", "short_top20", "total_oi", "net_long_top20"],
    )
    for c in ["long_top20", "short_top20", "total_oi", "net_long_top20"]:
        out[c] = h.to_numeric(out[c])
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"], errors="coerce")
        # 仅当 date 列不全为 NaT 时才按日期过滤
        if out["date"].notna().any():
            out = out.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        else:
            # 无日期数据时,用行号作伪日期(保留所有行)
            out = out.drop(columns=["date"])
            out["date"] = pd.Timestamp.now().normalize()
    if "net_long_top20" not in out.columns or out["net_long_top20"].isna().all():
        if {"long_top20", "short_top20"}.issubset(out.columns):
            out["net_long_top20"] = out["long_top20"] - out["short_top20"]
    return out


def _concentration(data: pd.DataFrame) -> pd.Series:
    """前 20 名集中度:(long + short) / (2 * total_oi)。
    无 total_oi 时退回 long_top20 相对 60 日均值的标准化。
    """
    if "total_oi" in data.columns and data["total_oi"].notna().any():
        denom = (2.0 * data["total_oi"]).replace(0, np.nan)
        return (
            data.get("long_top20", 0).fillna(0) + data.get("short_top20", 0).fillna(0)
        ) / denom
    if "long_top20" in data.columns:
        m = data["long_top20"].rolling(60, min_periods=10).mean()
        sd = data["long_top20"].rolling(60, min_periods=10).std()
        return (data["long_top20"] - m) / sd.replace(0, np.nan)
    return pd.Series(np.nan, index=data.index)


def _signals(
    pctl: Optional[float],
    net_chg_5d: Optional[float],
    concentration: Optional[float],
    long_change_5d: Optional[float] = None,
    short_change_5d: Optional[float] = None,
    lsr_change_5d: Optional[float] = None,
    consecutive_days: Optional[int] = None,
    price_pos_alignment: Optional[str] = None,
) -> List[str]:
    sigs: List[str] = []
    if pctl is not None and not (isinstance(pctl, float) and np.isnan(pctl)):
        if pctl >= 0.8:
            sigs.append("拥挤度处高分位(警惕反转)")
        elif pctl <= 0.2:
            sigs.append("拥挤度处低分位(关注建仓)")
    if net_chg_5d is not None:
        if net_chg_5d > 0:
            sigs.append("前20净多增加(主力看多)")
        elif net_chg_5d < 0:
            sigs.append("前20净多减少(主力看空)")
    if concentration is not None:
        if concentration >= 0.5:
            sigs.append(f"前20集中度偏高({concentration:.1%})")
        elif concentration <= 0.2:
            sigs.append(f"前20集中度偏低({concentration:.1%})")
    # 多空双边信号
    if long_change_5d is not None:
        if long_change_5d > 0:
            sigs.append(f"多头前20主动加仓({long_change_5d:+.0f})")
        elif long_change_5d < 0:
            sigs.append(f"多头前20减仓({long_change_5d:+.0f})")
    if short_change_5d is not None:
        if short_change_5d > 0:
            sigs.append(f"空头前20加仓({short_change_5d:+.0f})")
        elif short_change_5d < 0:
            sigs.append(f"空头前20减仓({short_change_5d:+.0f})")
    if lsr_change_5d is not None and abs(lsr_change_5d) > 0.2:
        sigs.append(f"多空比急剧变化({lsr_change_5d:+.2f})")
    if consecutive_days is not None and abs(consecutive_days) >= 2:
        if consecutive_days > 0:
            sigs.append(f"连续{consecutive_days}日净多增加(主力稳步建仓)")
        else:
            sigs.append(f"连续{abs(consecutive_days)}日净多减少(主力持续撤退)")
    if price_pos_alignment is not None and "背离" in price_pos_alignment:
        sigs.append(f"价格-持仓背离({price_pos_alignment})")
    return sigs


def compute_positioning_metrics(
    df_or_dict: Union[pd.DataFrame, Dict[str, pd.DataFrame], None],
    symbol: Optional[str] = None,
    price_direction: Optional[str] = None,
) -> Dict[str, Any]:
    """席位与拥挤度指标。

    Args:
        df_or_dict: 单品种 DataFrame 或多品种 Dict[str, DataFrame]
        symbol: 品种过滤(Dict 模式下用于选 key)
        price_direction: 日线价格方向(bullish/bearish/neutral),用于价格-持仓交叉验证
    """
    if df_or_dict is None:
        return h.empty_result("无席位缓存")
    raw = _coerce_input(df_or_dict, symbol)
    if raw.empty:
        return h.empty_result(f"目标品种 {symbol or '?'} 无席位数据")
    data = _prepare(raw, symbol)
    if data.empty:
        return h.empty_result("规范化后无数据")
    if len(data) < 5:
        return h.empty_result(f"样本不足(仅 {len(data)} 行)")

    # 集中度
    data = data.copy()
    data["conc_metric"] = _concentration(data)

    last = data.iloc[-1]
    latest = {
        "date": str(last.get("date")) if pd.notna(last.get("date")) else None,
        "symbol": last.get("symbol"),
        "long_top20": h.safe_float(last.get("long_top20")),
        "short_top20": h.safe_float(last.get("short_top20")),
        "total_oi": h.safe_float(last.get("total_oi")),
        "net_long_top20": h.safe_float(last.get("net_long_top20")),
        # 多空比
        "long_short_ratio": (
            float(last["long_top20"] / last["short_top20"])
            if pd.notna(last.get("long_top20")) and pd.notna(last.get("short_top20"))
            and last.get("short_top20") not in (None, 0)
            else None
        ),
    }
    concentration = h.safe_float(last.get("conc_metric"))
    pctl = h.percentile_rank(data["conc_metric"].dropna() if data["conc_metric"].notna().any() else pd.Series(dtype=float), 180)

    # 净多单边变化
    net_chg_5d = None
    long_chg_5d = None
    short_chg_5d = None
    if len(data) >= 6:
        if "net_long_top20" in data.columns:
            v_last = data["net_long_top20"].iloc[-1]
            v_prev = data["net_long_top20"].iloc[-6]
            if pd.notna(v_last) and pd.notna(v_prev):
                net_chg_5d = float(v_last - v_prev)
        if "long_top20" in data.columns:
            v_last = data["long_top20"].iloc[-1]
            v_prev = data["long_top20"].iloc[-6]
            if pd.notna(v_last) and pd.notna(v_prev):
                long_chg_5d = float(v_last - v_prev)
        if "short_top20" in data.columns:
            v_last = data["short_top20"].iloc[-1]
            v_prev = data["short_top20"].iloc[-6]
            if pd.notna(v_last) and pd.notna(v_prev):
                short_chg_5d = float(v_last - v_prev)

    # 多空比 5 日变化
    lsr_change_5d = None
    if len(data) >= 6:
        lsr_cur = latest.get("long_short_ratio") or (
            float(data["long_top20"].iloc[-1] / data["short_top20"].iloc[-1])
            if "long_top20" in data.columns and "short_top20" in data.columns
            and pd.notna(data["short_top20"].iloc[-1]) and data["short_top20"].iloc[-1] != 0
            else None
        )
        lsr_prev = (
            float(data["long_top20"].iloc[-6] / data["short_top20"].iloc[-6])
            if "long_top20" in data.columns and "short_top20" in data.columns
            and pd.notna(data["short_top20"].iloc[-6]) and data["short_top20"].iloc[-6] != 0
            else None
        )
        if lsr_cur is not None and lsr_prev is not None:
            lsr_change_5d = float(lsr_cur - lsr_prev)

    # 连续净多变化天数
    consecutive_net_long_days = 0
    if "net_long_top20" in data.columns:
        nl = data["net_long_top20"]
        sign_series = nl.diff().apply(lambda x: 1 if (pd.notna(x) and x > 0) else (-1 if (pd.notna(x) and x < 0) else 0))
        # 从最新一天向前累加同符号天数
        cnt = 0
        for i in range(len(sign_series) - 1, -1, -1):
            s = sign_series.iloc[i]
            if s == 0:
                continue
            if cnt == 0 or s == (1 if cnt > 0 else -1):
                cnt += s
            else:
                break
        consecutive_net_long_days = cnt

    # 价格-持仓对齐
    price_pos_alignment = None
    if price_direction:
        if price_direction == "bullish" and (net_chg_5d is not None and net_chg_5d > 0):
            price_pos_alignment = "同向看多(价涨仓增)"
        elif price_direction == "bearish" and (net_chg_5d is not None and net_chg_5d < 0):
            price_pos_alignment = "同向看空(价跌仓减)"
        elif price_direction == "bullish" and (net_chg_5d is not None and net_chg_5d < 0):
            price_pos_alignment = "背离(价涨仓减)"
        elif price_direction == "bearish" and (net_chg_5d is not None and net_chg_5d > 0):
            price_pos_alignment = "背离(价跌仓增)"

    signals = _signals(
        pctl, net_chg_5d, concentration,
        long_change_5d=long_chg_5d,
        short_change_5d=short_chg_5d,
        lsr_change_5d=lsr_change_5d,
        consecutive_days=consecutive_net_long_days,
        price_pos_alignment=price_pos_alignment,
    )
    snapshot = {
        **latest,
        "concentration": concentration,
        "crowding_pctl_180d": pctl,
        "net_long_change_5d": net_chg_5d,
        # 新字段
        "long_top20_change_5d": long_chg_5d,
        "short_top20_change_5d": short_chg_5d,
        "long_short_ratio_change_5d": lsr_change_5d,
        "consecutive_net_long_days": consecutive_net_long_days,
        "price_direction": price_direction or "N/A",
        "price_position_alignment": price_pos_alignment or "N/A",
        # 衍生指标
        "net_long_slope_20d": h.slope(data["net_long_top20"], 20) if "net_long_top20" in data.columns else None,
        "long_share": (
            float(last["long_top20"] / (2 * last["total_oi"]))
            if pd.notna(last.get("long_top20")) and pd.notna(last.get("total_oi"))
            and last.get("total_oi") not in (None, 0)
            else None
        ),
        "short_share": (
            float(last["short_top20"] / (2 * last["total_oi"]))
            if pd.notna(last.get("short_top20")) and pd.notna(last.get("total_oi"))
            and last.get("total_oi") not in (None, 0)
            else None
        ),
    }
    quality = h.data_quality(data, value_col="long_top20")
    quality["symbol"] = symbol or latest.get("symbol")

    return {
        "latest": latest,
        "stats": {"zscore_180d": pctl, "slope_20d": snapshot.get("net_long_slope_20d")},
        "signals": signals,
        "snapshot": snapshot,
        "quality": quality,
    }
