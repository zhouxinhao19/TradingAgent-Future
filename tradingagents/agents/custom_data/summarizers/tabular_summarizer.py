"""
tabular_summarizer.py — TabularSummarizer: TabularContent → dict 摘要
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from tradingagents.agents.custom_data.content.tabular import TabularContent
from tradingagents.utils.logging_init import get_logger

logger = get_logger("default")

# 最大描述行数：超过此值时仅输出统计信息
_MAX_DESCRIBE_ROWS = 100_000


class TabularSummarizer:
    """TabularContent 摘要器。

    生成可注入 LLM prompt 的结构化摘要：
      - 基本统计（行数、列数、缺失值）
      - 列名与类型
      - 数值列统计（均值、标准差、分位数）
      - 时间列自动识别
      - 前 5 行示例
    """

    def summarize(self, content: TabularContent) -> Dict[str, Any]:
        """生成结构化摘要。

        Args:
            content: TabularContent 实例

        Returns:
            dict，包含 overview / columns / statistics / sample / warnings
        """
        df = content.dataframe
        result: Dict[str, Any] = {
            "type": "tabular",
            "source": content.source_path,
            "overview": {
                "rows": int(content.shape[0]),
                "columns": int(content.shape[1]),
                "missing_cells": sum(content.missing_summary.values()),
                "missing_ratio": round(
                    sum(content.missing_summary.values())
                    / max(content.shape[0] * content.shape[1], 1), 4
                ),
            },
            "columns": [
                {
                    "name": col,
                    "dtype": content.dtypes.get(col, "unknown"),
                    "missing": content.missing_summary.get(col, 0),
                }
                for col in content.columns
            ],
        }

        # ---- 数值列统计 ----
        if content.numeric_columns:
            num_df = df[content.numeric_columns]
            desc = num_df.describe(percentiles=[0.05, 0.25, 0.5, 0.75, 0.95]).to_dict()
            result["statistics"] = {
                col: {
                    "count": int(v.get("count", 0)),
                    "mean": _safe_float(v.get("mean")),
                    "std": _safe_float(v.get("std")),
                    "min": _safe_float(v.get("min")),
                    "p5": _safe_float(v.get("5%")),
                    "p25": _safe_float(v.get("25%")),
                    "p50": _safe_float(v.get("50%")),
                    "p75": _safe_float(v.get("75%")),
                    "p95": _safe_float(v.get("95%")),
                    "max": _safe_float(v.get("max")),
                }
                for col, v in desc.items()
            }

        # ---- 时间列自动识别 ----
        time_cols = []
        for col in df.columns:
            if str(col).lower() in ("date", "time", "datetime", "日期", "时间", "交易日期"):
                time_cols.append(str(col))
        if not time_cols:
            for col in content.columns:
                if content.dtypes.get(col) in ("datetime64[ns]",):
                    time_cols.append(col)
        result["time_columns"] = time_cols
        if time_cols:
            try:
                parsed = pd.to_datetime(df[time_cols[0]], errors="coerce")
                valid = parsed.dropna()
                result["date_range"] = {
                    "min": str(valid.min()) if not valid.empty else None,
                    "max": str(valid.max()) if not valid.empty else None,
                    "unique_dates": int(valid.nunique()),
                }
            except Exception:
                pass

        # ---- 样本数据（头 3 行 + 尾 3 行） ----
        # 仅取 head 会导致上传数据的 LLM 解读只看得到最早的行，
        # 对于 20 年历史数据(如 COMEX 铜库存)会误判数据新鲜度。
        head_tail = pd.concat([df.head(3), df.tail(3)]).drop_duplicates().reset_index(drop=True)
        result["sample"] = (
            [_json_safe_record(rec) for rec in head_tail.to_dict(orient="records")]
            if not head_tail.empty else []
        )

        # ---- 警告 ----
        warnings = []
        if content.shape[0] == 0:
            warnings.append("文件为空（0 行数据）")
        if content.shape[1] > 50:
            warnings.append(f"列数过多（{content.shape[1]} 列），建议精简")
        if result["overview"]["missing_ratio"] > 0.5:
            warnings.append(f"缺失值比例过高（{result['overview']['missing_ratio']:.1%}）")
        if warnings:
            result["warnings"] = warnings

        return result


def _safe_float(v: Any) -> float | None:
    """安全转换为 float，NaN/None 返回 None。"""
    if v is None:
        return None
    try:
        f = float(v)
        if f != f:  # NaN
            return None
        return round(f, 4)
    except (TypeError, ValueError):
        return None


def _json_safe_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    """把一行记录转成 JSON 安全的值。

    pandas 的 Timestamp / Timedelta / numpy 标量 / NaN 等无法直接 json.dumps，
    统一转成字符串 / Python 原生数值 / None。
    """
    safe: Dict[str, Any] = {}
    for k, v in rec.items():
        key = str(k)
        # NaN / NaT
        try:
            if v is None or (pd.isna(v) if not isinstance(v, (list, tuple, dict)) else False):
                safe[key] = None
                continue
        except (TypeError, ValueError):
            pass
        if isinstance(v, (pd.Timestamp,)):
            safe[key] = v.isoformat()
        elif isinstance(v, pd.Timedelta):
            safe[key] = str(v)
        elif isinstance(v, (bool, int, float, str)):
            safe[key] = v
        elif hasattr(v, "item"):  # numpy 标量
            try:
                safe[key] = v.item()
            except (ValueError, TypeError):
                safe[key] = str(v)
        else:
            safe[key] = str(v)
    return safe


__all__ = ["TabularSummarizer"]
