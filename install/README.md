# 演示系统部署文件

## 📋 目录说明

本目录包含用于快速部署 TradingAgents 演示系统的配置文件。

### 文件列表

| 文件 | 说明 |
|------|------|
| `database_export_config_2025-10-16.json` | 系统配置数据导出文件 |

---

## 📦 配置文件内容

### `database_export_config_2025-10-16.json`

包含以下配置数据（共 9 个集合，约 48 个文档）：

| 集合 | 说明 | 文档数 |
|------|------|--------|
| `system_configs` | 系统配置（包括 15 个 LLM 配置） | 1 |
| `users` | 用户数据 | 3 |
| `llm_providers` | LLM 提供商配置 | 5 |
| `market_categories` | 市场分类 | 10 |
| `user_tags` | 用户标签 | 8 |
| `datasource_groupings` | 数据源分组 | 3 |
| `platform_configs` | 平台配置 | 1 |
| `user_configs` | 用户配置 | 2 |
| `model_catalog` | 模型目录 | 15 |

**包含的 LLM 模型**：
- ✅ Google Gemini (gemini-1.5-pro, gemini-1.5-flash)
- ✅ DeepSeek (deepseek-chat, deepseek-reasoner)
- ✅ 百度千帆 (ERNIE-4.0-Turbo-8K, ERNIE-3.5-8K)
- ✅ 阿里百炼 (qwen-max, qwen-plus, qwen-turbo)
- ✅ OpenRouter (多个模型)

**不包含的数据**：
- ❌ 分析报告（`analysis_reports`）
- ❌ 股票数据（`stock_basic_info`, `market_quotes`）
- ❌ 历史记录（`operation_logs`, `scheduler_history`）
- ❌ 缓存数据（`financial_data_cache`）

---

## 🚀 使用方法

### 方法 1：使用一键部署脚本（推荐）

```bash
# 下载并运行部署脚本
curl -fsSL https://raw.githubusercontent.com/your-org/TradingAgents-CN/main/scripts/deploy_demo.sh | bash
```

脚本会自动：
1. 检查系统要求
2. 安装 Docker 和 Docker Compose
3. 下载项目文件（包括本配置文件）
4. 配置环境变量
5. 启动服务
6. 导入配置数据
7. 创建默认管理员账号（admin/admin123）

### 方法 2：手动部署

#### 步骤 1：克隆仓库或下载文件

```bash
# 克隆完整仓库
git clone https://github.com/your-org/TradingAgents-CN.git
cd TradingAgents-CN

# 或只下载必要文件
mkdir -p TradingAgents-Demo/install
cd TradingAgents-Demo
curl -o install/database_export_config_2025-10-16.json \
  https://raw.githubusercontent.com/your-org/TradingAgents-CN/main/install/database_export_config_2025-10-16.json
```

#### 步骤 2：启动服务

```bash
# 配置环境变量
cp .env.example .env
nano .env  # 修改必要的配置

# 启动服务
docker compose -f docker-compose.hub.yml up -d

# 等待服务启动
sleep 15
```

#### 步骤 3：导入配置数据

```bash
# 安装 Python 依赖
pip3 install pymongo

# 运行导入脚本（自动从 install 目录读取配置文件）
python3 scripts/import_config_and_create_user.py

# 重启后端服务
docker restart tradingagents-backend
```

#### 步骤 4：访问系统

- 前端：`http://your-server:3000`
- 用户名：`admin`
- 密码：`admin123`

---

## 🔄 更新配置文件

如果需要更新配置文件（例如添加新的 LLM 模型或修改系统配置）：

### 1. 在原系统导出新配置

1. 登录原系统
2. 进入：`系统管理` → `数据库管理`
3. 选择：`配置数据（用于演示系统）`
4. 导出格式：`JSON`
5. 下载文件

### 2. 替换配置文件

```bash
# 备份旧文件
mv install/database_export_config_2025-10-16.json \
   install/database_export_config_2025-10-16.json.bak

# 复制新文件
cp /path/to/new/export.json install/database_export_config_$(date +%Y-%m-%d).json
```

### 3. 重新导入

```bash
# 使用覆盖模式导入
python3 scripts/import_config_and_create_user.py --overwrite

# 重启后端
docker restart tradingagents-backend
```

---

## 📝 注意事项

### 1. API 密钥

配置文件中的 API 密钥已加密，但仍建议：
- ✅ 导入后在系统中重新配置 API 密钥
- ✅ 不要在公开仓库中提交包含真实 API 密钥的配置文件
- ✅ 使用环境变量管理敏感信息

### 2. 用户数据

配置文件中包含的用户数据：
- ✅ 密码已使用 SHA256 哈希
- ✅ 导入脚本会自动创建默认管理员（admin/admin123）
- ⚠️ 建议导入后立即修改默认密码

### 3. 数据完整性

- ✅ 配置文件包含完整的系统配置
- ✅ 导入脚本会自动转换数据类型（ObjectId、DateTime）
- ✅ 支持增量导入（跳过已存在的文档）
- ✅ 支持覆盖导入（删除现有数据后导入）

### 4. 版本兼容性

- ✅ 配置文件格式：JSON
- ✅ 导出时间：2025-10-16
- ✅ 系统版本：v1.0.0+
- ⚠️ 如果系统版本不匹配，可能需要手动调整配置

---

## 🐛 故障排除

### 问题 1：配置文件未找到

**错误信息**：
```
install 目录中未找到配置文件 (database_export_config_*.json)
```

**解决方案**：
```bash
# 检查文件是否存在
ls -lh install/

# 手动指定文件路径
python3 scripts/import_config_and_create_user.py install/database_export_config_2025-10-16.json
```

### 问题 2：导入失败

**解决方案**：
```bash
# 检查 MongoDB 是否运行
docker ps | grep mongodb

# 检查文件格式
python3 -m json.tool install/database_export_config_2025-10-16.json > /dev/null

# 查看详细错误
python3 scripts/import_config_and_create_user.py --verbose
```

### 问题 3：配置未生效

**解决方案**：
```bash
# 重启后端服务
docker restart tradingagents-backend

# 查看后端日志
docker logs tradingagents-backend --tail 50

# 验证配置是否导入
docker exec -it tradingagents-mongodb mongosh tradingagents \
  -u admin -p tradingagents123 --authenticationDatabase admin \
  --eval "db.system_configs.countDocuments()"
```

---

## 📚 相关文档

- [演示系统部署完整指南](../docs/deploy_demo_system.md)
- [使用脚本导入配置](../docs/import_config_with_script.md)
- [导出配置数据](../docs/export_config_for_demo.md)

---

## 🔗 快速链接

- **部署脚本**：`../scripts/deploy_demo.sh`
- **导入脚本**：`../scripts/import_config_and_create_user.py`
- **创建用户脚本**：`../scripts/create_default_admin.py`
- **Docker Compose**：`../docker-compose.hub.yml`

---

## 💡 提示

1. **首次部署**：使用一键部署脚本最简单
2. **更新配置**：使用 `--overwrite` 参数覆盖导入
3. **安全加固**：部署后立即修改默认密码
4. **备份数据**：定期导出配置数据作为备份

---

## 📞 获取帮助

如有问题，请：
- 📖 查看完整文档：`docs/deploy_demo_system.md`
- 🐛 提交 Issue：GitHub Issues
- 💬 联系支持：技术支持团队

