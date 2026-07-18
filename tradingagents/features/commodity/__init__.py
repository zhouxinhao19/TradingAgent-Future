"""Commodity features 子包(Phase 3b-i / 3b-ii)。

6 个模块,纯规则计算,零 LLM:
  - technical 技术面(50+ 指标 / 日周多周期 / OI 背离 / 资金流 / 综合评分)
  - basis 基差(现货/近月/主力价 + 基差率 + 180d 分位 + 升贴水信号)
  - inventory 库存(WoW/MoM 变化 + 180d 分位 + 跳变标志)
  - positioning 持仓(前20净多变化 + 集中度 + 拥挤度分位 + 5d 净多)
  - term_structure 期限结构(structure + carry_score + roll_yield/spread)
  - news_sentiment 新闻情感(1/3/7/14/30 天计数 + 多空情感比 + 重要性事件)

输入为 DataFrame 或 Dict,输出严格遵循统一 schema(latest/stats/signals/snapshot/quality)。
"""
from . import _helpers  # noqa: F401
from .technical import compute_technical_metrics
from .basis import compute_basis_metrics
from .inventory import compute_inventory_metrics
from .positioning import compute_positioning_metrics
from .term_structure import compute_term_structure_metrics
from .news_sentiment import compute_news_sentiment_metrics
from .news_annotator import NewsAnnotator, NewsAnnotation

__all__ = [
    "_helpers",
    "compute_technical_metrics",
    "compute_basis_metrics",
    "compute_inventory_metrics",
    "compute_positioning_metrics",
    "compute_term_structure_metrics",
    "compute_news_sentiment_metrics",
    "NewsAnnotator",
    "NewsAnnotation",
]
