"""
配置桥接模块
将统一配置系统的配置桥接到环境变量，供 TradingAgents 核心库使用
"""

import os
import logging
from typing import Optional

logger = logging.getLogger("app.config_bridge")


def bridge_config_to_env():
    """
    将统一配置桥接到环境变量

    这个函数会：
    1. 从统一配置读取大模型配置（API 密钥、超时、温度等）
    2. 将配置写入环境变量
    3. 将默认模型写入环境变量
    4. 将数据源配置写入环境变量（API 密钥、超时、重试等）
    5. 将系统运行时配置写入环境变量

    这样 TradingAgents 核心库就能通过环境变量读取到用户配置的数据
    """
    try:
        from app.core.unified_config import unified_config
        from app.services.config_service import config_service

        logger.info("🔧 开始桥接配置到环境变量...")
        bridged_count = 0

        # 1. 桥接大模型配置（基础 API 密钥）
        llm_configs = unified_config.get_llm_configs()
        for llm_config in llm_configs:
            if llm_config.enabled and llm_config.api_key:
                # 将 API 密钥写入环境变量
                env_key = f"{llm_config.provider.value.upper()}_API_KEY"
                os.environ[env_key] = llm_config.api_key
                logger.info(f"  ✓ 桥接 {env_key} (长度: {len(llm_config.api_key)})")
                bridged_count += 1

        # 2. 桥接默认模型配置
        default_model = unified_config.get_default_model()
        if default_model:
            os.environ['TRADINGAGENTS_DEFAULT_MODEL'] = default_model
            logger.info(f"  ✓ 桥接默认模型: {default_model}")
            bridged_count += 1

        quick_model = unified_config.get_quick_analysis_model()
        if quick_model:
            os.environ['TRADINGAGENTS_QUICK_MODEL'] = quick_model
            logger.info(f"  ✓ 桥接快速分析模型: {quick_model}")
            bridged_count += 1

        deep_model = unified_config.get_deep_analysis_model()
        if deep_model:
            os.environ['TRADINGAGENTS_DEEP_MODEL'] = deep_model
            logger.info(f"  ✓ 桥接深度分析模型: {deep_model}")
            bridged_count += 1

        # 3. 桥接数据源配置（基础 API 密钥）
        data_source_configs = unified_config.get_data_source_configs()
        for ds_config in data_source_configs:
            if ds_config.enabled and ds_config.api_key:
                # Tushare Token
                if ds_config.type.value == 'tushare':
                    os.environ['TUSHARE_TOKEN'] = ds_config.api_key
                    logger.info(f"  ✓ 桥接 TUSHARE_TOKEN (长度: {len(ds_config.api_key)})")
                    bridged_count += 1
                # FinnHub API Key
                elif ds_config.type.value == 'finnhub':
                    os.environ['FINNHUB_API_KEY'] = ds_config.api_key
                    logger.info(f"  ✓ 桥接 FINNHUB_API_KEY (长度: {len(ds_config.api_key)})")
                    bridged_count += 1

        # 4. 桥接数据源细节配置（超时、重试、缓存等）
        bridged_count += _bridge_datasource_details(data_source_configs)

        # 5. 桥接系统运行时配置
        bridged_count += _bridge_system_settings()

        logger.info(f"✅ 配置桥接完成，共桥接 {bridged_count} 项配置")
        return True

    except Exception as e:
        logger.error(f"❌ 配置桥接失败: {e}", exc_info=True)
        logger.warning("⚠️  TradingAgents 将使用 .env 文件中的配置")
        return False


def _bridge_datasource_details(data_source_configs) -> int:
    """
    桥接数据源细节配置到环境变量

    Args:
        data_source_configs: 数据源配置列表

    Returns:
        int: 桥接的配置项数量
    """
    bridged_count = 0

    for ds_config in data_source_configs:
        if not ds_config.enabled:
            continue

        # 注意：字段名是 type 而不是 source_type
        source_type = ds_config.type.value.upper()

        # 超时时间
        if ds_config.timeout:
            env_key = f"{source_type}_TIMEOUT"
            os.environ[env_key] = str(ds_config.timeout)
            logger.debug(f"  ✓ 桥接 {env_key}: {ds_config.timeout}")
            bridged_count += 1

        # 速率限制
        if ds_config.rate_limit:
            env_key = f"{source_type}_RATE_LIMIT"
            os.environ[env_key] = str(ds_config.rate_limit / 60.0)  # 转换为每秒请求数
            logger.debug(f"  ✓ 桥接 {env_key}: {ds_config.rate_limit / 60.0}")
            bridged_count += 1

        # 最大重试次数（从 config_params 中获取）
        if ds_config.config_params and 'max_retries' in ds_config.config_params:
            env_key = f"{source_type}_MAX_RETRIES"
            os.environ[env_key] = str(ds_config.config_params['max_retries'])
            logger.debug(f"  ✓ 桥接 {env_key}: {ds_config.config_params['max_retries']}")
            bridged_count += 1

        # 缓存 TTL（从 config_params 中获取）
        if ds_config.config_params and 'cache_ttl' in ds_config.config_params:
            env_key = f"{source_type}_CACHE_TTL"
            os.environ[env_key] = str(ds_config.config_params['cache_ttl'])
            logger.debug(f"  ✓ 桥接 {env_key}: {ds_config.config_params['cache_ttl']}")
            bridged_count += 1

        # 是否启用缓存（从 config_params 中获取）
        if ds_config.config_params and 'cache_enabled' in ds_config.config_params:
            env_key = f"{source_type}_CACHE_ENABLED"
            os.environ[env_key] = str(ds_config.config_params['cache_enabled']).lower()
            logger.debug(f"  ✓ 桥接 {env_key}: {ds_config.config_params['cache_enabled']}")
            bridged_count += 1

    if bridged_count > 0:
        logger.info(f"  ✓ 桥接数据源细节配置: {bridged_count} 项")

    return bridged_count


def _bridge_system_settings() -> int:
    """
    桥接系统运行时配置到环境变量

    Returns:
        int: 桥接的配置项数量
    """
    try:
        from app.core.database import get_mongo_db

        # 直接从数据库读取系统设置（同步方式）
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def get_settings():
                db = get_mongo_db()
                settings_doc = await db.system_settings.find_one({})
                return settings_doc if settings_doc else {}

            system_settings = loop.run_until_complete(get_settings())
            loop.close()
        except Exception as e:
            logger.debug(f"  ⚠️  无法从数据库获取系统设置: {e}")
            return 0

        if not system_settings:
            logger.debug("  ⚠️  系统设置为空，跳过桥接")
            return 0

        bridged_count = 0

        # TradingAgents 运行时配置
        ta_settings = {
            'ta_hk_min_request_interval_seconds': 'TA_HK_MIN_REQUEST_INTERVAL_SECONDS',
            'ta_hk_timeout_seconds': 'TA_HK_TIMEOUT_SECONDS',
            'ta_hk_max_retries': 'TA_HK_MAX_RETRIES',
            'ta_hk_rate_limit_wait_seconds': 'TA_HK_RATE_LIMIT_WAIT_SECONDS',
            'ta_hk_cache_ttl_seconds': 'TA_HK_CACHE_TTL_SECONDS',
            'ta_use_app_cache': 'TA_USE_APP_CACHE',
        }

        for setting_key, env_key in ta_settings.items():
            if setting_key in system_settings:
                value = system_settings[setting_key]
                os.environ[env_key] = str(value).lower() if isinstance(value, bool) else str(value)
                logger.debug(f"  ✓ 桥接 {env_key}: {value}")
                bridged_count += 1

        # 时区配置
        if 'app_timezone' in system_settings:
            os.environ['APP_TIMEZONE'] = system_settings['app_timezone']
            logger.debug(f"  ✓ 桥接 APP_TIMEZONE: {system_settings['app_timezone']}")
            bridged_count += 1

        # 货币偏好
        if 'currency_preference' in system_settings:
            os.environ['CURRENCY_PREFERENCE'] = system_settings['currency_preference']
            logger.debug(f"  ✓ 桥接 CURRENCY_PREFERENCE: {system_settings['currency_preference']}")
            bridged_count += 1

        if bridged_count > 0:
            logger.info(f"  ✓ 桥接系统运行时配置: {bridged_count} 项")

        return bridged_count

    except Exception as e:
        logger.warning(f"  ⚠️  桥接系统设置失败: {e}")
        return 0


def get_bridged_api_key(provider: str) -> Optional[str]:
    """
    获取桥接的 API 密钥
    
    Args:
        provider: 提供商名称 (如: openai, deepseek, dashscope)
    
    Returns:
        API 密钥，如果不存在返回 None
    """
    env_key = f"{provider.upper()}_API_KEY"
    return os.environ.get(env_key)


def get_bridged_model(model_type: str = "default") -> Optional[str]:
    """
    获取桥接的模型名称
    
    Args:
        model_type: 模型类型 (default, quick, deep)
    
    Returns:
        模型名称，如果不存在返回 None
    """
    if model_type == "quick":
        return os.environ.get('TRADINGAGENTS_QUICK_MODEL')
    elif model_type == "deep":
        return os.environ.get('TRADINGAGENTS_DEEP_MODEL')
    else:
        return os.environ.get('TRADINGAGENTS_DEFAULT_MODEL')


def clear_bridged_config():
    """
    清除桥接的配置

    用于测试或重新加载配置
    """
    keys_to_clear = [
        # 模型配置
        'TRADINGAGENTS_DEFAULT_MODEL',
        'TRADINGAGENTS_QUICK_MODEL',
        'TRADINGAGENTS_DEEP_MODEL',
        # 数据源 API 密钥
        'TUSHARE_TOKEN',
        'FINNHUB_API_KEY',
        # 系统配置
        'APP_TIMEZONE',
        'CURRENCY_PREFERENCE',
    ]

    # 清除所有可能的 API 密钥
    providers = ['OPENAI', 'ANTHROPIC', 'GOOGLE', 'DEEPSEEK', 'DASHSCOPE', 'QIANFAN']
    for provider in providers:
        keys_to_clear.append(f'{provider}_API_KEY')

    # 清除数据源细节配置
    data_sources = ['TUSHARE', 'AKSHARE', 'FINNHUB', 'TDX']
    for ds in data_sources:
        keys_to_clear.extend([
            f'{ds}_TIMEOUT',
            f'{ds}_RATE_LIMIT',
            f'{ds}_MAX_RETRIES',
            f'{ds}_CACHE_TTL',
            f'{ds}_CACHE_ENABLED',
        ])

    # 清除 TradingAgents 运行时配置
    ta_runtime_keys = [
        'TA_HK_MIN_REQUEST_INTERVAL_SECONDS',
        'TA_HK_TIMEOUT_SECONDS',
        'TA_HK_MAX_RETRIES',
        'TA_HK_RATE_LIMIT_WAIT_SECONDS',
        'TA_HK_CACHE_TTL_SECONDS',
        'TA_USE_APP_CACHE',
    ]
    keys_to_clear.extend(ta_runtime_keys)

    for key in keys_to_clear:
        if key in os.environ:
            del os.environ[key]
            logger.debug(f"  清除环境变量: {key}")

    logger.info("✅ 已清除所有桥接的配置")


def reload_bridged_config():
    """
    重新加载桥接的配置
    
    用于配置更新后重新桥接
    """
    logger.info("🔄 重新加载配置桥接...")
    clear_bridged_config()
    return bridge_config_to_env()


# 导出函数
__all__ = [
    'bridge_config_to_env',
    'get_bridged_api_key',
    'get_bridged_model',
    'clear_bridged_config',
    'reload_bridged_config',
]

