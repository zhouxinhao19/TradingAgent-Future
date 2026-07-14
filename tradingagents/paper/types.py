"""
共享类型定义(`tradingagents/paper/types.py`)

为 Phase 4 paper trading 子包提供零外部依赖的 dataclass,
供 pnl / account / matcher / risk / repo 共用:

数据语义:
- Direction(持仓方向):long 多仓 / short 空仓
- OffsetFlag(开平标志):open 开仓 / close 平仓(优先平今) / close_today / close_yesterday
- OrderType:market 市价 / limit 限价 / stop 止损 / stop_limit 止损限价
- OrderStatus:pending 待成交 / filled 已成交 / partial 部分成交 / cancelled 已撤 / rejected 已拒

设计原则:
- 纯 dataclass,无 MongoDB / Pydantic 等外部依赖,便于 Phase 4 单测
- 字段命名对齐 Pydantic/MongoDB ODM 后续迁移(PaperOrder / PaperPosition / PaperAccount)
- 字段默认值与 phase-4.md §三 数据模型对齐
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Literal, Optional


# 类型别名(避免在多处重复 Literal)
Direction = Literal["long", "short"]
OffsetFlag = Literal["open", "close", "close_today", "close_yesterday"]
OrderType = Literal["market", "limit", "stop", "stop_limit"]
OrderStatus = Literal["pending", "filled", "partial", "cancelled", "rejected"]
RejectReason = Literal[
    "invalid_lots",
    "exceeds_max_lots_per_order",
    "exceeds_max_position_per_symbol",
    "insufficient_margin",
    "price_exceeds_limit",
    "unknown_symbol",
    "account_inactive",
    "market_closed",
]


# =============================================================================
# Position — 单品种持仓(净持仓模型)
# =============================================================================

@dataclass
class Position:
    """单品种净持仓。

    字段对齐 phase-4.md §3.3 PaperPosition,但去除外键 id / account_id 与 MongoDB
    时间戳字段(由 repo 层处理)。lots 为 0 表示已平仓。
    """
    full_symbol: str                               # "CU2501.SHF"
    direction: Direction                          # "long" / "short"
    lots: int                                     # 净手数(>= 0)
    avg_cost: float                               # 加权平均成本(含手续费)
    current_price: float = 0.0                    # 最新价,每分钟更新
    floating_pnl: float = 0.0                     # 浮动盈亏(快照,由 pnl 模块计算)
    margin_used: float = 0.0                      # 占用保证金
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    opened_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @property
    def is_open(self) -> bool:
        """是否持仓中(lots > 0)。"""
        return self.lots > 0

    @property
    def notional_value(self) -> float:
        """名义价值(按当前价) = lots × current_price × contract_size。
        contract_size 由 spec 层提供,本 dataclass 不持有 spec 引用。

        注:不在此处计算 notional,以免 Position dataclass 反向依赖 spec。
        """
        return 0.0  # 由调用方传入 spec 计算


# =============================================================================
# PaperAccount — 模拟账户
# =============================================================================

@dataclass
class PaperAccount:
    """模拟账户聚合状态(纯内存表示,MongoDB 持久化由 repo 层处理)。

    字段说明:
    - 原始字段:id / balance / margin_used / frozen / realized_pnl
    - 派生字段(由 account.recalculate_account 算出,不在 dataclass 中持久化):
      unrealized_pnl / equity / available / risk_ratio
    """
    id: str
    balance: float                                # 账户余额(初始 = initial_capital,扣手续费/已实现盈亏)
    margin_used: float = 0.0                      # 占用保证金
    frozen: float = 0.0                           # 冻结(挂单未成交)
    realized_pnl: float = 0.0                     # 累计已实现盈亏


# =============================================================================
# SubmitOrderRequest — 客户端发起的下单请求
# =============================================================================

@dataclass
class SubmitOrderRequest:
    """下单请求。所有字段由调用方填写,matcher 层做预检。"""
    account_id: str
    full_symbol: str                              # "CU2501.SHF"
    direction: Direction                         # "long" / "short"
    offset: OffsetFlag                            # "open" / "close" / ...
    order_type: OrderType                         # "market" / "limit" / ...
    lots: int                                    # 委托手数(>= 1)
    price: Optional[float] = None                 # limit 单必填
    stop_price: Optional[float] = None            # stop / stop_limit 单必填
    stop_loss: Optional[float] = None             # 附带止损(持仓时生效)
    take_profit: Optional[float] = None           # 附带止盈
    source: Literal["manual", "agent_decision"] = "manual"
    decision_id: Optional[str] = None             # from_decision 调用时填


# =============================================================================
# Fill — 单笔成交记录(append-only)
# =============================================================================

@dataclass
class Fill:
    """单笔成交记录。

    对齐 phase-4.md §3.4 PaperFill,字段为内部表示,MongoDB 序列化由 repo 层完成。
    """
    order_id: str
    account_id: str
    full_symbol: str
    direction: Direction
    offset: OffsetFlag
    lots: int
    price: float                                  # 实际成交价(含滑点)
    commission: float                             # 单边手续费
    slippage: float                               # 滑点金额(>0 表示不利方向)
    matched_at: datetime = field(default_factory=datetime.utcnow)


# =============================================================================
# OrderResult — 下单返回值(matcher 层用)
# =============================================================================

@dataclass
class OrderResult:
    """下单结果的内存表示。

    - accepted + fill=None:挂单待成交(limit 等触价)
    - accepted + fill=Fill:立即成交(market / current_price mode)
    - rejected + reject_reason:拒单

    Phase 4 后续 I/O 层会把 OrderResult 拆分为 PaperOrder(accepted) + PaperFill。
    """
    status: Literal["accepted", "rejected"]
    reject_reason: Optional[RejectReason] = None  # 仅 rejected
    fill: Optional[Fill] = None                   # 仅立即成交


# =============================================================================
# 通用辅助
# =============================================================================

def lots_to_units(lots: int, contract_size: int) -> int:
    """手数 → 实物单位数(用于 PnL 计算)。"""
    return lots * contract_size


def units_to_lots(units: int, contract_size: int) -> int:
    """实物单位数 → 手数(舍入到整数,contract_size 应能整除 units)。"""
    if contract_size <= 0:
        raise ValueError(f"contract_size 必须 > 0,实际={contract_size}")
    if units % contract_size != 0:
        raise ValueError(
            f"units={units} 不能被 contract_size={contract_size} 整除"
        )
    return units // contract_size


__all__ = [
    "Direction",
    "OffsetFlag",
    "OrderType",
    "OrderStatus",
    "RejectReason",
    "Position",
    "PaperAccount",
    "SubmitOrderRequest",
    "Fill",
    "OrderResult",
    "lots_to_units",
    "units_to_lots",
]
