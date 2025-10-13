"""
TradingAgents-CN v1.0.0-preview FastAPI Backend
主应用程序入口

Copyright (c) 2025 hsliuping. All rights reserved.
版权所有 (c) 2025 hsliuping。保留所有权利。

This software is proprietary and confidential. Unauthorized copying, distribution,
or use of this software, via any medium, is strictly prohibited.
本软件为专有和机密软件。严禁通过任何媒介未经授权复制、分发或使用本软件。

For commercial licensing, please contact: hsliup@163.com
商业许可咨询，请联系：hsliup@163.com
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import logging
import time
from contextlib import asynccontextmanager
import asyncio

from app.core.config import settings
from app.core.database import init_db, close_db
from app.core.logging_config import setup_logging
from app.routers import auth, analysis, screening, queue, sse, health, favorites, config, reports, database, operation_logs, tags, tushare_init, akshare_init, baostock_init, historical_data, multi_period_sync, financial_data, news_data, social_media, internal_messages, usage_statistics, model_capabilities
from app.routers import sync as sync_router, multi_source_sync
from app.routers import stocks as stocks_router
from app.routers import stock_data as stock_data_router
from app.routers import notifications as notifications_router
from app.routers import scheduler as scheduler_router
from app.services.basics_sync_service import get_basics_sync_service
from app.services.scheduler_service import set_scheduler_instance
from app.worker.tushare_sync_service import (
    run_tushare_basic_info_sync,
    run_tushare_quotes_sync,
    run_tushare_historical_sync,
    run_tushare_financial_sync,
    run_tushare_status_check
)
from app.worker.akshare_sync_service import (
    run_akshare_basic_info_sync,
    run_akshare_quotes_sync,
    run_akshare_historical_sync,
    run_akshare_financial_sync,
    run_akshare_status_check
)
from app.worker.baostock_sync_service import (
    run_baostock_basic_info_sync,
    run_baostock_quotes_sync,
    run_baostock_historical_sync,
    run_baostock_status_check
)
from app.middleware.operation_log_middleware import OperationLogMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from app.services.quotes_ingestion_service import QuotesIngestionService
from app.routers import paper as paper_router


async def _print_config_summary(logger):
    """显示配置摘要"""
    try:
        logger.info("=" * 70)
        logger.info("📋 TradingAgents-CN Configuration Summary")
        logger.info("=" * 70)

        # 环境信息
        env = "Production" if settings.is_production else "Development"
        logger.info(f"Environment: {env}")

        # 数据库连接
        logger.info(f"MongoDB: {settings.MONGODB_HOST}:{settings.MONGODB_PORT}/{settings.MONGODB_DATABASE}")
        logger.info(f"Redis: {settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}")

        # 检查大模型配置
        try:
            from app.services.config_service import config_service
            config = await config_service.get_system_config()
            if config and config.llm_configs:
                enabled_llms = [llm for llm in config.llm_configs if llm.enabled]
                logger.info(f"Enabled LLMs: {len(enabled_llms)}")
                if enabled_llms:
                    for llm in enabled_llms[:3]:  # 只显示前3个
                        logger.info(f"  • {llm.provider.value}: {llm.model_name}")
                    if len(enabled_llms) > 3:
                        logger.info(f"  • ... and {len(enabled_llms) - 3} more")
                else:
                    logger.warning("⚠️  No LLM enabled. Please configure at least one LLM in Web UI.")
            else:
                logger.warning("⚠️  No LLM configured. Please configure at least one LLM in Web UI.")
        except Exception as e:
            logger.warning(f"⚠️  Failed to check LLM configs: {e}")

        # 检查数据源配置
        try:
            if config and config.data_source_configs:
                enabled_sources = [ds for ds in config.data_source_configs if ds.enabled]
                logger.info(f"Enabled Data Sources: {len(enabled_sources)}")
                if enabled_sources:
                    for ds in enabled_sources[:3]:  # 只显示前3个
                        logger.info(f"  • {ds.type.value}: {ds.name}")
                    if len(enabled_sources) > 3:
                        logger.info(f"  • ... and {len(enabled_sources) - 3} more")
            else:
                logger.info("Data Sources: Using default (AKShare)")
        except Exception as e:
            logger.warning(f"⚠️  Failed to check data source configs: {e}")

        logger.info("=" * 70)
    except Exception as e:
        logger.error(f"Failed to print config summary: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    setup_logging()
    logger = logging.getLogger("app.main")

    # 验证启动配置
    try:
        from app.core.startup_validator import validate_startup_config
        validate_startup_config()
    except Exception as e:
        logger.error(f"配置验证失败: {e}")
        raise

    await init_db()

    # 🔧 配置桥接：将统一配置写入环境变量，供 TradingAgents 核心库使用
    try:
        from app.core.config_bridge import bridge_config_to_env
        bridge_config_to_env()
    except Exception as e:
        logger.warning(f"⚠️  配置桥接失败: {e}")
        logger.warning("⚠️  TradingAgents 将使用 .env 文件中的配置")

    # Apply dynamic settings (log_level, enable_monitoring) from ConfigProvider
    try:
        from app.services.config_provider import provider as config_provider  # local import to avoid early DB init issues
        eff = await config_provider.get_effective_system_settings()
        desired_level = str(eff.get("log_level", "INFO")).upper()
        setup_logging(log_level=desired_level)
        for name in ("webapi", "worker", "uvicorn", "fastapi"):
            logging.getLogger(name).setLevel(desired_level)
        try:
            from app.middleware.operation_log_middleware import set_operation_log_enabled
            set_operation_log_enabled(bool(eff.get("enable_monitoring", True)))
        except Exception:
            pass
    except Exception as e:
        logging.getLogger("webapi").warning(f"Failed to apply dynamic settings: {e}")

    # 显示配置摘要
    await _print_config_summary(logger)

    logger.info("TradingAgents FastAPI backend started")

    # 启动期：若需要在休市时补充上一交易日收盘快照
    if settings.QUOTES_BACKFILL_ON_STARTUP:
        try:
            qi = QuotesIngestionService()
            await qi.ensure_indexes()
            await qi.backfill_last_close_snapshot_if_needed()
        except Exception as e:
            logger.warning(f"Startup backfill failed (ignored): {e}")

    # 启动每日定时任务：可配置
    scheduler: AsyncIOScheduler | None = None
    try:
        from croniter import croniter
    except Exception:
        croniter = None  # 可选依赖
    try:
        scheduler = AsyncIOScheduler(timezone=settings.TIMEZONE)
        service = get_basics_sync_service()
        # 立即在启动后尝试一次（不阻塞）
        asyncio.create_task(service.run_full_sync(force=False))

        # 配置调度：优先使用 CRON，其次使用 HH:MM
        if settings.SYNC_STOCK_BASICS_ENABLED:
            if settings.SYNC_STOCK_BASICS_CRON:
                # 如果提供了cron表达式
                scheduler.add_job(
                    service.run_full_sync,  # coroutine function; AsyncIOScheduler will await it
                    CronTrigger.from_crontab(settings.SYNC_STOCK_BASICS_CRON, timezone=settings.TIMEZONE),
                    id="basics_sync_service"
                )
                logger.info(f"📅 Stock basics sync scheduled by CRON: {settings.SYNC_STOCK_BASICS_CRON} ({settings.TIMEZONE})")
            else:
                hh, mm = (settings.SYNC_STOCK_BASICS_TIME or "06:30").split(":")
                scheduler.add_job(
                    service.run_full_sync,  # coroutine function; AsyncIOScheduler will await it
                    CronTrigger(hour=int(hh), minute=int(mm), timezone=settings.TIMEZONE),
                    id="basics_sync_service"
                )
                logger.info(f"📅 Stock basics sync scheduled daily at {settings.SYNC_STOCK_BASICS_TIME} ({settings.TIMEZONE})")

        # 实时行情入库任务（每N秒），内部自判交易时段
        if settings.QUOTES_INGEST_ENABLED:
            quotes_ingestion = QuotesIngestionService()
            await quotes_ingestion.ensure_indexes()
            scheduler.add_job(
                quotes_ingestion.run_once,  # coroutine function; AsyncIOScheduler will await it
                IntervalTrigger(seconds=settings.QUOTES_INGEST_INTERVAL_SECONDS, timezone=settings.TIMEZONE),
                id="quotes_ingestion_service"
            )
            logger.info(f"⏱ 实时行情入库任务已启动: 每 {settings.QUOTES_INGEST_INTERVAL_SECONDS}s")

        # Tushare统一数据同步任务配置
        if settings.TUSHARE_UNIFIED_ENABLED:
            logger.info("🔄 配置Tushare统一数据同步任务...")

            # 基础信息同步任务
            if settings.TUSHARE_BASIC_INFO_SYNC_ENABLED:
                scheduler.add_job(
                    run_tushare_basic_info_sync,
                    CronTrigger.from_crontab(settings.TUSHARE_BASIC_INFO_SYNC_CRON, timezone=settings.TIMEZONE),
                    id="tushare_basic_info_sync",
                    kwargs={"force_update": False}
                )
                logger.info(f"📅 Tushare基础信息同步已配置: {settings.TUSHARE_BASIC_INFO_SYNC_CRON}")

            # 实时行情同步任务
            if settings.TUSHARE_QUOTES_SYNC_ENABLED:
                scheduler.add_job(
                    run_tushare_quotes_sync,
                    CronTrigger.from_crontab(settings.TUSHARE_QUOTES_SYNC_CRON, timezone=settings.TIMEZONE),
                    id="tushare_quotes_sync"
                )
                logger.info(f"📈 Tushare行情同步已配置: {settings.TUSHARE_QUOTES_SYNC_CRON}")

            # 历史数据同步任务
            if settings.TUSHARE_HISTORICAL_SYNC_ENABLED:
                scheduler.add_job(
                    run_tushare_historical_sync,
                    CronTrigger.from_crontab(settings.TUSHARE_HISTORICAL_SYNC_CRON, timezone=settings.TIMEZONE),
                    id="tushare_historical_sync",
                    kwargs={"incremental": True}
                )
                logger.info(f"📊 Tushare历史数据同步已配置: {settings.TUSHARE_HISTORICAL_SYNC_CRON}")

            # 财务数据同步任务
            if settings.TUSHARE_FINANCIAL_SYNC_ENABLED:
                scheduler.add_job(
                    run_tushare_financial_sync,
                    CronTrigger.from_crontab(settings.TUSHARE_FINANCIAL_SYNC_CRON, timezone=settings.TIMEZONE),
                    id="tushare_financial_sync"
                )
                logger.info(f"💰 Tushare财务数据同步已配置: {settings.TUSHARE_FINANCIAL_SYNC_CRON}")

            # 状态检查任务
            if settings.TUSHARE_STATUS_CHECK_ENABLED:
                scheduler.add_job(
                    run_tushare_status_check,
                    CronTrigger.from_crontab(settings.TUSHARE_STATUS_CHECK_CRON, timezone=settings.TIMEZONE),
                    id="tushare_status_check"
                )
                logger.info(f"🔍 Tushare状态检查已配置: {settings.TUSHARE_STATUS_CHECK_CRON}")

        # AKShare统一数据同步任务配置
        logger.info("🔄 配置AKShare统一数据同步任务...")

        # 基础信息同步任务
        scheduler.add_job(
            run_akshare_basic_info_sync,
            CronTrigger.from_crontab(settings.AKSHARE_BASIC_INFO_SYNC_CRON, timezone=settings.TIMEZONE),
            id="akshare_basic_info_sync",
            kwargs={"force_update": False}
        )
        if not (settings.AKSHARE_UNIFIED_ENABLED and settings.AKSHARE_BASIC_INFO_SYNC_ENABLED):
            scheduler.pause_job("akshare_basic_info_sync")
            logger.info(f"⏸️ AKShare基础信息同步已添加但暂停: {settings.AKSHARE_BASIC_INFO_SYNC_CRON}")
        else:
            logger.info(f"📅 AKShare基础信息同步已配置: {settings.AKSHARE_BASIC_INFO_SYNC_CRON}")

        # 实时行情同步任务
        scheduler.add_job(
            run_akshare_quotes_sync,
            CronTrigger.from_crontab(settings.AKSHARE_QUOTES_SYNC_CRON, timezone=settings.TIMEZONE),
            id="akshare_quotes_sync"
        )
        if not (settings.AKSHARE_UNIFIED_ENABLED and settings.AKSHARE_QUOTES_SYNC_ENABLED):
            scheduler.pause_job("akshare_quotes_sync")
            logger.info(f"⏸️ AKShare行情同步已添加但暂停: {settings.AKSHARE_QUOTES_SYNC_CRON}")
        else:
            logger.info(f"📈 AKShare行情同步已配置: {settings.AKSHARE_QUOTES_SYNC_CRON}")

        # 历史数据同步任务
        scheduler.add_job(
            run_akshare_historical_sync,
            CronTrigger.from_crontab(settings.AKSHARE_HISTORICAL_SYNC_CRON, timezone=settings.TIMEZONE),
            id="akshare_historical_sync",
            kwargs={"incremental": True}
        )
        if not (settings.AKSHARE_UNIFIED_ENABLED and settings.AKSHARE_HISTORICAL_SYNC_ENABLED):
            scheduler.pause_job("akshare_historical_sync")
            logger.info(f"⏸️ AKShare历史数据同步已添加但暂停: {settings.AKSHARE_HISTORICAL_SYNC_CRON}")
        else:
            logger.info(f"📊 AKShare历史数据同步已配置: {settings.AKSHARE_HISTORICAL_SYNC_CRON}")

        # 财务数据同步任务
        scheduler.add_job(
            run_akshare_financial_sync,
            CronTrigger.from_crontab(settings.AKSHARE_FINANCIAL_SYNC_CRON, timezone=settings.TIMEZONE),
            id="akshare_financial_sync"
        )
        if not (settings.AKSHARE_UNIFIED_ENABLED and settings.AKSHARE_FINANCIAL_SYNC_ENABLED):
            scheduler.pause_job("akshare_financial_sync")
            logger.info(f"⏸️ AKShare财务数据同步已添加但暂停: {settings.AKSHARE_FINANCIAL_SYNC_CRON}")
        else:
            logger.info(f"💰 AKShare财务数据同步已配置: {settings.AKSHARE_FINANCIAL_SYNC_CRON}")

        # 状态检查任务
        scheduler.add_job(
            run_akshare_status_check,
            CronTrigger.from_crontab(settings.AKSHARE_STATUS_CHECK_CRON, timezone=settings.TIMEZONE),
            id="akshare_status_check"
        )
        if not (settings.AKSHARE_UNIFIED_ENABLED and settings.AKSHARE_STATUS_CHECK_ENABLED):
            scheduler.pause_job("akshare_status_check")
            logger.info(f"⏸️ AKShare状态检查已添加但暂停: {settings.AKSHARE_STATUS_CHECK_CRON}")
        else:
            logger.info(f"🔍 AKShare状态检查已配置: {settings.AKSHARE_STATUS_CHECK_CRON}")

        # BaoStock统一数据同步任务配置
        logger.info("🔄 配置BaoStock统一数据同步任务...")

        # 基础信息同步任务
        scheduler.add_job(
            run_baostock_basic_info_sync,
            CronTrigger.from_crontab(settings.BAOSTOCK_BASIC_INFO_SYNC_CRON, timezone=settings.TIMEZONE),
            id="baostock_basic_info_sync"
        )
        if not (settings.BAOSTOCK_UNIFIED_ENABLED and settings.BAOSTOCK_BASIC_INFO_SYNC_ENABLED):
            scheduler.pause_job("baostock_basic_info_sync")
            logger.info(f"⏸️ BaoStock基础信息同步已添加但暂停: {settings.BAOSTOCK_BASIC_INFO_SYNC_CRON}")
        else:
            logger.info(f"📋 BaoStock基础信息同步已配置: {settings.BAOSTOCK_BASIC_INFO_SYNC_CRON}")

        # 行情同步任务
        scheduler.add_job(
            run_baostock_quotes_sync,
            CronTrigger.from_crontab(settings.BAOSTOCK_QUOTES_SYNC_CRON, timezone=settings.TIMEZONE),
            id="baostock_quotes_sync"
        )
        if not (settings.BAOSTOCK_UNIFIED_ENABLED and settings.BAOSTOCK_QUOTES_SYNC_ENABLED):
            scheduler.pause_job("baostock_quotes_sync")
            logger.info(f"⏸️ BaoStock行情同步已添加但暂停: {settings.BAOSTOCK_QUOTES_SYNC_CRON}")
        else:
            logger.info(f"📈 BaoStock行情同步已配置: {settings.BAOSTOCK_QUOTES_SYNC_CRON}")

        # 历史数据同步任务
        scheduler.add_job(
            run_baostock_historical_sync,
            CronTrigger.from_crontab(settings.BAOSTOCK_HISTORICAL_SYNC_CRON, timezone=settings.TIMEZONE),
            id="baostock_historical_sync"
        )
        if not (settings.BAOSTOCK_UNIFIED_ENABLED and settings.BAOSTOCK_HISTORICAL_SYNC_ENABLED):
            scheduler.pause_job("baostock_historical_sync")
            logger.info(f"⏸️ BaoStock历史数据同步已添加但暂停: {settings.BAOSTOCK_HISTORICAL_SYNC_CRON}")
        else:
            logger.info(f"📊 BaoStock历史数据同步已配置: {settings.BAOSTOCK_HISTORICAL_SYNC_CRON}")

        # 状态检查任务
        scheduler.add_job(
            run_baostock_status_check,
            CronTrigger.from_crontab(settings.BAOSTOCK_STATUS_CHECK_CRON, timezone=settings.TIMEZONE),
            id="baostock_status_check"
        )
        if not (settings.BAOSTOCK_UNIFIED_ENABLED and settings.BAOSTOCK_STATUS_CHECK_ENABLED):
            scheduler.pause_job("baostock_status_check")
            logger.info(f"⏸️ BaoStock状态检查已添加但暂停: {settings.BAOSTOCK_STATUS_CHECK_CRON}")
        else:
            logger.info(f"🔍 BaoStock状态检查已配置: {settings.BAOSTOCK_STATUS_CHECK_CRON}")

        # 新闻数据同步任务配置（使用AKShare同步所有股票新闻）
        if settings.NEWS_SYNC_ENABLED:
            logger.info("🔄 配置新闻数据同步任务...")

            from app.worker.akshare_sync_service import get_akshare_sync_service

            async def run_news_sync():
                """运行新闻同步任务 - 使用AKShare同步所有股票新闻"""
                try:
                    logger.info("📰 开始新闻数据同步（AKShare）...")
                    service = await get_akshare_sync_service()
                    result = await service.sync_news_data(
                        symbols=None,  # None表示同步所有股票
                        max_news_per_stock=settings.NEWS_SYNC_MAX_PER_SOURCE
                    )
                    logger.info(
                        f"✅ 新闻同步完成: "
                        f"处理{result['total_processed']}只股票, "
                        f"成功{result['success_count']}只, "
                        f"失败{result['error_count']}只, "
                        f"新闻总数{result['news_count']}条, "
                        f"耗时{(datetime.utcnow() - result['start_time']).total_seconds():.2f}秒"
                    )
                except Exception as e:
                    logger.error(f"❌ 新闻同步失败: {e}", exc_info=True)

            scheduler.add_job(
                run_news_sync,
                CronTrigger.from_crontab(settings.NEWS_SYNC_CRON, timezone=settings.TIMEZONE),
                id="news_sync"
            )
            logger.info(f"📰 新闻数据同步已配置: {settings.NEWS_SYNC_CRON}")

        scheduler.start()

        # 设置调度器实例到服务中，以便API可以管理任务
        set_scheduler_instance(scheduler)
        logger.info("✅ 调度器服务已初始化")
    except Exception as e:
        logger.warning(f"Failed to start scheduler: {e}")

    try:
        yield
    finally:
        # 关闭时清理
        if scheduler:
            try:
                scheduler.shutdown(wait=False)
                logger.info("🛑 Scheduler stopped")
            except Exception as e:
                logger.warning(f"Scheduler shutdown error: {e}")
        await close_db()
        logger.info("TradingAgents FastAPI backend stopped")


# 创建FastAPI应用
app = FastAPI(
    title="TradingAgents-CN API",
    description="股票分析与批量队列系统 API",
    version="0.1.16",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan
)

# 安全中间件
if not settings.DEBUG:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.ALLOWED_HOSTS
    )

# CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# 操作日志中间件
app.add_middleware(OperationLogMiddleware)


# 请求日志中间件
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()

    # 跳过健康检查和静态文件请求的日志
    if request.url.path in ["/health", "/favicon.ico"] or request.url.path.startswith("/static"):
        response = await call_next(request)
        return response

    # 使用webapi logger记录请求
    logger = logging.getLogger("webapi")
    logger.info(f"🔄 {request.method} {request.url.path} - 开始处理")

    response = await call_next(request)
    process_time = time.time() - start_time

    # 记录请求完成
    status_emoji = "✅" if response.status_code < 400 else "❌"
    logger.info(f"{status_emoji} {request.method} {request.url.path} - 状态: {response.status_code} - 耗时: {process_time:.3f}s")

    return response


# 全局异常处理
# 请求ID/Trace-ID 中间件（需作为最外层，放在函数式中间件之后）
from app.middleware.request_id import RequestIDMiddleware
app.add_middleware(RequestIDMiddleware)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logging.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Internal server error occurred",
                "request_id": getattr(request.state, "request_id", None)
            }
        }
    )


# 测试端点 - 验证中间件是否工作
@app.get("/api/test-log")
async def test_log():
    """测试日志中间件是否工作"""
    print("🧪 测试端点被调用 - 这条消息应该出现在控制台")
    return {"message": "测试成功", "timestamp": time.time()}

# 注册路由
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(auth.router, prefix="/api/auth", tags=["authentication"])
app.include_router(analysis.router, prefix="/api/analysis", tags=["analysis"])
app.include_router(reports.router, tags=["reports"])
app.include_router(screening.router, prefix="/api/screening", tags=["screening"])
app.include_router(queue.router, prefix="/api/queue", tags=["queue"])
app.include_router(favorites.router, prefix="/api", tags=["favorites"])
app.include_router(stocks_router.router, prefix="/api", tags=["stocks"])
app.include_router(stock_data_router.router, tags=["stock-data"])
app.include_router(tags.router, prefix="/api", tags=["tags"])
app.include_router(config.router, prefix="/api", tags=["config"])
app.include_router(model_capabilities.router, tags=["model-capabilities"])
app.include_router(usage_statistics.router, tags=["usage-statistics"])
app.include_router(database.router, prefix="/api/system", tags=["database"])
app.include_router(operation_logs.router, prefix="/api/system", tags=["operation_logs"])
# 新增：系统配置只读摘要
from app.routers import system_config as system_config_router
app.include_router(system_config_router.router, prefix="/api/system", tags=["system"])

# 通知模块（REST + SSE）
app.include_router(notifications_router.router, prefix="/api", tags=["notifications"])

# 定时任务管理
app.include_router(scheduler_router.router, tags=["scheduler"])

app.include_router(sse.router, prefix="/api/stream", tags=["streaming"])
app.include_router(sync_router.router)
app.include_router(multi_source_sync.router)
app.include_router(paper_router.router, prefix="/api", tags=["paper"])
app.include_router(tushare_init.router, prefix="/api", tags=["tushare-init"])
app.include_router(akshare_init.router, prefix="/api", tags=["akshare-init"])
app.include_router(baostock_init.router, prefix="/api", tags=["baostock-init"])
app.include_router(historical_data.router, tags=["historical-data"])
app.include_router(multi_period_sync.router, tags=["multi-period-sync"])
app.include_router(financial_data.router, tags=["financial-data"])
app.include_router(news_data.router, tags=["news-data"])
app.include_router(social_media.router, tags=["social-media"])
app.include_router(internal_messages.router, tags=["internal-messages"])


@app.get("/")
async def root():
    """根路径，返回API信息"""
    print("🏠 根路径被访问")
    return {
        "name": "TradingAgents-CN API",
        "version": "0.1.16",
        "status": "running",
        "docs_url": "/docs" if settings.DEBUG else None
    }


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info",
        reload_dirs=["app"] if settings.DEBUG else None,
        reload_excludes=[
            "__pycache__",
            "*.pyc",
            "*.pyo",
            "*.pyd",
            ".git",
            ".pytest_cache",
            "*.log",
            "*.tmp"
        ] if settings.DEBUG else None,
        reload_includes=["*.py"] if settings.DEBUG else None
    )