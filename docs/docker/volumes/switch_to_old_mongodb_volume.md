# 切换到旧 MongoDB 数据卷

## 📊 问题分析

### 当前情况

| 项目 | 数据卷名称 | 状态 | 数据 |
|------|-----------|------|------|
| **当前运行的容器** | `tradingagents-cn_tradingagents_mongodb_data_v1` | ✅ 正在使用 | ❌ 空的（只有3个LLM配置） |
| **昨天使用的数据卷** | `tradingagents_mongodb_data` | ⚠️ 未使用 | ✅ **有完整数据**（15个LLM配置） |

### 数据卷内容对比

#### 旧数据卷 `tradingagents_mongodb_data`（有数据）

```
数据库大小: 4.27 GB
集合数量: 48 个
启用的 LLM: 15 个
  - google: gemini-2.5-pro
  - google: gemini-2.5-flash
  - deepseek: deepseek-chat
  - qianfan: ernie-3.5-8k
  - qianfan: ernie-4.0-turbo-8k
  - dashscope: qwen3-max
  - dashscope: qwen-flash
  - dashscope: qwen-plus
  - dashscope: qwen-turbo
  - openrouter: anthropic/claude-sonnet-4.5
  - openrouter: openai/gpt-5
  - openrouter: google/gemini-2.5-pro
  - openrouter: google/gemini-2.5-flash
  - openrouter: openai/gpt-3.5-turbo
  - openrouter: google/gemini-2.0-flash-001
```

#### 新数据卷 `tradingagents-cn_tradingagents_mongodb_data_v1`（空的）

```
启用的 LLM: 3 个
  - zhipu: glm-4
  - 其他2个
```

---

## 🔍 根本原因

不同的 `docker-compose` 文件使用了不同的数据卷名称：

| 文件 | MongoDB 数据卷 | Redis 数据卷 |
|------|---------------|-------------|
| `docker-compose.yml` | `tradingagents_mongodb_data` | `tradingagents_redis_data` |
| `docker-compose.split.yml` | `tradingagents_mongodb_data` | `tradingagents_redis_data` |
| `docker-compose.v1.0.0.yml` | `tradingagents_mongodb_data_v1` | `tradingagents_redis_data_v1` |
| `docker-compose.hub.yml` | `tradingagents_mongodb_data_v1` | `tradingagents_redis_data_v1` |

**当前运行的容器**使用的是 `docker-compose.hub.yml`（或类似配置），挂载了 `_v1` 后缀的新数据卷。

---

## ✅ 解决方案

### 方案 1：停止容器并使用旧数据卷重启（推荐）

#### 步骤 1：停止当前容器

```bash
# 停止 MongoDB 容器
docker stop tradingagents-mongodb

# 停止 Redis 容器（可选）
docker stop tradingagents-redis

# 或者停止所有相关容器
docker stop tradingagents-backend tradingagents-frontend tradingagents-mongodb tradingagents-redis
```

#### 步骤 2：删除当前容器

```bash
# 删除 MongoDB 容器
docker rm tradingagents-mongodb

# 删除 Redis 容器（可选）
docker rm tradingagents-redis
```

#### 步骤 3：使用旧数据卷重新启动

```bash
# 方法 A：使用 docker run 手动启动（推荐，更灵活）
docker run -d \
  --name tradingagents-mongodb \
  --network tradingagents-network \
  -p 27017:27017 \
  -v tradingagents_mongodb_data:/data/db \
  -v ./scripts/mongo-init.js:/docker-entrypoint-initdb.d/mongo-init.js:ro \
  -e MONGO_INITDB_ROOT_USERNAME=admin \
  -e MONGO_INITDB_ROOT_PASSWORD=CHANGE_ME_LOCAL_PASSWORD \
  -e MONGO_INITDB_DATABASE=tradingagents \
  -e TZ="Asia/Shanghai" \
  --restart unless-stopped \
  mongo:4.4

# 方法 B：使用 docker-compose.yml 启动
docker-compose up -d mongodb

# 方法 C：使用 docker-compose.split.yml 启动
docker-compose -f docker-compose.split.yml up -d mongodb
```

#### 步骤 4：验证数据

```bash
# 等待 MongoDB 启动
sleep 10

# 连接到 MongoDB 并查看数据
docker exec tradingagents-mongodb mongo tradingagents \
  -u admin -p CHANGE_ME_LOCAL_PASSWORD --authenticationDatabase admin \
  --eval "db.system_configs.findOne({is_active: true}).llm_configs.filter(c => c.enabled).map(c => c.provider + ': ' + c.model_name)"
```

**预期输出**：应该看到 15 个启用的 LLM 配置

---

### 方案 2：修改 docker-compose 文件统一使用旧数据卷

如果您经常使用 `docker-compose.hub.yml` 或 `docker-compose.v1.0.0.yml`，可以修改这些文件：

#### 修改 `docker-compose.hub.yml`

```yaml
# 修改前
volumes:
  tradingagents_mongodb_data_v1:
  tradingagents_redis_data_v1:

# 修改后
volumes:
  tradingagents_mongodb_data_v1:
    external: true
    name: tradingagents_mongodb_data
  tradingagents_redis_data_v1:
    external: true
    name: tradingagents_redis_data
```

#### 修改 `docker-compose.v1.0.0.yml`

```yaml
# 修改前
volumes:
  mongodb_data:
    driver: local
    name: tradingagents_mongodb_data_v1
  redis_data:
    driver: local
    name: tradingagents_redis_data_v1

# 修改后
volumes:
  mongodb_data:
    driver: local
    name: tradingagents_mongodb_data
  redis_data:
    driver: local
    name: tradingagents_redis_data
```

然后重启容器：

```bash
docker-compose -f docker-compose.hub.yml down
docker-compose -f docker-compose.hub.yml up -d
```

---

### 方案 3：数据迁移（如果需要保留两个数据卷的数据）

如果新数据卷中也有重要数据，可以进行数据迁移：

```bash
# 1. 导出新数据卷的数据
docker exec tradingagents-mongodb mongodump \
  -u admin -p CHANGE_ME_LOCAL_PASSWORD --authenticationDatabase admin \
  -d tradingagents -o /tmp/new_backup

docker cp tradingagents-mongodb:/tmp/new_backup ./mongodb_new_backup

# 2. 停止容器并切换到旧数据卷（参考方案1）

# 3. 导入新数据（选择性导入需要的集合）
docker cp ./mongodb_new_backup tradingagents-mongodb:/tmp/new_backup

docker exec tradingagents-mongodb mongorestore \
  -u admin -p CHANGE_ME_LOCAL_PASSWORD --authenticationDatabase admin \
  -d tradingagents /tmp/new_backup/tradingagents
```

---

## 🚀 快速操作脚本

### PowerShell 脚本

```powershell
# 停止并删除临时检查容器
docker stop temp_old_mongodb
docker rm temp_old_mongodb

# 停止当前 MongoDB 容器
docker stop tradingagents-mongodb
docker rm tradingagents-mongodb

# 使用旧数据卷重新启动 MongoDB
docker run -d `
  --name tradingagents-mongodb `
  --network tradingagents-network `
  -p 27017:27017 `
  -v tradingagents_mongodb_data:/data/db `
  -v ${PWD}/scripts/mongo-init.js:/docker-entrypoint-initdb.d/mongo-init.js:ro `
  -e MONGO_INITDB_ROOT_USERNAME=admin `
  -e MONGO_INITDB_ROOT_PASSWORD=CHANGE_ME_LOCAL_PASSWORD `
  -e MONGO_INITDB_DATABASE=tradingagents `
  -e TZ="Asia/Shanghai" `
  --restart unless-stopped `
  mongo:4.4

# 等待 MongoDB 启动
Write-Host "等待 MongoDB 启动..." -ForegroundColor Yellow
Start-Sleep -Seconds 15

# 验证数据
Write-Host "验证数据..." -ForegroundColor Yellow
docker exec tradingagents-mongodb mongo tradingagents `
  -u admin -p CHANGE_ME_LOCAL_PASSWORD --authenticationDatabase admin `
  --quiet --eval "print('启用的 LLM 数量: ' + db.system_configs.findOne({is_active: true}).llm_configs.filter(c => c.enabled).length)"

Write-Host "✅ 切换完成！" -ForegroundColor Green
```

### Bash 脚本

```bash
#!/bin/bash

# 停止并删除临时检查容器
docker stop temp_old_mongodb
docker rm temp_old_mongodb

# 停止当前 MongoDB 容器
docker stop tradingagents-mongodb
docker rm tradingagents-mongodb

# 使用旧数据卷重新启动 MongoDB
docker run -d \
  --name tradingagents-mongodb \
  --network tradingagents-network \
  -p 27017:27017 \
  -v tradingagents_mongodb_data:/data/db \
  -v $(pwd)/scripts/mongo-init.js:/docker-entrypoint-initdb.d/mongo-init.js:ro \
  -e MONGO_INITDB_ROOT_USERNAME=admin \
  -e MONGO_INITDB_ROOT_PASSWORD=CHANGE_ME_LOCAL_PASSWORD \
  -e MONGO_INITDB_DATABASE=tradingagents \
  -e TZ="Asia/Shanghai" \
  --restart unless-stopped \
  mongo:4.4

# 等待 MongoDB 启动
echo "等待 MongoDB 启动..."
sleep 15

# 验证数据
echo "验证数据..."
docker exec tradingagents-mongodb mongo tradingagents \
  -u admin -p CHANGE_ME_LOCAL_PASSWORD --authenticationDatabase admin \
  --quiet --eval "print('启用的 LLM 数量: ' + db.system_configs.findOne({is_active: true}).llm_configs.filter(c => c.enabled).length)"

echo "✅ 切换完成！"
```

---

## ⚠️ 注意事项

1. **备份数据**（可选但推荐）：
   ```bash
   # 备份旧数据卷
   docker run --rm -v tradingagents_mongodb_data:/data -v $(pwd):/backup \
     alpine tar czf /backup/mongodb_backup_$(date +%Y%m%d_%H%M%S).tar.gz /data
   ```

2. **检查网络**：
   确保 `tradingagents-network` 网络存在：
   ```bash
   docker network ls | grep tradingagents-network
   # 如果不存在，创建网络
   docker network create tradingagents-network
   ```

3. **检查端口占用**：
   确保 27017 端口未被占用：
   ```bash
   netstat -ano | findstr :27017
   ```

4. **后端服务**：
   切换数据卷后，需要重启后端服务以重新连接数据库：
   ```bash
   docker restart tradingagents-backend
   ```

---

## ✅ 验证清单

切换完成后，请验证以下内容：

- [ ] MongoDB 容器正常运行：`docker ps | grep tradingagents-mongodb`
- [ ] 挂载了正确的数据卷：`docker inspect tradingagents-mongodb -f '{{range .Mounts}}{{.Name}}{{end}}'` 应显示 `tradingagents_mongodb_data`
- [ ] 数据库包含完整数据：连接 MongoDB 并查看 `system_configs` 集合
- [ ] 启用的 LLM 配置数量正确：应该有 15 个
- [ ] 后端服务能正常连接数据库
- [ ] 前端能正常显示配置数据

---

## 📝 总结

| 操作 | 命令 |
|------|------|
| **停止临时容器** | `docker stop temp_old_mongodb && docker rm temp_old_mongodb` |
| **停止当前容器** | `docker stop tradingagents-mongodb && docker rm tradingagents-mongodb` |
| **使用旧数据卷启动** | `docker run -d --name tradingagents-mongodb -v tradingagents_mongodb_data:/data/db ...` |
| **验证数据** | `docker exec tradingagents-mongodb mongo tradingagents -u admin -p CHANGE_ME_LOCAL_PASSWORD --authenticationDatabase admin --eval "db.system_configs.find()"` |

**关键点**：
- ✅ 旧数据卷 `tradingagents_mongodb_data` 包含完整的配置数据（15个LLM）
- ✅ 新数据卷 `tradingagents-cn_tradingagents_mongodb_data_v1` 是空的（只有3个LLM）
- 🔧 解决方案：停止容器，使用旧数据卷重新启动
- 📋 建议：统一所有 docker-compose 文件使用相同的数据卷名称

