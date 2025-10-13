# USER_MANAGEMENT 操作类型缺失问题修复

## 问题描述

用户在修改密码时遇到错误：

```
2025-10-13 10:40:00,677 | app.routers.auth | ERROR | 修改密码失败: type object 'ActionType' has no attribute 'USER_MANAGEMENT'
```

### 错误堆栈

```python
File "app/routers/auth.py", line 310, in change_password
    action_type=ActionType.USER_MANAGEMENT,
AttributeError: type object 'ActionType' has no attribute 'USER_MANAGEMENT'
```

## 根本原因

### 代码使用情况

在 `app/routers/auth.py` 中，`change_password` 端点使用了 `ActionType.USER_MANAGEMENT`：

```python
# app/routers/auth.py (第 310、330、354 行)
await log_operation(
    user_id=user["id"],
    username=user["username"],
    action_type=ActionType.USER_MANAGEMENT,  # ❌ 使用了不存在的属性
    action="修改密码",
    # ...
)
```

### 定义缺失

但在 `app/models/operation_log.py` 中，`ActionType` 类**没有定义** `USER_MANAGEMENT` 属性：

```python
# app/models/operation_log.py (修复前)
class ActionType:
    """操作类型常量"""
    STOCK_ANALYSIS = "stock_analysis"
    CONFIG_MANAGEMENT = "config_management"
    CACHE_OPERATION = "cache_operation"
    DATA_IMPORT = "data_import"
    DATA_EXPORT = "data_export"
    SYSTEM_SETTINGS = "system_settings"
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    # ❌ 缺少 USER_MANAGEMENT
    DATABASE_OPERATION = "database_operation"
    SCREENING = "screening"
    REPORT_GENERATION = "report_generation"
```

## 解决方案

### 1. 后端修复

**文件**：`app/models/operation_log.py`

**修改**：添加 `USER_MANAGEMENT` 操作类型

```python
# 操作类型常量
class ActionType:
    """操作类型常量"""
    STOCK_ANALYSIS = "stock_analysis"
    CONFIG_MANAGEMENT = "config_management"
    CACHE_OPERATION = "cache_operation"
    DATA_IMPORT = "data_import"
    DATA_EXPORT = "data_export"
    SYSTEM_SETTINGS = "system_settings"
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    USER_MANAGEMENT = "user_management"  # ✅ 添加用户管理操作类型
    DATABASE_OPERATION = "database_operation"
    SCREENING = "screening"
    REPORT_GENERATION = "report_generation"


# 操作类型映射
ACTION_TYPE_NAMES = {
    ActionType.STOCK_ANALYSIS: "股票分析",
    ActionType.CONFIG_MANAGEMENT: "配置管理",
    ActionType.CACHE_OPERATION: "缓存操作",
    ActionType.DATA_IMPORT: "数据导入",
    ActionType.DATA_EXPORT: "数据导出",
    ActionType.SYSTEM_SETTINGS: "系统设置",
    ActionType.USER_LOGIN: "用户登录",
    ActionType.USER_LOGOUT: "用户登出",
    ActionType.USER_MANAGEMENT: "用户管理",  # ✅ 添加用户管理操作类型名称
    ActionType.DATABASE_OPERATION: "数据库操作",
    ActionType.SCREENING: "股票筛选",
    ActionType.REPORT_GENERATION: "报告生成",
}
```

### 2. 前端同步更新

**文件**：`frontend/src/api/operationLogs.ts`

**修改**：添加 `USER_MANAGEMENT` 操作类型定义

```typescript
// 操作类型常量
export const ActionTypes = {
  STOCK_ANALYSIS: 'stock_analysis',
  CONFIG_MANAGEMENT: 'config_management',
  CACHE_OPERATION: 'cache_operation',
  DATA_IMPORT: 'data_import',
  DATA_EXPORT: 'data_export',
  SYSTEM_SETTINGS: 'system_settings',
  USER_LOGIN: 'user_login',
  USER_LOGOUT: 'user_logout',
  USER_MANAGEMENT: 'user_management',  // ✅ 添加用户管理操作类型
  DATABASE_OPERATION: 'database_operation',
  SCREENING: 'screening',
  REPORT_GENERATION: 'report_generation'
} as const

// 操作类型名称映射
export const ActionTypeNames = {
  [ActionTypes.STOCK_ANALYSIS]: '股票分析',
  [ActionTypes.CONFIG_MANAGEMENT]: '配置管理',
  [ActionTypes.CACHE_OPERATION]: '缓存操作',
  [ActionTypes.DATA_IMPORT]: '数据导入',
  [ActionTypes.DATA_EXPORT]: '数据导出',
  [ActionTypes.SYSTEM_SETTINGS]: '系统设置',
  [ActionTypes.USER_LOGIN]: '用户登录',
  [ActionTypes.USER_LOGOUT]: '用户登出',
  [ActionTypes.USER_MANAGEMENT]: '用户管理',  // ✅ 添加用户管理操作类型名称
  [ActionTypes.DATABASE_OPERATION]: '数据库操作',
  [ActionTypes.SCREENING]: '股票筛选',
  [ActionTypes.REPORT_GENERATION]: '报告生成'
} as const

// 操作类型标签颜色映射
export const ActionTypeTagColors = {
  [ActionTypes.STOCK_ANALYSIS]: 'primary',
  [ActionTypes.CONFIG_MANAGEMENT]: 'success',
  [ActionTypes.CACHE_OPERATION]: 'warning',
  [ActionTypes.DATA_IMPORT]: 'info',
  [ActionTypes.DATA_EXPORT]: 'info',
  [ActionTypes.SYSTEM_SETTINGS]: 'danger',
  [ActionTypes.USER_LOGIN]: 'success',
  [ActionTypes.USER_LOGOUT]: 'warning',
  [ActionTypes.USER_MANAGEMENT]: 'warning',  // ✅ 添加用户管理操作类型颜色
  [ActionTypes.DATABASE_OPERATION]: 'primary',
  [ActionTypes.SCREENING]: 'info',
  [ActionTypes.REPORT_GENERATION]: 'primary'
} as const
```

## 影响范围

### 受影响的功能

1. **修改密码功能**（`POST /api/auth/change-password`）
   - 旧密码验证失败时记录日志（第 310 行）
   - 修改密码成功时记录日志（第 330 行）
   - 修改密码失败时记录日志（第 354 行）

### 操作日志记录

修复后，以下操作将被正确记录：

| 操作 | 操作类型 | 操作类型名称 | 标签颜色 |
|------|---------|-------------|---------|
| 修改密码 | `user_management` | "用户管理" | warning |

## 测试步骤

### 1. 重启后端服务

```bash
# 重启后端
python -m uvicorn app.main:app --reload
```

### 2. 测试修改密码功能

```bash
# 登录获取 token
curl -X POST http://127.0.0.1:3000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'

# 修改密码
curl -X POST http://127.0.0.1:3000/api/auth/change-password \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"old_password": "admin123", "new_password": "newpassword123"}'
```

### 3. 验证操作日志

```bash
# 查询操作日志
curl -X GET "http://127.0.0.1:3000/api/system/logs/operations?action_type=user_management" \
  -H "Authorization: Bearer <token>"
```

**期望结果**：
- 修改密码成功，返回 `{"success": true, "message": "密码修改成功"}`
- 操作日志中记录了 `action_type: "user_management"`，`action: "修改密码"`

### 4. 前端验证

1. 登录系统
2. 进入"系统设置" → "操作日志"
3. 筛选操作类型为"用户管理"
4. 应该能看到修改密码的操作记录

## 相关文件

### 后端

- `app/models/operation_log.py` - 操作类型定义
- `app/routers/auth.py` - 认证路由（使用 USER_MANAGEMENT）
- `app/services/operation_log_service.py` - 操作日志服务

### 前端

- `frontend/src/api/operationLogs.ts` - 操作日志 API 和类型定义
- `frontend/src/views/System/OperationLogs.vue` - 操作日志页面

## 总结

**问题根源**：代码中使用了 `ActionType.USER_MANAGEMENT`，但该属性未在 `ActionType` 类中定义。

**解决方案**：
1. 在 `ActionType` 类中添加 `USER_MANAGEMENT = "user_management"` 属性
2. 在 `ACTION_TYPE_NAMES` 字典中添加对应的中文名称
3. 在前端 TypeScript 定义中同步添加该类型

**关键教训**：
- 在使用常量之前，确保已经定义
- 前后端的类型定义应该保持同步
- 添加新的操作类型时，需要同时更新：
  1. 后端 `ActionType` 类
  2. 后端 `ACTION_TYPE_NAMES` 字典
  3. 前端 `ActionTypes` 常量
  4. 前端 `ActionTypeNames` 映射
  5. 前端 `ActionTypeTagColors` 映射

