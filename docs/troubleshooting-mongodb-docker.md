# MongoDB Docker 连接问题排查指南

## 🔍 问题描述

在 Docker 环境中启动应用时，出现 MongoDB 认证失败错误：

```
❌ MongoDB: MongoDB连接失败: Authentication failed.
```

## 📋 常见原因

### 1. 用户名/密码不匹配

**问题**：应用配置的用户名/密码与 MongoDB 实际用户不匹配。

**检查方法**：
```bash
# 1. 查看 Docker Compose 配置
cat docker-compose.hub.nginx.yml | grep MONGODB

# 2. 进入 MongoDB 容器检查用户（MongoDB 4.4 使用 mongo 命令）
docker exec -it tradingagents-mongodb mongo -u admin -p CHANGE_ME_LOCAL_PASSWORD --authenticationDatabase admin

# 3. 在 mongo shell 中查看用户
use admin
db.getUsers()
```

**解决方案**：
- 确保 `MONGODB_USERNAME` 和 `MONGODB_PASSWORD` 与 MongoDB 中的用户匹配
- 确保 `MONGODB_AUTH_SOURCE` 设置正确（通常是 `admin`）

### 2. MongoDB 初始化脚本未执行

**问题**：MongoDB 容器首次启动时，初始化脚本没有正确执行。

**检查方法**：
```bash
# 查看 MongoDB 容器日志
docker logs tradingagents-mongodb | grep "mongo-init.js"
```

**解决方案**：
```bash
# 1. 停止并删除容器和卷
docker-compose -f docker-compose.hub.nginx.yml down -v

# 2. 重新启动（会重新执行初始化脚本）
docker-compose -f docker-compose.hub.nginx.yml up -d
```

### 3. authSource 配置错误

**问题**：连接字符串中的 `authSource` 参数不正确。

**正确配置**：
```bash
# 使用 root 用户（admin 数据库）
mongodb://admin:CHANGE_ME_LOCAL_PASSWORD@mongodb:27017/tradingagents?authSource=admin

# 使用应用用户（tradingagents 数据库）
mongodb://tradingagents:CHANGE_ME_LOCAL_PASSWORD@mongodb:27017/tradingagents?authSource=admin
```

**注意**：
- `authSource` 指定**验证用户的数据库**，不是目标数据库
- root 用户在 `admin` 数据库中验证
- 应用用户也在 `admin` 数据库中验证（由初始化脚本创建）

### 4. Docker 网络问题

**问题**：应用容器无法连接到 MongoDB 容器。

**检查方法**：
```bash
# 1. 检查容器是否在同一网络
docker network inspect tradingagents-network

# 2. 从应用容器 ping MongoDB 容器
docker exec -it tradingagents-backend ping mongodb

# 3. 测试端口连接
docker exec -it tradingagents-backend nc -zv mongodb 27017
```

**解决方案**：
- 确保所有容器都在 `tradingagents-network` 网络中
- 使用服务名（`mongodb`）而不是 IP 地址

## 🛠️ 排查步骤

### 步骤 1：运行调试脚本

在服务器上运行调试脚本：

```bash
# 进入应用容器
docker exec -it tradingagents-backend bash

# 运行调试脚本
python3 scripts/debug_mongodb_connection.py
```

### 步骤 2：检查 MongoDB 容器状态

```bash
# 查看容器状态
docker ps | grep mongo

# 查看容器日志
docker logs tradingagents-mongodb --tail 100

# 检查健康状态
docker inspect tradingagents-mongodb | grep -A 10 Health
```

### 步骤 3：手动测试连接

```bash
# 方法 1：使用 mongo shell（MongoDB 4.4）
docker exec -it tradingagents-mongodb mongo -u admin -p CHANGE_ME_LOCAL_PASSWORD --authenticationDatabase admin

# 方法 2：使用 Python
docker exec -it tradingagents-backend python3 -c "
from pymongo import MongoClient
client = MongoClient('mongodb://admin:CHANGE_ME_LOCAL_PASSWORD@mongodb:27017/tradingagents?authSource=admin')
print(client.server_info())
"
```

### 步骤 4：检查环境变量

```bash
# 查看应用容器的环境变量
docker exec -it tradingagents-backend env | grep MONGODB
```

## ✅ 推荐配置

### 使用 Root 用户（推荐，简单）

**docker-compose.hub.nginx.yml**：
```yaml
environment:
  MONGODB_HOST: "mongodb"
  MONGODB_PORT: "27017"
  MONGODB_USERNAME: "admin"
  MONGODB_PASSWORD: "CHANGE_ME_LOCAL_PASSWORD"
  MONGODB_DATABASE: "tradingagents"
  MONGODB_AUTH_SOURCE: "admin"
  MONGODB_CONNECTION_STRING: "mongodb://admin:CHANGE_ME_LOCAL_PASSWORD@mongodb:27017/tradingagents?authSource=admin"
```

**优点**：
- 配置简单
- 不需要额外创建用户
- 适合开发和测试环境

**缺点**：
- 使用 root 权限，安全性较低
- 生产环境建议使用专用用户

### 使用应用用户（推荐，安全）

**docker-compose.hub.nginx.yml**：
```yaml
environment:
  MONGODB_HOST: "mongodb"
  MONGODB_PORT: "27017"
  MONGODB_USERNAME: "tradingagents"
  MONGODB_PASSWORD: "CHANGE_ME_LOCAL_PASSWORD"
  MONGODB_DATABASE: "tradingagents"
  MONGODB_AUTH_SOURCE: "admin"
  MONGODB_CONNECTION_STRING: "mongodb://tradingagents:CHANGE_ME_LOCAL_PASSWORD@mongodb:27017/tradingagents?authSource=admin"
```

**优点**：
- 最小权限原则
- 更安全
- 适合生产环境

**前提**：
- 确保 `scripts/mongo-init.js` 已正确执行
- 用户 `tradingagents` 已创建

## 🔧 快速修复

### 方案 1：重置 MongoDB（推荐）

```bash
# 1. 停止所有容器
docker-compose -f docker-compose.hub.nginx.yml down

# 2. 删除 MongoDB 数据卷
docker volume rm tradingagents_mongodb_data

# 3. 重新启动
docker-compose -f docker-compose.hub.nginx.yml up -d

# 4. 查看日志
docker logs -f tradingagents-backend
```

### 方案 2：手动创建用户

```bash
# 1. 进入 MongoDB 容器（MongoDB 4.4 使用 mongo 命令）
docker exec -it tradingagents-mongodb mongo -u admin -p CHANGE_ME_LOCAL_PASSWORD --authenticationDatabase admin

# 2. 创建应用用户
use admin
db.createUser({
  user: 'tradingagents',
  pwd: 'CHANGE_ME_LOCAL_PASSWORD',
  roles: [
    { role: 'readWrite', db: 'tradingagents' }
  ]
})

# 3. 验证用户
db.auth('tradingagents', 'CHANGE_ME_LOCAL_PASSWORD')

# 4. 退出并重启应用容器
exit
docker restart tradingagents-backend
```

### 方案 3：修改配置使用 Root 用户

```bash
# 1. 编辑 docker-compose.hub.nginx.yml
# 确保使用 admin 用户和 authSource=admin

# 2. 重启应用容器
docker-compose -f docker-compose.hub.nginx.yml restart backend

# 3. 查看日志
docker logs -f tradingagents-backend
```

## 📝 验证修复

修复后，应该看到以下日志：

```
✅ MongoDB: MongoDB连接成功
✅ Redis: Redis连接成功
主要缓存后端: mongodb
MongoDB客户端初始化成功
数据库管理器初始化完成 - MongoDB: True, Redis: True
```

## 🚨 注意事项

1. **生产环境**：
   - 修改默认密码
   - 使用专用应用用户
   - 启用 SSL/TLS
   - 限制网络访问

2. **数据备份**：
   - 定期备份 MongoDB 数据
   - 使用 `docker volume` 持久化数据

3. **安全性**：
   - 不要在代码中硬编码密码
   - 使用 `.env` 文件管理敏感信息
   - 不要将 `.env` 文件提交到 Git

## 📚 参考资料

- [MongoDB Docker 官方文档](https://hub.docker.com/_/mongo)
- [MongoDB 认证文档](https://docs.mongodb.com/manual/core/authentication/)
- [Docker Compose 网络文档](https://docs.docker.com/compose/networking/)

