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
from datetime import datetime
from contextlib import asynccontextmanager
import asyncio
from pathlib import Path

from app.core.config import settings
from app.core.database import init_db, close_db
from app.core.logging_config import setup_logging
from app.routers import auth_db as auth, queue, sse, health, config, reports, database, operation_logs, tags, internal_messages, usage_statistics, model_capabilities, cache, logs
from app.routers import notifications as notifications_router
from app.routers import websocket_notifications as websocket_notifications_router
from app.middleware.operation_log_middleware import OperationLogMiddleware

# 模块级 logger(供商品模块条件 include_router 的 else 分支等场景使用)
logger = logging.getLogger("app.main")


def get_version() -> str:
    """从 VERSION 文件读取版本号"""
    try:
        version_file = Path(__file__).parent.parent / "VERSION"
        if version_file.exists():
            return version_file.read_text(encoding='utf-8').strip()
    except Exception:
        pass
    return "1.0.0"  # 默认版本号


async def _print_config_summary(logger):
    """显示配置摘要"""
    try:
        logger.info("=" * 70)
        logger.info("📋 TradingAgents-CN Configuration Summary")
        logger.info("=" * 70)

        # .env 文件路径信息
        import os
        from pathlib import Path
        
        current_dir = Path.cwd()
        logger.info(f"📁 Current working directory: {current_dir}")
        
        # 检查可能的 .env 文件位置
        env_files_to_check = [
            current_dir / ".env",
            current_dir / "app" / ".env",
            Path(__file__).parent.parent / ".env",  # 项目根目录
        ]
        
        logger.info("🔍 Checking .env file locations:")
        env_file_found = False
        for env_file in env_files_to_check:
            if env_file.exists():
                logger.info(f"  ✅ Found: {env_file} (size: {env_file.stat().st_size} bytes)")
                env_file_found = True
                # 显示文件的前几行（隐藏敏感信息）
                try:
                    with open(env_file, 'r', encoding='utf-8') as f:
                        lines = f.readlines()[:5]  # 只读前5行
                        logger.info(f"     Preview (first 5 lines):")
                        for i, line in enumerate(lines, 1):
                            # 隐藏包含密码、密钥等敏感信息的行
                            if any(keyword in line.upper() for keyword in ['PASSWORD', 'SECRET', 'KEY', 'TOKEN']):
                                logger.info(f"       {i}: {line.split('=')[0]}=***")
                            else:
                                logger.info(f"       {i}: {line.strip()}")
                except Exception as e:
                    logger.warning(f"     Could not preview file: {e}")
            else:
                logger.info(f"  ❌ Not found: {env_file}")
        
        if not env_file_found:
            logger.warning("⚠️  No .env file found in checked locations")
        
        # Pydantic Settings 配置加载状态
        logger.info("⚙️  Pydantic Settings Configuration:")
        logger.info(f"  • Settings class: {settings.__class__.__name__}")
        logger.info(f"  • Config source: {getattr(settings.model_config, 'env_file', 'Not specified')}")
        logger.info(f"  • Encoding: {getattr(settings.model_config, 'env_file_encoding', 'Not specified')}")
        
        # 显示一些关键配置值的来源（环境变量 vs 默认值）
        key_settings = ['HOST', 'PORT', 'DEBUG', 'MONGODB_HOST', 'REDIS_HOST']
        logger.info("  • Key settings sources:")
        for setting_name in key_settings:
            env_var_name = setting_name
            env_value = os.getenv(env_var_name)
            config_value = getattr(settings, setting_name, None)
            if env_value is not None:
                logger.info(f"    - {setting_name}: from environment variable ({config_value})")
            else:
                logger.info(f"    - {setting_name}: using default value ({config_value})")
        
        # 环境信息
        env = "Production" if settings.is_production else "Development"
        logger.info(f"Environment: {env}")

        # 数据库连接
        logger.info(f"MongoDB: {settings.MONGODB_HOST}:{settings.MONGODB_PORT}/{settings.MONGODB_DATABASE}")
        logger.info(f"Redis: {settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}")

        # 代理配置
        import os
        if settings.HTTP_PROXY or settings.HTTPS_PROXY:
            logger.info("Proxy Configuration:")
            if settings.HTTP_PROXY:
                logger.info(f"  HTTP_PROXY: {settings.HTTP_PROXY}")
            if settings.HTTPS_PROXY:
                logger.info(f"  HTTPS_PROXY: {settings.HTTPS_PROXY}")
            if settings.NO_PROXY:
                # 只显示前3个域名
                no_proxy_list = settings.NO_PROXY.split(',')
                if len(no_proxy_list) <= 3:
                    logger.info(f"  NO_PROXY: {settings.NO_PROXY}")
                else:
                    logger.info(f"  NO_PROXY: {','.join(no_proxy_list[:3])}... ({len(no_proxy_list)} domains)")
            logger.info(f"  ✅ Proxy environment variables set successfully")
        else:
            logger.info("Proxy: Not configured (direct connection)")

        # 检查大模型配置
        try:
            from app.services.config_service import config_service
            config = await config_service.get_system_config()
            if config and config.llm_configs:
                enabled_llms = [llm for llm in config.llm_configs if llm.enabled]
                logger.info(f"Enabled LLMs: {len(enabled_llms)}")
                if enabled_llms:
                    for llm in enabled_llms[:3]:  # 只显示前3个
                        logger.info(f"  • {llm.provider}: {llm.model_name}")
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

    #  配置桥接：将统一配置写入环境变量，供 TradingAgents 核心库使用
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

    # Phase 5+: 商品分析任务回填 + 卡死任务清理
    try:
        from app.routers.commodity.analysis import (
            _backfill_completed_tasks,
            _tasks_collection,
        )
        if settings.FEATURE_COMMODITY_ANALYSIS:
            count = await _backfill_completed_tasks()
            logger.info(f"✅ 商品任务回填: {count} 条历史报告已导入任务中心")

            # 把卡在 processing 的老任务标为 failed (服务重启等场景)
            coll = _tasks_collection()
            if coll is not None:
                from datetime import datetime, timedelta
                cutoff = datetime.utcnow() - timedelta(minutes=5)
                result = await coll.update_many(
                    {"status": "processing", "created_at": {"$lt": cutoff}},
                    {"$set": {
                        "status": "failed",
                        "error_message": "服务重启,任务中断",
                        "completed_at": datetime.utcnow(),
                    }},
                )
                if result.modified_count > 0:
                    logger.info(
                        f"✅ 商品任务清理: {result.modified_count} 条 processing 任务被标记为失败"
                    )
    except Exception as e:
        logger.warning(f"⚠️ 商品任务初始化失败 (非阻塞): {e}")

    logger.info("TradingAgents FastAPI backend started")

    try:
        yield
    finally:
        # 关闭 UserService MongoDB 连接
        try:
            from app.services.user_service import user_service
            user_service.close()
        except Exception as e:
            logger.warning(f"UserService cleanup error: {e}")

        await close_db()
        logger.info("TradingAgents FastAPI backend stopped")


# 创建FastAPI应用
app = FastAPI(
    title="TradingAgents-CN API",
    description="大宗商品分析与批量队列系统 API",
    version=get_version(),
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
app.include_router(reports.router, tags=["reports"])
app.include_router(queue.router, prefix="/api/queue", tags=["queue"])
app.include_router(tags.router, prefix="/api", tags=["tags"])
app.include_router(config.router, prefix="/api", tags=["config"])
app.include_router(model_capabilities.router, tags=["model-capabilities"])
app.include_router(usage_statistics.router, tags=["usage-statistics"])
app.include_router(database.router, prefix="/api/system", tags=["database"])
app.include_router(cache.router, tags=["cache"])
app.include_router(operation_logs.router, prefix="/api/system", tags=["operation_logs"])
app.include_router(logs.router, prefix="/api/system", tags=["logs"])
# 新增：系统配置只读摘要
from app.routers import system_config as system_config_router
app.include_router(system_config_router.router, prefix="/api/system", tags=["system"])

# 通知模块（REST + SSE）
app.include_router(notifications_router.router, prefix="/api", tags=["notifications"])

# 🔥 WebSocket 通知模块（替代 SSE + Redis PubSub）
app.include_router(websocket_notifications_router.router, prefix="/api", tags=["websocket"])

app.include_router(sse.router, prefix="/api/stream", tags=["streaming"])
app.include_router(internal_messages.router, tags=["internal-messages"])


# ===== 大宗商品路由(Feature Flag 渐进开启,Phase 0 引入) =====
# 总开关关闭时,所有 /api/commodity/* 路由不注册
# 子开关按需细粒度控制:Phase 1=数据,Phase 2=分析,Phase 4=模拟交易
if settings.FEATURE_COMMODITY_ENABLED:
    from app.routers.commodity import quotes_router, extended_router, news_router

    if settings.FEATURE_COMMODITY_DATA:
        # Phase 1:商品基础信息/行情/历史/品类/交易所(5 端点)
        app.include_router(quotes_router, prefix="/api")
        # Phase 3a:13 扩展接口 + 静态品种字典(15 端点)
        app.include_router(extended_router, prefix="/api")
        # Phase 3a:6 类新闻聚合(2 端点)
        app.include_router(news_router, prefix="/api")
        total = len(quotes_router.routes) + len(extended_router.routes) + len(news_router.routes)
        logger.info(f"✅ 大宗商品数据路由已注册(/api/commodity/* 共 {total} 端点)")
    else:
        logger.info("⏸️  大宗商品数据路由未启用(FEATURE_COMMODITY_DATA=false)")

    # Phase 3b-ii-D 启用:商品分析任务(异步跑决策链)
    if settings.FEATURE_COMMODITY_ANALYSIS:
        from app.routers.commodity import analysis_router
        app.include_router(analysis_router, prefix="/api")
        logger.info("✅ 大宗商品分析路由已注册(/api/commodity/{symbol}/analyze + reports)")
    else:
        logger.info("⏸️  大宗商品分析路由未启用(FEATURE_COMMODITY_ANALYSIS=false)")

    # Phase 4 启用:大宗商品模拟交易
    if settings.FEATURE_COMMODITY_PAPER:
        from app.routers.commodity import paper_rules_router
        app.include_router(paper_rules_router, prefix="/api")
        logger.info(f"✅ 大宗商品模拟交易路由已注册(/api/commodity/paper/*, 共 {len(paper_rules_router.routes)} 端点)")
    else:
        logger.info("⏸️  大宗商品模拟交易路由未启用(FEATURE_COMMODITY_PAPER=false)")
else:
    logger.info("⏸️  大宗商品模块未启用(FEATURE_COMMODITY_ENABLED=false)")


@app.get("/")
async def root():
    """根路径，返回API信息"""
    print("🏠 根路径被访问")
    return {
        "name": "TradingAgents-CN API",
        "version": get_version(),
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