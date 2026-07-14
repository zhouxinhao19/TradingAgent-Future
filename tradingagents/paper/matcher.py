"""
撮合引擎 — 纯逻辑层(`tradingagents/paper/matcher.py`)

Phase 4 第二刀交付,纯函数 API,无 MongoDB / SSE 依赖:
- 配置(从 .env):PAPER_MATCHING_MODE / PAPER_SLIPPAGE_BPS / PAPER_MAX_LOTS_PER_ORDER /
  PAPER_MAX_POSITION_PER_SYMBOL
- pre_check_order(req, account, spec, prev_settlement, current_position_lots)
    → (ok, reason):涨跌停 + 限额 + 资金预检(下单前置闸口)
- apply_slippage(price, direction) → (new_price, slippage_amount):不利方向滑点
- match_current_price(req, current_quote, spec) → Optional[Fill]:
    current_price mode 下立即撮合判定(market 立即 / limit 触价 / stop 触发)
- get_slippage_config() / get_matching_config():配置快照(便于测试 override)

第三刀将负责:
- 异步编排(PaperOrder 落库 → SSE 推送 → 持仓 / 账户更新 → 风险巡检)
- 限价挂单轮询(每分钟扫一次,触价后再 match_current_price)
- 止损 / 条件单 / 大单 VWAP 撮合

公式速查:
- 滑点(bps):PAPER_SLIPPAGE_BPS / 10000 = 0.0001
- 多(买入)滑点:+price × bps;空(卖出)滑点:-price × bps
- 涨跌停区间:[prev * (1 - limit), prev * (1 + limit)](闭区间,等号可成交)
"""
from __future__ import annotations

import os
from typing import Optional, Tuple

from .spec import (
    ContractSpec,
    calc_commission,
    check_price_limit,
)
from .types import (
    Direction,
    Fill,
    RejectReason,
    SubmitOrderRequest,
)


# =============================================================================
# 配置(从环境变量加载,可单元测试期间 monkey patch os.environ)
# =============================================================================

PAPER_MATCHING_MODE = os.getenv("PAPER_MATCHING_MODE", "current_price")
PAPER_SLIPPAGE_BPS = float(os.getenv("PAPER_SLIPPAGE_BPS", "1"))
PAPER_MAX_LOTS_PER_ORDER = int(os.getenv("PAPER_MAX_LOTS_PER_ORDER", "10"))
PAPER_MAX_POSITION_PER_SYMBOL = int(
    os.getenv("PAPER_MAX_POSITION_PER_SYMBOL", "50")
)


def get_slippage_config() -> dict:
    """返回当前滑点配置快照(便于测试断言 / API 暴露)。"""
    return {
        "matching_mode": PAPER_MATCHING_MODE,
        "slippage_bps": PAPER_SLIPPAGE_BPS,
        "max_lots_per_order": PAPER_MAX_LOTS_PER_ORDER,
        "max_position_per_symbol": PAPER_MAX_POSITION_PER_SYMBOL,
    }


# =============================================================================
# 滑点
# =============================================================================

def apply_slippage(price: float, direction: Direction) -> Tuple[float, float]:
    """对成交价施加滑点(不利方向滑动)。

    Args:
        price: 当前最新成交价(撮合结果)
        direction: 成交方向(long=买入 → 往上滑 ; short=卖出 → 往下滑)

    Returns:
        (slipped_price, slippage_amount):
        - slipped_price:含滑点的实际成交价
        - slippage_amount:滑点金额(绝对值,便于记账;对 long 为正、对 short 也存正值)

    滑点量 = price × (PAPER_SLIPPAGE_BPS / 10000)
    """
    if price < 0:
        raise ValueError(f"apply_slippage: price 不能为负,实际={price}")
    bps_fraction = PAPER_SLIPPAGE_BPS / 10000.0
    slippage_amount = price * bps_fraction
    sign = 1 if direction == "long" else -1
    slipped_price = price + slippage_amount * sign
    return slipped_price, slippage_amount


# =============================================================================
# 下单预检
# =============================================================================

def pre_check_order(
    req: SubmitOrderRequest,
    account_balance: float,
    account_available: float,
    spec: ContractSpec,
    prev_settlement: float,
    current_position_lots: int = 0,
    current_position_direction: Optional[Direction] = None,
) -> Tuple[bool, Optional[RejectReason]]:
    """下单前预检闸口(在写库前调用,通过后才入 pending 队列)。

    Args:
        req: 下单请求
        account_balance: 当前账户余额(冗余信息,用于穿仓预判)
        account_available: 当前可用资金(equity - margin_used - frozen)
        spec: 合约规格
        prev_settlement: 昨结算价(用于涨跌停区间计算)
        current_position_lots: 当前同品种持仓手数(用于限仓)
        current_position_direction: 当前同品种持仓方向(用于校验 close)

    Returns:
        (ok, reason):
        - ok=True, reason=None:通过
        - ok=False, reason=具体 RejectReason:被拒单
    """
    # ---- 基础校验 ----
    if req.lots <= 0:
        return False, "invalid_lots"

    if req.lots > PAPER_MAX_LOTS_PER_ORDER:
        return False, "exceeds_max_lots_per_order"

    # ---- 平仓校验:不能超过持仓手数 ----
    if req.offset in ("close", "close_today", "close_yesterday"):
        if req.lots > current_position_lots:
            return False, "invalid_lots"
        if current_position_lots == 0:
            # 没持仓但要平仓,允许时匹配引擎会忽略(防御)
            return False, "invalid_lots"
        # 平仓方向必须与持仓方向一致
        if current_position_direction and current_position_direction != req.direction:
            return False, "invalid_lots"

    # ---- 涨跌停预检(限价 / 止损单) ----
    if req.order_type == "limit":
        if req.price is None or req.price <= 0:
            return False, "invalid_lots"
        if not check_price_limit(req.price, prev_settlement, spec):
            return False, "price_exceeds_limit"

    if req.order_type in ("stop", "stop_limit"):
        if req.stop_price is None or req.stop_price <= 0:
            return False, "invalid_lots"
        # 止损触发价也应在涨跌停区间内
        if not check_price_limit(req.stop_price, prev_settlement, spec):
            return False, "price_exceeds_limit"
        if req.order_type == "stop_limit" and req.price is None:
            return False, "invalid_lots"

    # ---- 开仓资金预检 ----
    if req.offset == "open":
        # 反向开仓时,所需保证金按"新开仓手数 × 价 × 合约乘数 × 保证金率"扣
        from .spec import calc_margin
        ref_price = req.price or prev_settlement
        if ref_price <= 0:
            return False, "invalid_lots"
        required_margin = calc_margin(req.lots, ref_price, spec)
        if required_margin > account_available:
            return False, "insufficient_margin"

        # ---- 持仓限额预检 ----
        # 反向开仓不增加该方向净持仓(实际上是平+开),这里只对同向加仓严格限制
        if (current_position_direction is None
                or current_position_direction == req.direction):
            projected_lots = current_position_lots + req.lots
        else:
            # 反向开仓:净持仓变化 = 开新仓手数 - 平旧仓手数
            projected_lots = abs(req.lots - current_position_lots)
        if projected_lots > PAPER_MAX_POSITION_PER_SYMBOL:
            return False, "exceeds_max_position_per_symbol"

    return True, None


# =============================================================================
# 立即撮合(current_price 模式)
# =============================================================================

def match_current_price(
    req: SubmitOrderRequest,
    current_quote: float,
    spec: ContractSpec,
    order_id: str,
) -> Optional[Fill]:
    """current_price 模式下撮合判定。

    撮合规则:
    - market 单:任何行情立即成交,价格 = current_quote ± slippage
    - limit 单(买入):仅当 current_quote <= limit_price 时成交
    - limit 单(卖出):仅当 current_quote >= limit_price 时成交
    - stop 单:仅当行情触达 stop_price 时成交(本函数不维护价格历史,返回 None 表示挂单)
    - stop_limit 单:触达 stop_price 后转为 limit,逻辑同 limit(本函数返回 None 表示挂单)

    Args:
        req: 下单请求
        current_quote: 当前最新行情(撮合价基准)
        spec: 合约规格
        order_id: 撮合生成的 order_id(用于 Fill 关联)

    Returns:
        Fill 实例(立即成交) / None(挂单等待触价)
    """
    if current_quote <= 0:
        return None

    fill_price = None

    if req.order_type == "market":
        # 市价单立即成交
        fill_price = current_quote

    elif req.order_type == "limit":
        if req.price is None or req.price <= 0:
            return None
        # 限价买入:市价 ≤ 限价才接受;限价卖出:市价 ≥ 限价才接受
        if req.direction == "long" and current_quote <= req.price:
            fill_price = req.price  # 按限价成交
        elif req.direction == "short" and current_quote >= req.price:
            fill_price = req.price

    elif req.order_type == "stop":
        # 止损单:本函数不维护价格历史;交由 risk.loop 巡检触价后再调用
        return None

    elif req.order_type == "stop_limit":
        return None

    if fill_price is None:
        return None

    # 施加滑点
    slipped_price, slippage_amount = apply_slippage(fill_price, req.direction)

    # 计算单边手续费
    commission = calc_commission(req.lots, slipped_price, spec)

    return Fill(
        order_id=order_id,
        account_id=req.account_id,
        full_symbol=req.full_symbol,
        direction=req.direction,
        offset=req.offset,
        lots=req.lots,
        price=slipped_price,
        commission=commission,
        slippage=slippage_amount,
    )


# =============================================================================
# 触发价判定(供 risk/risk_inspect 轮询调用)
# =============================================================================

def is_stop_triggered(
    direction: Direction,
    stop_price: float,
    current_quote: float,
    is_long: bool,
) -> bool:
    """止损触发判定。

    多仓止损触发:current_quote <= stop_price
    空仓止损触发:current_quote >= stop_price

    Args:
        direction: 下单方向(long / short)—— 此参数预留,实际判定只用 is_long
        stop_price: 触发价
        current_quote: 当前价
        is_long: 当前持仓方向是否为多

    Returns:
        True 表示触发止损,应自动平仓。

    兼容 stop_loss(止损)与 take_profit(止盈):take_profit 触发价在"有利方向",
    多仓 take_profit 触发:current_quote >= tp_price,空仓 tp:current_quote <= tp_price
    """
    if is_long:
        return current_quote <= stop_price
    return current_quote >= stop_price


def is_take_profit_triggered(
    stop_price: float,   # 此处实为 take_profit
    current_quote: float,
    is_long: bool,
) -> bool:
    """止盈触发判定(与 is_stop_triggered 方向相反)。"""
    if is_long:
        return current_quote >= stop_price
    return current_quote <= stop_price


__all__ = [
    # 配置
    "PAPER_MATCHING_MODE",
    "PAPER_SLIPPAGE_BPS",
    "PAPER_MAX_LOTS_PER_ORDER",
    "PAPER_MAX_POSITION_PER_SYMBOL",
    "get_slippage_config",
    # 核心
    "apply_slippage",
    "pre_check_order",
    "match_current_price",
    "is_stop_triggered",
    "is_take_profit_triggered",
]
