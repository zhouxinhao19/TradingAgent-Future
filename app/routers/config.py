"""
配置管理API路由
"""

import logging
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.routers.auth import get_current_user
from app.models.user import User
from app.models.config import (
    SystemConfigResponse, LLMConfigRequest, DataSourceConfigRequest,
    DatabaseConfigRequest, ConfigTestRequest, ConfigTestResponse,
    LLMConfig, DataSourceConfig, DatabaseConfig,
    LLMProvider, LLMProviderRequest, LLMProviderResponse,
    MarketCategory, MarketCategoryRequest, DataSourceGrouping,
    DataSourceGroupingRequest, DataSourceOrderRequest
)
from app.services.config_service import config_service
from datetime import datetime
from app.services.operation_log_service import log_operation
from app.models.operation_log import ActionType


router = APIRouter(prefix="/config", tags=["配置管理"])
logger = logging.getLogger("webapi")


# ===== 方案A：敏感字段响应脱敏 & 请求清洗 =====
from copy import deepcopy

def _sanitize_llm_configs(items):
    try:
        return [LLMConfig(**{**i.dict(), "api_key": None}) for i in items]
    except Exception:
        return items

def _sanitize_datasource_configs(items):
    try:
        return [DataSourceConfig(**{**i.dict(), "api_key": None, "api_secret": None}) for i in items]
    except Exception:
        return items

def _sanitize_database_configs(items):
    try:
        return [DatabaseConfig(**{**i.dict(), "password": None}) for i in items]
    except Exception:
        return items

def _sanitize_kv(d: Dict[str, Any]) -> Dict[str, Any]:
    """对字典中的可能敏感键进行脱敏（仅用于响应）。"""
    try:
        if not isinstance(d, dict):
            return d
        sens_patterns = ("key", "secret", "password", "token", "client_secret")
        redacted = {}
        for k, v in d.items():
            if isinstance(k, str) and any(p in k.lower() for p in sens_patterns):
                redacted[k] = None
            else:
                redacted[k] = v
        return redacted
    except Exception:
        return d




class SetDefaultRequest(BaseModel):
    """设置默认配置请求"""
    name: str


@router.get("/system", response_model=SystemConfigResponse)
async def get_system_config(
    current_user: User = Depends(get_current_user)
):
    """获取系统配置"""
    try:
        config = await config_service.get_system_config()
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="系统配置不存在"
            )

        return SystemConfigResponse(
            config_name=config.config_name,
            config_type=config.config_type,
            llm_configs=_sanitize_llm_configs(config.llm_configs),
            default_llm=config.default_llm,
            data_source_configs=_sanitize_datasource_configs(config.data_source_configs),
            default_data_source=config.default_data_source,
            database_configs=_sanitize_database_configs(config.database_configs),
            system_settings=_sanitize_kv(config.system_settings),
            created_at=config.created_at,
            updated_at=config.updated_at,
            version=config.version,
            is_active=config.is_active
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取系统配置失败: {str(e)}"
        )


# ========== 大模型厂家管理 ==========

@router.get("/llm/providers", response_model=List[LLMProviderResponse])
async def get_llm_providers(
    current_user: User = Depends(get_current_user)
):
    """获取所有大模型厂家"""
    try:
        providers = await config_service.get_llm_providers()
        return [
            LLMProviderResponse(
                id=str(provider.id),
                name=provider.name,
                display_name=provider.display_name,
                description=provider.description,
                website=provider.website,
                api_doc_url=provider.api_doc_url,
                logo_url=provider.logo_url,
                is_active=provider.is_active,
                supported_features=provider.supported_features,
                default_base_url=provider.default_base_url,
                # 安全考虑：不返回完整API密钥，只返回前缀和状态
                api_key=provider.api_key[:8] + "..." if provider.api_key else None,
                api_secret=provider.api_secret[:8] + "..." if provider.api_secret else None,
                extra_config={
                    **provider.extra_config,
                    "has_api_key": bool(provider.api_key),
                    "has_api_secret": bool(provider.api_secret)
                },
                created_at=provider.created_at,
                updated_at=provider.updated_at
            )
            for provider in providers
        ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取厂家列表失败: {str(e)}"
        )


@router.post("/llm/providers", response_model=dict)
async def add_llm_provider(
    request: LLMProviderRequest,
    current_user: User = Depends(get_current_user)
):
    """添加大模型厂家"""
    try:
        provider = LLMProvider(**request.dict())
        provider_id = await config_service.add_llm_provider(provider)

        return {
            "success": True,
            "message": "厂家添加成功",
            "data": {"id": str(provider_id)}
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"添加厂家失败: {str(e)}"
        )


@router.put("/llm/providers/{provider_id}", response_model=dict)
async def update_llm_provider(
    provider_id: str,
    request: LLMProviderRequest,
    current_user: User = Depends(get_current_user)
):
    """更新大模型厂家"""
    try:
        success = await config_service.update_llm_provider(provider_id, request.dict())

        if success:
            return {
                "success": True,
                "message": "厂家更新成功",
                "data": {}
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="厂家不存在"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新厂家失败: {str(e)}"
        )


@router.delete("/llm/providers/{provider_id}", response_model=dict)
async def delete_llm_provider(
    provider_id: str,
    current_user: User = Depends(get_current_user)
):
    """删除大模型厂家"""
    try:
        success = await config_service.delete_llm_provider(provider_id)

        if success:
            return {
                "success": True,
                "message": "厂家删除成功",
                "data": {}
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="厂家不存在"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除厂家失败: {str(e)}"
        )


@router.patch("/llm/providers/{provider_id}/toggle", response_model=dict)
async def toggle_llm_provider(
    provider_id: str,
    request: dict,
    current_user: User = Depends(get_current_user)
):
    """切换大模型厂家状态"""
    try:
        is_active = request.get("is_active", True)
        success = await config_service.toggle_llm_provider(provider_id, is_active)

        if success:
            return {
                "success": True,
                "message": f"厂家已{'启用' if is_active else '禁用'}",
                "data": {}
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="厂家不存在"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"切换厂家状态失败: {str(e)}"
        )


@router.post("/llm/providers/migrate-env", response_model=dict)
async def migrate_env_to_providers(
    current_user: User = Depends(get_current_user)
):
    """将环境变量配置迁移到厂家管理"""
    try:
        result = await config_service.migrate_env_to_providers()

        return {
            "success": result["success"],
            "message": result["message"],
            "data": {
                "migrated_count": result.get("migrated_count", 0),
                "skipped_count": result.get("skipped_count", 0)
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"环境变量迁移失败: {str(e)}"
        )


@router.post("/llm/providers/{provider_id}/test", response_model=dict)
async def test_provider_api(
    provider_id: str,
    current_user: User = Depends(get_current_user)
):
    """测试厂家API密钥"""
    try:
        logger.info(f"🧪 收到API测试请求 - provider_id: {provider_id}")
        result = await config_service.test_provider_api(provider_id)
        logger.info(f"🧪 API测试结果: {result}")
        return result
    except Exception as e:
        logger.error(f"测试厂家API失败: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"测试厂家API失败: {str(e)}"
        )


# ========== 大模型配置管理 ==========

@router.post("/llm", response_model=dict)
async def add_llm_config(
    request: LLMConfigRequest,
    current_user: User = Depends(get_current_user)
):
    """添加或更新大模型配置"""
    try:
        logger.info(f"🔧 添加/更新大模型配置开始")
        logger.info(f"📊 请求数据: {request.dict()}")
        logger.info(f"🏷️ 厂家: {request.provider}, 模型: {request.model_name}")

        # 创建LLM配置
        llm_config_data = request.dict()
        logger.info(f"📋 原始配置数据: {llm_config_data}")

        # 如果没有提供API密钥，从厂家配置中获取
        if not llm_config_data.get('api_key'):
            logger.info(f"🔑 API密钥为空，从厂家配置获取: {request.provider}")

            # 获取厂家配置
            providers = await config_service.get_llm_providers()
            logger.info(f"📊 找到 {len(providers)} 个厂家配置")

            for p in providers:
                logger.info(f"   - 厂家: {p.name}, 有API密钥: {bool(p.api_key)}")

            provider_config = next((p for p in providers if p.name == request.provider), None)

            if provider_config:
                logger.info(f"✅ 找到厂家配置: {provider_config.name}")
                if provider_config.api_key:
                    llm_config_data['api_key'] = provider_config.api_key
                    logger.info(f"✅ 成功获取厂家API密钥 (长度: {len(provider_config.api_key)})")
                else:
                    logger.warning(f"⚠️ 厂家 {request.provider} 没有配置API密钥")
                    llm_config_data['api_key'] = ""
            else:
                logger.warning(f"⚠️ 未找到厂家 {request.provider} 的配置")
                llm_config_data['api_key'] = ""
        else:
            logger.info(f"🔑 使用提供的API密钥 (长度: {len(llm_config_data.get('api_key', ''))})")

        logger.info(f"📋 最终配置数据: {llm_config_data}")
        # 方案A：禁止通过 REST 写入/落盘密钥，统一从环境变量/厂家配置注入
        if 'api_key' in llm_config_data:
            llm_config_data['api_key'] = ""


        # 尝试创建LLMConfig对象
        try:
            llm_config = LLMConfig(**llm_config_data)
            logger.info(f"✅ LLMConfig对象创建成功")
        except Exception as e:
            logger.error(f"❌ LLMConfig对象创建失败: {e}")
            logger.error(f"📋 失败的数据: {llm_config_data}")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"配置数据验证失败: {str(e)}"
            )

        # 保存配置
        success = await config_service.update_llm_config(llm_config)

        if success:
            logger.info(f"✅ 大模型配置更新成功: {llm_config.provider}/{llm_config.model_name}")
            return {"message": "大模型配置更新成功", "model_name": llm_config.model_name}
        else:
            logger.error(f"❌ 大模型配置保存失败")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="大模型配置更新失败"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 添加大模型配置异常: {e}")
        import traceback
        logger.error(f"📋 异常堆栈: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"添加大模型配置失败: {str(e)}"
        )


@router.post("/datasource", response_model=dict)
async def add_data_source_config(
    request: DataSourceConfigRequest,
    current_user: User = Depends(get_current_user)
):
    """添加数据源配置"""
    try:
        # 开源版本：所有用户都可以修改配置

        # 获取当前配置
        config = await config_service.get_system_config()
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="系统配置不存在"
            )

        # 添加新的数据源配置（方案A：清洗敏感字段）
        _req = request.dict()
        _req['api_key'] = ""
        _req['api_secret'] = ""
        ds_config = DataSourceConfig(**_req)
        config.data_source_configs.append(ds_config)

        success = await config_service.save_system_config(config)
        if success:
            return {"message": "数据源配置添加成功", "name": ds_config.name}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="数据源配置添加失败"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"添加数据源配置失败: {str(e)}"
        )


@router.post("/database", response_model=dict)
async def add_database_config(
    request: DatabaseConfigRequest,
    current_user: User = Depends(get_current_user)
):
    """添加数据库配置"""
    try:
        # 开源版本：所有用户都可以修改配置

        # 获取当前配置
        config = await config_service.get_system_config()
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="系统配置不存在"
            )

        # 添加新的数据库配置（方案A：清洗敏感字段）
        _req = request.dict()
        _req['password'] = ""
        db_config = DatabaseConfig(**_req)
        config.database_configs.append(db_config)

        success = await config_service.save_system_config(config)
        if success:
            return {"message": "数据库配置添加成功", "name": db_config.name}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="数据库配置添加失败"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"添加数据库配置失败: {str(e)}"
        )


@router.post("/test", response_model=ConfigTestResponse)
async def test_config(
    request: ConfigTestRequest,
    current_user: User = Depends(get_current_user)
):
    """测试配置连接"""
    try:
        if request.config_type == "llm":
            llm_config = LLMConfig(**request.config_data)
            result = await config_service.test_llm_config(llm_config)
        elif request.config_type == "datasource":
            ds_config = DataSourceConfig(**request.config_data)
            result = await config_service.test_data_source_config(ds_config)
        elif request.config_type == "database":
            db_config = DatabaseConfig(**request.config_data)
            result = await config_service.test_database_config(db_config)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不支持的配置类型"
            )

        return ConfigTestResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"测试配置失败: {str(e)}"
        )


@router.get("/llm", response_model=List[LLMConfig])
async def get_llm_configs(
    current_user: User = Depends(get_current_user)
):
    """获取所有大模型配置"""
    try:
        logger.info("🔄 开始获取大模型配置...")
        config = await config_service.get_system_config()

        if not config:
            logger.warning("⚠️ 系统配置为空，返回空列表")
            return []

        logger.info(f"📊 系统配置存在，大模型配置数量: {len(config.llm_configs)}")

        # 如果没有大模型配置，创建一些示例配置
        if not config.llm_configs:
            logger.info("🔧 没有大模型配置，创建示例配置...")
            # 这里可以根据已有的厂家创建示例配置
            # 暂时返回空列表，让前端显示"暂无配置"

        return _sanitize_llm_configs(config.llm_configs)
    except Exception as e:
        logger.error(f"❌ 获取大模型配置失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取大模型配置失败: {str(e)}"
        )


@router.delete("/llm/{provider}/{model_name}")
async def delete_llm_config(
    provider: str,
    model_name: str,
    current_user: User = Depends(get_current_user)
):
    """删除大模型配置"""
    try:
        logger.info(f"🗑️ 删除大模型配置请求 - provider: {provider}, model_name: {model_name}")
        success = await config_service.delete_llm_config(provider, model_name)

        if success:
            logger.info(f"✅ 大模型配置删除成功 - {provider}/{model_name}")
            return {"message": "大模型配置删除成功"}
        else:
            logger.warning(f"⚠️ 未找到大模型配置 - {provider}/{model_name}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="大模型配置不存在"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 删除大模型配置异常 - {provider}/{model_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除大模型配置失败: {str(e)}"
        )


@router.post("/llm/set-default")
async def set_default_llm(
    request: SetDefaultRequest,
    current_user: User = Depends(get_current_user)
):
    """设置默认大模型"""
    try:
        success = await config_service.set_default_llm(request.name)
        if success:
            return {"message": "默认大模型设置成功", "default_llm": request.name}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="指定的大模型不存在"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"设置默认大模型失败: {str(e)}"
        )


@router.get("/datasource", response_model=List[DataSourceConfig])
async def get_data_source_configs(
    current_user: User = Depends(get_current_user)
):
    """获取所有数据源配置"""
    try:
        config = await config_service.get_system_config()
        if not config:
            return []
        return _sanitize_datasource_configs(config.data_source_configs)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取数据源配置失败: {str(e)}"
        )


@router.put("/datasource/{name}", response_model=dict)
async def update_data_source_config(
    name: str,
    request: DataSourceConfigRequest,
    current_user: User = Depends(get_current_user)
):
    """更新数据源配置"""
    try:
        # 获取当前配置
        config = await config_service.get_system_config()
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="系统配置不存在"
            )

        # 查找并更新数据源配置
        for i, ds_config in enumerate(config.data_source_configs):
            if ds_config.name == name:
                # 更新配置（方案A：清洗敏感字段）
                _req = request.dict()
                _req['api_key'] = ""
                _req['api_secret'] = ""
                updated_config = DataSourceConfig(**_req)
                config.data_source_configs[i] = updated_config

                success = await config_service.save_system_config(config)
                if success:
                    return {"message": "数据源配置更新成功"}
                else:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="数据源配置更新失败"
                    )

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="数据源配置不存在"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新数据源配置失败: {str(e)}"
        )


@router.delete("/datasource/{name}", response_model=dict)
async def delete_data_source_config(
    name: str,
    current_user: User = Depends(get_current_user)
):
    """删除数据源配置"""
    try:
        # 获取当前配置
        config = await config_service.get_system_config()
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="系统配置不存在"
            )

        # 查找并删除数据源配置
        for i, ds_config in enumerate(config.data_source_configs):
            if ds_config.name == name:
                config.data_source_configs.pop(i)

                success = await config_service.save_system_config(config)
                if success:
                    return {"message": "数据源配置删除成功"}
                else:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="数据源配置删除失败"
                    )

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="数据源配置不存在"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除数据源配置失败: {str(e)}"
        )


# ==================== 市场分类管理 ====================

@router.get("/market-categories", response_model=List[MarketCategory])
async def get_market_categories(
    current_user: User = Depends(get_current_user)
):
    """获取所有市场分类"""
    try:
        categories = await config_service.get_market_categories()
        return categories
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取市场分类失败: {str(e)}"
        )


@router.post("/market-categories", response_model=dict)
async def add_market_category(
    request: MarketCategoryRequest,
    current_user: User = Depends(get_current_user)
):
    """添加市场分类"""
    try:
        category = MarketCategory(**request.dict())
        success = await config_service.add_market_category(category)

        if success:
            return {"message": "市场分类添加成功", "id": category.id}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="市场分类ID已存在"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"添加市场分类失败: {str(e)}"
        )


@router.put("/market-categories/{category_id}", response_model=dict)
async def update_market_category(
    category_id: str,
    request: Dict[str, Any],
    current_user: User = Depends(get_current_user)
):
    """更新市场分类"""
    try:
        success = await config_service.update_market_category(category_id, request)

        if success:
            return {"message": "市场分类更新成功"}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="市场分类不存在"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新市场分类失败: {str(e)}"
        )


@router.delete("/market-categories/{category_id}", response_model=dict)
async def delete_market_category(
    category_id: str,
    current_user: User = Depends(get_current_user)
):
    """删除市场分类"""
    try:
        success = await config_service.delete_market_category(category_id)

        if success:
            return {"message": "市场分类删除成功"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无法删除分类，可能还有数据源使用此分类"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除市场分类失败: {str(e)}"
        )


# ==================== 数据源分组管理 ====================

@router.get("/datasource-groupings", response_model=List[DataSourceGrouping])
async def get_datasource_groupings(
    current_user: User = Depends(get_current_user)
):
    """获取所有数据源分组关系"""
    try:
        groupings = await config_service.get_datasource_groupings()
        return groupings
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取数据源分组关系失败: {str(e)}"
        )


@router.post("/datasource-groupings", response_model=dict)
async def add_datasource_to_category(
    request: DataSourceGroupingRequest,
    current_user: User = Depends(get_current_user)
):
    """将数据源添加到分类"""
    try:
        grouping = DataSourceGrouping(**request.dict())
        success = await config_service.add_datasource_to_category(grouping)

        if success:
            return {"message": "数据源添加到分类成功"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="数据源已在该分类中"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"添加数据源到分类失败: {str(e)}"
        )


@router.delete("/datasource-groupings/{data_source_name}/{category_id}", response_model=dict)
async def remove_datasource_from_category(
    data_source_name: str,
    category_id: str,
    current_user: User = Depends(get_current_user)
):
    """从分类中移除数据源"""
    try:
        success = await config_service.remove_datasource_from_category(data_source_name, category_id)

        if success:
            return {"message": "数据源从分类中移除成功"}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="数据源分组关系不存在"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"从分类中移除数据源失败: {str(e)}"
        )


@router.put("/datasource-groupings/{data_source_name}/{category_id}", response_model=dict)
async def update_datasource_grouping(
    data_source_name: str,
    category_id: str,
    request: Dict[str, Any],
    current_user: User = Depends(get_current_user)
):
    """更新数据源分组关系"""
    try:
        success = await config_service.update_datasource_grouping(data_source_name, category_id, request)

        if success:
            return {"message": "数据源分组关系更新成功"}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="数据源分组关系不存在"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新数据源分组关系失败: {str(e)}"
        )


@router.put("/market-categories/{category_id}/datasource-order", response_model=dict)
async def update_category_datasource_order(
    category_id: str,
    request: DataSourceOrderRequest,
    current_user: User = Depends(get_current_user)
):
    """更新分类中数据源的排序"""
    try:
        success = await config_service.update_category_datasource_order(category_id, request.data_sources)

        if success:
            return {"message": "数据源排序更新成功"}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="数据源排序更新失败"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新数据源排序失败: {str(e)}"
        )


@router.post("/datasource/set-default")
async def set_default_data_source(
    request: SetDefaultRequest,
    current_user: User = Depends(get_current_user)
):
    """设置默认数据源"""
    try:
        success = await config_service.set_default_data_source(request.name)
        if success:
            return {"message": "默认数据源设置成功", "default_data_source": request.name}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="指定的数据源不存在"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"设置默认数据源失败: {str(e)}"
        )


@router.get("/settings", response_model=Dict[str, Any])
async def get_system_settings(
    current_user: User = Depends(get_current_user)
):
    """获取系统设置"""
    try:
        config = await config_service.get_system_config()
        if not config:
            return {}
        return _sanitize_kv(config.system_settings)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取系统设置失败: {str(e)}"
        )


@router.put("/settings", response_model=dict)
async def update_system_settings(
    settings: Dict[str, Any],
    current_user: User = Depends(get_current_user)
):
    """更新系统设置"""
    try:
        success = await config_service.update_system_settings(settings)
        if success:
            # 审计日志（忽略日志异常，不影响主流程）
            try:
                await log_operation(
                    user_id=str(getattr(current_user, "id", "")),
                    username=getattr(current_user, "username", "unknown"),
                    action_type=ActionType.CONFIG_MANAGEMENT,
                    action="update_system_settings",
                    details={"changed_keys": list(settings.keys())},
                    success=True,
                )
            except Exception:
                pass
            return {"message": "系统设置更新成功"}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="系统设置更新失败"
            )
    except HTTPException:
        raise
    except Exception as e:
        # 审计失败记录（忽略日志异常）
        try:
            await log_operation(
                user_id=str(getattr(current_user, "id", "")),
                username=getattr(current_user, "username", "unknown"),
                action_type=ActionType.CONFIG_MANAGEMENT,
                action="update_system_settings",
                details={"changed_keys": list(settings.keys())},
                success=False,
                error_message=str(e),
            )
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新系统设置失败: {str(e)}"
        )


@router.post("/export", response_model=dict)
async def export_config(
    current_user: User = Depends(get_current_user)
):
    """导出配置"""
    try:
        config_data = await config_service.export_config()
        return {
            "message": "配置导出成功",
            "data": config_data,
            "exported_at": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"导出配置失败: {str(e)}"
        )


@router.post("/import", response_model=dict)
async def import_config(
    config_data: Dict[str, Any],
    current_user: User = Depends(get_current_user)
):
    """导入配置"""
    try:
        success = await config_service.import_config(config_data)
        if success:
            return {"message": "配置导入成功"}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="配置导入失败"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"导入配置失败: {str(e)}"
        )


@router.post("/migrate-legacy", response_model=dict)
async def migrate_legacy_config(
    current_user: User = Depends(get_current_user)
):
    """迁移传统配置"""
    try:
        success = await config_service.migrate_legacy_config()
        if success:
            return {"message": "传统配置迁移成功"}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="传统配置迁移失败"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"迁移传统配置失败: {str(e)}"
        )


@router.post("/default/llm", response_model=dict)
async def set_default_llm(
    request: SetDefaultRequest,
    current_user: User = Depends(get_current_user)
):
    """设置默认大模型"""
    try:
        # 开源版本：所有用户都可以修改配置

        success = await config_service.set_default_llm(request.name)
        if success:
            return {"message": f"默认大模型已设置为: {request.name}"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="设置默认大模型失败，请检查模型名称是否正确"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"设置默认大模型失败: {str(e)}"
        )


@router.post("/default/datasource", response_model=dict)
async def set_default_data_source(
    request: SetDefaultRequest,
    current_user: User = Depends(get_current_user)
):
    """设置默认数据源"""
    try:
        # 开源版本：所有用户都可以修改配置

        success = await config_service.set_default_data_source(request.name)
        if success:
            return {"message": f"默认数据源已设置为: {request.name}"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="设置默认数据源失败，请检查数据源名称是否正确"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"设置默认数据源失败: {str(e)}"
        )


@router.get("/models", response_model=List[Dict[str, Any]])
async def get_available_models(
    current_user: User = Depends(get_current_user)
):
    """获取可用的模型列表"""
    try:
        models = await config_service.get_available_models()
        return models
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取模型列表失败: {str(e)}"
        )
