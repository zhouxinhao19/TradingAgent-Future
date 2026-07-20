"""
tabular_reader.py — TabularReader: .xlsx / .xls / .csv → TabularContent

依赖 pandas，如果 pandas 不可用则抛出 ImportError。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from tradingagents.agents.custom_data.content.tabular import TabularContent
from tradingagents.utils.logging_init import get_logger

logger = get_logger("default")

# 自动检测行数上限：超过此值时仅读取前 N 行 + 采样尾部，避免 OOM
_MAX_ROWS_AUTO = 500_000
_SAMPLE_TAIL = 1_000


class TabularReader:
    """表格文件阅读器。支持 .xlsx / .xls / .csv。"""

    def read(self, file_path: str) -> TabularContent:
        """读取表格文件，返回 TabularContent。

        Args:
            file_path: 文件绝对路径

        Returns:
            TabularContent 实例

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: 不支持的文件类型
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        ext = path.suffix.lower()
        logger.info(f"TabularReader: 读取 {file_path} (ext={ext})")

        # 根据扩展名选择读取方法
        if ext == ".csv":
            df = self._read_csv(file_path)
        elif ext in (".xlsx", ".xls"):
            df = self._read_excel(file_path)
        else:
            raise ValueError(f"TabularReader 不支持 {ext}，支持 .xlsx/.xls/.csv")

        # 超大文件处理
        if len(df) > _MAX_ROWS_AUTO:
            logger.warning(f"TabularReader: 文件过大 ({len(df)} 行)，截取前 {_MAX_ROWS_AUTO} 行")
            df = pd.concat([
                df.head(_MAX_ROWS_AUTO),
                df.tail(_SAMPLE_TAIL),
            ]).drop_duplicates().reset_index(drop=True)

        return TabularContent(dataframe=df, source_path=file_path)

    def _read_csv(self, file_path: str) -> pd.DataFrame:
        """读取 CSV 文件，自动探测编码和分隔符。"""
        # 尝试常见编码
        encodings = ["utf-8", "gbk", "gb2312", "gb18030", "latin-1"]
        for enc in encodings:
            try:
                # 先读少量行检测分隔符
                sample = pd.read_csv(file_path, nrows=5, encoding=enc)
                sep = ","
                if sample.shape[1] == 1:
                    # 可能不是逗号分隔，尝试常见 sep
                    for s in ["\t", ";", "|", " "]:
                        try:
                            sample2 = pd.read_csv(file_path, nrows=5, encoding=enc, sep=s)
                            if sample2.shape[1] > 1:
                                sep = s
                                break
                        except Exception:
                            continue
                return pd.read_csv(file_path, encoding=enc, sep=sep, low_memory=False)
            except (UnicodeDecodeError, pd.errors.ParserError):
                continue
        # fallback: latin-1 能读所有字节但不一定正确
        logger.warning(f"TabularReader: 编码检测失败，使用 latin-1 fallback")
        return pd.read_csv(file_path, encoding="latin-1", low_memory=False)

    def _read_excel(self, file_path: str) -> pd.DataFrame:
        """读取 Excel 文件。只读第一个 sheet。"""
        # pandas 3.x 不再支持空文件自动推断引擎，所有异常兜底走 empty DataFrame
        try:
            xl = pd.ExcelFile(file_path)
            sheet_name = xl.sheet_names[0]
            if len(xl.sheet_names) > 1:
                logger.info(f"TabularReader: Excel 含 {len(xl.sheet_names)} 个 sheet，仅读取第一个: {sheet_name}")
            return pd.read_excel(file_path, sheet_name=sheet_name)
        except Exception as e:
            logger.warning(f"TabularReader: 读取 Excel 失败 ({e})，返回空 DataFrame")
            return pd.DataFrame()


__all__ = ["TabularReader"]
