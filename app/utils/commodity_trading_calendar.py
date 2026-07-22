"""期货交易日历(简化版)。

当前实现:周一~周五视为交易日,周末 + 已知节假日排除。

TODO(优化空间):
  - 接入 akshare tool_trade_date_hist_sina 获取实际节假日表(国内三大交易所),
    缓存到本地,避免每年硬编码更新。
  - 区分日间盘/夜盘品种的"交易日边界"(期货夜盘跨自然日时,
    周一开盘前的"周日夜晚"实际属于周一交易日)。

设计原则:
  - 纯函数 + 最小依赖(仅 datetime)
  - 失败安全(fallback 到"工作日")以免影响主链路
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable, Optional, Set


# 已知节假日集合(按需扩充)。日期格式:YYYY-MM-DD。
# 数据来源:国务院办公厅每年发布的放假通知;3 年滚动维护。
# 仅在需要严格判断时使用,否则 is_trading_day() 会 fallback 到 weekday < 5。
_KNOWN_HOLIDAYS: Set[date] = set()


def register_holidays(dates: Iterable[date]) -> None:
    """动态注册节假日(供节假日表加载完成后调用)。"""
    global _KNOWN_HOLIDAYS
    _KNOWN_HOLIDAYS = set(_KNOWN_HOLIDAYS) | set(dates)


def clear_holidays() -> None:
    """清空动态注册的节假日(主要用于测试隔离)。"""
    global _KNOWN_HOLIDAYS
    _KNOWN_HOLIDAYS = set()


def is_trading_day(d: date) -> bool:
    """判断给定日期是否为期货交易日(简化版:周末排除 + 节假日表)。

    Args:
        d: 日期

    Returns:
        True = 交易日,False = 非交易日
    """
    if not isinstance(d, date):
        try:
            d = datetime.strptime(str(d)[:10], "%Y-%m-%d").date()
        except Exception:
            return False
    if d in _KNOWN_HOLIDAYS:
        return False
    # Monday=0, ..., Sunday=6 → 工作日 = weekday < 5
    return d.weekday() < 5


def trading_days_between(start: date, end: date) -> int:
    """计算 (start, end] 半开区间内的交易日数量(简化版:周末排除 + 节假日)。

    约定: end 是参考点(今天),start 是数据最后日期;返回 start 之后到 end
    (含)之间经历过的交易日数。如果 last_date == today,则 0。

    Args:
        start: 起始日(不包含)
        end: 结束日(包含)

    Returns:
        区间内交易日数;若 start >= end 返回 0
    """
    if not isinstance(start, date) or not isinstance(end, date):
        return 0
    if start >= end:
        return 0
    n = 0
    cur = start + timedelta(days=1)
    while cur <= end:
        if is_trading_day(cur):
            n += 1
        cur = cur + timedelta(days=1)
    return n


def freshness_in_trading_days(last_date: date, today: Optional[date] = None) -> Optional[int]:
    """计算数据新鲜度(交易日天数)。

    替代 (today - last_date).days,避免"周一开盘被算成 3 天"问题。
    输入可以是 date 或可解析字符串。

    Args:
        last_date: 数据最后日期
        today: 参考"今天";None 表示系统当天

    Returns:
        交易日数;无法解析时返回 None
    """
    def _to_date(v) -> Optional[date]:
        if v is None:
            return None
        if isinstance(v, date) and not isinstance(v, datetime):
            return v
        if isinstance(v, datetime):
            return v.date()
        s = str(v).strip()
        # 兼容 'YYYY-MM-DD' 和 'YYYY-MM-DD HH:MM:SS'
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d"):
            try:
                return datetime.strptime(s[: len(fmt) + 5 if fmt == "%Y-%m-%d %H:%M:%S" else 10], fmt).date()
            except ValueError:
                continue
        # pandas Timestamp 兜底
        try:
            import pandas as _pd
            t = _pd.Timestamp(s)
            if t is _pd.NaT:
                return None
            return t.date()
        except Exception:
            return None

    ld = _to_date(last_date)
    td = _to_date(today) if today is not None else date.today()
    if ld is None or td is None:
        return None
    if ld >= td:
        return 0
    return trading_days_between(ld, td)
