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
    extract_first_sentence,
    get_full_symbol,
    inject_analyst_id,
    load_features,
    make_analyst_id,
    quality_gate,
    truncate_snapshot,
)

logger = get_logger("default")

NEWS_SYSTEM_PROMPT = """你是一位资深的期货新闻分析师,采用"宏观-产业-资金-情绪"四层分析框架。

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

## 四层分析框架

### 第一层:宏观叙事
聚焦影响当前品种的全球宏观因子:
- 美联储/ECB/央行货币政策(利率/QT/QE)
- OPEC+决策与地缘政治(制裁/冲突/贸易摩擦)
- 中国经济政策(基建/房地产/制造业PMI)
- 美元指数与汇率波动
- 全球经济增长预期(IMF/世界银行)

### 第二层:产业叙事
根据品种行业分类(category)聚焦产业级事件:
- **金属(Metal)**: 矿山产能/冶炼开工率/下游加工/废料回收/LME库存
- **化工(Chemical)**: 炼厂检修/PTA负荷/甲醇开工/聚酯需求/乙烯价格
- **能源(Energy)**: 油田产量/炼油利润/裂解价差/电力需求/天然气库存
- **农产品(Agricultural)**: 天气/种植面积/USDA报告/生猪存栏/压榨利润
- **金融(Financial)**: 股指估值/债市收益率/信用利差/资金流向

### 第三层:资金情绪
- 新闻情感比反映当前市场情绪倾向
- 正面事件与负面事件的数量对比
- 关键事件的潜在影响大小

### 第四层:综合判断
- 汇总宏观+产业+情绪三层证据,给出明确方向
- 标注主要不确定性来源
- 与其他分析师(技术/基本面/持仓)的信号交叉验证

## 输出格式

使用 Markdown,500-800 字。结构:
- ## 宏观叙事
- ## 产业叙事
- ## 资金情绪
- ## 综合判断(方向+置信度+核心叙事)
- ## 风险提示

禁止使用 emoji;保持专业性。"""


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
    recent_events: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """LLM 失败时,返回情感统计 + 新闻原文摘要(无 LLM 叙事)。"""
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

    # 加入新闻原文摘要(前 5 条)
    if recent_events:
        md += "\n\n## 新闻原文摘要(最近事件)\n"
        for i, evt in enumerate(recent_events[:5], 1):
            title = evt.get("title", "")
            content = evt.get("content", "")
            source = evt.get("source", "")
            if title:
                md += f"\n{i}. **{title}**"
                if content:
                    md += f"\n   {content[:200]}"
                if source:
                    md += f"\n   来源:{source}"
                md += "\n"
    else:
        md += "\n\n(无新闻原文数据)"

    md += (
        f"\n---\n"
        f"_本报告仅含情感统计与新闻原文摘要,叙事不可得;"
        f"LLM 故障恢复后请重新提交任务。_\n"
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
            report_md = empty_report("neutral", reason)
            analyst_id = make_analyst_id("NEWS", full_symbol, trade_date, seed="empty")
            tagged_report = inject_analyst_id(report_md, analyst_id)
            registry_entry = {analyst_id: {"id": analyst_id, "prefix": "NEWS", "analyst": "news", "report_key": "news_report", "direction": "neutral", "summary": "(数据缺失: 跳过)"}}
            return {
                "news_report": tagged_report,
                "messages": [],
                "news_tool_call_count": 0,
                "analyst_registry": registry_entry,
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
            analyst_id = make_analyst_id("NEWS", full_symbol, trade_date)
            tagged_report = inject_analyst_id(report_md, analyst_id)
            registry_entry = {analyst_id: {"id": analyst_id, "prefix": "NEWS", "analyst": "news", "report_key": "news_report", "direction": "neutral", "summary": extract_first_sentence(report_md)}}
            return {
                "news_report": tagged_report,
                "messages": [msg_out],
                "news_tool_call_count": 0,
                "analyst_registry": registry_entry,
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
                    recent_events=recent_events,
                )
            except Exception as inner_e:
                logger.error(f"❌ [新闻分析师] fallback 也失败: {inner_e}")
                fallback_md = empty_report("neutral", f"LLM 失败且 fallback 异常: {inner_e}")

            analyst_id = make_analyst_id("NEWS", full_symbol, trade_date, seed="fallback")
            tagged_fallback = inject_analyst_id(fallback_md, analyst_id)
            registry_entry = {analyst_id: {"id": analyst_id, "prefix": "NEWS", "analyst": "news", "report_key": "news_report", "direction": "neutral", "summary": "(降级: LLM 不可用)"}}
            return {
                "news_report": tagged_fallback,
                "messages": [],
                "news_tool_call_count": 0,
                "analyst_registry": registry_entry,
            }

    return news_analyst_node


__all__ = ["create_news_analyst"]