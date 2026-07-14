"""
_helpers.py — 商品特征层共享工具函数

供 `technical.py` / `basis.py` / `inventory.py` / `positioning.py` /
`term_structure.py` / `news_sentiment.py` 共用:
  - 列名规范化(中文 / 英文混用)
  - 安全类型转换
  - 统计函数(zscore / slope / percentile)
  - 数据质量评估
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


# =============================================================================
# 1. 列名规范化
# =============================================================================

# 按 canonical key 注册别名(aliases)。canonical key 即规范化后列名。
COLUMN_ALIASES: Dict[str, List[str]] = {
    "date": ["日期", "时间", "date", "trade_date", "datetime", "time", "发布时间"],
    "open": ["开盘价", "开盘", "open"],
    "high": ["最高价", "最高", "high"],
    "low": ["最低价", "最低", "low"],
    "close": ["收盘价", "收盘", "close", "price"],
    "volume": ["成交量", "volume", "vol"],
    "open_interest": ["持仓量", "open_interest", "oi"],
    "value": ["value", "库存", "数量", "amount", "qty"],
    "spot_price": ["spot_price", "现货价格", "spot"],
    "near_contract_price": ["near_contract_price", "近月合约价", "近月价格"],
    "dominant_contract_price": ["dominant_contract_price", "主力合约价", "主力价格"],
    "near_basis": ["near_basis", "近月基差"],
    "dom_basis": ["dom_basis", "主力基差"],
    "near_basis_rate": ["near_basis_rate", "近月基差率"],
    "dom_basis_rate": ["dom_basis_rate", "主力基差率", "basis_rate"],
    "long_top20": ["long_top20", "long_open_interest_top20", "前20多头"],
    "short_top20": ["short_top20", "short_open_interest_top20", "前20空头"],
    "total_oi": ["total_oi", "total_open_interest", "总持仓"],
    "net_long_top20": ["net_long_top20", "前20净多"],
    "roll_yield": ["roll_yield", "rollYield", "roll", "yield", "展期收益率"],
    "spread": ["spread", "price_spread", "main_minus_second", "价差"],
    "content": ["content", "内容", "title", "标题"],
}

# 中文(默认)→ canonical 映射,作为基线
CHINESE_TO_CANONICAL: Dict[str, str] = {
    "日期": "date",
    "时间": "date",
    "开盘价": "open",
    "最高价": "high",
    "最低价": "low",
    "收盘价": "close",
    "成交量": "volume",
    "持仓量": "open_interest",
    "现货价格": "spot_price",
    "近月基差": "near_basis",
    "主力基差": "dom_basis",
    "近月基差率": "near_basis_rate",
    "主力基差率": "dom_basis_rate",
    "库存": "value",
    "数量": "value",
    "发布时间": "date",
    "内容": "content",
    "标题": "content",
}


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """将输入 DataFrame 的列名规范化。

    策略:
      1. 先按 `CHINESE_TO_CANONICAL` 转换中文别名
      2. 再扫一遍剩余未匹配列,按 `COLUMN_ALIASES` 的别名表匹配
      3. 不在别名中的列原样保留(供调用方识别额外字段)
      4. 日期列尝试转 datetime

    注意: 同一 canonical 名只被占用一次。若 "标题" 和 "内容" 都映射到 "content",
          后到的会跳过(避免 pandas rename 覆盖丢失数据)。
    """
    if df is None or df.empty:
        return df.copy() if df is not None else pd.DataFrame()

    rename_map: Dict[str, str] = {}
    taken_targets: set = set()  # 已被占用的 canonical 名
    used_sources: set = set()    # 已被使用的原始列名
    cols = list(df.columns)
    for c in cols:
        if c in used_sources:
            continue
        tgt: Optional[str] = None
        if c in CHINESE_TO_CANONICAL:
            tgt = CHINESE_TO_CANONICAL[c]
        else:
            for canonical, aliases in COLUMN_ALIASES.items():
                if c == canonical or c in aliases:
                    tgt = canonical
                    break
        if tgt is None:
            continue
        # 同名 canonical 已被占用 → 跳过(避免覆盖丢失数据)
        if tgt in taken_targets:
            continue
        rename_map[c] = tgt
        taken_targets.add(tgt)
        used_sources.add(c)

    out = df.rename(columns=rename_map)
    if "date" in out.columns and not pd.api.types.is_datetime64_any_dtype(out["date"]):
        try:
            out["date"] = pd.to_datetime(out["date"], errors="coerce")
        except Exception:
            pass
    return out


def ensure_columns(df: pd.DataFrame, required: List[str]) -> pd.DataFrame:
    """为缺失的必需列填 NA(数值列 NaN,字符串列 None),避免后续 KeyError。"""
    out = df.copy()
    for c in required:
        if c not in out.columns:
            out[c] = np.nan
    return out


# =============================================================================
# 2. 安全类型转换
# =============================================================================

def safe_float(x: Any) -> Optional[float]:
    """x 为 None/NaN/Inf 时返回 None;否则安全转 float。"""
    try:
        if x is None:
            return None
        v = float(x)
        if np.isnan(v) or np.isinf(v):
            return None
        return v
    except (TypeError, ValueError):
        return None


def safe_int(x: Any) -> int:
    """NaN / None → 0;其余安全转 int(用于布尔标志列)。"""
    try:
        if x is None:
            return 0
        v = float(x)
        if np.isnan(v):
            return 0
        return int(v)
    except (TypeError, ValueError):
        return 0


def to_numeric(series: pd.Series) -> pd.Series:
    """to_numeric(errors="coerce") 封装。"""
    return pd.to_numeric(series, errors="coerce")


# =============================================================================
# 3. 统计函数
# =============================================================================

def zscore(series: pd.Series, window: int = 180, min_periods: int = 20) -> Optional[float]:
    """最近一值在最近 window 日内的 z-score。窗口内样本 < min_periods 返回 None。"""
    if series is None or series.empty:
        return None
    tail = series.dropna().tail(window)
    if len(tail) < min_periods:
        return None
    last = float(tail.iloc[-1])
    mu = float(tail.mean())
    sd = float(tail.std(ddof=0))
    if sd == 0 or np.isnan(sd):
        return None
    return (last - mu) / sd


def slope(series: pd.Series, window: int = 20, min_periods: int = 5) -> Optional[float]:
    """最近 window 期的线性回归斜率(单位: 原值/期)。"""
    if series is None or series.empty:
        return None
    tail = series.dropna().tail(window)
    if len(tail) < min_periods:
        return None
    y = tail.values.astype(float)
    x = np.arange(len(y), dtype=float)
    n = len(y)
    x_mean = x.mean()
    y_mean = y.mean()
    denom = float(((x - x_mean) ** 2).sum())
    if denom == 0:
        return None
    return float(((x - x_mean) * (y - y_mean)).sum() / denom)


def percentile_rank(series: pd.Series, window: int = 180, min_periods: int = 20) -> Optional[float]:
    """最近一值在 window 期内的分位(0~1)。"""
    if series is None or series.empty:
        return None
    tail = series.dropna().tail(window)
    if len(tail) < min_periods:
        return None
    last = float(tail.iloc[-1])
    return float((tail <= last).mean())


def wow_change(series: pd.Series, weeks: int = 1) -> Optional[float]:
    """近 N 周变化(绝对值,数值列):last - value_N_weeks_ago。"""
    if series is None or series.empty:
        return None
    if len(series) < weeks * 5 + 1:
        return None
    last = series.iloc[-1]
    prev = series.iloc[-(weeks * 5 + 1)] if weeks > 0 else series.iloc[-1]
    if pd.isna(last) or pd.isna(prev):
        return None
    return float(last - prev)


# =============================================================================
# 4. 数据质量评估
# =============================================================================

def data_quality(df: pd.DataFrame, value_col: str = "value") -> Dict[str, Any]:
    """数据质量:行数、有效率、最新日期距今天的天数。

    Args:
        df: 输入 DataFrame
        value_col: 用于计算 coverage 的数值列名(默认 value)
    """
    if df is None or df.empty:
        return {"rows": 0, "coverage": 0.0, "data_freshness_days": None}
    rows = int(len(df))
    if value_col in df.columns:
        coverage = float(df[value_col].notna().mean())
    else:
        coverage = 1.0 if rows > 0 else 0.0
    freshness = None
    if "date" in df.columns:
        try:
            last_date = df["date"].iloc[-1]
            if pd.notna(last_date):
                today = pd.Timestamp(datetime.now().date())
                if not isinstance(last_date, pd.Timestamp):
                    last_date = pd.Timestamp(last_date)
                freshness = int((today - last_date).days)
        except Exception:
            freshness = None
    return {"rows": rows, "coverage": round(coverage, 3), "data_freshness_days": freshness}


# =============================================================================
# 5. 统一输出 schema 工厂
# =============================================================================

def empty_result(reason: str = "无数据") -> Dict[str, Any]:
    """生成符合统一 schema 的"空"结果。

    所有 6 个 feature 模块(empty / 无数据时)均返回此结构,便于上层聚合。
    """
    return {
        "latest": {},
        "stats": {"zscore_180d": None, "slope_20d": None},
        "signals": [reason] if reason else [],
        "snapshot": {},
        "quality": {"rows": 0, "coverage": 0.0, "data_freshness_days": None, "reason": reason},
    }
