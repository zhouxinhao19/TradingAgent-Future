"""
Provider 查找工具函数
根据模型名称从数据库配置中查找对应的供应商、API URL 和 API Key
"""
import logging

logger = logging.getLogger("app.services.provider_lookup")

# 配置服务实例
from app.services.config_service import ConfigService
_config_service = ConfigService()


async def get_provider_by_model_name(model_name: str) -> str:
    """
    根据模型名称从数据库配置中查找对应的供应商（异步版本）
    """
    try:
        system_config = await _config_service.get_system_config()
        if not system_config or not system_config.llm_configs:
            logger.warning(f"⚠️ 系统配置为空，使用默认供应商映射")
            return _get_default_provider_by_model(model_name)

        for llm_config in system_config.llm_configs:
            if llm_config.model_name == model_name:
                provider = llm_config.provider.value if hasattr(llm_config.provider, 'value') else str(llm_config.provider)
                logger.info(f"✅ 从数据库找到模型 {model_name} 的供应商: {provider}")
                return provider

        logger.warning(f"⚠️ 数据库中未找到模型 {model_name}，使用默认映射")
        return _get_default_provider_by_model(model_name)

    except Exception as e:
        logger.error(f"❌ 查找模型供应商失败: {e}")
        return _get_default_provider_by_model(model_name)


def get_provider_by_model_name_sync(model_name: str) -> str:
    """同步版本"""
    provider_info = get_provider_and_url_by_model_sync(model_name)
    return provider_info["provider"]


def get_provider_and_url_by_model_sync(model_name: str) -> dict:
    """
    根据模型名称从数据库配置中查找对应的供应商和 API URL（同步版本）
    Returns: {"provider": "...", "backend_url": "...", "api_key": "..."}
    """
    try:
        from pymongo import MongoClient
        from app.core.config import settings

        client = MongoClient(settings.MONGO_URI)
        db = client[settings.MONGO_DB]

        configs_collection = db.system_configs
        doc = configs_collection.find_one({"is_active": True}, sort=[("version", -1)])

        if doc and "llm_configs" in doc:
            for config_dict in doc["llm_configs"]:
                if config_dict.get("model_name") == model_name:
                    provider = config_dict.get("provider")
                    api_base = config_dict.get("api_base")
                    model_api_key = config_dict.get("api_key")

                    providers_collection = db.llm_providers
                    provider_doc = providers_collection.find_one({"name": provider})

                    api_key = None
                    if model_api_key and model_api_key.strip() and model_api_key != "your-api-key":
                        api_key = model_api_key
                        logger.info(f"✅ [同步查询] 使用模型配置的 API Key")
                    elif provider_doc and provider_doc.get("api_key"):
                        pa = provider_doc["api_key"]
                        if pa and pa.strip() and pa != "your-api-key":
                            api_key = pa
                            logger.info(f"✅ [同步查询] 使用厂家配置的 API Key")

                    if not api_key:
                        api_key = _get_env_api_key_for_provider(provider)
                        if api_key:
                            logger.info(f"✅ [同步查询] 使用环境变量的 API Key")

                    backend_url = None
                    if api_base:
                        backend_url = api_base
                        logger.info(f"✅ [同步查询] 模型 {model_name} 使用自定义 API: {api_base}")
                    elif provider_doc and provider_doc.get("default_base_url"):
                        backend_url = provider_doc["default_base_url"]
                        logger.info(f"✅ [同步查询] 模型 {model_name} 使用厂家默认 API: {backend_url}")
                    else:
                        logger.warning(f"⚠️ [同步查询] 厂家 {provider} 没有配置 default_base_url")

                    from tradingagents.llm_clients.provider_keys import normalize_provider_key

                    provider_key = normalize_provider_key(provider)

                    client.close()
                    return {
                        "provider": provider_key,
                        "backend_url": backend_url or _get_default_backend_url(provider_key),
                        "api_key": api_key
                    }

        client.close()
        logger.warning(f"⚠️ [同步查询] 数据库中未找到模型 {model_name}，使用默认映射")
        provider = _get_default_provider_by_model(model_name)
        return _fallback_provider_config(provider)

    except Exception as e:
        logger.error(f"❌ [同步查询] 查找模型供应商失败: {e}")
        provider = _get_default_provider_by_model(model_name)
        return _fallback_provider_config(provider)


def _fallback_provider_config(provider: str) -> dict:
    """回退到硬编码默认 URL 和环境变量 API Key"""
    try:
        from pymongo import MongoClient
        from app.core.config import settings
        from tradingagents.llm_clients.provider_keys import normalize_provider_key

        client = MongoClient(settings.MONGO_URI)
        db = client[settings.MONGO_DB]
        provider_doc = db.llm_providers.find_one({"name": provider})

        backend_url = _get_default_backend_url(provider)
        api_key = _get_env_api_key_for_provider(provider)

        if provider_doc:
            if provider_doc.get("default_base_url"):
                backend_url = provider_doc["default_base_url"]
            if provider_doc.get("api_key"):
                pa = provider_doc["api_key"]
                if pa and pa.strip() and pa != "your-api-key":
                    api_key = pa

        client.close()
        return {
            "provider": normalize_provider_key(provider),
            "backend_url": backend_url,
            "api_key": api_key
        }
    except Exception as e:
        logger.warning(f"⚠️ [回退] 无法查询厂家配置: {e}")

    from tradingagents.llm_clients.provider_keys import normalize_provider_key
    return {
        "provider": normalize_provider_key(provider),
        "backend_url": _get_default_backend_url(provider),
        "api_key": _get_env_api_key_for_provider(provider)
    }


def _get_env_api_key_for_provider(provider: str):
    import os
    from tradingagents.llm_clients.provider_keys import env_key_for_provider, normalize_provider_key

    provider_key = normalize_provider_key(provider)
    env_key_name = env_key_for_provider(provider_key)
    if not env_key_name and provider_key in ("302ai", "aihubmix"):
        env_key_name = {"302ai": "AI302_API_KEY", "aihubmix": "AIHUBMIX_API_KEY"}.get(provider_key)
    if env_key_name:
        api_key = os.getenv(env_key_name)
        if api_key and api_key.strip() and api_key != "your-api-key":
            return api_key
    return None


def _get_default_backend_url(provider: str) -> str:
    from tradingagents.llm_clients.provider_keys import default_backend_url, normalize_provider_key

    provider_key = normalize_provider_key(provider)
    if provider_key == "302ai":
        url = "https://api.302.ai/v1"
    elif provider_key == "aihubmix":
        url = "https://aihubmix.com/v1"
    else:
        url = default_backend_url(provider_key)

    logger.info(f"🔧 [默认URL] {provider} -> {url}")
    return url


def _get_default_provider_by_model(model_name: str) -> str:
    model_provider_map = {
        'qwen-turbo': 'qwen', 'qwen-plus': 'qwen', 'qwen-max': 'qwen',
        'qwen-plus-latest': 'qwen', 'qwen-max-longcontext': 'qwen',
        'gpt-3.5-turbo': 'openai', 'gpt-4': 'openai', 'gpt-4-turbo': 'openai',
        'gpt-4o': 'openai', 'gpt-4o-mini': 'openai',
        'gemini-pro': 'google', 'gemini-2.0-flash': 'google',
        'gemini-2.0-flash-thinking-exp': 'google',
        'deepseek-chat': 'deepseek', 'deepseek-coder': 'deepseek',
        'glm-4': 'glm', 'glm-3-turbo': 'glm', 'chatglm3-6b': 'glm'
    }
    provider = model_provider_map.get(model_name, 'qwen')
    logger.info(f"🔧 使用默认映射: {model_name} -> {provider}")
    return provider
