# 模型能力验证修复文档

## 📋 问题描述

用户报告在使用 `gemini-2.5-flash` + `qwen-plus` 进行期货分析时，系统提示：

```
❌ 快速模型 gemini-2.5-flash 不支持工具调用，无法完成数据收集任务
🔄 自动切换到推荐模型...
```

但是，用户在数据库中配置了 `gemini-2.5-flash` 的 `features` 包含 `["tool_calling", "cost_effective", "fast_response"]`，应该支持工具调用。

## 🔍 问题分析

### 1. 数据源不一致

**问题**：模型能力验证服务 (`model_capability_service.py`) 从 **`unified_config.get_llm_configs()`** 读取配置，而这个方法从 **`models.json` 文件**读取，而不是从 MongoDB 读取。

**影响**：
- API 接口 (`/api/config/llm`) 从 MongoDB 读取配置 ✅
- 分析服务从 `models.json` 文件读取配置 ❌
- 两个地方读取的数据源不一致，导致配置不同步

### 2. 字符串与枚举类型不匹配

**问题**：数据库中存储的 `features` 和 `suitable_roles` 是**字符串列表**（如 `["tool_calling"]`），但验证代码期望的是 **枚举列表**（如 `[ModelFeature.TOOL_CALLING]`）。

**影响**：
```python
if ModelFeature.TOOL_CALLING not in quick_features:  # ❌ 永远不会通过
    # quick_features = ["tool_calling"]  # 字符串列表
    # ModelFeature.TOOL_CALLING  # 枚举对象
```

### 3. MongoDB 集合名称错误

**问题**：代码中使用的集合名称是 `system_config`（单数），但实际的集合名称是 `system_configs`（复数）。

### 4. 查询条件缺失

**问题**：代码使用 `collection.find_one()` 查询，没有指定 `{"is_active": True}` 条件，导致可能查询到旧的配置。

## ✅ 修复方案

### 修改的文件

**文件**：`app/services/model_capability_service.py`

### 修改内容

#### 1. 从 MongoDB 读取配置

**修改前**：
```python
# 1. 优先从数据库配置读取
try:
    llm_configs = unified_config.get_llm_configs()  # ❌ 从 models.json 读取
    for config in llm_configs:
        if config.model_name == model_name:
            # ...
```

**修改后**：
```python
# 1. 优先从 MongoDB 数据库配置读取（使用同步客户端）
try:
    from pymongo import MongoClient
    from app.core.config import settings
    
    # 使用同步 MongoDB 客户端
    client = MongoClient(settings.MONGO_URI)
    db = client[settings.MONGO_DB]
    collection = db.system_configs  # ✅ 集合名是复数
    
    # 查询系统配置（与 config_service 保持一致）
    doc = collection.find_one({"is_active": True}, sort=[("version", -1)])  # ✅ 查询最新的活跃配置
    
    if doc and "llm_configs" in doc:
        llm_configs = doc["llm_configs"]
        for config_dict in llm_configs:
            if config_dict.get("model_name") == model_name:
                # ...
```

#### 2. 字符串到枚举的转换

**修改前**：
```python
"features": getattr(config, 'features', []),  # ❌ 字符串列表
"suitable_roles": getattr(config, 'suitable_roles', [ModelRole.BOTH]),  # ❌ 字符串列表
```

**修改后**：
```python
# 🔧 将字符串列表转换为枚举列表
features_str = config_dict.get('features', [])
features_enum = []
for feature_str in features_str:
    try:
        # 将字符串转换为 ModelFeature 枚举
        features_enum.append(ModelFeature(feature_str))
    except ValueError:
        logger.warning(f"⚠️ 未知的特性值: {feature_str}")

# 🔧 将字符串列表转换为枚举列表
roles_str = config_dict.get('suitable_roles', ["both"])
roles_enum = []
for role_str in roles_str:
    try:
        # 将字符串转换为 ModelRole 枚举
        roles_enum.append(ModelRole(role_str))
    except ValueError:
        logger.warning(f"⚠️ 未知的角色值: {role_str}")

# 如果没有角色，默认为 both
if not roles_enum:
    roles_enum = [ModelRole.BOTH]

return {
    "model_name": config_dict.get("model_name"),
    "capability_level": config_dict.get('capability_level', 2),
    "suitable_roles": roles_enum,  # ✅ 枚举列表
    "features": features_enum,  # ✅ 枚举列表
    "recommended_depths": config_dict.get('recommended_depths', ["快速", "基础", "标准"]),
    "performance_metrics": config_dict.get('performance_metrics', None)
}
```

## 🧪 测试验证

### 测试脚本

创建了 `scripts/test_simple.py` 测试脚本。

### 测试结果

```
================================================================================
测试：gemini-2.5-flash 配置
================================================================================

features: [<ModelFeature.TOOL_CALLING: 'tool_calling'>, <ModelFeature.COST_EFFECTIVE: 'cost_effective'>, <ModelFeature.FAST_RESPONSE: 'fast_response'>]
suitable_roles: [<ModelRole.BOTH: 'both'>]

================================================================================
测试：模型对验证
================================================================================

验证结果:
  - valid: True
  - warnings: 0 条

✅ 验证通过！模型对可以使用
```

## 📊 修复效果

### 修复前

- ❌ 从 `models.json` 文件读取配置
- ❌ 配置与数据库不同步
- ❌ 字符串列表无法与枚举比较
- ❌ 验证失败，提示不支持工具调用
- ❌ 自动切换到其他模型

### 修复后

- ✅ 从 MongoDB 读取配置
- ✅ 配置与数据库同步
- ✅ 字符串列表正确转换为枚举列表
- ✅ 验证通过，支持工具调用
- ✅ 使用用户指定的模型

## 🔍 根本原因

这是一个**数据源不一致**的问题：

1. **API 接口**从 MongoDB 读取配置
2. **分析服务**从 `models.json` 文件读取配置
3. 两个地方读取的数据源不同，导致配置不同步

此外，还有一个**类型转换**问题：

1. 数据库中存储的是字符串列表
2. 验证代码期望的是枚举列表
3. 没有进行类型转换，导致比较失败

## 💡 预防措施

### 1. 统一数据源

所有服务都应该从 MongoDB 读取配置，而不是从文件读取。

### 2. 类型转换

在读取数据库配置时，应该将字符串列表转换为枚举列表。

### 3. 单元测试

为模型能力验证添加单元测试：

```python
def test_model_capability_validation():
    """测试模型能力验证"""
    service = ModelCapabilityService()
    
    # 测试 gemini-2.5-flash
    config = service.get_model_config("gemini-2.5-flash")
    assert ModelFeature.TOOL_CALLING in config["features"]
    
    # 测试模型对验证
    result = service.validate_model_pair(
        quick_model="gemini-2.5-flash",
        deep_model="qwen-plus",
        research_depth="标准"
    )
    assert result["valid"] == True
```

### 4. 日志记录

在读取配置时记录详细的日志，方便调试：

```python
logger.info(f"📊 [MongoDB配置] {model_name}: features={features_enum}, roles={roles_enum}")
```

## 📝 相关文件

1. ✅ `app/services/model_capability_service.py` - 修复模型能力验证
2. ✅ `scripts/test_simple.py` - 测试脚本
3. ✅ `scripts/test_direct_mongodb.py` - MongoDB 查询测试
4. ✅ `scripts/check_mongodb_system_config.py` - 系统配置检查脚本

## 🎯 总结

这是一个**数据源不一致**和**类型转换**的问题：

- **原因1**：模型能力验证服务从 `models.json` 文件读取配置，而不是从 MongoDB 读取
- **原因2**：数据库中存储的是字符串列表，但验证代码期望的是枚举列表
- **影响**：导致验证失败，提示不支持工具调用
- **修复**：从 MongoDB 读取配置，并将字符串列表转换为枚举列表
- **验证**：通过测试脚本验证修复效果

修复后，系统可以正确读取数据库中的模型配置，验证通过，使用用户指定的模型！🎉

## 📅 修复日期

2025-10-12

