"""
news_analyst.py — 商品期货新闻分析师节点 (Phase 3b-ii)

输入:
  - state['commodity_features']['news_sentiment']
  - state.get('latest_news', [])  # 来自 Propagator 调用 provider.get_futures_news()

输出:state['news_report'] = Markdown 新闻叙事分析报告

新闻分析师必调 LLM(features 层只算情感统计,叙事需要 LLM 总结):
  - 宏观叙事(全球宏观聚合)
  - 产业叙事(按商品 category 分类:金属/化工/能源/农产品/金融)
  - 关键事件卡片

LLM 失败降级:仅返回 features.news_sentiment 的统计部分(情感比 + 计数)。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import AIMessage

from tradingagents.utils.logging_init import get_logger

from ._base import (
    empty_report,
    get_full_symbol,
    load_features,
    quality_gate,
    truncate_snapshot,
)

logger = get_logger("default")

NEWS_SYSTEM_PROMPT = """你是一位资深的期货新闻分析师,聚焦宏观叙事 + 产业事件。

## 分析对象
- 标的代码:{full_symbol}
- 品种:{variety_name}
- 交易所:{exchange}
- 行业分类:{category}
- 分析日期:{trade_date}

## 特征层(已计算)

### 情感统计
- 正面数量:{positive_count}
- 负面数量:{negative_count}
- 中性数量:{neutral_count}
- 情感比:{sentiment_ratio}
- 触发信号:{signals}

### 最近重要事件(原文)
{recent_events}

---

## 分析要求

1. **宏观叙事**:美联储/中国央行/OPEC+/地缘政治 等宏观因子对当前品种的影响
2. **产业叙事**:产业链上下游事件(产能/库存/限产/替代品)
3. **情感倾向**:基于正面/负面事件数量与情感比,给出方向
4. **关键事件卡片**:列出 3-5 条最重要的事件,每条 1-2 句话
5. **风险提示**:数据稀疏或新闻源少时,降低 confidence

## 输出格式

使用 Markdown,500-800 字,结构:
- ## 宏观叙事
- ## 产业叙事
- ## 情感倾向
- ## 关键事件卡片(列表)
- ## 风险提示
"""


def _fmt(v: Any) -> str:
    if v is None:
        return "N/A"
    if isinstance(v, float):
        if v != v:
            return "N/A"
        return f"{v:.4f}".rstrip("0").rstrip(".")
    return str(v)


def _format_events(events: List[Dict[str, Any]], max_items: int = 10) -> str:
    """把新闻列表格式化为 markdown。"""
    if not events:
        return "(无新闻原文)"
    items = events[:max_items]
    lines = []
    for e in items:
        published = e.get("published_at", "")
        title = e.get("title", "")
        content = e.get("content", "")
        source = e.get("source", "")
        sentiment = e.get("sentiment", "")
        line = f"- [{published}] {title}"
        if content:
            line += f" — {content[:200]}"
        meta_bits = []
        if source:
            meta_bits.append(f"来源:{source}")
        if sentiment:
            meta_bits.append(f"情感:{sentiment}")
        if meta_bits:
            line += f" ({', '.join(meta_bits)})"
        lines.append(line)
    return "\n".join(lines)


def _build_fallback_report(
    full_symbol: str,
    news_block: Dict[str, Any],
    sentiment_ratio: Optional[float],
    positive_count: int,
    negative_count: int,
    neutral_count: int,
    signals: List[str],
) -> str:
    """LLM 失败时,返回情感统计 + 触发信号(无叙事)。"""
    direction = "中性"
    if sentiment_ratio is not None:
        if sentiment_ratio > 0.2:
            direction = "看多"
        elif sentiment_ratio < -0.2:
            direction = "看空"
    md = (
        f"# {full_symbol} 新闻分析报告(降级版本 — LLM 不可用)\n\n"
        f"## 情感倾向\n方向:{direction}(情感比={_fmt(sentiment_ratio)})\n\n"
        f"## 情感统计\n"
        f"- 正面:{positive_count}\n"
        f"- 负面:{negative_count}\n"
        f"- 中性:{neutral_count}\n\n"
        f"## 触发信号\n"
    )
    md += "\n".join(f"- {s}" for s in signals[:10]) or "- (无触发信号)"
    md += (
        f"\n\n---\n"
        f"_本报告仅含情感统计,无叙事;LLM 故障恢复后请重新提交任务。_\n"
    )
    return md


def create_news_analyst(llm):
    """新闻分析师工厂函数。"""

    def news_analyst_node(state: dict) -> dict:
        full_symbol = get_full_symbol(state)
        trade_date = state.get("trade_date", "")

        logger.info(f"📰 [新闻分析师] 启动: {full_symbol} @ {trade_date}")

        features = load_features(state)
        news_block = features.get("news_sentiment")

        # 读最近事件(state 注入,来自 Propagator)
        recent_events: List[Dict[str, Any]] = state.get("latest_news") or []

        # --- 降级 1:features 与 latest_news 都空 ---
        if not isinstance(news_block, dict) and not recent_events:
            reason = "新闻 features 与 latest_news 均空"
            return {
                "news_report": empty_report("neutral", reason),
                "messages": [],
                "news_tool_call_count": 0,
            }

        # --- 准备 prompt 变量 ---
        if isinstance(news_block, dict):
            latest = news_block.get("latest", {}) or {}
            stats = news_block.get("stats", {}) or {}
            signals = news_block.get("signals", []) or []
            positive_count = int(latest.get("positive_count", 0) or 0)
            negative_count = int(latest.get("negative_count", 0) or 0)
            neutral_count = int(latest.get("neutral_count", 0) or 0)
            sentiment_ratio = latest.get("sentiment_ratio")
            if sentiment_ratio is None:
                total = positive_count + negative_count
                sentiment_ratio = positive_count / total if total > 0 else None
        else:
            positive_count = 0
            negative_count = 0
            neutral_count = 0
            sentiment_ratio = None
            signals = []
            latest = {}
            stats = {}

        variety_name = state.get("variety_name", full_symbol)
        exchange = state.get("exchange", "")
        category = state.get("category", "general")

        prompt_vars = dict(
            full_symbol=full_symbol,
            variety_name=variety_name,
            exchange=exchange,
            category=category,
            trade_date=trade_date,
            positive_count=positive_count,
            negative_count=negative_count,
            neutral_count=neutral_count,
            sentiment_ratio=_fmt(sentiment_ratio),
            signals="\n".join(f"- {s}" for s in signals[:8]) or "- (无触发信号)",
            recent_events=_format_events(recent_events, max_items=10),
        )

        try:
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", NEWS_SYSTEM_PROMPT),
                    MessagesPlaceholder(variable_name="messages"),
                ]
            ).partial(**prompt_vars)

            messages_payload = prompt.format_messages(
                messages=state.get("messages", []) or []
            )

            logger.info(f"📰 [新闻分析师] 调用 LLM(必调),full_symbol={full_symbol}")
            result = llm.invoke(messages_payload)

            if hasattr(result, "content"):
                content = result.content
                if not isinstance(content, str):
                    content = str(content) if content is not None else ""
            else:
                content = str(result) if result is not None else ""

            report_md = content
            logger.info(f"✅ [新闻分析师] LLM 报告生成: {len(report_md)} 字符")

            msg_out = result if hasattr(result, "content") else AIMessage(content=report_md)
            return {
                "news_report": report_md,
                "messages": [msg_out],
                "news_tool_call_count": 0,
            }

        except Exception as e:
            logger.error(f"❌ [新闻分析师] LLM 调用失败: {e}")
            try:
                fallback_md = _build_fallback_report(
                    full_symbol,
                    news_block or {},
                    sentiment_ratio,
                    positive_count,
                    negative_count,
                    neutral_count,
                    signals,
                )
            except Exception as inner_e:
                logger.error(f"❌ [新闻分析师] fallback 也失败: {inner_e}")
                fallback_md = empty_report("neutral", f"LLM 失败且 fallback 异常: {inner_e}")

            return {
                "news_report": fallback_md,
                "messages": [],
                "news_tool_call_count": 0,
            }

    return news_analyst_node


__all__ = ["create_news_analyst"]