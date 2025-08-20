"""
系统配置相关数据模型
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from enum import Enum
from bson import ObjectId
from .user import PyObjectId


class ModelProvider(str, Enum):
    """大模型提供商枚举"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    ZHIPU = "zhipu"
    QWEN = "qwen"
    BAIDU = "baidu"
    TENCENT = "tencent"
    GEMINI = "gemini"
    GLM = "glm"
    CLAUDE = "claude"
    DEEPSEEK = "deepseek"
    DASHSCOPE = "dashscope"
    GOOGLE = "google"
    SILICONFLOW = "siliconflow"
    OPENROUTER = "openrouter"
    CUSTOM_OPENAI = "custom_openai"
    QIANFAN = "qianfan"
    LOCAL = "local"


class LLMProvider(BaseModel):
    """大模型厂家配置"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    name: str = Field(..., description="厂家唯一标识")
    display_name: str = Field(..., description="显示名称")
    description: Optional[str] = Field(None, description="厂家描述")
    website: Optional[str] = Field(None, description="官网地址")
    api_doc_url: Optional[str] = Field(None, description="API文档地址")
    logo_url: Optional[str] = Field(None, description="Logo地址")
    is_active: bool = Field(True, description="是否启用")
    supported_features: List[str] = Field(default_factory=list, description="支持的功能")
    default_base_url: Optional[str] = Field(None, description="默认API地址")
    api_key: Optional[str] = Field(None, description="API密钥")
    api_secret: Optional[str] = Field(None, description="API密钥（某些厂家需要）")
    extra_config: Dict[str, Any] = Field(default_factory=dict, description="额外配置参数")
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class LLMProviderRequest(BaseModel):
    """大模型厂家请求"""
    name: str = Field(..., description="厂家唯一标识")
    display_name: str = Field(..., description="显示名称")
    description: Optional[str] = Field(None, description="厂家描述")
    website: Optional[str] = Field(None, description="官网地址")
    api_doc_url: Optional[str] = Field(None, description="API文档地址")
    logo_url: Optional[str] = Field(None, description="Logo地址")
    is_active: bool = Field(True, description="是否启用")
    supported_features: List[str] = Field(default_factory=list, description="支持的功能")
    default_base_url: Optional[str] = Field(None, description="默认API地址")
    api_key: Optional[str] = Field(None, description="API密钥")
    api_secret: Optional[str] = Field(None, description="API密钥（某些厂家需要）")
    extra_config: Dict[str, Any] = Field(default_factory=dict, description="额外配置参数")


class LLMProviderResponse(BaseModel):
    """大模型厂家响应"""
    id: str
    name: str
    display_name: str
    description: Optional[str] = None
    website: Optional[str] = None
    api_doc_url: Optional[str] = None
    logo_url: Optional[str] = None
    is_active: bool
    supported_features: List[str]
    default_base_url: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    extra_config: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class DataSourceType(str, Enum):
    """数据源类型枚举"""
    TUSHARE = "tushare"
    AKSHARE = "akshare"
    YAHOO_FINANCE = "yahoo_finance"
    ALPHA_VANTAGE = "alpha_vantage"
    WIND = "wind"
    CHOICE = "choice"
    LOCAL_FILE = "local_file"


class DatabaseType(str, Enum):
    """数据库类型枚举"""
    MONGODB = "mongodb"
    MYSQL = "mysql"
    POSTGRESQL = "postgresql"
    REDIS = "redis"
    SQLITE = "sqlite"


class LLMConfig(BaseModel):
    """大模型配置"""
    provider: ModelProvider = ModelProvider.OPENAI
    model_name: str = Field(..., description="模型名称")
    api_key: Optional[str] = Field(None, description="API密钥(可选，优先从厂家配置获取)")
    api_base: Optional[str] = Field(None, description="API基础URL")
    max_tokens: int = Field(default=4000, description="最大token数")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="温度参数")
    timeout: int = Field(default=60, description="请求超时时间(秒)")
    retry_times: int = Field(default=3, description="重试次数")
    enabled: bool = Field(default=True, description="是否启用")
    description: Optional[str] = Field(None, description="配置描述")

    # 新增字段 - 来自sidebar.py的配置项
    model_category: Optional[str] = Field(None, description="模型类别(用于OpenRouter等)")
    custom_endpoint: Optional[str] = Field(None, description="自定义端点URL")
    enable_memory: bool = Field(default=False, description="启用记忆功能")
    enable_debug: bool = Field(default=False, description="启用调试模式")
    priority: int = Field(default=0, description="优先级")


class DataSourceConfig(BaseModel):
    """数据源配置"""
    name: str = Field(..., description="数据源名称")
    type: DataSourceType = Field(..., description="数据源类型")
    api_key: Optional[str] = Field(None, description="API密钥")
    api_secret: Optional[str] = Field(None, description="API密钥")
    endpoint: Optional[str] = Field(None, description="API端点")
    timeout: int = Field(default=30, description="请求超时时间(秒)")
    rate_limit: int = Field(default=100, description="每分钟请求限制")
    enabled: bool = Field(default=True, description="是否启用")
    priority: int = Field(default=0, description="优先级，数字越大优先级越高")
    config_params: Dict[str, Any] = Field(default_factory=dict, description="额外配置参数")
    description: Optional[str] = Field(None, description="配置描述")
    # 新增字段：支持市场分类
    market_categories: Optional[List[str]] = Field(default_factory=list, description="所属市场分类列表")
    display_name: Optional[str] = Field(None, description="显示名称")
    provider: Optional[str] = Field(None, description="数据提供商")
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow, description="创建时间")
    updated_at: Optional[datetime] = Field(default_factory=datetime.utcnow, description="更新时间")


class DatabaseConfig(BaseModel):
    """数据库配置"""
    name: str = Field(..., description="数据库名称")
    type: DatabaseType = Field(..., description="数据库类型")
    host: str = Field(..., description="主机地址")
    port: int = Field(..., description="端口号")
    username: Optional[str] = Field(None, description="用户名")
    password: Optional[str] = Field(None, description="密码")
    database: Optional[str] = Field(None, description="数据库名")
    connection_params: Dict[str, Any] = Field(default_factory=dict, description="连接参数")
    pool_size: int = Field(default=10, description="连接池大小")
    max_overflow: int = Field(default=20, description="最大溢出连接数")
    enabled: bool = Field(default=True, description="是否启用")
    description: Optional[str] = Field(None, description="配置描述")


class MarketCategory(BaseModel):
    """市场分类配置"""
    id: str = Field(..., description="分类ID")
    name: str = Field(..., description="分类名称")
    display_name: str = Field(..., description="显示名称")
    description: Optional[str] = Field(None, description="分类描述")
    enabled: bool = Field(default=True, description="是否启用")
    sort_order: int = Field(default=1, description="排序顺序")
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow, description="创建时间")
    updated_at: Optional[datetime] = Field(default_factory=datetime.utcnow, description="更新时间")


class DataSourceGrouping(BaseModel):
    """数据源分组关系"""
    data_source_name: str = Field(..., description="数据源名称")
    market_category_id: str = Field(..., description="市场分类ID")
    priority: int = Field(default=0, description="在该分类中的优先级")
    enabled: bool = Field(default=True, description="是否启用")
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow, description="创建时间")
    updated_at: Optional[datetime] = Field(default_factory=datetime.utcnow, description="更新时间")


class SystemConfig(BaseModel):
    """系统配置模型"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    config_name: str = Field(..., description="配置名称")
    config_type: str = Field(..., description="配置类型")
    
    # 大模型配置
    llm_configs: List[LLMConfig] = Field(default_factory=list, description="大模型配置列表")
    default_llm: Optional[str] = Field(None, description="默认大模型")
    
    # 数据源配置
    data_source_configs: List[DataSourceConfig] = Field(default_factory=list, description="数据源配置列表")
    default_data_source: Optional[str] = Field(None, description="默认数据源")
    
    # 数据库配置
    database_configs: List[DatabaseConfig] = Field(default_factory=list, description="数据库配置列表")
    
    # 系统设置
    system_settings: Dict[str, Any] = Field(default_factory=dict, description="系统设置")
    
    # 元数据
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[PyObjectId] = Field(None, description="创建者")
    updated_by: Optional[PyObjectId] = Field(None, description="更新者")
    version: int = Field(default=1, description="配置版本")
    is_active: bool = Field(default=True, description="是否激活")
    
    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


# API请求/响应模型

class LLMConfigRequest(BaseModel):
    """大模型配置请求"""
    provider: ModelProvider
    model_name: str
    api_key: Optional[str] = None  # 可选，优先从厂家配置获取
    api_base: Optional[str] = None
    max_tokens: int = 4000
    temperature: float = 0.7
    timeout: int = 60
    retry_times: int = 3
    enabled: bool = True
    description: Optional[str] = None

    # 新增字段以匹配前端
    enable_memory: bool = False
    enable_debug: bool = False
    priority: int = 0
    model_category: Optional[str] = None


class DataSourceConfigRequest(BaseModel):
    """数据源配置请求"""
    name: str
    type: DataSourceType
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    endpoint: Optional[str] = None
    timeout: int = 30
    rate_limit: int = 100
    enabled: bool = True
    priority: int = 0
    config_params: Dict[str, Any] = Field(default_factory=dict)
    description: Optional[str] = None
    # 新增字段
    market_categories: Optional[List[str]] = Field(default_factory=list)
    display_name: Optional[str] = None
    provider: Optional[str] = None


class MarketCategoryRequest(BaseModel):
    """市场分类请求"""
    id: str
    name: str
    display_name: str
    description: Optional[str] = None
    enabled: bool = True
    sort_order: int = 1


class DataSourceGroupingRequest(BaseModel):
    """数据源分组请求"""
    data_source_name: str
    market_category_id: str
    priority: int = 0
    enabled: bool = True


class DataSourceOrderRequest(BaseModel):
    """数据源排序请求"""
    data_sources: List[Dict[str, Any]] = Field(..., description="排序后的数据源列表")


class DatabaseConfigRequest(BaseModel):
    """数据库配置请求"""
    name: str
    type: DatabaseType
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    database: Optional[str] = None
    connection_params: Dict[str, Any] = Field(default_factory=dict)
    pool_size: int = 10
    max_overflow: int = 20
    enabled: bool = True
    description: Optional[str] = None


class SystemConfigResponse(BaseModel):
    """系统配置响应"""
    config_name: str
    config_type: str
    llm_configs: List[LLMConfig]
    default_llm: Optional[str]
    data_source_configs: List[DataSourceConfig]
    default_data_source: Optional[str]
    database_configs: List[DatabaseConfig]
    system_settings: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    version: int
    is_active: bool


class ConfigTestRequest(BaseModel):
    """配置测试请求"""
    config_type: str = Field(..., description="配置类型: llm/datasource/database")
    config_data: Dict[str, Any] = Field(..., description="配置数据")


class ConfigTestResponse(BaseModel):
    """配置测试响应"""
    success: bool
    message: str
    details: Optional[Dict[str, Any]] = None
    response_time: Optional[float] = None
