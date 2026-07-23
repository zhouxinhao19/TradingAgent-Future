# 数据库字段标准化分析

> 分析项目中所有MongoDB集合的品种代码字段命名不一致问题，并提供统一方案

## 📋 问题概述

当前项目中，不同的MongoDB集合和模型对品种代码字段使用了不同的命名，导致：
- 代码可读性差
- 容易产生混淆
- 增加维护成本
- 查询时需要记住不同集合的字段名

## 🔍 当前字段命名情况

### 1. 品种代码字段命名汇总

| 集合/模型 | 当前字段名 | 含义 | 示例值 |
|----------|-----------|------|--------|
| **stock_basic_info** | `code` | 6位品种代码 | "000001" |
| **stock_daily_quotes** | `symbol` | 6位品种代码 | "000001" |
| **analysis_tasks** | `stock_code` | 6位品种代码 | "000001" |
| **analysis_batches** | - | (通过tasks关联) | - |
| **screening** | `code` | 6位品种代码 | "000001" |
| **StockBasicInfo (tradingagents)** | `symbol` | 6位品种代码 | "000001" |
| **StockDailyQuote (tradingagents)** | `symbol` | 6位品种代码 | "000001" |
| **StockBasicInfoExtended (app)** | `code` | 6位品种代码 | "000001" |

### 2. 完整代码字段命名

| 集合/模型 | 当前字段名 | 含义 | 示例值 |
|----------|-----------|------|--------|
| **stock_basic_info** | - | (无) | - |
| **stock_daily_quotes** | - | (无) | - |
| **StockBasicInfo (tradingagents)** | `exchange_symbol` | 交易所完整代码 | "000001.SZ" |
| **StockBasicInfoExtended (app)** | `full_symbol` | 完整标准化代码 | "000001.SZ" |

## 📊 详细分析

### 集合1: stock_basic_info

**当前结构**:
```javascript
{
  "_id": ObjectId("..."),
  "code": "000001",           // ❌ 不一致
  "name": "平安银行",
  "area": "深圳",
  "industry": "银行",
  "market": "深圳证券交易所",
  "sse": "主板",
  "total_mv": 2500.0,
  "circ_mv": 2000.0,
  "pe": 5.2,
  "pb": 0.8,
  "updated_at": "2024-01-15T10:00:00Z"
}
```

**问题**:
- 使用 `code` 而非 `symbol`
- 缺少完整代码字段（如 "000001.SZ"）
- 与其他集合不一致

### 集合2: stock_daily_quotes

**当前结构**:
```javascript
{
  "_id": ObjectId("..."),
  "symbol": "000001",         // ✅ 使用symbol
  "trade_date": "2024-01-15",
  "open": 10.5,
  "high": 10.8,
  "low": 10.3,
  "close": 10.6,
  "volume": 1000000,
  "amount": 10600000,
  "data_source": "tushare",
  "period": "daily"
}
```

**问题**:
- 缺少完整代码字段
- 缺少市场标识

### 集合3: analysis_tasks

**当前结构**:
```javascript
{
  "_id": ObjectId("..."),
  "task_id": "task_abc123",
  "user_id": ObjectId("..."),
  "stock_code": "000001",     // ❌ 使用stock_code
  "stock_name": "平安银行",
  "status": "completed",
  "progress": 100,
  "created_at": ISODate("2024-01-15T10:00:00Z"),
  "result": { ... }
}
```

**问题**:
- 使用 `stock_code` 而非 `symbol`
- 与其他集合命名不一致

### 集合4: screening (筛选结果)

**当前结构**:
```javascript
// 筛选条件中使用
{
  "field": "code",            // ❌ 使用code
  "operator": "==",
  "value": "000001"
}
```

**问题**:
- 筛选字段使用 `code`
- 与数据模型不一致

## 🎯 标准化方案

### 方案1: 统一使用 `symbol` (推荐)

**优点**:
- 符合金融行业惯例
- 与tradingagents模型一致
- 语义清晰

**缺点**:
- 需要修改现有集合
- 需要数据迁移

**标准字段定义**:
```python
# 基础字段
symbol: str          # 6位品种代码，如 "000001"
full_symbol: str     # 完整代码，如 "000001.SZ"
market: str          # 市场代码，如 "SZ", "SH"
exchange: str        # 交易所，如 "SZSE", "SSE"
```

### 方案2: 保持 `code`，添加 `symbol` 别名

**优点**:
- 向后兼容
- 渐进式迁移

**缺点**:
- 数据冗余
- 维护成本高

## ✅ 推荐的统一标准

### 1. 字段命名标准

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| `symbol` | string | ✅ | 6位品种代码 | "000001" |
| `full_symbol` | string | ✅ | 完整标准化代码 | "000001.SZ" |
| `name` | string | ✅ | 期货品种名称 | "平安银行" |
| `market` | string | ✅ | 市场代码 | "SZ" |
| `exchange` | string | ✅ | 交易所代码 | "SZSE" |
| `exchange_name` | string | ❌ | 交易所名称 | "深圳证券交易所" |

### 2. 索引标准

```javascript
// stock_basic_info 索引
db.stock_basic_info.createIndex({ "symbol": 1 }, { unique: true })
db.stock_basic_info.createIndex({ "full_symbol": 1 }, { unique: true })
db.stock_basic_info.createIndex({ "market": 1, "symbol": 1 })

// stock_daily_quotes 索引
db.stock_daily_quotes.createIndex({ "symbol": 1, "trade_date": -1 })
db.stock_daily_quotes.createIndex({ "full_symbol": 1, "trade_date": -1 })
db.stock_daily_quotes.createIndex({ "market": 1, "trade_date": -1 })

// analysis_tasks 索引
db.analysis_tasks.createIndex({ "symbol": 1, "created_at": -1 })
db.analysis_tasks.createIndex({ "user_id": 1, "symbol": 1 })
db.analysis_tasks.createIndex({ "task_id": 1 }, { unique: true })
```

### 3. 模型定义标准

```python
# app/models/base.py
from pydantic import BaseModel, Field
from typing import Optional

class StockIdentifier(BaseModel):
    """期货品种标识符基类"""
    symbol: str = Field(..., description="6位品种代码", pattern=r"^\d{6}$")
    full_symbol: str = Field(..., description="完整标准化代码", pattern=r"^\d{6}\.(SZ|SH|BJ)$")
    market: str = Field(..., description="市场代码", pattern=r"^(SZ|SH|BJ)$")
    exchange: str = Field(..., description="交易所代码")
    name: str = Field(..., description="期货品种名称")

# app/models/stock_models.py
class StockBasicInfo(StockIdentifier):
    """期货品种基础信息"""
    area: Optional[str] = None
    industry: Optional[str] = None
    list_date: Optional[str] = None
    # ... 其他字段

# app/models/analysis.py
class AnalysisTask(BaseModel):
    """分析任务"""
    task_id: str
    symbol: str = Field(..., description="6位品种代码")  # ✅ 统一使用symbol
    full_symbol: Optional[str] = None
    stock_name: Optional[str] = None
    # ... 其他字段
```

## 🔄 迁移方案

### 阶段1: 添加新字段（不破坏现有功能）

```javascript
// 为 stock_basic_info 添加 symbol 和 full_symbol
db.stock_basic_info.updateMany(
  {},
  [
    {
      $set: {
        symbol: "$code",
        full_symbol: {
          $concat: [
            "$code",
            ".",
            {
              $cond: {
                if: { $regexMatch: { input: "$market", regex: /深圳/ } },
                then: "SZ",
                else: {
                  $cond: {
                    if: { $regexMatch: { input: "$market", regex: /上海/ } },
                    then: "SH",
                    else: "BJ"
                  }
                }
              }
            }
          ]
        }
      }
    }
  ]
)

// 为 analysis_tasks 添加 symbol
db.analysis_tasks.updateMany(
  {},
  [
    {
      $set: {
        symbol: "$stock_code"
      }
    }
  ]
)
```

### 阶段2: 更新代码使用新字段

```python
# 修改所有查询代码
# 旧代码
stock = db.stock_basic_info.find_one({"code": "000001"})

# 新代码
stock = db.stock_basic_info.find_one({"symbol": "000001"})
```

### 阶段3: 创建索引

```javascript
// 创建新索引
db.stock_basic_info.createIndex({ "symbol": 1 }, { unique: true })
db.stock_basic_info.createIndex({ "full_symbol": 1 }, { unique: true })
db.analysis_tasks.createIndex({ "symbol": 1, "created_at": -1 })
```

### 阶段4: 删除旧字段（可选）

```javascript
// 确认所有代码已更新后，删除旧字段
db.stock_basic_info.updateMany({}, { $unset: { code: "" } })
db.analysis_tasks.updateMany({}, { $unset: { stock_code: "" } })

// 删除旧索引
db.stock_basic_info.dropIndex("code_1")
```

## 📝 需要修改的文件清单

### 1. 模型文件

- [ ] `app/models/stock_models.py` - StockBasicInfoExtended
- [ ] `app/models/analysis.py` - AnalysisTask, StockInfo
- [ ] `app/models/screening.py` - BASIC_FIELDS_INFO
- [ ] `tradingagents/models/stock_data_models.py` - 已使用symbol ✅

### 2. 路由文件

- [ ] `app/routers/stock_data.py` - 搜索和查询接口
- [ ] `app/routers/analysis.py` - 分析任务接口
- [ ] `app/routers/screening.py` - 筛选接口

### 3. 服务文件

- [ ] `app/services/analysis_service.py` - 分析服务
- [ ] `app/services/stock_service.py` - 期货数据服务
- [ ] `app/services/screening_service.py` - 筛选服务

### 4. 数据库脚本

- [ ] `scripts/docker/mongo-init.js` - 初始化脚本
- [ ] `scripts/setup/create_historical_data_collection.py` - 历史数据集合
- [ ] 所有 `scripts/validation/` 下的验证脚本

### 5. 前端代码

- [ ] `frontend/src/api/stock.ts` - API接口
- [ ] `frontend/src/types/stock.ts` - 类型定义
- [ ] `frontend/src/views/` - 所有使用品种代码的视图

## 🎯 实施建议

### 优先级

**P0 (立即执行)**:
1. 统一模型定义
2. 添加新字段到现有集合
3. 创建新索引

**P1 (1周内)**:
4. 更新所有查询代码
5. 更新API接口
6. 更新前端代码

**P2 (2周内)**:
7. 更新文档
8. 删除旧字段和索引

### 测试计划

1. **单元测试**: 测试所有模型的字段验证
2. **集成测试**: 测试API接口的查询功能
3. **数据验证**: 验证数据迁移的完整性
4. **性能测试**: 验证新索引的查询性能

## 📊 影响评估

### 数据量

- stock_basic_info: ~5000条记录
- stock_daily_quotes: ~1,000,000条记录
- analysis_tasks: ~10,000条记录

### 迁移时间估算

- 数据迁移: 5-10分钟
- 代码更新: 2-3天
- 测试验证: 1-2天
- 总计: 3-5天

### 风险评估

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| 数据丢失 | 高 | 低 | 备份数据库 |
| 查询失败 | 高 | 中 | 保留旧字段过渡期 |
| 性能下降 | 中 | 低 | 优化索引 |
| 前端报错 | 中 | 中 | 渐进式更新 |

## ✅ 检查清单

- [ ] 备份生产数据库
- [ ] 在测试环境执行迁移
- [ ] 验证数据完整性
- [ ] 更新所有模型定义
- [ ] 更新所有查询代码
- [ ] 更新API文档
- [ ] 更新前端代码
- [ ] 执行完整测试
- [ ] 更新用户文档
- [ ] 在生产环境执行迁移
- [ ] 监控系统运行状态
- [ ] 删除旧字段（可选）

## 📞 联系方式

如有问题，请联系：
- 技术负责人: [技术负责人邮箱]
- 数据库管理员: [DBA邮箱]

---

**文档版本**: v1.0
**创建日期**: 2024-01-15
**最后更新**: 2024-01-15

