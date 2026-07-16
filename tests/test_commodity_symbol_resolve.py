"""品种代码 → 主力连续合约自动解析回归测试。

覆盖:
  - resolve_variety_to_symbol()   commodity_metadata.py
  - _resolve_input_symbol()       analysis.py (API 入口解析)
"""

import pytest

from tradingagents.dataflows.providers.commodity.commodity_metadata import (
    resolve_variety_to_symbol,
)


class TestResolveVarietyToSymbol:
    """测试 resolve_variety_to_symbol() — 纯品种→合约解析。"""

    @pytest.mark.parametrize(
        "variety, expected_symbol, expected_name, expected_exchange, expected_category",
        [
            ("RB", "RB.SHF", "螺纹钢", "SHFE", "metal"),
            ("CU", "CU.SHF", "铜", "SHFE", "metal"),
            ("SC", "SC.INE", "原油", "INE", "energy"),
            ("M", "M.DCE", "豆粕", "DCE", "agricultural"),
            ("TA", "TA.ZCE", "精对苯二甲酸(PTA)", "CZCE", "chemical"),
            ("SI", "SI.GFEX", "工业硅", "GFEX", "metal"),
            ("IF", "IF.CFX", "沪深300股指", "CFFEX", "financial"),
        ],
    )
    def test_resolve_standard_varieties(
        self, variety, expected_symbol, expected_name, expected_exchange, expected_category,
    ):
        result = resolve_variety_to_symbol(variety)
        assert result is not None
        assert result["full_symbol"] == expected_symbol
        assert result["variety_name"] == expected_name
        assert result["exchange"] == expected_exchange
        assert result["category"] == expected_category
        assert "quote_unit" in result

    def test_resolve_unknown_variety_returns_none(self):
        """不存在的品种代码返回 None。"""
        assert resolve_variety_to_symbol("ZZZZ") is None

    def test_resolve_empty_input_returns_none(self):
        """空输入返回 None。"""
        assert resolve_variety_to_symbol("") is None
        assert resolve_variety_to_symbol(None) is None

    def test_resolve_lowercase_variety(self):
        """小写品种代码自动大写。"""
        result = resolve_variety_to_symbol("rb")
        assert result is not None
        assert result["full_symbol"] == "RB.SHF"
        assert result["variety_name"] == "螺纹钢"

    def test_resolve_quote_unit_is_reasonable(self):
        """报价单位格式正确。"""
        result = resolve_variety_to_symbol("RB")
        assert result is not None
        assert result["quote_unit"] == "吨/手"

        result = resolve_variety_to_symbol("AU")
        assert result is not None
        assert result["quote_unit"] == "克/手"


class TestResolveInputSymbol:
    """测试 _resolve_input_symbol() — API 入口智能解析。"""

    def _resolve(self, raw: str):
        """直接导入 _resolve_input_symbol 并调用。"""
        from app.routers.commodity.analysis import _resolve_input_symbol
        return _resolve_input_symbol(raw)

    def test_full_contract_unchanged(self):
        """完整合约格式(RB2501.SHF) → 返回 None,原样使用。"""
        result = self._resolve("RB2501.SHF")
        assert result is None

    def test_full_contract_dce(self):
        """完整合约格式 DCE。"""
        result = self._resolve("M2505.DCE")
        assert result is None

    def test_bare_exchange_symbol_unchanged(self):
        """带交易所无月份(RB.SHF) → 返回 None,provider 自动走主力连续。"""
        result = self._resolve("RB.SHF")
        assert result is None

    def test_bare_exchange_dce(self):
        """带交易所无月份 DCE。"""
        result = self._resolve("M.DCE")
        assert result is None

    def test_variety_resolves(self):
        """纯品种代码 → 自动解析。"""
        result = self._resolve("RB")
        assert result is not None
        assert result["full_symbol"] == "RB.SHF"
        assert result["variety_name"] == "螺纹钢"

    def test_variety_copper(self):
        result = self._resolve("CU")
        assert result is not None
        assert result["full_symbol"] == "CU.SHF"

    def test_variety_agri(self):
        """农产品品种。"""
        result = self._resolve("M")
        assert result is not None
        assert result["full_symbol"] == "M.DCE"

    def test_variety_oil(self):
        result = self._resolve("SC")
        assert result is not None
        assert result["full_symbol"] == "SC.INE"

    def test_unknown_variety_returns_none(self):
        """不存在的纯品种 → 返回 None。"""
        result = self._resolve("ZZZZ")
        assert result is None

    def test_lowercase_variety(self):
        """小写品种代码也支持。"""
        result = self._resolve("rb")
        assert result is not None
        assert result["full_symbol"] == "RB.SHF"

    def test_tricky_single_letter_dce(self):
        """单字母品种(A/B/C/I/J/L/M/P/V)正确解析。"""
        for v in ["A", "B", "C", "I", "J", "M", "P", "V"]:
            result = self._resolve(v)
            assert result is not None, f"品种 {v} 应能解析"
            assert result["full_symbol"].endswith(".DCE"), f"{v} 应解析到 DCE"

    def test_tricky_two_letter(self):
        """两字母品种。"""
        result = self._resolve("RB")
        assert result is not None
        assert result["full_symbol"] == "RB.SHF"
