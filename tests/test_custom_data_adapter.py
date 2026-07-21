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