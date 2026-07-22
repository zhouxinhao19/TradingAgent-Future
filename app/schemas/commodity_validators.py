"""
商品分析任务共享 Pydantic 验证器。

- validate_trade_date: 统一 trade_date 校验,防御未来日期、过长回测、错误格式
- COMMODITY_MAX_BACKTEST_DAYS: 历史回测上限,通过环境变量可调(默认 30 天)

调用点:
  - app/routers/commodity/analysis.py::AnalysisRequest
  - app/routers/commodity/analysis.py::BatchAnalysisRequest
  - app/routers/commodity/custom_data_router.py::CustomDataAnalysisRequest
"""
from __future__ import annotations

import os
from datetime import date, datetime
from typing import Optional

from zoneinfo import ZoneInfo

# 历史回测上限(默认 30 天)。AKShare 部分接口对超过 ~45 天的查询窗口返回空,
# 历史回测意义有限;过大也会让 features 全空概率升高。
COMMODITY_MAX_BACKTEST_DAYS = int(os.getenv("COMMODITY_MAX_BACKTEST_DAYS", "30"))


def _today_local() -> date:
    """项目时区下的今天(避免 UTC 跨日导致日期校验错位)。"""
    try:
        from app.core.config import settings
        tz = ZoneInfo(settings.TIMEZONE)
    except Exception:
        tz = ZoneInfo("Asia/Shanghai")
    return datetime.now(tz).date()


def validate_trade_date(v: Optional[str]) -> Optional[str]:
    """统一 trade_date 校验:YYYY-MM-DD + 不超过今天 + 不超过历史回测上限。

    Args:
        v: 原始字符串

    Returns:
        校验通过的字符串(原样返回,不做归一化)

    Raises:
        ValueError: 不符合任一约束时
    """
    if v is None or v == "":
        return None
    if not isinstance(v, str):
        raise ValueError(f"trade_date 必须是字符串: {type(v).__name__}")
    try:
        d = datetime.strptime(v.strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"trade_date 必须是 YYYY-MM-DD 格式: {v!r}")
    today = _today_local()
    if d > today:
        raise ValueError(f"trade_date 不能晚于今天({today.isoformat()}): {v!r}")
    if (today - d).days > COMMODITY_MAX_BACKTEST_DAYS:
        raise ValueError(
            f"trade_date 超过 {COMMODITY_MAX_BACKTEST_DAYS} 天历史回测范围: {v!r}"
        )
    return v
