"""
大宗商品模拟交易路由(Phase 4 第四刀)

端点汇总:
  账户:
    POST   /commodity/paper/accounts                    — 创建模拟账户
    GET    /commodity/paper/accounts                     — 当前用户账户列表
    GET    /commodity/paper/accounts/{account_id}        — 账户详情
    POST   /commodity/paper/accounts/{account_id}/reset  — 重置账户
    GET    /commodity/paper/accounts/{account_id}/snapshot — 账户快照(含持仓)
    GET    /commodity/paper/accounts/{account_id}/metrics  — 账户指标
  订单:
    POST   /commodity/paper/orders                       — 提交订单
    GET    /commodity/paper/orders                        — 订单列表
    GET    /commodity/paper/orders/{order_id}             — 订单详情
    POST   /commodity/paper/orders/{order_id}/cancel      — 撤单
  持仓:
    GET    /commodity/paper/positions                     — 持仓列表
  成交:
    GET    /commodity/paper/fills                         — 成交记录
  决策:
    POST   /commodity/paper/from-decision                 — CIO 决策转下单
  快照:
    GET    /commodity/paper/snapshots                     — 日终快照列表

依赖:
  - FEATURE_COMMODITY_PAPER=true (在 main.py 条件 include)
  - app.services.commodity.paper_trading_service.service
  - 认证:get_current_user(来自 app.routers.auth_db)
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.response import ok
from app.routers.auth_db import get_current_user
from app.services.commodity.paper_trading_service import service

from tradingagents.paper.spec import get_spec, parse_variety

logger = logging.getLogger("webapi")
router = APIRouter(prefix="/commodity/paper", tags=["commodity-paper"])


# =============================================================================
# 辅助:从认证用户获取 user_id
# =============================================================================

def _user_id(user: dict) -> str:
    """从认证用户 dict 提取 user_id。"""
    return user.get("username") or user.get("sub") or user.get("user_id", "")


# =============================================================================
# 账户端点
# =============================================================================

@router.post("/accounts", response_model=dict, summary="创建模拟账户")
async def create_account(
    name: str = Query("默认账户", description="账户显示名"),
    initial_capital: Optional[float] = Query(None, gt=0, description="初始资金(默认 100 万)"),
    user: dict = Depends(get_current_user),
):
    """创建大宗商品模拟交易账户。
    每个用户可创建多个模拟账户(命名区分)。
    """
    uid = _user_id(user)
    if not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    data = await service.create_account(uid, name=name, initial_capital=initial_capital)
    return ok(data=data, message="账户创建成功")


@router.get("/accounts", response_model=dict, summary="当前用户账户列表")
async def list_accounts(
    user: dict = Depends(get_current_user),
):
    """返回当前认证用户的所有模拟账户列表。"""
    uid = _user_id(user)
    if not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    data = await service.list_user_accounts(uid)
    return ok(data={"accounts": data}, message=f"共 {len(data)} 个账户")


@router.get("/accounts/{account_id}", response_model=dict, summary="账户详情")
async def get_account(
    account_id: str,
    user: dict = Depends(get_current_user),
):
    """获取指定模拟账户基础信息。"""
    data = await service.get_account(account_id)
    return ok(data=data, message="获取账户成功")


@router.get("/accounts/{account_id}/snapshot", response_model=dict, summary="账户快照(含持仓)")
async def get_account_snapshot(
    account_id: str,
    user: dict = Depends(get_current_user),
):
    """获取账户完整快照:账户信息 + 当前持仓 + 最新订单。"""
    data = await service.get_account_snapshot(account_id)
    # 额外补充最新订单
    try:
        orders = await service.list_orders(account_id, limit=5)
        data["recent_orders"] = orders.get("orders", [])
    except Exception:
        data["recent_orders"] = []
    return ok(data=data, message="获取快照成功")


@router.get("/accounts/{account_id}/metrics", response_model=dict, summary="账户指标")
async def get_account_metrics(
    account_id: str,
    user: dict = Depends(get_current_user),
):
    """获取账户详细指标(含保证金/风险度/盈亏分解)。"""
    data = await service.get_account_metrics(account_id)
    return ok(data=data, message="获取指标成功")


@router.post("/accounts/{account_id}/reset", response_model=dict, summary="重置账户")
async def reset_account(
    account_id: str,
    user: dict = Depends(get_current_user),
):
    """重置模拟账户到初始资金,清空持仓/订单/成交记录。"""
    data = await service.reset_account(account_id)
    return ok(data=data, message="账户已重置")


# =============================================================================
# 订单端点
# =============================================================================

@router.post("/orders", response_model=dict, summary="提交订单")
async def submit_order(
    account_id: str = Query(..., description="模拟账户 ID"),
    full_symbol: str = Query(..., description="合约代码,如 CU2501.SHF"),
    direction: str = Query(..., description="long 做多 / short 做空", pattern="^(long|short)$"),
    offset: str = Query("open", description="open 开仓 / close 平仓", pattern="^(open|close|close_today|close_yesterday)$"),
    order_type: str = Query("market", description="market 市价 / limit 限价", pattern="^(market|limit|stop|stop_limit)$"),
    lots: int = Query(..., gt=0, le=100, description="手数"),
    price: Optional[float] = Query(None, gt=0, description="限价(限价单必填)"),
    stop_price: Optional[float] = Query(None, gt=0, description="触发价(止损单必填)"),
    stop_loss: Optional[float] = Query(None, gt=0, description="止损价"),
    take_profit: Optional[float] = Query(None, gt=0, description="止盈价"),
    user: dict = Depends(get_current_user),
):
    """提交大宗商品模拟交易订单。

    支持的订单类型:
    - market: 市价单,立即以当前价撮合
    - limit: 限价单,达到指定价才成交
    - stop: 止损单,触发价条件单
    - stop_limit: 止损限价单
    """
    data = await service.submit_order(
        account_id=account_id,
        full_symbol=full_symbol,
        direction=direction,
        offset=offset,
        order_type=order_type,
        lots=lots,
        price=price,
        stop_price=stop_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )
    return ok(data=data, message="订单已提交")


@router.get("/orders", response_model=dict, summary="订单列表")
async def list_orders(
    account_id: str = Query(..., description="模拟账户 ID"),
    status: Optional[str] = Query(None, description="按状态过滤:pending/filled/cancelled/rejected"),
    full_symbol: Optional[str] = Query(None, description="按合约过滤"),
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
    skip: int = Query(0, ge=0, description="跳过条数"),
    user: dict = Depends(get_current_user),
):
    """获取模拟账户的订单列表(支持状态/合约过滤)。"""
    data = await service.list_orders(
        account_id, status=status, full_symbol=full_symbol, limit=limit, skip=skip,
    )
    return ok(data=data, message="获取订单列表成功")


@router.get("/orders/{order_id}", response_model=dict, summary="订单详情")
async def get_order(
    order_id: str,
    account_id: str = Query(..., description="模拟账户 ID"),
    user: dict = Depends(get_current_user),
):
    """获取单笔订单的完整详情(含成交明细)。"""
    data = await service.list_orders(account_id, limit=1)
    orders = data.get("orders", [])
    target = [o for o in orders if o.get("id") == order_id]
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"订单不存在: {order_id}",
        )
    return ok(data=target[0], message="获取订单成功")


@router.post("/orders/{order_id}/cancel", response_model=dict, summary="撤单")
async def cancel_order(
    order_id: str,
    user: dict = Depends(get_current_user),
):
    """撤销指定订单(仅 pending 状态可撤)。"""
    data = await service.cancel_order(order_id)
    return ok(data=data, message="撤单成功")


# =============================================================================
# 持仓端点
# =============================================================================

@router.get("/positions", response_model=dict, summary="持仓列表")
async def list_positions(
    account_id: str = Query(..., description="模拟账户 ID"),
    open_only: bool = Query(True, description="是否仅显示未平持仓"),
    user: dict = Depends(get_current_user),
):
    """获取模拟账户当前持仓列表(净持仓模型，同品种同方向合并)。"""
    data = await service.list_positions(account_id, open_only=open_only)
    return ok(data=data, message="获取持仓成功")


# =============================================================================
# 成交端点
# =============================================================================

@router.get("/fills", response_model=dict, summary="成交记录")
async def list_fills(
    account_id: str = Query(..., description="模拟账户 ID"),
    full_symbol: Optional[str] = Query(None, description="按合约过滤"),
    limit: int = Query(100, ge=1, le=500, description="返回条数"),
    skip: int = Query(0, ge=0, description="跳过条数"),
    user: dict = Depends(get_current_user),
):
    """获取模拟账户历史成交记录(append-only)。"""
    data = await service.list_fills(
        account_id, full_symbol=full_symbol, limit=limit, skip=skip,
    )
    return ok(data=data, message="获取成交记录成功")


# =============================================================================
# 决策下单端点
# =============================================================================

@router.post("/from-decision", response_model=dict, summary="CIO 决策转下单")
async def from_decision(
    account_id: str = Query(..., description="模拟账户 ID"),
    decision_id: str = Query(..., description="Phase 3b CIO 决策 ID"),
    lots: Optional[int] = Query(None, gt=0, description="覆盖手数(空=自动计算)"),
    user: dict = Depends(get_current_user),
):
    """将 Phase 3b CIO 决策自动转为模拟订单。

    自动处理:
    - neutral 决策 → 不下单(返回 no_action)
    - long/short → 按决策入场区间取中点限价,计算手数,提交订单
    - 失败返回具体原因
    """
    data = await service.from_decision(account_id, decision_id, override_lots=lots)
    return ok(data=data, message="决策已处理")


# =============================================================================
# 日终快照端点
# =============================================================================

@router.get("/snapshots", response_model=dict, summary="日终快照列表")
async def list_snapshots(
    account_id: str = Query(..., description="模拟账户 ID"),
    limit: int = Query(30, ge=1, le=365, description="返回条数"),
    user: dict = Depends(get_current_user),
):
    """获取模拟账户日终净值快照列表(用于 PnL 折线图)。"""
    try:
        from tradingagents.paper.repo import get_snapshot_repo
        repo = get_snapshot_repo()
        snapshots = await repo.list_by_account(account_id, limit=limit)
    except Exception as exc:
        logger.warning("获取日终快照失败: %s", exc)
        snapshots = []
    items = []
    for s in snapshots:
        items.append({
            "id": s.id,
            "date": str(s.date),
            "equity": round(s.equity, 2),
            "balance": round(s.balance, 2),
            "realized_pnl": round(s.realized_pnl, 2),
            "unrealized_pnl": round(s.unrealized_pnl, 2),
            "positions_count": s.positions_count,
            "trades_count": s.trades_count,
            "snapshot_at": str(s.snapshot_at),
        })
    return ok(data={"snapshots": items}, message="获取快照成功")
