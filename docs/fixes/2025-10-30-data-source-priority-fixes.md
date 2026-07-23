# 2025-10-30 数据源优先级修复总结

## 问题背景

用户反馈 `/api/stocks/000001/fundamentals` 接口返回的 `roe`、`debt_ratio`、`ps` 都是 `null`。

### 根本原因分析

1. **数据源混用问题**
   - `stock_basic_info` 中的数据来自 Tushare（source: tushare）
   - `stock_financial_data` 中有两条记录：
     * 最新的（20251231）来自 AKShare，但所有字段都是 None（解析失败）
     * 之前的（20250930）来自 Tushare，有 ROE=7.5711, debt_to_assets=91.0187

2. **接口逻辑问题**
   - 接口优先查询 `stock_financial_data` 中最新的记录（按 report_period 降序）
   - 但最新的记录（AKShare 20251231）所有字段都是 None
   - 接口没有按数据源优先级查询，直接返回 None

3. **系统级问题**
   - 多个地方的数据查询没有按数据源优先级进行
   - 导致可能混用不同数据源的数据

## 修复内容

### 1. 修复 `/api/stocks/{code}/fundamentals` 接口

**文件**: `app/routers/stocks.py`

**修改**: 第160-192行

**改进**:
- 按数据源优先级查询财务数据，而不是按时间戳
- 优先级：tushare > akshare > baostock
- 确保不混用不同数据源的数据

```python
# 🔥 按数据源优先级查询，而不是按时间戳，避免混用不同数据源的数据
financial_data = None
try:
    # 获取数据源优先级配置
    from app.core.unified_config import UnifiedConfigManager
    config = UnifiedConfigManager()
    data_source_configs = await config.get_data_source_configs_async()
    
    # 提取启用的数据源，按优先级排序
    enabled_sources = [
        ds.type.lower() for ds in data_source_configs
        if ds.enabled and ds.type.lower() in ['tushare', 'akshare', 'baostock']
    ]
    
    if not enabled_sources:
        enabled_sources = ['tushare', 'akshare', 'baostock']
    
    # 按数据源优先级查询财务数据
    for data_source in enabled_sources:
        financial_data = await db["stock_financial_data"].find_one(
            {"$or": [{"symbol": code6}, {"code": code6}], "data_source": data_source},
            {"_id": 0},
            sort=[("report_period", -1)]
        )
        if financial_data:
            logger.info(f"✅ 使用数据源 {data_source} 的财务数据")
            break
```

### 2. 修复 `app/routers/reports.py` 中的 `get_stock_name()` 函数

**文件**: `app/routers/reports.py`

**修改**: 第23-84行

**改进**:
- 添加按数据源优先级查询的逻辑
- 优先级：tushare > akshare > baostock
- 如果所有数据源都没有，回退到不带 source 条件的查询（兼容旧数据）

### 3. 修复 `app/services/database_screening_service.py` 中的聚合查询

**文件**: `app/services/database_screening_service.py`

**修改**: 第241-274行

**改进**:
- 在聚合查询中添加数据源过滤
- 只查询优先级最高的数据源的财务数据
- 避免混用不同数据源的数据

```python
# 🔥 获取数据源优先级配置
from app.core.unified_config import UnifiedConfigManager
config = UnifiedConfigManager()
data_source_configs = await config.get_data_source_configs_async()

# 提取启用的数据源，按优先级排序
enabled_sources = [
    ds.type.lower() for ds in data_source_configs
    if ds.enabled and ds.type.lower() in ['tushare', 'akshare', 'baostock']
]

if not enabled_sources:
    enabled_sources = ['tushare', 'akshare', 'baostock']

# 优先使用优先级最高的数据源
preferred_source = enabled_sources[0] if enabled_sources else 'tushare'

# 批量查询最新的财务数据（只查询优先级最高的数据源）
pipeline = [
    {"$match": {"code": {"$in": codes}, "data_source": preferred_source}},
    ...
]
```

## 已验证的正确实现

以下地方已经按数据源优先级查询，无需修改：

1. `app/routers/stocks.py` - `get_fundamentals()` ✅
2. `app/routers/stock_data.py` - 已按优先级查询 ✅
3. `app/routers/screening.py` - 已按优先级查询 ✅
4. `app/services/stock_data_service.py` - 已按优先级查询 ✅
5. `app/services/favorites_service.py` - 已按优先级查询 ✅

## 测试建议

1. 调用 `/api/stocks/000001/fundamentals` 接口，验证返回的 `roe`、`debt_ratio`、`ps` 不再是 `null`
2. 验证接口返回的数据来自 Tushare（最高优先级）
3. 测试其他品种代码，确保数据一致性

## 相关配置

数据源优先级配置在 `app/core/unified_config.py` 中：

```python
# 默认顺序：Tushare > AKShare > BaoStock
enabled_sources = ['tushare', 'akshare', 'baostock']
```

可以通过数据库中的 `system_configs` 集合修改优先级。

