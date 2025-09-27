"""
配置管理服务
"""

import time
import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime
from bson import ObjectId

from app.core.database import get_mongo_db
from app.core.unified_config import unified_config
from app.models.config import (
    SystemConfig, LLMConfig, DataSourceConfig, DatabaseConfig,
    ModelProvider, DataSourceType, DatabaseType, LLMProvider,
    MarketCategory, DataSourceGrouping
)


class ConfigService:
    """配置管理服务类"""

    def __init__(self, db_manager=None):
        self.db = None
        self.db_manager = db_manager

    async def _get_db(self):
        """获取数据库连接"""
        if self.db is None:
            if self.db_manager and self.db_manager.mongo_db is not None:
                # 如果有DatabaseManager实例，直接使用
                self.db = self.db_manager.mongo_db
            else:
                # 否则使用全局函数
                self.db = get_mongo_db()
        return self.db

    # ==================== 市场分类管理 ====================

    async def get_market_categories(self) -> List[MarketCategory]:
        """获取所有市场分类"""
        try:
            db = await self._get_db()
            categories_collection = db.market_categories

            categories_data = await categories_collection.find({}).to_list(length=None)
            categories = [MarketCategory(**data) for data in categories_data]

            # 如果没有分类，创建默认分类
            if not categories:
                categories = await self._create_default_market_categories()

            # 按排序顺序排列
            categories.sort(key=lambda x: x.sort_order)
            return categories
        except Exception as e:
            print(f"❌ 获取市场分类失败: {e}")
            return []

    async def _create_default_market_categories(self) -> List[MarketCategory]:
        """创建默认市场分类"""
        default_categories = [
            MarketCategory(
                id="a_shares",
                name="a_shares",
                display_name="A股",
                description="中国A股市场数据源",
                enabled=True,
                sort_order=1
            ),
            MarketCategory(
                id="us_stocks",
                name="us_stocks",
                display_name="美股",
                description="美国股票市场数据源",
                enabled=True,
                sort_order=2
            ),
            MarketCategory(
                id="hk_stocks",
                name="hk_stocks",
                display_name="港股",
                description="香港股票市场数据源",
                enabled=True,
                sort_order=3
            ),
            MarketCategory(
                id="crypto",
                name="crypto",
                display_name="数字货币",
                description="数字货币市场数据源",
                enabled=True,
                sort_order=4
            ),
            MarketCategory(
                id="futures",
                name="futures",
                display_name="期货",
                description="期货市场数据源",
                enabled=True,
                sort_order=5
            )
        ]

        # 保存到数据库
        db = await self._get_db()
        categories_collection = db.market_categories

        for category in default_categories:
            await categories_collection.insert_one(category.dict())

        return default_categories

    async def add_market_category(self, category: MarketCategory) -> bool:
        """添加市场分类"""
        try:
            db = await self._get_db()
            categories_collection = db.market_categories

            # 检查ID是否已存在
            existing = await categories_collection.find_one({"id": category.id})
            if existing:
                return False

            await categories_collection.insert_one(category.dict())
            return True
        except Exception as e:
            print(f"❌ 添加市场分类失败: {e}")
            return False

    async def update_market_category(self, category_id: str, updates: Dict[str, Any]) -> bool:
        """更新市场分类"""
        try:
            db = await self._get_db()
            categories_collection = db.market_categories

            updates["updated_at"] = datetime.utcnow()
            result = await categories_collection.update_one(
                {"id": category_id},
                {"$set": updates}
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"❌ 更新市场分类失败: {e}")
            return False

    async def delete_market_category(self, category_id: str) -> bool:
        """删除市场分类"""
        try:
            db = await self._get_db()
            categories_collection = db.market_categories
            groupings_collection = db.datasource_groupings

            # 检查是否有数据源使用此分类
            groupings_count = await groupings_collection.count_documents(
                {"market_category_id": category_id}
            )
            if groupings_count > 0:
                return False

            result = await categories_collection.delete_one({"id": category_id})
            return result.deleted_count > 0
        except Exception as e:
            print(f"❌ 删除市场分类失败: {e}")
            return False

    # ==================== 数据源分组管理 ====================

    async def get_datasource_groupings(self) -> List[DataSourceGrouping]:
        """获取所有数据源分组关系"""
        try:
            db = await self._get_db()
            groupings_collection = db.datasource_groupings

            groupings_data = await groupings_collection.find({}).to_list(length=None)
            return [DataSourceGrouping(**data) for data in groupings_data]
        except Exception as e:
            print(f"❌ 获取数据源分组关系失败: {e}")
            return []

    async def add_datasource_to_category(self, grouping: DataSourceGrouping) -> bool:
        """将数据源添加到分类"""
        try:
            db = await self._get_db()
            groupings_collection = db.datasource_groupings

            # 检查是否已存在
            existing = await groupings_collection.find_one({
                "data_source_name": grouping.data_source_name,
                "market_category_id": grouping.market_category_id
            })
            if existing:
                return False

            await groupings_collection.insert_one(grouping.dict())
            return True
        except Exception as e:
            print(f"❌ 添加数据源到分类失败: {e}")
            return False

    async def remove_datasource_from_category(self, data_source_name: str, category_id: str) -> bool:
        """从分类中移除数据源"""
        try:
            db = await self._get_db()
            groupings_collection = db.datasource_groupings

            result = await groupings_collection.delete_one({
                "data_source_name": data_source_name,
                "market_category_id": category_id
            })
            return result.deleted_count > 0
        except Exception as e:
            print(f"❌ 从分类中移除数据源失败: {e}")
            return False

    async def update_datasource_grouping(self, data_source_name: str, category_id: str, updates: Dict[str, Any]) -> bool:
        """更新数据源分组关系"""
        try:
            db = await self._get_db()
            groupings_collection = db.datasource_groupings

            updates["updated_at"] = datetime.utcnow()
            result = await groupings_collection.update_one(
                {
                    "data_source_name": data_source_name,
                    "market_category_id": category_id
                },
                {"$set": updates}
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"❌ 更新数据源分组关系失败: {e}")
            return False

    async def update_category_datasource_order(self, category_id: str, ordered_datasources: List[Dict[str, Any]]) -> bool:
        """更新分类中数据源的排序"""
        try:
            db = await self._get_db()
            groupings_collection = db.datasource_groupings

            # 批量更新优先级
            for item in ordered_datasources:
                await groupings_collection.update_one(
                    {
                        "data_source_name": item["name"],
                        "market_category_id": category_id
                    },
                    {
                        "$set": {
                            "priority": item["priority"],
                            "updated_at": datetime.utcnow()
                        }
                    }
                )
            return True
        except Exception as e:
            print(f"❌ 更新分类数据源排序失败: {e}")
            return False

    async def get_system_config(self) -> Optional[SystemConfig]:
        """获取系统配置 - 优先从数据库获取最新数据"""
        try:
            # 直接从数据库获取最新配置，避免缓存问题
            db = await self._get_db()
            config_collection = db.system_configs

            config_data = await config_collection.find_one(
                {"is_active": True},
                sort=[("version", -1)]
            )

            if config_data:
                print(f"📊 从数据库获取配置，版本: {config_data.get('version', 0)}, LLM配置数量: {len(config_data.get('llm_configs', []))}")
                return SystemConfig(**config_data)

            # 如果没有配置，创建默认配置
            print("⚠️ 数据库中没有配置，创建默认配置")
            return await self._create_default_config()

        except Exception as e:
            print(f"❌ 从数据库获取配置失败: {e}")

            # 作为最后的回退，尝试从统一配置管理器获取
            try:
                unified_system_config = await unified_config.get_unified_system_config()
                if unified_system_config:
                    print("🔄 回退到统一配置管理器")
                    return unified_system_config
            except Exception as e2:
                print(f"从统一配置获取也失败: {e2}")

            return None
    
    async def _create_default_config(self) -> SystemConfig:
        """创建默认系统配置"""
        default_config = SystemConfig(
            config_name="默认配置",
            config_type="system",
            llm_configs=[
                LLMConfig(
                    provider=ModelProvider.OPENAI,
                    model_name="gpt-3.5-turbo",
                    api_key="your-openai-api-key",
                    api_base="https://api.openai.com/v1",
                    max_tokens=4000,
                    temperature=0.7,
                    enabled=False,
                    description="OpenAI GPT-3.5 Turbo模型"
                ),
                LLMConfig(
                    provider=ModelProvider.ZHIPU,
                    model_name="glm-4",
                    api_key="your-zhipu-api-key",
                    api_base="https://open.bigmodel.cn/api/paas/v4",
                    max_tokens=4000,
                    temperature=0.7,
                    enabled=True,
                    description="智谱AI GLM-4模型（推荐）"
                ),
                LLMConfig(
                    provider=ModelProvider.QWEN,
                    model_name="qwen-turbo",
                    api_key="your-qwen-api-key",
                    api_base="https://dashscope.aliyuncs.com/api/v1",
                    max_tokens=4000,
                    temperature=0.7,
                    enabled=False,
                    description="阿里云通义千问模型"
                )
            ],
            default_llm="glm-4",
            data_source_configs=[
                DataSourceConfig(
                    name="AKShare",
                    type=DataSourceType.AKSHARE,
                    endpoint="https://akshare.akfamily.xyz",
                    timeout=30,
                    rate_limit=100,
                    enabled=True,
                    priority=1,
                    description="AKShare开源金融数据接口"
                ),
                DataSourceConfig(
                    name="Tushare",
                    type=DataSourceType.TUSHARE,
                    api_key="your-tushare-token",
                    endpoint="http://api.tushare.pro",
                    timeout=30,
                    rate_limit=200,
                    enabled=False,
                    priority=2,
                    description="Tushare专业金融数据接口"
                )
            ],
            default_data_source="AKShare",
            database_configs=[
                DatabaseConfig(
                    name="MongoDB主库",
                    type=DatabaseType.MONGODB,
                    host="localhost",
                    port=27017,
                    database="tradingagents",
                    enabled=True,
                    description="MongoDB主数据库"
                ),
                DatabaseConfig(
                    name="Redis缓存",
                    type=DatabaseType.REDIS,
                    host="localhost",
                    port=6379,
                    database="0",
                    enabled=True,
                    description="Redis缓存数据库"
                )
            ],
            system_settings={
                "max_concurrent_tasks": 3,
                "default_analysis_timeout": 300,
                "enable_cache": True,
                "cache_ttl": 3600,
                "log_level": "INFO",
                "enable_monitoring": True
            }
        )
        
        # 保存到数据库
        await self.save_system_config(default_config)
        return default_config
    
    async def save_system_config(self, config: SystemConfig) -> bool:
        """保存系统配置到数据库"""
        try:
            print(f"💾 开始保存配置，LLM配置数量: {len(config.llm_configs)}")

            # 保存到数据库
            db = await self._get_db()
            config_collection = db.system_configs

            # 更新时间戳和版本
            config.updated_at = datetime.utcnow()
            config.version += 1

            # 将当前激活的配置设为非激活
            update_result = await config_collection.update_many(
                {"is_active": True},
                {"$set": {"is_active": False}}
            )
            print(f"📝 禁用旧配置数量: {update_result.modified_count}")

            # 插入新配置 - 移除_id字段让MongoDB自动生成新的
            config_dict = config.dict(by_alias=True)
            if '_id' in config_dict:
                del config_dict['_id']  # 移除旧的_id，让MongoDB生成新的

            insert_result = await config_collection.insert_one(config_dict)
            print(f"📝 新配置ID: {insert_result.inserted_id}")

            # 验证保存结果
            saved_config = await config_collection.find_one({"_id": insert_result.inserted_id})
            if saved_config:
                print(f"✅ 配置保存成功，验证LLM配置数量: {len(saved_config.get('llm_configs', []))}")

                # 暂时跳过统一配置同步，避免冲突
                # unified_config.sync_to_legacy_format(config)

                return True
            else:
                print("❌ 配置保存验证失败")
                return False

        except Exception as e:
            print(f"❌ 保存配置失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def delete_llm_config(self, provider: str, model_name: str) -> bool:
        """删除大模型配置"""
        try:
            print(f"🗑️ 删除大模型配置 - provider: {provider}, model_name: {model_name}")

            config = await self.get_system_config()
            if not config:
                print("❌ 系统配置为空")
                return False

            print(f"📊 当前大模型配置数量: {len(config.llm_configs)}")

            # 打印所有现有配置
            for i, llm in enumerate(config.llm_configs):
                print(f"   {i+1}. provider: {llm.provider.value}, model_name: {llm.model_name}")

            # 查找并删除指定的LLM配置
            original_count = len(config.llm_configs)

            # 使用更宽松的匹配条件
            config.llm_configs = [
                llm for llm in config.llm_configs
                if not (str(llm.provider.value).lower() == provider.lower() and llm.model_name == model_name)
            ]

            new_count = len(config.llm_configs)
            print(f"🔄 删除后配置数量: {new_count} (原来: {original_count})")

            if new_count == original_count:
                print(f"❌ 没有找到匹配的配置: {provider}/{model_name}")
                return False  # 没有找到要删除的配置

            # 保存更新后的配置
            save_result = await self.save_system_config(config)
            print(f"💾 保存结果: {save_result}")

            return save_result

        except Exception as e:
            print(f"❌ 删除LLM配置失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def set_default_llm(self, model_name: str) -> bool:
        """设置默认大模型"""
        try:
            config = await self.get_system_config()
            if not config:
                return False

            # 检查指定的模型是否存在
            model_exists = any(
                llm.model_name == model_name for llm in config.llm_configs
            )

            if not model_exists:
                return False

            config.default_llm = model_name
            return await self.save_system_config(config)

        except Exception as e:
            print(f"设置默认LLM失败: {e}")
            return False

    async def set_default_data_source(self, data_source_name: str) -> bool:
        """设置默认数据源"""
        try:
            config = await self.get_system_config()
            if not config:
                return False

            # 检查指定的数据源是否存在
            source_exists = any(
                ds.name == data_source_name for ds in config.data_source_configs
            )

            if not source_exists:
                return False

            config.default_data_source = data_source_name
            return await self.save_system_config(config)

        except Exception as e:
            print(f"设置默认数据源失败: {e}")
            return False

    async def update_system_settings(self, settings: Dict[str, Any]) -> bool:
        """更新系统设置"""
        try:
            config = await self.get_system_config()
            if not config:
                return False

            # 更新系统设置
            config.system_settings.update(settings)
            return await self.save_system_config(config)

        except Exception as e:
            print(f"更新系统设置失败: {e}")
            return False

    async def get_system_settings(self) -> Dict[str, Any]:
        """获取系统设置"""
        try:
            config = await self.get_system_config()
            if not config:
                return {}
            return config.system_settings
        except Exception as e:
            print(f"获取系统设置失败: {e}")
            return {}

    async def export_config(self) -> Dict[str, Any]:
        """导出配置"""
        try:
            config = await self.get_system_config()
            if not config:
                return {}

            # 转换为可序列化的字典格式
            # 方案A：导出时对敏感字段脱敏/清空
            def _llm_sanitize(x: LLMConfig):
                d = x.dict()
                d["api_key"] = ""
                return d
            def _ds_sanitize(x: DataSourceConfig):
                d = x.dict()
                d["api_key"] = ""
                d["api_secret"] = ""
                return d
            def _db_sanitize(x: DatabaseConfig):
                d = x.dict()
                d["password"] = ""
                return d
            export_data = {
                "config_name": config.config_name,
                "config_type": config.config_type,
                "llm_configs": [_llm_sanitize(llm) for llm in config.llm_configs],
                "default_llm": config.default_llm,
                "data_source_configs": [_ds_sanitize(ds) for ds in config.data_source_configs],
                "default_data_source": config.default_data_source,
                "database_configs": [_db_sanitize(db) for db in config.database_configs],
                "system_settings": config.system_settings,
                "exported_at": datetime.utcnow().isoformat(),
                "version": config.version
            }

            return export_data

        except Exception as e:
            print(f"导出配置失败: {e}")
            return {}

    async def import_config(self, config_data: Dict[str, Any]) -> bool:
        """导入配置"""
        try:
            # 验证配置数据格式
            if not self._validate_config_data(config_data):
                return False

            # 创建新的系统配置
            new_config = SystemConfig(
                config_name=config_data.get("config_name", "导入的配置"),
                config_type="imported",
                llm_configs=[LLMConfig(**llm) for llm in config_data.get("llm_configs", [])],
                default_llm=config_data.get("default_llm"),
                data_source_configs=[DataSourceConfig(**ds) for ds in config_data.get("data_source_configs", [])],
                default_data_source=config_data.get("default_data_source"),
                database_configs=[DatabaseConfig(**db) for db in config_data.get("database_configs", [])],
                system_settings=config_data.get("system_settings", {})
            )

            return await self.save_system_config(new_config)

        except Exception as e:
            print(f"导入配置失败: {e}")
            return False

    def _validate_config_data(self, config_data: Dict[str, Any]) -> bool:
        """验证配置数据格式"""
        try:
            required_fields = ["llm_configs", "data_source_configs", "database_configs", "system_settings"]
            for field in required_fields:
                if field not in config_data:
                    print(f"配置数据缺少必需字段: {field}")
                    return False

            return True

        except Exception as e:
            print(f"验证配置数据失败: {e}")
            return False

    async def migrate_legacy_config(self) -> bool:
        """迁移传统配置"""
        try:
            # 这里可以调用迁移脚本的逻辑
            # 或者直接在这里实现迁移逻辑
            from scripts.migrate_config_to_webapi import ConfigMigrator

            migrator = ConfigMigrator()
            return await migrator.migrate_all_configs()

        except Exception as e:
            print(f"迁移传统配置失败: {e}")
            return False
    
    async def update_llm_config(self, llm_config: LLMConfig) -> bool:
        """更新大模型配置"""
        try:
            # 直接保存到统一配置管理器
            success = unified_config.save_llm_config(llm_config)
            if not success:
                return False

            # 同时更新数据库配置
            config = await self.get_system_config()
            if not config:
                return False

            # 查找并更新对应的LLM配置
            for i, existing_config in enumerate(config.llm_configs):
                if existing_config.model_name == llm_config.model_name:
                    config.llm_configs[i] = llm_config
                    break
            else:
                # 如果不存在，添加新配置
                config.llm_configs.append(llm_config)

            return await self.save_system_config(config)
        except Exception as e:
            print(f"更新LLM配置失败: {e}")
            return False
    
    async def test_llm_config(self, llm_config: LLMConfig) -> Dict[str, Any]:
        """测试大模型配置"""
        start_time = time.time()
        try:
            # 这里应该实际调用LLM API进行测试
            # 目前返回模拟结果
            await asyncio.sleep(1)  # 模拟API调用
            
            response_time = time.time() - start_time
            
            return {
                "success": True,
                "message": f"成功连接到 {llm_config.provider.value} {llm_config.model_name}",
                "response_time": response_time,
                "details": {
                    "provider": llm_config.provider.value,
                    "model": llm_config.model_name,
                    "api_base": llm_config.api_base
                }
            }
        except Exception as e:
            response_time = time.time() - start_time
            return {
                "success": False,
                "message": f"连接失败: {str(e)}",
                "response_time": response_time,
                "details": None
            }
    
    async def test_data_source_config(self, ds_config: DataSourceConfig) -> Dict[str, Any]:
        """测试数据源配置"""
        start_time = time.time()
        try:
            # 这里应该实际调用数据源API进行测试
            await asyncio.sleep(0.5)  # 模拟API调用
            
            response_time = time.time() - start_time
            
            return {
                "success": True,
                "message": f"成功连接到数据源 {ds_config.name}",
                "response_time": response_time,
                "details": {
                    "type": ds_config.type.value,
                    "endpoint": ds_config.endpoint
                }
            }
        except Exception as e:
            response_time = time.time() - start_time
            return {
                "success": False,
                "message": f"连接失败: {str(e)}",
                "response_time": response_time,
                "details": None
            }
    
    async def test_database_config(self, db_config: DatabaseConfig) -> Dict[str, Any]:
        """测试数据库配置"""
        start_time = time.time()
        try:
            # 这里应该实际测试数据库连接
            await asyncio.sleep(0.3)  # 模拟连接测试
            
            response_time = time.time() - start_time
            
            return {
                "success": True,
                "message": f"成功连接到数据库 {db_config.name}",
                "response_time": response_time,
                "details": {
                    "type": db_config.type.value,
                    "host": db_config.host,
                    "port": db_config.port
                }
            }
        except Exception as e:
            response_time = time.time() - start_time
            return {
                "success": False,
                "message": f"连接失败: {str(e)}",
                "response_time": response_time,
                "details": None
            }
    
    async def get_available_models(self) -> List[Dict[str, Any]]:
        """获取可用的模型列表"""
        return [
            {
                "provider": "openai",
                "models": ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo"]
            },
            {
                "provider": "anthropic", 
                "models": ["claude-3-haiku", "claude-3-sonnet", "claude-3-opus"]
            },
            {
                "provider": "zhipu",
                "models": ["glm-4", "glm-3-turbo", "chatglm3-6b"]
            },
            {
                "provider": "qwen",
                "models": ["qwen-turbo", "qwen-plus", "qwen-max"]
            },
            {
                "provider": "baidu",
                "models": ["ernie-bot", "ernie-bot-turbo", "ernie-bot-4"]
            }
        ]


    async def set_default_llm(self, model_name: str) -> bool:
        """设置默认大模型"""
        try:
            config = await self.get_system_config()
            if not config:
                return False

            # 检查模型是否存在
            model_exists = any(
                llm.model_name == model_name
                for llm in config.llm_configs
            )

            if not model_exists:
                return False

            config.default_llm = model_name
            return await self.save_system_config(config)
        except Exception as e:
            print(f"设置默认LLM失败: {e}")
            return False

    async def set_default_data_source(self, source_name: str) -> bool:
        """设置默认数据源"""
        try:
            config = await self.get_system_config()
            if not config:
                return False

            # 检查数据源是否存在
            source_exists = any(
                ds.name == source_name
                for ds in config.data_source_configs
            )

            if not source_exists:
                return False

            config.default_data_source = source_name
            return await self.save_system_config(config)
        except Exception as e:
            print(f"设置默认数据源失败: {e}")
            return False

    # ========== 大模型厂家管理 ==========

    async def get_llm_providers(self) -> List[LLMProvider]:
        """获取所有大模型厂家（合并环境变量配置）"""
        try:
            db = await self._get_db()
            providers_collection = db.llm_providers

            providers_data = await providers_collection.find().to_list(length=None)
            providers = []

            for provider_data in providers_data:
                provider = LLMProvider(**provider_data)
                # 如果厂家配置中没有API密钥，尝试从环境变量获取
                if not provider.api_key:
                    env_key = self._get_env_api_key(provider.name)
                    if env_key:
                        provider.api_key = env_key
                        provider.extra_config = provider.extra_config or {}
                        provider.extra_config["source"] = "environment"
                        print(f"✅ 从环境变量为厂家 {provider.display_name} 获取API密钥")

                providers.append(provider)

            return providers
        except Exception as e:
            print(f"获取厂家列表失败: {e}")
            return []

    def _get_env_api_key(self, provider_name: str) -> Optional[str]:
        """从环境变量获取API密钥"""
        import os

        # 环境变量映射表
        env_key_mapping = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GOOGLE_API_KEY",
            "zhipu": "ZHIPU_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "dashscope": "DASHSCOPE_API_KEY",
            "qianfan": "QIANFAN_API_KEY",
            "azure": "AZURE_OPENAI_API_KEY",
            "siliconflow": "SILICONFLOW_API_KEY",
            "openrouter": "OPENROUTER_API_KEY"
        }

        env_var = env_key_mapping.get(provider_name)
        if env_var:
            api_key = os.getenv(env_var)
            # 过滤掉占位符
            if api_key and not api_key.startswith('your_'):
                return api_key

        return None

    async def add_llm_provider(self, provider: LLMProvider) -> str:
        """添加大模型厂家"""
        try:
            db = await self._get_db()
            providers_collection = db.llm_providers

            # 检查厂家名称是否已存在
            existing = await providers_collection.find_one({"name": provider.name})
            if existing:
                raise ValueError(f"厂家 {provider.name} 已存在")

            provider.created_at = datetime.utcnow()
            provider.updated_at = datetime.utcnow()

            result = await providers_collection.insert_one(provider.dict(by_alias=True))
            return str(result.inserted_id)
        except Exception as e:
            print(f"添加厂家失败: {e}")
            raise

    async def update_llm_provider(self, provider_id: str, update_data: Dict[str, Any]) -> bool:
        """更新大模型厂家"""
        try:
            db = await self._get_db()
            providers_collection = db.llm_providers

            update_data["updated_at"] = datetime.utcnow()

            result = await providers_collection.update_one(
                {"_id": ObjectId(provider_id)},
                {"$set": update_data}
            )

            return result.modified_count > 0
        except Exception as e:
            print(f"更新厂家失败: {e}")
            return False

    async def delete_llm_provider(self, provider_id: str) -> bool:
        """删除大模型厂家"""
        try:
            print(f"🗑️ 删除厂家 - provider_id: {provider_id}")
            print(f"🔍 ObjectId类型: {type(ObjectId(provider_id))}")

            db = await self._get_db()
            providers_collection = db.llm_providers
            print(f"📊 数据库: {db.name}, 集合: {providers_collection.name}")

            # 先列出所有厂家的ID，看看格式
            all_providers = await providers_collection.find({}, {"_id": 1, "display_name": 1}).to_list(length=None)
            print(f"📋 数据库中所有厂家ID:")
            for p in all_providers:
                print(f"   - {p['_id']} ({type(p['_id'])}) - {p.get('display_name')}")
                if str(p['_id']) == provider_id:
                    print(f"   ✅ 找到匹配的ID!")

            # 尝试不同的查找方式
            print(f"🔍 尝试用ObjectId查找...")
            existing1 = await providers_collection.find_one({"_id": ObjectId(provider_id)})

            print(f"🔍 尝试用字符串查找...")
            existing2 = await providers_collection.find_one({"_id": provider_id})

            print(f"🔍 ObjectId查找结果: {existing1 is not None}")
            print(f"🔍 字符串查找结果: {existing2 is not None}")

            existing = existing1 or existing2
            if not existing:
                print(f"❌ 两种方式都找不到厂家: {provider_id}")
                return False

            print(f"✅ 找到厂家: {existing.get('display_name')}")

            # 使用找到的方式进行删除
            if existing1:
                result = await providers_collection.delete_one({"_id": ObjectId(provider_id)})
            else:
                result = await providers_collection.delete_one({"_id": provider_id})

            success = result.deleted_count > 0

            print(f"🗑️ 删除结果: {success}, deleted_count: {result.deleted_count}")
            return success

        except Exception as e:
            print(f"❌ 删除厂家失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def toggle_llm_provider(self, provider_id: str, is_active: bool) -> bool:
        """切换大模型厂家状态"""
        try:
            db = await self._get_db()
            providers_collection = db.llm_providers

            result = await providers_collection.update_one(
                {"_id": ObjectId(provider_id)},
                {"$set": {"is_active": is_active, "updated_at": datetime.utcnow()}}
            )

            return result.modified_count > 0
        except Exception as e:
            print(f"切换厂家状态失败: {e}")
            return False

    async def migrate_env_to_providers(self) -> Dict[str, Any]:
        """将环境变量配置迁移到厂家管理"""
        import os

        try:
            db = await self._get_db()
            providers_collection = db.llm_providers

            # 预设厂家配置
            default_providers = [
                {
                    "name": "openai",
                    "display_name": "OpenAI",
                    "description": "OpenAI是人工智能领域的领先公司，提供GPT系列模型",
                    "website": "https://openai.com",
                    "api_doc_url": "https://platform.openai.com/docs",
                    "default_base_url": "https://api.openai.com/v1",
                    "supported_features": ["chat", "completion", "embedding", "image", "vision", "function_calling", "streaming"]
                },
                {
                    "name": "anthropic",
                    "display_name": "Anthropic",
                    "description": "Anthropic专注于AI安全研究，提供Claude系列模型",
                    "website": "https://anthropic.com",
                    "api_doc_url": "https://docs.anthropic.com",
                    "default_base_url": "https://api.anthropic.com",
                    "supported_features": ["chat", "completion", "function_calling", "streaming"]
                },
                {
                    "name": "dashscope",
                    "display_name": "阿里云百炼",
                    "description": "阿里云百炼大模型服务平台，提供通义千问等模型",
                    "website": "https://bailian.console.aliyun.com",
                    "api_doc_url": "https://help.aliyun.com/zh/dashscope/",
                    "default_base_url": "https://dashscope.aliyuncs.com/api/v1",
                    "supported_features": ["chat", "completion", "embedding", "function_calling", "streaming"]
                },
                {
                    "name": "deepseek",
                    "display_name": "DeepSeek",
                    "description": "DeepSeek提供高性能的AI推理服务",
                    "website": "https://www.deepseek.com",
                    "api_doc_url": "https://platform.deepseek.com/api-docs",
                    "default_base_url": "https://api.deepseek.com",
                    "supported_features": ["chat", "completion", "function_calling", "streaming"]
                }
            ]

            migrated_count = 0
            updated_count = 0
            skipped_count = 0

            for provider_config in default_providers:
                # 从环境变量获取API密钥
                api_key = self._get_env_api_key(provider_config["name"])

                # 检查是否已存在
                existing = await providers_collection.find_one({"name": provider_config["name"]})

                if existing:
                    # 如果已存在但没有API密钥，且环境变量中有密钥，则更新
                    if not existing.get("api_key") and api_key:
                        update_data = {
                            "api_key": api_key,
                            "is_active": True,
                            "extra_config": {"migrated_from": "environment"},
                            "updated_at": datetime.utcnow()
                        }
                        await providers_collection.update_one(
                            {"name": provider_config["name"]},
                            {"$set": update_data}
                        )
                        updated_count += 1
                        print(f"✅ 更新厂家 {provider_config['display_name']} 的API密钥")
                    else:
                        skipped_count += 1
                        print(f"⏭️ 跳过厂家 {provider_config['display_name']} (已有配置)")
                    continue

                # 创建新厂家配置
                provider_data = {
                    **provider_config,
                    "api_key": api_key,
                    "is_active": bool(api_key),  # 有密钥的自动启用
                    "extra_config": {"migrated_from": "environment"} if api_key else {},
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }

                await providers_collection.insert_one(provider_data)
                migrated_count += 1
                print(f"✅ 创建厂家 {provider_config['display_name']}")

            total_changes = migrated_count + updated_count
            message_parts = []
            if migrated_count > 0:
                message_parts.append(f"新建 {migrated_count} 个厂家")
            if updated_count > 0:
                message_parts.append(f"更新 {updated_count} 个厂家的API密钥")
            if skipped_count > 0:
                message_parts.append(f"跳过 {skipped_count} 个已配置的厂家")

            if total_changes > 0:
                message = "迁移完成：" + "，".join(message_parts)
            else:
                message = "所有厂家都已配置，无需迁移"

            return {
                "success": True,
                "migrated_count": migrated_count,
                "updated_count": updated_count,
                "skipped_count": skipped_count,
                "message": message
            }

        except Exception as e:
            print(f"环境变量迁移失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "环境变量迁移失败"
            }

    async def test_provider_api(self, provider_id: str) -> dict:
        """测试厂家API密钥"""
        try:
            print(f"🔍 测试厂家API - provider_id: {provider_id}")

            db = await self._get_db()
            providers_collection = db.llm_providers

            # 查找厂家
            from bson import ObjectId
            try:
                provider_data = await providers_collection.find_one({"_id": ObjectId(provider_id)})
            except Exception as e:
                print(f"❌ ObjectId转换失败: {e}")
                return {
                    "success": False,
                    "message": f"无效的厂家ID格式: {provider_id}"
                }

            if not provider_data:
                # 尝试查找所有厂家，看看数据库中有什么
                all_providers = await providers_collection.find().to_list(length=None)
                print(f"📊 数据库中的所有厂家:")
                for p in all_providers:
                    print(f"   - ID: {p['_id']}, name: {p.get('name')}, display_name: {p.get('display_name')}")

                return {
                    "success": False,
                    "message": f"厂家不存在 (ID: {provider_id})"
                }

            provider_name = provider_data.get("name")
            api_key = provider_data.get("api_key")
            display_name = provider_data.get("display_name", provider_name)

            if not api_key:
                return {
                    "success": False,
                    "message": f"{display_name} 未配置API密钥"
                }

            # 根据厂家类型调用相应的测试函数
            test_result = await self._test_provider_connection(provider_name, api_key, display_name)

            return test_result

        except Exception as e:
            print(f"测试厂家API失败: {e}")
            return {
                "success": False,
                "message": f"测试失败: {str(e)}"
            }

    async def _test_provider_connection(self, provider_name: str, api_key: str, display_name: str) -> dict:
        """测试具体厂家的连接"""
        import asyncio

        try:
            if provider_name == "google":
                return await asyncio.get_event_loop().run_in_executor(None, self._test_google_api, api_key, display_name)
            elif provider_name == "deepseek":
                return await asyncio.get_event_loop().run_in_executor(None, self._test_deepseek_api, api_key, display_name)
            elif provider_name == "dashscope":
                return await asyncio.get_event_loop().run_in_executor(None, self._test_dashscope_api, api_key, display_name)
            elif provider_name == "openrouter":
                return await asyncio.get_event_loop().run_in_executor(None, self._test_openrouter_api, api_key, display_name)
            elif provider_name == "openai":
                return await asyncio.get_event_loop().run_in_executor(None, self._test_openai_api, api_key, display_name)
            elif provider_name == "anthropic":
                return await asyncio.get_event_loop().run_in_executor(None, self._test_anthropic_api, api_key, display_name)
            elif provider_name == "qianfan":
                return await asyncio.get_event_loop().run_in_executor(None, self._test_qianfan_api, api_key, display_name)
            else:
                return {
                    "success": False,
                    "message": f"暂不支持测试 {display_name} 厂家"
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"{display_name} 连接测试失败: {str(e)}"
            }

    def _test_google_api(self, api_key: str, display_name: str) -> dict:
        """测试Google AI API"""
        try:
            import requests

            # 使用正确的Google AI Gemini API端点
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"

            headers = {
                "Content-Type": "application/json"
            }

            data = {
                "contents": [{
                    "parts": [{
                        "text": "Hello, please introduce yourself briefly."
                    }]
                }],
                "generationConfig": {
                    "maxOutputTokens": 50,
                    "temperature": 0.1
                }
            }

            response = requests.post(url, json=data, headers=headers, timeout=15)

            if response.status_code == 200:
                result = response.json()
                if "candidates" in result and len(result["candidates"]) > 0:
                    candidate = result["candidates"][0]
                    if "content" in candidate and "parts" in candidate["content"]:
                        text = candidate["content"]["parts"][0].get("text", "")
                        if text and len(text.strip()) > 0:
                            return {
                                "success": True,
                                "message": f"{display_name} API连接测试成功"
                            }
                        else:
                            return {
                                "success": False,
                                "message": f"{display_name} API响应内容为空"
                            }
                    else:
                        return {
                            "success": False,
                            "message": f"{display_name} API响应格式异常"
                        }
                else:
                    return {
                        "success": False,
                        "message": f"{display_name} API无有效候选响应"
                    }
            elif response.status_code == 400:
                try:
                    error_detail = response.json()
                    error_msg = error_detail.get("error", {}).get("message", "未知错误")
                    return {
                        "success": False,
                        "message": f"{display_name} API请求错误: {error_msg}"
                    }
                except:
                    return {
                        "success": False,
                        "message": f"{display_name} API请求格式错误"
                    }
            elif response.status_code == 403:
                return {
                    "success": False,
                    "message": f"{display_name} API密钥无效或权限不足"
                }
            else:
                return {
                    "success": False,
                    "message": f"{display_name} API测试失败: HTTP {response.status_code}"
                }

        except Exception as e:
            return {
                "success": False,
                "message": f"{display_name} API测试异常: {str(e)}"
            }

    def _test_deepseek_api(self, api_key: str, display_name: str) -> dict:
        """测试DeepSeek API"""
        try:
            import requests

            url = "https://api.deepseek.com/chat/completions"

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }

            data = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "user", "content": "你好，请简单介绍一下你自己。"}
                ],
                "max_tokens": 50,
                "temperature": 0.1
            }

            response = requests.post(url, json=data, headers=headers, timeout=10)

            if response.status_code == 200:
                result = response.json()
                if "choices" in result and len(result["choices"]) > 0:
                    content = result["choices"][0]["message"]["content"]
                    if content and len(content.strip()) > 0:
                        return {
                            "success": True,
                            "message": f"{display_name} API连接测试成功"
                        }
                    else:
                        return {
                            "success": False,
                            "message": f"{display_name} API响应为空"
                        }
                else:
                    return {
                        "success": False,
                        "message": f"{display_name} API响应格式异常"
                    }
            else:
                return {
                    "success": False,
                    "message": f"{display_name} API测试失败: HTTP {response.status_code}"
                }

        except Exception as e:
            return {
                "success": False,
                "message": f"{display_name} API测试异常: {str(e)}"
            }

    def _test_dashscope_api(self, api_key: str, display_name: str) -> dict:
        """测试阿里云百炼API"""
        try:
            import requests

            # 使用阿里云百炼的OpenAI兼容接口
            url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }

            data = {
                "model": "qwen-turbo",
                "messages": [
                    {"role": "user", "content": "你好，请简单介绍一下你自己。"}
                ],
                "max_tokens": 50,
                "temperature": 0.1
            }

            response = requests.post(url, json=data, headers=headers, timeout=10)

            if response.status_code == 200:
                result = response.json()
                if "choices" in result and len(result["choices"]) > 0:
                    content = result["choices"][0]["message"]["content"]
                    if content and len(content.strip()) > 0:
                        return {
                            "success": True,
                            "message": f"{display_name} API连接测试成功"
                        }
                    else:
                        return {
                            "success": False,
                            "message": f"{display_name} API响应为空"
                        }
                else:
                    return {
                        "success": False,
                        "message": f"{display_name} API响应格式异常"
                    }
            else:
                return {
                    "success": False,
                    "message": f"{display_name} API测试失败: HTTP {response.status_code}"
                }

        except Exception as e:
            return {
                "success": False,
                "message": f"{display_name} API测试异常: {str(e)}"
            }

    def _test_openrouter_api(self, api_key: str, display_name: str) -> dict:
        """测试OpenRouter API"""
        try:
            import requests

            url = "https://openrouter.ai/api/v1/chat/completions"

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://tradingagents.cn",  # OpenRouter要求
                "X-Title": "TradingAgents-CN"
            }

            data = {
                "model": "meta-llama/llama-3.2-3b-instruct:free",  # 使用免费模型
                "messages": [
                    {"role": "user", "content": "你好，请简单介绍一下你自己。"}
                ],
                "max_tokens": 50,
                "temperature": 0.1
            }

            response = requests.post(url, json=data, headers=headers, timeout=15)

            if response.status_code == 200:
                result = response.json()
                if "choices" in result and len(result["choices"]) > 0:
                    content = result["choices"][0]["message"]["content"]
                    if content and len(content.strip()) > 0:
                        return {
                            "success": True,
                            "message": f"{display_name} API连接测试成功"
                        }
                    else:
                        return {
                            "success": False,
                            "message": f"{display_name} API响应为空"
                        }
                else:
                    return {
                        "success": False,
                        "message": f"{display_name} API响应格式异常"
                    }
            else:
                return {
                    "success": False,
                    "message": f"{display_name} API测试失败: HTTP {response.status_code}"
                }

        except Exception as e:
            return {
                "success": False,
                "message": f"{display_name} API测试异常: {str(e)}"
            }

    def _test_openai_api(self, api_key: str, display_name: str) -> dict:
        """测试OpenAI API"""
        try:
            import requests

            url = "https://api.openai.com/v1/chat/completions"

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }

            data = {
                "model": "gpt-3.5-turbo",
                "messages": [
                    {"role": "user", "content": "你好，请简单介绍一下你自己。"}
                ],
                "max_tokens": 50,
                "temperature": 0.1
            }

            response = requests.post(url, json=data, headers=headers, timeout=10)

            if response.status_code == 200:
                result = response.json()
                if "choices" in result and len(result["choices"]) > 0:
                    content = result["choices"][0]["message"]["content"]
                    if content and len(content.strip()) > 0:
                        return {
                            "success": True,
                            "message": f"{display_name} API连接测试成功"
                        }
                    else:
                        return {
                            "success": False,
                            "message": f"{display_name} API响应为空"
                        }
                else:
                    return {
                        "success": False,
                        "message": f"{display_name} API响应格式异常"
                    }
            else:
                return {
                    "success": False,
                    "message": f"{display_name} API测试失败: HTTP {response.status_code}"
                }

        except Exception as e:
            return {
                "success": False,
                "message": f"{display_name} API测试异常: {str(e)}"
            }

    def _test_anthropic_api(self, api_key: str, display_name: str) -> dict:
        """测试Anthropic API"""
        try:
            import requests

            url = "https://api.anthropic.com/v1/messages"

            headers = {
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01"
            }

            data = {
                "model": "claude-3-haiku-20240307",
                "max_tokens": 50,
                "messages": [
                    {"role": "user", "content": "你好，请简单介绍一下你自己。"}
                ]
            }

            response = requests.post(url, json=data, headers=headers, timeout=10)

            if response.status_code == 200:
                result = response.json()
                if "content" in result and len(result["content"]) > 0:
                    content = result["content"][0]["text"]
                    if content and len(content.strip()) > 0:
                        return {
                            "success": True,
                            "message": f"{display_name} API连接测试成功"
                        }
                    else:
                        return {
                            "success": False,
                            "message": f"{display_name} API响应为空"
                        }
                else:
                    return {
                        "success": False,
                        "message": f"{display_name} API响应格式异常"
                    }
            else:
                return {
                    "success": False,
                    "message": f"{display_name} API测试失败: HTTP {response.status_code}"
                }

        except Exception as e:
            return {
                "success": False,
                "message": f"{display_name} API测试异常: {str(e)}"
            }

    def _test_qianfan_api(self, api_key: str, display_name: str) -> dict:
        """测试百度千帆API"""
        try:
            import requests

            # 千帆新一代API使用OpenAI兼容接口
            url = "https://qianfan.baidubce.com/v2/chat/completions"

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }

            data = {
                "model": "ernie-3.5-8k",
                "messages": [
                    {"role": "user", "content": "你好，请简单介绍一下你自己。"}
                ],
                "max_tokens": 50,
                "temperature": 0.1
            }

            response = requests.post(url, json=data, headers=headers, timeout=15)

            if response.status_code == 200:
                result = response.json()
                if "choices" in result and len(result["choices"]) > 0:
                    content = result["choices"][0]["message"]["content"]
                    if content and len(content.strip()) > 0:
                        return {
                            "success": True,
                            "message": f"{display_name} API连接测试成功"
                        }
                    else:
                        return {
                            "success": False,
                            "message": f"{display_name} API响应为空"
                        }
                else:
                    return {
                        "success": False,
                        "message": f"{display_name} API响应格式异常"
                    }
            elif response.status_code == 401:
                return {
                    "success": False,
                    "message": f"{display_name} API密钥无效或已过期"
                }
            elif response.status_code == 403:
                return {
                    "success": False,
                    "message": f"{display_name} API权限不足或配额已用完"
                }
            else:
                try:
                    error_detail = response.json()
                    error_msg = error_detail.get("error", {}).get("message", f"HTTP {response.status_code}")
                    return {
                        "success": False,
                        "message": f"{display_name} API测试失败: {error_msg}"
                    }
                except:
                    return {
                        "success": False,
                        "message": f"{display_name} API测试失败: HTTP {response.status_code}"
                    }

        except Exception as e:
            return {
                "success": False,
                "message": f"{display_name} API测试异常: {str(e)}"
            }


# 创建全局实例
config_service = ConfigService()
