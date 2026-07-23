# 数据源管理架构重构方案

## 📋 当前问题

### 1. 重复的配置读取逻辑

**问题描述：**
- `app/` 目录：有统一配置管理 (`unified_config.py`, `config_service.py`)
- `tradingagents/` 目录：数据源管理器自己读取数据库配置
- 两套系统各自读取数据库，造成代码重复和维护困难

**当前代码位置：**
```
app/core/unified_config.py                    # ✅ 统一配置管理
app/services/config_service.py                # ✅ 配置服务

tradingagents/dataflows/data_source_manager.py
├── DataSourceManager                         # ❌ 自己读数据库
│   ├── _get_enabled_sources_from_db()       # 重复逻辑
│   └── _check_available_sources()           # 检查 API Key
└── USDataSourceManager                       # ❌ 自己读数据库
    ├── _get_enabled_sources_from_db()       # 重复逻辑
    ├── _get_datasource_configs_from_db()    # 重复逻辑
    └── _check_available_sources()           # 检查 API Key
```

### 2. API Key 检查逻辑分散

**A股/港股数据源管理器 (`DataSourceManager`)：**
- 第 466 行：检查 Tushare，只从环境变量读取 `TUSHARE_TOKEN`
- 没有从数据库配置读取 API Key

**美股数据源管理器 (`USDataSourceManager`)：**
- 第 2322 行：检查 Alpha Vantage，优先从数据库读取（已修复）
- 第 2339 行：检查 Finnhub，优先从数据库读取（已修复）

**不一致性：**
- 美股数据源已经支持从数据库读取 API Key
- 数据源还是只从环境变量读取
- 逻辑不统一，容易出错

## 🎯 重构目标

### 1. 单一职责原则

**配置管理层 (`app/`)：**
- 负责读取数据库配置
- 负责读取环境变量
- 负责配置的优先级处理
- 提供统一的配置接口

**业务逻辑层 (`tradingagents/`)：**
- 接收配置参数
- 执行业务逻辑（数据获取、分析等）
- 不直接访问数据库配置

### 2. 统一的配置获取方式

所有数据源的 API Key 获取优先级：
1. 数据库配置（Web 界面配置）
2. 环境变量（.env 文件）
3. 配置文件（兼容旧版本）

## 🔧 重构方案

### 方案 A：配置注入（推荐）

**优点：**
- 解耦配置和业务逻辑
- 易于测试（可以注入 mock 配置）
- 符合依赖注入原则

**实现：**

```python
# app/services/datasource_config_provider.py
class DataSourceConfigProvider:
    """数据源配置提供器（统一配置管理）"""
    
    async def get_datasource_config(self, datasource_name: str) -> Optional[Dict]:
        """
        获取数据源配置
        
        优先级：
        1. 数据库配置
        2. 环境变量
        3. 默认配置
        """
        # 从数据库读取
        db_config = await self._get_from_database(datasource_name)
        if db_config and db_config.get('api_key'):
            return db_config
        
        # 从环境变量读取
        env_config = self._get_from_env(datasource_name)
        if env_config:
            return env_config
        
        return None
    
    async def get_enabled_datasources(self, market_category: str) -> List[str]:
        """获取启用的数据源列表"""
        # 从数据库读取 datasource_groupings
        pass

# tradingagents/dataflows/data_source_manager.py
class DataSourceManager:
    """数据源管理器（业务逻辑）"""
    
    def __init__(self, config_provider: DataSourceConfigProvider):
        """
        初始化数据源管理器
        
        Args:
            config_provider: 配置提供器（由 app 层注入）
        """
        self.config_provider = config_provider
        self.available_sources = []
    
    async def initialize(self):
        """异步初始化（检查可用数据源）"""
        # 从配置提供器获取启用的数据源
        enabled_sources = await self.config_provider.get_enabled_datasources('a_shares')
        
        # 检查每个数据源是否可用
        for source_name in enabled_sources:
            config = await self.config_provider.get_datasource_config(source_name)
            if self._is_source_available(source_name, config):
                self.available_sources.append(source_name)
```

### 方案 B：配置缓存（简单）

**优点：**
- 改动较小
- 保持现有接口

**缺点：**
- 仍然有配置读取逻辑在 `tradingagents/`
- 不够解耦

**实现：**

```python
# tradingagents/dataflows/data_source_manager.py
class DataSourceManager:
    def __init__(self):
        # 从 app 层获取配置（而不是自己读数据库）
        from app.services.config_service import config_service
        self.config_service = config_service
        
        # 初始化
        self.available_sources = self._check_available_sources()
    
    def _get_datasource_config(self, datasource_name: str) -> Optional[Dict]:
        """从 app 层获取配置"""
        # 调用 app 层的配置服务
        config = asyncio.run(self.config_service.get_datasource_config(datasource_name))
        return config
```

## 📝 实施步骤

### 阶段 1：创建统一配置提供器

1. 在 `app/services/` 创建 `datasource_config_provider.py`
2. 实现统一的配置获取逻辑：
   - `get_datasource_config(name)` - 获取单个数据源配置
   - `get_enabled_datasources(market_category)` - 获取启用的数据源列表
   - `get_datasource_priority(market_category)` - 获取数据源优先级

### 阶段 2：修改 数据源管理器

1. 修改 `DataSourceManager._check_available_sources()`
2. 添加从数据库读取 Tushare API Key 的逻辑
3. 统一 API Key 获取优先级（数据库 > 环境变量）

### 阶段 3：重构数据源管理器

1. 修改 `DataSourceManager` 和 `USDataSourceManager` 的初始化
2. 接收配置提供器作为参数
3. 移除直接读取数据库的代码

### 阶段 4：更新调用方

1. 修改所有创建数据源管理器的地方
2. 注入配置提供器
3. 测试功能是否正常

## 🚀 快速修复（临时方案）

在完整重构之前，先修复 数据源的 API Key 读取问题：

**修改位置：** `tradingagents/dataflows/data_source_manager.py` 第 462-475 行

**修改内容：**
```python
# 检查Tushare
if 'tushare' in enabled_sources_in_db:
    try:
        import tushare as ts
        # 🔥 优先从数据库配置读取 API Key，其次从环境变量读取
        datasource_configs = self._get_datasource_configs_from_db()
        token = datasource_configs.get('tushare', {}).get('api_key') or os.getenv('TUSHARE_TOKEN')
        if token:
            available.append(ChinaDataSource.TUSHARE)
            source = "数据库配置" if datasource_configs.get('tushare', {}).get('api_key') else "环境变量"
            logger.info(f"✅ Tushare数据源可用且已启用 (API Key来源: {source})")
        else:
            logger.warning("⚠️ Tushare数据源不可用: API Key未配置（数据库和环境变量均未找到）")
    except ImportError:
        logger.warning("⚠️ Tushare数据源不可用: 库未安装")
else:
    logger.info("ℹ️ Tushare数据源已在数据库中禁用")
```

## 📊 影响范围

### 需要修改的文件

1. **新增文件：**
   - `app/services/datasource_config_provider.py` - 配置提供器

2. **修改文件：**
   - `tradingagents/dataflows/data_source_manager.py` - 数据源管理器
   - `tradingagents/dataflows/providers/us/optimized.py` - 美股数据提供器
   - `tradingagents/dataflows/providers/china/tushare.py` - Tushare 提供器

3. **调用方（需要更新）：**
   - `app/services/simple_analysis_service.py` - 简单分析服务
   - `app/worker/akshare_sync_service.py` - AKShare 同步服务
   - 其他使用数据源管理器的地方

### 测试范围

1. **单元测试：**
   - 配置提供器的配置获取逻辑
   - 数据源管理器的初始化逻辑

2. **集成测试：**
   - Web 界面配置数据源 → 系统识别并使用
   - 环境变量配置 → 系统降级使用
   - 数据源优先级和降级逻辑

3. **端到端测试：**
   - 美股分析流程
   - 期货分析流程
   - 港股分析流程

## 🎯 预期效果

### 重构前

```
用户在 Web 界面配置 Tushare API Key
    ↓
保存到数据库 ✅
    ↓
系统启动时读取配置
    ↓
数据源管理器：只检查环境变量 ❌
    ↓
显示"Tushare数据源不可用: 未设置TUSHARE_TOKEN" ❌
```

### 重构后

```
用户在 Web 界面配置 Tushare API Key
    ↓
保存到数据库 ✅
    ↓
系统启动时读取配置
    ↓
配置提供器：从数据库读取 API Key ✅
    ↓
数据源管理器：使用配置提供器的配置 ✅
    ↓
显示"✅ Tushare数据源可用且已启用 (API Key来源: 数据库配置)" ✅
```

## 📅 时间估算

- **快速修复（临时方案）：** 1-2 小时
- **完整重构（方案 A）：** 1-2 天
- **测试和验证：** 1 天

## 🔗 相关文档

- [统一配置管理文档](./UNIFIED_CONFIG.md)
- [数据源配置文档](../configuration/DATASOURCE_CONFIG.md)
- [API Key 管理文档](../configuration/API_KEY_MANAGEMENT.md)

