"""
news_sentiment.py — 商品期货新闻 / 情感特征模块 (Phase 3b-i)

输入:
  - DataFrame:列名 `发布时间/date`、`标题/title`、`内容/content`(可任一)
  - List[Dict]:provider `get_futures_news(category, limit)` 原始返回
  - 单条 Dict 也可

输出: 标准 schema Dict
  {
    "latest":   {...},
    "stats":    {"zscore_180d": null, "slope_20d": null},   # 时间序列统计不适配,保留 None
    "signals":  [...],
    "snapshot": {counts: {n1/n3/n7/n14/n30, total},
                 sentiment: {bullish, bearish, ratio},
                 categories: {...}, importance: {...}},
    "quality":  {rows, coverage, data_freshness_days, sources},
  }

Notes:
  - 纯规则,无 LLM
  - 情感判断使用扩展关键词词典(多空)
  - 重要性按"标题命中关键词"近似
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import numpy as np
import pandas as pd

from tradingagents.features.commodity import _helpers as h


# 期货多空情感关键词词典(可扩展)
BULLISH_KW: List[str] = [
    "上调", "上涨", "涨幅", "扩大", "改善", "提振", "好转", "超预期", "强势",
    "看多", "做多", "利多", "支撑", "回升", "反弹", "突破", "利好", "紧缺",
    "供给紧张", "需求旺盛", "增产不及预期", "库存下降", "去库", "现货运费上涨",
]
BEARISH_KW: List[str] = [
    "下调", "下跌", "跌幅", "收缩", "恶化", "承压", "不及预期", "弱势",
    "看空", "做空", "利空", "阻力", "回落", "下跌", "跌破", "利空", "过剩",
    "供给宽松", "需求疲软", "增产超预期", "库存上升", "累库", "现货运费下跌",
]
IMPORTANCE_KW: List[str] = [
    "央行", "美联储", "欧央行", "降息", "加息", "决议", "重要", "重大", "突发",
    "OPEC", "欧佩克", "非农", "CPI", "PPI", "GDP", "PMI", "紧急",
]
CATEGORY_KW: Dict[str, List[str]] = {
    "metal": ["有色", "铜", "铝", "锌", "镍", "锡", "铅", "黄金", "白银", "金属"],
    "energy": ["原油", "石油", "燃料", "煤炭", "天然气", "电力", "焦煤", "焦炭"],
    "agricultural": ["大豆", "豆粕", "豆油", "玉米", "小麦", "棉花", "白糖", "生猪", "鸡蛋", "苹果", "红枣"],
    "chemical": ["化工", "PTA", "甲醇", "塑料", "PP", "PVC", "橡胶", "沥青", "尿素"],
    "financial": ["股指", "国债", "国债期货", "上证", "深证", "沪深300", "中证500"],
    "macro": ["宏观", "央行", "美联储", "欧央行", "降息", "加息", "CPI", "PPI", "GDP"],
}


def _coerce_input(
    inp: Union[pd.DataFrame, List[Dict[str, Any]], Dict[str, Any], None],
) -> pd.DataFrame:
    """统一输入到 DataFrame。"""
    if inp is None:
        return pd.DataFrame()
    if isinstance(inp, pd.DataFrame):
        return inp
    if isinstance(inp, dict):
        return pd.DataFrame([inp])
    if isinstance(inp, list):
        if not inp:
            return pd.DataFrame()
        if all(isinstance(x, dict) for x in inp):
            return pd.DataFrame(inp)
        return pd.DataFrame()
    return pd.DataFrame()


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = h.normalize_columns(df)
    if "content" not in out.columns and "title" in out.columns:
        out["content"] = out["title"]
    if "content" not in out.columns:
        # 用第一字符串列作 content
        str_cols = [c for c in out.columns
                    if out[c].dtype == object and c not in ("date",)]
        if str_cols:
            out["content"] = out[str_cols[0]].astype(str)
        else:
            out["content"] = ""
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"], errors="coerce")
        # 去除时区信息,统一为 tz-naive
        if out["date"].dt.tz is not None:
            out["date"] = out["date"].dt.tz_localize(None)
        out = out.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    out["content"] = out["content"].fillna("").astype(str)
    if "title" in out.columns:
        out["title"] = out["title"].fillna("").astype(str)
    return out


def _classify_category(text: str) -> List[str]:
    cats: List[str] = []
    for cat, kws in CATEGORY_KW.items():
        if any(kw in text for kw in kws):
            cats.append(cat)
    return cats or ["other"]


def _sentiment(text: str) -> int:
    """返回 +1 / 0 / -1。"""
    bpos = sum(1 for kw in BULLISH_KW if kw in text)
    bneg = sum(1 for kw in BEARISH_KW if kw in text)
    if bpos > bneg:
        return 1
    if bneg > bpos:
        return -1
    return 0


def _signals(counts: Dict[str, int], sentiment: Dict[str, Any], importance_count: int) -> List[str]:
    sigs: List[str] = []
    if counts.get("n7", 0) >= 50:
        sigs.append("近一周新闻热度高")
    elif counts.get("n7", 0) >= 20:
        sigs.append("近一周新闻热度中等")
    if counts.get("n3", 0) >= 10:
        sigs.append("近 3 天新闻密集")
    ratio = sentiment.get("ratio")
    total = sentiment.get("bullish", 0) + sentiment.get("bearish", 0)
    if total >= 10:
        if ratio is not None and ratio > 0.2:
            sigs.append("新闻情绪偏多")
        elif ratio is not None and ratio < -0.2:
            sigs.append("新闻情绪偏空")
        else:
            sigs.append("新闻情绪中性")
    if importance_count >= 3:
        sigs.append(f"近 7 天 {importance_count} 条重要事件")
    return sigs


def compute_news_sentiment_metrics(
    inp: Union[pd.DataFrame, List[Dict[str, Any]], None],
    source: str = "all",
) -> Dict[str, Any]:
    """新闻 / 事件统计与情感指标(纯规则,零 LLM)。

    Args:
        inp: provider `get_futures_news()` 的返回(可以是 DataFrame 或 List[Dict])
        source: 标注新闻来源(写入 quality)
    """
    if inp is None:
        return h.empty_result("无新闻数据")
    raw = _coerce_input(inp)
    data = _prepare(raw)
    if data.empty:
        return h.empty_result("无新闻数据")

    n_total = len(data)
    now = data["date"].max()
    today = pd.Timestamp(datetime.now().date())

    def _cnt(days: int) -> int:
        since = now - pd.Timedelta(days=days)
        return int((data["date"] >= since).sum())

    counts = {
        "n1": _cnt(1),
        "n3": _cnt(3),
        "n7": _cnt(7),
        "n14": _cnt(14),
        "n30": _cnt(30),
        "total": n_total,
    }

    # 近 3 天热度 Top5
    recent = data[data["date"] >= (now - pd.Timedelta(days=3))].sort_values(
        "date", ascending=False
    ).head(5)
    recent_top: List[Dict[str, Any]] = []
    for _, r in recent.iterrows():
        content = str(r.get("content", ""))[:120]
        recent_top.append({
            "date": str(r.get("date")),
            "content": content,
            "sentiment": _sentiment(content),
        })

    # 情感计数(最近 200 条)
    sentiments = data["content"].astype(str).tail(200).apply(_sentiment)
    bullish_count = int((sentiments == 1).sum())
    bearish_count = int((sentiments == -1).sum())
    total = bullish_count + bearish_count
    ratio = float((bullish_count - bearish_count) / total) if total > 0 else None

    # 分类统计
    categories: Dict[str, int] = {}
    for txt in data["content"].astype(str):
        for c in _classify_category(txt):
            categories[c] = categories.get(c, 0) + 1

    # 重要性(标题 / 内容含重要性关键词)
    title_series = data.get("title", data["content"]).astype(str)
    importance_count = int(title_series.tail(200).apply(
        lambda t: any(kw in t for kw in IMPORTANCE_KW)
    ).sum())

    signals = _signals(counts, {"bullish": bullish_count, "bearish": bearish_count, "ratio": ratio}, importance_count)

    # quality
    quality = {
        "rows": n_total,
        "coverage": 1.0 if n_total > 0 else 0.0,
        "data_freshness_days": int((today - now).days) if pd.notna(now) else None,
        "sources": [source] if source else [],
        "first_date": str(data["date"].min()),
        "last_date": str(now),
    }

    latest = {
        "last_date": str(now),
        "last_content": recent_top[0]["content"] if recent_top else None,
    }
    snapshot = {
        "counts": counts,
        "sentiment": {"bullish": bullish_count, "bearish": bearish_count, "ratio": ratio},
        "categories": categories,
        "importance_count": importance_count,
        "recent_top": recent_top,
    }
    stats = {
        "zscore_180d": None,
        "slope_20d": None,
        "n_total": n_total,
        "avg_per_day_7d": round(counts["n7"] / 7.0, 2) if counts["n7"] else 0.0,
    }

    return {
        "latest": latest,
        "stats": stats,
        "signals": signals,
        "snapshot": snapshot,
        "quality": quality,
    }
