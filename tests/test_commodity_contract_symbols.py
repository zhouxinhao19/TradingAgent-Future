"""商品主力连续与具体月份合约标识回归测试。"""

import pytest

from tradingagents.dataflows.providers.commodity.akshare_futures import AkshareFuturesProvider
from tradingagents.utils.commodity_utils import CommodityMarket, CommodityUtils


@pytest.mark.parametrize(
    "full_symbol",
    ["CU0.SHF", "RB0.DCE", "SC0.INE", "CU2501.SHF", "CU2501.SHFE", "SR409.CZCE"],
)
def test_identify_domestic_continuous_and_contract_symbols(full_symbol):
    assert CommodityUtils.identify_market(full_symbol) is CommodityMarket.CHINA_FUTURES


@pytest.mark.parametrize(
    "full_symbol, expected",
    [
        ("CU0.SHF", "CU0"),
        ("CU2501.SHFE", "CU2501"),
        ("SR409.CZCE", "SR409"),
        ("IF0.CFFEX", "IF0"),
    ],
)
def test_strip_exchange_accepts_short_and_full_exchange_codes(full_symbol, expected):
    assert AkshareFuturesProvider._strip_exchange(full_symbol) == expected


def test_main_continuous_is_not_a_specific_month_contract():
    assert AkshareFuturesProvider._has_yyymm("CU0.SHF") is False
    assert AkshareFuturesProvider._has_yyymm("CU2501.SHF") is True


@pytest.mark.parametrize("full_symbol", ["CU0.SHF", "CU2501.SHFE", "RB0.DCE"])
def test_build_basic_info_supports_continuous_and_exchange_aliases(full_symbol):
    info = AkshareFuturesProvider._build_basic_info(full_symbol)

    assert info is not None
    assert info["is_china_futures"] is True
    assert info["underlying"] in {"CU", "RB"}
    assert info["contract_size"] > 0
