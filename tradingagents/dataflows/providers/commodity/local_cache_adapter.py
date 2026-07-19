"""
local_cache_adapter.py — 商品期货本地数据库回退适配器 (Phase 3b-iii)

从参考项目 TradingAgents_for_Futures-main 的预建 CSV 数据库读取
基差/持仓/期限结构数据,在 AKShare 在线获取失败时自动回退。

路径约定:
  REF_PROJECT_DIR/database/basis/{SYMBOL}/basis_data.csv
  REF_PROJECT_DIR/database/positioning/{SYMBOL}/long_position_ranking.csv
  REF_PROJECT_DIR/database/positioning/{SYMBOL}/short_position_ranking.csv
  REF_PROJECT_DIR/database/positioning/{SYMBOL}/volume_ranking.csv
  REF_PROJECT_DIR/database/term_structure/{VAR}/term_structure.csv
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from tradingagents.utils.logging_init import get_logger

logger = get_logger("default")

_DEFAULT_REF_DIR = Path(
    r"D:\改造\TradingAgents_for_Futures-main\qihuo\database"
)


class CommodityLocalCacheAdapter:
    """从参考项目本地 CSV 数据库读取数据的适配器。"""

    def __init__(self, database_dir: Optional[Path] = None):
        self._db_dir = database_dir or _DEFAULT_REF_DIR

    @staticmethod
    def _parse_date_col(df: pd.DataFrame, col: str = "date") -> pd.DataFrame:
        """安全解析日期列,支持 YYYYMMDD 和 YYYY-MM-DD 两种格式。"""
        if col in df.columns:
            s = df[col].astype(str).str.strip()
            # 先尝试 YYYYMMDD (term_structure)
            parsed = pd.to_datetime(s, format="%Y%m%d", errors="coerce")
            # 若全部 NaT 则尝试 YYYY-MM-DD (basis)
            if parsed.isna().all():
                parsed = pd.to_datetime(s, format="%Y-%m-%d", errors="coerce")
            # 若仍有 NaT 则用自动推断
            if parsed.isna().any():
                parsed = pd.to_datetime(s, errors="coerce")
            df[col] = parsed
        return df

    # ---- basis ----

    def read_basis(self, symbol: str) -> Optional[pd.DataFrame]:
        """读取基差日度数据。

        期望 CSV 列(与 futures_spot_price_daily 一致):
          date, symbol, spot_price, near_contract, near_contract_price,
          dominant_contract, dominant_contract_price,
          near_month, dominant_month, near_basis, dom_basis,
          near_basis_rate, dom_basis_rate
        """
        path = self._db_dir / "basis" / symbol.upper() / "basis_data.csv"
        if not path.exists():
            logger.debug("📂 本地基差缓存不存在: %s", path)
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

    # ---- positioning ----

    def read_positioning(self, symbol: str) -> Optional[pd.DataFrame]:
        """读取并聚合持仓排名数据。

        从 long/short 排名 CSV 聚合成行级:
          date, long_top20, short_top20

        原始列:
          排名,会员简称,持仓量,比上交易增减,date,contract,position_type,symbol
        """
        sym_upper = symbol.upper()
        base = self._db_dir / "positioning" / sym_upper

        long_path = base / "long_position_ranking.csv"
        short_path = base / "short_position_ranking.csv"

        if not long_path.exists() or not short_path.exists():
            logger.debug("📂 本地持仓缓存不存在: %s", base)
            return None

        try:
            long_df = pd.read_csv(long_path)
            short_df = pd.read_csv(short_path)

            if long_df.empty or short_df.empty:
                return None

            # 按 date 聚合 long_top20 = sum(持仓量)
            long_agg = (
                long_df.groupby("date")["持仓量"]
                .sum()
                .reset_index()
                .rename(columns={"持仓量": "long_top20"})
            )
            short_agg = (
                short_df.groupby("date")["持仓量"]
                .sum()
                .reset_index()
                .rename(columns={"持仓量": "short_top20"})
            )

            merged = pd.merge(long_agg, short_agg, on="date", how="outer").fillna(0)
            merged["date"] = pd.to_datetime(
                merged["date"].astype(str).str.strip(),
                format="%Y%m%d",
                errors="coerce",
            )
            merged = merged.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
            merged["symbol"] = sym_upper

            logger.info(
                "📂 本地持仓缓存命中: %s (%d 行, long_top20=%.0f, short_top20=%.0f)",
                base, len(merged),
                merged["long_top20"].iloc[-1] if not merged.empty else 0,
                merged["short_top20"].iloc[-1] if not merged.empty else 0,
            )
            return merged
        except Exception as e:
            logger.warning("⚠️ 读取本地持仓缓存失败 %s: %s", base, e)
            return None

    # ---- term_structure ----

    def read_term_structure(self, var: str) -> Optional[pd.DataFrame]:
        """读取期限结构 / 展期收益率数据。

        期望 CSV 列:
          date, symbol, close, volume, open_interest, roll_yield
        """
        path = self._db_dir / "term_structure" / var.upper() / "term_structure.csv"
        if not path.exists():
            logger.debug("📂 本地期限结构缓存不存在: %s", path)
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
        return (self._db_dir / "basis" / symbol.upper() / "basis_data.csv").exists()

    def has_positioning(self, symbol: str) -> bool:
        return (self._db_dir / "positioning" / symbol.upper() / "long_position_ranking.csv").exists()

    def has_term_structure(self, var: str) -> bool:
        return (self._db_dir / "term_structure" / var.upper() / "term_structure.csv").exists()


__all__ = ["CommodityLocalCacheAdapter"]
