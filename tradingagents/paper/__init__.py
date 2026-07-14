"""
tradingagents.paper — 大宗商品模拟交易(撮合 / 持仓 / PnL / 风控)子包

设计目标:
- 提供纯函数计算层(spec / pnl / matcher / risk),零 LLM 依赖
- 从 commodity_metadata 读取合约规格(82 品种 / 6 交易所)
- 与 app/routers/commodity/paper_rules.py 协作组成"决策 → 下单 → 撮合 → 盯市 → 风控"闭环

模块划分:
- spec.py        合约规格:ContractSpec 数据类 + 保证金/手续费/涨跌停计算
- pnl.py         浮动 / 已实现 PnL 计算
- account.py     账户聚合:余额 / 可用 / 占用 / 净值 / 风险度
- matcher.py     撮合引擎:市价 / 限价 / 止损单
- risk.py        风控:止损止盈触发 / 保证金追缴 / 强平
- repo.py        MongoDB 读写封装(4 集合)

Phase 4 起步仅交付 spec.py,其余模块后续 commit 跟进。
"""
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

__all__ = [
    "ContractSpec",
    "calc_margin",
    "calc_commission",
    "check_price_limit",
    "parse_variety",
    "get_spec",
    "list_supported_symbols",
    "VARIETY_SPEC_INDEX",
]
