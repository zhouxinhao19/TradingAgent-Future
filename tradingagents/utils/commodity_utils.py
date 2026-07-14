"""
大宗商品工具函数
提供大宗商品代码识别、分类和处理功能
与 stock_utils.py 对称设计,便于 Phase 5 清理时整体替换
"""

import re
from typing import Dict, Tuple, Optional
from enum import Enum

# 导入统一日志系统
from tradingagents.utils.logging_init import get_logger
logger = get_logger("default")


class CommodityMarket(Enum):
    """大宗商品市场枚举"""
    CHINA_FUTURES = "china_futures"   # 国内期货:SHFE/DCE/CZCE/INE/GFEX
    INTERNATIONAL = "international"   # 国际期货:CME/NYMEX/COMEX/LME/ICE
    SPOT_CN = "spot_cn"               # 国内现货:SGE
    UNKNOWN = "unknown"               # 未知


# 国内期货交易所后缀(包含中金所期货:股指/国债)
_CHINA_FUTURES_EXCHANGES = ("SHF", "DCE", "CZC", "INE", "GFEX", "CFFEX")

# 国际期货:Yahoo Finance 主力连续合约代码(常见品种)
_INTERNATIONAL_FUTURES_PREFIX = {
    "CL",   # WTI 原油
    "GC",   # 黄金
    "SI",   # 白银
    "HG",   # 铜
    "PL",   # 铂金
    "PA",   # 钯金
    "NG",   # 天然气
    "RB",   # 汽油
    "HO",   # 燃油
    "ZC",   # 玉米
    "ZW",   # 小麦
    "ZS",   # 大豆
    "ZM",   # 豆粕
    "ZL",   # 豆油
    "ZR",   # 稻谷
    "ZO",   # 燕麦
    "KC",   # 咖啡
    "CT",   # 棉花
    "SB",   # 白糖
    "CC",   # 可可
    "OJ",   # 橙汁
    "LE",   # 活牛
    "GF",   # 活牛饲料
    "HE",   # 瘦猪
}

# 品种代码 → 品类
# 参考 AKShare 期货品种分类
_COMMODITY_CATEGORY = {
    # 贵金属
    "AU": "precious", "AG": "precious", "PT": "precious", "PD": "precious",
    "GC": "precious", "SI": "precious", "PL": "precious", "PA": "precious",
    # 有色金属
    "CU": "metal", "AL": "metal", "ZN": "metal", "PB": "metal", "NI": "metal",
    "SN": "metal", "SS": "metal", "BC": "metal", "AO": "metal", "BR": "metal",
    "HG": "metal",  # 国际铜
    # 黑色金属
    "RB": "metal", "WR": "metal", "HC": "metal", "I": "metal", "J": "metal",
    "JM": "metal", "SS": "metal", "SF": "metal", "SM": "metal",
    # 能源化工
    "SC": "energy", "FU": "energy", "LU": "energy", "PG": "energy", "BU": "energy",
    "RU": "chemical", "NR": "chemical", "BR": "chemical", "EB": "chemical",
    "EG": "chemical", "EGS": "chemical", "TA": "chemical", "MA": "chemical",
    "L": "chemical", "V": "chemical", "PP": "chemical", "PE": "chemical",
    "PVC": "chemical", "SA": "chemical", "UR": "chemical", "FG": "chemical",
    "CL": "energy", "NG": "energy", "HO": "energy", "RB": "energy",
    # 农产品 - 油脂油料
    "Y": "agricultural", "P": "agricultural", "OI": "agricultural", "M": "agricultural",
    "RM": "agricultural", "A": "agricultural", "B": "agricultural",
    "ZS": "agricultural", "ZM": "agricultural", "ZL": "agricultural", "ZC": "agricultural",
    "ZW": "agricultural", "ZR": "agricultural", "ZO": "agricultural",
    # 农产品 - 软商品
    "SR": "agricultural", "CF": "agricultural", "CY": "agricultural", "AP": "agricultural",
    "CJ": "agricultural", "PK": "agricultural", "KC": "agricultural", "CT": "agricultural",
    "SB": "agricultural", "CC": "agricultural", "OJ": "agricultural",
    # 农产品 - 畜牧
    "JD": "agricultural", "LH": "agricultural", "LE": "agricultural", "GF": "agricultural",
    "HE": "agricultural",
    # 金融
    "TF": "financial", "T": "financial", "TS": "financial", "TL": "financial",
    "IF": "financial", "IH": "financial", "IC": "financial", "IM": "financial",
}

# 品种代码 → 计量单位
_COMMODITY_UNIT = {
    "CU": ("吨", 5), "AL": ("吨", 5), "ZN": ("吨", 5), "PB": ("吨", 5),
    "NI": ("吨", 1), "SN": ("吨", 1), "SS": ("吨", 5),
    "AU": ("克", 1000), "AG": ("千克", 15),
    "SC": ("桶", 1000), "FU": ("吨", 10), "RU": ("吨", 10),
    "CL": ("桶", 1000), "GC": ("盎司", 100),
    "Y": ("吨", 10), "P": ("吨", 10), "M": ("吨", 10),
    "SR": ("吨", 10), "CF": ("吨", 5),
    "I": ("吨", 100), "RB": ("吨", 10), "HC": ("吨", 10),
    "A": ("吨", 10), "B": ("吨", 10), "C": ("吨", 10), "CS": ("吨", 10),
}


class CommodityUtils:
    """大宗商品工具类(与 StockUtils 镜像)"""

    @staticmethod
    def identify_market(code: str) -> CommodityMarket:
        """
        识别大宗商品代码所属市场

        Args:
            code: 商品代码,如 CU2501.SHF / CL=F / AU9999.SGE

        Returns:
            CommodityMarket: 商品市场类型
        """
        if not code:
            return CommodityMarket.UNKNOWN

        code = str(code).strip().upper()

        # 国内期货: <SYMBOL><YYMM>.<EXCHANGE>
        # 大部分合约是 4 位数字(YEAR2+MONTH2),CZCE 部分品种采用 3 位(YEAR1+MONTH2)
        for exch in _CHINA_FUTURES_EXCHANGES:
            # 标准 4 位数字
            if re.match(rf'^[A-Z]{{1,3}}\d{{4}}\.{exch}$', code):
                return CommodityMarket.CHINA_FUTURES
        # CZCE 兼容 3 位数字(YYM):如 AP410 / CF401 / SR409
        if re.match(r'^[A-Z]{1,3}\d{3}\.(CZC|CZCE)$', code):
            return CommodityMarket.CHINA_FUTURES

        # 现货: <SYMBOL><NNNN>.<EXCHANGE> 4位数字 (SGE 上海黄金交易所)
        if re.match(r'^[A-Z]{1,3}\d{4}\.SGE$', code):
            return CommodityMarket.SPOT_CN

        # 国际期货: =F 主力连续 (CL=F / GC=F 等)
        if re.match(r'^[A-Z]{1,3}=F$', code):
            prefix = code.split('=')[0]
            if prefix in _INTERNATIONAL_FUTURES_PREFIX:
                return CommodityMarket.INTERNATIONAL

        # LME 伦敦金属交易所: <SYMBOL>.LME
        if re.match(r'^[A-Z]{2,3}\.LME$', code):
            return CommodityMarket.INTERNATIONAL

        return CommodityMarket.UNKNOWN

    @staticmethod
    def is_china_futures(code: str) -> bool:
        """判断是否为国内期货"""
        return CommodityUtils.identify_market(code) == CommodityMarket.CHINA_FUTURES

    @staticmethod
    def is_international_futures(code: str) -> bool:
        """判断是否为国际期货"""
        return CommodityUtils.identify_market(code) == CommodityMarket.INTERNATIONAL

    @staticmethod
    def is_spot_cn(code: str) -> bool:
        """判断是否为国内现货"""
        return CommodityUtils.identify_market(code) == CommodityMarket.SPOT_CN

    @staticmethod
    def get_underlying_symbol(code: str) -> Optional[str]:
        """
        提取标的物代码(去掉年月和交易所后缀)
        例: CU2501.SHF → CU; CL=F → CL
        """
        if not code:
            return None
        code = str(code).strip().upper()
        m = re.match(r'^([A-Z]{1,3})', code)
        return m.group(1) if m else None

    @staticmethod
    def get_category(code: str) -> str:
        """
        返回商品品类
        取值: precious / metal / energy / chemical / agricultural / financial / unknown
        """
        underlying = CommodityUtils.get_underlying_symbol(code)
        if not underlying:
            return "unknown"
        return _COMMODITY_CATEGORY.get(underlying, "unknown")

    @staticmethod
    def get_currency(code: str) -> str:
        """
        根据商品代码获取货币代码
        返回: CNY / USD
        """
        market = CommodityUtils.identify_market(code)
        if market in (CommodityMarket.CHINA_FUTURES, CommodityMarket.SPOT_CN):
            return "CNY"
        if market == CommodityMarket.INTERNATIONAL:
            return "USD"
        return "UNKNOWN"

    @staticmethod
    def get_unit(code: str) -> Tuple[str, float]:
        """
        返回(单位, 1手合约规模)
        例: 沪铜 → (吨, 5)
        """
        underlying = CommodityUtils.get_underlying_symbol(code)
        if not underlying:
            return ("手", 1.0)
        return _COMMODITY_UNIT.get(underlying, ("手", 1.0))

    @staticmethod
    def get_market_info(code: str) -> Dict:
        """
        获取商品市场详细信息(与 StockUtils.get_market_info 对称)
        """
        market = CommodityUtils.identify_market(code)
        category = CommodityUtils.get_category(code)
        currency = CommodityUtils.get_currency(code)
        unit, contract_size = CommodityUtils.get_unit(code)

        market_names = {
            CommodityMarket.CHINA_FUTURES: "国内期货",
            CommodityMarket.INTERNATIONAL: "国际期货",
            CommodityMarket.SPOT_CN: "国内现货",
            CommodityMarket.UNKNOWN: "未知市场",
        }

        return {
            "code": code,
            "market": market.value,
            "market_name": market_names[market],
            "category": category,
            "currency": currency,
            "unit": unit,
            "contract_size": contract_size,
            "underlying": CommodityUtils.get_underlying_symbol(code),
            "is_china_futures": market == CommodityMarket.CHINA_FUTURES,
            "is_international": market == CommodityMarket.INTERNATIONAL,
            "is_spot_cn": market == CommodityMarket.SPOT_CN,
        }


# 便捷函数,保持向后兼容
def is_china_futures(code: str) -> bool:
    """判断是否为国内期货"""
    return CommodityUtils.is_china_futures(code)


def is_international_futures(code: str) -> bool:
    """判断是否为国际期货"""
    return CommodityUtils.is_international_futures(code)


def get_commodity_market_info(code: str) -> Dict:
    """获取商品市场信息"""
    return CommodityUtils.get_market_info(code)
