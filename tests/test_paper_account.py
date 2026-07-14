"""
tests/test_paper_account.py — account.py 单测

覆盖:
- TestApplyFillToPosition
  * Case 1:新建持仓(pos is None)
  * Case 1b:新建持仓覆盖原 pos.lots=0
  * Case 2:同向加仓(加权平均成本)
  * Case 3:反向开仓(部分平旧开新)
  * Case 3b:反向完全平旧(不剩)
  * Case 3c:反向完全开新(平 0 手,全开新)
  * Case 4:平仓(部分)
  * Case 4b:平仓(全部)— return None
  * 边界:fill.lots <= 0 抛错
  * 防御:无 pos 但 offset=close → 忽略返回 (None, 0)
- TestComputePositionMargin
- TestRecalculateAccount
  * 基本账户:无持仓 → 仅 equity=balance,risk_ratio=0
  * 单持仓:浮动 PnL / margin / equity
  * 多持仓:聚合
  * 净值耗尽:equity<=0 → risk_ratio=999
  * 缺价 / 缺 spec:跳过(防御)
- TestAccountSnapshotDict

目标:≥18 测试全过。
"""
from __future__ import annotations

from datetime import datetime

import pytest

from tradingagents.paper.account import (
    AccountMetrics,
    apply_fill_to_position,
    compute_position_margin,
    recalculate_account,
    to_account_snapshot,
)
from tradingagents.paper.spec import get_spec
from tradingagents.paper.types import (
    Fill,
    PaperAccount,
    Position,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def spec_cu():
    return get_spec("CU", "SHFE")


@pytest.fixture
def spec_rb():
    return get_spec("RB", "SHFE")


def _make_fill(full_symbol: str, direction: str, offset: str, lots: int, price: float) -> Fill:
    return Fill(
        order_id="test-order-1",
        account_id="acc-1",
        full_symbol=full_symbol,
        direction=direction,           # type: ignore[arg-type]
        offset=offset,                 # type: ignore[arg-type]
        lots=lots,
        price=price,
        commission=35.0,
        slippage=0.0,
        matched_at=datetime(2026, 7, 14, 10, 0, 0),
    )


# =============================================================================
# Test 1 — TestApplyFillToPosition
# =============================================================================

class TestApplyFillToPosition:
    def test_open_new_position_from_none(self, spec_cu):
        """Case 1:pos is None,open → 新建持仓"""
        fill = _make_fill("CU2501.SHF", "long", "open", 5, 70000.0)
        new_pos, realized = apply_fill_to_position(None, fill, spec_cu)
        assert new_pos is not None
        assert new_pos.lots == 5
        assert new_pos.avg_cost == 70000.0
        assert new_pos.direction == "long"
        assert realized == 0.0

    def test_open_new_from_zero_lots_position(self, spec_cu):
        """Case 1b:原 pos.lots=0(已平仓残留),open 新方向 → 新建"""
        zero_pos = Position(
            full_symbol="CU2501.SHF", direction="long", lots=0, avg_cost=0.0
        )
        fill = _make_fill("CU2501.SHF", "short", "open", 3, 70500.0)
        new_pos, realized = apply_fill_to_position(zero_pos, fill, spec_cu)
        assert new_pos.lots == 3
        assert new_pos.direction == "short"
        assert new_pos.avg_cost == 70500.0

    def test_same_direction_add_to_position(self, spec_cu):
        """Case 2:同向加仓 → 加权平均"""
        pos = Position(
            full_symbol="CU2501.SHF", direction="long", lots=5, avg_cost=70000.0
        )
        fill = _make_fill("CU2501.SHF", "long", "open", 5, 71000.0)
        new_pos, realized = apply_fill_to_position(pos, fill, spec_cu)
        assert new_pos.lots == 10
        # (70000*5 + 71000*5) / 10 = 70500
        assert new_pos.avg_cost == pytest.approx(70500.0)
        assert realized == 0.0

    def test_reverse_open_partial_close(self, spec_cu):
        """Case 3:反向开仓(短空覆盖原 2 手多)
        平 2 手多 @ 71000 vs avg 70000: (1000) × 2 × 5 × 1 = +10000
        """
        pos = Position(
            full_symbol="CU2501.SHF", direction="long", lots=2, avg_cost=70000.0
        )
        fill = _make_fill("CU2501.SHF", "short", "open", 5, 71000.0)
        new_pos, realized = apply_fill_to_position(pos, fill, spec_cu)
        # close_amount=min(5,2)=2; reverse_open_amount=5-2=3
        # realized = (71000-70000) × 2 × 5 × 1 = +10000
        assert realized == pytest.approx(10000.0)
        assert new_pos.lots == 3
        assert new_pos.direction == "short"
        assert new_pos.avg_cost == 71000.0

    def test_reverse_open_full_close_remainder(self, spec_cu):
        """Case 3b:fill.lots == pos.lots,完全平仓不剩"""
        pos = Position(
            full_symbol="CU2501.SHF", direction="long", lots=2, avg_cost=70000.0
        )
        fill = _make_fill("CU2501.SHF", "short", "open", 2, 71000.0)
        new_pos, realized = apply_fill_to_position(pos, fill, spec_cu)
        assert new_pos is None
        assert realized == pytest.approx(10000.0)

    def test_reverse_open_no_close(self, spec_rb):
        """Case 3c:反向开仓,fill.lots > pos.lots → 平完旧仓再开剩余
        平 2 手多 @ 3900 vs avg 4000: (-100) × 2 × 10 × 1 = -2000(亏损,多仓下跌)
        """
        pos = Position(
            full_symbol="RB2501.SHF", direction="long", lots=2, avg_cost=4000.0
        )
        fill = _make_fill("RB2501.SHF", "short", "open", 5, 3900.0)
        new_pos, realized = apply_fill_to_position(pos, fill, spec_rb)
        # close 2 手多 (多仓亏损): (3900-4000) × 2 × 10 × +1 = -2000
        assert realized == pytest.approx(-2000.0)
        # reverse_open = 5-2=3 手新空
        assert new_pos.lots == 3
        assert new_pos.direction == "short"
        assert new_pos.avg_cost == 3900.0

    def test_close_partial(self, spec_cu):
        """Case 4:平仓部分手数"""
        pos = Position(
            full_symbol="CU2501.SHF", direction="long", lots=5, avg_cost=70000.0
        )
        fill = _make_fill("CU2501.SHF", "long", "close", 2, 71000.0)
        new_pos, realized = apply_fill_to_position(pos, fill, spec_cu)
        # 2 手平多: (71000-70000) × 2 × 5 × 1 = +10000
        assert realized == pytest.approx(10000.0)
        assert new_pos.lots == 3  # 5-2

    def test_close_full_returns_none(self, spec_cu):
        """Case 4b:全部平仓 → return (None, realized)
        平 5 手多 @ 71000 vs avg 70000: (1000) × 5 × 5 × 1 = +25000
        """
        pos = Position(
            full_symbol="CU2501.SHF", direction="long", lots=5, avg_cost=70000.0
        )
        fill = _make_fill("CU2501.SHF", "long", "close", 5, 71000.0)
        new_pos, realized = apply_fill_to_position(pos, fill, spec_cu)
        assert new_pos is None
        assert realized == pytest.approx(25000.0)

    def test_close_more_than_position_lots(self, spec_cu):
        """平仓量超过持仓,只平现有手数"""
        pos = Position(
            full_symbol="CU2501.SHF", direction="long", lots=2, avg_cost=70000.0
        )
        fill = _make_fill("CU2501.SHF", "long", "close", 5, 71000.0)
        new_pos, realized = apply_fill_to_position(pos, fill, spec_cu)
        assert new_pos is None
        # 只平 2 手: (71000-70000) × 2 × 5 = +10000
        assert realized == pytest.approx(10000.0)

    def test_close_with_no_position_returns_zero(self, spec_cu):
        """无 pos 但 close 指令 → 防御性忽略,返回 (None, 0)"""
        fill = _make_fill("CU2501.SHF", "long", "close", 1, 71000.0)
        new_pos, realized = apply_fill_to_position(None, fill, spec_cu)
        assert new_pos is None
        assert realized == 0.0

    def test_invalid_fill_lots_raises(self, spec_cu):
        fill = _make_fill("CU2501.SHF", "long", "open", 0, 70000.0)
        pos = Position(
            full_symbol="CU2501.SHF", direction="long", lots=5, avg_cost=70000.0
        )
        with pytest.raises(ValueError):
            apply_fill_to_position(pos, fill, spec_cu)


# =============================================================================
# Test 2 — TestComputePositionMargin
# =============================================================================

class TestComputePositionMargin:
    def test_long_5lots_cu_at_70000(self, spec_cu):
        """CU 5手 × 70000 × 5(合同) × 0.10 = 175000"""
        pos = Position(
            full_symbol="CU2501.SHF", direction="long", lots=5,
            avg_cost=70000.0, current_price=70000.0,
        )
        assert compute_position_margin(pos, 70000.0, spec_cu) == pytest.approx(175000.0)

    def test_zero_lots_returns_zero(self, spec_cu):
        pos = Position(
            full_symbol="CU2501.SHF", direction="long", lots=0,
            avg_cost=70000.0, current_price=70000.0,
        )
        assert compute_position_margin(pos, 70000.0, spec_cu) == 0.0


# =============================================================================
# Test 3 — TestRecalculateAccount
# =============================================================================

class TestRecalculateAccount:
    def test_no_positions_baseline(self):
        """无持仓:equity=balance, available=balance-frozen, risk_ratio=0"""
        account = PaperAccount(id="acc-1", balance=1000000.0, frozen=50000.0)
        m = recalculate_account(account, [], {}, {})
        assert m.unrealized_pnl == 0.0
        assert m.margin_used == 0.0
        assert m.equity == 1000000.0
        assert m.available == 950000.0
        assert m.risk_ratio == 0.0

    def test_single_position_with_profit(self, spec_cu):
        """单持仓 + 浮盈 → equity 上升"""
        account = PaperAccount(id="acc-1", balance=500000.0)
        pos = Position(
            full_symbol="CU2501.SHF", direction="long", lots=10,
            avg_cost=70000.0, current_price=71000.0,
        )
        m = recalculate_account(
            account, [pos],
            specs_by_symbol={"CU2501.SHF": spec_cu},
            current_prices={"CU2501.SHF": 71000.0},
        )
        # unrealized = (1000) × 10 × 5 × 1 = +50000
        assert m.unrealized_pnl == pytest.approx(50000.0)
        # margin = 10 × 71000 × 5 × 0.10 = 355000
        assert m.margin_used == pytest.approx(355000.0)
        # equity = 500000 + 50000 = 550000
        assert m.equity == pytest.approx(550000.0)
        # available = 550000 - 355000 - 0 = 195000
        assert m.available == pytest.approx(195000.0)
        # risk = 355000 / 550000 ≈ 0.6455
        assert m.risk_ratio == pytest.approx(355000.0 / 550000.0)

    def test_aggregate_two_positions(self, spec_cu, spec_rb):
        """聚合两持仓"""
        account = PaperAccount(id="acc-1", balance=1000000.0)
        pos1 = Position(
            full_symbol="CU2501.SHF", direction="long", lots=2,
            avg_cost=70000.0, current_price=71000.0,
        )
        pos2 = Position(
            full_symbol="RB2501.SHF", direction="short", lots=5,
            avg_cost=4000.0, current_price=3900.0,
        )
        m = recalculate_account(
            account, [pos1, pos2],
            specs_by_symbol={"CU2501.SHF": spec_cu, "RB2501.SHF": spec_rb},
            current_prices={"CU2501.SHF": 71000.0, "RB2501.SHF": 3900.0},
        )
        # unrealized CU: 1000 × 2 × 5 × 1 = 10000
        # unrealized RB: (-100) × 5 × 10 × -1 = 5000
        assert m.unrealized_pnl == pytest.approx(15000.0)
        # margin CU: 2 × 71000 × 5 × 0.10 = 71000
        # margin RB: 5 × 3900 × 10 × 0.11 = 21450
        assert m.margin_used == pytest.approx(92450.0)
        assert m.equity == pytest.approx(1015000.0)

    def test_zero_equity_returns_999_risk(self):
        """净值耗尽 → risk_ratio 视为无穷大(强平信号)"""
        account = PaperAccount(id="acc-1", balance=-5000.0)  # 已穿仓
        m = recalculate_account(account, [], {}, {})
        assert m.equity == -5000.0
        assert m.risk_ratio == 999.0

    def test_missing_spec_skips_position(self, spec_cu):
        """持仓对应 spec 缺失 → 防御性跳过"""
        account = PaperAccount(id="acc-1", balance=100000.0)
        pos = Position(
            full_symbol="UNKNOWN.SHF", direction="long", lots=10,
            avg_cost=100.0, current_price=110.0,
        )
        m = recalculate_account(
            account, [pos], specs_by_symbol={}, current_prices={}
        )
        assert m.unrealized_pnl == 0.0
        assert m.margin_used == 0.0

    def test_missing_price_skips_margin(self, spec_cu):
        """无当前价 → 不计算 margin(避免按陈旧价扣保证金)"""
        account = PaperAccount(id="acc-1", balance=100000.0)
        pos = Position(
            full_symbol="CU2501.SHF", direction="long", lots=10,
            avg_cost=70000.0, current_price=0.0,
        )
        m = recalculate_account(
            account, [pos],
            specs_by_symbol={"CU2501.SHF": spec_cu},
            current_prices={},
        )
        # 价格 0 ≤ 0 触发跳过
        assert m.margin_used == 0.0
        assert m.unrealized_pnl == 0.0


# =============================================================================
# Test 4 — TestAccountSnapshotDict
# =============================================================================

class TestAccountSnapshotDict:
    def test_snapshot_keys_present(self, spec_cu):
        """snapshot dict 包含前端需要的所有字段"""
        account = PaperAccount(id="acc-1", balance=500000.0)
        pos = Position(
            full_symbol="CU2501.SHF", direction="long", lots=2,
            avg_cost=70000.0, current_price=70000.0,
        )
        snap = to_account_snapshot(
            account, [pos],
            specs_by_symbol={"CU2501.SHF": spec_cu},
            current_prices={"CU2501.SHF": 70000.0},
        )
        for key in (
            "id", "balance", "margin_used", "frozen", "realized_pnl",
            "unrealized_pnl", "equity", "available", "risk_ratio",
            "positions_count", "total_long_lots", "total_short_lots",
        ):
            assert key in snap
        assert snap["id"] == "acc-1"
        assert snap["positions_count"] == 1
        assert snap["total_long_lots"] == 2
        assert snap["total_short_lots"] == 0

    def test_snapshot_breaks_even(self):
        """初始账户(无持仓)→ 各派生值都是 0"""
        account = PaperAccount(id="acc-empty", balance=100000.0)
        snap = to_account_snapshot(account, [], {}, {})
        assert snap["equity"] == 100000.0
        assert snap["available"] == 100000.0
        assert snap["risk_ratio"] == 0.0
        assert snap["positions_count"] == 0

    def test_account_metrics_is_frozen(self):
        """AccountMetrics 是 frozen dataclass,不可变"""
        m = AccountMetrics(
            unrealized_pnl=0.0,
            margin_used=0.0,
            equity=100.0,
            available=100.0,
            risk_ratio=0.0,
            realized_pnl=0.0,
        )
        from dataclasses import FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            m.equity = 0.0  # type: ignore[misc]
