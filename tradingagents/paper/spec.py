"""
合约规格(`tradingagents/paper/spec.py`)

提供:
- ContractSpec(frozen dataclass): 单品种合约规格,所有计算函数的入参
- calc_margin / calc_commission / check_price_limit: 三个核心计算
- parse_variety(full_symbol): 从 "CU2501.SHF" / "RB2501.DCE" 等解析 (variety_code, exchange)
- VARIETY_SPEC_INDEX: 全品种索引(82 品种 / 6 交易所)

设计原则:
- 纯函数、零外部依赖(只依赖 commodity_metadata)
- frozen dataclass 保证运行时不可变
- 所有数值字段从 commodity_metadata 静态加载,运行时不再调外部接口

落地依据:
- 参考项目 `期货TradingAgents系统_交易员.py:188` 的 multiplier 语义,
  我们直接复用 contract_size(1 手对应实物数量)
- 保证金率 / 手续费率 / 涨跌停板见 commodity_metadata.margin_rate 等
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from tradingagents.dataflows.providers.commodity.commodity_metadata import (
    _ALL_VARIETIES,
    get_trading_hours,
    get_variety,
    normalize_exchange_code,
)


# =============================================================================
# ContractSpec — 单品种合约规格(不可变)
# =============================================================================

@dataclass(frozen=True)
class ContractSpec:
    """单品种合约规格,字段对齐 commodity_metadata + 3 个 Phase 4 字段。

    字段取值:
    - variety_code / symbol: 品种代码(CU / RB / IF 等)
    - name_cn: 中文名("铜")
    - exchange: 交易所代码(SHFE / DCE / CZCE / INE / GFEX / CFFEX)
    - contract_size: 1 手对应实物数量(等价于 multiplier)
    - tick_size: 最小变动价位
    - margin_rate: 保证金率(0~1,期货公司常规标准,2024-07 公告)
    - commission_rate: 手续费率(单边单次,实际开+平合计按 2×)
    - limit_up_down: 涨跌停板宽度(普通交易日非扩板期)
    - unit: 计量单位("吨" / "克" / "桶" 等)
    - category: 品类(metal / precious / energy / chemical / agricultural / financial)
    - list_date: 标准合约首次上市日("1999-06-18")
    - trading_hours_raw: 交易时段原始字符串元组
        (call_auction, day_session, night_session),缺失夜盘时第三个为 None
    """
    variety_code: str
    symbol: str
    name_cn: str
    exchange: str
    contract_size: int
    tick_size: float
    margin_rate: float
    commission_rate: float
    limit_up_down: float
    unit: str
    category: str
    list_date: str
    trading_hours_raw: Tuple[Optional[str], Optional[str], Optional[str]] = field(
        default_factory=lambda: (None, None, None)
    )

    @classmethod
    def from_metadata(cls, item: dict) -> "ContractSpec":
        """从 commodity_metadata 的 dict 构造 ContractSpec。

        Args:
            item: 含 variety_code/symbol/name_cn/exchange/contract_size/tick_size/
                  margin_rate/commission_rate/limit_up_down_pct/unit/category/list_date
                  字段的 dict(由 get_variety() / list_variities() 返回)

        Returns:
            ContractSpec 实例。trading_hours_raw 字段从 get_trading_hours() 拉取,
            拉不到则为 (None, None, None)。
        """
        hours = get_trading_hours(item["variety_code"], item["exchange"]) or {}
        return cls(
            variety_code=item["variety_code"],
            symbol=item["symbol"],
            name_cn=item["name_cn"],
            exchange=item["exchange"],
            contract_size=item["contract_size"],
            tick_size=item["tick_size"],
            margin_rate=item["margin_rate"],
            commission_rate=item["commission_rate"],
            limit_up_down=item["limit_up_down_pct"],
            unit=item["unit"],
            category=item["category"],
            list_date=item["list_date"],
            trading_hours_raw=(
                hours.get("call_auction"),
                hours.get("day_session"),
                hours.get("night_session"),
            ),
        )

    @classmethod
    def from_variety(
        cls, variety_code: str, exchange: Optional[str] = None
    ) -> "ContractSpec":
        """根据品种代码(+ 可选交易所)查询并构造 ContractSpec。

        Args:
            variety_code: 品种代码(CU / RB / IF 等,大小写不敏感)
            exchange: 可选交易所代码(SHFE / DCE 等,大小写不敏感),
                      不传时按 _VARIETY_INDEX_BY_SYMBOL 唯一命中(可能撞符号)

        Raises:
            KeyError: 未知品种 / 品种与交易所不匹配
        """
        item = get_variety(variety_code, exchange)
        if not item:
            raise KeyError(
                f"ContractSpec.from_variety: 未知品种 "
                f"{variety_code!r} (exchange={exchange!r})"
            )
        return cls.from_metadata(item)

    # =========================================================================
    # 派生属性
    # =========================================================================

    @property
    def exchange_suffix(self) -> str:
        """合约后缀(交易所缩写,如 'SHF' / 'DCE' / 'ZCE' / 'GFEX')"""
        suffix_map = {
            "SHFE": "SHF",
            "DCE": "DCE",
            "CZCE": "ZCE",
            "INE": "INE",
            "GFEX": "GFEX",
            "CFFEX": "CFX",
        }
        return suffix_map.get(self.exchange, self.exchange[:4])


# =============================================================================
# 静态索引 — 启动时构建,82 品种全覆盖
# =============================================================================

# key = (exchange, symbol),便于精确查询国际铜等仅在 INE 的品种
# key = symbol,模糊匹配(可能撞符号如 FU/AL 等只在 SHFE 故简化为 symbol)
VARIETY_SPEC_INDEX: Dict[Tuple[str, str], ContractSpec] = {}
_SPEC_BY_EXCHANGE_SYMBOL: Dict[Tuple[str, str], ContractSpec] = {}


def _build_spec_index() -> None:
    """从 _ALL_VARIETIES 构建 VARIETY_SPEC_INDEX。模块导入时自动调用。"""
    for item in _ALL_VARIETIES:
        spec = ContractSpec.from_metadata(item)
        VARIETY_SPEC_INDEX[(item["exchange"], item["symbol"])] = spec
        _SPEC_BY_EXCHANGE_SYMBOL[(item["exchange"], item["symbol"])] = spec


# 模块导入即构建(零 IO,只是 dataclass 实例化)
_build_spec_index()


def get_spec(symbol: str, exchange: Optional[str] = None) -> ContractSpec:
    """查询 ContractSpec(优先按 (exchange, symbol) 精确查,无 exchange 时按 symbol 唯一查)。

    Args:
        symbol: 品种代码(CU / RB 等,大小写不敏感)
        exchange: 可选交易所(SHFE / DCE 等)

    Returns:
        ContractSpec

    Raises:
        KeyError: 找不到品种(symbol 在多交易所冲突时也抛错)
    """
    sym_upper = symbol.upper() if symbol else ""
    ex_upper = exchange.upper() if exchange else ""

    if ex_upper:
        spec = _SPEC_BY_EXCHANGE_SYMBOL.get((ex_upper, sym_upper))
        if spec:
            return spec
        raise KeyError(
            f"get_spec: 找不到品种 {sym_upper}.{ex_upper}"
        )

    # 不传 exchange,遍历整个索引找唯一命中的 symbol
    matches = [
        s for (ex, sym), s in _SPEC_BY_EXCHANGE_SYMBOL.items()
        if sym == sym_upper
    ]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise KeyError(f"get_spec: 未知品种 {sym_upper!r}")
    symbols_in = sorted({(s.exchange, s.symbol) for s in matches})
    raise KeyError(
        f"get_spec: {sym_upper!r} 命中多个交易所 {symbols_in},请显式传 exchange"
    )


def list_supported_symbols() -> Dict[str, int]:
    """列出全部支持品种,按交易所分组计数(调试 / 健康检查用)。"""
    by_exchange: Dict[str, int] = {}
    for (exchange, _symbol), _spec in _SPEC_BY_EXCHANGE_SYMBOL.items():
        by_exchange[exchange] = by_exchange.get(exchange, 0) + 1
    return dict(sorted(by_exchange.items()))


# =============================================================================
# 品种代码解析 — 从 "CU2501.SHF" 解析出 ("CU", "SHFE")
# =============================================================================

# 匹配:<VARIETY_LETTERS><YYMM><DOT><EXCHANGE_SUFFIX>
# 品种代码 1-3 个大写字母,合约年月 4 位数字,CZCE 部分品种采用 3 位(已弃用对月)
_FULL_SYMBOL_PATTERN = re.compile(
    r"^(?P<variety>[A-Z]{1,3})(?P<yymm>\d{4})\.(?P<suffix>[A-Z]+)$"
)


def parse_variety(full_symbol: str) -> Tuple[str, str]:
    """从合约代码解析 (variety_code, exchange)。

    支持的输入格式:
    - 'CU2501.SHF'         → ('CU', 'SHFE')
    - 'RB2505.DCE'         → ('RB', 'DCE')
    - 'AP410.ZCE'          → ('AP', 'CZCE')  兼容 CZCE 三位数字(YYM)
    - 'IF2503.CFX'         → ('IF', 'CFFEX')

    Args:
        full_symbol: 完整合约代码

    Returns:
        (variety_code, exchange_canonical) 二元组,其中 exchange 已归一化
        为标准 4~5 字母代码(SHFE / DCE / CZCE / INE / GFEX / CFFEX)

    Raises:
        ValueError: 输入格式不合法 / 交易所后缀无法识别 / 品种代码不在元数据中
    """
    if not full_symbol or not isinstance(full_symbol, str):
        raise ValueError(f"parse_variety: full_symbol 必须是字符串,实际={full_symbol!r}")

    full_symbol = full_symbol.strip().upper()

    # 尝试标准 4 位数字格式
    m = _FULL_SYMBOL_PATTERN.match(full_symbol)
    if not m:
        # CZCE 兼容 3 位数字(YYM,历史惯例)
        m = re.match(r"^(?P<variety>[A-Z]{1,3})(?P<yymm>\d{3})\.(?P<suffix>[A-Z]+)$",
                     full_symbol)
        if not m:
            raise ValueError(
                f"parse_variety: 无法解析合约代码 {full_symbol!r} "
                f"(期望格式如 'CU2501.SHF')"
            )

    variety = m.group("variety")
    suffix = m.group("suffix")

    exchange = normalize_exchange_code(suffix)
    if not exchange:
        raise ValueError(
            f"parse_variety: 无法识别交易所后缀 {suffix!r} "
            f"in {full_symbol!r}"
        )

    return variety, exchange


# =============================================================================
# 核心计算函数
# =============================================================================

def calc_margin(lots: int, price: float, spec: ContractSpec) -> float:
    """占用保证金 = lots × price × contract_size × margin_rate。

    Args:
        lots: 委托手数(>= 1)
        price: 价格(单价位,元 / 吨 或 元 / 克 等)
        spec: 合约规格

    Returns:
        占用保证金金额(元,人民币)

    Raises:
        ValueError: lots <= 0
    """
    if lots <= 0:
        raise ValueError(f"calc_margin: lots 必须 > 0,实际={lots}")
    if price < 0:
        raise ValueError(f"calc_margin: price 不能为负,实际={price}")
    return float(lots) * float(price) * spec.contract_size * spec.margin_rate


def calc_commission(lots: int, price: float, spec: ContractSpec) -> float:
    """手续费 = lots × price × contract_size × commission_rate(单边单次)。

    实际总手续费 = 2× 此值(开仓 + 平仓各算一次)。

    Args:
        lots: 委托手数
        price: 价格
        spec: 合约规格

    Returns:
        单边手续费金额(元)
    """
    if lots <= 0:
        raise ValueError(f"calc_commission: lots 必须 > 0,实际={lots}")
    if price < 0:
        raise ValueError(f"calc_commission: price 不能为负,实际={price}")
    return float(lots) * float(price) * spec.contract_size * spec.commission_rate


def check_price_limit(
    price: float,
    prev_settlement: float,
    spec: ContractSpec,
    extended: bool = False,
) -> bool:
    """涨跌停预检。

    Args:
        price: 委托价格
        prev_settlement: 昨结算价(0 表示无限,视为无涨跌停)
        spec: 合约规格
        extended: 是否扩板日(扩板 = 上界额外 +50%)

    Returns:
        True 表示价格在涨跌停区间内可成交;False 表示超限应拒单。

    Notes:
        - prev_settlement <= 0 时视为无涨跌停(刚上市 / 暂停后重启)
        - 扩展日上限 = prev_settlement × (1 + limit × 1.5)
        - 计算统一基于昨结算,不用昨收盘(交易所规则)
    """
    if prev_settlement <= 0:
        return True
    if price < 0:
        return False
    multiplier = 1.5 if extended else 1.0
    upper = prev_settlement * (1 + spec.limit_up_down * multiplier)
    lower = prev_settlement * (1 - spec.limit_up_down * multiplier)
    return lower <= price <= upper


def calc_upper_limit(
    prev_settlement: float,
    spec: ContractSpec,
    extended: bool = False,
) -> float:
    """计算涨跌停上界(便于前端展示 / 订单预填)。"""
    if prev_settlement <= 0:
        return float("inf")
    multiplier = 1.5 if extended else 1.0
    return prev_settlement * (1 + spec.limit_up_down * multiplier)


def calc_lower_limit(
    prev_settlement: float,
    spec: ContractSpec,
    extended: bool = False,
) -> float:
    """计算涨跌停下界。"""
    if prev_settlement <= 0:
        return 0.0
    multiplier = 1.5 if extended else 1.0
    return max(0.0, prev_settlement * (1 - spec.limit_up_down * multiplier))
