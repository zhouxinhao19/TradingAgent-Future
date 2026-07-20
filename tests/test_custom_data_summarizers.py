"""
测试 summarizers 模块: TabularSummarizer
"""

import pandas as pd
import pytest

from tradingagents.agents.custom_data.content.tabular import TabularContent
from tradingagents.agents.custom_data.summarizers import TabularSummarizer


class TestTabularSummarizer:
    def test_basic_summary(self):
        """TabularSummarizer 生成基本概要"""
        df = pd.DataFrame({
            "date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
            "price": [100.0, 101.5, 99.8],
            "volume": [1000, 1500, 1200],
        })
        tc = TabularContent(dataframe=df)
        summary = TabularSummarizer().summarize(tc)

        assert summary["type"] == "tabular"
        assert summary["overview"]["rows"] == 3
        assert summary["overview"]["columns"] == 3
        assert summary["overview"]["missing_cells"] == 0

        # 列信息
        assert len(summary["columns"]) == 3

        # 统计信息
        assert "statistics" in summary
        assert "price" in summary["statistics"]
        assert summary["statistics"]["price"]["mean"] == pytest.approx(100.4333, rel=1e-3)

        # 时间列自动识别
        assert "date" in summary.get("time_columns", [])
        assert summary["date_range"]["min"] is not None

        # 样本数据
        assert len(summary["sample"]) == 3

    def test_missing_values(self):
        """含缺失值的数据"""
        df = pd.DataFrame({"a": [1.0, None, 3.0], "b": [None, 2.0, None]})
        tc = TabularContent(dataframe=df)
        summary = TabularSummarizer().summarize(tc)

        assert summary["overview"]["missing_cells"] == 3
        assert summary["overview"]["missing_ratio"] > 0

    def test_large_dataset(self):
        """大数据集只算统计"""
        df = pd.DataFrame({"x": range(1000), "y": [float(i * 2) for i in range(1000)]})
        tc = TabularContent(dataframe=df)
        summary = TabularSummarizer().summarize(tc)

        assert summary["overview"]["rows"] == 1000
        assert "x" in summary["statistics"]
        assert summary["statistics"]["x"]["min"] == 0.0
        assert summary["statistics"]["x"]["max"] == 999.0

    def test_empty_dataframe(self):
        """空 DataFrame"""
        df = pd.DataFrame()
        tc = TabularContent(dataframe=df)
        summary = TabularSummarizer().summarize(tc)

        assert summary["overview"]["rows"] == 0
        assert summary["overview"]["columns"] == 0

    def test_string_column(self):
        """字符串列不产生统计"""
        df = pd.DataFrame({"name": ["Alice", "Bob", "Charlie"], "score": [90, 85, 95]})
        tc = TabularContent(dataframe=df)
        summary = TabularSummarizer().summarize(tc)

        assert "name" not in summary.get("statistics", {})
        assert "score" in summary.get("statistics", {})

    def test_date_column_inference(self):
        """时间列自动识别"""
        df = pd.DataFrame({
            "date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
            "value": [1.0, 2.0],
        })
        tc = TabularContent(dataframe=df)
        summary = TabularSummarizer().summarize(tc)

        assert "date" in summary.get("time_columns", [])
