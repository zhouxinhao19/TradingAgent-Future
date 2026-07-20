"""
测试 readers 模块: ReaderRegistry + TabularReader
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tradingagents.agents.custom_data.readers import ReaderRegistry, TabularReader, UnsupportedFormatError


class TestReaderRegistry:
    def test_register_and_read_csv(self):
        """注册 .csv → TabularReader，读取 CSV 返回 TabularContent"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write("a,b,c\n1,2,3\n4,5,6\n")
            f.flush()
            fpath = f.name
        try:
            content = ReaderRegistry.read(fpath)
            assert content.type_name == "tabular"
            assert content.shape == (2, 3)
            assert content.columns == ["a", "b", "c"]
            assert content.validate() is True
        finally:
            os.unlink(fpath)

    def test_unsupported_extension(self):
        """未注册的扩展名抛出 UnsupportedFormatError"""
        with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
            fpath = f.name
        try:
            with pytest.raises(UnsupportedFormatError):
                ReaderRegistry.read(fpath)
        finally:
            os.unlink(fpath)

    def test_file_not_found(self):
        """不存在的文件抛出 FileNotFoundError"""
        with pytest.raises(FileNotFoundError):
            ReaderRegistry.read("/tmp/nonexistent_file_12345.csv")

    def test_supported_extensions(self):
        """supported_extensions 返回已注册的扩展名列表"""
        exts = ReaderRegistry.supported_extensions()
        assert ".csv" in exts
        assert ".xlsx" in exts
        assert ".xls" in exts

    def test_clear_registry(self):
        """clear() 清空注册表"""
        ReaderRegistry.clear()
        assert ReaderRegistry.supported_extensions() == []
        # 重新注册
        ReaderRegistry.register(".csv", TabularReader)


class TestTabularReader:
    def test_read_csv_with_gbk(self):
        """读取 GBK 编码的 CSV"""
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".csv", delete=False) as f:
            # GBK 编码: "日期,价格\n2024-01-01,100"
            f.write("日期,价格\n2024-01-01,100\n2024-01-02,200".encode("gbk"))
            f.flush()
            fpath = f.name
        try:
            content = TabularReader().read(fpath)
            assert content.shape == (2, 2)
            assert "日期" in content.columns
        finally:
            os.unlink(fpath)

    def test_read_csv_with_tab_sep(self):
        """读取 Tab 分隔的 CSV"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write("a\tb\tc\n1\t2\t3\n")
            f.flush()
            fpath = f.name
        try:
            content = TabularReader().read(fpath)
            assert content.shape == (1, 3)
        finally:
            os.unlink(fpath)

    def test_read_xlsx(self):
        """读取 .xlsx 返回 TabularContent —— mock pandas"""
        df_mock = pd.DataFrame({"x": [1, 2], "y": [3, 4]})
        from pathlib import Path
        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "suffix", ".xlsx", create=True):
                with patch("pandas.ExcelFile") as mock_xl_cls:
                    mock_xl = MagicMock()
                    mock_xl.sheet_names = ["Sheet1"]
                    mock_xl_cls.return_value = mock_xl
                    with patch("pandas.read_excel", return_value=df_mock):
                        from tradingagents.agents.custom_data.readers.tabular_reader import TabularReader
                        content = TabularReader().read("/tmp/test.xlsx")
                        assert content.shape == (2, 2)
                        assert content.columns == ["x", "y"]

    def test_read_excel_multiple_sheets(self):
        """多 sheet Excel 只读第一个"""
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            fpath = f.name
        try:
            df_mock = pd.DataFrame({"sheet1_col": [1]})
            with patch("pandas.ExcelFile") as mock_xl:
                mock_xl.return_value.sheet_names = ["Sheet1", "Sheet2"]
                with patch("pandas.read_excel", return_value=df_mock):
                    content = TabularReader().read(fpath)
                    assert content.shape == (1, 1)
        finally:
            os.unlink(fpath)

    def test_empty_file(self):
        """空文件返回空的 TabularContent"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write("a,b,c\n")
            f.flush()
            fpath = f.name
        try:
            content = TabularReader().read(fpath)
            assert content.shape == (0, 3)
            assert content.validate() is False
        finally:
            os.unlink(fpath)


class TestTabularContent:
    def test_to_dict(self):
        """TabularContent.to_dict() 包含元数据"""
        df = pd.DataFrame({"a": [1, 2, 3], "b": [4.0, 5.0, 6.0]})
        from tradingagents.agents.custom_data.content.tabular import TabularContent

        tc = TabularContent(dataframe=df, source_path="/tmp/test.csv")
        d = tc.to_dict()
        assert d["type_name"] == "tabular"
        assert d["columns"] == ["a", "b"]
        assert d["shape"] == [3, 2]
        assert "dtypes" in d
        assert "numeric_columns" in d
        assert "missing_summary" in d

    def test_missing_data(self):
        """含缺失值的 TabularContent 正确统计"""
        df = pd.DataFrame({"a": [1, None, 3], "b": [None, None, 3.0]})
        from tradingagents.agents.custom_data.content.tabular import TabularContent

        tc = TabularContent(dataframe=df)
        assert tc.missing_summary["a"] == 1
        assert tc.missing_summary["b"] == 2
