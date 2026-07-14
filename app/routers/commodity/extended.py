"""
大宗商品扩展数据路由(Phase 3a)
- 14 端点,涵盖 Phase 2 实现的 13 扩展接口 + 静态品种字典(/varieties)
- 全部路由共享 /commodity 前缀,挂载在 main.py 的 FEATURE_COMMODITY_DATA 分支
- 失败一律 4xx/404,服务端永不抛 500(防止爬虫挂掉)
"""
import logging
from datetime import datetime, date
from typing import List, Optional

from fastapi import APIRouter, HTTPException, status, Query

from app.core.response import ok
from app.services.commodity.unified_commodity_service import service

logger = logging.getLogger("webapi")
router = APIRouter(prefix="/commodity", tags=["commodity-extended"])


# 工具
def _today() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def _today_yyyymmdd() -> str:
    return datetime.utcnow().strftime("%Y%m%d")


def _parse_date(s: str, fmt_hint: str = "YYYY-MM-DD") -> date:
    """日期字符串解析,统一返 date 对象(无效 400)"""
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"日期格式无效({fmt_hint}): {s}",
    )


# ============================================================
# 端点
# ============================================================

@router.get("/varieties", response_model=dict, summary="静态品种字典(80+ 品种)")
async def get_varieties(
    exchange: Optional[str] = Query(None, description="交易所代码过滤:SHFE/DCE/CZCE/INE/GFEX/CFFEX"),
    category: Optional[str] = Query(None, description="品类过滤:metal/chemical/energy/agricultural/financial/precious/black"),
):
    """
    返回静态品种字典(零依赖)。

    字段:variety_code / symbol / name_cn / abbreviation_akshare / category /
          unit / contract_size / tick_size / list_date / exchange
    """
    items = await service.get_varieties(exchange=exchange, category=category)
    return ok(data={"items": items, "count": len(items)}, message="获取品种字典成功")


@router.get("/{full_symbol}/fees", response_model=dict, summary="手续费/保证金/涨跌停")
async def get_fees(
    full_symbol: str,
    date: Optional[str] = Query(None, description="交易日 YYYYMMDD,默认今天"),
):
    """
    手续费 / 保证金率 / 涨跌停板。

    Path: GET /api/commodity/CU2501.SHF/fees
    Path: GET /api/commodity/CU2501.SHF/fees?date=20250710

    注:统一用 full_symbol 中的交易所代码做服务端过滤;若需要全交易所汇总不传 full_symbol
    的部分参数。本端点优先匹配该交易所的汇总数据。
    """
    ex = full_symbol.split(".")[-1].upper() if "." in full_symbol else None
    rows = await service.get_fees_and_margin(exchange=ex, symbol=None, date=date)
    if not rows:
        return ok(data={"items": [], "count": 0, "exchange": ex}, message="暂无可用数据")
    return ok(data={"items": rows, "count": len(rows) if isinstance(rows, list) else 1, "exchange": ex},
              message="获取手续费/保证金成功")


@router.get("/{full_symbol}/inventory", response_model=dict, summary="库存数据")
async def get_inventory(
    full_symbol: str,
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
):
    """
    库存(Eastern Wealth 近 60 个交易日 + 99 期货长期)。

    Path: GET /api/commodity/A.DCE/inventory
    """
    symbol = full_symbol.split(".")[0]
    data = await service.get_inventory(symbol=symbol, start_date=start_date, end_date=end_date)
    if not data:
        return ok(data={"symbol": symbol, "rows": [], "count": 0},
                  message="库存数据暂不可用,该品种可能不支持库存接口")
    return ok(data=data, message="获取库存成功")


@router.get("/{exchange_code}/warehouse-receipt", response_model=dict, summary="仓单日报")
async def get_warehouse_receipt(
    exchange_code: str,
    date: Optional[str] = Query(None, description="交易日 YYYY-MM-DD,默认今天"),
):
    """
    仓单日报(SHFE/DCE/CZCE/GFEX)。

    Path: GET /api/commodity/SHFE/warehouse-receipt?date=2025-07-10
    """
    if exchange_code.upper() not in ("SHFE", "DCE", "CZCE", "CZC", "GFEX"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"仓单接口不支持该交易所: {exchange_code}(仅支持 SHFE/DCE/CZCE/GFEX)",
        )
    d = _parse_date(date or _today())
    data = await service.get_warehouse_receipt(exchange_code, d)
    if not data:
        return ok(data={"exchange": exchange_code, "date": str(d), "rows": [], "count": 0},
                  message="仓单日报暂不可用")
    return ok(data=data, message="获取仓单成功")


@router.get("/{exchange_code}/position-rank", response_model=dict, summary="会员持仓排名")
async def get_position_rank(
    exchange_code: str,
    date: Optional[str] = Query(None, description="交易日 YYYY-MM-DD,默认今天"),
    vars_list: Optional[str] = Query(None, description="品种列表,逗号分隔,如 'CU,AL'"),
):
    """
    会员持仓排名(DCE/GFEX/SHFE/CFFEX/CZCE)。

    Path: GET /api/commodity/DCE/position-rank?date=2025-07-10&vars_list=CU
    """
    if exchange_code.upper() not in ("DCE", "GFEX", "SHFE", "CFFEX", "CZCE", "CZC"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"持仓排名接口不支持该交易所: {exchange_code}",
        )
    d = _parse_date(date or _today())
    parsed_vars = [v.strip() for v in vars_list.split(",")] if vars_list else None
    data = await service.get_position_rank(exchange_code, d, vars_list=parsed_vars)
    if not data:
        return ok(data={"exchange": exchange_code, "date": str(d), "by_variety": {}, "count": 0},
                  message="持仓排名暂不可用")
    return ok(data=data, message="获取持仓排名成功")


@router.get("/spot-price", response_model=dict, summary="当日现货价格 + 基差(全品种)")
async def get_spot_price(
    date: Optional[str] = Query(None, description="交易日 YYYY-MM-DD,默认今天"),
):
    """
    51 行当日现货价格 + 基差(全品种一次返回)。

    Path: GET /api/commodity/spot-price?date=2025-07-10
    """
    d = _parse_date(date or _today())
    data = await service.get_spot_price(str(d))
    if not data:
        return ok(data={"date": str(d), "rows": [], "count": 0},
                  message="现货价格暂不可用")
    return ok(data=data, message="获取现货价格成功")


@router.get("/basis", response_model=dict, summary="历史基差(按品种范围)")
async def get_basis_history(
    vars_list: str = Query(..., description="品种列表,逗号分隔,如 'CU,AL'"),
    start_day: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD"),
    end_day: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD,默认今天"),
):
    """
    历史基差值(AKShare: futures_spot_price_daily)。

    Path: GET /api/commodity/basis?vars_list=CU,AL&start_day=2025-06-01
    """
    sd = _parse_date(start_day or (_today()))
    ed = _parse_date(end_day or (_today()))
    vars_parsed = [v.strip() for v in vars_list.split(",") if v.strip()]
    data = await service.get_basis_history(str(sd), str(ed), vars_parsed)
    if not data:
        return ok(data={"vars_list": vars_parsed, "rows": [], "count": 0},
                  message="基差数据暂不可用")
    return ok(data=data, message="获取基差成功")


@router.get("/basis-spot-previous", response_model=dict, summary="历史某日基差汇总")
async def get_basis_spot_previous(
    date: Optional[str] = Query(None, description="交易日 YYYY-MM-DD,默认今天"),
):
    """
    历史某日基差汇总(含 180 日最高/最低/平均)。

    Path: GET /api/commodity/basis-spot-previous?date=2025-07-10
    """
    d = _parse_date(date or _today())
    data = await service.get_basis_spot_previous(str(d))
    if not data:
        return ok(data={"date": str(d), "rows": [], "count": 0},
                  message="基差汇总暂不可用")
    return ok(data=data, message="获取基差汇总成功")


@router.get("/roll-yield", response_model=dict, summary="展期收益率")
async def get_roll_yield(
    type_method: str = Query("var", description="查询方式:date / symbol / var"),
    var: Optional[str] = Query(None, description="品种代码(date/symbol 模式必填)"),
    date: Optional[str] = Query(None, description="交易日 YYYY-MM-DD(var/symbol 模式必填)"),
    start_day: Optional[str] = Query(None, description="起始日期(date 模式必填)"),
    end_day: Optional[str] = Query(None, description="结束日期(date 模式必填)"),
):
    """
    展期收益率。

    Path: GET /api/commodity/roll-yield?type_method=var&date=2025-07-10
    """
    if type_method not in ("date", "symbol", "var"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"type_method 必须是 date/symbol/var 之一: {type_method}",
        )
    kwargs: dict = {"type_method": type_method}
    if type_method == "date":
        if not (var and start_day):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="type_method=date 必须传 var 与 start_day",
            )
        kwargs["var"] = var
        kwargs["start_day"] = str(_parse_date(start_day))
        kwargs["end_day"] = str(_parse_date(end_day or start_day))
    elif type_method == "symbol":
        if not (var and date):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="type_method=symbol 必须传 var 与 date",
            )
        kwargs["var"] = var
        kwargs["date"] = str(_parse_date(date))
    else:  # var
        if not date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="type_method=var 必须传 date",
            )
        kwargs["date"] = str(_parse_date(date))
    data = await service.get_roll_yield(**kwargs)
    if not data:
        return ok(data={"type_method": type_method, "rows": [], "count": 0},
                  message="展期收益率暂不可用")
    return ok(data=data, message="获取展期收益率成功")


@router.get("/{exchange_code}/contract-info", response_model=dict, summary="合约信息")
async def get_contract_info(
    exchange_code: str,
    date: Optional[str] = Query(None, description="交易日 YYYY-MM-DD,默认今天"),
):
    """
    合约信息(SHFE/INE/DCE/CZCE/GFEX/CFFEX 全交易所)。

    Path: GET /api/commodity/SHFE/contract-info?date=2025-07-10
    """
    if exchange_code.upper() not in ("SHFE", "INE", "DCE", "CZCE", "CZC", "GFEX", "CFFEX"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"合约信息接口不支持该交易所: {exchange_code}",
        )
    d = _parse_date(date or _today()) if date else None
    data = await service.get_contract_info(exchange_code, str(d) if d else None)
    if not data:
        return ok(data={"exchange": exchange_code, "rows": [], "count": 0},
                  message="合约信息暂不可用")
    return ok(data=data, message="获取合约信息成功")


@router.get("/trading-calendar", response_model=dict, summary="交易日历 + 合约参数")
async def get_trading_calendar(
    date: Optional[str] = Query(None, description="交易日 YYYY-MM-DD,默认今天"),
):
    """
    交易日历 + 合约参数(122 行,国泰君安期货)。

    Path: GET /api/commodity/trading-calendar?date=2025-07-10
    """
    d = _parse_date(date or _today())
    data = await service.get_trading_calendar(str(d))
    if not data:
        return ok(data={"date": str(d), "rows": [], "count": 0},
                  message="交易日历暂不可用")
    return ok(data=data, message="获取交易日历成功")


@router.get("/realtime-quote", response_model=dict, summary="实时行情(CF/FF)")
async def get_realtime_quote(
    symbols: str = Query(..., description="单合约如 'CU2501' 或多合约 'CU2501,AL2501'"),
    market: str = Query("CF", description="市场:CF 商品期货 / FF 金融期货"),
):
    """
    多合约实时行情(AKShare: futures_zh_spot)。

    Path: GET /api/commodity/realtime-quote?symbols=CU2501,AL2501&market=CF
    """
    if market not in ("CF", "FF"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"market 必须是 CF/FF 之一: {market}",
        )
    data = await service.get_realtime_quote(symbols, market=market)
    if not data:
        return ok(data={"symbols": symbols, "market": market, "rows": [], "count": 0},
                  message="实时行情暂不可用")
    return ok(data=data, message="获取实时行情成功")


@router.get("/{full_symbol}/minute-kline", response_model=dict, summary="分时 K 线")
async def get_minute_kline(
    full_symbol: str,
    period: int = Query(5, description="周期:1/5/15/30/60 分钟"),
):
    """
    分时 K 线(AKShare: futures_zh_minute_sina)。

    Path: GET /api/commodity/RB0.SHF/minute-kline?period=5

    注意:这里 full_symbol 应为**主力连续合约代码**(如 RB0 / CU0),而不是合约代码(CU2501)。
    """
    if period not in (1, 5, 15, 30, 60):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"period 必须是 1/5/15/30/60 之一: {period}",
        )
    symbol = full_symbol.split(".")[0]
    data = await service.get_minute_kline(symbol=symbol, period=period)
    if not data:
        return ok(data={"symbol": symbol, "period": period, "rows": [], "count": 0},
                  message="分时 K 线暂不可用(可能不是主力连续代码)")
    return ok(data=data, message="获取分时 K 线成功")


@router.get("/{exchange_code}/delivery-info", response_model=dict, summary="交割统计")
async def get_delivery_info(
    exchange_code: str,
    date: str = Query(..., description="交易月份 YYYYMM 或 交易日 YYYYMMDD"),
):
    """
    交割统计 / 期转现(DCE/CZCE/SHFE)。

    Path: GET /api/commodity/DCE/delivery-info?date=202507
    Path: GET /api/commodity/CZCE/delivery-info?date=20250710
    """
    if exchange_code.upper() not in ("DCE", "CZCE", "CZC", "SHFE"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"交割接口不支持该交易所: {exchange_code}",
        )
    if not (len(date) == 6 or len(date) == 8) or not date.isdigit():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"date 必须是 YYYYMM 或 YYYYMMDD: {date}",
        )
    data = await service.get_delivery_info(exchange_code, date)
    if not data:
        return ok(data={"exchange": exchange_code, "date": date, "rows": [], "count": 0},
                  message="交割数据暂不可用")
    return ok(data=data, message="获取交割数据成功")


@router.get("/{full_symbol}/holding-position", response_model=dict, summary="成交持仓")
async def get_holding_position(
    full_symbol: str,
    indicator: str = Query("成交量", description="指标:成交量 / 多单持仓 / 空单持仓"),
    date: Optional[str] = Query(None, description="交易日 YYYYMMDD,默认今天"),
):
    """
    期货成交持仓(AKShare: futures_hold_pos_sina)。

    Path: GET /api/commodity/OI2501.CZC/holding-position?indicator=成交量

    注意:full_symbol 中的合约代码应是**主力合约**而不是主力连续。
    """
    if indicator not in ("成交量", "多单持仓", "空单持仓"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"indicator 必须是 成交量/多单持仓/空单持仓 之一: {indicator}",
        )
    symbol = full_symbol.split(".")[0]
    data = await service.get_holding_position(symbol=symbol, indicator=indicator, date=date)
    if not data:
        return ok(data={"symbol": symbol, "indicator": indicator, "rows": [], "count": 0},
                  message="成交持仓暂不可用")
    return ok(data=data, message="获取成交持仓成功")
