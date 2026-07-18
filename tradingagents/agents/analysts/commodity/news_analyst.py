"""
news_analyst.py — 商品期货新闻分析师节点 (Phase 3b-ii / 新闻改造)

输入:
  - state['commodity_features']['news_sentiment']
  - state.get('latest_news', [])  # 从 Propagator 获取,含 LLM 预标注

输出:
  state['news_report'] = Markdown 新闻叙事分析报告

关键变化(新闻改造):
  - 关键词统计不再注入 prompt,改为注入 LLM 预标注的情感标签
  - _format_events 条数从 10 → 50
  - 框架从四层改为五层:情绪总览→宏观→产业→关键矛盾→综合判断
  - LLM 失败时降级仍使用关键词统计与新闻原文
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
    make_conclusion_id,
    make_registry_entry,
    quality_gate,
    truncate_snapshot,
)

logger = get_logger("default")

NEWS_SYSTEM_PROMPT = """你是一位资深的期货新闻分析师,采用"情绪总览→宏观→产业→关键矛盾→综合判断"五层框架。

## 分析对象
- 标的代码:{full_symbol}
- 品种:{variety_name}
- 交易所:{exchange}
- 行业分类:{category}
- 分析日期:{trade_date}

## 预标注情感(LLM 标注,仅供参考)
每条新闻已附带 LLM 预标注的情感标签和品种归属,仅供参考。
如果有矛盾信号或你觉得标注不准确的地方,请在你的分析中指出。

### 提供的事件列表(含预标注)
{recent_events}

---

## 五层分析框架

### 第〇步:情绪总览
列出利多信号(最多5条)、利空信号(最多5条)、中性信息(最多3条)。
每条例证直接引用 LLM 预标注的 reasoning。
如果预标注与你的判断矛盾,注明差异。

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

### 第三层:关键矛盾
- 多空证据冲突(如"库存去化利多 vs 下游需求疲软利空")
- 不同来源的信号分歧
- 需要后续关注的潜在转折

### 第四层:综合判断
- 汇总宏观+产业+情绪三层证据,给出明确方向
- 标注主要不确定性来源
- 与其他分析师(技术/基本面/持仓)的信号交叉验证

## 输出格式

使用 Markdown,500-800 字。结构:
- ## 情绪总览
- ## 宏观叙事
- ## 产业叙事
- ## 关键矛盾
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


def _format_events(events: List[Dict[str, Any]], max_items: int = 50) -> str:
    """把新闻列表(含 LLM 预标注)格式化为 markdown。"""
    if not events:
        return "(无新闻原文)"
    items = events[:max_items]
    lines = []
    for e in items:
        published = e.get("published_at", "")
        title = e.get("title", "")
        content = e.get("content", "")
        source = e.get("source", "")

        # LLM 预标注字段(优先)
        sentiment = e.get("llm_sentiment", e.get("sentiment", ""))
        confidence = e.get("llm_sentiment_confidence", "")
        reasoning = e.get("llm_sentiment_reasoning", "")
        summary = e.get("llm_summary", "")
        importance = e.get("llm_importance", "")
        varieties = e.get("relevant_varieties", [])

        # 使用 summary(精炼) 或 title
        heading = summary or title
        line = f"- [{published}] {heading}"

        # 情感标签
        if sentiment:
            line += f" [{sentiment}"
            if confidence:
                line += f", 置信度{confidence}"
            line += "]"

        # 品种归属
        if varieties:
            line += f" 品种:{','.join(varieties)}"

        # 推理理由
        if reasoning:
            line += f" — {reasoning}"

        # 原文(前 150 字)
        if content:
            line += f"\n  原文:{content[:150]}"

        # 元信息
        meta_bits = []
        if source:
            meta_bits.append(f"来源:{source}")
        if importance:
            meta_bits.append(f"重要度:{importance}")
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

    if recent_events:
        md += "\n\n## 新闻原文摘要(最近事件)\n"
        for i, evt in enumerate(recent_events[:5], 1):
            title = evt.get("title", "")
            content = evt.get("content", "")
            summary = evt.get("llm_summary", "")
            source = evt.get("source", "")
            heading = summary or title
            if heading:
                md += f"\n{i}. **{heading}**"
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
            conclusion_id = make_conclusion_id("NEWS", 1)
            tagged_report = inject_analyst_id(report_md, analyst_id)
            registry_entry = make_registry_entry(analyst_id, conclusion_id, "NEWS", "news", "news_report", "neutral", "(数据缺失: 跳过)")
            return {
                "news_report": tagged_report,
                "messages": [],
                "news_tool_call_count": 0,
                "analyst_registry": registry_entry,
            }

        # --- 准备 prompt 变量:优先使用 LLM 预标注,降级用关键词统计 ---
        variety_name = state.get("variety_name", full_symbol)
        exchange = state.get("exchange", "")
        category = state.get("category", "general")

        # 从 latest_news 提取预标注摘要
        positive_count = sum(1 for e in recent_events if e.get("llm_sentiment") == "positive")
        negative_count = sum(1 for e in recent_events if e.get("llm_sentiment") == "negative")
        neutral_count = sum(1 for e in recent_events if e.get("llm_sentiment") == "neutral")
        total = positive_count + negative_count
        sentiment_ratio = (positive_count - negative_count) / total if total > 0 else None

        # 同时保留 features 统计作为 fallback
        if isinstance(news_block, dict):
            latest = news_block.get("latest", {}) or {}
            signals = news_block.get("signals", []) or []
        else:
            signals = []

        prompt_vars = dict(
            full_symbol=full_symbol,
            variety_name=variety_name,
            exchange=exchange,
            category=category,
            trade_date=trade_date,
            recent_events=_format_events(recent_events, max_items=50),
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
            conclusion_id = make_conclusion_id("NEWS", 1)
            tagged_report = inject_analyst_id(report_md, analyst_id)
            registry_entry = make_registry_entry(analyst_id, conclusion_id, "NEWS", "news", "news_report", "neutral", extract_first_sentence(report_md))
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
            conclusion_id = make_conclusion_id("NEWS", 1)
            tagged_fallback = inject_analyst_id(fallback_md, analyst_id)
            registry_entry = make_registry_entry(analyst_id, conclusion_id, "NEWS", "news", "news_report", "neutral", "(降级: LLM 不可用)")
            return {
                "news_report": tagged_fallback,
                "messages": [],
                "news_tool_call_count": 0,
                "analyst_registry": registry_entry,
            }

    return news_analyst_node


__all__ = ["create_news_analyst"]
