from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

# 统一指标库
from tradingagents.tools.analysis.indicators import IndicatorSpec, compute_many
# 统一多数据源DF接口（按优先级降级）
from tradingagents.dataflows.unified_dataframe import get_china_daily_df_unified


# --- DSL 约束 ---
ALLOWED_FIELDS = {
    # 原始行情（统一为小写列）
    "open", "high", "low", "close", "vol", "amount",
    # 派生
    "pct_chg",  # 当日涨跌幅
    # 指标（固定参数）
    "ma5", "ma10", "ma20", "ma60",
    "ema12", "ema26",
    "dif", "dea", "macd_hist",
    "rsi14",
    "boll_mid", "boll_upper", "boll_lower",
    "atr14",
    "kdj_k", "kdj_d", "kdj_j",
}

ALLOWED_OPS = {">", "<", ">=", "<=", "==", "!=", "between", "cross_up", "cross_down"}


@dataclass
class ScreeningParams:
    market: str = "CN"
    date: Optional[str] = None  # YYYY-MM-DD，None=最近交易日
    adj: str = "qfq"  # 预留参数，当前实现使用Tdx数据，不区分复权
    limit: int = 50
    offset: int = 0
    order_by: Optional[List[Dict[str, str]]] = None  # [{field, direction}]


class ScreeningService:
    def __init__(self):
        # 数据源通过统一DF接口获取，不直接绑定具体源
        self.provider = None

    # --- 公共入口 ---
    def run(self, conditions: Dict[str, Any], params: ScreeningParams) -> Dict[str, Any]:
        symbols = self._get_universe()
        # 为控制时长，先限制样本规模（后续用批量/缓存优化）
        symbols = symbols[:200]

        end_date = datetime.now()
        start_date = end_date - timedelta(days=220)
        end_s = end_date.strftime("%Y-%m-%d")
        start_s = start_date.strftime("%Y-%m-%d")

        results: List[Dict[str, Any]] = []

        for code in symbols:
            try:
                df = get_china_daily_df_unified(code, start_s, end_s)
                if df is None or df.empty:
                    continue
                # 统一列为小写
                dfu = df.rename(columns={
                    "Open": "open", "High": "high", "Low": "low", "Close": "close",
                    "Volume": "vol", "Amount": "amount"
                }).copy()
                # 计算派生：pct_chg
                if "close" in dfu.columns:
                    dfu["pct_chg"] = dfu["close"].pct_change() * 100.0

                # 计算指标（P0：固定一组，后续可从DSL推断需求）
                specs = [
                    IndicatorSpec("ma", {"n": 5}),
                    IndicatorSpec("ma", {"n": 10}),
                    IndicatorSpec("ma", {"n": 20}),
                    IndicatorSpec("ema", {"n": 12}),
                    IndicatorSpec("ema", {"n": 26}),
                    IndicatorSpec("macd"),
                    IndicatorSpec("rsi", {"n": 14}),
                    IndicatorSpec("boll", {"n": 20, "k": 2}),
                    IndicatorSpec("atr", {"n": 14}),
                    IndicatorSpec("kdj", {"n": 9, "m1": 3, "m2": 3}),
                ]
                dfc = compute_many(dfu, specs)

                if self._evaluate_conditions(dfc, conditions):
                    # 取最新一行
                    last = dfc.iloc[-1]
                    item = {
                        "code": code,
                        "close": self._safe_float(last.get("close")),
                        "pct_chg": self._safe_float(last.get("pct_chg")),
                        "amount": self._safe_float(last.get("amount")),
                        "ma20": self._safe_float(last.get("ma20")),
                        "rsi14": self._safe_float(last.get("rsi14")),
                        "kdj_k": self._safe_float(last.get("kdj_k")),
                        "kdj_d": self._safe_float(last.get("kdj_d")),
                        "kdj_j": self._safe_float(last.get("kdj_j")),
                        "dif": self._safe_float(last.get("dif")),
                        "dea": self._safe_float(last.get("dea")),
                        "macd_hist": self._safe_float(last.get("macd_hist")),
                    }
                    results.append(item)
            except Exception:
                continue

        total = len(results)
        # 排序
        if params.order_by:
            for order in reversed(params.order_by):  # 后者优先级低
                f = order.get("field")
                d = order.get("direction", "desc").lower()
                if f in ALLOWED_FIELDS:
                    results.sort(key=lambda x: (x.get(f) is None, x.get(f)), reverse=(d == "desc"))

        # 分页
        start = params.offset or 0
        end = start + (params.limit or 50)
        page_items = results[start:end]

        return {
            "total": total,
            "items": page_items,
        }

    # --- 内部：DSL 评估 ---
    def _evaluate_conditions(self, df: pd.DataFrame, node: Dict[str, Any]) -> bool:
        if not node:
            return True
        # group 节点
        if node.get("op") == "group" or "children" in node:
            logic = (node.get("logic") or "AND").upper()
            children = node.get("children", [])
            if logic not in {"AND", "OR"}:
                logic = "AND"
            flags = [self._evaluate_conditions(df, c) for c in children]
            return all(flags) if logic == "AND" else any(flags)

        # 叶子：字段比较
        field = node.get("field")
        op = node.get("op")
        if field not in ALLOWED_FIELDS or op not in ALLOWED_OPS:
            return False

        # 需要最近两行（交叉）
        if op in {"cross_up", "cross_down"}:
            right_field = node.get("right_field")
            if right_field not in ALLOWED_FIELDS:
                return False
            if len(df) < 2:
                return False
            t0 = df.iloc[-1]
            t1 = df.iloc[-2]
            a0 = t0.get(field)
            a1 = t1.get(field)
            b0 = t0.get(right_field)
            b1 = t1.get(right_field)
            if any(pd.isna([a0, a1, b0, b1])):
                return False
            if op == "cross_up":
                return (a1 <= b1) and (a0 > b0)
            else:
                return (a1 >= b1) and (a0 < b0)

        # 普通比较：最近一行
        t0 = df.iloc[-1]
        left = t0.get(field)
        if pd.isna(left):
            return False

        if node.get("right_field"):
            rf = node.get("right_field")
            if rf not in ALLOWED_FIELDS:
                return False
            right = t0.get(rf)
        else:
            right = node.get("value")

        try:
            if op == ">":
                return float(left) > float(right)
            if op == "<":
                return float(left) < float(right)
            if op == ">=":
                return float(left) >= float(right)
            if op == "<=":
                return float(left) <= float(right)
            if op == "==":
                return float(left) == float(right)
            if op == "!=":
                return float(left) != float(right)
            if op == "between":
                lo, hi = right if isinstance(right, (list, tuple)) else (None, None)
                if lo is None or hi is None:
                    return False
                v = float(left)
                return float(lo) <= v <= float(hi)
        except Exception:
            return False
        return False

    # --- 工具 ---
    def _safe_float(self, v: Any) -> Optional[float]:
        try:
            if v is None or (isinstance(v, float) and np.isnan(v)):
                return None
            return float(v)
        except Exception:
            return None

    def _get_universe(self) -> List[str]:
        """获取A股代码集合：
        P0：使用 tdx_utils 内部的常见股票映射 + 常见代码兜底
        后续：切换为 tushare 全量列表（需token与缓存）。
        """
        # 直接复用 tdx_utils 的常见表
        from tradingagents.dataflows.tdx_utils import _common_stock_names  # type: ignore
        base = list(_common_stock_names.keys())
        # 兜底补充：
        extras = ["000001", "000002", "000858", "600519", "600036", "601318", "300750"]
        pool = list(dict.fromkeys(base + extras))
        return pool

