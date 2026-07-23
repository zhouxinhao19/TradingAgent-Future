# 修复 full_symbol 唯一索引冲突问题

## 📋 问题描述

在运行期货品种基础信息同步任务时，出现 MongoDB 唯一索引冲突错误：

```
ERROR | Bulk write error on batch 2: batch op errors occurred, full error: 
{'writeErrors': [{'index': 823, 'code': 11000, 'keyPattern': {'full_symbol': 1}, 
'keyValue': {'full_symbol': None}, 
'errmsg': 'E11000 duplicate key error collection: tradingagents.stock_basic_info 
index: full_symbol_1 dup key: { full_symbol: null }', ...}]}
```

### 受影响的期货品种

- **301563** (N云汉) - 创业板新股，上市日期：20250930
- **920080** (奥美森) - 北交所，上市日期：20251010

这些都是新上市的期货品种，数据同步时 `full_symbol` 字段没有被正确设置。

---

## 🔍 根本原因

### 1. 索引配置问题

MongoDB 的 `stock_basic_info` 集合有一个 `full_symbol` 字段的唯一索引（来自扩展脚本 `scripts/migration/extend_stock_collections.py`）：

```python
await basic_collection.create_index("full_symbol", unique=True)
```

### 2. 数据同步逻辑缺陷

`app/services/basics_sync_service.py` 在构建文档时**没有设置 `full_symbol` 字段**：

```python
doc = {
    "code": code,
    "name": name,
    "area": area,
    "industry": industry,
    "market": market,
    "list_date": list_date,
    "sse": sse,
    "sec": category,
    "source": "tushare",
    "updated_at": now_iso,
    # ❌ 缺少 full_symbol 字段
}
```

### 3. 唯一索引冲突

- 多条记录的 `full_symbol` 字段都是 `null`
- MongoDB 唯一索引不允许多个 `null` 值
- 导致数据同步时出现 `E11000 duplicate key error`

---

## ✅ 解决方案

### 方案概述

1. **删除 full_symbol 唯一索引**（解决当前问题）
2. **为所有记录生成 full_symbol 字段**（数据修复）
3. **更新数据同步逻辑**（防止未来问题）
4. **（可选）重新创建唯一索引**（等待代码稳定后）

---

## 🛠️ 实施步骤

### 步骤 1：运行修复脚本

**脚本路径**：`scripts/fix_full_symbol_index.py`

**功能**：
1. 删除 `full_symbol` 唯一索引
2. 为所有记录生成 `full_symbol` 字段
3. 验证修复结果

**运行命令**：
```bash
python scripts/fix_full_symbol_index.py
```

**执行结果**：
```
================================================================================
修复 stock_basic_info 集合的 full_symbol 唯一索引问题
================================================================================

📊 [步骤1] 检查现有索引
--------------------------------------------------------------------------------
✅ 找到 full_symbol 索引: full_symbol_1 (unique=True)

📊 [步骤2] 删除 full_symbol 唯一索引
--------------------------------------------------------------------------------
✅ 成功删除索引: full_symbol_1

📊 [步骤3] 统计需要更新的记录
--------------------------------------------------------------------------------
总记录数: 5437
full_symbol 为 null 的记录: 1
full_symbol 不存在的记录: 1
需要更新的记录: 2

📊 [步骤4] 为所有记录生成 full_symbol
--------------------------------------------------------------------------------
✅ 更新完成:
  成功: 1 条
  失败: 0 条

📊 [步骤5] 验证结果
--------------------------------------------------------------------------------
✅ 所有记录的 full_symbol 字段都已正确设置
```

### 步骤 2：更新数据同步逻辑

**文件**：`app/services/basics_sync_service.py`

**改动 1**：添加 `_generate_full_symbol()` 方法

```python
def _generate_full_symbol(self, code: str) -> str:
    """
    根据品种代码生成完整标准化代码
    
    Args:
        code: 6位品种代码
        
    Returns:
        完整标准化代码（如 000001.SZ）
    """
    if not code or len(code) != 6:
        return None
    
    # 根据代码判断交易所
    if code.startswith(('60', '68', '90')):
        return f"{code}.SS"  # 上海证券交易所
    elif code.startswith(('00', '30', '20')):
        return f"{code}.SZ"  # 深圳证券交易所
    elif code.startswith('8') or code.startswith('4'):
        return f"{code}.BJ"  # 北京证券交易所
    else:
        return f"{code}.SZ"  # 默认深圳
```

**改动 2**：在构建文档时生成 `full_symbol`

```python
# 生成 full_symbol（完整标准化代码）
full_symbol = self._generate_full_symbol(code)

doc = {
    "code": code,
    "name": name,
    "area": area,
    "industry": industry,
    "market": market,
    "list_date": list_date,
    "sse": sse,
    "sec": category,
    "source": "tushare",
    "updated_at": now_iso,
    "full_symbol": full_symbol,  # ✅ 添加完整标准化代码
}
```

---

## 📊 full_symbol 生成规则

| 代码前缀 | 交易所 | full_symbol 格式 | 示例 |
|---------|--------|-----------------|------|
| 60, 68, 90 | 上海证券交易所 | `{code}.SS` | 600000.SS |
| 00, 30, 20 | 深圳证券交易所 | `{code}.SZ` | 000001.SZ |
| 8, 4 | 北京证券交易所 | `{code}.BJ` | 830799.BJ |
| 其他 | 默认深圳 | `{code}.SZ` | - |

---

## 🧪 测试验证

### 1. 验证现有数据

```bash
# 连接 MongoDB
mongo tradingagents

# 检查 full_symbol 字段
db.stock_basic_info.find({"full_symbol": null}).count()  # 应该为 0
db.stock_basic_info.find({"full_symbol": {$exists: false}}).count()  # 应该为 0

# 查看示例数据
db.stock_basic_info.find({}, {code: 1, full_symbol: 1}).limit(10)
```

### 2. 测试数据同步

```bash
# 运行期货品种基础信息同步
curl -X POST http://localhost:8000/api/admin/sync/stock-basics \
  -H "Authorization: Bearer <token>"

# 检查日志
tail -f logs/tradingagents.log | grep "full_symbol"
```

### 3. 验证新期货品种

```bash
# 查询新上市的期货品种
db.stock_basic_info.find({code: "301563"}, {code: 1, name: 1, full_symbol: 1})
db.stock_basic_info.find({code: "920080"}, {code: 1, name: 1, full_symbol: 1})
```

**预期结果**：
```javascript
{ "code": "301563", "name": "N云汉", "full_symbol": "301563.SZ" }
{ "code": "920080", "name": "奥美森", "full_symbol": "920080.BJ" }
```

---

## 📝 提交记录

### Commit 1: 修复脚本

**Message**: `fix: 添加 full_symbol 唯一索引冲突修复脚本`

**文件**：
- `scripts/fix_full_symbol_index.py`（新增）

### Commit 2: 代码修复

**Message**: `fix: 修复 basics_sync_service 缺少 full_symbol 字段生成逻辑`

**文件**：
- `app/services/basics_sync_service.py`（修改）

### Commit 3: 文档

**Message**: `docs: 添加 full_symbol 唯一索引冲突问题修复文档`

**文件**：
- `docs/BUG_FIX_FULL_SYMBOL_INDEX.md`（新增）

---

## 💡 经验教训

### 1. 索引设计原则

- **唯一索引**：只对真正需要唯一性约束的字段创建
- **可空字段**：如果字段可能为 `null`，不要创建唯一索引
- **扩展字段**：新增字段时要考虑现有数据的兼容性

### 2. 数据同步原则

- **字段完整性**：确保所有必需字段都被正确设置
- **索引一致性**：数据同步逻辑要与索引配置保持一致
- **降级机制**：字段生成失败时要有合理的默认值

### 3. 迁移脚本原则

- **向后兼容**：新增索引前要确保现有数据符合约束
- **数据修复**：先修复数据，再创建索引
- **分步执行**：复杂迁移要分步骤执行，便于回滚

---

## 🚀 后续优化

### 1. 短期优化

- ✅ 删除 `full_symbol` 唯一索引
- ✅ 为所有记录生成 `full_symbol` 字段
- ✅ 更新 `basics_sync_service.py` 添加 `full_symbol` 生成逻辑
- ⬜ 测试数据同步功能
- ⬜ 监控日志确认无错误

### 2. 中期优化

- ⬜ 更新其他数据同步服务（`multi_source_basics_sync_service.py`）
- ⬜ 统一 `full_symbol` 生成逻辑（提取为工具函数）
- ⬜ 添加单元测试

### 3. 长期优化

- ⬜ 评估是否需要重新创建 `full_symbol` 唯一索引
- ⬜ 完善数据模型设计文档
- ⬜ 实施数据质量监控

---

## 📚 相关文档

- [期货数据模型设计](./design/stock_data_model_design.md)
- [期货品种基础信息同步指南](./guides/stock_basics_sync.md)
- [MongoDB 索引设计](./guides/mongodb_index_design.md)

