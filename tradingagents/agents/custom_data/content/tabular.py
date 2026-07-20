"""
tabular.py — TabularContent (表格/结构化文件)

对应 .xlsx / .xls / .csv 等表格文件，核心是 pd.DataFrame。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .base import Content


class TabularContent(Content):
    """表格类文件的 Content 表示。

    Attributes:
        type_name: 固定为 "tabular"
        dataframe: 原始 pd.DataFrame
        columns: 列名列表
        shape: (行数, 列数)
        dtypes: {列名: 类型名} 映射
        numeric_columns: 数值列列表
        missing_summary: 缺失值统计，如 {"col_a": 3, "col_b": 0}
    """

    type_name: str = "tabular"
    dataframe: pd.DataFrame = pd.DataFrame()
    columns: List[str] = []
    shape: Tuple[int, int] = (0, 0)
    dtypes: Dict[str, str] = {}
    numeric_columns: List[str] = []
    missing_summary: Dict[str, int] = {}

    def __init__(
        self,
        dataframe: pd.DataFrame,
        source_path: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.dataframe = dataframe
        self.source_path = source_path
        self.metadata = {
            "filename": source_path.split("/")[-1].split("\\")[-1],
            "ext": source_path.split(".")[-1] if "." in source_path else "",
            "size": len(dataframe),
        }
        if metadata:
            self.metadata.update(metadata)

        self.columns = list(dataframe.columns) if not dataframe.empty else []
        self.shape = dataframe.shape
        self.dtypes = {col: str(dtype) for col, dtype in dataframe.dtypes.items()}
        self.numeric_columns = list(dataframe.select_dtypes(include="number").columns)
        self.missing_summary = {
            col: int(dataframe[col].isna().sum())
            for col in dataframe.columns
        }

    def validate(self) -> bool:
        """检查 DataFrame 是否非空且至少有一列。"""
        return not self.dataframe.empty and len(self.dataframe.columns) > 0

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "columns": self.columns,
            "shape": list(self.shape),
            "dtypes": self.dtypes,
            "numeric_columns": self.numeric_columns,
            "missing_summary": self.missing_summary,
        })
        return base


__all__ = ["TabularContent"]
