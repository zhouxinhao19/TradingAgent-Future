"""
共享的文档指标处理函数
- add_financial_metrics: 将日度基础指标（市值/估值/交易）追加到文档中
"""
from typing import Dict


def add_financial_metrics(doc: Dict, daily_metrics: Dict) -> None:
    """
    将财务与交易指标写入 doc（就地修改）。
    - 市值：total_mv/circ_mv（从万元转换为亿元）
    - 估值：pe/pb/pe_ttm/pb_mrq（过滤 NaN/None）
    - 交易：turnover_rate/volume_ratio（过滤 NaN/None）
    """
    # 市值（万元 -> 亿元）
    if "total_mv" in daily_metrics and daily_metrics["total_mv"] is not None:
        doc["total_mv"] = daily_metrics["total_mv"] / 10000
    if "circ_mv" in daily_metrics and daily_metrics["circ_mv"] is not None:
        doc["circ_mv"] = daily_metrics["circ_mv"] / 10000

    # 估值指标
    for field in ["pe", "pb", "pe_ttm", "pb_mrq"]:
        if field in daily_metrics and daily_metrics[field] is not None:
            try:
                value = float(daily_metrics[field])
                if not (value != value):  # 过滤 NaN
                    doc[field] = value
            except (ValueError, TypeError):
                pass

    # 交易指标
    for field in ["turnover_rate", "volume_ratio"]:
        if field in daily_metrics and daily_metrics[field] is not None:
            try:
                value = float(daily_metrics[field])
                if not (value != value):  # 过滤 NaN
                    doc[field] = value
            except (ValueError, TypeError):
                pass

