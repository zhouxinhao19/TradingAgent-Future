"""
大宗商品数据层单元测试

覆盖:
- commodity_metadata: 静态字典(交易所/品种/合约参数/主力连续)
- commodity_utils: 标的识别(国内期货 / 现货 / 国际)
- base_commodity_provider: 抽象接口的扩展方法签名
- akshare_futures: 标准化方法和工厂方法

不依赖 akshare 真实环境(用 mock 或跳过网络调用)
"""
import asyncio
import sys
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def meta_mod():
    """直接以文件路径加载 commodity_metadata(不依赖 tradingagents 顶层 logger)"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "commodity_metadata",
        "tradingagents/dataflows/providers/commodity/commodity_metadata.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def utils_mod():
    """commodity_utils(支持国内期货/商品/国际)"""
    from tradingagents.utils.commodity_utils import (
        CommodityMarket, CommodityUtils,
        is_china_futures, is_international_futures,
    )
    return {
        "CommodityMarket": CommodityMarket,
        "CommodityUtils": CommodityUtils,
        "is_china_futures": is_china_futures,
        "is_international_futures": is_international_futures,
    }


@pytest.fixture
def base_mod():
    from tradingagents.dataflows.providers.commodity.base_commodity_provider import (
        BaseCommodityDataProvider,
    )
    return BaseCommodityDataProvider


@pytest.fixture
def akshare_mod():
    """直接以文件路径加载 akshare_futures 模块"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "akshare_futures",
        "tradingagents/dataflows/providers/commodity/akshare_futures.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def provider(akshare_mod):
    """akshare_futures provider 实例(不连接真实数据源)"""
    return akshare_mod.AkshareFuturesProvider()


# =============================================================================
# 1. commodity_metadata 测试
# =============================================================================

class TestCommodityMetadata:
    """测试静态元数据(交易所、品种、主力连续、归一化)"""

    def test_exchanges_count(self, meta_mod):
        """6 大期货交易所全部覆盖"""
        exchanges = meta_mod.list_exchanges()
        assert len(exchanges) == 6
        codes = {e["code"] for e in exchanges}
        assert codes == {"SHFE", "INE", "DCE", "CZCE", "GFEX", "CFFEX"}

    def test_exchange_metadata_fields(self, meta_mod):
        """交易所必须含 code/suffix/name_cn/homepage"""
        for code in ["SHFE", "DCE", "CZCE", "INE", "GFEX", "CFFEX"]:
            ex = meta_mod.get_exchange(code)
            assert ex is not None, f"缺交易所: {code}"
            for field in ("code", "suffix", "name_cn", "homepage", "abbreviation_akshare"):
                assert field in ex, f"交易所 {code} 缺字段 {field}"

    def test_varieties_at_least_70(self, meta_mod):
        """品种字典至少覆盖 70 个活跃品种(AKShare 文档约 100 个)"""
        varieties = meta_mod.list_varieties()
        assert len(varieties) >= 70

    def test_variety_required_fields(self, meta_mod):
        """每个品种必须含:variety_code/symbol/name_cn/category/unit/contract_size"""
        for v in meta_mod.list_varieties():
            for field in ("variety_code", "symbol", "name_cn", "category",
                         "unit", "contract_size", "tick_size", "list_date", "exchange"):
                assert field in v
                assert v[field], f"{v.get('symbol', '?')} 字段 {field} 为空"

    def test_variety_lookup_by_code(self, meta_mod):
        """根据品种代码精确查找"""
        cu = meta_mod.get_variety("CU")
        assert cu is not None
        assert cu["name_cn"] == "铜"
        assert cu["exchange"] == "SHFE"
        assert cu["contract_size"] == 5
        assert cu["tick_size"] == 10
        assert cu["unit"] == "吨"

    def test_variety_lookup_by_exchange_避免歧义(self, meta_mod):
        """BC 在 SHFE 不存在,只有 INE"""
        assert meta_mod.get_variety_by_exchange("SHFE", "BC") is None
        bc = meta_mod.get_variety_by_exchange("INE", "BC")
        assert bc is not None
        assert bc["name_cn"] == "国际铜"

    def test_品种几乎全交易所覆盖(self, meta_mod):
        """6 个交易所必须有品种"""
        summary = meta_mod.variety_summary()
        for ex in ("SHFE", "INE", "DCE", "CZCE", "GFEX", "CFFEX"):
            assert summary["by_exchange"].get(ex, 0) > 0, f"{ex} 缺失品种"

    def test_品类覆盖(self, meta_mod):
        """主要品类(金属/农产品/化工/能源/金融)必须有"""
        summary = meta_mod.variety_summary()
        cats = summary["by_category"]
        assert cats.get("metal", 0) > 0
        assert cats.get("agricultural", 0) > 0
        assert cats.get("financial", 0) > 0

    def test_主力连续合约代码(self, meta_mod):
        """AKShare 主力连续合约对照表"""
        assert meta_mod.get_main_continuous_symbol("CU") == "CU0"
        assert meta_mod.get_main_continuous_symbol("IF") == "IF0"
        assert meta_mod.get_main_continuous_symbol("RB") == "RB0"
        assert meta_mod.get_main_continuous_symbol("XX") is None  # 不存在

    def test_交易时间_有夜盘(self, meta_mod):
        """SC/INE 有夜盘(原油至 02:30),JD/DCE 无夜盘"""
        sc = meta_mod.get_trading_hours("SC", "INE")
        assert sc is not None
        assert sc["has_night_session"] is True
        assert "21:00" in sc["night_session"]

        jd = meta_mod.get_trading_hours("JD", "DCE")
        assert jd is not None
        assert jd["has_night_session"] is False

    def test_交易所别名归一化(self, meta_mod):
        """常见缩写 SHF/CZC/CFX/全名 都要能识别"""
        assert meta_mod.normalize_exchange_code("SHF") == "SHFE"
        assert meta_mod.normalize_exchange_code("CZC") == "CZCE"
        assert meta_mod.normalize_exchange_code("CFX") == "CFFEX"
        assert meta_mod.normalize_exchange_code("shfe") == "SHFE"
        assert meta_mod.normalize_exchange_code("SSE") is None  # 上海证券交易所不是期货所

    def test_is_valid_exchange(self, meta_mod):
        assert meta_mod.is_valid_exchange("SHFE")
        assert not meta_mod.is_valid_exchange("SSE")


# =============================================================================
# 2. commodity_utils 测试
# =============================================================================

class TestCommodityUtils:
    def test_识别国内期货_4位编码(self, utils_mod):
        """标准 YYMM 编码"""
        assert utils_mod["CommodityUtils"].identify_market("CU2501.SHF") == utils_mod["CommodityMarket"].CHINA_FUTURES
        assert utils_mod["CommodityUtils"].identify_market("RB2510.DCE") == utils_mod["CommodityMarket"].CHINA_FUTURES

    def test_识别国内期货_CZCE_3位编码(self, utils_mod):
        """CZCE 农产品合约可能用 3 位年月份"""
        assert utils_mod["CommodityUtils"].identify_market("AP410.CZC") == utils_mod["CommodityMarket"].CHINA_FUTURES
        assert utils_mod["CommodityUtils"].identify_market("CF401.CZC") == utils_mod["CommodityMarket"].CHINA_FUTURES

    def test_识别金融期货(self, utils_mod):
        """中金所 CFFEX 期货(股指/国债)"""
        assert utils_mod["CommodityUtils"].identify_market("IF2506.CFFEX") == utils_mod["CommodityMarket"].CHINA_FUTURES
        assert utils_mod["CommodityUtils"].identify_market("TS2509.CFFEX") == utils_mod["CommodityMarket"].CHINA_FUTURES

    def test_识别国际期货(self, utils_mod):
        """=F 主力连续"""
        assert utils_mod["CommodityUtils"].identify_market("CL=F") == utils_mod["CommodityMarket"].INTERNATIONAL
        assert utils_mod["CommodityUtils"].identify_market("GC=F") == utils_mod["CommodityMarket"].INTERNATIONAL

    def test_识别现货(self, utils_mod):
        """SGE 上海黄金交易所现货"""
        assert utils_mod["CommodityUtils"].identify_market("AU9999.SGE") == utils_mod["CommodityMarket"].SPOT_CN

    def test_识别未知(self, utils_mod):
        assert utils_mod["CommodityUtils"].identify_market("ZZZZ") == utils_mod["CommodityMarket"].UNKNOWN
        assert utils_mod["CommodityUtils"].identify_market("") == utils_mod["CommodityMarket"].UNKNOWN

    def test_快捷函数(self, utils_mod):
        assert utils_mod["is_china_futures"]("CU2501.SHF") is True
        assert utils_mod["is_china_futures"]("000001.SZ") is False
        assert utils_mod["is_international_futures"]("CL=F") is True


# =============================================================================
# 3. base_commodity_provider 测试
# =============================================================================

class TestBaseProvider:
    """基类:扩展接口默认抛 NotImplementedError"""

    def _make_concrete_provider(self, name):
        """创建一个能实例化的测试 provider"""

        class _P(base_mod := __import__(
            "tradingagents.dataflows.providers.commodity.base_commodity_provider",
            fromlist=["BaseCommodityDataProvider"]
        ).BaseCommodityDataProvider):
            async def connect(self):
                self.connected = True
                return True

            async def get_commodity_basic_info(self, full_symbol=None):
                return {"full_symbol": full_symbol or "CU2501.SHF"}

            async def get_commodity_quotes(self, full_symbol):
                return {"full_symbol": full_symbol, "close": 100.0}

            async def get_historical_data(self, full_symbol, start_date, end_date=None):
                return pd.DataFrame({"close": [100.0]})

        return _P(name)

    def test_强制抽象方法(self):
        """基础方法必须实现,否则无法实例化"""
        from tradingagents.dataflows.providers.commodity.base_commodity_provider import (
            BaseCommodityDataProvider,
        )
        with pytest.raises(TypeError):
            BaseCommodityDataProvider("x")  # type: ignore

    def test_扩展接口_默认_NotImplementedError(self):
        p = self._make_concrete_provider("test")
        # 所有扩展方法默认抛 NotImplementedError;按各自签名传最小必填参数
        # 注:get_inventory / get_registered_receipt / get_basis_history /
        #    get_basis_history 必填位置参数 → 传空字符串
        cases = [
            ("get_fees_and_margin", ()),
            ("get_inventory", ("A",)),
            ("get_warehouse_receipt", ("SHFE", "20240101")),
            ("get_position_rank", ("DCE", "20240101")),
            ("get_registered_receipt", ("20240101", "20240201", ["A"])),
            ("get_spot_price", ("20240101",)),
            ("get_basis_history", ("20240101", "20240201", ["A"])),
            ("get_basis_spot_previous", ("20240101",)),
            ("get_roll_yield", ("date",)),
            ("get_contract_info", ("SHFE", "20240101")),
            ("get_trading_calendar", ("20240101",)),
            ("get_realtime_quote", ("V2205",)),
            ("get_minute_kline", ("RB0",)),
            ("get_delivery_info", ("DCE", "20240101")),
            ("get_holding_position", ("RB0",)),
        ]
        for method, args in cases:
            with pytest.raises(NotImplementedError):
                asyncio.run(getattr(p, method)(*args))

    def test_标准化方法(self):
        p = self._make_concrete_provider("t")
        basic = p.standardize_basic_info({
            "code": "CU2501", "full_symbol": "CU2501.SHF", "name": "沪铜2501",
        })
        assert basic["data_source"] == "t"
        assert basic["code"] == "CU2501"
        assert isinstance(basic["updated_at"], datetime)


# =============================================================================
# 4. akshare_futures 测试
# =============================================================================

class TestAkshareProvider:
    def test_provider_name(self, provider):
        assert provider.provider_name == "akshare_futures"
        assert provider.is_available() is False  # 未 connect

    @pytest.mark.parametrize("full_symbol,exchange,underlying,unit,contract_size", [
        ("CU2501.SHF", "SHF", "CU", "吨", 5),
        ("AU2502.SHF", "SHF", "AU", "克", 1000),
        ("RB2510.SHF", "SHF", "RB", "吨", 10),
        ("BC2506.INE", "INE", "BC", "吨", 5),
        ("SC2503.INE", "INE", "SC", "桶", 1000),
        ("A2509.DCE", "DCE", "A", "吨", 10),
        ("I2509.DCE", "DCE", "I", "吨", 100),
        ("SR2509.CZC", "CZC", "SR", "吨", 10),
        ("MA2509.CZC", "CZC", "MA", "吨", 10),
        ("SI2509.GFEX", "GFEX", "SI", "吨", 5),
        ("LC2509.GFEX", "GFEX", "LC", "吨", 1),
        ("IF2506.CFFEX", "CFFEX", "IF", "点", 300),
        ("TS2509.CFFEX", "CFFEX", "TS", "点", 20000),
    ])
    def test_build_basic_info_全品种(
        self, akshare_mod, full_symbol, exchange, underlying, unit, contract_size,
    ):
        info = akshare_mod.AkshareFuturesProvider._build_basic_info(full_symbol)
        assert info is not None, f"_build_basic_info 失败: {full_symbol}"
        assert info["exchange"] == exchange
        assert info["underlying"] == underlying
        assert info["unit"] == unit
        assert info["contract_size"] == contract_size
        assert info["is_china_futures"] is True
        assert info["data_source"] == "akshare_futures"
        # 必须有 tick_size 和 list_date(来自 commodity_metadata)
        assert "tick_size" in info
        assert "list_date" in info

    def test_build_basic_info_未知标的返回None(self, akshare_mod):
        """非国内期货返回 None"""
        info = akshare_mod.AkshareFuturesProvider._build_basic_info("000001.SZ")
        assert info is None
        info = akshare_mod.AkshareFuturesProvider._build_basic_info("CL=F")
        assert info is None

    @pytest.mark.parametrize("full_symbol,expected", [
        ("CU2501.SHF", "CU2501"),
        ("RB2506.DCE", "RB2506"),
        ("SC2503.INE", "SC2503"),
        ("IF2506.CFFEX", "IF2506"),
    ])
    def test_strip_exchange(self, akshare_mod, full_symbol, expected):
        assert akshare_mod.AkshareFuturesProvider._strip_exchange(full_symbol) == expected

    def test_to_ak_exchange(self, akshare_mod):
        """交易所代码 -> AKShare 接口缩写"""
        m = akshare_mod._to_ak_exchange
        assert m("SHFE") == "shfe"
        assert m("CZCE") == "czce"
        assert m("DCE") == "dce"

    def test_list_all_varieties_无网络也返回(self, provider):
        """list_all_varieties 不依赖网络,使用 commodity_metadata 静态表"""
        items = asyncio.run(provider.list_all_varieties())
        assert isinstance(items, list)
        assert len(items) >= 70
        # 每条都是 variety type
        assert all(it["type"] == "variety" for it in items)
        # 含上期所主力品种
        symbols = {it["symbol"] for it in items}
        assert "CU" in symbols  # 铜
        assert "AU" in symbols  # 黄金
        assert "IF" in symbols  # 股指

    def test_akshare_未装_不抛异常(self, provider):
        """akshare import 失败时,所有 _call 路径都应优雅返回 None

        通过 monkeypatch connect 模拟"akshare 未安装"场景,
        此时 _ak 保持 None, _ensure_ak 返回 False → 各方法直接返回 None
        """
        async def _fake_connect():
            self_provider_id = id(provider)
            provider._ak = None
            return False

        # 强制让 connect() 失败,_ak 仍为 None
        import unittest.mock as _mock
        with _mock.patch.object(
            provider.__class__, "connect",
            new=lambda self: _fake_connect(),
        ):
            provider._ak = None
            provider.connected = False
            df = asyncio.run(provider.get_historical_data("CU2501.SHF", "2024-01-01"))
            assert df is None
            quotes = asyncio.run(provider.get_commodity_quotes("CU2501.SHF"))
            assert quotes is None
            info = asyncio.run(provider.get_fees_and_margin())
            assert info is None
            df = asyncio.run(provider.get_inventory("A"))
            assert df is None


# =============================================================================
# 5. 集成测试(用 monkeypatch mock AKShare 接口,验证调用链)
# =============================================================================

class TestAkshareIntegration:
    """验证每个数据接口会调用正确的 AKShare 函数名 + 正确的参数"""

    @pytest.fixture
    def mock_ak(self, akshare_mod):
        """注入一个 mock 的 akshare 模块,所有函数返回预置 DataFrame"""
        mock = MagicMock()
        # 每个函数返回空白但有效 DataFrame
        empty_df = pd.DataFrame({"col": [1, 2, 3]})
        mock.futures_main_sina.return_value = empty_df
        mock.futures_comm_info.return_value = empty_df
        mock.futures_comm_js.return_value = empty_df
        mock.futures_fees_info.return_value = empty_df
        mock.futures_settle.return_value = empty_df
        mock.futures_inventory_em.return_value = empty_df
        mock.futures_inventory_99.return_value = empty_df
        mock.futures_shfe_warehouse_receipt.return_value = {"CU": empty_df}
        mock.futures_warehouse_receipt_dce.return_value = empty_df
        mock.futures_gfex_warehouse_receipt.return_value = {"SI": empty_df}
        mock.futures_warehouse_receipt_czce.return_value = {"AP": empty_df}
        mock.futures_dce_position_rank.return_value = {"a2509": empty_df}
        mock.futures_gfex_position_rank.return_value = {"si2509": empty_df}
        mock.get_shfe_rank_table.return_value = empty_df
        mock.get_cffex_rank_table.return_value = empty_df
        mock.get_rank_table_czce.return_value = empty_df
        mock.get_receipt.return_value = empty_df
        mock.futures_spot_price.return_value = empty_df
        mock.futures_spot_price_previous.return_value = empty_df
        mock.futures_spot_price_daily.return_value = empty_df
        mock.get_roll_yield_bar.return_value = empty_df
        mock.get_roll_yield.return_value = empty_df
        mock.futures_contract_info_shfe.return_value = empty_df
        mock.futures_contract_info_ine.return_value = empty_df
        mock.futures_contract_info_dce.return_value = empty_df
        mock.futures_contract_info_czce.return_value = empty_df
        mock.futures_contract_info_gfex.return_value = empty_df
        mock.futures_contract_info_cffex.return_value = empty_df
        mock.futures_rule.return_value = empty_df
        mock.futures_zh_spot.return_value = empty_df
        mock.futures_zh_realtime.return_value = empty_df
        mock.futures_zh_minute_sina.return_value = empty_df
        mock.futures_delivery_dce.return_value = empty_df
        mock.futures_delivery_czce.return_value = empty_df
        mock.futures_delivery_shfe.return_value = empty_df
        mock.futures_to_spot_dce.return_value = empty_df
        mock.futures_to_spot_czce.return_value = empty_df
        mock.futures_to_spot_shfe.return_value = empty_df
        mock.futures_hold_pos_sina.return_value = empty_df
        mock.futures_news_shmet.return_value = empty_df
        # 合成器使用的接口
        mock.energy_oil_hist.return_value = empty_df
        mock.macro_china_daily_energy.return_value = empty_df
        mock.macro_china_agricultural_product.return_value = empty_df
        mock.futures_hog_supply.return_value = empty_df
        mock.index_hog_spot_price.return_value = empty_df
        mock.index_outer_quote_sugar_msweet.return_value = empty_df
        # financial 合成器
        mock.index_option_300index_qvix.return_value = empty_df
        mock.index_option_300etf_qvix.return_value = empty_df
        mock.index_option_1000index_qvix.return_value = empty_df
        mock.bond_zh_us_rate.return_value = empty_df
        mock.macro_china_shibor_all.return_value = empty_df
        mock.macro_china_lpr.return_value = empty_df
        # global_macro 合成器
        mock.stock_info_cjzc_em.return_value = empty_df
        mock.stock_info_global_em.return_value = empty_df
        mock.stock_info_global_futu.return_value = empty_df
        mock.stock_info_global_ths.return_value = empty_df
        mock.stock_info_global_sina.return_value = empty_df
        mock.stock_info_global_cls.return_value = empty_df
        return mock

    def test_get_inventory_优先_em(self, akshare_mod, mock_ak):
        provider = akshare_mod.AkshareFuturesProvider()
        provider._ak = mock_ak

        df = asyncio.run(provider.get_inventory("A"))

        # 新逻辑: 先尝试中文名"豆一"(比英文代码更高效),成功后直接返回
        mock_ak.futures_inventory_em.assert_called_once_with(symbol="豆一")
        mock_ak.futures_inventory_99.assert_not_called()
        assert df is not None

    def test_get_warehouse_receipt_交易所分支(self, akshare_mod, mock_ak):
        provider = akshare_mod.AkshareFuturesProvider()
        provider._ak = mock_ak

        # SHFE -> futures_shfe_warehouse_receipt
        asyncio.run(provider.get_warehouse_receipt("SHFE", "20240101"))
        mock_ak.futures_shfe_warehouse_receipt.assert_called_with(date="20240101")

        # CZC -> futures_warehouse_receipt_czce
        asyncio.run(provider.get_warehouse_receipt("CZC", "20240101"))
        mock_ak.futures_warehouse_receipt_czce.assert_called_with(date="20240101")

        # GFEX
        asyncio.run(provider.get_warehouse_receipt("GFEX", "20240101"))
        mock_ak.futures_gfex_warehouse_receipt.assert_called_with(date="20240101")

    def test_get_position_rank_交易所分支(self, akshare_mod, mock_ak):
        provider = akshare_mod.AkshareFuturesProvider()
        provider._ak = mock_ak

        asyncio.run(provider.get_position_rank("DCE", "20240101", vars_list=["A"]))
        mock_ak.futures_dce_position_rank.assert_called_with(date="20240101", vars_list=["A"])

        asyncio.run(provider.get_position_rank("SHFE", "20240101"))
        mock_ak.get_shfe_rank_table.assert_called_with(date="20240101")

        asyncio.run(provider.get_position_rank("CFFEX", "20240101"))
        mock_ak.get_cffex_rank_table.assert_called_with(date="20240101")

    def test_get_contract_info_交易所分支(self, akshare_mod, mock_ak):
        provider = akshare_mod.AkshareFuturesProvider()
        provider._ak = mock_ak

        asyncio.run(provider.get_contract_info("SHFE", "20240101"))
        mock_ak.futures_contract_info_shfe.assert_called_once()

        asyncio.run(provider.get_contract_info("DCE"))
        mock_ak.futures_contract_info_dce.assert_called_once()

        asyncio.run(provider.get_contract_info("GFEX"))
        mock_ak.futures_contract_info_gfex.assert_called_once()

    def test_get_roll_yield_三种类型(self, akshare_mod, mock_ak):
        provider = akshare_mod.AkshareFuturesProvider()
        provider._ak = mock_ak

        # type_method=date
        asyncio.run(provider.get_roll_yield(
            "date", var="RB", start_day="20240101", end_day="20240201"
        ))
        mock_ak.get_roll_yield_bar.assert_called_with(
            type_method="date", var="RB", start_day="20240101", end_day="20240201"
        )

        # type_method=symbol
        asyncio.run(provider.get_roll_yield("symbol", var="RB", date="20240101"))
        mock_ak.get_roll_yield_bar.assert_called_with(
            type_method="symbol", var="RB", date="20240101"
        )

        # type_method=var
        asyncio.run(provider.get_roll_yield("var", date="20240101"))
        mock_ak.get_roll_yield_bar.assert_called_with(
            type_method="var", date="20240101"
        )

    def test_get_fees_and_margin_多源降级(self, akshare_mod, mock_ak):
        """SHFE -> 优先 futures_comm_info"""
        provider = akshare_mod.AkshareFuturesProvider()
        provider._ak = mock_ak

        result = asyncio.run(provider.get_fees_and_margin(exchange="SHFE"))
        mock_ak.futures_comm_info.assert_called_with(symbol="上海期货交易所")
        # 因为 mock_ak.futures_comm_info 返回 empty_df,转换 dict 后返回
        assert result is not None

    def test_get_spot_price(self, akshare_mod, mock_ak):
        provider = akshare_mod.AkshareFuturesProvider()
        provider._ak = mock_ak

        # get_spot_price 现在优先调用 futures_spot_price_daily(避开100ppi.com)
        # 需要 mock 返回有效的 DataFrame
        spot_daily_df = pd.DataFrame({
            "date": ["2024-01-02"],
            "symbol": ["CU"],
            "spot_price": [70000.0],
            "dominant_contract": ["cu2402"],
            "dominant_contract_price": [69800.0],
            "dom_basis": [-200.0],
            "dom_basis_rate": [-0.002857],
        })
        mock_ak.futures_spot_price_daily.return_value = spot_daily_df

        df = asyncio.run(provider.get_spot_price("20240101"))
        # 验证调用了 futures_spot_price_daily (非 futures_spot_price)
        mock_ak.futures_spot_price_daily.assert_called()
        mock_ak.futures_spot_price.assert_not_called()
        assert df is not None
        assert not df.empty

    def test_get_minute_kline(self, akshare_mod, mock_ak):
        provider = akshare_mod.AkshareFuturesProvider()
        provider._ak = mock_ak

        asyncio.run(provider.get_minute_kline("RB0", period=5))
        mock_ak.futures_zh_minute_sina.assert_called_with(symbol="RB0", period=5)

    # ----- get_futures_news -----

    def test_get_futures_news_分类映射_铜(self, akshare_mod, mock_ak):
        provider = akshare_mod.AkshareFuturesProvider()
        provider._ak = mock_ak
        # 设 DataFrame 返回带【】标题的多行
        provider._ak.futures_news_shmet.return_value = pd.DataFrame({
            "发布时间": [
                "2024-03-21 14:02:44+08:00",
                "2024-03-21 12:10:40+08:00",
            ],
            "内容": [
                "【铜价强势上涨 主因库存去化】本日铜价强势上涨,主因库存去化,行业利好",
                "【SHMET铜现货报价】上海金属网讯:截止11:30,1#电解铜报72700-72800",
            ],
        })

        items = asyncio.run(provider.get_futures_news(category="copper", limit=10))

        mock_ak.futures_news_shmet.assert_called_with(symbol="铜")
        assert items is not None
        assert len(items) == 2
        # 标题解析
        assert items[0]["title"] == "铜价强势上涨 主因库存去化"
        assert "本日铜价强势上涨" in items[0]["content"]
        # 第二条同样应有 title
        assert items[1]["title"] == "SHMET铜现货报价"
        # 第一条 sentiment 应为 positive(强势上涨+利好)
        assert items[0]["sentiment"] == "positive"
        assert items[0]["sentiment_score"] > 0
        # 来源
        assert items[0]["source"] == "shmet"
        assert items[0]["category"] == "copper"

    def test_get_futures_news_默认all(self, akshare_mod, mock_ak):
        """category='all' 或空 → 调用 shmet symbol='全部'"""
        provider = akshare_mod.AkshareFuturesProvider()
        provider._ak = mock_ak
        provider._ak.futures_news_shmet.return_value = pd.DataFrame({
            "发布时间": ["2024-03-21 09:00:00+08:00"],
            "内容": ["【期货市场大幅调整】今日期货市场大幅下跌,行业利空,空头氛围浓"],
        })

        items = asyncio.run(provider.get_futures_news())
        mock_ak.futures_news_shmet.assert_called_with(symbol="全部")
        assert items[0]["sentiment"] == "negative"
        assert items[0]["sentiment_score"] < 0

    def test_get_futures_news_financial_已不再支持(self, akshare_mod, mock_ak):
        """financial(IF/IH/国债等)已不再支持的分类 → 返回 []"""
        provider = akshare_mod.AkshareFuturesProvider()
        provider._ak = mock_ak
        items = asyncio.run(provider.get_futures_news(category="financial"))
        assert items == []
        mock_ak.futures_news_shmet.assert_not_called()

    def test_get_futures_news_未识别分类_返回空列表(self, akshare_mod, mock_ak):
        """完全未识别的 category(如 xyz) → 返回 [] + warning,不调用任何 AKShare"""
        provider = akshare_mod.AkshareFuturesProvider()
        provider._ak = mock_ak

        items = asyncio.run(provider.get_futures_news(category="xyz未知分类"))
        assert items == []
        mock_ak.futures_news_shmet.assert_not_called()
        mock_ak.energy_oil_hist.assert_not_called()
        mock_ak.macro_china_daily_energy.assert_not_called()
        mock_ak.macro_china_agricultural_product.assert_not_called()

    def test_get_futures_news_无标题_退回整段(self, akshare_mod, mock_ak):
        """内容不以【开头时,title 应为空"""
        provider = akshare_mod.AkshareFuturesProvider()
        provider._ak = mock_ak
        provider._ak.futures_news_shmet.return_value = pd.DataFrame({
            "发布时间": ["2024-03-21 09:00:00+08:00"],
            "内容": ["  2024年3月21日LME铜库存增加1234吨,行业利空"],
        })

        items = asyncio.run(provider.get_futures_news())
        assert items[0]["title"] == ""
        assert "LME铜库存增加" in items[0]["content"]
        # "利空" / "增加" 关键词触发 negative
        assert items[0]["sentiment"] == "negative"

    def test_get_futures_news_limit_生效(self, akshare_mod, mock_ak):
        provider = akshare_mod.AkshareFuturesProvider()
        provider._ak = mock_ak
        provider._ak.futures_news_shmet.return_value = pd.DataFrame({
            "发布时间": ["2024-03-21 09:00:00+08:00"] * 100,
            "内容": ["【行业大涨】行业大涨,利好出货"] * 100,
        })

        items = asyncio.run(provider.get_futures_news(limit=10))
        assert len(items) == 10

    def test_get_futures_news_空DataFrame(self, akshare_mod, mock_ak):
        """返回空 df → 返回空列表(不应抛错)"""
        provider = akshare_mod.AkshareFuturesProvider()
        provider._ak = mock_ak
        provider._ak.futures_news_shmet.return_value = pd.DataFrame(columns=["发布时间", "内容"])

        items = asyncio.run(provider.get_futures_news())
        assert items == []

    def test_get_futures_news_情感_neutral(self, akshare_mod, mock_ak):
        """中性关键词"""
        provider = akshare_mod.AkshareFuturesProvider()
        provider._ak = mock_ak
        provider._ak.futures_news_shmet.return_value = pd.DataFrame({
            "发布时间": ["2024-03-21 09:00:00+08:00"],
            "内容": ["【正常生产】今日工厂正常生产,出货稳定"],
        })

        items = asyncio.run(provider.get_futures_news())
        assert items[0]["sentiment"] == "neutral"
        assert items[0]["sentiment_score"] == 0.0

    # ----- global_macro 合成器测试 -----

    def test_get_futures_news_global_macro_全部6源调用(self, akshare_mod, mock_ak):
        """global_macro 类别应尝试所有 6 个 AKShare 资讯源"""
        provider = akshare_mod.AkshareFuturesProvider()
        provider._ak = mock_ak

        items = asyncio.run(provider.get_futures_news(category="global_macro"))

        # 6 个接口都应被尝试
        mock_ak.stock_info_global_cls.assert_called_once_with(symbol="全部")
        mock_ak.stock_info_global_em.assert_called_once()
        mock_ak.stock_info_global_ths.assert_called_once()
        mock_ak.stock_info_global_futu.assert_called_once()
        mock_ak.stock_info_cjzc_em.assert_called_once()
        mock_ak.stock_info_global_sina.assert_called_once()

        # mock 给的是空 df → 返回空列表
        assert items == []

    def test_get_futures_news_global_macro_混合字段(self, akshare_mod, mock_ak):
        """每个源用各自字段映射,统一标题/正文/时间/链接"""
        provider = akshare_mod.AkshareFuturesProvider()
        provider._ak = mock_ak

        # 东财: 标题+摘要+发布时间+链接
        mock_ak.stock_info_global_em.return_value = pd.DataFrame({
            "标题": ["欧央行维勒鲁瓦: 6月降息可能性高于4月"],
            "摘要": ["仍有可能在春季降息,取决于通胀数据"],
            "发布时间": ["2024-03-13 16:20:00"],
            "链接": ["https://kuaixun.eastmoney.com/a/abc.html"],
        })
        # 新浪: 只有时间+内容
        mock_ak.stock_info_global_sina.return_value = pd.DataFrame({
            "时间": ["2024-03-13 16:18:40"],
            "内容": ["【Canalys:2023年Q4英特尔CPU出货5000万颗】根据Canalys数据..."],
        })
        # 同花顺: 标题+内容+发布时间+链接
        mock_ak.stock_info_global_ths.return_value = pd.DataFrame({
            "标题": ["机构论市: 指数一波三折"],
            "内容": ["传媒、游戏逆势走强!"],
            "发布时间": ["2024-03-13 15:00:00"],
            "链接": ["https://news.10jqka.com.cn/abc.html"],
        })
        # 财经早餐: 标题+摘要(不是内容)
        mock_ak.stock_info_cjzc_em.return_value = pd.DataFrame({
            "标题": ["东方财富财经早餐 3月13日周三"],
            "摘要": ["今日财经早餐..."],
            "发布时间": ["2024-03-13 06:00:00"],
            "链接": ["http://finance.eastmoney.com/a/abc.html"],
        })

        items = asyncio.run(provider.get_futures_news(category="global_macro", limit=20))

        # 应该至少 4 条(去掉没有内容的)
        assert len(items) >= 4
        # source 标识
        sources = {it["source"] for it in items}
        assert sources == {"eastmoney", "sina", "ths", "cjzc"}
        # category / metal
        for it in items:
            assert it["category"] == "global_macro"
            assert it["metal"] == "全球宏观"
        # 检查 sina 自动从【】解析 title
        sina_items = [it for it in items if it["source"] == "sina"]
        assert len(sina_items) == 1
        assert sina_items[0]["title"] == "Canalys:2023年Q4英特尔CPU出货5000万颗"
        # 检查 cjzc 用摘要做内容
        cjzc_items = [it for it in items if it["source"] == "cjzc"]
        assert len(cjzc_items) == 1
        assert cjzc_items[0]["content"] == "今日财经早餐..."
        # 检查 url 字段
        assert "kuaixun.eastmoney.com" in items[0]["url"] or any(
            "kuaixun.eastmoney.com" in it["url"] for it in items
        )
        # 检查 sina 没有 url(空字符串)
        assert sina_items[0]["url"] == ""

    def test_get_futures_news_global_macro_情感判定(self, akshare_mod, mock_ak):
        """情感分析应该对全球宏观新闻生效"""
        provider = akshare_mod.AkshareFuturesProvider()
        provider._ak = mock_ak
        # 只配一个源,放一条利好新闻
        mock_ak.stock_info_global_em.return_value = pd.DataFrame({
            "标题": ["重大利好: 经济数据超预期,大涨"],
            "摘要": ["今日 GDP 数据大幅增长,行业大涨,创新高"],
            "发布时间": ["2024-03-13 16:20:00"],
            "链接": ["https://kuaixun.eastmoney.com/abc.html"],
        })
        # 抑制其它源
        mock_ak.stock_info_global_cls.return_value = pd.DataFrame(
            columns=["标题", "内容", "发布日期", "发布时间"]
        )
        mock_ak.stock_info_global_ths.return_value = pd.DataFrame(
            columns=["标题", "内容", "发布时间", "链接"]
        )
        mock_ak.stock_info_global_futu.return_value = pd.DataFrame(
            columns=["标题", "内容", "发布时间", "链接"]
        )
        mock_ak.stock_info_cjzc_em.return_value = pd.DataFrame(
            columns=["标题", "摘要", "发布时间", "链接"]
        )
        mock_ak.stock_info_global_sina.return_value = pd.DataFrame(
            columns=["时间", "内容"]
        )

        items = asyncio.run(provider.get_futures_news(category="global_macro"))
        assert len(items) >= 1
        # 利好新闻 → positive
        em_item = [it for it in items if it["source"] == "eastmoney"][0]
        assert em_item["sentiment"] == "positive"
        assert em_item["sentiment_score"] > 0

    def test_get_futures_news_global_macro_时间倒序(self, akshare_mod, mock_ak):
        """多源新闻按发布时间倒序合并"""
        provider = akshare_mod.AkshareFuturesProvider()
        provider._ak = mock_ak
        # 东财 16:20
        mock_ak.stock_info_global_em.return_value = pd.DataFrame({
            "标题": ["东财新闻"],
            "摘要": ["内容"],
            "发布时间": ["2024-03-13 16:20:00"],
            "链接": [""],
        })
        # 同花顺 10:00
        mock_ak.stock_info_global_ths.return_value = pd.DataFrame({
            "标题": ["同花顺新闻"],
            "内容": ["内容"],
            "发布时间": ["2024-03-13 10:00:00"],
            "链接": [""],
        })
        mock_ak.stock_info_global_cls.return_value = pd.DataFrame(
            columns=["标题", "内容", "发布日期", "发布时间"]
        )
        mock_ak.stock_info_global_futu.return_value = pd.DataFrame(
            columns=["标题", "内容", "发布时间", "链接"]
        )
        mock_ak.stock_info_cjzc_em.return_value = pd.DataFrame(
            columns=["标题", "摘要", "发布时间", "链接"]
        )
        mock_ak.stock_info_global_sina.return_value = pd.DataFrame(
            columns=["时间", "内容"]
        )

        items = asyncio.run(provider.get_futures_news(category="global_macro"))

        em = [it for it in items if it["title"] == "东财新闻"][0]
        ths = [it for it in items if it["title"] == "同花顺新闻"][0]
        # 东财 16:20 应在 同花顺 10:00 之前(更靠前)
        assert items.index(em) < items.index(ths)

    def test_get_futures_news_global_macro_limit生效(self, akshare_mod, mock_ak):
        """limit 参数客户端截断"""
        provider = akshare_mod.AkshareFuturesProvider()
        provider._ak = mock_ak
        # 东财 100 条
        em_df = pd.DataFrame({
            "标题": [f"东财{i:03d}" for i in range(100)],
            "摘要": ["内容"] * 100,
            "发布时间": [f"2024-03-13 16:{i//60:02d}:{i%60:02d}" for i in range(100)],
            "链接": [""] * 100,
        })
        mock_ak.stock_info_global_em.return_value = em_df
        mock_ak.stock_info_global_cls.return_value = pd.DataFrame(
            columns=["标题", "内容", "发布日期", "发布时间"]
        )
        mock_ak.stock_info_global_ths.return_value = pd.DataFrame(
            columns=["标题", "内容", "发布时间", "链接"]
        )
        mock_ak.stock_info_global_futu.return_value = pd.DataFrame(
            columns=["标题", "内容", "发布时间", "链接"]
        )
        mock_ak.stock_info_cjzc_em.return_value = pd.DataFrame(
            columns=["标题", "摘要", "发布时间", "链接"]
        )
        mock_ak.stock_info_global_sina.return_value = pd.DataFrame(
            columns=["时间", "内容"]
        )

        items = asyncio.run(provider.get_futures_news(category="global_macro", limit=10))
        assert len(items) == 10

    def test_get_futures_news_global_macro_仅时间被解析(self, akshare_mod, mock_ak):
        """新浪只有【时间】列,应被识别为时间字段"""
        provider = akshare_mod.AkshareFuturesProvider()
        provider._ak = mock_ak
        mock_ak.stock_info_global_sina.return_value = pd.DataFrame({
            "时间": ["2024-03-13 16:18:40"],
            "内容": ["【测试1】仅新浪源,这是一条快讯"],
        })
        mock_ak.stock_info_global_cls.return_value = pd.DataFrame(
            columns=["标题", "内容", "发布日期", "发布时间"]
        )
        mock_ak.stock_info_global_em.return_value = pd.DataFrame(
            columns=["标题", "摘要", "发布时间", "链接"]
        )
        mock_ak.stock_info_global_ths.return_value = pd.DataFrame(
            columns=["标题", "内容", "发布时间", "链接"]
        )
        mock_ak.stock_info_global_futu.return_value = pd.DataFrame(
            columns=["标题", "内容", "发布时间", "链接"]
        )
        mock_ak.stock_info_cjzc_em.return_value = pd.DataFrame(
            columns=["标题", "摘要", "发布时间", "链接"]
        )

        items = asyncio.run(provider.get_futures_news(category="global_macro", limit=10))
        assert len(items) == 1
        assert items[0]["source"] == "sina"
        assert items[0]["published_at"] == "2024-03-13 16:18:40"
        # 从【】解析 title
        assert items[0]["title"] == "测试1"


# =============================================================================
# 6. 合约 → 静态元数据 → 标准化 全链路一致性测试
# =============================================================================

class TestIntegration:
    """合约代码 → commodity_metadata → akshare_futures._build_basic_info 全链路"""

    @pytest.mark.parametrize("symbol_code,exchange,expected_name_cn,expected_unit,expected_size", [
        ("CU", "SHFE", "铜", "吨", 5),
        ("AU", "SHFE", "黄金", "克", 1000),
        ("AG", "SHFE", "白银", "千克", 15),
        ("SC", "INE", "原油", "桶", 1000),
        ("IF", "CFFEX", "沪深300股指", "点", 300),
        ("TL", "CFFEX", "30年期国债", "点", 10000),
        ("A", "DCE", "黄大豆1号", "吨", 10),
        ("CF", "CZCE", "一号棉花", "吨", 5),
        ("SI", "GFEX", "工业硅", "吨", 5),
    ])
    def test_合约元数据一致性(
        self, meta_mod, akshare_mod, symbol_code, exchange,
        expected_name_cn, expected_unit, expected_size,
    ):
        """静态元数据与 _build_basic_info 输出必须一致"""
        variety = meta_mod.get_variety_by_exchange(exchange, symbol_code)
        assert variety is not None
        assert variety["name_cn"] == expected_name_cn
        assert variety["unit"] == expected_unit
        assert variety["contract_size"] == expected_size

        # 与 akshare_futures._build_basic_info 输出交叉验证
        info = akshare_mod.AkshareFuturesProvider._build_basic_info(
            f"{symbol_code}2501.{exchange[:3] if exchange != 'SHFE' else 'SHF'}"
        )
        if info is not None:
            assert info["unit"] == expected_unit
            assert info["contract_size"] == expected_size


class TestMainContractFallback:
    """主力连续回退测试(Phase 3a P0 修复):

    具体合约(如 CU2501.SHF)无行情时,自动回退到主力连续(CU0)。
    验证:
    - get_commodity_quotes:回退后 used_continuous_fallback=True, data_source 含
      "continuous_fallback" 标记
    - get_historical_data:回退后 df.attrs["data_source_note"] == "continuous_fallback"
    - _try_continuous_fallback:辅助方法直接调,成功/失败两种路径
    """

    @pytest.fixture
    def mock_ak_empty(self):
        """mock 整个 akshare 模块,让所有接口返空 DataFrame"""
        import pandas as pd
        mock = MagicMock()
        empty = pd.DataFrame()
        # 所有 futures_* 接口返空
        for name in (
            "futures_hist_em", "futures_main_sina", "futures_inventory_em",
            "futures_inventory_99", "futures_shfe_warehouse_receipt",
            "futures_warehouse_receipt_czce", "futures_gfex_warehouse_receipt",
        ):
            setattr(mock, name, MagicMock(return_value=empty))
        return mock

    def _make_main_sina_df(self, price=103890.0):
        """构造一个 2 行的主力连续接口响应(开盘 103890, 收盘 104340)"""
        import pandas as pd
        return pd.DataFrame({
            "日期": [date(2026, 7, 13), date(2026, 7, 14)],
            "开盘价": [price, price + 100.0],
            "最高价": [price + 500.0, price + 660.0],
            "最低价": [price - 200.0, price - 320.0],
            "收盘价": [price + 200.0, price + 450.0],
            "动态结算价": [price + 150.0, price + 200.0],
            "成交量": [80000, 74063],
            "持仓量": [175000, 177778],
        })

    def test_quotes_fallback_when_specific_contract_empty(
        self, akshare_mod, mock_ak_empty
    ):
        """具体合约 CU2501.SHF 无行情 → 回退 CU0 → 返数据 + used_continuous_fallback=True"""
        provider = akshare_mod.AkshareFuturesProvider()
        provider._ak = mock_ak_empty
        # 让 futures_main_sina 返非空
        mock_ak_empty.futures_main_sina.return_value = self._make_main_sina_df()

        result = asyncio.run(provider.get_commodity_quotes("CU2501.SHF"))

        assert result is not None
        assert result["full_symbol"] == "CU2501.SHF"  # 保留原 full_symbol
        assert result["current_price"] == 103890.0 + 450.0  # 主力连续最新收盘
        assert result["used_continuous_fallback"] is True
        assert "continuous_fallback" in result["data_source"]
        # 验证 mock 调用:futures_hist_em 失败 → futures_main_sina 成功
        mock_ak_empty.futures_hist_em.assert_called_once()
        mock_ak_empty.futures_main_sina.assert_called_once_with(symbol="CU0")

    def test_quotes_no_fallback_when_specific_contract_has_data(
        self, akshare_mod, mock_ak_empty
    ):
        """具体合约有行情 → 不走 fallback → used_continuous_fallback=False"""
        provider = akshare_mod.AkshareFuturesProvider()
        provider._ak = mock_ak_empty
        # 让 futures_hist_em 返非空(具体合约成功)
        contract_df = self._make_main_sina_df(price=50000.0)
        contract_df = provider._normalize_hist_em_df(contract_df)
        mock_ak_empty.futures_hist_em.return_value = contract_df

        result = asyncio.run(provider.get_commodity_quotes("CU2501.SHF"))

        assert result is not None
        assert result["used_continuous_fallback"] is False
        assert result["data_source"] == "akshare_futures"
        # futures_main_sina 不应被调用
        mock_ak_empty.futures_main_sina.assert_not_called()

    def test_quotes_returns_none_when_both_fail(
        self, akshare_mod, mock_ak_empty
    ):
        """具体合约 + 主力连续都无数据 → 返 None"""
        provider = akshare_mod.AkshareFuturesProvider()
        provider._ak = mock_ak_empty
        # 默认都返空

        result = asyncio.run(provider.get_commodity_quotes("ZZ9999.SHF"))

        assert result is None

    def test_historical_fallback_when_specific_contract_empty(
        self, akshare_mod, mock_ak_empty
    ):
        """具体合约历史 K 线无数据 → 回退主力连续 + 标记 data_source_note"""
        provider = akshare_mod.AkshareFuturesProvider()
        provider._ak = mock_ak_empty
        mock_ak_empty.futures_main_sina.return_value = self._make_main_sina_df()

        df = asyncio.run(
            provider.get_historical_data(
                "CU2501.SHF",
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 14),
            )
        )

        assert df is not None
        assert not df.empty
        assert df.attrs.get("data_source_note") == "continuous_fallback"
        # 主力连续应被调
        mock_ak_empty.futures_main_sina.assert_called_once_with(symbol="CU0")

    def test_try_continuous_fallback_success(self, akshare_mod, mock_ak_empty):
        """_try_continuous_fallback 成功路径"""
        provider = akshare_mod.AkshareFuturesProvider()
        provider._ak = mock_ak_empty
        mock_ak_empty.futures_main_sina.return_value = self._make_main_sina_df()

        df = asyncio.run(provider._try_continuous_fallback("CU2501.SHF"))

        assert df is not None
        assert not df.empty
        mock_ak_empty.futures_main_sina.assert_called_once_with(symbol="CU0")

    def test_try_continuous_fallback_returns_none_when_empty(
        self, akshare_mod, mock_ak_empty
    ):
        """_try_continuous_fallback 失败时返 None"""
        provider = akshare_mod.AkshareFuturesProvider()
        provider._ak = mock_ak_empty
        # 默认空

        df = asyncio.run(provider._try_continuous_fallback("ZZ9999.SHF"))

        assert df is None

    def test_try_continuous_fallback_uses_underlying_symbol(
        self, akshare_mod, mock_ak_empty
    ):
        """_try_continuous_fallback 正确提取 underlying(CU→CU0)"""
        provider = akshare_mod.AkshareFuturesProvider()
        provider._ak = mock_ak_empty
        mock_ak_empty.futures_main_sina.return_value = self._make_main_sina_df()

        asyncio.run(provider._try_continuous_fallback("RB2510.DCE"))

        mock_ak_empty.futures_main_sina.assert_called_once_with(symbol="RB0")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
