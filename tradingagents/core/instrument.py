"""
标的抽象(Instrument)
为大宗商品提供统一的代码识别与元数据抽象
Phase 5 已清理,仅保留商品路径

设计原则:
- 工厂方法 `Instrument.of(code)` 自动识别标的类型
- 失败时抛 ValueError,避免 silent failure
- 提供 to_dict() 供 AgentState 注入
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional

from tradingagents.utils.logging_init import get_logger
from tradingagents.utils.commodity_utils import CommodityMarket, CommodityUtils

logger = get_logger("default")


# 资产类型常量
ASSET_TYPE_COMMODITY = "commodity"
ASSET_TYPE_UNKNOWN = "unknown"


@dataclass
class Instrument:
    """统一标的抽象(大宗商品)"""

    code: str
    asset_type: str                          # commodity
    market: str                              # 枚举值字符串(便于 JSON 序列化)
    market_name: str = ""
    category: str = ""                       # 股票:industry / 商品:metal/energy/...
    currency: str = "CNY"                    # CNY / HKD / USD
    unit: str = "手"                         # 商品才有意义
    contract_size: float = 1.0               # 1手合约规模
    data_source: str = "unknown"             # 推荐数据源标识
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典,供 AgentState 注入或 MongoDB 存储"""
        d = asdict(self)
        return d

    @staticmethod
    def of(code: str) -> "Instrument":
        """
        工厂方法:自动识别标的类型(仅商品)

        Args:
            code: 商品代码 (CU2501.SHF / CL=F / AU9999.SGE)

        Returns:
            Instrument 实例

        Raises:
            ValueError: 无法识别的代码
        """
        if not code:
            raise ValueError("Instrument.of: 标的代码不能为空")

        code = str(code).strip()
        if not code:
            raise ValueError("Instrument.of: 标的代码不能为空")

        # 尝试商品识别
        commodity_market = CommodityUtils.identify_market(code)
        if commodity_market != CommodityMarket.UNKNOWN:
            info = CommodityUtils.get_market_info(code)
            return Instrument(
                code=code.upper(),
                asset_type=ASSET_TYPE_COMMODITY,
                market=info["market"],
                market_name=info["market_name"],
                category=info["category"],
                currency=info["currency"],
                unit=info["unit"],
                contract_size=info["contract_size"],
                data_source="akshare_futures" if info["is_china_futures"] else "yfinance_futures",
                extra={
                    "underlying": info["underlying"],
                    "is_china_futures": info["is_china_futures"],
                    "is_international": info["is_international"],
                    "is_spot_cn": info["is_spot_cn"],
                },
            )

        raise ValueError(f"Instrument.of: 无法识别标的代码: {code!r}")

    @staticmethod
    def try_of(code: str) -> Optional["Instrument"]:
        """
        工厂方法:不抛异常的版本,识别失败返回 None
        适合不确定输入是否合法时使用
        """
        try:
            return Instrument.of(code)
        except ValueError:
            return None

    @property
    def is_commodity(self) -> bool:
        return self.asset_type == ASSET_TYPE_COMMODITY
