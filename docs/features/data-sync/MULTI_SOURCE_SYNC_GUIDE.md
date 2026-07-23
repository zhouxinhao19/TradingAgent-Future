# 多数据源同步使用指南

**更新日期**: 2025-09-30
**版本**: v1.3

## 📊 概述

多数据源同步功能为TradingAgents项目提供了强大的数据源分级和fallback机制，确保在主数据源不可用时能够自动切换到备用数据源，提高系统的可靠性和数据获取的成功率。

## 🎯 核心特性

### 1. 数据源分级
- **Tushare** (优先级1): 专业金融数据API，提供最全面的财务指标，支持日线/周线/月线数据
- **AKShare** (优先级2): 开源金融数据库，提供基础期货品种信息，支持日线/周线/月线数据
- **BaoStock** (优先级3): 免费证券数据平台，提供历史数据，支持日线/周线/月线数据

### 2. 自动Fallback机制
- 主数据源失败时自动切换到备用数据源
- 智能重试和错误处理
- 详细的数据源使用统计

### 3. 灵活配置
- 支持指定优先使用的数据源
- 可配置数据源优先级
- 实时数据源状态检查
- 支持多周期数据同步（日线、周线、月线）

## 🛠️ 配置方法

### 环境变量配置

```bash
# Tushare配置（推荐）
TUSHARE_ENABLED=true
TUSHARE_TOKEN=your_tushare_token_here

# AKShare配置
AKSHARE_ENABLED=true

# BaoStock配置
BAOSTOCK_ENABLED=true

# 默认数据源
DEFAULT_CHINA_DATA_SOURCE=tushare
```

### 数据源优先级

系统默认按以下优先级使用数据源：

1. **Tushare** - 最高优先级，提供最完整的数据
2. **AKShare** - 中等优先级，提供基础数据
3. **BaoStock** - 最低优先级，作为最后备用

## 🚀 使用方法

### 1. API接口

#### 获取数据源状态
```bash
GET /api/sync/multi-source/sources/status
```

响应示例：
```json
[
  {
    "name": "tushare",
    "priority": 1,
    "available": true,
    "description": "专业金融数据API，提供高质量的期货数据和财务指标"
  },
  {
    "name": "akshare",
    "priority": 2,
    "available": true,
    "description": "开源金融数据库，提供基础的期货品种信息"
  }
]
```

#### 运行多数据源同步
```bash
POST /api/sync/multi-source/stock_basics/run
```

可选参数：
- `force`: 是否强制运行（默认false）
- `preferred_sources`: 优先使用的数据源，用逗号分隔

#### 测试数据源连接
```bash
POST /api/sync/multi-source/test-sources
```

#### 获取同步建议
```bash
GET /api/sync/multi-source/recommendations
```

### 2. Python代码使用

```python
from app.services.multi_source_basics_sync_service import get_multi_source_sync_service
from app.services.data_source_adapters import DataSourceManager

# 获取数据源管理器
manager = DataSourceManager()
available_adapters = manager.get_available_adapters()

# 运行多数据源同步
service = get_multi_source_sync_service()
result = await service.run_full_sync(
    force=False,
    preferred_sources=["tushare", "akshare"]
)
```

### 3. 命令行测试

```bash
# 运行测试脚本
python scripts/test_multi_source_sync.py
```

## 📈 同步流程

### 1. 数据源检查
- 检测所有可用的数据源
- 按优先级排序
- 记录数据源状态

### 2. 期货品种列表获取
- 优先从Tushare获取完整期货品种列表
- 失败时自动切换到AKShare或BaoStock
- 标准化数据格式

### 3. 财务数据获取
- 查找最新交易日期
- 获取每日基础财务数据（PE、PB、市值等）
- 目前主要依赖Tushare的daily_basic接口

### 4. 数据处理和存储
- 统一数据格式
- 6位品种代码标准化
- 批量更新MongoDB

## 🔧 故障排除

### 常见问题

#### 1. 所有数据源都不可用
**症状**: API返回"No available data sources found"

**解决方案**:
- 检查环境变量配置
- 确保至少安装了一个数据源的依赖包
- 验证Tushare token是否有效

#### 2. 只有部分期货品种有扩展字段
**症状**: PE、PB等财务指标缺失

**解决方案**:
- 确保Tushare可用（其他数据源暂不支持财务指标）
- 检查交易日期是否正确
- 验证daily_basic数据是否可获取

#### 3. 同步速度慢
**症状**: 同步耗时过长

**解决方案**:
- 优先配置Tushare（数据最全面）
- 检查网络连接
- 考虑增加缓存机制

### 调试方法

#### 1. 检查数据源状态
```bash
curl http://localhost:8000/api/sync/multi-source/sources/status
```

#### 2. 测试数据源连接
```bash
curl -X POST http://localhost:8000/api/sync/multi-source/test-sources
```

#### 3. 查看同步日志
检查应用日志中的数据源切换信息：
```
INFO: Trying to fetch stock list from TushareAdapter
INFO: Successfully fetched 5427 stocks from TushareAdapter
```

## 📊 性能优化

### 1. 数据源选择策略
- **生产环境**: 优先使用Tushare，配置AKShare作为备用
- **开发环境**: 可以使用AKShare或BaoStock降低成本
- **测试环境**: 使用任何可用的数据源

### 2. 缓存策略
- 期货品种列表缓存24小时
- 财务数据缓存1小时
- 失败的数据源暂时跳过

### 3. 并发控制
- 同一时间只允许一个同步任务运行
- 使用异步处理避免阻塞
- 批量数据库操作提高效率

## 🔮 未来规划

### 1. 更多数据源支持
- 东方财富API
- 同花顺API
- Wind API（企业版）

### 2. 智能数据源选择
- 基于数据质量自动选择
- 成本优化算法
- 实时性能监控

### 3. 数据验证和清洗
- 跨数据源数据对比
- 异常数据检测
- 自动数据修复

## 📝 最佳实践

### 1. 配置建议
```bash
# 推荐配置
TUSHARE_ENABLED=true
TUSHARE_TOKEN=your_token
AKSHARE_ENABLED=true
BAOSTOCK_ENABLED=true
DEFAULT_CHINA_DATA_SOURCE=tushare
```

### 2. 监控建议
- 定期检查数据源状态
- 监控同步成功率
- 设置数据质量告警

### 3. 维护建议
- 定期更新数据源依赖
- 备份重要配置
- 测试故障切换机制

## 🤝 贡献指南

如需添加新的数据源适配器：

1. 继承`DataSourceAdapter`基类
2. 实现必要的抽象方法
3. 在`DataSourceManager`中注册
4. 添加相应的测试用例
5. 更新文档

---

## 🎯 选择性数据同步

### 功能说明

选择性数据同步功能允许您只更新特定类型的数据，适用于增量更新和数据修复场景。

### 支持的数据类型

- `basic_info` - 期货品种基础信息
- `historical` - 历史行情（日线）
- `weekly` - 周线数据
- `monthly` - 月线数据
- `financial` - 财务数据
- `quotes` - 最新行情

### 使用示例

```bash
# 仅更新历史数据
python cli/tushare_init.py --full --sync-items historical --historical-days 30

# 仅更新财务数据
python cli/tushare_init.py --full --sync-items financial

# 同步多个数据类型
python cli/tushare_init.py --full --sync-items historical,financial,quotes
```

详细说明请参考：[Tushare数据初始化指南](guides/tushare_unified/data_initialization_guide.md#选择性数据同步)

## 🌐 全历史数据同步

### 功能说明

全历史数据同步功能允许获取期货品种从1990年至今的完整历史数据，适用于长期回测和研究。

### 阈值机制

当 `--historical-days >= 3650`（10年）时，系统自动切换到全历史模式：

| historical_days | 同步范围 | 说明 |
|----------------|---------|------|
| < 3650 | 指定天数 | 从当前日期往前推算指定天数 |
| >= 3650 | 全历史 | 从1990-01-01至今的所有数据 |

### 使用示例

```bash
# Tushare全历史初始化
python cli/tushare_init.py --full --historical-days 10000

# AKShare全历史初始化
python cli/akshare_init.py --full --historical-days 10000

# BaoStock全历史初始化
python cli/baostock_init.py --full --historical-days 10000

# 全历史多周期初始化（推荐生产环境）
python cli/tushare_init.py --full --multi-period --historical-days 10000
```

### 数据量对比

| 同步模式 | 日线记录数 | 存储空间 | 同步耗时 |
|---------|-----------|---------|---------|
| 默认1年 | ~1,250,000条 | ~500MB | 30-60分钟 |
| 全历史 | ~8,000,000条 | 2-5GB | 2-4小时 |

### 适用场景

- ✅ **生产环境首次部署** - 获取完整历史数据
- ✅ **长期回测研究** - 需要多年历史数据
- ✅ **数据补全** - 补充缺失的历史数据

### 注意事项

1. **耗时较长**: 全历史同步需要2-4小时，建议非交易时间进行
2. **API限流**: 注意各数据源的调用频率限制
3. **存储空间**: 确保有2-5GB可用磁盘空间
4. **推荐策略**: 首次全历史初始化，日常增量更新

详细说明请参考：[Tushare数据初始化指南](guides/tushare_unified/data_initialization_guide.md#全历史数据同步)

## 📊 多周期数据支持

### 支持的数据周期

所有三个数据源（Tushare、AKShare、BaoStock）都支持多周期历史数据：

1. **日线数据** (daily) - 每个交易日的OHLCV数据
2. **周线数据** (weekly) - 每周的OHLCV数据
3. **月线数据** (monthly) - 每月的OHLCV数据

### 数据存储

所有周期的数据统一存储在 `stock_daily_quotes` 集合中，通过 `period` 字段区分：
- `period: "daily"` - 日线数据
- `period: "weekly"` - 周线数据
- `period: "monthly"` - 月线数据

### 初始化多周期数据

```bash
# Tushare多周期初始化（默认1年）
python cli/tushare_init.py --full --multi-period

# 指定历史数据范围（6个月）
python cli/tushare_init.py --full --multi-period --historical-days 180

# 全历史多周期初始化（从1990年至今，推荐生产环境）
python cli/tushare_init.py --full --multi-period --historical-days 10000
```

### 查询多周期数据

```python
from tradingagents.config.database_manager import get_mongodb_client

client = get_mongodb_client()
db = client.get_database('tradingagents')
collection = db.stock_daily_quotes

# 查询日线数据
daily_data = list(collection.find({
    'symbol': '000001',
    'period': 'daily',
    'data_source': 'tushare'
}))

# 查询周线数据
weekly_data = list(collection.find({
    'symbol': '000001',
    'period': 'weekly',
    'data_source': 'tushare'
}))

# 查询月线数据
monthly_data = list(collection.find({
    'symbol': '000001',
    'period': 'monthly',
    'data_source': 'tushare'
}))
```

---

**注意**: 多数据源同步功能需要至少配置一个可用的数据源。推荐使用Tushare作为主数据源以获得最完整的财务数据。

**更新日期**: 2025-09-30
**版本**: v1.2 - 新增选择性数据同步和多周期数据支持
