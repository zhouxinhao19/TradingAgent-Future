"""
大宗商品模拟交易 FastAPI 服务层(Phase 4 第四刀)

包装 `tradingagents/paper/service.py` 的业务函数,提供:
1. FastAPI 友好的依赖注入(单例 PaperServiceContext + 真实行情注入)
2. 用户 → 账户映射辅助(当前认证用户自动关联账户)
3. 异常统一转换(PaperTradingError → HTTPException)

设计原则:
- 不重复业务逻辑,所有核心计算委托给 tradingagents.paper.service
- 行情实时性:quote_fn 先尝试 unified_commodity_service,fallback 到默认
- SSE 推送预留钩子(第四刀实现),当前空实现
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status

from app.core.config import settings

from tradingagents.paper.service import (
    PaperServiceContext,
    PaperTradingError,
    OrderRejected,
    InsufficientMargin,
    AccountNotFound,
    create_account as svc_create_account,
    reset_account as svc_reset_account,
    get_account as svc_get_account,
    get_account_snapshot as svc_get_account_snapshot,
    get_account_metrics as svc_get_account_metrics,
    list_accounts_by_user as svc_list_accounts,
    submit_order as svc_submit_order,
    cancel_order as svc_cancel_order,
    list_orders as svc_list_orders,
    list_positions as svc_list_positions,
    list_fills as svc_list_fills,
    from_decision as svc_from_decision,
)
from tradingagents.paper.types import SubmitOrderRequest
from tradingagents.paper.spec import parse_variety

logger = logging.getLogger("webapi")


# =============================================================================
# 真实行情回调(尝试接 unified_commodity_service,失败则 mock)
# =============================================================================

async def _real_quote_fn(full_symbol: str) -> float:
    """从 unified_commodity_service 获取实时行情。

    若服务不可用(Phase 4 暂未加载),回退到 mock 返回 0.0。
    """
    try:
        from app.services.commodity.unified_commodity_service import service
        quote = await service.get_realtime_quote(full_symbol)
        return quote if quote is not None else 0.0
    except Exception as exc:
        logger.debug("paper quote_fn fallback: %s (%s)", full_symbol, exc)
        return 0.0


# =============================================================================
# 服务单例
# =============================================================================

class CommodityPaperTradingService:
    """大宗商品模拟交易 FastAPI 服务。

    持有 PaperServiceContext(含 repo + quote_fn + sse_fn),
    供 HTTP 路由器端到端调用。
    """

    def __init__(self):
        self._ctx: Optional[PaperServiceContext] = None

    # ---- 上下文懒初始化 ----

    @property
    def ctx(self) -> PaperServiceContext:
        if self._ctx is None:
            self._ctx = PaperServiceContext.default()
            # 注入真实行情(即有 unified_commodity_service 时使用)
            self._ctx.quote_fn = _real_quote_fn
        return self._ctx

    # ---- 异常转换 ----

    def _raise_on_error(self, exc: Exception) -> None:
        """将业务异常转换为 HTTPException。

        注意:repo 层的 get_or_404 抛 ValueError(约定),上层统一捕获转 404。
        """
        if isinstance(exc, (AccountNotFound, ValueError)):
            # ValueError 来自 repo.get_or_404("paper xxx not found: xxx")
            detail = str(exc) if isinstance(exc, AccountNotFound) else str(exc)
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
        if isinstance(exc, OrderRejected):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "order_rejected", "reason": exc.reason, "message": str(exc)},
            )
        if isinstance(exc, InsufficientMargin):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "insufficient_margin", "message": str(exc)},
            )
        if isinstance(exc, PaperTradingError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
        # 未预期的异常让 FastAPI 全局 handler 处理
        raise exc

    # ---- 账户 ----

    async def create_account(
        self, user_id: str, name: str = "默认账户",
        initial_capital: Optional[float] = None,
    ) -> Dict[str, Any]:
        """创建模拟账户。"""
        try:
            acc = await svc_create_account(self.ctx, user_id, name, initial_capital)
            return acc.to_snapshot_dict()
        except Exception as e:
            self._raise_on_error(e)

    async def get_account(self, account_id: str) -> Dict[str, Any]:
        """获取账户详情(ODM dict)。"""
        try:
            acc = await svc_get_account(self.ctx, account_id)
            return acc.to_snapshot_dict()
        except Exception as e:
            self._raise_on_error(e)

    async def get_account_snapshot(self, account_id: str) -> Dict[str, Any]:
        """获取账户快照(含账户 + 持仓 + 最新订单)。"""
        try:
            snapshot = await svc_get_account_snapshot(self.ctx, account_id)
            positions = await svc_list_positions(self.ctx, account_id, open_only=True)
            snapshot["positions"] = [self._position_to_dict(p) for p in positions]
            return snapshot
        except Exception as e:
            self._raise_on_error(e)

    async def get_account_metrics(self, account_id: str) -> Dict[str, Any]:
        """获取账户指标(含 PnL 明细)。"""
        try:
            metrics = await svc_get_account_metrics(self.ctx, account_id)
            return {
                "equity": round(metrics.equity, 2),
                "margin_used": round(metrics.margin_used, 2),
                "available": round(metrics.available, 2),
                "unrealized_pnl": round(metrics.unrealized_pnl, 2),
                "realized_pnl": round(metrics.realized_pnl, 2),
                "risk_ratio": round(metrics.risk_ratio, 4),
            }
        except Exception as e:
            self._raise_on_error(e)

    async def reset_account(self, account_id: str) -> Dict[str, Any]:
        """重置账户到初始资金。"""
        try:
            acc = await svc_reset_account(self.ctx, account_id)
            return acc.to_snapshot_dict()
        except Exception as e:
            self._raise_on_error(e)

    async def list_user_accounts(self, user_id: str) -> List[Dict[str, Any]]:
        """列出用户所有账户。"""
        try:
            accounts = await svc_list_accounts(self.ctx, user_id)
            return [a.to_snapshot_dict() for a in accounts]
        except Exception as e:
            self._raise_on_error(e)

    # ---- 订单 ----

    async def submit_order(
        self,
        account_id: str,
        full_symbol: str,
        direction: str,
        offset: str,
        order_type: str,
        lots: int,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        source: str = "manual",
        decision_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """提交订单。"""
        try:
            req = SubmitOrderRequest(
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
                source=source,
                decision_id=decision_id,
            )
            result = await svc_submit_order(self.ctx, req)
            ret: Dict[str, Any] = {"status": "accepted"}
            if result.reject_reason:
                ret["reject_reason"] = result.reject_reason
                ret["status"] = "rejected"
            if result.fill:
                ret["fill"] = {
                    "order_id": result.fill.order_id,
                    "full_symbol": result.fill.full_symbol,
                    "direction": result.fill.direction,
                    "offset": result.fill.offset,
                    "lots": result.fill.lots,
                    "price": result.fill.price,
                    "commission": result.fill.commission,
                    "slippage": result.fill.slippage,
                }
            return ret
        except Exception as e:
            self._raise_on_error(e)

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """撤单。"""
        try:
            order = await svc_cancel_order(self.ctx, order_id)
            return {"order_id": order.id, "status": order.status}
        except Exception as e:
            self._raise_on_error(e)

    async def list_orders(
        self, account_id: str, *,
        status: Optional[str] = None,
        full_symbol: Optional[str] = None,
        limit: int = 50,
        skip: int = 0,
    ) -> Dict[str, Any]:
        """订单列表。"""
        try:
            orders = await svc_list_orders(
                self.ctx, account_id,
                status=status, full_symbol=full_symbol,
                limit=limit, skip=skip,
            )
            return {
                "orders": [self._order_to_dict(o) for o in orders],
                "total": len(orders),
                "limit": limit,
                "skip": skip,
            }
        except Exception as e:
            self._raise_on_error(e)

    # ---- 持仓 ----

    async def list_positions(
        self, account_id: str, *, open_only: bool = True,
    ) -> Dict[str, Any]:
        """持仓列表。"""
        try:
            positions = await svc_list_positions(self.ctx, account_id, open_only=open_only)
            return {"positions": [self._position_to_dict(p) for p in positions]}
        except Exception as e:
            self._raise_on_error(e)

    # ---- 成交 ----

    async def list_fills(
        self, account_id: str, *,
        full_symbol: Optional[str] = None,
        limit: int = 100,
        skip: int = 0,
    ) -> Dict[str, Any]:
        """成交记录列表。"""
        try:
            fills = await svc_list_fills(
                self.ctx, account_id,
                full_symbol=full_symbol, limit=limit, skip=skip,
            )
            return {
                "fills": [self._fill_to_dict(f) for f in fills],
                "total": len(fills),
            }
        except Exception as e:
            self._raise_on_error(e)

    # ---- 决策下单 ----

    async def from_decision(
        self, account_id: str, decision_id: str,
        override_lots: Optional[int] = None,
    ) -> Dict[str, Any]:
        """从 CIO 决策自动下单。"""
        try:
            result = await svc_from_decision(self.ctx, account_id, decision_id, override_lots)
            return result
        except Exception as e:
            self._raise_on_error(e)

    # ---- 辅助序列化 ----

    @staticmethod
    def _position_to_dict(pos) -> Dict[str, Any]:
        return {
            "id": pos.id,
            "account_id": pos.account_id,
            "full_symbol": pos.full_symbol,
            "direction": pos.direction,
            "lots": pos.lots,
            "avg_cost": round(pos.avg_cost, 2) if pos.avg_cost else 0.0,
            "current_price": round(pos.current_price, 2) if pos.current_price else 0.0,
            "floating_pnl": round(pos.floating_pnl, 2) if pos.floating_pnl else 0.0,
            "margin_used": round(pos.margin_used, 2) if pos.margin_used else 0.0,
            "stop_loss": round(pos.stop_loss, 2) if pos.stop_loss else None,
            "take_profit": round(pos.take_profit, 2) if pos.take_profit else None,
            "opened_at": str(pos.opened_at) if pos.opened_at else None,
            "updated_at": str(pos.updated_at) if pos.updated_at else None,
        }

    @staticmethod
    def _order_to_dict(order) -> Dict[str, Any]:
        return {
            "id": order.id,
            "account_id": order.account_id,
            "full_symbol": order.full_symbol,
            "direction": order.direction,
            "offset": order.offset,
            "order_type": order.order_type,
            "lots": order.lots,
            "price": round(order.price, 2) if order.price else None,
            "stop_price": round(order.stop_price, 2) if order.stop_price else None,
            "stop_loss": round(order.stop_loss, 2) if order.stop_loss else None,
            "take_profit": round(order.take_profit, 2) if order.take_profit else None,
            "status": order.status,
            "filled_lots": order.filled_lots,
            "filled_avg_price": round(order.filled_avg_price, 2) if order.filled_avg_price else 0.0,
            "commission": round(order.commission, 2),
            "source": order.source,
            "decision_id": order.decision_id,
            "created_at": str(order.created_at) if order.created_at else None,
            "filled_at": str(order.filled_at) if order.filled_at else None,
            "cancelled_at": str(order.cancelled_at) if order.cancelled_at else None,
        }

    @staticmethod
    def _fill_to_dict(fill) -> Dict[str, Any]:
        return {
            "id": fill.id,
            "order_id": fill.order_id,
            "account_id": fill.account_id,
            "full_symbol": fill.full_symbol,
            "direction": fill.direction,
            "offset": fill.offset,
            "lots": fill.lots,
            "price": round(fill.price, 2),
            "commission": round(fill.commission, 2),
            "slippage": round(fill.slippage, 2),
            "matched_at": str(fill.matched_at) if fill.matched_at else None,
        }


# =============================================================================
# 模块级服务单例(与 unified_commodity_service 风格一致)
# =============================================================================

service = CommodityPaperTradingService()
