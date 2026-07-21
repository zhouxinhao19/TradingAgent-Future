"""
test_custom_data_adapter.py — 测试自定义数据适配层 (Phase Data Analyst)

测试 parse_custom_data() 将文件解析为结构化摘要并注入 features dict。
使用 tempfile 创建临时 CSV 文件，避免依赖外部文件系统。
"""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from tradingagents.features.custom_data_adapter import parse_custom_data, _format_summaries


class TestParseCustomData:
    def test_empty_file_list(self):
        """空文件列表时返回 parsed=False"""
        result = parse_custom_data(file_paths=[])
        assert result["parsed"] is False
        assert "error" in result
        assert result["file_count"] == 0

    def test_nonexistent_file(self):
        """不存在的文件路径返回 parsed=False"""
        result = parse_custom_data(file_paths=["/tmp/nonexistent_xyz.csv"])
        assert result["parsed"] is False
        assert "error" in result

    def test_valid_csv_file(self):
        """有效 CSV 文件返回 parsed=True 含摘要"""
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8")
        f.write("date,price,volume\n2024-01-01,100.0,1000\n2024-01-02,101.5,1500\n")
        f.close()
        fpath = f.name
        try:
            result = parse_custom_data(file_paths=[fpath])
            assert result["parsed"] is True
            assert result["file_count"] == 1
            assert result["summary_text"] != ""
            assert "price" in result["summary_text"] or "volume" in result["summary_text"]
            assert "文件" in result["summary_text"]
        finally:
            try:
                os.unlink(fpath)
            except PermissionError:
                pass

    def test_multiple_files(self):
        """多个文件合并返回"""
        paths = []
        files = []
        try:
            for content in [
                "a,b\n1,2\n3,4\n",
                "x,y\n5,6\n7,8\n",
            ]:
                f = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8")
                f.write(content)
                f.close()
                paths.append(f.name)
            result = parse_custom_data(file_paths=paths)
            assert result["parsed"] is True
            assert result["file_count"] == 2
            assert "文件 1" in result["summary_text"]
            assert "文件 2" in result["summary_text"]
        finally:
            for p in paths:
                try:
                    os.unlink(p)
                except PermissionError:
                    pass

    def test_with_user_context(self):
        """用户上下文出现在摘要中"""
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8")
        f.write("a,b\n1,2\n")
        f.close()
        fpath = f.name
        try:
            result = parse_custom_data(file_paths=[fpath], user_context="2024 年铜库存周报")
            assert result["user_context"] == "2024 年铜库存周报"
            assert "2024 年铜库存周报" in result["summary_text"]
        finally:
            try:
                os.unlink(fpath)
            except PermissionError:
                pass

    def test_summary_truncation(self):
        """摘要截断到 max_summary_chars"""
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8")
        f.write("a,b\n" + "\n".join(f"{i},{i+1}" for i in range(1000)))
        f.close()
        fpath = f.name
        try:
            result = parse_custom_data(file_paths=[fpath], max_summary_chars=100)
            assert len(result["summary_text"]) <= 120  # 略超截断长度（含 ... 后缀）
            assert result["summary_text"].endswith("...(摘要已截断)")
        finally:
            try:
                os.unlink(fpath)
            except PermissionError:
                pass

    def test_format_summaries_empty(self):
        """空摘要列表返回基本信息"""
        text = _format_summaries([], file_names=[], user_context="")
        assert "自定义数据文件摘要" in text
        assert "文件数: 0" in text

    def test_format_summaries_with_data(self):
        """格式化包含 overview、columns、stats 的摘要"""
        summaries = [{
            "type": "tabular",
            "overview": {"rows": 100, "columns": 5, "missing_cells": 0, "missing_ratio": 0.0},
            "columns": [{"name": "date"}, {"name": "price"}, {"name": "volume"}],
            "date_range": {"min": "2024-01-01", "max": "2024-12-31"},
            "statistics": {
                "price": {"mean": 100.0, "std": 10.0, "min": 80.0, "max": 120.0},
                "volume": {"mean": 5000, "std": 1000, "min": 3000, "max": 7000},
            },
            "warnings": [],
            "sample": [{"date": "2024-01-01", "price": 100.0}],
        }]
        text = _format_summaries(summaries, file_names=["data.csv"], user_context="测试数据")
        assert "测试数据" in text
        assert "data.csv" in text
        assert "100" in text  # rows
        assert "price" in text  # column name
        assert "2024-01-01" in text  # date range
        assert "mean=100.0" in text  # stats


class TestBuildCustomDataContext:
    """测试 _base.py 的 build_custom_data_context 函数"""

    def test_no_custom_data(self):
        """features 无 custom_data 时返回空字符串"""
        from tradingagents.agents.analysts.commodity._base import build_custom_data_context
        text = build_custom_data_context({})
        assert text == ""

    def test_unparsed_custom_data(self):
        """parsed=False 时返回空字符串"""
        from tradingagents.agents.analysts.commodity._base import build_custom_data_context
        text = build_custom_data_context({"custom_data": {"parsed": False}})
        assert text == ""

    def test_with_summary(self):
        """旧摘要无结构化当前值时保留摘要并追加未知时点护栏。"""
        from tradingagents.agents.analysts.commodity._base import build_custom_data_context
        text = build_custom_data_context({
            "custom_data": {
                "parsed": True,
                "summary_text": "这是一个测试摘要",
            }
        })
        assert "这是一个测试摘要" in text
        assert "摘要未提供可验证的当前时点值" in text
        assert "不得推断当前趋势" in text
        assert text.endswith("\n")

    def test_historical_series_forbids_current_trend_inference(self):
        from tradingagents.agents.analysts.commodity._base import build_custom_data_context

        text = build_custom_data_context({
            "custom_data": {
                "parsed": True,
                "summary_text": "库存均值=100，最大值=160",
                "raw_summaries": [{
                    "time_columns": ["date"],
                    "date_range": {"min": "2020-01-01", "max": "2024-12-31"},
                    "statistics": {"inventory": {"mean": 100, "max": 160}},
                    "sample": [{"date": "2020-01-01", "inventory": 120}],
                }],
            }
        })

        assert "无法获取当前时点数值，无法判断趋势" in text
        assert "只能引用历史均值、极值、分位数和样本区间" in text
        assert "禁止据此声称当前去库/补库" in text
        assert "库存均值=100" in text

    def test_non_temporal_summary_does_not_claim_current_value(self):
        from tradingagents.agents.analysts.commodity._base import build_custom_data_context

        text = build_custom_data_context({
            "custom_data": {
                "parsed": True,
                "summary_text": "品类分布统计",
                "raw_summaries": [{"statistics": {"count": {"mean": 3}}}],
            }
        })

        assert "摘要未提供可验证的当前时点值" in text
        assert "品类分布统计" in text

    def test_verified_current_observation_allows_only_as_of_value(self):
        from tradingagents.agents.analysts.commodity._base import build_custom_data_context

        text = build_custom_data_context({
            "custom_data": {
                "parsed": True,
                "summary_text": "当前观测库存=88",
                "raw_summaries": [{
                    "time_columns": ["date"],
                    "latest_observation": {"inventory": 88},
                    "as_of": "2026-07-20",
                }],
            }
        })

        assert "带 as_of 的 latest_observation/current_value" in text
        assert "不得把全局统计或样本行冒充当前值" in text


# =============================================================================
# Phase 自定义数据升级: parse_custom_data_async + feature_dict 三态分支
# =============================================================================


def _mock_llm_content(content_str: str):
    """构造 MagicMock LLM: ainvoke 是真正的 async 函数,invoke 同步返回。"""
    from unittest.mock import AsyncMock, MagicMock

    class _Msg:
        def __init__(self, c):
            self.content = c

    mock = MagicMock()
    mock.invoke = MagicMock(return_value=_Msg(content_str))
    mock.ainvoke = AsyncMock(return_value=_Msg(content_str))
    return mock


class TestParseCustomDataAsync:
    """parse_custom_data_async 的 LLM 集成与降级路径。"""

    def test_llm_returns_valid_feature_dict(self):
        """LLM 返回合规 JSON → feature_dict 填充标准 schema。"""
        import asyncio
        from tradingagents.features.custom_data_adapter import parse_custom_data_async

        # 写一个含价格时序的 CSV
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        )
        rows = ["date,inventory\n"]
        for i in range(30):
            rows.append(f"2024-{i+1:02d}-01,{1000 - i * 5}\n")
        f.write("".join(rows))
        f.close()
        fpath = f.name
        try:
            llm = _mock_llm_content(
                json.dumps({
                    "interpretation_type": "tabular_timeseries",
                    "matched_module": "inventory",
                    "current_observation": {"inventory": 880},
                    "as_of": "2024-12-30",
                    "direction": "bullish",
                    "direction_confidence": 0.7,
                    "reasoning": "库存持续下降,处于自身历史低位",
                    "warning": "",
                }, ensure_ascii=False)
            )
            result = asyncio.run(parse_custom_data_async(
                file_paths=[fpath], llm=llm,
            ))
            assert result["parsed"] is True
            assert result["feature_dict"] is not None
            fd = result["feature_dict"]
            assert fd["_direction"] == "bullish"
            assert fd["_matched_module"] == "inventory"
            assert fd["latest"]["inventory"] == 880.0
            assert fd["latest"]["_as_of"] == "2024-12-30"
            assert fd["snapshot"]["current_value"] == 880.0
            assert fd["snapshot"]["as_of"] == "2024-12-30"
            assert fd["snapshot"]["matched_module"] == "inventory"
            assert fd["quality"]["has_as_of"] is True
            assert len(fd["signals"]) >= 1
        finally:
            try:
                os.unlink(fpath)
            except PermissionError:
                pass

    def test_llm_timeout_returns_feature_dict_none(self):
        """LLM 超时 → feature_dict=None, parsed=True(主流程不受影响)。"""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock
        from tradingagents.features.custom_data_adapter import parse_custom_data_async

        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        )
        f.write("date,price\n2024-01-01,100\n2024-01-02,101\n")
        f.close()
        fpath = f.name
        try:
            llm = MagicMock()

            async def _slow(*args, **kwargs):
                import asyncio as _aio
                await _aio.sleep(5)
                return MagicMock(content="{}")

            llm.ainvoke = _slow
            result = asyncio.run(parse_custom_data_async(
                file_paths=[fpath], llm=llm, llm_timeout_s=0.1,
            ))
            assert result["parsed"] is True
            assert result["feature_dict"] is None
            assert result["summary_text"] != ""
        finally:
            try:
                os.unlink(fpath)
            except PermissionError:
                pass

    def test_llm_invalid_json_returns_feature_dict_none(self):
        """LLM 返回非 JSON → feature_dict=None(主流程降级到老 guardrail)。"""
        import asyncio
        from tradingagents.features.custom_data_adapter import parse_custom_data_async

        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        )
        f.write("date,price\n2024-01-01,100\n2024-01-02,101\n")
        f.close()
        fpath = f.name
        try:
            llm = _mock_llm_content("not a valid json response")
            result = asyncio.run(parse_custom_data_async(
                file_paths=[fpath], llm=llm,
            ))
            assert result["parsed"] is True
            # LLM 解析失败等同于 LLM 不可用,降级到无 feature_dict
            assert result["feature_dict"] is None
            assert result["summary_text"] != ""
        finally:
            try:
                os.unlink(fpath)
            except PermissionError:
                pass

    def test_llm_none_falls_back_to_sync(self):
        """llm=None 时 feature_dict=None 但 summary_text 正常生成。"""
        import asyncio
        from tradingagents.features.custom_data_adapter import parse_custom_data_async

        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        )
        f.write("date,price\n2024-01-01,100\n")
        f.close()
        fpath = f.name
        try:
            result = asyncio.run(parse_custom_data_async(
                file_paths=[fpath], llm=None,
            ))
            assert result["parsed"] is True
            assert result["feature_dict"] is None
            assert result["summary_text"] != ""
            assert result.get("_llm_skipped") is True
        finally:
            try:
                os.unlink(fpath)
            except PermissionError:
                pass

    def test_sync_parse_data_includes_feature_dict_none(self):
        """老同步 parse_custom_data 返回值含 feature_dict=None(向后兼容字段)。"""
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        )
        f.write("date,price\n2024-01-01,100\n")
        f.close()
        fpath = f.name
        try:
            result = parse_custom_data(file_paths=[fpath])
            assert result["parsed"] is True
            assert "feature_dict" in result
            assert result["feature_dict"] is None
        finally:
            try:
                os.unlink(fpath)
            except PermissionError:
                pass


class TestBuildCustomDataContextFeatureDict:
    """build_custom_data_context 在 feature_dict 存在时的"低权重 + 交叉验证"新分支。"""

    def _make_features(self, fd):
        return {"custom_data": {"parsed": True, "feature_dict": fd}}

    def test_feature_dict_uses_new_prompt(self):
        """feature_dict 存在 → 注入文本包含「低权重参考」+「交叉验证」。"""
        from tradingagents.agents.analysts.commodity._base import build_custom_data_context

        fd = {
            "latest": {"inventory": 880.0, "_as_of": "2024-12-30"},
            "snapshot": {
                "current_value": 880.0,
                "current_value_label": "inventory",
                "as_of": "2024-12-30",
                "matched_module": "inventory",
                "self_pctl_180d": 15.0,
            },
            "signals": ["用户上传: 库存=880 处于自身 15% 分位(bullish)"],
            "quality": {"has_as_of": True, "reason": ""},
            "_direction": "bullish",
        }
        text = build_custom_data_context(self._make_features(fd))
        assert "低权重参考" in text
        assert "交叉验证" in text
        assert "[USER_DATA_CONFLICT]" in text
        assert "用户提供当前观测 [inventory]=880" in text
        assert "自身历史分位(180d)=15%" in text

    def test_feature_dict_without_as_of_warns_background_only(self):
        """无 as_of → 提示「仅可作背景,不可作当前趋势依据」。"""
        from tradingagents.agents.analysts.commodity._base import build_custom_data_context

        fd = {
            "latest": {"inventory": 880.0},
            "snapshot": {
                "current_value": 880.0,
                "current_value_label": "inventory",
                "matched_module": "inventory",
                "self_pctl_180d": 50.0,
            },
            "signals": [],
            "quality": {"has_as_of": False, "reason": "缺少 as_of"},
            "_direction": "neutral",
        }
        text = build_custom_data_context(self._make_features(fd))
        assert "缺少 as_of" in text
        assert "仅可作背景" in text

    def test_legacy_branch_preserved_without_feature_dict(self):
        """无 feature_dict 但有 raw_summaries → 走老 guardrail(无结构化当前值)。"""
        from tradingagents.agents.analysts.commodity._base import build_custom_data_context

        features = {
            "custom_data": {
                "parsed": True,
                "summary_text": "老格式摘要",
                "raw_summaries": [{
                    "time_columns": ["date"],
                    "statistics": {"price": {"mean": 100}},
                }],
            }
        }
        text = build_custom_data_context(features)
        # 走老 guardrail:historical_series 分支
        assert "无法获取当前时点数值" in text
        assert "禁止据此声称当前去库/补库" in text

    def test_legacy_branch_no_feature_dict_no_raw_summaries_uses_summary_only(self):
        """无 feature_dict 无 raw_summaries 但有 summary_text → 老第三档护栏。"""
        from tradingagents.agents.analysts.commodity._base import build_custom_data_context

        features = {
            "custom_data": {
                "parsed": True,
                "summary_text": "纯统计摘要",
            }
        }
        text = build_custom_data_context(features)
        assert "摘要未提供可验证的当前时点值" in text
        assert "不得推断当前趋势" in text

    def test_build_fact_cards_includes_custom_data_card(self):
        """build_fact_cards 在 feature_dict 存在时生成 FACT-CUSTOM 卡片。"""
        from tradingagents.agents.analysts.commodity._base import build_fact_cards

        features = {
            "technical": {},
            "basis": {},
            "inventory": {},
            "positioning": {},
            "term_structure": {},
            "news_sentiment": {},
            "custom_data": {
                "parsed": True,
                "feature_dict": {
                    "snapshot": {
                        "current_value": 880,
                        "current_value_label": "inventory",
                        "as_of": "2024-12-30",
                        "self_pctl_180d": 15.0,
                    },
                    "_direction": "bullish",
                },
            },
        }
        cards = build_fact_cards(features)
        custom_cards = [c for c in cards if c["module"] == "custom_data"]
        assert len(custom_cards) == 1
        c = custom_cards[0]
        assert "用户上传数据" in c["statement"]
        assert c["value"] == 880
        assert c["percentile"] == 15.0
        assert c["direction"] == "bullish"
        assert c["source"] == "features.custom_data"