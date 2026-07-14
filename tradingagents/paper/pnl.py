"""
PnL 计算(`tradingagents/paper/pnl.py`)

提供纯函数,所有 PnL 计算依赖:
- Position / SubmitOrderRequest / Fill(types.py)
- ContractSpec / spec_by_full_symbol(spec.py)

核心函数:
- calc_floating_pnl    单持仓浮动 PnL
- calc_realized_pnl    单笔已实现 PnL(平仓)
- aggregate_floating_pnl 多持仓聚合
- mark_position_to_market 按当前价刷新 Position 的 floating_pnl 字段
- calc_commission_for_fill 单笔成交应扣手续费(单边)
- calc_round_trip_pnl  开仓→平仓链路总 PnL(便于回测示例)

符号规则:
- direction=long(多头):price↑ → PnL+
- direction=short(空头):price↓ → PnL+
- 公式:(price - avg_cost) × lots × contract_size × sign
  其中 sign = +1 for long, -1 for short
"""
from __future__ import annotations

from typing import Iterable, Mapping

from .spec import ContractSpec, calc_commission
from .types import Direction, Fill, Position


# =============================================================================
# 内部辅助
# =============================================================================

def _direction_sign(direction: Direction) -> int:
    """long → +1, short → -1。"""
    return 1 if direction == "long" else -1


# =============================================================================
# 浮动 PnL — 单持仓 / 聚合 / 标记到市价
# =============================================================================

def calc_floating_pnl(
    pos: Position,
    current_price: float,
    spec: ContractSpec,
) -> float:
    """计算单持仓的浮动 PnL。

    Args:
        pos: 持仓对象(lots 必须 > 0,否则返回 0)
        current_price: 当前最新价
        spec: 合约规格

    Returns:
        浮动盈亏金额(元,可正可负)。未开仓返回 0。
    """
    if pos.lots <= 0:
        return 0.0
    sign = _direction_sign(pos.direction)
    return (current_price - pos.avg_cost) * pos.lots * spec.contract_size * sign


def mark_position_to_market(
    pos: Position,
    current_price: float,
    spec: ContractSpec,
) -> Position:
    """按当前价刷新 Position 的 floating_pnl / current_price 字段。

    返回新的 Position 实例(原对象不变,Position 是 mutable dataclass 但本函数按
    "返回新对象"模式实现以方便 immutable 调用)。

    Args:
        pos: 原持仓
        current_price: 最新价
        spec: 合约规格

    Returns:
        新 Position 实例,current_price / floating_pnl 已更新。
    """
    new_pnl = calc_floating_pnl(pos, current_price, spec)
    # dataclasses.replace 标准替代法
    from dataclasses import replace
    return replace(
        pos,
        current_price=current_price,
        floating_pnl=new_pnl,
    )


def aggregate_floating_pnl(
    positions: Iterable[Position],
    spec_for: Mapping[str, ContractSpec],
    current_prices: Mapping[str, float],
) -> float:
    """聚合多持仓的浮动 PnL。

    Args:
        positions: 持仓列表
        spec_for: full_symbol → ContractSpec 映射(可只包含持仓对应的品种)
        current_prices: full_symbol → 最新价 映射

    Returns:
        全部持仓的浮动 PnL 总和(忽略 current_prices 缺失的持仓 — 用 0)。

    Notes:
        - 若持仓的 full_symbol 不在 spec_for 中,该持仓按 0 PnL 处理(防御性)
        - 没传 current_price 的持仓视为陈旧报价,按持仓自身 current_price 计算
    """
    total = 0.0
    for pos in positions:
        if pos.lots <= 0:
            continue
        spec = spec_for.get(pos.full_symbol)
        if spec is None:
            continue
        price = current_prices.get(pos.full_symbol, pos.current_price)
        total += calc_floating_pnl(pos, price, spec)
    return total


# =============================================================================
# 已实现 PnL(平仓)
# =============================================================================

def calc_realized_pnl(
    open_avg_cost: float,
    close_price: float,
    lots: int,
    direction: Direction,
    spec: ContractSpec,
) -> float:
    """计算平仓已实现 PnL(单笔平仓或聚合)。

    Args:
        open_avg_cost: 开仓加权平均成本
        close_price: 平仓价
        lots: 平仓手数(>0)
        direction: 持仓方向(long / short)
        spec: 合约规格

    Returns:
        已实现盈亏金额(可正可负)。

    公式:(close_price - open_avg_cost) × lots × contract_size × sign
    """
    if lots <= 0:
        return 0.0
    sign = _direction_sign(direction)
    return (close_price - open_avg_cost) * lots * spec.contract_size * sign


def calc_round_trip_pnl(
    open_price: float,
    close_price: float,
    lots: int,
    direction: Direction,
    spec: ContractSpec,
) -> float:
    """开仓→平仓链路总 PnL(忽略手续费)。

    与 calc_realized_pnl 等价;提供友好别名便于回测脚本调用。
    """
    return calc_realized_pnl(
        open_avg_cost=open_price,
        close_price=close_price,
        lots=lots,
        direction=direction,
        spec=spec,
    )


# =============================================================================
# 手续费(基于 spec / fill)
# =============================================================================

def calc_commission_for_fill(
    lots: int,
    price: float,
    spec: ContractSpec,
) -> float:
    """单笔成交应扣手续费(单边)。

    实际双边合计 = 2 × 此值(开仓+平仓各算一次)。

    Args:
        lots: 成交手数
        price: 成交价
        spec: 合约规格

    Returns:
        单边手续费金额(元)。
    """
    return calc_commission(lots, price, spec)


def calc_round_trip_commission(
    lots: int,
    price: float,
    spec: ContractSpec,
) -> float:
    """一开一平双边手续费合计 = 2 × 单边。"""
    return 2 * calc_commission(lots, price, spec)


# =============================================================================
# 收益指标(辅助函数,便于前端展示)
# =============================================================================

def calc_return_pct(pnl: float, initial_capital: float) -> float:
    """盈亏百分比 = pnl / initial_capital。

    Args:
        pnl: 盈亏金额
        initial_capital: 初始资金(分母 <= 0 时返回 0)

    Returns:
        百分比(0.05 = 5%)。
    """
    if initial_capital <= 0:
        return 0.0
    return pnl / initial_capital


__all__ = [
    "calc_floating_pnl",
    "mark_position_to_market",
    "aggregate_floating_pnl",
    "calc_realized_pnl",
    "calc_round_trip_pnl",
    "calc_commission_for_fill",
    "calc_round_trip_commission",
    "calc_return_pct",
]
