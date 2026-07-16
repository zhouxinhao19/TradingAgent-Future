"""
大宗商品静态元数据(基于 AKShare 期货接口文档 2024-11-18 快照)

提供国内 6 大期货交易所全品种基础信息:
- 交易所字典(代码 / 后缀 / 中文名 / 官网)
- 品种字典(品种代码 / 中文名 / 英文名 / 上市日期 / 基础参数)
- 合约乘数 / 最小变动价位(标准合约)
- 保证金率 / 手续费率 / 涨跌停板(Phase 4 paper trading 引入)
- 交易时间(参考交易所文档,实际以交易日历为准)

数据来源:
- AKShare 期货基础信息文档(本目录 ak share 期货数据 .txt)
- 各交易所官方合约规格
- 期货公司 2024-07 保证金率标准公示 + 3% 浮动

设计原则:
- 纯静态,无外部依赖
- 与 commodity_utils 中的分类表互为补充
- 字段命名遵循 snake_case,方便转 Pydantic
"""
from typing import Dict, List, Optional, Tuple

# =============================================================================
# 交易所字典
# =============================================================================

# 参考表: 交易所 -> (代码, 合约后缀, 中文名, 官网)
EXCHANGES: Dict[str, Dict] = {
    "CFFEX": {
        "code": "CFFEX",
        "mic": "CCFX",
        "suffix": ".CFX",
        "name_cn": "中国金融期货交易所",
        "name_short": "中金所",
        "homepage": "http://www.cffex.com.cn",
        "abbreviation_akshare": "cffex",
    },
    "SHFE": {
        "code": "SHFE",
        "mic": "XSHG",
        "suffix": ".SHF",
        "name_cn": "上海期货交易所",
        "name_short": "上期所",
        "homepage": "https://www.shfe.com.cn",
        "abbreviation_akshare": "shfe",
    },
    "INE": {
        "code": "INE",
        "mic": "XINE",
        "suffix": ".INE",
        "name_cn": "上海国际能源交易中心",
        "name_short": "上期能源",
        "homepage": "https://www.ine.cn",
        "abbreviation_akshare": "ine",
    },
    "DCE": {
        "code": "DCE",
        "mic": "XDCE",
        "suffix": ".DCE",
        "name_cn": "大连商品交易所",
        "name_short": "大商所",
        "homepage": "http://www.dce.com.cn",
        "abbreviation_akshare": "dce",
    },
    "CZCE": {
        "code": "CZCE",
        "mic": "XZCE",
        "suffix": ".ZCE",
        "name_cn": "郑州商品交易所",
        "name_short": "郑商所",
        "homepage": "http://www.czce.com.cn",
        "abbreviation_akshare": "czce",
    },
    "GFEX": {
        "code": "GFEX",
        "mic": "XGFX",
        "suffix": ".GFEX",
        "name_cn": "广州期货交易所",
        "name_short": "广期所",
        "homepage": "http://www.gfex.com.cn",
        "abbreviation_akshare": "gfex",
    },
}


def get_exchange(code: str) -> Optional[Dict]:
    """根据交易所代码获取交易所信息,如 'SHFE' / 'CZCE'"""
    if not code:
        return None
    return EXCHANGES.get(code.upper())


def list_exchanges() -> List[Dict]:
    """列出所有交易所"""
    return list(EXCHANGES.values())


# =============================================================================
# 品种字典 — 各交易所品种表
# =============================================================================
# 字段(v1 → v2 扩展):每行元组长度从 9 → 12
#   variety_code        交易所用代码(大写)
#   symbol              新浪 / 通用代码
#   name_cn             中文名
#   abbrev              AKShare 接口命名(`shfe` / `dce` 等)
#   category            品类: precious / metal / energy / chemical / agricultural / financial
#   unit                计量单位: 吨 / 克 / 千克 / 桶 / 张 / 点 / 立方米
#   contract_size       1 手 = ? 单位(等价于一手对应实物数量,即 multiplier)
#   tick_size           最小变动价位
#   list_date           标准合约首次上市日, YYYY-MM-DD
#   margin_rate         保证金率(0~1,期货公司常规标准,2024-07 公告,
#                       含基础保证金 + 浮动 3%)
#   commission_rate     手续费率(双边计算 = lots × price × contract_size × rate,
#                       实际开仓+平仓各按 1× 计算,合计 2× 实际费率,
#                       此处为单边单次率)
#   limit_up_down_pct   涨跌停板宽度(普通交易日非扩板期,扩板日 +50% 即上表中 0.05 扩为 0.075)

_SHFE_VARIETIES = [
    # 金属 — 铜铝锌铅镍锡氧化铝
    ("CU", "CU", "铜", "shfe", "metal", "吨", 5, 10, "1999-06-18", 0.10, 0.0001, 0.06),
    ("AL", "AL", "铝", "shfe", "metal", "吨", 5, 5, "1999-08-04", 0.10, 0.0001, 0.06),
    ("ZN", "ZN", "锌", "shfe", "metal", "吨", 5, 5, "2007-03-26", 0.10, 0.0001, 0.06),
    ("PB", "PB", "铅", "shfe", "metal", "吨", 5, 5, "2011-03-24", 0.10, 0.0001, 0.06),
    ("NI", "NI", "镍", "shfe", "metal", "吨", 1, 10, "2015-03-27", 0.12, 0.0001, 0.06),
    ("SN", "SN", "锡", "shfe", "metal", "吨", 1, 10, "2015-03-27", 0.12, 0.0001, 0.06),
    ("AO", "AO", "氧化铝", "shfe", "metal", "吨", 20, 1, "2023-06-19", 0.11, 0.0001, 0.06),
    # 贵金属 — 金银(AKShare SHFE 也涵盖)
    ("AU", "AU", "黄金", "shfe", "precious", "克", 1000, 0.02, "2008-01-09", 0.08, 0.00002, 0.07),
    ("AG", "AG", "白银", "shfe", "precious", "千克", 15, 1, "2012-05-10", 0.09, 0.00005, 0.07),
    # 黑色 — 螺纹/线材/热卷/不锈钢
    ("RB", "RB", "螺纹钢", "shfe", "metal", "吨", 10, 1, "2009-03-27", 0.11, 0.0001, 0.05),
    ("WR", "WR", "线材", "shfe", "metal", "吨", 10, 1, "2009-03-27", 0.11, 0.0001, 0.05),
    ("HC", "HC", "热轧卷板", "shfe", "metal", "吨", 10, 1, "2014-03-21", 0.11, 0.0001, 0.05),
    ("SS", "SS", "不锈钢", "shfe", "metal", "吨", 5, 5, "2019-09-25", 0.11, 0.0001, 0.05),
    # 能化 — 沥青/橡胶/纸浆/燃料油/合成橡胶
    ("BU", "BU", "石油沥青", "shfe", "energy", "吨", 10, 1, "2013-10-09", 0.10, 0.0001, 0.06),
    ("RU", "RU", "天然橡胶", "shfe", "chemical", "吨", 10, 5, "1999-05-04", 0.10, 0.0001, 0.06),
    ("BR", "BR", "合成橡胶", "shfe", "chemical", "吨", 5, 5, "2023-07-28", 0.10, 0.0001, 0.06),
    ("SP", "SP", "纸浆", "shfe", "chemical", "吨", 10, 2, "2018-11-27", 0.10, 0.0001, 0.06),
    ("FU", "FU", "燃料油", "shfe", "energy", "吨", 10, 1, "2004-08-25", 0.10, 0.0001, 0.06),
]

_INE_VARIETIES = [
    # 国际能源 — 原油/20号胶/低硫燃料油/集运指数/国际铜
    ("SC", "SC", "原油", "ine", "energy", "桶", 1000, 0.1, "2018-03-26", 0.10, 0.00005, 0.08),
    ("NR", "NR", "20号胶", "ine", "chemical", "吨", 10, 5, "2019-08-12", 0.10, 0.0001, 0.07),
    ("LU", "LU", "低硫燃料油", "ine", "energy", "吨", 10, 1, "2020-06-22", 0.10, 0.0001, 0.07),
    ("EC", "EC", "集运指数(欧线)", "ine", "energy", "点", 50, 0.1, "2023-08-18", 0.15, 0.0001, 0.10),
    ("BC", "BC", "国际铜", "ine", "metal", "吨", 5, 10, "2020-11-19", 0.10, 0.0001, 0.06),
]

_DCE_VARIETIES = [
    # 农产品 — 豆一/豆二/玉米/玉米淀粉/豆粕/豆油/棕榈油
    ("A", "A", "黄大豆1号", "dce", "agricultural", "吨", 10, 1, "1999-01-18", 0.08, 0.0001, 0.05),
    ("B", "B", "黄大豆2号", "dce", "agricultural", "吨", 10, 1, "2004-12-22", 0.08, 0.0001, 0.05),
    ("C", "C", "黄玉米", "dce", "agricultural", "吨", 10, 1, "2004-09-22", 0.08, 0.0001, 0.05),
    ("CS", "CS", "玉米淀粉", "dce", "agricultural", "吨", 10, 1, "2014-12-19", 0.08, 0.0001, 0.05),
    ("M", "M", "豆粕", "dce", "agricultural", "吨", 10, 1, "2000-07-17", 0.08, 0.0001, 0.05),
    ("Y", "Y", "豆油", "dce", "agricultural", "吨", 10, 2, "2006-01-09", 0.08, 0.0001, 0.05),
    ("P", "P", "棕榈油", "dce", "agricultural", "吨", 10, 2, "2007-10-29", 0.10, 0.0001, 0.06),
    # 黑色 — 铁矿石/焦炭/焦煤
    ("I", "I", "铁矿石", "dce", "metal", "吨", 100, 0.5, "2013-10-18", 0.13, 0.0001, 0.06),
    ("J", "J", "焦炭", "dce", "metal", "吨", 100, 0.5, "2011-04-15", 0.13, 0.0001, 0.06),
    ("JM", "JM", "焦煤", "dce", "metal", "吨", 60, 0.5, "2013-03-22", 0.13, 0.0001, 0.06),
    # 化工 — 塑料/PVC/聚丙烯/乙二醇/苯乙烯/LPG
    ("L", "L", "聚乙烯", "dce", "chemical", "吨", 5, 1, "2007-07-31", 0.09, 0.0001, 0.05),
    ("V", "V", "聚氯乙烯(PVC)", "dce", "chemical", "吨", 5, 1, "2009-05-25", 0.09, 0.0001, 0.05),
    ("PP", "PP", "聚丙烯", "dce", "chemical", "吨", 5, 1, "2014-02-28", 0.09, 0.0001, 0.05),
    ("EG", "EG", "乙二醇", "dce", "chemical", "吨", 10, 1, "2018-12-10", 0.09, 0.0001, 0.05),
    ("EB", "EB", "苯乙烯", "dce", "chemical", "吨", 5, 1, "2019-09-26", 0.09, 0.0001, 0.05),
    ("PG", "PG", "液化石油气", "dce", "energy", "吨", 20, 1, "2020-03-30", 0.10, 0.0001, 0.06),
    # 农副 — 鸡蛋/粳米/纤维板/胶合板/生猪/原木
    ("JD", "JD", "鸡蛋", "dce", "agricultural", "吨", 10, 1, "2013-11-08", 0.09, 0.0001, 0.05),
    ("RR", "RR", "粳米", "dce", "agricultural", "吨", 10, 1, "2019-08-16", 0.08, 0.0001, 0.05),
    ("FB", "FB", "纤维板", "dce", "agricultural", "立方米", 10, 0.5, "2013-12-06", 0.10, 0.0001, 0.05),
    ("BB", "BB", "胶合板", "dce", "agricultural", "张", 500, 0.05, "2013-12-06", 0.10, 0.0001, 0.05),
    ("LH", "LH", "生猪", "dce", "agricultural", "吨", 16, 5, "2021-01-08", 0.12, 0.0002, 0.06),
    ("LG", "LG", "原木", "dce", "agricultural", "立方米", 60, 0.5, "2024-11-18", 0.11, 0.0001, 0.06),
]

_CZCE_VARIETIES = [
    # 农产品 — 棉花/白糖/棉纱/苹果/红枣/花生/菜粕/菜油/菜籽
    ("CF", "CF", "一号棉花", "czce", "agricultural", "吨", 5, 5, "2004-06-01", 0.09, 0.0001, 0.05),
    ("SR", "SR", "白砂糖", "czce", "agricultural", "吨", 10, 1, "2006-01-06", 0.08, 0.0001, 0.05),
    ("CY", "CY", "棉纱", "czce", "agricultural", "吨", 5, 5, "2017-08-18", 0.09, 0.0001, 0.05),
    ("AP", "AP", "苹果", "czce", "agricultural", "吨", 10, 1, "2017-12-22", 0.12, 0.0001, 0.06),
    ("CJ", "CJ", "红枣", "czce", "agricultural", "吨", 5, 5, "2019-04-30", 0.12, 0.0001, 0.06),
    ("PK", "PK", "花生", "czce", "agricultural", "吨", 5, 2, "2021-02-01", 0.10, 0.0001, 0.05),
    ("RM", "RM", "菜粕", "czce", "agricultural", "吨", 10, 1, "2012-12-28", 0.08, 0.0001, 0.05),
    ("OI", "OI", "菜籽油", "czce", "agricultural", "吨", 10, 1, "2013-05-16", 0.08, 0.0001, 0.05),
    ("RS", "RS", "菜籽", "czce", "agricultural", "吨", 10, 1, "2012-12-28", 0.08, 0.0001, 0.05),
    # 粮食 — 普麦/强麦/早籼/晚籼/粳稻
    ("PM", "PM", "普通小麦", "czce", "agricultural", "吨", 50, 1, "2012-01-17", 0.08, 0.0001, 0.05),
    ("WH", "WH", "强麦", "czce", "agricultural", "吨", 20, 1, "2013-05-24", 0.08, 0.0001, 0.05),
    ("RI", "RI", "早籼稻", "czce", "agricultural", "吨", 20, 1, "2013-05-24", 0.08, 0.0001, 0.05),
    ("LR", "LR", "晚籼稻", "czce", "agricultural", "吨", 20, 1, "2014-07-08", 0.08, 0.0001, 0.05),
    ("JR", "JR", "粳稻", "czce", "agricultural", "吨", 20, 1, "2013-11-18", 0.08, 0.0001, 0.05),
    # 能化 — PTA/甲醇/玻璃/纯碱/烧碱/尿素/短纤/对二甲苯/瓶片/动力煤/硅铁/锰硅
    ("TA", "TA", "精对苯二甲酸(PTA)", "czce", "chemical", "吨", 5, 2, "2006-12-18", 0.09, 0.0001, 0.05),
    ("MA", "MA", "甲醇", "czce", "chemical", "吨", 10, 1, "2015-05-18", 0.10, 0.0001, 0.06),
    ("FG", "FG", "玻璃", "czce", "chemical", "吨", 20, 1, "2012-12-03", 0.10, 0.0001, 0.06),
    ("SA", "SA", "纯碱", "czce", "chemical", "吨", 20, 1, "2019-12-06", 0.09, 0.0001, 0.06),
    ("SH", "SH", "烧碱", "czce", "chemical", "吨", 30, 1, "2023-09-15", 0.10, 0.0001, 0.06),
    ("UR", "UR", "尿素", "czce", "chemical", "吨", 20, 1, "2019-08-09", 0.08, 0.0001, 0.05),
    ("PF", "PF", "短纤", "czce", "chemical", "吨", 5, 2, "2020-10-12", 0.09, 0.0001, 0.06),
    ("PX", "PX", "对二甲苯", "czce", "chemical", "吨", 5, 2, "2023-09-15", 0.09, 0.0001, 0.06),
    ("PR", "PR", "瓶片", "czce", "chemical", "吨", 5, 2, "2024-08-30", 0.09, 0.0001, 0.06),
    ("ZC", "ZC", "动力煤", "czce", "energy", "吨", 100, 0.2, "2013-09-26", 0.10, 0.0001, 0.06),
    ("SF", "SF", "硅铁", "czce", "metal", "吨", 5, 2, "2014-08-08", 0.09, 0.0001, 0.06),
    ("SM", "SM", "锰硅", "czce", "metal", "吨", 5, 2, "2014-08-08", 0.09, 0.0001, 0.06),
]

_GFEX_VARIETIES = [
    ("SI", "SI", "工业硅", "gfex", "metal", "吨", 5, 5, "2022-12-22", 0.12, 0.0001, 0.07),
    ("LC", "LC", "碳酸锂", "gfex", "metal", "吨", 1, 50, "2023-07-21", 0.13, 0.0001, 0.08),
    ("PS", "PS", "多晶硅", "gfex", "metal", "吨", 1, 0.5, "2024-12-26", 0.13, 0.0001, 0.08),
]

_CFFEX_VARIETIES = [
    # 股指
    ("IF", "IF", "沪深300股指", "cffex", "financial", "点", 300, 0.2, "2010-04-16", 0.13, 0.000023, 0.10),
    ("IH", "IH", "上证50股指", "cffex", "financial", "点", 300, 0.2, "2015-04-16", 0.13, 0.000023, 0.10),
    ("IC", "IC", "中证500股指", "cffex", "financial", "点", 200, 0.2, "2015-04-16", 0.13, 0.000023, 0.10),
    ("IM", "IM", "中证1000股指", "cffex", "financial", "点", 200, 0.2, "2022-07-22", 0.13, 0.000023, 0.10),
    # 国债
    ("TS", "TS", "2年期国债", "cffex", "financial", "点", 20000, 0.005, "2017-02-27", 0.03, 0.00005, 0.02),
    ("TF", "TF", "5年期国债", "cffex", "financial", "点", 10000, 0.005, "2013-09-06", 0.03, 0.00005, 0.02),
    ("T", "T", "10年期国债", "cffex", "financial", "点", 10000, 0.005, "2015-03-20", 0.03, 0.00005, 0.02),
    ("TL", "TL", "30年期国债", "cffex", "financial", "点", 10000, 0.005, "2023-04-21", 0.04, 0.00005, 0.02),
]

# 汇总,合并所有交易所的品种
_ALL_VARIETIES: List[Dict] = []
_VARIETY_INDEX_BY_EXCHANGE_SYMBOL: Dict[Tuple[str, str], Dict] = {}
_VARIETY_INDEX_BY_SYMBOL: Dict[str, Dict] = {}

for _EX_VARIETIES in (
    _SHFE_VARIETIES, _INE_VARIETIES, _DCE_VARIETIES,
    _CZCE_VARIETIES, _GFEX_VARIETIES, _CFFEX_VARIETIES,
):
    for (variety_code, symbol, name_cn, abbrev, category,
         unit, contract_size, tick_size, list_date,
         margin_rate, commission_rate, limit_up_down_pct) in _EX_VARIETIES:
        # 由 abbreviation_akshare 直接推断交易所(最可靠)
        _ABBREV_TO_EXCHANGE = {
            "shfe": "SHFE",
            "ine": "INE",
            "dce": "DCE",
            "czce": "CZCE",
            "gfex": "GFEX",
            "cffex": "CFFEX",
        }
        exchange = _ABBREV_TO_EXCHANGE.get(abbrev, "SHFE")

        item = {
            "variety_code": variety_code,
            "symbol": symbol,
            "name_cn": name_cn,
            "abbreviation_akshare": abbrev,
            "category": category,
            "unit": unit,
            "contract_size": contract_size,
            "tick_size": tick_size,
            "list_date": list_date,
            "exchange": exchange,
            # Phase 4 扩展字段
            "margin_rate": margin_rate,
            "commission_rate": commission_rate,
            "limit_up_down_pct": limit_up_down_pct,
        }
        _ALL_VARIETIES.append(item)
        _VARIETY_INDEX_BY_EXCHANGE_SYMBOL[(exchange, symbol)] = item
        _VARIETY_INDEX_BY_SYMBOL.setdefault(symbol, item)


# =============================================================================
# 品种字典(公开)
# =============================================================================

def list_varieties(exchange: Optional[str] = None) -> List[Dict]:
    """
    列出所有品种/指定交易所的品种

    Args:
        exchange: 交易所代码,如 'SHFE' / 'DCE',空则返回全部
    """
    if not exchange:
        return list(_ALL_VARIETIES)
    exchange = exchange.upper()
    return [v for v in _ALL_VARIETIES if v["exchange"] == exchange]


def get_variety(symbol: str, exchange: Optional[str] = None) -> Optional[Dict]:
    """
    根据品种代码获取品种信息

    Args:
        symbol: 品种代码(大写),如 'CU' / 'RB' / 'IF'
        exchange: 交易所代码(可选,部分代码如 BC 国际铜只在 INE,可能与其他交易所符号重叠)
    """
    if not symbol:
        return None
    symbol = symbol.upper()
    if exchange:
        return _VARIETY_INDEX_BY_EXCHANGE_SYMBOL.get((exchange.upper(), symbol))
    return _VARIETY_INDEX_BY_SYMBOL.get(symbol)


def get_variety_by_exchange(exchange: str, symbol: str) -> Optional[Dict]:
    """根据交易所 + 品种代码获取品种信息(精确匹配,如国际铜只在 INE)"""
    if not exchange or not symbol:
        return None
    return _VARIETY_INDEX_BY_EXCHANGE_SYMBOL.get((exchange.upper(), symbol.upper()))


def resolve_variety_to_symbol(variety: str) -> Optional[Dict[str, str]]:
    """品种代码 → 合约代码 + 元信息。

    Args:
        variety: 品种代码,如 "RB" / "CU" / "SC"

    Returns:
        {
            "full_symbol": "RB.SHF",        # 不带 YYMM,触发 provider 主力连续路径
            "variety_name": "螺纹钢",
            "exchange": "SHFE",
            "category": "metal",
            "quote_unit": "元/吨",
        }
        或 None(品种未找到)
    """
    if not variety:
        return None
    variety_info = get_variety(variety.upper())
    if not variety_info:
        return None
    exchange_code = variety_info["exchange"]
    exch_info = EXCHANGES.get(exchange_code)
    if not exch_info:
        return None
    suffix = exch_info.get("suffix", f".{exchange_code}")
    unit = variety_info.get("unit", "吨")
    return {
        "full_symbol": f"{variety.upper()}{suffix}",
        "variety_name": variety_info.get("name_cn", variety.upper()),
        "exchange": exchange_code,
        "category": variety_info.get("category", ""),
        "quote_unit": f"{unit}/手",
    }


# =============================================================================
# 主力连续合约代码(新浪),与 AKShare 一致
# =============================================================================

# 各品种的主力连续合约代码(AKShare / 新浪约定)
MAIN_CONTINUOUS_SYMBOLS: Dict[str, str] = {
    # DCE
    "V": "V0", "P": "P0", "B": "B0", "M": "M0", "I": "I0",
    "JD": "JD0", "L": "L0", "PP": "PP0", "FB": "FB0", "BB": "BB0",
    "Y": "Y0", "C": "C0", "A": "A0", "J": "J0", "JM": "JM0",
    "CS": "CS0", "EG": "EG0", "RR": "RR0", "EB": "EB0", "LH": "LH0",
    # CZCE
    "TA": "TA0", "OI": "OI0", "RS": "RS0", "RM": "RM0",
    "ZC": "ZC0", "WH": "WH0", "JR": "JR0", "SR": "SR0",
    "CF": "CF0", "RI": "RI0", "MA": "MA0", "FG": "FG0",
    "LR": "LR0", "SF": "SF0", "SM": "SM0", "CY": "CY0",
    "AP": "AP0", "CJ": "CJ0", "UR": "UR0", "SA": "SA0",
    "PF": "PF0", "PK": "PK0",
    # SHFE
    "FU": "FU0", "AL": "AL0", "RU": "RU0", "ZN": "ZN0",
    "CU": "CU0", "AU": "AU0", "RB": "RB0", "WR": "WR0",
    "PB": "PB0", "AG": "AG0", "BU": "BU0", "HC": "HC0",
    "SN": "SN0", "NI": "NI0", "SP": "SP0", "SS": "SS0",
    # INE
    "NR": "NR0", "LU": "LU0", "BC": "BC0", "SC": "SC0",
    # CFFEX
    "IF": "IF0", "TF": "TF0", "IH": "IH0",
    "IC": "IC0", "TS": "TS0",
}


def get_main_continuous_symbol(symbol: str) -> Optional[str]:
    """获取主力连续合约代码(AKShare / 新浪格式),不存在返回 None"""
    if not symbol:
        return None
    return MAIN_CONTINUOUS_SYMBOLS.get(symbol.upper())


# =============================================================================
# 指数连续合约代码(99 结尾, AKShare 约定)
# =============================================================================

# 各品种的指数连续合约代码(AKShare 约定: 代码以 99 结尾)
# 指数连续合约 = 当前品种全部可交易合约以累计持仓量为权重加权平均得到
# 目前仅 CFFEX 金融期货有标准 99 代码; 商品期货 AKShare 支持有限
INDEX_SYMBOLS: Dict[str, str] = {
    # CFFEX 金融期货
    "IF": "IF99",
    "IH": "IH99",
    "IC": "IC99",
    "IM": "IM99",
    "TF": "TF99",
    "T": "T99",
    "TS": "TS99",
}


def get_index_symbol(underlying: str) -> Optional[str]:
    """获取品种的指数连续合约代码(AKShare 99 格式)。

    Args:
        underlying: 品种代码, 如 "IF" / "CU"

    Returns:
        指数连续合约代码, 如 "IF99"; 不存在返回 None
    """
    if not underlying:
        return None
    return INDEX_SYMBOLS.get(underlying.upper())


# =============================================================================
# 交易时间(参考 AKShare 交易时间表 2024-11-18 快照)
# =============================================================================
# 字段:
#   exchange: 交易所代码
#   variety_code: 品种代码
#   call_auction: 集合竞价时段
#   day_session: 日盘交易时段
#   night_session: 夜盘交易时段
#   has_night_session: 是否有夜盘

_TRADING_HOURS: Dict[Tuple[str, str], Dict] = {
    # 上期所 SHFE
    ("SHFE", "RB"): {"call_auction": "20:55-21:00, 08:55-09:00",
                    "day_session": "09:00-10:15, 10:30-11:30, 13:30-15:00",
                    "night_session": "21:00-23:00"},
    ("SHFE", "HC"): {"call_auction": "20:55-21:00, 08:55-09:00",
                    "day_session": "09:00-10:15, 10:30-11:30, 13:30-15:00",
                    "night_session": "21:00-23:00"},
    ("SHFE", "CU"): {"call_auction": "20:55-21:00, 08:55-09:00",
                    "day_session": "09:00-10:15, 10:30-11:30, 13:30-15:00",
                    "night_session": "21:00-01:00"},
    ("SHFE", "AL"): {"call_auction": "20:55-21:00, 08:55-09:00",
                    "day_session": "09:00-10:15, 10:30-11:30, 13:30-15:00",
                    "night_session": "21:00-01:00"},
    ("SHFE", "AU"): {"call_auction": "20:55-21:00, 08:55-09:00",
                    "day_session": "09:00-10:15, 10:30-11:30, 13:30-15:00",
                    "night_session": "21:00-02:30"},
    ("SHFE", "AG"): {"call_auction": "20:55-21:00, 08:55-09:00",
                    "day_session": "09:00-10:15, 10:30-11:30, 13:30-15:00",
                    "night_session": "21:00-02:30"},
    ("SHFE", "WR"): {"call_auction": "08:55-09:00",
                    "day_session": "09:00-10:15, 10:30-11:30, 13:30-15:00",
                    "night_session": None},
    # 上期能源 INE
    ("INE", "SC"): {"call_auction": "20:55-21:00, 08:55-09:00",
                    "day_session": "09:00-10:15, 10:30-11:30, 13:30-15:00",
                    "night_session": "21:00-02:30"},
    ("INE", "BC"): {"call_auction": "20:55-21:00, 08:55-09:00",
                    "day_session": "09:00-10:15, 10:30-11:30, 13:30-15:00",
                    "night_session": "21:00-01:00"},
    ("INE", "NR"): {"call_auction": "20:55-21:00, 08:55-09:00",
                    "day_session": "09:00-10:15, 10:30-11:30, 13:30-15:00",
                    "night_session": "21:00-23:00"},
    ("INE", "EC"): {"call_auction": "08:55-09:00",
                    "day_session": "09:00-10:15, 10:30-11:30, 13:30-15:00",
                    "night_session": None},
    # 大商所 DCE — 大部分有夜盘,部分无
    ("DCE", "A"): {"call_auction": "20:55-21:00, 08:55-09:00",
                   "day_session": "09:00-10:15, 10:30-11:30, 13:30-15:00",
                   "night_session": "21:00-23:00"},
    ("DCE", "JD"): {"call_auction": "08:55-09:00",
                    "day_session": "09:00-10:15, 10:30-11:30, 13:30-15:00",
                    "night_session": None},
    ("DCE", "LH"): {"call_auction": "08:55-09:00",
                    "day_session": "09:00-10:15, 10:30-11:30, 13:30-15:00",
                    "night_session": None},
    # 中金所 CFFEX — 股指/国债交易时间
    ("CFFEX", "IF"): {"call_auction": "09:25-09:30",
                      "day_session": "09:30-11:30, 13:00-15:00",
                      "night_session": None},
    ("CFFEX", "TS"): {"call_auction": "09:25-09:30",
                      "day_session": "09:30-11:30, 13:00-15:15",
                      "night_session": None},
    ("CFFEX", "TL"): {"call_auction": "09:25-09:30",
                      "day_session": "09:30-11:30, 13:00-15:15",
                      "night_session": None},
}

# 交易所统一交易时间(作为上面查不到的回退)
_EXCHANGE_DEFAULT_HOURS: Dict[str, Dict] = {
    "SHFE": {
        "call_auction": "20:55-21:00, 08:55-09:00",
        "day_session": "09:00-10:15, 10:30-11:30, 13:30-15:00",
        "night_session": "21:00-01:00 或 21:00-23:00 或 21:00-02:30",
    },
    "INE": {
        "call_auction": "20:55-21:00, 08:55-09:00",
        "day_session": "09:00-10:15, 10:30-11:30, 13:30-15:00",
        "night_session": "21:00-01:00 或 21:00-23:00 或 21:00-02:30",
    },
    "DCE": {
        "call_auction": "20:55-21:00, 08:55-09:00",
        "day_session": "09:00-10:15, 10:30-11:30, 13:30-15:00",
        "night_session": "21:00-23:00",
    },
    "CZCE": {
        "call_auction": "20:55-21:00",
        "day_session": "09:00-10:15, 10:30-11:30, 13:30-15:00",
        "night_session": "21:00-23:00",
    },
    "GFEX": {
        "call_auction": "08:55-09:00",
        "day_session": "09:00-10:15, 10:30-11:30, 13:30-15:00",
        "night_session": None,
    },
    "CFFEX": {
        "call_auction": "09:25-09:30",
        "day_session": "09:30-11:30, 13:00-15:00 (国债 13:00-15:15)",
        "night_session": None,
    },
}


def get_trading_hours(variety_code: str, exchange: Optional[str] = None) -> Optional[Dict]:
    """
    获取品种交易时间

    Args:
        variety_code: 品种代码,大写
        exchange: 交易所代码(可选,提高精确度)

    Returns:
        dict: 含 call_auction / day_session / night_session
    """
    if not variety_code:
        return None
    if exchange:
        info = _TRADING_HOURS.get((exchange.upper(), variety_code.upper()))
        if info:
            return dict(info, has_night_session=bool(info.get("night_session")))
    return None


def get_exchange_trading_hours(exchange: str) -> Optional[Dict]:
    """获取交易所默认交易时间(回退)"""
    if not exchange:
        return None
    return _EXCHANGE_DEFAULT_HOURS.get(exchange.upper())


def has_night_session(variety_code: str, exchange: Optional[str] = None) -> Optional[bool]:
    """判断品种是否有夜盘(None 表示未知)"""
    info = get_trading_hours(variety_code, exchange)
    if not info:
        return None
    return bool(info.get("night_session"))


# =============================================================================
# 工具函数
# =============================================================================

def is_valid_exchange(code: str) -> bool:
    """判断是否为国内合法期货交易所代码"""
    return code and code.upper() in EXCHANGES


def normalize_exchange_code(code: str) -> Optional[str]:
    """归一化交易所代码(接受 'SHF' / 'shfe' / '上海期货交易所' / 'CZC' 等)"""
    if not code:
        return None
    code_upper = code.upper().strip()
    # 常见别名(不带点的交易所简写)
    alias_map = {
        "CZC": "CZCE",  # commodity_data 中常用 CZC 别名郑商所
        "SHF": "SHFE",
        "CFX": "CFFEX",
    }
    if code_upper in alias_map:
        return alias_map[code_upper]
    # 直接匹配
    if code_upper in EXCHANGES:
        return code_upper
    # 匹配后缀(去掉前导 '.')
    suffix_map = {v["suffix"].lstrip(".").upper(): k for k, v in EXCHANGES.items()}
    if code_upper in suffix_map:
        return suffix_map[code_upper]
    # 匹配缩写
    abbrev_map = {v["abbreviation_akshare"].upper(): k for k, v in EXCHANGES.items()}
    if code_upper in abbrev_map:
        return abbrev_map[code_upper]
    return None


def variety_summary() -> Dict:
    """品种汇总统计(用于健康检查/进度报告)"""
    by_exchange: Dict[str, int] = {}
    by_category: Dict[str, int] = {}
    for v in _ALL_VARIETIES:
        by_exchange[v["exchange"]] = by_exchange.get(v["exchange"], 0) + 1
        by_category[v["category"]] = by_category.get(v["category"], 0) + 1
    return {
        "total_varieties": len(_ALL_VARIETIES),
        "total_exchanges": len(EXCHANGES),
        "by_exchange": by_exchange,
        "by_category": by_category,
    }


if __name__ == "__main__":
    # 命令行调试:`python -m tradingagents.dataflows.providers.commodity.commodity_metadata`
    import json
    summary = variety_summary()
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    print()
    print("=== SHFE 品种列表(含 margin/commission/limit) ===")
    for v in list_varieties("SHFE"):
        print(f"  {v['symbol']:<4} {v['name_cn']:<10} {v['unit']:<6} "
              f"{v['contract_size']:>4}  margin={v['margin_rate']:.2%} "
              f"comm={v['commission_rate']:.5f} limit={v['limit_up_down_pct']:.2%}")
    print()
    cu = get_variety("CU", "SHFE")
    print(f"=== 抽样保证金核算: CU.SHFE 1手 × 70000 ===")
    required_margin = 1 * 70000 * cu["contract_size"] * cu["margin_rate"]
    print(f"  = 1 × 70000 × {cu['contract_size']}(合同乘数) × {cu['margin_rate']:.2%} "
          f"= {required_margin:,.2f} 元")
    print()
    print("=== CFFEX 交易时间示例 ===")
    print(get_trading_hours("TS", "CFFEX"))
