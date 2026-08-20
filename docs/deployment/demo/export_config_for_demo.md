# 导出配置数据用于演示系统部署

## 📋 概述

本文档说明如何使用系统内置的数据导出功能，导出配置数据用于在新服务器上部署演示系统。

---

## 🎯 使用场景

当您需要在新服务器上部署演示系统时，可以：
- ✅ **保留**：系统配置、LLM 配置、用户数据等配置信息
- ❌ **不保留**：分析报告、期货数据、历史记录等业务数据

这样可以快速搭建一个包含完整配置的演示环境，而不需要重新配置 15 个 LLM 模型。

---

## 🚀 操作步骤

### 1. 导出配置数据

#### 方法 1：使用前端界面（推荐）

1. **登录系统**
   - 访问前端界面
   - 使用管理员账号登录

2. **进入数据库管理页面**
   - 导航到：`系统管理` → `数据库管理`

3. **导出配置数据**
   - 在"数据导出"区域：
     - **导出格式**：选择 `JSON`（推荐）
     - **数据集合**：选择 `配置数据（用于演示系统）`
   - 点击"导出数据"按钮
   - 浏览器会自动下载文件：`database_export_config_YYYY-MM-DD.json`

#### 方法 2：使用 API

```bash
# 使用 curl 导出配置数据
curl -X POST "http://localhost:8000/api/system/database/export" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "collections": [
      "system_configs",
      "users",
      "llm_providers",
      "market_categories",
      "user_tags",
      "datasource_groupings",
      "platform_configs",
      "user_configs",
      "model_catalog",
      "market_quotes",
      "stock_basic_info"
    ],
    "format": "json"
  }' \
  --output config_export.json
```

---

### 2. 传输到新服务器

将导出的文件传输到新服务器：

```bash
# 使用 scp
scp database_export_config_2025-10-16.json user@new-server:/path/to/destination/

# 或使用其他方式（FTP、云存储等）
```

---

### 3. 在新服务器上导入

#### 方法 1：使用前端界面（推荐）

1. **确保新服务器已部署**
   - MongoDB 容器正在运行
   - 后端服务正在运行
   - 前端服务正在运行

2. **登录新服务器的前端**
   - 使用默认管理员账号登录（如果是全新部署）

3. **导入配置数据**
   - 导航到：`系统管理` → `数据库管理`
   - 在"数据导入"区域：
     - 选择要导入的集合（或选择"覆盖所有"）
     - 上传导出的 JSON 文件
     - 勾选"覆盖现有数据"（如果需要）
   - 点击"导入数据"按钮

4. **重启后端服务**
   ```bash
   docker restart tradingagents-backend
   ```

#### 方法 2：使用 API

```bash
# 导入配置数据
curl -X POST "http://new-server:8000/api/system/database/import" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@database_export_config_2025-10-16.json" \
  -F "collection=system_configs" \
  -F "format=json" \
  -F "overwrite=true"
```

---

## 📦 导出的配置数据包含

| 集合名称 | 说明 | 重要性 |
|---------|------|--------|
| `system_configs` | 系统配置（包括 15 个 LLM 配置） | ⭐⭐⭐⭐⭐ |
| `users` | 用户账号和权限 | ⭐⭐⭐⭐⭐ |
| `llm_providers` | LLM 提供商信息 | ⭐⭐⭐⭐ |
| `market_categories` | 市场分类配置 | ⭐⭐⭐ |
| `user_tags` | 用户标签配置 | ⭐⭐⭐ |
| `datasource_groupings` | 数据源分组配置 | ⭐⭐⭐ |
| `platform_configs` | 平台配置 | ⭐⭐⭐ |
| `user_configs` | 用户个性化配置 | ⭐⭐ |
| `model_catalog` | 模型目录 | ⭐⭐ |
| `market_quotes` | 实时行情数据 | ⭐⭐⭐⭐ |
| `stock_basic_info` | 期货品种基础信息 | ⭐⭐⭐⭐ |

### 包含的 LLM 配置（15 个）

导出的配置数据包含以下已启用的 LLM 模型：

```
✅ Google Gemini
   - gemini-2.5-pro
   - gemini-2.5-flash

✅ DeepSeek
   - deepseek-chat

✅ 百度千帆
   - ernie-3.5-8k
   - ernie-4.0-turbo-8k

✅ 阿里百炼 (DashScope)
   - qwen3-max
   - qwen-flash
   - qwen-plus
   - qwen-turbo

✅ OpenRouter
   - anthropic/claude-sonnet-4.5
   - openai/gpt-5
   - google/gemini-2.5-pro
   - google/gemini-2.5-flash
   - openai/gpt-3.5-turbo
   - google/gemini-2.0-flash-001
```

---

## ❌ 不导出的数据

以下数据**不会**被导出（节省空间和时间）：

| 集合名称 | 说明 | 原因 |
|---------|------|------|
| `analysis_reports` | 分析报告 | 演示系统不需要历史报告 |
| `analysis_tasks` | 分析任务 | 演示系统不需要历史任务 |
| `stock_basic_info` | 期货品种基础信息 | 数据量大，可重新同步 |
| `market_quotes` | 市场行情 | 实时数据，可重新获取 |
| `stock_daily_quotes` | 日线行情 | 数据量大，可重新同步 |
| `financial_data_cache` | 财务数据缓存 | 缓存数据，可重新生成 |
| `financial_metrics_cache` | 财务指标缓存 | 缓存数据，可重新生成 |
| `operation_logs` | 操作日志 | 演示系统不需要历史日志 |
| `scheduler_history` | 调度历史 | 演示系统不需要历史记录 |
| `token_usage` | Token 使用记录 | 演示系统不需要历史记录 |
| `usage_records` | 使用记录 | 演示系统不需要历史记录 |
| `notifications` | 通知消息 | 演示系统不需要历史通知 |

---

## ⚠️ 重要注意事项

### 1. API 密钥安全

导出的配置数据包含 LLM 和数据源的 API 密钥，请：
- ✅ 妥善保管导出文件
- ✅ 使用加密传输（HTTPS、SCP）
- ✅ 传输后删除临时文件
- ❌ 不要上传到公共代码仓库
- ❌ 不要通过不安全的渠道传输

### 2. 用户密码

导出的用户数据包含加密后的密码：
- ✅ 密码已使用 bcrypt 加密
- ✅ 导入后用户可以使用原密码登录
- ⚠️ 如果是演示系统，建议导入后修改密码

### 3. 数据覆盖

导入时如果选择"覆盖现有数据"：
- ⚠️ 会删除新服务器上的同名集合
- ⚠️ 建议在导入前备份新服务器数据
- ✅ 如果是全新部署，可以安全覆盖

### 4. 服务重启

导入配置数据后，**必须重启后端服务**：
```bash
docker restart tradingagents-backend
```

原因：
- 配置桥接机制需要重新加载配置
- 环境变量需要重新同步
- 缓存需要清空

---

## ✅ 验证导入

### 1. 检查系统配置

```bash
# 连接到 MongoDB
docker exec -it tradingagents-mongodb mongo tradingagents \
  -u admin -p CHANGE_ME_LOCAL_PASSWORD --authenticationDatabase admin

# 检查系统配置
db.system_configs.countDocuments()

# 检查 LLM 配置
var config = db.system_configs.findOne({is_active: true});
if (config && config.llm_configs) {
  print('启用的 LLM 数量: ' + config.llm_configs.filter(c => c.enabled).length);
}
```

### 2. 检查用户数据

```bash
# 检查用户数量
db.users.countDocuments()

# 查看用户列表
db.users.find({}, {username: 1, email: 1, role: 1})
```

### 3. 测试登录

- 使用原系统的用户名和密码登录新系统
- 检查是否能正常访问

### 4. 测试 LLM 配置

- 进入"系统配置"页面
- 检查 LLM 配置是否正确显示
- 测试 LLM 连接

---

## 🔧 故障排除

### 问题 1：导入后配置不生效

**解决方案**：
```bash
# 重启后端服务
docker restart tradingagents-backend

# 检查后端日志
docker logs tradingagents-backend --tail 100
```

### 问题 2：导入失败

**可能原因**：
- MongoDB 容器未运行
- 文件格式错误
- 权限不足

**解决方案**：
```bash
# 检查 MongoDB 状态
docker ps | grep mongodb

# 检查文件格式
head -n 20 database_export_config_2025-10-16.json

# 检查用户权限
# 确保使用管理员账号登录
```

### 问题 3：用户无法登录

**可能原因**：
- 密码加密方式不兼容
- 用户数据未正确导入

**解决方案**：
```bash
# 重置管理员密码
docker exec -it tradingagents-mongodb mongo tradingagents \
  -u admin -p CHANGE_ME_LOCAL_PASSWORD --authenticationDatabase admin \
  --eval "db.users.updateOne({username: 'admin'}, {\$set: {password: '\$2b\$12\$...'}})"
```

---

## 📚 相关文档

- [数据库管理文档](./database_management.md)
- [Docker 数据卷管理](./docker_volumes_unified.md)
- [系统配置说明](./system_configuration.md)

---

## 💡 最佳实践

### 1. 定期导出配置

建议定期导出配置数据作为备份：
```bash
# 每周导出一次
# 保存到安全的位置
```

### 2. 版本控制

为导出文件添加版本标记：
```
database_export_config_v1.0.0_2025-10-16.json
```

### 3. 文档化

记录每次导出的内容和用途：
```
导出时间: 2025-10-16
导出原因: 部署演示系统
包含配置: 15 个 LLM 模型
目标服务器: demo.example.com
```

---

## 🎉 总结

使用系统内置的"配置数据"导出功能，您可以：

✅ **快速部署演示系统**
- 无需重新配置 15 个 LLM 模型
- 保留用户账号和权限
- 保留所有系统配置

✅ **节省时间和空间**
- 只导出必要的配置数据
- 不包含大量业务数据
- 文件小，传输快

✅ **安全可靠**
- API 密钥加密传输
- 用户密码已加密
- 支持数据覆盖和增量导入

现在您可以轻松地在新服务器上部署一个包含完整配置的演示系统了！🚀

