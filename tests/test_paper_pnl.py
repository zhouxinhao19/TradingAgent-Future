"""
tests/test_paper_pnl.py — PnL 计算模块单测

覆盖:
- TestCalcFloatingPnl     浮动 PnL 多空方向 / 价差 / 手数 / 零持仓边界
- TestMarkPositionToMarket dataclass 不可变性 / 字段更新
- TestAggregateFloatingPnl 多持仓聚合 / 缺失报价 / spec 缺失
- TestCalcRealizedPnl     已实现 PnL 平仓 / 零手数
- TestCalcCommission      单边 / 双边 / 不同品种
- TestHelpers             calc_return_pct / round_trip_pnl / round_trip_commission

目标:≥14 测试全过。
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from tradingagents.paper.pnl import (
    calc_floating_pnl,
    calc_realized_pnl,
    aggregate_floating_pnl,
    mark_position_to_market,
    calc_commission_for_fill,
    calc_round_trip_pnl,
    calc_round_trip_commission,
    calc_return_pct,
)
from tradingagents.paper.spec import get_spec
from tradingagents.paper.types import Position


# =============================================================================
# Test 1 — TestCalcFloatingPnl
# =============================================================================

class TestCalcFloatingPnl:
    def test_long_profit(self):
        """多仓价格上涨 1000 元/吨 × 5 手 × 5 吨 = +25000"""
        spec = get_spec("CU", "SHFE")
        pos = Position(
            full_symbol="CU2501.SHF",
            direction="long",
            lots=5,
            avg_cost=70000.0,
        )
        assert calc_floating_pnl(pos, 71000.0, spec) == pytest.approx(25000.0)

    def test_long_loss(self):
        """多仓价格下跌 500 元/吨 × 10 手 × 10 吨 = -50000"""
        spec = get_spec("RB", "SHFE")  # contract_size=10
        pos = Position(
            full_symbol="RB2501.SHF",
            direction="long",
            lots=10,
            avg_cost=4000.0,
        )
        assert calc_floating_pnl(pos, 3500.0, spec) == pytest.approx(-50000.0)

    def test_short_profit_when_price_drops(self):
        """空仓价格下跌盈利:8500 → 8000 = +500/桶 × 1 手 × 1000 桶 = +500000"""
        spec = get_spec("SC", "INE")
        pos = Position(
            full_symbol="SC2506.INE",
            direction="short",
            lots=1,
            avg_cost=8500.0,
        )
        # 空头盈利 = (price - avg) × lots × cs × (-1) = (8000-8500) × 1 × 1000 × -1 = 500000
        assert calc_floating_pnl(pos, 8000.0, spec) == pytest.approx(500000.0)

    def test_short_loss_when_price_rises(self):
        """空仓价格上涨亏损"""
        spec = get_spec("IF", "CFFEX")  # contract_size=300
        pos = Position(
            full_symbol="IF2503.CFX",
            direction="short",
            lots=1,
            avg_cost=3800.0,
        )
        # (3900-3800) × 1 × 300 × (-1) = -30000
        assert calc_floating_pnl(pos, 3900.0, spec) == pytest.approx(-30000.0)

    def test_zero_lots_returns_zero(self):
        """已平仓持仓返回 0,不会因为 avg_cost 残留导致错误 PnL"""
        spec = get_spec("CU", "SHFE")
        pos = Position(
            full_symbol="CU2501.SHF",
            direction="long",
            lots=0,
            avg_cost=70000.0,
        )
        assert calc_floating_pnl(pos, 80000.0, spec) == 0.0

    def test_break_even_at_avg_cost(self):
        """当前价等于均价 → PnL = 0"""
        spec = get_spec("RB", "SHFE")
        pos = Position(
            full_symbol="RB2501.SHF",
            direction="long",
            lots=5,
            avg_cost=4000.0,
        )
        assert calc_floating_pnl(pos, 4000.0, spec) == 0.0


# =============================================================================
# Test 2 — TestMarkPositionToMarket
# =============================================================================

class TestMarkPositionToMarket:
    def test_returns_new_position(self):
        """返回新 Position,原对象不修改"""
        spec = get_spec("CU", "SHFE")
        pos = Position(
            full_symbol="CU2501.SHF",
            direction="long",
            lots=2,
            avg_cost=70000.0,
            current_price=0.0,
            floating_pnl=0.0,
        )
        marked = mark_position_to_market(pos, 71500.0, spec)
        # 原对象不变
        assert pos.current_price == 0.0
        assert pos.floating_pnl == 0.0
        # 新对象更新
        assert marked.current_price == 71500.0
        # (71500 - 70000) × 2 × 5 × 1 = +15000
        assert marked.floating_pnl == pytest.approx(15000.0)

    def test_zero_lots_does_not_change_pnl(self):
        spec = get_spec("CU", "SHFE")
        pos = Position(
            full_symbol="CU2501.SHF",
            direction="long",
            lots=0,
            avg_cost=70000.0,
            current_price=0.0,
            floating_pnl=0.0,
        )
        marked = mark_position_to_market(pos, 99999.0, spec)
        assert marked.current_price == 99999.0
        assert marked.floating_pnl == 0.0  # 因为 lots=0


# =============================================================================
# Test 3 — TestAggregateFloatingPnl
# =============================================================================

class TestAggregateFloatingPnl:
    def test_aggregate_two_positions(self):
        """CU + RB 两个持仓聚合浮动 PnL"""
        spec_cu = get_spec("CU", "SHFE")
        spec_rb = get_spec("RB", "SHFE")
        pos1 = Position(
            full_symbol="CU2501.SHF", direction="long",
            lots=3, avg_cost=70000.0, current_price=71000.0,
        )
        pos2 = Position(
            full_symbol="RB2501.SHF", direction="short",
            lots=5, avg_cost=4000.0, current_price=3900.0,
        )
        total = aggregate_floating_pnl(
            [pos1, pos2],
            spec_for={"CU2501.SHF": spec_cu, "RB2501.SHF": spec_rb},
            current_prices={"CU2501.SHF": 71000.0, "RB2501.SHF": 3900.0},
        )
        # CU: (1000) × 3 × 5 × 1 = +15000
        # RB: (-100) × 5 × 10 × -1 = +5000
        # 总计 +20000
        assert total == pytest.approx(20000.0)

    def test_empty_positions_returns_zero(self):
        spec_cu = get_spec("CU", "SHFE")
        total = aggregate_floating_pnl(
            [], spec_for={"CU2501.SHF": spec_cu}, current_prices={}
        )
        assert total == 0.0

    def test_missing_spec_skipped(self):
        """持仓对应的 spec 缺失 → 跳过(不抛错)"""
        pos = Position(
            full_symbol="UNKNOWN.SHF", direction="long",
            lots=1, avg_cost=100.0, current_price=200.0,
        )
        total = aggregate_floating_pnl([pos], spec_for={}, current_prices={})
        assert total == 0.0

    def test_missing_price_uses_position_current_price(self):
        """current_prices 缺失 → 用持仓自身的 current_price"""
        spec_cu = get_spec("CU", "SHFE")
        pos = Position(
            full_symbol="CU2501.SHF", direction="long",
            lots=1, avg_cost=70000.0, current_price=71500.0,
        )
        total = aggregate_floating_pnl(
            [pos], spec_for={"CU2501.SHF": spec_cu}, current_prices={}
        )
        # (71500-70000) × 1 × 5 × 1 = +7500
        assert total == pytest.approx(7500.0)


# =============================================================================
# Test 4 — TestCalcRealizedPnl
# =============================================================================

class TestCalcRealizedPnl:
    def test_long_close_profit(self):
        """多仓 70000 → 71000 平仓 × 5 手 × 5 吨 = +25000"""
        spec = get_spec("CU", "SHFE")
        assert calc_realized_pnl(70000.0, 71000.0, 5, "long", spec) == pytest.approx(25000.0)

    def test_short_close_profit(self):
        """空仓 4000 → 3900 平仓 × 10 手 × 10 吨 × (-1) = +10000

        数学验算:(3900-4000) × 10 × 10 × (-1) = -100 × 100 × -1 = +10000
        """
        spec = get_spec("RB", "SHFE")
        assert calc_realized_pnl(4000.0, 3900.0, 10, "short", spec) == pytest.approx(10000.0)

    def test_zero_lots_returns_zero(self):
        spec = get_spec("CU", "SHFE")
        assert calc_realized_pnl(70000.0, 80000.0, 0, "long", spec) == 0.0

    def test_break_even_zero_pnl(self):
        spec = get_spec("CU", "SHFE")
        assert calc_realized_pnl(70000.0, 70000.0, 5, "long", spec) == 0.0

    def test_round_trip_alias(self):
        """calc_round_trip_pnl 与 calc_realized_pnl 等价"""
        spec = get_spec("CU", "SHFE")
        pnl1 = calc_realized_pnl(70000.0, 71000.0, 1, "long", spec)
        pnl2 = calc_round_trip_pnl(70000.0, 71000.0, 1, "long", spec)
        assert pnl1 == pnl2


# =============================================================================
# Test 5 — TestCalcCommission
# =============================================================================

class TestCalcCommission:
    def test_single_side_cu(self):
        spec = get_spec("CU", "SHFE")
        # 1 × 70000 × 5 × 0.0001 = 35
        assert calc_commission_for_fill(1, 70000.0, spec) == pytest.approx(35.0)

    def test_round_trip_double(self):
        spec = get_spec("CU", "SHFE")
        assert calc_round_trip_commission(1, 70000.0, spec) == pytest.approx(70.0)

    def test_au_gold_low_rate(self):
        """AU 单边手续费极低:1 × 500 × 1000 × 0.00002 = 10 元"""
        spec = get_spec("AU", "SHFE")
        assert calc_commission_for_fill(1, 500.0, spec) == pytest.approx(10.0)


# =============================================================================
# Test 6 — TestHelpers
# =============================================================================

class TestHelpers:
    def test_return_pct_positive(self):
        """100000 初始,盈利 5000 = 5%"""
        assert calc_return_pct(5000.0, 100000.0) == pytest.approx(0.05)

    def test_return_pct_negative(self):
        assert calc_return_pct(-2000.0, 100000.0) == pytest.approx(-0.02)

    def test_return_pct_zero_initial(self):
        """初始资金为 0 防御性返回 0(避免除零)"""
        assert calc_return_pct(100.0, 0.0) == 0.0

    def test_return_pct_negative_initial(self):
        assert calc_return_pct(100.0, -50.0) == 0.0
