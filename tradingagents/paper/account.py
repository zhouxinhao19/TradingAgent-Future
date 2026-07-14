"""
账户聚合 + 持仓更新(`tradingagents/paper/account.py`)

职责:
- recalculate_account:根据持仓 + 行情重算 PaperAccount 的派生字段
- apply_fill_to_position:把成交作用于持仓(开仓 / 加仓 / 平仓 / 反向开仓)
- aggregate_account_metrics:便捷聚合函数(直接返回 equity/available/risk_ratio)
- compute_position_margin:单持仓占用保证金

设计决策:
- avg_cost 不含手续费(手续费由 balance 扣减)。若以后需要在 PnL 中扣除手续费,
  可在 account.apply_fill 时同步更新 — 此处暂不分摊到成本。
- "派生字段"unrealized_pnl / equity / available / risk_ratio 不写回 PaperAccount,
  而是由 recalculate_account 返回 dict(便于调用方灵活选择)。

锁定内存模型:
- PaperAccount 在持仓变化时不变(id / balance / margin_used / frozen / realized_pnl)
- 行情驱动的 unrealized_pnl 等每分钟重新计算,不入库
- 真正的 margin_used 在每次 apply_fill 后立即更新到 PaperAccount(recalc 后再校准)
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable, Mapping, Optional, Tuple

from .pnl import _direction_sign, calc_floating_pnl, calc_realized_pnl
from .spec import ContractSpec, calc_margin
from .types import Direction, Fill, OffsetFlag, PaperAccount, Position


# =============================================================================
# 派生账户指标 dataclass — 不写入 PaperAccount,作为纯返回类型
# =============================================================================

@dataclass(frozen=True)
class AccountMetrics:
    """账户派生指标,recalculate_account 返回类型。"""
    unrealized_pnl: float
    margin_used: float
    equity: float                                  # balance + unrealized_pnl
    available: float                               # equity - margin_used - frozen
    risk_ratio: float                              # margin_used / equity (999 表示无穷)
    realized_pnl: float                            # 透传 PaperAccount.realized_pnl


# =============================================================================
# 持仓保证金 — 单持仓占用保证金计算
# =============================================================================

def compute_position_margin(
    pos: Position,
    current_price: float,
    spec: ContractSpec,
) -> float:
    """单持仓占用保证金 = lots × current_price × contract_size × margin_rate。

    Args:
        pos: 持仓对象
        current_price: 当前最新价(最新盯市价)
        spec: 合约规格

    Returns:
        占用保证金金额(元)。
    """
    if pos.lots <= 0:
        return 0.0
    return calc_margin(pos.lots, current_price, spec)


# =============================================================================
# apply_fill_to_position — 把成交作用于持仓
# =============================================================================

def apply_fill_to_position(
    pos: Optional[Position],
    fill: Fill,
    spec: ContractSpec,
) -> Tuple[Optional[Position], float]:
    """把一笔成交作用于持仓,返回 (new_position, realized_pnl_from_this_fill)。

    Args:
        pos: 当前持仓(可能 None,表示未持仓)
        fill: 成交记录(必须含 direction / offset / lots / price)
        spec: 合约规格(用于已实现 PnL 计算)

    Returns:
        (new_position, realized_pnl):
        - new_position=None:持仓已清空,需从 DB 删除
        - realized_pnl:本次成交对账户余额的贡献(平仓部分,开仓为 0)

    行为规则:
    1. offset=open & pos is None / lots=0:
       新建持仓,lots=fill.lots, avg_cost=fill.price, direction=fill.direction
    2. offset=open & pos.direction == fill.direction:
       加仓:加权平均成本(无手续费分摊 — 手续费由账户余额扣,不进 avg_cost)
    3. offset=open & pos.direction != fill.direction:
       反向开仓:先平掉旧仓(close_amount=min(fill.lots, pos.lots)),
       剩余手数 fill.lots - close_amount 作为新方向开仓
    4. offset in (close, close_today, close_yesterday):
       平仓量 = min(fill.lots, pos.lots),实现在 fill.price 上
    5. 平仓导致 lots=0:return (None, realized_pnl)
    """
    if fill.lots <= 0:
        raise ValueError(f"fill.lots 必须 > 0,实际={fill.lots}")

    direction = fill.direction
    offset = fill.offset
    price = fill.price

    # ---- Case 1: 新开仓 ----
    if offset == "open" and (pos is None or pos.lots == 0):
        new_pos = Position(
            full_symbol=fill.full_symbol,
            direction=direction,
            lots=fill.lots,
            avg_cost=price,
        )
        return new_pos, 0.0

    # 后续 case 必须有持仓
    if pos is None or pos.lots == 0:
        # close 指令但无持仓 → 忽略,返回 (None, 0)
        return None, 0.0

    # ---- Case 2: 同向加仓 ----
    if offset == "open" and pos.direction == direction:
        total_value = pos.avg_cost * pos.lots + price * fill.lots
        new_lots = pos.lots + fill.lots
        new_avg_cost = total_value / new_lots
        new_pos = replace(
            pos,
            lots=new_lots,
            avg_cost=new_avg_cost,
        )
        return new_pos, 0.0

    # ---- Case 3: 反向开仓(先平旧仓,再开新仓) ----
    if offset == "open" and pos.direction != direction:
        close_amount = min(fill.lots, pos.lots)
        reverse_open_amount = fill.lots - close_amount

        # 1. 平掉 close_amount 手旧仓
        realized_old = calc_realized_pnl(
            pos.avg_cost, price, close_amount, pos.direction, spec
        )
        remaining_old_lots = pos.lots - close_amount

        if reverse_open_amount == 0:
            # fill.lots == close_amount,完全平掉旧仓
            if remaining_old_lots == 0:
                return None, realized_old
            else:
                new_pos = replace(pos, lots=remaining_old_lots)
                return new_pos, realized_old

        # 2. 剩余 fill.lots - close_amount 手作为新方向开仓
        new_avg = price  # 不分摊手续费到成本
        new_pos = Position(
            full_symbol=fill.full_symbol,
            direction=direction,
            lots=reverse_open_amount,
            avg_cost=new_avg,
        )
        return new_pos, realized_old

    # ---- Case 4: 平仓(close / close_today / close_yesterday) ----
    if offset in ("close", "close_today", "close_yesterday"):
        close_amount = min(fill.lots, pos.lots)
        realized = calc_realized_pnl(
            pos.avg_cost, price, close_amount, pos.direction, spec
        )
        new_lots = pos.lots - close_amount
        if new_lots == 0:
            return None, realized
        new_pos = replace(pos, lots=new_lots)
        return new_pos, realized

    # 不应到达这里
    raise ValueError(f"apply_fill_to_position: 不支持的 offset={offset!r}")


# =============================================================================
# 账户派生指标 — recalculate_account
# =============================================================================

def recalculate_account(
    account: PaperAccount,
    positions: Iterable[Position],
    specs_by_symbol: Mapping[str, ContractSpec],
    current_prices: Mapping[str, float],
) -> AccountMetrics:
    """根据持仓和行情,重算账户派生指标。

    Args:
        account: 账户主数据(id / balance / frozen / realized_pnl / 旧 margin_used)
        positions: 当前所有持仓
        specs_by_symbol: full_symbol → ContractSpec 映射
        current_prices: full_symbol → 当前价 映射

    Returns:
        AccountMetrics(unrealized_pnl / margin_used / equity / available / risk_ratio)

    公式:
        unrealized_pnl = Σ pos.floating_pnl(当前价)
        margin_used    = Σ pos.lots × current_price × contract_size × margin_rate
        equity         = balance + unrealized_pnl
        available      = equity - margin_used - frozen
        risk_ratio     = margin_used / equity (equity <= 0 时 → 999.0 表示强平信号)

    Notes:
        - 输入 account 的 margin_used 字段**不被信任**,由本函数基于持仓+价重新计算
        - 返回 AccountMetrics 是个 frozen dataclass,不含 id(便于序列化展示)
    """
    unrealized_pnl = 0.0
    margin_used = 0.0

    for pos in positions:
        if pos.lots <= 0:
            continue
        spec = specs_by_symbol.get(pos.full_symbol)
        if spec is None:
            # 防御:持仓对应品种没找到 spec,跳过(不应发生)
            continue
        price = current_prices.get(pos.full_symbol, pos.current_price)
        if price <= 0:
            # 无报价 → 沿用持仓的当前价 / 不计 margin
            continue
        unrealized_pnl += calc_floating_pnl(pos, price, spec)
        margin_used += compute_position_margin(pos, price, spec)

    equity = account.balance + unrealized_pnl
    if equity > 0:
        risk_ratio = margin_used / equity
        available = equity - margin_used - account.frozen
    else:
        # 净值耗尽(或为负),risk_ratio 视为无穷大
        risk_ratio = 999.0
        available = 0.0
    return AccountMetrics(
        unrealized_pnl=unrealized_pnl,
        margin_used=margin_used,
        equity=equity,
        available=available,
        risk_ratio=risk_ratio,
        realized_pnl=account.realized_pnl,
    )


def aggregate_account_metrics(
    account: PaperAccount,
    positions: Iterable[Position],
    specs_by_symbol: Mapping[str, ContractSpec],
    current_prices: Mapping[str, float],
) -> AccountMetrics:
    """recalculate_account 的别名(语义清晰)。"""
    return recalculate_account(account, positions, specs_by_symbol, current_prices)


# =============================================================================
# 便捷函数 — 把账户 + 持仓 + 行情一次性转成前端展示 dict
# =============================================================================

def to_account_snapshot(
    account: PaperAccount,
    positions: Iterable[Position],
    specs_by_symbol: Mapping[str, ContractSpec],
    current_prices: Mapping[str, float],
) -> dict:
    """把账户 + 持仓 + 行情打包成 dict,便于 API 返回前端。

    返回字段:
        id, balance, margin_used, frozen, realized_pnl,
        unrealized_pnl, equity, available, risk_ratio,
        positions_count, total_long_lots, total_short_lots
    """
    positions_list = list(positions)
    metrics = recalculate_account(
        account, positions_list, specs_by_symbol, current_prices
    )
    long_lots = sum(p.lots for p in positions_list if p.direction == "long")
    short_lots = sum(p.lots for p in positions_list if p.direction == "short")
    return {
        "id": account.id,
        "balance": account.balance,
        "margin_used": metrics.margin_used,
        "frozen": account.frozen,
        "realized_pnl": account.realized_pnl,
        "unrealized_pnl": metrics.unrealized_pnl,
        "equity": metrics.equity,
        "available": metrics.available,
        "risk_ratio": metrics.risk_ratio,
        "positions_count": sum(1 for p in positions_list if p.lots > 0),
        "total_long_lots": long_lots,
        "total_short_lots": short_lots,
    }


__all__ = [
    "AccountMetrics",
    "compute_position_margin",
    "apply_fill_to_position",
    "recalculate_account",
    "aggregate_account_metrics",
    "to_account_snapshot",
]
