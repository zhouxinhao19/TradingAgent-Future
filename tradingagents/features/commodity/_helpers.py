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
    "date": ["日期", "时间", "date", "trade_date", "datetime", "time", "发布时间", "published_at"],
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
    "long_top20": ["long_top20", "long_open_interest_top20", "long_open_interest", "前20多头"],
    "short_top20": ["short_top20", "short_open_interest_top20", "short_open_interest", "前20空头"],
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
    "published_at": "date",
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
      5. 若 index 包含日期对象,将其重置为 `date` 列(如 AKShare roll_yield_bar)

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

    # 若 index 包含日期对象且没有 date 列,重置为 date 列
    if "date" not in out.columns and len(out.index) > 0:
        try:
            first = out.index[0]
            if hasattr(first, "strftime"):
                out = out.reset_index()
                if "index" in out.columns and "date" not in out.columns:
                    out = out.rename(columns={"index": "date"})
        except (IndexError, TypeError):
            pass

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


# =============================================================================
# 6. 合约选择工具
# =============================================================================

# 期货合约月份编号(YYMM 格式的后两位 MM 对应月份)
_MONTH_MAP = {
    "01": 1, "02": 2, "03": 3, "04": 4, "05": 5, "06": 6,
    "07": 7, "08": 8, "09": 9, "10": 10, "11": 11, "12": 12,
}


def extract_yyymm(symbol: str) -> Optional[int]:
    """从完整合约代码提取 YYMM 数字。

    Args:
        symbol: 合约代码, 如 ``RB2501.SHF`` 或 ``CU2501.SHF``

    Returns:
        YYMM 整数, 如 2501; 无 YYMM 时返回 None(如 ``CU0.SHF`` 主力连续)
    """
    import re
    if not symbol:
        return None
    # 匹配 SYMBOLYYMM 模式: 品种代码后跟 4 位数字
    m = re.search(r'[A-Za-z]+(\d{4})(?:\.|[A-Z]|$)', symbol)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


def is_near_delivery(
    symbol: str,
    trade_date: str,
    days_threshold: int = 30,
) -> bool:
    """判断合约是否临近交割(距到期 < 阈值)。

    Args:
        symbol: 合约代码, 如 ``RB2501.SHF``
        trade_date: 当前交易日, YYYY-MM-DD
        days_threshold: 临近交割阈值天数, 默认 30 天

    Returns:
        True 表示合约距交割不足阈值; 无法判断时返回 False
    """
    from datetime import datetime, timedelta

    yymm = extract_yyymm(symbol)
    if yymm is None:
        return False  # 主力连续代码,无到期概念

    try:
        date_obj = datetime.strptime(trade_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return False

    # 从 YYMM 推断到期日: 合约年份 = 2000 + YY, 合约月份 = MM
    yy = yymm // 100  # 前两位: 年份
    mm = yymm % 100   # 后两位: 月份
    if mm < 1 or mm > 12:
        return False

    # 年份: YY 以当前年份为基准, 若 YY < 当前年份后两位, 则加 10 年
    current_year = date_obj.year
    current_yy = current_year % 100
    if yy < current_yy:
        yy += 100  # 下个世纪
    year = 2000 + yy

    # 期货合约通常在该月第 15 个自然日附近到期(简化)
    from datetime import date as date_type
    try:
        delivery_date = date_type(year, mm, 15)
    except ValueError:
        return False

    remaining = (delivery_date - date_obj).days
    return 0 <= remaining < days_threshold


def normalize_multi_contract_input(
    main_df: Optional[pd.DataFrame],
    index_df: Optional[pd.DataFrame] = None,
    contracts_dict: Optional[Dict[str, pd.DataFrame]] = None,
) -> Dict[str, Any]:
    """统一多合约输入格式, 补充缺失字段。

    Args:
        main_df: 主力连续合约 OHLCV DataFrame
        index_df: 指数合约 OHLCV DataFrame(可选)
        contracts_dict: 品种下各合约的 OHLCV DataFrame 字典(可选),
                        key=合约代码, value=DataFrame

    Returns:
        {
            "main_df": pd.DataFrame,        # 空 DataFrame 不抛错
            "index_df": pd.DataFrame,       # 空 DataFrame 表示不可用
            "contracts_dict": Dict,          # 空 dict 表示无合约明细
            "has_main": bool,               # 主力连续是否可用
            "has_index": bool,              # 指数合约是否可用
            "has_contracts": bool,          # 合约明细是否可用
        }
    """
    main_df_safe = main_df if main_df is not None else pd.DataFrame()
    index_df_safe = index_df if index_df is not None else pd.DataFrame()
    contracts_safe = contracts_dict if contracts_dict is not None else {}

    return {
        "main_df": main_df_safe,
        "index_df": index_df_safe,
        "contracts_dict": contracts_safe,
        "has_main": not main_df_safe.empty,
        "has_index": not index_df_safe.empty,
        "has_contracts": bool(contracts_safe),
    }
