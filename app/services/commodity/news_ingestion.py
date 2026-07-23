"""
news_ingestion.py — 新闻定时拉取 + LLM 标注 Worker

后台定期执行:
1. 并行拉取 shmet 多品种 + global_macro 聚合新闻
2. content_hash + title_fingerprint 去重
3. NewsAnnotator 批量 LLM 标注
4. 写入 MongoDB commodity_news_annotations

注册方式: app/main.py lifespan 中调用 ensure_ingestion_worker()
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

logger = logging.getLogger("webapi")

# 全局 worker task 引用
_ingestion_task: Optional[asyncio.Task] = None

# Worker 运行间隔(秒)
_FETCH_INTERVAL_SECONDS = 60  # 1 分钟拉取一次,NewsAnnotator 自动跳过已标注新闻


def _content_hash(title: str, content: str) -> str:
    return hashlib.sha256(f"{title}|{content}".encode("utf-8")).hexdigest()


# ========================================================================
# LLM 工厂:获取用于标注的快速廉价模型
# ========================================================================

async def _get_annotator_llm() -> Any:
    """获取标注用的快速 LLM，与 agent 层同一来源。

    读取链路与 agent 一致:
      model = unified_config.get_quick_analysis_model()
      provider = normalize_provider_key(await get_provider_by_model_name(model))
    然后用 create_llm_by_provider（返回底层 .get_llm()，有 ainvoke）。
    """
    from app.core.unified_config import unified_config
    from app.services.provider_lookup import get_provider_by_model_name
    from tradingagents.llm_clients.provider_keys import normalize_provider_key
    from tradingagents.graph.trading_graph import create_llm_by_provider

    model = unified_config.get_quick_analysis_model()
    # ⚠️ get_provider_by_model_name 是 async 函数,必须 await。
    # 历史 bug: 未 await 直接传 coroutine 对象给 normalize_provider_key,
    # 导致 provider 变成 "<coroutine object ... at 0x...>",
    # 进而 create_llm_by_provider 抛 Connection error,新闻标注全失败。
    provider_raw = await get_provider_by_model_name(model)
    provider = normalize_provider_key(provider_raw)
    backend_url = unified_config.get_system_settings().get("backend_url", "")

    try:
        llm = create_llm_by_provider(
            provider=provider,
            model=model,
            backend_url=backend_url,
            temperature=0,
            max_tokens=4000,
            timeout=120,
        )
        if llm:
            logger.info(f"✅ 新闻标注模型(agent 同源): {provider}/{model}")
            return llm
    except Exception as e:
        logger.warning(f"创建 agent LLM 失败(provider={provider}, model={model}): {e}")

    # Fallback: create_llm_client + .get_llm()
    try:
        from tradingagents.llm_clients.factory import create_llm_client
        llm_client = create_llm_client(
            provider="deepseek",
            model="deepseek-chat",
            temperature=0,
        )
        llm = llm_client.get_llm()
        if llm:
            logger.info("✅ 新闻标注模型(fallback): deepseek/deepseek-chat")
            return llm
    except Exception as e:
        logger.warning(f"Fallback LLM 创建失败: {e}")

    return None


# ========================================================================
# MongoDB 集合工厂
# ========================================================================

def _get_annotation_collection():
    """获取 commodity_news_annotations 集合。"""
    from app.core.database import get_database
    db = get_database()
    return db["commodity_news_annotations"]


def _get_audit_collection():
    """获取 commodity_news_annotations_audit 集合。"""
    from app.core.database import get_database
    db = get_database()
    return db["commodity_news_annotations_audit"]


# ========================================================================
# 核心 Worker
# ========================================================================

async def _ingest_and_annotate() -> int:
    """执行一次拉取 + 去重 + LLM 标注流水线。

    NewsAnnotator 自动查 MongoDB content_hash 去重,
    仅全新新闻触发 LLM 调用,历史新闻零成本跳过。

    Returns:
        本次标注的新增新闻条数。
    """
    logger.info("📡 [ingest] 开始拉取新闻源...")
    from tradingagents.dataflows.providers.commodity.akshare_futures import (
        AkshareFuturesProvider,
    )
    from tradingagents.annotators.commodity.news_annotator import NewsAnnotator

    provider = AkshareFuturesProvider()
    await provider.connect()

    # ── 并行拉取新闻源(shmet + global_macro) ──
    all_items: List[Dict[str, Any]] = []

    async def _fetch(source_type: str, arg: Any) -> List[Dict[str, Any]]:
        try:
            if source_type == "global_macro":
                result = await provider._synth_global_macro_news(100)
                return result or []
            else:
                result = await provider.get_futures_news(arg, 100)
                return result or []
        except Exception as e:
            logger.debug(f"新闻源拉取失败 {source_type}/{arg}: {e}")
            return []

    shmet_sources = [
        ("shmet", "all"),
        ("shmet", "cu"), ("shmet", "al"), ("shmet", "zn"),
        ("shmet", "ni"), ("shmet", "sn"), ("shmet", "precious"),
    ]

    all_tasks = []
    for s_type, s_arg in shmet_sources:
        all_tasks.append(_fetch(s_type, s_arg))
    all_tasks.append(_fetch("global_macro", None))

    results = await asyncio.gather(*all_tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, Exception):
            continue
        if r:
            all_items.extend(r)

    if not all_items:
        logger.info("⏭️ 新闻拉取结果为空,跳过本轮标注")
        return 0

    # ── content_hash 去重 ──
    seen = set()
    unique: List[Dict[str, Any]] = []
    for item in all_items:
        h = _content_hash(
            str(item.get("title", "") or ""),
            str(item.get("content", "") or ""),
        )
        if h not in seen:
            seen.add(h)
            unique.append(item)

    # ── title_fingerprint 跨源转载去重(前 40 字去标点,同 ingestion 周期内只保留最早一条) ──
    import re as _re
    _fingerprint_seen: set = set()
    _fingerprint_unique: List[Dict[str, Any]] = []
    for item in unique:
        title = str(item.get("title", "") or "")
        fp = _re.sub(r'[^\w\d一-鿿]', '', title)[:40]
        if fp:
            if fp in _fingerprint_seen:
                continue
            _fingerprint_seen.add(fp)
        _fingerprint_unique.append(item)
    unique = _fingerprint_unique

    logger.info(f"📰 新闻拉取: {len(all_items)} 条总, {len(unique)} 条去重后")

    # ── LLM 标注(NewsAnnotator 自动跳过已缓存) ──
    llm = await _get_annotator_llm()
    if not llm:
        logger.warning("⏭️ 标注 LLM 不可用,跳过本轮标注")
        return 0

    annotator = NewsAnnotator(
        llm=llm,
        cache_collection=_get_annotation_collection(),
        annotator_model=getattr(llm, "model_name", "unknown"),
        audit_collection=_get_audit_collection(),
    )
    await annotator.ensure_indexes()
    annotated = await annotator.annotate_batch(unique, max_concurrent=5)

    logger.info(f"✅ 新闻入库: {len(unique)} 条拉取, {len(annotated)} 条已标注")
    return len(annotated)


async def _run_ingestion_loop() -> None:
    """后台循环:每 {_FETCH_INTERVAL_SECONDS} 秒拉取新闻并标注。

    NewsAnnotator 内部通过 content_hash 查 MongoDB 去重,
    仅全新新闻产生 LLM 调用,已标注的新闻零成本跳过。
    """
    logger.info("🚀 新闻标注 Worker 启动: 间隔=%ds, 自动跳过已缓存新闻", _FETCH_INTERVAL_SECONDS)

    # 启动时立即执行一次
    try:
        count = await _ingest_and_annotate()
        logger.info(f"✅ 首次新闻拉取+标注完成: {count} 条新标注")
    except Exception as e:
        logger.error(f"❌ 首次新闻标注失败: {e}")

    tick_count = 0
    while True:
        # 关键: sleep 必须等够才能让 tick 心跳按节奏出来
        await asyncio.sleep(_FETCH_INTERVAL_SECONDS)
        tick_count += 1
        logger.info(f"⏰ [ingest loop] tick={tick_count} 开始新一轮")
        try:
            count = await _ingest_and_annotate()
            if count:
                logger.info(f"✅ 新增 {count} 条新闻已标注 (tick={tick_count})")
            else:
                logger.debug(f"⏭️ 本轮 tick={tick_count} 无新增新闻 (worker 存活)")
        except Exception as e:
            logger.error(f"❌ 定时新闻拉取失败 (tick={tick_count}): {e}")


# ========================================================================
# 生命周期接口(供 app/main.py lifespan 调用)
# ========================================================================

def ensure_ingestion_worker() -> None:
    """启动新闻标注后台 worker(若未运行)。"""
    global _ingestion_task
    if _ingestion_task is None or _ingestion_task.done():
        _ingestion_task = asyncio.create_task(_run_ingestion_loop())
        logger.info("🚀 新闻标注 worker 已启动(间隔=%ds, 自动跳过已缓存)", _FETCH_INTERVAL_SECONDS)


async def stop_ingestion_worker() -> None:
    """停止新闻标注后台 worker。"""
    global _ingestion_task
    if _ingestion_task and not _ingestion_task.done():
        _ingestion_task.cancel()
        try:
            await _ingestion_task
        except asyncio.CancelledError:
            pass
        _ingestion_task = None
        logger.info("🛑 新闻标注 worker 已停止")
