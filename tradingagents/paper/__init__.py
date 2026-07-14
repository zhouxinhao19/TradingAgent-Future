"""
tradingagents.paper — 大宗商品模拟交易(撮合 / 持仓 / PnL / 风控)子包

设计目标:
- 提供纯函数计算层(spec / pnl / matcher / risk),零 LLM 依赖
- 从 commodity_metadata 读取合约规格(82 品种 / 6 交易所)
- 与 app/routers/commodity/paper_rules.py 协作组成"决策 → 下单 → 撮合 → 盯市 → 风控"闭环

模块划分:
- types.py       共享 dataclass(Position / PaperAccount / SubmitOrderRequest / Fill / OrderResult)
- spec.py        合约规格:ContractSpec 数据类 + 保证金/手续费/涨跌停计算
- pnl.py         浮动 / 已实现 PnL 计算
- account.py     账户聚合:余额 / 可用 / 占用 / 净值 / 风险度 + 持仓更新
- matcher.py     撮合引擎预检 + 滑点 + 当前价撮合(纯逻辑,MongoDB 编排待补)
- risk.py        风控:止损止盈触发 / 保证金追缴 / 强平 — 待第三刀
- repo.py        MongoDB 读写封装(4 集合)— 待第三刀

Phase 4 现状(spec + 第二刀已交):
- spec.py / types.py / pnl.py / account.py / matcher.py 全部纯逻辑层
- 测试覆盖 96 个,全部 0 失败
"""
from .types import (
    Direction,
    OffsetFlag,
    OrderType,
    OrderStatus,
    RejectReason,
    Position,
    PaperAccount,
    SubmitOrderRequest,
    Fill,
    OrderResult,
    lots_to_units,
    units_to_lots,
)
from .spec import (
    ContractSpec,
    calc_margin,
    calc_commission,
    check_price_limit,
    parse_variety,
    get_spec,
    list_supported_symbols,
    VARIETY_SPEC_INDEX,
)
from .pnl import (
    calc_floating_pnl,
    mark_position_to_market,
    aggregate_floating_pnl,
    calc_realized_pnl,
    calc_round_trip_pnl,
    calc_commission_for_fill,
    calc_round_trip_commission,
    calc_return_pct,
)
from .account import (
    AccountMetrics,
    compute_position_margin,
    apply_fill_to_position,
    recalculate_account,
    aggregate_account_metrics,
    to_account_snapshot,
)
from .matcher import (
    PAPER_MATCHING_MODE,
    PAPER_SLIPPAGE_BPS,
    PAPER_MAX_LOTS_PER_ORDER,
    PAPER_MAX_POSITION_PER_SYMBOL,
    get_slippage_config,
    apply_slippage,
    pre_check_order,
    match_current_price,
    is_stop_triggered,
    is_take_profit_triggered,
)

__all__ = [
    # types
    "Direction", "OffsetFlag", "OrderType", "OrderStatus", "RejectReason",
    "Position", "PaperAccount", "SubmitOrderRequest", "Fill", "OrderResult",
    "lots_to_units", "units_to_lots",
    # spec
    "ContractSpec", "calc_margin", "calc_commission", "check_price_limit",
    "parse_variety", "get_spec", "list_supported_symbols", "VARIETY_SPEC_INDEX",
    # pnl
    "calc_floating_pnl", "mark_position_to_market", "aggregate_floating_pnl",
    "calc_realized_pnl", "calc_round_trip_pnl", "calc_commission_for_fill",
    "calc_round_trip_commission", "calc_return_pct",
    # account
    "AccountMetrics", "compute_position_margin", "apply_fill_to_position",
    "recalculate_account", "aggregate_account_metrics", "to_account_snapshot",
    # matcher
    "PAPER_MATCHING_MODE", "PAPER_SLIPPAGE_BPS",
    "PAPER_MAX_LOTS_PER_ORDER", "PAPER_MAX_POSITION_PER_SYMBOL",
    "get_slippage_config",
    "apply_slippage", "pre_check_order", "match_current_price",
    "is_stop_triggered", "is_take_profit_triggered",
]
