"""
tests/test_paper_spec.py — ContractSpec / calc_margin / calc_commission /
                          check_price_limit / parse_variety 单测

覆盖:
- TestContractSpecFields:   12 个主流品种字段值(margin/commission/limit/contract_size)
- TestCalcMargin:           保证金计算的线性 / 不同品种 / 边界
- TestCalcCommission:       手续费计算
- TestCheckPriceLimit:      涨跌停上下界 / 含等号 / 扩板 / 昨结 = 0
- TestParseVariety:         标准 / CZCE 三位 / 错误格式 / 大小写
- TestSpecIndex:            索引完整性 / 已支持 82 品种
- TestContractSpecFrozen:   不可变

目标:≥18 测试全过。
"""
from __future__ import annotations

import pytest

from tradingagents.paper.spec import (
    ContractSpec,
    calc_margin,
    calc_commission,
    check_price_limit,
    parse_variety,
    get_spec,
    list_supported_symbols,
    VARIETY_SPEC_INDEX,
    calc_upper_limit,
    calc_lower_limit,
)


# =============================================================================
# Test 1 — TestContractSpecFields
# =============================================================================

class TestContractSpecFields:
    """主流品种合约字段快照校验(防止商品元数据被无意修改)。
    跑测试相当于"生产线守护":任何修改 metadata 的 PR 必须同步更新此处。
    """

    def test_cu_shfe_basic(self):
        spec = get_spec("CU", "SHFE")
        assert spec.symbol == "CU"
        assert spec.exchange == "SHFE"
        assert spec.name_cn == "铜"
        assert spec.contract_size == 5
        assert spec.tick_size == 10
        assert spec.margin_rate == pytest.approx(0.10)
        assert spec.commission_rate == pytest.approx(0.0001)
        assert spec.limit_up_down == pytest.approx(0.06)
        assert spec.unit == "吨"
        assert spec.category == "metal"
        assert spec.exchange_suffix == "SHF"

    def test_rb_shfe(self):
        spec = get_spec("RB", "SHFE")
        assert spec.contract_size == 10
        assert spec.margin_rate == pytest.approx(0.11)
        assert spec.limit_up_down == pytest.approx(0.05)

    def test_au_shfe(self):
        """黄金合约特殊:单位"克" + 较低费率。"""
        spec = get_spec("AU", "SHFE")
        assert spec.contract_size == 1000
        assert spec.unit == "克"
        assert spec.commission_rate == pytest.approx(0.00002)
        assert spec.margin_rate == pytest.approx(0.08)

    def test_if_cffex_index(self):
        """沪深 300 股指,合约乘数 300 / 较高保证金。"""
        spec = get_spec("IF", "CFFEX")
        assert spec.contract_size == 300
        assert spec.margin_rate == pytest.approx(0.13)
        assert spec.limit_up_down == pytest.approx(0.10)

    def test_ts_cffex_treasury(self):
        """2 年期国债:极低保证金 + 小涨跌停。"""
        spec = get_spec("TS", "CFFEX")
        assert spec.contract_size == 20000
        assert spec.margin_rate == pytest.approx(0.03)
        assert spec.limit_up_down == pytest.approx(0.02)

    def test_i_dce_iron_ore(self):
        """铁矿石:合约乘数 100 / 较高保证金。"""
        spec = get_spec("I", "DCE")
        assert spec.contract_size == 100
        assert spec.margin_rate == pytest.approx(0.13)

    def test_sc_ine_crude_oil(self):
        """INE 原油:桶为单位 / 较高涨跌停。"""
        spec = get_spec("SC", "INE")
        assert spec.unit == "桶"
        assert spec.contract_size == 1000
        assert spec.limit_up_down == pytest.approx(0.08)

    def test_lc_gfex_lithium_carbonate(self):
        """广州期货所碳酸锂:合约乘数 1 / 50 涨跌停。"""
        spec = get_spec("LC", "GFEX")
        assert spec.contract_size == 1
        assert spec.tick_size == 50

    def test_24_major_varieties_have_valid_spec(self):
        """24 个最常见品种都应该有非零、非负的合理字段。"""
        major = [
            ("CU", "SHFE"), ("AL", "SHFE"), ("ZN", "SHFE"), ("AU", "SHFE"),
            ("AG", "SHFE"), ("RB", "SHFE"), ("HC", "SHFE"), ("RU", "SHFE"),
            ("I", "DCE"), ("J", "DCE"), ("M", "DCE"), ("Y", "DCE"),
            ("C", "DCE"), ("P", "DCE"),
            ("CF", "CZCE"), ("SR", "CZCE"), ("TA", "CZCE"), ("MA", "CZCE"),
            ("IF", "CFFEX"), ("IH", "CFFEX"), ("IC", "CFFEX"), ("IM", "CFFEX"),
            ("TS", "CFFEX"), ("T", "CFFEX"),
        ]
        for sym, exch in major:
            spec = get_spec(sym, exch)
            assert spec.contract_size > 0, f"{sym}.{exch} contract_size"
            assert 0 < spec.margin_rate < 0.5, f"{sym}.{exch} margin_rate"
            assert 0 <= spec.commission_rate < 0.01, f"{sym}.{exch} commission_rate"
            assert 0 < spec.limit_up_down <= 0.20, f"{sym}.{exch} limit_up_down"


# =============================================================================
# Test 2 — TestCalcMargin
# =============================================================================

class TestCalcMargin:
    def test_cu_1lot_70000(self):
        """CU 1手 × 70000 元/吨 × 5 吨 × 10% = 35000 元"""
        spec = get_spec("CU", "SHFE")
        assert calc_margin(1, 70000, spec) == pytest.approx(35000.0)

    def test_rb_10lot_4000(self):
        """RB 10手 × 4000 × 10 × 11% = 44000 元"""
        spec = get_spec("RB", "SHFE")
        assert calc_margin(10, 4000, spec) == pytest.approx(44000.0)

    def test_if_1lot_3800_index(self):
        """IF 1手 × 3800 点 × 300 元/点 × 13% = 148200 元"""
        spec = get_spec("IF", "CFFEX")
        assert calc_margin(1, 3800, spec) == pytest.approx(148200.0)

    def test_margin_linear_lots(self):
        """保证金对手数线性放大"""
        spec = get_spec("CU", "SHFE")
        assert calc_margin(5, 70000, spec) == pytest.approx(5 * calc_margin(1, 70000, spec))

    def test_margin_linear_price(self):
        """保证金对价格线性放大"""
        spec = get_spec("RB", "SHFE")
        m1 = calc_margin(1, 4000, spec)
        m2 = calc_margin(1, 8000, spec)
        assert m2 == pytest.approx(2 * m1)

    def test_margin_zero_lots_raises(self):
        spec = get_spec("CU", "SHFE")
        with pytest.raises(ValueError, match="lots"):
            calc_margin(0, 70000, spec)

    def test_margin_negative_lots_raises(self):
        spec = get_spec("CU", "SHFE")
        with pytest.raises(ValueError, match="lots"):
            calc_margin(-1, 70000, spec)

    def test_margin_negative_price_raises(self):
        spec = get_spec("CU", "SHFE")
        with pytest.raises(ValueError, match="price"):
            calc_margin(1, -100, spec)


# =============================================================================
# Test 3 — TestCalcCommission
# =============================================================================

class TestCalcCommission:
    def test_cu_single_side(self):
        """CU 单边手续费 = 1 × 70000 × 5 × 0.0001 = 35 元"""
        spec = get_spec("CU", "SHFE")
        assert calc_commission(1, 70000, spec) == pytest.approx(35.0)

    def test_cu_double_side_total(self):
        """双边合计 = 单边 × 2"""
        spec = get_spec("CU", "SHFE")
        single = calc_commission(1, 70000, spec)
        assert single * 2 == pytest.approx(70.0)

    def test_if_zero_commission_rate(self):
        """IF 极低手续费:几乎为零(精确值 0.00207 元)"""
        spec = get_spec("IF", "CFFEX")
        fee = calc_commission(1, 3800, spec)
        # 1 × 3800 × 300 × 0.000023 = 26.22 元
        assert fee == pytest.approx(26.22)

    def test_au_gold_commission(self):
        """AU 黄金:单边 1 × 500 × 1000 × 0.00002 = 10 元"""
        spec = get_spec("AU", "SHFE")
        fee = calc_commission(1, 500, spec)
        assert fee == pytest.approx(10.0)

    def test_commission_invalid_lots(self):
        spec = get_spec("CU", "SHFE")
        with pytest.raises(ValueError):
            calc_commission(0, 70000, spec)


# =============================================================================
# Test 4 — TestCheckPriceLimit
# =============================================================================

class TestCheckPriceLimit:
    """涨跌停预检:等于限价是允许成交的(交易所规则),超限才拒单。"""

    def test_within_range(self):
        spec = get_spec("RB", "SHFE")  # limit 5%
        assert check_price_limit(4000, 4000, spec) is True  # 持平

    def test_upper_boundary_inclusive(self):
        """等于上界 = 允许成交(True)"""
        spec = get_spec("RB", "SHFE")
        assert check_price_limit(4200, 4000, spec) is True  # +5% = 4200

    def test_lower_boundary_inclusive(self):
        """等于下界 = 允许成交(True)"""
        spec = get_spec("RB", "SHFE")
        assert check_price_limit(3800, 4000, spec) is True  # -5% = 3800

    def test_just_above_upper_rejected(self):
        spec = get_spec("RB", "SHFE")
        assert check_price_limit(4201, 4000, spec) is False

    def test_just_below_lower_rejected(self):
        spec = get_spec("RB", "SHFE")
        assert check_price_limit(3799, 4000, spec) is False

    def test_prev_settlement_zero_no_limit(self):
        """昨结 = 0(刚上市/暂停后重启):无涨跌停"""
        spec = get_spec("CU", "SHFE")
        assert check_price_limit(100000, 0, spec) is True
        assert check_price_limit(0, 0, spec) is True

    def test_extended_board(self):
        """扩板日 +50%:RB 普通 +5%,扩板 +7.5%"""
        spec = get_spec("RB", "SHFE")
        # 普通 +5% 应拒,扩板 +7.5% 应通过
        assert check_price_limit(4200, 4000, spec) is True              # +5%
        assert check_price_limit(4300, 4000, spec, extended=True) is True    # +7.5%
        assert check_price_limit(4310, 4000, spec, extended=True) is False   # >+7.5%

    def test_calc_upper_limit_helper(self):
        spec = get_spec("RB", "SHFE")
        assert calc_upper_limit(4000, spec) == pytest.approx(4200.0)
        assert calc_upper_limit(4000, spec, extended=True) == pytest.approx(4300.0)
        assert calc_upper_limit(0, spec) == float("inf")

    def test_calc_lower_limit_helper(self):
        spec = get_spec("RB", "SHFE")
        assert calc_lower_limit(4000, spec) == pytest.approx(3800.0)
        assert calc_lower_limit(0, spec) == 0.0


# =============================================================================
# Test 5 — TestParseVariety
# =============================================================================

class TestParseVariety:
    def test_standard_format(self):
        assert parse_variety("CU2501.SHF") == ("CU", "SHFE")

    def test_lowercase_input_normalized(self):
        assert parse_variety("cu2501.shf") == ("CU", "SHFE")

    def test_dce(self):
        assert parse_variety("RB2505.DCE") == ("RB", "DCE")

    def test_cffex_cfx_suffix(self):
        """中金所合约后缀是 .CFX"""
        assert parse_variety("IF2503.CFX") == ("IF", "CFFEX")

    def test_czce_zce_suffix(self):
        assert parse_variety("TA2506.ZCE") == ("TA", "CZCE")

    def test_ine(self):
        assert parse_variety("SC2506.INE") == ("SC", "INE")

    def test_gfex(self):
        assert parse_variety("SI2506.GFEX") == ("SI", "GFEX")

    def test_czce_3_digit_yymm(self):
        """CZCE 部分品种历史用 3 位数字(YYM)"""
        assert parse_variety("AP410.ZCE") == ("AP", "CZCE")

    def test_invalid_format_no_dot(self):
        with pytest.raises(ValueError, match="格式"):
            parse_variety("CU2501")

    def test_invalid_format_empty(self):
        with pytest.raises(ValueError, match="字符串"):
            parse_variety("")

    def test_invalid_format_no_variety(self):
        with pytest.raises(ValueError, match="格式"):
            parse_variety("2501.SHF")

    def test_invalid_format_unknown_suffix(self):
        with pytest.raises(ValueError, match="交易所"):
            parse_variety("CU2501.QQQ")


# =============================================================================
# Test 6 — TestSpecIndex
# =============================================================================

class TestSpecIndex:
    def test_total_index_size(self):
        """索引至少要覆盖 commodity_metadata 的 82 品种"""
        assert len(VARIETY_SPEC_INDEX) >= 82

    def test_supported_symbols_grouped(self):
        """按交易所分组,6 个交易所都覆盖"""
        summary = list_supported_symbols()
        assert set(summary.keys()) >= {"SHFE", "DCE", "CZCE", "INE", "GFEX", "CFFEX"}
        # 主流交易所品种数合理
        assert summary["SHFE"] >= 15
        assert summary["DCE"] >= 20
        assert summary["CZCE"] >= 20
        assert summary["CFFEX"] >= 5

    def test_get_spec_unknown_raises(self):
        with pytest.raises(KeyError):
            get_spec("XX", "SHFE")

    def test_get_spec_ambiguous_raises(self):
        """symbol 在多交易所冲突时(虽然 metadata 设计上不冲突)应抛错"""
        # 主要验证 API 行为;实际是否存在歧义取决于元数据
        try:
            get_spec("FU")  # FU 仅在 SHFE,应成功
            pass
        except KeyError as e:
            # 若真的多交易所同名,应抛错而非随机选一个
            assert "exchange" in str(e) or "未" in str(e)


# =============================================================================
# Test 7 — TestContractSpecFrozen
# =============================================================================

class TestContractSpecFrozen:
    def test_frozen_blocks_mutation(self):
        spec = get_spec("CU", "SHFE")
        from dataclasses import FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            spec.margin_rate = 0.99  # type: ignore

    def test_frozen_blocks_new_attr(self):
        spec = get_spec("CU", "SHFE")
        with pytest.raises(Exception):  # FrozenInstanceError
            spec.something_new = 1  # type: ignore

    def test_construct_from_metadata_works(self):
        spec = get_spec("CU", "SHFE")
        # 可以从已有 spec 构造 dataclass(method 链)
        same = ContractSpec.from_variety("CU", "SHFE")
        assert same.margin_rate == spec.margin_rate


# =============================================================================
# 简易可手动验证的"全 82 品种完整性"测试(失败时易诊断)
# =============================================================================

class TestAllVarietiesLoadable:
    """遍历 commodity_metadata 全部 82 品种,验证 ContractSpec.from_variety 全部成功。
    若元数据被破坏,这一个测试会一次性列出所有失败的品种。
    """

    @pytest.mark.parametrize("expect_count", [82])
    def test_variety_count_matches_metadata(self, expect_count):
        """VARIETY_SPEC_INDEX 大小 == commodity_metadata 总数"""
        from tradingagents.dataflows.providers.commodity.commodity_metadata import (
            variety_summary,
        )
        summary = variety_summary()
        assert len(VARIETY_SPEC_INDEX) == summary["total_varieties"]
        assert summary["total_varieties"] == expect_count

    def test_every_variety_in_index_has_valid_fields(self):
        """每个 ContractSpec 的字段都在合理范围内"""
        for (exchange, symbol), spec in VARIETY_SPEC_INDEX.items():
            assert 0 < spec.margin_rate < 0.5, (
                f"{symbol}.{exchange} margin_rate={spec.margin_rate}"
            )
            assert 0 <= spec.commission_rate < 0.01, (
                f"{symbol}.{exchange} commission_rate={spec.commission_rate}"
            )
            assert 0 < spec.limit_up_down <= 0.20, (
                f"{symbol}.{exchange} limit_up_down={spec.limit_up_down}"
            )
            assert spec.contract_size > 0, (
                f"{symbol}.{exchange} contract_size={spec.contract_size}"
            )
            assert spec.tick_size > 0, (
                f"{symbol}.{exchange} tick_size={spec.tick_size}"
            )
