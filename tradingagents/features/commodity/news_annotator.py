"""
news_annotator.py — 新闻 LLM 标注模块 (Phase 新闻改造)

在数据拉取与消费之间插入统一的 LLM 标注层:
  1. 品种归属标注(从 80+ 品种白名单中选择)
  2. 情感标注(positive/negative/neutral + 置信度 + 推理理由)
  3. 一句话摘要(≤40 字)
  4. 重要度(high/medium/low)

每批最多 10 条,并发多批。content_hash 去重保证幂等。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── 品种白名单(来自 commodity_metadata 的 80+ 品种) ──────────────────────────
# 保持与 commodity_metadata 同步;标注时注入 prompt 要求 LLM 只从中选择
_VARIETY_WHITELIST = [
    # 有色
    "CU", "AL", "ZN", "PB", "NI", "SN", "AO", "BC",
    # 贵金属
    "AU", "AG",
    # 黑色
    "RB", "HC", "I", "J", "JM", "SS", "WR", "SI", "LC", "PS",
    # 能源
    "SC", "FU", "LU", "BU", "PG", "EC", "NR",
    # 化工
    "MA", "TA", "RU", "BR", "SP", "PP", "L", "V", "EG", "EB",
    "PF", "PX", "PR", "SA", "SH", "UR", "FG",
    # 农产品
    "A", "B", "M", "Y", "P", "C", "CS", "JD", "LH",
    "CF", "SR", "CY", "AP", "CJ", "PK", "RM", "OI", "RS",
    # 农副
    "RR", "FB", "BB", "LG",
    # 金融
    "IF", "IH", "IC", "IM", "TS", "TF", "T", "TL",
    # 其他
    "ZC", "SF", "SM",
]

_VARIETY_PROMPT_LINE = "\n".join(
    f"  {v}" for v in _VARIETY_WHITELIST
)

# ── 关键词对照词典(防线 4) ────────────────────────────────────────────────────
_POS_KW: Dict[str, float] = {
    "上涨": 0.5, "大涨": 0.8, "暴涨": 0.9, "涨停": 1.0, "突破": 0.6,
    "创新高": 0.7, "增长": 0.4, "利好": 0.6, "看多": 0.5, "做多": 0.6,
    "提振": 0.5, "回升": 0.4, "反弹": 0.3, "去库": 0.5, "降库": 0.5,
    "需求旺盛": 0.6, "供给紧张": 0.5, "超预期": 0.5,
}
_NEG_KW: Dict[str, float] = {
    "下跌": -0.5, "大跌": -0.8, "暴跌": -0.9, "跌停": -1.0, "破位": -0.6,
    "创新低": -0.7, "下滑": -0.4, "利空": -0.6, "看空": -0.5, "做空": -0.6,
    "承压": -0.4, "回落": -0.3, "累库": -0.5, "垒库": -0.5,
    "需求疲软": -0.5, "供给宽松": -0.4, "不及预期": -0.4,
}


def _compute_content_hash(item: Dict[str, Any]) -> str:
    """sha256(title + content) 作为去重键。"""
    title = str(item.get("title", "") or "")
    content = str(item.get("content", "") or "")
    raw = f"{title}|{content}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _keyword_sentiment(text: str) -> float:
    """关键词情感评分(-1.0 ~ 1.0),用于验证对照。"""
    score = 0.0
    for kw, w in _POS_KW.items():
        if kw in text:
            score += w
    for kw, w in _NEG_KW.items():
        if kw in text:
            score += w
    return max(-1.0, min(1.0, score))


# ── Annotation 模型 ──────────────────────────────────────────────────────────

@dataclass
class NewsAnnotation:
    """单条新闻的 LLM 标注结果。"""
    content_hash: str
    relevant_varieties: List[str]     # ["CU", "AL"] — 品种归属
    sentiment: str                    # "positive" | "negative" | "neutral"
    sentiment_confidence: float       # 0.0 ~ 1.0
    sentiment_reasoning: str          # 必填,至少 10 字
    importance: str                   # "high" | "medium" | "low"
    summary: str                      # ≤40 字
    annotated_at: datetime
    annotator_model: str              # 标注使用的模型
    title: str = ""                   # 原标题(前端展示用)
    content: str = ""                 # 原内容(前端展示用)
    published_at: str = ""            # 原始发布时间
    source: str = ""                  # 新闻来源
    url: str = ""                     # 原始链接

    _review_flag: bool = False        # 内部:需要人工复核
    _keyword_conflict: bool = False   # 内部:关键词对照冲突

    def to_mongo(self) -> Dict[str, Any]:
        d = {
            "content_hash": self.content_hash,
            "relevant_varieties": self.relevant_varieties,
            "sentiment": self.sentiment,
            "sentiment_confidence": self.sentiment_confidence,
            "sentiment_reasoning": self.sentiment_reasoning,
            "importance": self.importance,
            "summary": self.summary,
            "title": self.title,
            "content": self.content,
            "published_at": self.published_at,
            "source": self.source,
            "url": self.url,
            "annotated_at": self.annotated_at,
            "annotator_model": self.annotator_model,
            "_review_flag": self._review_flag,
            "_keyword_conflict": self._keyword_conflict,
        }
        return d

    @classmethod
    def from_mongo(cls, doc: Dict[str, Any]) -> "NewsAnnotation":
        return cls(
            content_hash=doc.get("content_hash", ""),
            relevant_varieties=doc.get("relevant_varieties", []),
            sentiment=doc.get("sentiment", "neutral"),
            sentiment_confidence=float(doc.get("sentiment_confidence", 0.0)),
            sentiment_reasoning=doc.get("sentiment_reasoning", ""),
            importance=doc.get("importance", "medium"),
            summary=doc.get("summary", ""),
            title=doc.get("title", ""),
            content=doc.get("content", ""),
            published_at=doc.get("published_at", ""),
            source=doc.get("source", ""),
            url=doc.get("url", ""),
            annotated_at=doc.get("annotated_at", datetime.min),
            annotator_model=doc.get("annotator_model", ""),
            _review_flag=doc.get("_review_flag", False),
            _keyword_conflict=doc.get("_keyword_conflict", False),
        )


# ── LLM 标注 Prompt ─────────────────────────────────────────────────────────

_ANNOTATION_PROMPT = """你是大宗商品期货新闻标注助手。为以下 {count} 条新闻逐条标注,输出 JSON 数组:

[{format_instructions}]

可用品种代码(仅从中选择,不得自创):
{variety_list}

如果新闻不涉及任何特定品种(如宏观政策、央行决议),
返回 relevant_varieties: [] (空数组,表示全局宏观新闻)。

标注要点:
- 一条新闻可能涉及多个品种,只标注明确提到的
- "positive"=对价格利多,"negative"=对价格利空
- "neutral"用于纯信息类(如交易所公告、数据发布)
- 同一条新闻对不同品种可能方向不同(如美元走强对黄金利空但对出口利多),
  此时选主要受影响品种的方向
- sentiment_reasoning 必填且至少 10 字
- summary 不超过 40 字

新闻列表:
{items_json}
"""


# ── NewsAnnotator ────────────────────────────────────────────────────────────

class NewsAnnotator:
    """新闻 LLM 标注器。

    Args:
        llm: LLM 客户端,需实现 ``invoke(messages)`` 返回含 ``content`` 属性的对象。
        cache_collection: MongoDB 集合或类 dict 对象,需提供:
            - find_one(filter) → dict | None
            - insert_one(doc)
            - create_index(key_or_list, kwargs)  (可选,首次初始化时调用)
        annotator_model: 标注模型名称,写入 annotation 用于质量追踪。
        audit_collection: (可选) 抽样审计集合。
    """

    def __init__(
        self,
        llm: Any,
        cache_collection: Any,
        annotator_model: str = "unknown",
        audit_collection: Any = None,
    ):
        self._llm = llm
        self._cache = cache_collection
        self._audit = audit_collection
        self.annotator_model = annotator_model
        self._annotation_count = 0  # 用于抽样计数

    async def ensure_indexes(self) -> None:
        """确保 MongoDB 索引存在(首次调用时)。"""
        try:
            if hasattr(self._cache, "create_index"):
                await self._cache.create_index("content_hash", unique=True)
                await self._cache.create_index("annotated_at", expireAfterSeconds=604800)
                await self._cache.create_index([("relevant_varieties", 1), ("annotated_at", -1)])
                await self._cache.create_index("sentiment")
        except Exception as exc:
            logger.warning(f"创建索引失败: {exc}")

    async def annotate_batch(
        self,
        items: List[Dict[str, Any]],
        max_concurrent: int = 5,
    ) -> List[Dict[str, Any]]:
        """批量标注:已缓存的直接读取,未标注的调 LLM。

        Args:
            items: 原始新闻列表(每项含 title/content/published_at/source/url 等)。
            max_concurrent: 最大并发批次数。

        Returns:
            合并了标注字段的新闻列表,每项包含原始字段 + 标注字段。
        """
        if not items:
            return []

        # ── 1. 计算 content_hash,区分已标注/未标注 ──
        cached_map: Dict[str, NewsAnnotation] = {}
        uncached: List[Dict[str, Any]] = []

        for item in items:
            h = _compute_content_hash(item)
            item["_content_hash"] = h
            cached = None
            try:
                doc = await self._cache.find_one({"content_hash": h})
                if doc:
                    cached = NewsAnnotation.from_mongo(doc)
            except Exception:
                pass  # MongoDB 不可用,全部走 LLM

            if cached:
                cached_map[h] = cached
            else:
                uncached.append(item)

        # ── 2. 未标注的分批调 LLM ──
        new_annotations: List[NewsAnnotation] = []
        if uncached:
            batches = [uncached[i:i + 10] for i in range(0, len(uncached), 10)]

            sem = asyncio.Semaphore(max_concurrent)

            async def _annotate_one_batch(batch: List[Dict[str, Any]]) -> List[NewsAnnotation]:
                async with sem:
                    return await self._call_llm_batch(batch)

            tasks = [_annotate_one_batch(b) for b in batches]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for r in results:
                if isinstance(r, Exception):
                    logger.error(f"标注批次失败: {r}")
                    continue
                if r:
                    new_annotations.extend(r)

            # ── 3. 写入 MongoDB ──
            for ann in new_annotations:
                try:
                    await self._cache.insert_one(ann.to_mongo())
                except Exception as exc:
                    logger.warning(f"MongoDB insert_one失败: {exc}")

        # ── 4. 合并原始 + 标注 ──
        result: List[Dict[str, Any]] = []
        for item in items:
            h = item.pop("_content_hash", "")
            ann = cached_map.get(h)
            if ann is None:
                ann = next((a for a in new_annotations if a.content_hash == h), None)
            if ann:
                result.append({
                    "published_at": item.get("published_at", ""),
                    "title": item.get("title", ""),
                    "content": item.get("content", ""),
                    "source": item.get("source", ""),
                    "url": item.get("url", ""),
                    "category": item.get("category", ""),
                    "metal": item.get("metal", ""),
                    # 保留原始关键词情感作为对照
                    "sentiment": item.get("sentiment", ""),
                    "sentiment_score": item.get("sentiment_score", 0.0),
                    # LLM 标注字段
                    "relevant_varieties": ann.relevant_varieties,
                    "llm_sentiment": ann.sentiment,
                    "llm_sentiment_confidence": ann.sentiment_confidence,
                    "llm_sentiment_reasoning": ann.sentiment_reasoning,
                    "llm_importance": ann.importance,
                    "llm_summary": ann.summary,
                    "annotated_at": ann.annotated_at.isoformat() if ann.annotated_at else "",
                    "annotator_model": ann.annotator_model,
                    "_review_flag": ann._review_flag,
                })
            else:
                # LLM 失败:返回无标注原始新闻(前端降级显示)
                result.append(item)

        return result

    async def annotate_single(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """实时单条标注。"""
        return (await self.annotate_batch([item]))[0] if item else item

    async def _call_llm_batch(
        self, batch: List[Dict[str, Any]]
    ) -> List[NewsAnnotation]:
        """调 LLM 标注一批(≤10 条)。"""
        # 构造每条的结构
        items_for_prompt = []
        for item in batch:
            title = str(item.get("title", "") or "")[:200]
            content = str(item.get("content", "") or "")[:500]
            items_for_prompt.append({
                "content_hash": _compute_content_hash(item),
                "title": title,
                "content": content,
            })

        prompt_text = _ANNOTATION_PROMPT.format(
            count=len(batch),
            format_instructions="",
            variety_list=_VARIETY_PROMPT_LINE,
            items_json=json.dumps(items_for_prompt, ensure_ascii=False, indent=2),
        )

        try:
            messages = [{"role": "user", "content": prompt_text}]
            response = await self._llm.ainvoke(messages)
            raw_text = ""
            if hasattr(response, "content"):
                raw_text = response.content
                if not isinstance(raw_text, str):
                    raw_text = str(raw_text) if raw_text else ""
            elif isinstance(response, str):
                raw_text = response

            annotations = self._parse_llm_response(raw_text, batch)
            return annotations

        except Exception as e:
            logger.error(f"LLM 批量标注调用失败: {e}")
            return []

    def _parse_llm_response(
        self, raw_text: str, batch: List[Dict[str, Any]]
    ) -> List[NewsAnnotation]:
        """解析 LLM 返回的 JSON,构造 NewsAnnotation 列表。"""
        parsed: List[Dict[str, Any]] = []
        try:
            # 尝试提取 ```json ... ``` 包裹
            if "```json" in raw_text:
                start = raw_text.index("```json") + 7
                end = raw_text.index("```", start) if "```" in raw_text[start:] else len(raw_text)
                raw_text = raw_text[start:end].strip()
            elif "```" in raw_text:
                start = raw_text.index("```") + 3
                end = raw_text.index("```", start) if "```" in raw_text[start:] else len(raw_text)
                raw_text = raw_text[start:end].strip()
            parsed = json.loads(raw_text)
            if isinstance(parsed, dict):
                parsed = [parsed]
        except (json.JSONDecodeError, ValueError):
            logger.warning(f"LLM 返回非 JSON:{raw_text[:200]}")
            return []

        now = datetime.now(timezone.utc)
        result: List[NewsAnnotation] = []
        item_map = {_compute_content_hash(it): it for it in batch}
        audit_samples: List[NewsAnnotation] = []

        for entry in parsed:
            h = entry.get("content_hash", "")
            item = item_map.get(h)
            if not item:
                continue

            sentiment = entry.get("sentiment", "neutral")
            if sentiment not in ("positive", "negative", "neutral"):
                sentiment = "neutral"

            importance = entry.get("importance", "medium")
            if importance not in ("high", "medium", "low"):
                importance = "medium"

            reasoning = str(entry.get("sentiment_reasoning", "") or "")
            if len(reasoning) < 5:
                reasoning = f"{sentiment}情绪(自动化标注)"

            summary = str(entry.get("summary", "") or "")[:40]

            confidence = float(entry.get("sentiment_confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))

            ann = NewsAnnotation(
                content_hash=h,
                relevant_varieties=entry.get("relevant_varieties", []),
                sentiment=sentiment,
                sentiment_confidence=confidence,
                sentiment_reasoning=reasoning,
                importance=importance,
                summary=summary,
                title=str(item.get("title", "") or ""),
                content=str(item.get("content", "") or ""),
                published_at=str(item.get("published_at", "") or ""),
                source=str(item.get("source", "") or ""),
                url=str(item.get("url", "") or ""),
                annotated_at=now,
                annotator_model=self.annotator_model,
            )

            # 防线 4:关键词对照
            text = f"{item.get('title', '')} {item.get('content', '')}"
            kw_score = _keyword_sentiment(text)
            kw_label = "positive" if kw_score >= 0.3 else ("negative" if kw_score <= -0.3 else "neutral")
            if kw_label != sentiment and confidence > 0.8:
                direction_map = {"positive": 1, "negative": -1, "neutral": 0}
                if direction_map.get(kw_label, 0) * direction_map.get(sentiment, 0) < 0:
                    ann.sentiment_confidence *= 0.7
                    ann._keyword_conflict = True
                    logger.warning(
                        f"标注冲突: {item.get('title', '')[:40]} | "
                        f"关键词={kw_score:.2f}({kw_label}) LLM={sentiment}(conf={confidence})"
                    )

            result.append(ann)

            # 防线 5:抽样审计(1%)
            self._annotation_count += 1
            if self._audit is not None and random.random() < 0.01:
                audit_samples.append(ann)

        # 写入审计
        if audit_samples and self._audit is not None:
            try:
                for a in audit_samples:
                    audit_doc = a.to_mongo()
                    audit_doc["audit_status"] = "pending"
                    audit_doc["original_text"] = str(item_map.get(a.content_hash, {}).get("content", ""))[:500]
                    self._audit.insert_one(audit_doc)
            except Exception:
                pass

        return result
