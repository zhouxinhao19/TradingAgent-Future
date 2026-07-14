"""
大宗商品模拟交易 ODM 模型(`app/models/commodity_paper.py`)

Phase 4 第三刀交付:
- 5 个 Pydantic v2 ODM 类,对应 MongoDB 5 集合(paper_accounts / paper_orders /
  paper_positions / paper_fills / paper_daily_snapshots)
- 字段严格对齐 phase-4.md §三 数据模型
- 字段命名遵循:
  - MongoDB 主键统一为字符串 UUID(str,而非 ObjectId),便于前端 / Redis 直接使用
  - 时间字段统一为带时区 datetime,序列化为 ISO 8601
  - Pydantic v2 ConfigDict(populate_by_name + arbitrary_types_allowed)

设计原则:
- 与 `tradingagents.paper.types` 中的 dataclass 保持一一对应,但为持久化形态
  增加 id / user_id / *_at 时间戳字段
- 6 大关系字段(account_id / order_id / full_symbol)统一建索引
- all 字段默认 None 或安全默认值,支持部分更新
"""
from __future__ import annotations

from datetime import datetime
from datetime import date as _date
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.utils.timezone import now_tz


# =============================================================================
# 枚举类型(与 tradingagents.paper.types 保持一致)
# =============================================================================

AccountStatus = Literal["active", "closed"]
OrderSource = Literal["manual", "agent_decision"]
OrderDirection = Literal["long", "short"]
OffsetFlag = Literal["open", "close", "close_today", "close_yesterday"]
OrderType = Literal["market", "limit", "stop", "stop_limit"]
OrderStatus = Literal["pending", "filled", "partial", "cancelled", "rejected"]


def _new_uuid() -> str:
    """生成新的 UUID4 字符串(作为 MongoDB _id 与业务 id 通用)。"""
    return str(uuid4())


# =============================================================================
# PaperAccount — 账户主表
# =============================================================================

class PaperAccount(BaseModel):
    """模拟账户主表 / MongoDB `paper_accounts` 集合。

    字段来源:
    - id / user_id / name / initial_capital:开户时确定
    - balance / available / margin_used / frozen / equity:
      账户聚合指标,由 service 层 recalculate_account() 持续维护
    - realized_pnl / unrealized_pnl:累计已实现 + 当前浮动盈亏(快照式)
    - risk_ratio:margin_used / equity,>1 触发强平信号
    - status:active(运营中) / closed(软删)
    """
    id: str = Field(default_factory=_new_uuid, description="账户 UUID")

    # 用户关联(user_id 字符串,与 app/models/user.py 的 username 或 _id 关联,
    # Phase 4 暂用 username 简化,后续切到 ObjectId)
    user_id: str = Field(..., description="所属用户名/用户 ID")
    name: str = Field(default="默认账户", description="账户显示名")
    initial_capital: float = Field(default=1_000_000.0, description="初始资金")

    # 账户核心余额
    balance: float = Field(..., description="账户余额(扣手续费/已实现盈亏)")
    available: float = Field(..., description="可用资金 = balance - margin_used - frozen")
    margin_used: float = Field(default=0.0, description="占用保证金")
    frozen: float = Field(default=0.0, description="冻结(挂单未成交)")

    # 衍生指标
    equity: float = Field(..., description="净值 = balance + unrealized_pnl")
    realized_pnl: float = Field(default=0.0, description="累计已实现盈亏")
    unrealized_pnl: float = Field(default=0.0, description="当前浮动盈亏快照")
    risk_ratio: float = Field(default=0.0, description="风险度 = margin_used / equity")

    # 元信息
    status: AccountStatus = Field(default="active")
    created_at: datetime = Field(default_factory=now_tz)
    updated_at: datetime = Field(default_factory=now_tz)

    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    @field_serializer("created_at", "updated_at")
    def serialize_datetime(self, dt: Optional[datetime], _info) -> Optional[str]:
        """统一序列化 datetime 为 ISO 8601(含时区)。"""
        if dt is None:
            return None
        return dt.isoformat()

    def to_snapshot_dict(self) -> Dict[str, Any]:
        """转换为前端聚合快照 dict(供 /equity 端点或 SSE 推送)。"""
        return {
            "account_id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "initial_capital": self.initial_capital,
            "balance": round(self.balance, 2),
            "available": round(self.available, 2),
            "margin_used": round(self.margin_used, 2),
            "frozen": round(self.frozen, 2),
            "equity": round(self.equity, 2),
            "realized_pnl": round(self.realized_pnl, 2),
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "risk_ratio": round(self.risk_ratio, 4),
            "status": self.status,
            "updated_at": self.updated_at,
        }


# =============================================================================
# PaperOrder — 订单表
# =============================================================================

class PaperOrder(BaseModel):
    """模拟订单 / MongoDB `paper_orders` 集合。

    状态机:
    - pending → filled(全部成交)
    - pending → partial(部分成交,Phase 4 简化暂用一步到位模式,可扩展)
    - pending → cancelled(撤单)
    - pending → rejected(预检拒单,无 fill 记录)
    """
    id: str = Field(default_factory=_new_uuid, description="订单 UUID")
    account_id: str = Field(..., description="所属账户 ID")

    full_symbol: str = Field(..., description="标的代码,如 CU2501.SHF")
    direction: OrderDirection = Field(..., description="long 多 / short 空")
    offset: OffsetFlag = Field(..., description="open 开仓 / close 平仓 / close_today / close_yesterday")
    order_type: OrderType = Field(..., description="market 立即 / limit 限价 / stop 止损 / stop_limit")
    lots: int = Field(..., ge=0, description="委托手数")

    # 类型专属价格
    price: Optional[float] = Field(default=None, description="限价(限价单必填)")
    stop_price: Optional[float] = Field(default=None, description="触发价(止损单必填)")

    # 风控字段(可选)
    stop_loss: Optional[float] = Field(default=None, description="附带止损")
    take_profit: Optional[float] = Field(default=None, description="附带止盈")

    # 成交与状态
    status: OrderStatus = Field(default="pending")
    filled_lots: int = Field(default=0, description="已成交手数")
    filled_avg_price: float = Field(default=0.0, description="加权平均成交价")
    commission: float = Field(default=0.0, description="累计手续费")
    slippage: float = Field(default=0.0, description="累计滑点金额")

    # 拒单原因
    reject_reason: Optional[str] = Field(default=None, description="拒单原因 enum string")

    # 来源信息
    source: OrderSource = Field(default="manual", description="manual / agent_decision")
    decision_id: Optional[str] = Field(default=None, description="来自 Phase 3b CIO 决策 ID")

    # 时间戳
    created_at: datetime = Field(default_factory=now_tz)
    updated_at: datetime = Field(default_factory=now_tz)
    filled_at: Optional[datetime] = Field(default=None)
    cancelled_at: Optional[datetime] = Field(default=None)
    rejected_at: Optional[datetime] = Field(default=None)

    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    @field_serializer(
        "created_at", "updated_at", "filled_at", "cancelled_at", "rejected_at"
    )
    def serialize_datetime(self, dt: Optional[datetime], _info) -> Optional[str]:
        if dt is None:
            return None
        return dt.isoformat()


# =============================================================================
# PaperPosition — 持仓表(净持仓)
# =============================================================================

class PaperPosition(BaseModel):
    """模拟持仓 / MongoDB `paper_positions` 集合。

    设计要点(Phase 4 简化):
    - **净持仓模型**(同一品种同一方向合并到一条记录)
    - lots=0 视为已平仓,但为审计保留 doc,可加 status=closed 过滤
    - avg_cost 不含手续费(手续费独立记账),与 tradingagents.paper.pnl 设计一致
    """
    id: str = Field(default_factory=_new_uuid, description="持仓记录 UUID")
    account_id: str = Field(..., description="所属账户 ID")

    full_symbol: str = Field(..., description="标的,如 RB2501.DCE")
    direction: OrderDirection = Field(..., description="long / short")
    lots: int = Field(default=0, ge=0, description="净手数(0=已平)")
    avg_cost: float = Field(default=0.0, description="加权平均开仓价(不含手续费)")
    current_price: float = Field(default=0.0, description="最新价(由盯市更新)")

    floating_pnl: float = Field(default=0.0, description="浮动盈亏(快照)")
    margin_used: float = Field(default=0.0, description="占用保证金")

    # 风控
    stop_loss: Optional[float] = Field(default=None)
    take_profit: Optional[float] = Field(default=None)

    # 元信息
    opened_at: Optional[datetime] = Field(default=None)
    updated_at: datetime = Field(default_factory=now_tz)
    closed_at: Optional[datetime] = Field(default=None, description="平仓时间")

    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    @field_serializer("opened_at", "updated_at", "closed_at")
    def serialize_datetime(self, dt: Optional[datetime], _info) -> Optional[str]:
        if dt is None:
            return None
        return dt.isoformat()


# =============================================================================
# PaperFill — 成交明细(append-only)
# =============================================================================

class PaperFill(BaseModel):
    """模拟成交明细 / MongoDB `paper_fills` 集合(append-only)。

    一笔订单在分批成交/部分对冲场景下会产生多条 fill;
    Phase 4 默认 current_price 撮合模式,一笔订单只产生一条 fill。
    """
    id: str = Field(default_factory=_new_uuid, description="成交 UUID")
    order_id: str = Field(..., description="所属订单 ID")
    account_id: str = Field(..., description="所属账户 ID")
    full_symbol: str = Field(..., description="标的代码")
    direction: OrderDirection = Field(..., description="开仓方向")
    offset: OffsetFlag = Field(..., description="开/平")

    lots: int = Field(..., ge=1, description="本笔成交手数")
    price: float = Field(..., description="本笔实际成交价(含滑点)")
    commission: float = Field(default=0.0, description="本笔手续费")
    slippage: float = Field(default=0.0, description="本笔滑点金额")

    matched_at: datetime = Field(default_factory=now_tz, description="撮合时间")

    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    @field_serializer("matched_at")
    def serialize_datetime(self, dt: Optional[datetime], _info) -> Optional[str]:
        if dt is None:
            return None
        return dt.isoformat()


# =============================================================================
# PaperDailySnapshot — 日终快照(供 PnL 折线图)
# =============================================================================

class PaperDailySnapshot(BaseModel):
    """日终净值快照 / MongoDB `paper_daily_snapshots` 集合。

    落库时机:
    - 每日收盘后定时任务(15:30 后 ~15:35 之间)
    - 用户主动调 /accounts/{id}/snapshot 也可生成即席快照
    - 唯一性约束(由 service 层保证):(account_id, date) 唯一
    """
    id: str = Field(default_factory=_new_uuid)
    account_id: str = Field(..., description="账户 ID")
    date: _date = Field(..., description="快照日期 YYYY-MM-DD")

    equity: float = Field(..., description="当日收盘后净值")
    balance: float = Field(default=0.0)
    realized_pnl: float = Field(default=0.0)
    unrealized_pnl: float = Field(default=0.0)

    positions_count: int = Field(default=0, description="持仓品种数")
    trades_count: int = Field(default=0, description="当日成交笔数(按 fill 聚合)")

    snapshot_at: datetime = Field(default_factory=now_tz)

    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    @field_serializer("snapshot_at")
    def serialize_datetime(self, dt: Optional[datetime], _info) -> Optional[str]:
        if dt is None:
            return None
        return dt.isoformat()


# =============================================================================
# Request / Response 模型(供 FastAPI Router 用,Phase 4 第四刀用)
# =============================================================================

class CreateAccountRequest(BaseModel):
    """POST /api/commodity/paper/accounts 请求体。"""
    user_id: str = Field(..., min_length=1, description="用户名")
    name: str = Field(default="默认账户", description="账户显示名")
    initial_capital: float = Field(default=1_000_000.0, gt=0, description="初始资金")


class CreateAccountResponse(BaseModel):
    """新建账户响应。"""
    account: PaperAccount
    message: str = "账户创建成功"


class SubmitOrderRequestBody(BaseModel):
    """POST /api/commodity/paper/orders 请求体(与 types.SubmitOrderRequest 字段对应)。"""
    account_id: str
    full_symbol: str = Field(..., description="CU2501.SHF")
    direction: OrderDirection
    offset: OffsetFlag
    order_type: OrderType
    lots: int = Field(..., gt=0)
    price: Optional[float] = None
    stop_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


class OrderListResponse(BaseModel):
    """GET /api/commodity/paper/orders 响应(简单列表,含分页信息)。"""
    orders: List[PaperOrder]
    total: int


class PositionListResponse(BaseModel):
    """GET /api/commodity/paper/positions 响应。"""
    positions: List[PaperPosition]


class FillListResponse(BaseModel):
    """GET /api/commodity/paper/fills 响应。"""
    fills: List[PaperFill]
    total: int


class SnapshotListResponse(BaseModel):
    """GET /api/commodity/paper/snapshots 响应。"""
    snapshots: List[PaperDailySnapshot]


class FromDecisionRequest(BaseModel):
    """POST /api/commodity/paper/from-decision 请求体。

    接 Phase 3b CIO 决策(decision_id 可来自 MongoDB `decisions` 集合),
    自动转换成 PaperOrder 并落库。
    """
    account_id: str = Field(..., description="模拟账户 ID")
    decision_id: str = Field(..., description="Phase 3b CIO 决策 ID")
    lots: Optional[int] = Field(
        default=None, gt=0, description="覆盖默认手数(空=按风控算法自动算)"
    )


__all__ = [
    # ODM 模型
    "PaperAccount",
    "PaperOrder",
    "PaperPosition",
    "PaperFill",
    "PaperDailySnapshot",
    # 请求/响应
    "CreateAccountRequest",
    "CreateAccountResponse",
    "SubmitOrderRequestBody",
    "OrderListResponse",
    "PositionListResponse",
    "FillListResponse",
    "SnapshotListResponse",
    "FromDecisionRequest",
    # 枚举类型别名
    "AccountStatus",
    "OrderSource",
    "OrderDirection",
    "OffsetFlag",
    "OrderType",
    "OrderStatus",
]
