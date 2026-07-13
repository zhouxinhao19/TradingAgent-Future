"""
测试标的抽象(Instrument)和商品工具(CommodityUtils)
Phase 0 验证:stock / commodity 标识互斥、工厂方法正确
"""

import pytest

from tradingagents.core.instrument import (
    Instrument,
    ASSET_TYPE_STOCK,
    ASSET_TYPE_COMMODITY,
    ASSET_TYPE_UNKNOWN,
)
from tradingagents.utils.commodity_utils import (
    CommodityMarket,
    CommodityUtils,
)


# ==================== Instrument 工厂方法 ====================

class TestInstrumentOf:
    """Instrument.of 工厂方法"""

    # --- 股票标识 ---

    def test_of_a_share(self):
        inst = Instrument.of("000001")
        assert inst.asset_type == ASSET_TYPE_STOCK
        assert inst.is_stock is True
        assert inst.is_commodity is False
        assert inst.market == "china_a"
        assert inst.currency == "CNY"

    def test_of_hk_stock_with_suffix(self):
        inst = Instrument.of("0700.HK")
        assert inst.asset_type == ASSET_TYPE_STOCK
        assert inst.market == "hong_kong"
        assert inst.currency == "HKD"

    def test_of_hk_stock_digits_only(self):
        inst = Instrument.of("09988")
        assert inst.asset_type == ASSET_TYPE_STOCK
        assert inst.market == "hong_kong"

    def test_of_us_stock(self):
        inst = Instrument.of("AAPL")
        assert inst.asset_type == ASSET_TYPE_STOCK
        assert inst.market == "us"
        assert inst.currency == "USD"

    # --- 商品标识 ---

    def test_of_china_futures(self):
        inst = Instrument.of("CU2501.SHF")
        assert inst.asset_type == ASSET_TYPE_COMMODITY
        assert inst.is_commodity is True
        assert inst.is_stock is False
        assert inst.market == "china_futures"
        assert inst.currency == "CNY"
        assert inst.category == "metal"
        assert inst.unit == "吨"
        assert inst.contract_size == 5

    def test_of_international_futures(self):
        inst = Instrument.of("CL=F")
        assert inst.asset_type == ASSET_TYPE_COMMODITY
        assert inst.market == "international"
        assert inst.currency == "USD"
        assert inst.category == "energy"

    def test_of_international_gold(self):
        inst = Instrument.of("GC=F")
        assert inst.asset_type == ASSET_TYPE_COMMODITY
        assert inst.category == "precious"
        assert inst.unit == "盎司"
        assert inst.contract_size == 100

    def test_of_spot_cn(self):
        inst = Instrument.of("AU9999.SGE")
        assert inst.asset_type == ASSET_TYPE_COMMODITY
        assert inst.market == "spot_cn"
        assert inst.currency == "CNY"

    def test_of_lme(self):
        inst = Instrument.of("CU.LME")
        assert inst.asset_type == ASSET_TYPE_COMMODITY
        assert inst.market == "international"

    # --- 错误处理 ---

    def test_of_empty_raises(self):
        with pytest.raises(ValueError):
            Instrument.of("")

    def test_of_whitespace_raises(self):
        with pytest.raises(ValueError):
            Instrument.of("   ")

    def test_of_garbage_raises(self):
        with pytest.raises(ValueError, match="无法识别"):
            Instrument.of("not_a_valid_code_zzz_12345")

    def test_try_of_returns_none_on_invalid(self):
        assert Instrument.try_of("") is None
        assert Instrument.try_of("garbage") is None
        assert Instrument.try_of("000001") is not None

    # --- 序列化 ---

    def test_to_dict_stock(self):
        inst = Instrument.of("AAPL")
        d = inst.to_dict()
        assert d["code"] == "AAPL"
        assert d["asset_type"] == "stock"
        assert "market" in d
        assert "currency" in d

    def test_to_dict_commodity(self):
        inst = Instrument.of("CU2501.SHF")
        d = inst.to_dict()
        assert d["code"] == "CU2501.SHF"
        assert d["asset_type"] == "commodity"
        assert d["category"] == "metal"


# ==================== CommodityUtils 单元测试 ====================

class TestCommodityUtils:
    """CommodityUtils 工具类"""

    @pytest.mark.parametrize("code,expected", [
        # 国内期货
        ("CU2501.SHF", CommodityMarket.CHINA_FUTURES),
        ("AU2506.SHF", CommodityMarket.CHINA_FUTURES),
        ("I2501.DCE", CommodityMarket.CHINA_FUTURES),
        ("SR2501.CZC", CommodityMarket.CHINA_FUTURES),
        ("SC2501.INE", CommodityMarket.CHINA_FUTURES),
        ("SI2501.GFEX", CommodityMarket.CHINA_FUTURES),
        # 国际期货
        ("CL=F", CommodityMarket.INTERNATIONAL),
        ("GC=F", CommodityMarket.INTERNATIONAL),
        ("HG=F", CommodityMarket.INTERNATIONAL),
        # LME
        ("CU.LME", CommodityMarket.INTERNATIONAL),
        ("AL.LME", CommodityMarket.INTERNATIONAL),
        # 现货
        ("AU9999.SGE", CommodityMarket.SPOT_CN),
        ("AG9999.SGE", CommodityMarket.SPOT_CN),
        # 未知
        ("random_xxx", CommodityMarket.UNKNOWN),
        ("", CommodityMarket.UNKNOWN),
        ("000001", CommodityMarket.UNKNOWN),  # 6 位数字 = A股,不是商品
        ("AAPL", CommodityMarket.UNKNOWN),     # 美股代码,不是商品
    ])
    def test_identify_market(self, code, expected):
        assert CommodityUtils.identify_market(code) == expected

    @pytest.mark.parametrize("code,expected_currency", [
        ("CU2501.SHF", "CNY"),
        ("AU9999.SGE", "CNY"),
        ("CL=F", "USD"),
        ("GC=F", "USD"),
    ])
    def test_get_currency(self, code, expected_currency):
        assert CommodityUtils.get_currency(code) == expected_currency

    @pytest.mark.parametrize("code,expected_underlying", [
        ("CU2501.SHF", "CU"),
        ("AU2506.SHF", "AU"),
        ("CL=F", "CL"),
        ("GC=F", "GC"),
    ])
    def test_get_underlying_symbol(self, code, expected_underlying):
        assert CommodityUtils.get_underlying_symbol(code) == expected_underlying

    @pytest.mark.parametrize("code,expected_category", [
        ("CU2501.SHF", "metal"),
        ("AU2506.SHF", "precious"),
        ("I2501.DCE", "metal"),
        ("SR2501.CZC", "agricultural"),
        ("CL=F", "energy"),
        ("GC=F", "precious"),
        ("Y2501.DCE", "agricultural"),
    ])
    def test_get_category(self, code, expected_category):
        assert CommodityUtils.get_category(code) == expected_category

    def test_get_unit_copper(self):
        unit, size = CommodityUtils.get_unit("CU2501.SHF")
        assert unit == "吨"
        assert size == 5

    def test_get_unit_gold(self):
        unit, size = CommodityUtils.get_unit("AU2506.SHF")
        assert unit == "克"
        assert size == 1000

    def test_get_market_info_structure(self):
        info = CommodityUtils.get_market_info("CU2501.SHF")
        assert info["code"] == "CU2501.SHF"
        assert info["market"] == "china_futures"
        assert info["market_name"] == "国内期货"
        assert info["currency"] == "CNY"
        assert info["underlying"] == "CU"
        assert info["is_china_futures"] is True

    # --- 便捷函数 ---

    def test_is_china_futures(self):
        assert CommodityUtils.is_china_futures("CU2501.SHF") is True
        assert CommodityUtils.is_china_futures("CL=F") is False
        assert CommodityUtils.is_china_futures("000001") is False

    def test_is_international_futures(self):
        assert CommodityUtils.is_international_futures("CL=F") is True
        assert CommodityUtils.is_international_futures("CU2501.SHF") is False

    def test_is_spot_cn(self):
        assert CommodityUtils.is_spot_cn("AU9999.SGE") is True
        assert CommodityUtils.is_spot_cn("CU2501.SHF") is False


# ==================== 互斥性测试(关键) ====================

class TestStockCommodityExclusivity:
    """股票和商品识别互斥,同一代码不能同时被识别为两者"""

    @pytest.mark.parametrize("code", [
        # 股票代码不会被识别为商品
        "000001", "600519", "AAPL", "TSLA", "0700.HK",
    ])
    def test_stock_codes_not_commodity(self, code):
        market = CommodityUtils.identify_market(code)
        assert market == CommodityMarket.UNKNOWN, \
            f"股票代码 {code} 误识别为商品: {market}"

    @pytest.mark.parametrize("code", [
        # 商品代码不会被识别为股票
        "CU2501.SHF", "CL=F", "AU9999.SGE", "GC=F",
    ])
    def test_commodity_codes_not_stock(self, code):
        market = StockUtils.StockUtils.identify_stock_market(code) if False else None
        from tradingagents.utils.stock_utils import StockUtils, StockMarket
        stock_market = StockUtils.identify_stock_market(code)
        assert stock_market == StockMarket.UNKNOWN, \
            f"商品代码 {code} 误识别为股票: {stock_market}"
