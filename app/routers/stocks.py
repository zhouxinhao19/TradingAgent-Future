"""
股票详情相关API
- 统一响应包: {success, data, message, timestamp}
- 所有端点均需鉴权 (Bearer Token)
- 路径前缀在 main.py 中挂载为 /api，当前路由自身前缀为 /stocks
"""
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status

from app.routers.auth import get_current_user
from app.core.database import get_mongo_db
from app.core.response import ok

router = APIRouter(prefix="/stocks", tags=["stocks"])


def _zfill_code(code: str) -> str:
    try:
        s = str(code).strip()
        if len(s) == 6 and s.isdigit():
            return s
        return s.zfill(6)
    except Exception:
        return str(code)


@router.get("/{code}/quote", response_model=dict)
async def get_quote(code: str, current_user: dict = Depends(get_current_user)):
    """获取股票近实时快照（从入库的 market_quotes 集合 + 基础信息集合拼装）
    返回字段（data内，蛇形命名，保持与现有风格一致）:
      - code, name, market
      - price(close), change_percent(pct_chg), amount, prev_close(估算)
      - turnover_rate, volume_ratio
      - trade_date, updated_at
    若未命中行情，部分字段为 None
    """
    db = get_mongo_db()
    code6 = _zfill_code(code)

    # 行情
    q = await db["market_quotes"].find_one({"code": code6}, {"_id": 0})
    # 基础信息
    b = await db["stock_basic_info"].find_one({"code": code6}, {"_id": 0})

    if not q and not b:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到该股票的任何信息")

    close = (q or {}).get("close")
    pct = (q or {}).get("pct_chg")
    pre_close_saved = (q or {}).get("pre_close")
    prev_close = pre_close_saved
    if prev_close is None:
        try:
            if close is not None and pct is not None:
                prev_close = round(float(close) / (1.0 + float(pct) / 100.0), 4)
        except Exception:
            prev_close = None

    data = {
        "code": code6,
        "name": (b or {}).get("name"),
        "market": (b or {}).get("market"),
        "price": close,
        "change_percent": pct,
        "amount": (q or {}).get("amount"),
        "volume": (q or {}).get("volume"),
        "open": (q or {}).get("open"),
        "high": (q or {}).get("high"),
        "low": (q or {}).get("low"),
        "prev_close": prev_close,
        # 以下字段当前从基础信息日度指标中带出（若有）
        "turnover_rate": (b or {}).get("turnover_rate"),
        "volume_ratio": (b or {}).get("volume_ratio"),
        "trade_date": (q or {}).get("trade_date"),
        "updated_at": (q or {}).get("updated_at"),
    }

    return ok(data)


@router.get("/{code}/fundamentals", response_model=dict)
async def get_fundamentals(code: str, current_user: dict = Depends(get_current_user)):
    """
    获取基础面快照（优先从 MongoDB 获取）

    数据来源优先级：
    1. stock_basic_info 集合（基础信息、估值指标）
    2. stock_financial_data 集合（财务指标：ROE、负债率等）
    """
    db = get_mongo_db()
    code6 = _zfill_code(code)

    # 1. 获取基础信息
    b = await db["stock_basic_info"].find_one({"code": code6}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到该股票的基础信息")

    # 2. 尝试从 stock_financial_data 获取最新财务指标
    financial_data = None
    try:
        financial_data = await db["stock_financial_data"].find_one(
            {"symbol": code6},
            {"_id": 0},
            sort=[("report_period", -1)]  # 按报告期降序，获取最新数据
        )
    except Exception as e:
        print(f"获取财务数据失败: {e}")

    # 3. 构建返回数据
    data = {
        "code": code6,
        "name": b.get("name"),
        "industry": b.get("industry"),
        "market": b.get("market"),

        # 板块信息（优先使用 sse，其次 sec）
        "sector": b.get("sse") or b.get("sec") or b.get("sector"),

        # 估值指标（来自 stock_basic_info）
        "pe": b.get("pe"),
        "pb": b.get("pb"),
        "pe_ttm": b.get("pe_ttm"),
        "pb_mrq": b.get("pb_mrq"),

        # ROE（优先从 stock_financial_data 获取，其次从 stock_basic_info）
        "roe": None,

        # 负债率（从 stock_financial_data 获取）
        "debt_ratio": None,

        # 市值：已在同步服务中转换为亿元
        "total_mv": b.get("total_mv"),
        "circ_mv": b.get("circ_mv"),

        # 交易指标（可能为空）
        "turnover_rate": b.get("turnover_rate"),
        "volume_ratio": b.get("volume_ratio"),

        "updated_at": b.get("updated_at"),
    }

    # 4. 从财务数据中提取 ROE 和负债率
    if financial_data:
        # ROE（净资产收益率）
        if financial_data.get("financial_indicators"):
            indicators = financial_data["financial_indicators"]
            data["roe"] = indicators.get("roe")
            data["debt_ratio"] = indicators.get("debt_to_assets")

        # 如果 financial_indicators 中没有，尝试从顶层字段获取
        if data["roe"] is None:
            data["roe"] = financial_data.get("roe")
        if data["debt_ratio"] is None:
            data["debt_ratio"] = financial_data.get("debt_to_assets")

    # 5. 如果财务数据中没有 ROE，使用 stock_basic_info 中的
    if data["roe"] is None:
        data["roe"] = b.get("roe")

    return ok(data)


@router.get("/{code}/kline", response_model=dict)
async def get_kline(code: str, period: str = "day", limit: int = 120, adj: str = "none", current_user: dict = Depends(get_current_user)):
    """获取K线数据（Tushare主，AkShare兜底）
    period: day/week/month/5m/15m/30m/60m
    adj: none/qfq/hfq
    """
    from app.services.data_sources.manager import DataSourceManager
    valid_periods = {"day","week","month","5m","15m","30m","60m"}
    if period not in valid_periods:
        raise HTTPException(status_code=400, detail=f"不支持的period: {period}")
    adj_norm = None if adj in (None, "none", "", "null") else adj
    mgr = DataSourceManager()
    items, source = mgr.get_kline_with_fallback(code=_zfill_code(code), period=period, limit=limit, adj=adj_norm)
    data = {
        "code": _zfill_code(code),
        "period": period,
        "limit": limit,
        "adj": adj if adj else "none",
        "source": source,
        "items": items or []
    }
    return ok(data)


@router.get("/{code}/news", response_model=dict)
async def get_news(code: str, days: int = 2, limit: int = 50, include_announcements: bool = True, current_user: dict = Depends(get_current_user)):
    """获取新闻与公告（Tushare 主，AkShare 兜底）"""
    from app.services.data_sources.manager import DataSourceManager
    mgr = DataSourceManager()
    items, source = mgr.get_news_with_fallback(code=_zfill_code(code), days=days, limit=limit, include_announcements=include_announcements)
    data = {
        "code": _zfill_code(code),
        "days": days,
        "limit": limit,
        "include_announcements": include_announcements,
        "source": source,
        "items": items or []
    }
    return ok(data)

