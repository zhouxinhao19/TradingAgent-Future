"""
tests/test_paper_matcher.py — 撮合引擎纯逻辑单测

覆盖:
- TestApplySlippage
  * 多买入 price 上滑,空卖出 price 下滑
  * 滑点金额对称性
  * 0 价格边界,负价抛错
- TestPreCheckOrder
  * 通过:开仓资金足 / 限价在涨跌停内
  * 拒单:lots ≤ 0 / 超 MAX_LOTS_PER_ORDER / 资金不足 / 限价超涨跌停 /
    持仓限额 / 平仓超现有手数 / 平仓方向错
- TestMatchCurrentPrice
  * market 立即成交
  * limit 买入触价 / 未触价
  * limit 卖出触价 / 未触价
  * stop / stop_limit 不在 match_current_price 撮合(返回 None)
- TestTriggerHelpers
  * 多仓止损 vs 止盈判定
  * 空仓止损 vs 止盈判定
- TestConfigSnapshot
  * get_slippage_config 返回 4 项

目标:≥20 测试全过。
"""
from __future__ import annotations

import pytest

from tradingagents.paper.matcher import (
    PAPER_MAX_LOTS_PER_ORDER,
    PAPER_MAX_POSITION_PER_SYMBOL,
    PAPER_SLIPPAGE_BPS,
    apply_slippage,
    get_slippage_config,
    is_stop_triggered,
    is_take_profit_triggered,
    match_current_price,
    pre_check_order,
)
from tradingagents.paper.spec import get_spec
from tradingagents.paper.types import SubmitOrderRequest


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def spec_cu():
    return get_spec("CU", "SHFE")


def _req(
    direction: str = "long",
    offset: str = "open",
    order_type: str = "market",
    lots: int = 1,
    price: float = 70500.0,
    stop_price=None,
) -> SubmitOrderRequest:
    return SubmitOrderRequest(
        account_id="acc-1",
        full_symbol="CU2501.SHF",
        direction=direction,  # type: ignore[arg-type]
        offset=offset,        # type: ignore[arg-type]
        order_type=order_type,  # type: ignore[arg-type]
        lots=lots,
        price=price,
        stop_price=stop_price,
    )


# =============================================================================
# Test 1 — TestApplySlippage
# =============================================================================

class TestApplySlippage:
    def test_long_buy_slippage_up(self):
        """多(买入)→ 价格上滑(bps=1,默认 0.01%)"""
        # 70000 * (1 + 0.0001) = 70007
        new_price, slip = apply_slippage(70000.0, "long")
        assert new_price == pytest.approx(70000.0 * 1.0001, rel=1e-9)
        # 滑点金额 = 70000 * 0.0001 = 7
        assert slip == pytest.approx(7.0)

    def test_short_sell_slippage_down(self):
        """空(卖出)→ 价格下滑"""
        new_price, slip = apply_slippage(70000.0, "short")
        assert new_price == pytest.approx(70000.0 * 0.9999, rel=1e-9)
        assert slip == pytest.approx(7.0)

    def test_slippage_amount_always_positive(self):
        """slippage_amount 在 long/short 都是正值(对记账友好)"""
        _, slip_long = apply_slippage(70000.0, "long")
        _, slip_short = apply_slippage(70000.0, "short")
        assert slip_long > 0
        assert slip_short > 0
        # 同价 long/short 滑点金额对称
        assert slip_long == pytest.approx(slip_short)

    def test_zero_price_passes_through(self):
        """price=0 不增滑点(防御性)"""
        new_price, slip = apply_slippage(0.0, "long")
        assert new_price == 0.0
        assert slip == 0.0

    def test_negative_price_raises(self):
        with pytest.raises(ValueError):
            apply_slippage(-100.0, "long")


# =============================================================================
# Test 2 — TestPreCheckOrder
# =============================================================================

class TestPreCheckOrder:
    def test_open_market_passes(self, spec_cu):
        """市价开仓:有足够资金 → 通过"""
        req = _req(direction="long", offset="open", order_type="market",
                   lots=1, price=None)
        ok, reason = pre_check_order(
            req, account_balance=1000000.0,
            account_available=500000.0,  # 1手 CU 需 35000 保证金
            spec=spec_cu, prev_settlement=70000.0,
        )
        assert ok is True
        assert reason is None

    def test_open_insufficient_margin_rejected(self, spec_cu):
        """资金不足 → insufficient_margin(用 lots=5,避开 MAX_LOTS 默认 10)"""
        req = _req(direction="long", offset="open", order_type="market",
                   lots=5, price=None)
        # 5手 CU × 70000 × 5 × 0.10 = 175000,大于 50000 可用
        ok, reason = pre_check_order(
            req, account_balance=100000.0,
            account_available=50000.0,
            spec=spec_cu, prev_settlement=70000.0,
        )
        assert ok is False
        assert reason == "insufficient_margin"

    def test_invalid_lots_zero_rejected(self, spec_cu):
        req = _req(lots=0)
        ok, reason = pre_check_order(
            req, account_balance=1000000.0,
            account_available=500000.0,
            spec=spec_cu, prev_settlement=70000.0,
        )
        assert reason == "invalid_lots"
        assert ok is False

    def test_exceeds_max_lots_rejected(self, spec_cu):
        """lots > PAPER_MAX_LOTS_PER_ORDER → exceeded_max_lots_per_order"""
        req = _req(lots=PAPER_MAX_LOTS_PER_ORDER + 1)
        ok, reason = pre_check_order(
            req, account_balance=99999999.0,
            account_available=99999999.0,
            spec=spec_cu, prev_settlement=70000.0,
        )
        assert reason == "exceeds_max_lots_per_order"

    def test_limit_price_exceeds_limit_board_rejected(self, spec_cu):
        """限价超出涨跌停上界 → price_exceeds_limit(CU limit=6%)"""
        req = _req(direction="long", offset="open", order_type="limit",
                   lots=1, price=75000.0)  # 75000 vs 70000 = +7.14% 超限
        ok, reason = pre_check_order(
            req, account_balance=1000000.0,
            account_available=500000.0,
            spec=spec_cu, prev_settlement=70000.0,
        )
        assert reason == "price_exceeds_limit"

    def test_limit_price_within_board_passes(self, spec_cu):
        """限价在涨跌停区间内 → 通过"""
        req = _req(direction="long", offset="open", order_type="limit",
                   lots=1, price=71000.0)  # 71000 vs 70000 = +1.43%
        ok, reason = pre_check_order(
            req, account_balance=1000000.0,
            account_available=500000.0,
            spec=spec_cu, prev_settlement=70000.0,
        )
        assert ok is True
        assert reason is None

    def test_close_more_than_position_rejected(self, spec_cu):
        """平仓量超过持仓 → invalid_lots"""
        req = _req(direction="long", offset="close", order_type="market",
                   lots=10, price=None)
        ok, reason = pre_check_order(
            req, account_balance=1000000.0,
            account_available=500000.0,
            spec=spec_cu, prev_settlement=70000.0,
            current_position_lots=5,
            current_position_direction="long",
        )
        assert reason == "invalid_lots"

    def test_close_wrong_direction_rejected(self, spec_cu):
        """平仓方向与持仓方向不一致 → invalid_lots"""
        req = _req(direction="short", offset="close", order_type="market",
                   lots=1, price=None)
        ok, reason = pre_check_order(
            req, account_balance=1000000.0,
            account_available=500000.0,
            spec=spec_cu, prev_settlement=70000.0,
            current_position_lots=5,
            current_position_direction="long",
        )
        assert reason == "invalid_lots"

    def test_position_limit_rejected(self, spec_cu):
        """持仓超 MAX → exceeded_max_position_per_symbol"""
        req = _req(direction="long", offset="open", order_type="market",
                   lots=10, price=None)
        ok, reason = pre_check_order(
            req, account_balance=99999999.0,
            account_available=99999999.0,
            spec=spec_cu, prev_settlement=70000.0,
            current_position_lots=PAPER_MAX_POSITION_PER_SYMBOL,
            current_position_direction="long",
        )
        assert reason == "exceeds_max_position_per_symbol"

    def test_stop_without_stop_price_rejected(self, spec_cu):
        """stop 单缺 stop_price → invalid_lots"""
        req = _req(direction="long", offset="open", order_type="stop",
                   lots=1, price=None, stop_price=None)
        ok, reason = pre_check_order(
            req, account_balance=1000000.0,
            account_available=500000.0,
            spec=spec_cu, prev_settlement=70000.0,
        )
        assert reason == "invalid_lots"


# =============================================================================
# Test 3 — TestMatchCurrentPrice
# =============================================================================

class TestMatchCurrentPrice:
    def test_market_immediate_fill(self, spec_cu):
        """market 单:任何价立即成交"""
        req = _req(direction="long", offset="open", order_type="market",
                   lots=2, price=None)
        fill = match_current_price(req, current_quote=70000.0,
                                    spec=spec_cu, order_id="o1")
        assert fill is not None
        assert fill.lots == 2
        assert fill.direction == "long"
        assert fill.offset == "open"
        # 含滑点(买入向上)
        assert fill.price > 70000.0
        # 手续费 > 0
        assert fill.commission > 0
        # 滑点金额 > 0
        assert fill.slippage > 0

    def test_limit_long_inside_range_fills(self, spec_cu):
        """限价买入:current ≤ limit 成交,按 limit 价成交"""
        req = _req(direction="long", offset="open", order_type="limit",
                   lots=1, price=71000.0)
        fill = match_current_price(req, current_quote=70000.0,
                                    spec=spec_cu, order_id="o2")
        assert fill is not None
        # 按限价成交(限价优于此 current)
        assert fill.price == pytest.approx(71000.0 * 1.0001)

    def test_limit_long_outside_range_returns_none(self, spec_cu):
        """限价买入:current > limit 不成交(挂单)"""
        req = _req(direction="long", offset="open", order_type="limit",
                   lots=1, price=70500.0)
        fill = match_current_price(req, current_quote=71000.0,
                                    spec=spec_cu, order_id="o3")
        assert fill is None

    def test_limit_short_inside_range_fills(self, spec_cu):
        """限价卖出:current ≥ limit 成交"""
        req = _req(direction="short", offset="open", order_type="limit",
                   lots=1, price=69500.0)
        fill = match_current_price(req, current_quote=70000.0,
                                    spec=spec_cu, order_id="o4")
        assert fill is not None
        # 按限价成交,卖下滑
        assert fill.price == pytest.approx(69500.0 * 0.9999)

    def test_limit_short_outside_range_returns_none(self, spec_cu):
        """限价卖出:current < limit 不成交"""
        req = _req(direction="short", offset="open", order_type="limit",
                   lots=1, price=70500.0)
        fill = match_current_price(req, current_quote=70000.0,
                                    spec=spec_cu, order_id="o5")
        assert fill is None

    def test_stop_returns_none(self, spec_cu):
        """stop 单不在 match_current_price 撮合"""
        req = SubmitOrderRequest(
            account_id="acc-1", full_symbol="CU2501.SHF",
            direction="long", offset="open", order_type="stop",
            lots=1, price=None, stop_price=69000.0,
        )
        fill = match_current_price(req, current_quote=70000.0,
                                    spec=spec_cu, order_id="o6")
        assert fill is None

    def test_stop_limit_returns_none(self, spec_cu):
        """stop_limit 单不在 match_current_price 撮合"""
        req = SubmitOrderRequest(
            account_id="acc-1", full_symbol="CU2501.SHF",
            direction="long", offset="open", order_type="stop_limit",
            lots=1, price=69500.0, stop_price=69000.0,
        )
        fill = match_current_price(req, current_quote=70000.0,
                                    spec=spec_cu, order_id="o7")
        assert fill is None

    def test_zero_quote_returns_none(self, spec_cu):
        """current_quote=0 不撮合(防御)"""
        req = _req(direction="long", offset="open", order_type="market",
                   lots=1, price=None)
        assert match_current_price(req, 0.0, spec_cu, "o8") is None


# =============================================================================
# Test 4 — TestTriggerHelpers
# =============================================================================

class TestTriggerHelpers:
    def test_long_stop_loss_triggered(self):
        """多仓止损:价格下行触及止损价 → True"""
        assert is_stop_triggered("long", 69000.0, 68500.0, is_long=True) is True

    def test_long_stop_loss_not_triggered(self):
        """多仓止损:价格未到止损价 → False"""
        assert is_stop_triggered("long", 69000.0, 70000.0, is_long=True) is False

    def test_short_stop_loss_triggered(self):
        """空仓止损:价格上行触及止损价 → True"""
        assert is_stop_triggered("short", 71000.0, 71500.0, is_long=False) is True

    def test_long_take_profit_triggered(self):
        """多仓止盈:价格上行触及止盈价 → True"""
        assert is_take_profit_triggered(72000.0, 72500.0, is_long=True) is True

    def test_short_take_profit_triggered(self):
        """空仓止盈:价格下行触及止盈价 → True"""
        assert is_take_profit_triggered(68000.0, 67500.0, is_long=False) is True


# =============================================================================
# Test 5 — TestConfigSnapshot
# =============================================================================

class TestConfigSnapshot:
    def test_config_keys(self):
        cfg = get_slippage_config()
        assert "matching_mode" in cfg
        assert "slippage_bps" in cfg
        assert "max_lots_per_order" in cfg
        assert "max_position_per_symbol" in cfg
        assert cfg["slippage_bps"] == pytest.approx(PAPER_SLIPPAGE_BPS)
        assert cfg["max_lots_per_order"] == PAPER_MAX_LOTS_PER_ORDER
        assert cfg["max_position_per_symbol"] == PAPER_MAX_POSITION_PER_SYMBOL
