"""
local_cache_adapter.py — 商品期货本地缓存回退适配器 (Phase 3c)

从 CommodityCacheManager 的 Parquet 缓存(或 CSV 旧格式)读取数据,
在 AKShare 在线获取失败时自动回退。

不再强依赖外部参考项目路径; 默认使用本项目 commodity 缓存目录。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import pandas as pd

from tradingagents.utils.logging_init import get_logger

logger = get_logger("default")

# 优先使用 COMMODITY_CACHE_DIR 环境变量, 否则用本项目默认缓存目录
_DEFAULT_CACHE_ROOT = Path(
    os.getenv(
        "COMMODITY_CACHE_DIR",
        Path(__file__).resolve().parents[3] / "data" / "commodity_cache",
    )
)


class CommodityLocalCacheAdapter:
    """从本地 Parquet/CSV 缓存读取数据的适配器。

    读取优先级:
      1) CommodityCacheManager Parquet 缓存 (data_cache/commodity/)
      2) 旧格式 CSV 数据库缓存 (database/{type}/{symbol}/)
      3) 参考项目数据库 (legacy, 仅当显式指定)
    """

    def __init__(self, database_dir: Optional[Path] = None):
        # 主缓存目录: 读 Parquet
        self._parquet_dir = _DEFAULT_CACHE_ROOT
        # 旧 CSV 缓存目录
        self._csv_dir = database_dir or (_DEFAULT_CACHE_ROOT.parent / "database")

    @staticmethod
    def _parse_date_col(df: pd.DataFrame, col: str = "date") -> pd.DataFrame:
        """安全解析日期列,支持 YYYYMMDD 和 YYYY-MM-DD 两种格式。"""
        if col in df.columns:
            s = df[col].astype(str).str.strip()
            parsed = pd.to_datetime(s, format="%Y%m%d", errors="coerce")
            if parsed.isna().all():
                parsed = pd.to_datetime(s, format="%Y-%m-%d", errors="coerce")
            if parsed.isna().any():
                parsed = pd.to_datetime(s, errors="coerce")
            df[col] = parsed
        return df

    # ---- 从 Parquet 缓存读取 (CommodityCacheManager 写出的) ----

    def read_parquet_historical(self, underlying: str, start: str, end: str, market: str) -> Optional[pd.DataFrame]:
        """读取 Parquet 缓存的 K 线数据。"""
        mkt_dir = self._parquet_dir / "historical" / market.upper()
        path = mkt_dir / f"{underlying.upper()}_{start}_{end}.parquet"
        return self._read_parquet(path)

    def read_parquet_basis(self, var: str, start_day: str, end_day: str) -> Optional[pd.DataFrame]:
        """读取 Parquet 缓存的基差数据。"""
        vdir = self._parquet_dir / "basis" / var.upper()
        path = vdir / f"{var.upper()}_{start_day}_{end_day}.parquet"
        return self._read_parquet(path)

    def read_parquet_inventory(self, symbol: str) -> Optional[pd.DataFrame]:
        path = self._parquet_dir / "inventory" / f"{symbol.upper()}_inventory.parquet"
        return self._read_parquet(path)

    def read_parquet_roll_yield(self, key: str) -> Optional[pd.DataFrame]:
        path = self._parquet_dir / "roll_yield" / f"{key}.parquet"
        return self._read_parquet(path)

    @staticmethod
    def _read_parquet(path: Path) -> Optional[pd.DataFrame]:
        if not path.exists():
            return None
        try:
            df = pd.read_parquet(path)
            return df if not df.empty else None
        except Exception as e:
            logger.debug("Parquet 缓存读取失败 %s: %s", path, e)
            return None

    # ---- 旧格式 CSV 读取 (向后兼容) ----

    def read_basis(self, symbol: str) -> Optional[pd.DataFrame]:
        """读取基差日度数据(旧 CSV 格式)。"""
        path = self._csv_dir / "basis" / symbol.upper() / "basis_data.csv"
        if not path.exists():
            return None
        try:
            df = pd.read_csv(path)
            if df.empty:
                return None
            df = self._parse_date_col(df)
            logger.info("📂 本地基差缓存命中: %s (%d 行)", path, len(df))
            return df
        except Exception as e:
            logger.warning("⚠️ 读取本地基差缓存失败 %s: %s", path, e)
            return None

    def read_positioning(self, symbol: str) -> Optional[pd.DataFrame]:
        """读取并聚合持仓排名数据(旧 CSV 格式)。"""
        sym_upper = symbol.upper()
        base = self._csv_dir / "positioning" / sym_upper
        long_path = base / "long_position_ranking.csv"
        short_path = base / "short_position_ranking.csv"

        if not long_path.exists() or not short_path.exists():
            return None

        try:
            long_df = pd.read_csv(long_path)
            short_df = pd.read_csv(short_path)
            if long_df.empty or short_df.empty:
                return None

            long_agg = (
                long_df.groupby("date")["持仓量"]
                .sum().reset_index()
                .rename(columns={"持仓量": "long_top20"})
            )
            short_agg = (
                short_df.groupby("date")["持仓量"]
                .sum().reset_index()
                .rename(columns={"持仓量": "short_top20"})
            )

            merged = pd.merge(long_agg, short_agg, on="date", how="outer").fillna(0)
            merged["date"] = pd.to_datetime(
                merged["date"].astype(str).str.strip(),
                format="%Y%m%d", errors="coerce",
            )
            merged = merged.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
            merged["symbol"] = sym_upper
            logger.info("📂 本地持仓缓存命中: %s (%d 行)", base, len(merged))
            return merged
        except Exception as e:
            logger.warning("⚠️ 读取本地持仓缓存失败 %s: %s", base, e)
            return None

    def read_term_structure(self, var: str) -> Optional[pd.DataFrame]:
        """读取期限结构/展期收益率(旧 CSV 格式)。"""
        path = self._csv_dir / "term_structure" / var.upper() / "term_structure.csv"
        if not path.exists():
            return None
        try:
            df = pd.read_csv(path)
            if df.empty:
                return None
            df = self._parse_date_col(df)
            logger.info("📂 本地期限结构缓存命中: %s (%d 行)", path, len(df))
            return df
        except Exception as e:
            logger.warning("⚠️ 读取本地期限结构缓存失败 %s: %s", path, e)
            return None

    # ---- 批量查询 ----

    def has_basis(self, symbol: str) -> bool:
        return (self._csv_dir / "basis" / symbol.upper() / "basis_data.csv").exists()

    def has_positioning(self, symbol: str) -> bool:
        return (self._csv_dir / "positioning" / symbol.upper() / "long_position_ranking.csv").exists()

    def has_term_structure(self, var: str) -> bool:
        return (self._csv_dir / "term_structure" / var.upper() / "term_structure.csv").exists()


__all__ = ["CommodityLocalCacheAdapter"]
