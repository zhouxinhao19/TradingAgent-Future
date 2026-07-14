"""
业务编排层(`tradingagents/paper/service.py`)

Phase 4 第三刀交付:
- `create_account`:基于 INITIAL_CAPITAL 开户,落 PaperAccount
- `submit_order`:依赖注入 repo,跑预检 → 撮合 → 落 fill → 更新持仓 → 触发风控
- `cancel_order`:仅 pending 可撤,撤单后释放 frozen
- `from_decision`:接 Phase 3b CIO 决策(decision_id),自动转 PaperOrder
- `compute_account_metrics`:净值/风险度重算
- `get_realtime_quote_fn`:依赖注入抽象,默认 mock 返回 0.0(单元测试友好)

设计原则:
1. 业务编排层不持有 db / repo 单例,通过工厂函数或参数注入
2. Phase 3b `from_decision` 暂时以 stub 形式提供(等 Phase 3b 完全归档)
3. 失败全部用 `PaperTradingError` 抛出,供上层 Router 统一捕获转 HTTPException
4. SSE 推送在第四刀加,本刀只留 SSE 回调钩子 `_on_event`
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional

try:
    from app.models.commodity_paper import (  # type: ignore
        OrderSource,
        PaperAccount,
        PaperFill,
        PaperOrder,
        PaperPosition,
    )
except ImportError:  # pragma: no cover
    PaperAccount = PaperOrder = PaperPosition = PaperFill = OrderSource = None  # type: ignore

from app.core.config import settings as app_settings

from .account import (
    AccountMetrics,
    apply_fill_to_position,
    recalculate_account,
    to_account_snapshot,
)
from .matcher import (
    PAPER_MATCHING_MODE,
    PAPER_SLIPPAGE_BPS,
    PAPER_MAX_LOTS_PER_ORDER,
    PAPER_MAX_POSITION_PER_SYMBOL,
    get_slippage_config,
    match_current_price,
    pre_check_order,
)
from .repo import (
    PaperAccountRepo,
    PaperFillRepo,
    PaperOrderRepo,
    PaperPositionRepo,
    get_account_repo,
    get_fill_repo,
    get_order_repo,
    get_position_repo,
)
from .spec import ContractSpec, calc_commission, get_spec, parse_variety
from .types import Fill, OrderResult, SubmitOrderRequest

logger = logging.getLogger(__name__)


# =============================================================================
# 异常类型
# =============================================================================

class PaperTradingError(Exception):
    """模拟交易业务异常基类。"""

    def __init__(self, message: str, code: str = "paper_error"):
        super().__init__(message)
        self.message = message
        self.code = code


class OrderRejected(PaperTradingError):
    """订单被预检/撮合拒单。"""

    def __init__(self, reason: str, message: Optional[str] = None):
        super().__init__(message or f"order rejected: {reason}", code="order_rejected")
        self.reason = reason


class InsufficientMargin(PaperTradingError):
    """保证金不足。"""

    def __init__(self, required: float, available: float):
        msg = f"insufficient margin: required={required:.2f}, available={available:.2f}"
        super().__init__(msg, code="insufficient_margin")
        self.required = required
        self.available = available


class AccountNotFound(PaperTradingError):
    """账户不存在。"""

    def __init__(self, account_id: str):
        super().__init__(f"account not found: {account_id}", code="account_not_found")


# =============================================================================
# 依赖抽象(便于单测注入 fake)
# =============================================================================

# 实时行情回调:Phase 4 第三刀先用 mock get_realtime_quote
# 第六刀接入 unified_commodity_service.get_realtime_quote
RealtimeQuoteFn = Callable[[str], Awaitable[float]]


async def _default_quote_fn(full_symbol: str) -> float:
    """默认 mock 行情(返回 0.0,要求调用方始终注入)。

    真实注入:`unified_commodity_service.get_realtime_quote` 在第四刀接入。
    """
    logger.warning("paper.service 使用 mock 行情(full_symbol=%s),请注入真实数据源", full_symbol)
    return 0.0


SsePublishFn = Callable[[str, str, Dict[str, Any]], Awaitable[None]]
"""SSE 推送签名:(user_id, event_type, payload) -> None。"""


async def _default_sse_fn(user_id: str, event_type: str, payload: Dict[str, Any]) -> None:
    """默认 SSE 钩子(空实现,留待第四刀接入 WebSocket/SSE 服务)。"""
    logger.debug("paper SSE mock: user=%s event=%s payload keys=%s", user_id, event_type, list(payload.keys())[:5])


# =============================================================================
# 上下文:把所有依赖打包,函数显式接收
# =============================================================================

@dataclass
class PaperServiceContext:
    """服务上下文:聚合 repo + 行情回调 + SSE 回调 + 配置。"""
    account_repo: PaperAccountRepo
    order_repo: PaperOrderRepo
    position_repo: PaperPositionRepo
    fill_repo: PaperFillRepo
    quote_fn: RealtimeQuoteFn = _default_quote_fn
    sse_fn: SsePublishFn = _default_sse_fn

    @classmethod
    def default(cls) -> "PaperServiceContext":
        """默认上下文(用单例 repo + 默认 mock)。"""
        return cls(
            account_repo=get_account_repo(),
            order_repo=get_order_repo(),
            position_repo=get_position_repo(),
            fill_repo=get_fill_repo(),
            quote_fn=_default_quote_fn,
            sse_fn=_default_sse_fn,
        )


# =============================================================================
# Account 服务
# =============================================================================

async def create_account(
    ctx: PaperServiceContext,
    user_id: str,
    name: str = "默认账户",
    initial_capital: Optional[float] = None,
) -> PaperAccount:
    """新建模拟账户。"""
    if not user_id:
        raise PaperTradingError("user_id 不能为空", code="invalid_user_id")
    cap = initial_capital if initial_capital is not None else app_settings.PAPER_DEFAULT_INITIAL_CAPITAL
    if cap <= 0:
        raise PaperTradingError("initial_capital 必须 > 0", code="invalid_capital")

    acc = PaperAccount(
        user_id=user_id,
        name=name,
        initial_capital=cap,
        balance=cap,
        available=cap,
        equity=cap,
    )
    await ctx.account_repo.insert(acc)
    logger.info("Paper account created: user=%s id=%s capital=%.0f", user_id, acc.id, cap)
    await ctx.sse_fn(user_id, "paper.account.created", acc.to_snapshot_dict())
    return acc


async def reset_account(ctx: PaperServiceContext, account_id: str) -> PaperAccount:
    """重置账户到初始资金。"""
    acc = await ctx.account_repo.get_or_404(account_id)
    await ctx.account_repo.reset(account_id)
    new_acc = await ctx.account_repo.get(account_id)
    assert new_acc is not None
    await ctx.sse_fn(acc.user_id, "paper.account.reset", new_acc.to_snapshot_dict())
    return new_acc


async def list_accounts_by_user(ctx: PaperServiceContext, user_id: str) -> List[PaperAccount]:
    return await ctx.account_repo.list_by_user(user_id)


async def get_account(ctx: PaperServiceContext, account_id: str) -> PaperAccount:
    return await ctx.account_repo.get_or_404(account_id)


async def get_account_metrics(
    ctx: PaperServiceContext, account_id: str
) -> AccountMetrics:
    """重算账户指标(供前端 /equity 端点用)。"""
    acc = await ctx.account_repo.get_or_404(account_id)
    positions = await ctx.position_repo.list_by_account(account_id, open_only=False)
    # 转换为 tradingagents.paper.types.PaperAccount + Position 形态
    from .types import PaperAccount as PAPaperAccount, Position

    paper_acc = PAPaperAccount(
        id=acc.id,
        balance=acc.balance,
        margin_used=acc.margin_used,
        frozen=acc.frozen,
        realized_pnl=acc.realized_pnl,
    )

    # 构造 specs_by_symbol / current_prices
    specs_by_symbol: Dict[str, Any] = {}
    current_prices: Dict[str, float] = {}
    pos_list: List[Position] = []
    for p in positions:
        if p.lots <= 0:
            continue
        try:
            variety_code, _ = parse_variety(p.full_symbol)
            spec = get_spec(variety_code)
            specs_by_symbol[p.full_symbol] = spec
        except ValueError:
            continue
        current_prices[p.full_symbol] = p.current_price or 0.0
        pos_list.append(
            Position(
                full_symbol=p.full_symbol,
                direction=p.direction,
                lots=p.lots,
                avg_cost=p.avg_cost,
                current_price=p.current_price,
                floating_pnl=p.floating_pnl,
                margin_used=p.margin_used,
            )
        )
    return recalculate_account(paper_acc, pos_list, specs_by_symbol, current_prices)


# =============================================================================
# Order 服务
# =============================================================================

async def _load_or_init_position(
    ctx: PaperServiceContext, account_id: str, full_symbol: str, direction: str
) -> Optional[PaperPosition]:
    """查询已有持仓(同账户同品种同方向)。None 表示尚无持仓。"""
    return await ctx.position_repo.get(account_id, full_symbol, direction)


async def _get_current_position_lots(
    ctx: PaperServiceContext, account_id: str, full_symbol: str, direction: str
) -> int:
    pos = await _load_or_init_position(ctx, account_id, full_symbol, direction)
    return pos.lots if pos else 0


async def submit_order(
    ctx: PaperServiceContext, req: SubmitOrderRequest
) -> OrderResult:
    """提交订单全流程:预检 → 落 PaperOrder(pending) → 撮合 → 落 fill → 更新持仓 → 账户重算 → SSE。

    Args:
        ctx: 服务上下文
        req: 下单请求(不含 order_id,由 PaperOrder 自动生成)

    Returns:
        OrderResult(accepted/rejected)

    Raises:
        OrderRejected / InsufficientMargin / AccountNotFound / PaperTradingError
    """
    # ---- 0. 账户 + 合约 ----
    acc = await ctx.account_repo.get_or_404(req.account_id)
    if acc.status != "active":
        raise OrderRejected("account_inactive", "账户已关闭,不可下单")

    try:
        variety_code, exchange = parse_variety(req.full_symbol)
    except ValueError as e:
        raise OrderRejected("unknown_symbol", str(e))
    spec: ContractSpec = get_spec(variety_code)

    # 当前同品种持仓(用于限仓预检 + 平仓方向校验)
    cur_pos = await _load_or_init_position(ctx, req.account_id, req.full_symbol, req.direction)
    cur_lots = cur_pos.lots if cur_pos else 0
    cur_direction = cur_pos.direction if cur_pos else None

    # ---- 1. 获取当前行情(用于预检 & 撮合) ----
    current_quote = await ctx.quote_fn(req.full_symbol)

    # 预检参考价:限价单用 req.price,市价单用 current_quote(prev_settlement=0 时)
    # 第三刀暂不接真实昨结算,涨跌停预检用 current_quote 做近似
    ref_price_for_check = req.price if req.price and req.price > 0 else (current_quote if current_quote > 0 else None)
    prev_settlement_used = ref_price_for_check or 0.0

    ok, reason = pre_check_order(
        req=req,
        account_balance=acc.balance,
        account_available=acc.available,
        spec=spec,
        prev_settlement=prev_settlement_used,
        current_position_lots=cur_lots,
        current_position_direction=cur_direction,
    )
    if not ok:
        assert reason is not None
        raise OrderRejected(reason)

    # ---- 2. 创建 PaperOrder(pending) ----
    order = PaperOrder(
        account_id=req.account_id,
        full_symbol=req.full_symbol,
        direction=req.direction,
        offset=req.offset,
        order_type=req.order_type,
        lots=req.lots,
        price=req.price,
        stop_price=req.stop_price,
        stop_loss=req.stop_loss,
        take_profit=req.take_profit,
        source=req.source or "manual",
        decision_id=req.decision_id,
    )
    await ctx.order_repo.insert(order)
    await ctx.sse_fn(acc.user_id, "paper.order.pending", {"order_id": order.id, "symbol": order.full_symbol})

    # ---- 3. 撮合判定(current_price 模式 / market 单立即成交) ----
    if req.order_type in ("market",) or (PAPER_MATCHING_MODE == "current_price" and req.order_type in ("limit",)):
        fill = match_current_price(req, current_quote, spec, order.id)
        if fill is None:
            # 限价单未触价,保持 pending,等轮询
            logger.info("Paper order pending(limit not touched): order=%s symbol=%s", order.id, order.full_symbol)
            return OrderResult(status="accepted", reject_reason=None, fill=None)

    elif req.order_type in ("stop", "stop_limit"):
        # 止损/止损限价单挂单,等轮询
        return OrderResult(status="accepted", reject_reason=None, fill=None)

    else:
        return OrderResult(status="accepted", reject_reason=None, fill=None)

    # ---- 4. 落 fill → 更新持仓 → 重算账户 ----
    assert fill is not None
    await _apply_fill(ctx, acc, fill, spec, order, req.stop_loss, req.take_profit)

    return OrderResult(status="accepted", reject_reason=None, fill=fill)


async def _apply_fill(
    ctx: PaperServiceContext,
    acc: PaperAccount,
    fill: Fill,
    spec: ContractSpec,
    order: PaperOrder,
    stop_loss: Optional[float],
    take_profit: Optional[float],
) -> None:
    """成交后的事务化更新:写 fill → 更新 order → 更新 position → 重算 account → SSE。"""
    # 4.1 落 fill
    paper_fill = PaperFill(
        order_id=fill.order_id,
        account_id=fill.account_id,
        full_symbol=fill.full_symbol,
        direction=fill.direction,
        offset=fill.offset,
        lots=fill.lots,
        price=fill.price,
        commission=fill.commission,
        slippage=fill.slippage,
    )
    await ctx.fill_repo.insert(paper_fill)

    # 4.2 更新 order(fill 状态 + 价格)
    from app.utils.timezone import now_tz
    await ctx.order_repo.update_fields(
        fill.order_id,
        {
            "status": "filled",
            "filled_lots": fill.lots,
            "filled_avg_price": fill.price,
            "commission": fill.commission,
            "slippage": fill.slippage,
            "filled_at": now_tz(),
        },
    )

    # 4.3 更新持仓(净持仓模型:upsert 单条)
    cur_pos = await ctx.position_repo.get(acc.id, fill.full_symbol, fill.direction)
    from .types import Position as PurePosition

    cur_pure = None
    if cur_pos:
        cur_pure = PurePosition(
            full_symbol=cur_pos.full_symbol,
            direction=cur_pos.direction,
            lots=cur_pos.lots,
            avg_cost=cur_pos.avg_cost,
            current_price=cur_pos.current_price,
            floating_pnl=cur_pos.floating_pnl,
            margin_used=cur_pos.margin_used,
            stop_loss=cur_pos.stop_loss,
            take_profit=cur_pos.take_profit,
            opened_at=cur_pos.opened_at,
            updated_at=cur_pos.updated_at,
        )

    new_pos_pure, realized_pnl_this_fill = apply_fill_to_position(cur_pure, fill, spec)

    if new_pos_pure is None:
        # 持仓已清空,删除原 doc(如有)
        if cur_pos:
            await ctx.position_repo.delete(cur_pos.id)
    else:
        # upsert 新持仓
        from app.utils.timezone import now_tz as _now_tz
        new_pos = PaperPosition(
            account_id=acc.id,
            full_symbol=new_pos_pure.full_symbol,
            direction=new_pos_pure.direction,
            lots=new_pos_pure.lots,
            avg_cost=new_pos_pure.avg_cost,
            current_price=new_pos_pure.current_price,
            floating_pnl=new_pos_pure.floating_pnl,
            margin_used=new_pos_pure.margin_used,
            stop_loss=stop_loss if stop_loss is not None else new_pos_pure.stop_loss,
            take_profit=take_profit if take_profit is not None else new_pos_pure.take_profit,
            opened_at=new_pos_pure.opened_at or _now_tz(),
            updated_at=_now_tz(),
        )
        await ctx.position_repo.upsert(new_pos)

    # 4.4 重算账户(余额 = balance + realized_pnl)
    positions = await ctx.position_repo.list_by_account(acc.id, open_only=False)
    metrics = await get_account_metrics(ctx, acc.id)
    new_balance = acc.balance + realized_pnl_this_fill - fill.commission
    new_realized = acc.realized_pnl + realized_pnl_this_fill - fill.commission
    await ctx.account_repo.update_fields(
        acc.id,
        {
            "balance": new_balance,
            "realized_pnl": new_realized,
            "margin_used": metrics.margin_used,
            "equity": metrics.equity,
            "available": metrics.available,
            "unrealized_pnl": metrics.unrealized_pnl,
            "risk_ratio": metrics.risk_ratio,
        },
    )

    await ctx.sse_fn(acc.user_id, "paper.order.filled", {
        "order_id": fill.order_id,
        "fill_id": paper_fill.id,
        "symbol": fill.full_symbol,
        "direction": fill.direction,
        "offset": fill.offset,
        "lots": fill.lots,
        "price": fill.price,
        "commission": fill.commission,
        "realized_pnl": realized_pnl_this_fill,
    })


async def cancel_order(ctx: PaperServiceContext, order_id: str) -> PaperOrder:
    """撤单(仅 pending 可撤)。"""
    order = await ctx.order_repo.get_or_404(order_id)
    if order.status != "pending":
        raise OrderRejected("market_closed" if order.status == "filled" else "market_closed",
                            f"订单状态={order.status},不可撤单")
    from app.utils.timezone import now_tz
    await ctx.order_repo.update_fields(order_id, {
        "status": "cancelled",
        "cancelled_at": now_tz(),
    })
    acc = await ctx.account_repo.get_or_404(order.account_id)
    await ctx.sse_fn(acc.user_id, "paper.order.cancelled", {"order_id": order_id})
    return await ctx.order_repo.get_or_404(order_id)


async def list_orders(
    ctx: PaperServiceContext,
    account_id: str,
    *,
    status: Optional[str] = None,
    full_symbol: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
) -> List[PaperOrder]:
    return await ctx.order_repo.list_by_account(
        account_id,
        status=status,
        full_symbol=full_symbol,
        limit=limit,
        skip=skip,
    )


async def list_positions(
    ctx: PaperServiceContext,
    account_id: str,
    *,
    open_only: bool = True,
) -> List[PaperPosition]:
    return await ctx.position_repo.list_by_account(account_id, open_only=open_only)


async def list_fills(
    ctx: PaperServiceContext,
    account_id: str,
    *,
    full_symbol: Optional[str] = None,
    limit: int = 100,
    skip: int = 0,
) -> List[PaperFill]:
    return await ctx.fill_repo.list_by_account(
        account_id,
        full_symbol=full_symbol,
        limit=limit,
        skip=skip,
    )


# =============================================================================
# from_decision — 接 Phase 3b CIO 决策
# =============================================================================

@dataclass
class DecisionSnapshot:
    """从 Phase 3b decisions 集合读出的简化决策(只取下游用得着的字段)。"""
    id: str
    full_symbol: str
    direction: str  # "long" / "short" / "neutral"
    entry_price_range: List[float]  # [low, high]
    stop_loss_price: Optional[float]
    take_profit_price: Optional[float]
    position_sizing_method: str  # "fixed" / "kelly_criterion" / "volatility" / "risk_parity"
    position_percentage: Optional[float]  # fixed 模式百分比(0~1)


async def _load_decision_snapshot(decision_id: str) -> Optional[DecisionSnapshot]:
    """从 MongoDB `decisions` 集合读决策。

    第三刀 placeholder:返回 None,等待 Phase 3b 完全归档(分析结果已落表)后接入。
    """
    try:
        from app.core.database import get_mongo_db
        db = get_mongo_db()
        # Phase 3b 的决策文档 collection 名约定为 "commodity_decisions" / "decisions"
        # 第三刀先查询 commodity_decisions(若不存在返回 None)
        for coll_name in ("commodity_decisions", "decisions"):
            coll = db[coll_name]
            doc = await coll.find_one({"_id": decision_id}) or await coll.find_one({"id": decision_id}) or await coll.find_one({"decision_id": decision_id})
            if doc:
                return DecisionSnapshot(
                    id=decision_id,
                    full_symbol=doc.get("full_symbol") or doc.get("symbol", ""),
                    direction=doc.get("direction") or doc.get("decision", "neutral"),
                    entry_price_range=doc.get("entry_price_range") or doc.get("entry_range") or [0.0, 0.0],
                    stop_loss_price=doc.get("stop_loss_price") or doc.get("stop_loss"),
                    take_profit_price=doc.get("take_profit_price") or doc.get("take_profit"),
                    position_sizing_method=doc.get("position_sizing_method", "fixed"),
                    position_percentage=doc.get("position_percentage"),
                )
    except Exception as e:  # pragma: no cover - 仅在 MongoDB 不可用时触发
        logger.warning("加载决策 %s 失败:%s", decision_id, e)
    return None


async def _calc_lots_from_decision(
    account: PaperAccount,
    decision: DecisionSnapshot,
    spec: ContractSpec,
    override_lots: Optional[int] = None,
) -> int:
    """根据决策 + 账户余额计算手数。

    算法:
    - override_lots 优先(用户在前端手动覆盖)
    - kelly_criterion / volatility / risk_parity:Phase 4 简化统一按 fixed 算,
      预留 Phase 5+ 接入 trader 模块的 Kelly 算法
    - fixed:lots = max(1, floor(account.equity * pct / (price × contract_size × margin_rate)))
    """
    if override_lots is not None and override_lots > 0:
        return min(override_lots, PAPER_MAX_LOTS_PER_ORDER)

    pct = decision.position_percentage or 0.10  # 默认 10% 仓位
    if not decision.entry_price_range:
        return 1
    avg_price = (decision.entry_price_range[0] + decision.entry_price_range[1]) / 2
    if avg_price <= 0:
        return 1
    notional_per_lot = avg_price * spec.contract_size * spec.margin_rate
    if notional_per_lot <= 0:
        return 1
    raw = account.equity * pct / notional_per_lot
    lots = max(1, int(raw))
    return min(lots, PAPER_MAX_LOTS_PER_ORDER)


async def from_decision(
    ctx: PaperServiceContext,
    account_id: str,
    decision_id: str,
    override_lots: Optional[int] = None,
) -> Dict[str, Any]:
    """接 Phase 3b CIO 决策,自动转 PaperOrder 并落库。

    Returns:
        dict 含 status / order_id / lots / reason(neutral 时填 no_action)

    Raises:
        PaperTradingError / OrderRejected
    """
    decision = await _load_decision_snapshot(decision_id)
    if decision is None:
        raise PaperTradingError(f"decision not found: {decision_id}", code="decision_not_found")

    if decision.direction == "neutral":
        return {"status": "no_action", "reason": "neutral 决策不下单"}

    acc = await ctx.account_repo.get_or_404(account_id)

    # 解析合约规格
    try:
        variety_code, _exchange = parse_variety(decision.full_symbol)
    except ValueError as e:
        raise PaperTradingError(
            f"决策 {decision_id} 全符号无效: {decision.full_symbol} ({e})",
            code="invalid_symbol",
        )
    spec = get_spec(variety_code)

    lots = await _calc_lots_from_decision(acc, decision, spec, override_lots)

    # 限价 = 入场区间中点
    if decision.entry_price_range and len(decision.entry_price_range) == 2:
        entry_price = sum(decision.entry_price_range) / 2
    else:
        entry_price = None

    req = SubmitOrderRequest(
        account_id=account_id,
        full_symbol=decision.full_symbol,
        direction=decision.direction,
        offset="open",
        order_type="limit" if entry_price else "market",
        lots=lots,
        price=entry_price,
        stop_loss=decision.stop_loss_price,
        take_profit=decision.take_profit_price,
        source="agent_decision",
        decision_id=decision_id,
    )

    result = await submit_order(ctx, req)
    return {
        "status": "submitted" if result.status == "accepted" else "rejected",
        "decision_id": decision_id,
        "lots": lots,
        "order_id": None,  # submit_order 内部已经入 PaperOrder,要从 repo 反查
        "reason": result.reject_reason,
    }


# =============================================================================
# 公共接口镜像(供上层 router / 第四刀 frontend 调用)
# =============================================================================

async def get_account_snapshot(
    ctx: PaperServiceContext, account_id: str
) -> Dict[str, Any]:
    """返回前端友好的账户快照(dict)。"""
    acc = await ctx.account_repo.get_or_404(account_id)
    return acc.to_snapshot_dict()


async def get_orders_by_account(
    ctx: PaperServiceContext,
    account_id: str,
    *,
    limit: int = 50,
    skip: int = 0,
    status: Optional[str] = None,
    full_symbol: Optional[str] = None,
) -> Dict[str, Any]:
    """返回 dict 包订单列表 + 总数。"""
    orders = await list_orders(
        ctx, account_id, status=status, full_symbol=full_symbol, limit=limit, skip=skip
    )
    total = await ctx.order_repo.count_by_account(account_id, status=status)
    return {"orders": orders, "total": total}


__all__ = [
    "PaperTradingError",
    "OrderRejected",
    "InsufficientMargin",
    "AccountNotFound",
    "PaperServiceContext",
    "RealtimeQuoteFn",
    "SsePublishFn",
    "create_account",
    "reset_account",
    "list_accounts_by_user",
    "get_account",
    "get_account_metrics",
    "get_account_snapshot",
    "submit_order",
    "cancel_order",
    "list_orders",
    "get_orders_by_account",
    "list_positions",
    "list_fills",
    "from_decision",
    "DecisionSnapshot",
    "get_slippage_config",
]
