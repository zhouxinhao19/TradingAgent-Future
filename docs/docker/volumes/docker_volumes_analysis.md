# Docker 数据卷分析

## 📊 当前数据卷列表

根据 `docker volume ls` 的输出，系统中存在以下数据卷：

### MongoDB 数据卷

| 卷名 | 创建时间 | 项目 | 状态 |
|------|---------|------|------|
| `tradingagents-cn_tradingagents_mongodb_data_v1` | 2025-10-16 | tradingagents-cn | ✅ **正在使用** |
| `tradingagents_mongodb_data` | 2025-08-24 | tradingagentscn | ⚠️ 旧版本 |
| `tradingagents_mongodb_data_v1` | - | - | ⚠️ 未使用 |

### Redis 数据卷

| 卷名 | 创建时间 | 项目 | 状态 |
|------|---------|------|------|
| `tradingagents-cn_tradingagents_redis_data_v1` | - | tradingagents-cn | ✅ **正在使用** |
| `tradingagents_redis_data` | - | tradingagentscn | ⚠️ 旧版本 |
| `tradingagents_redis_data_v1` | - | - | ⚠️ 未使用 |

### 匿名数据卷

| 卷名 | 状态 |
|------|------|
| `7c8099091274da4fa7146ad0fb8ff2dbc9a5d77f06e23326cb18554edd2fe2fc` | ⚠️ 未使用 |
| `17cd87e8d52dbbae4df8edf59377e1b47b3a0144656d8fa5dac4e6f384c4be87` | ⚠️ 未使用 |
| `52f90bc01c6f02f51d4b54a00a830c404b5d8a7c06fbcd2c659bc3ffc95d30bd` | ⚠️ 未使用 |
| `971e629ccc222ec52bc14d178028eca40dbc54fa6c982e635d4c29d8cd5115c0` | ⚠️ 未使用 |
| `3501485e5d3a64e358d92e95fd72b9aec155728af37f46b0e3d7e576fce42e3b` | ⚠️ 未使用 |
| `056359556bb7e838a50cd74b2f7b494fbe7e9037f9967bfaee1d36123da5d1fd` | ⚠️ 未使用 |
| `a2f485bc38d1ff40b9d65b9a6fe2db302bdc8ec10beb15486bee69251579b3fb` | ⚠️ 未使用 |
| `a5be791ebe5612f3fe19e25d6e1ccc49999ee14f843bf64ea3c0400e5634341b` | ⚠️ 未使用 |
| `c58638ecd38414411e493d540727fb5ade66cb8595fc40bee5bdb42d83e59189` | ⚠️ 未使用 |
| `d1ff647e427f348e304f97565635ddc0d3031a5191616b338cb6eb3fd2453513` | ⚠️ 未使用 |
| `fcd68caf0fa26674712705ef9cf4407f2835d54a18cd5d9fbc3aa78f3668da28` | ✅ **正在使用** (MongoDB 绑定挂载) |

---

## 🔍 当前正在使用的数据卷

### 1️⃣ MongoDB 容器 (`tradingagents-mongodb`)

**容器状态**：✅ Up 4 hours (healthy)

**挂载的数据卷**：
```
Type: volume
Name: tradingagents-cn_tradingagents_mongodb_data_v1
Source: /var/lib/docker/volumes/tradingagents-cn_tradingagents_mongodb_data_v1/_data
```

**详细信息**：
```json
{
  "CreatedAt": "2025-10-16T01:04:44Z",
  "Driver": "local",
  "Labels": {
    "com.docker.compose.project": "tradingagents-cn",
    "com.docker.compose.volume": "tradingagents_mongodb_data_v1"
  },
  "Name": "tradingagents-cn_tradingagents_mongodb_data_v1"
}
```

---

### 2️⃣ Redis 容器 (`tradingagents-redis`)

**容器状态**：✅ Up 4 hours (healthy)

**挂载的数据卷**：
```
Type: volume
Name: tradingagents-cn_tradingagents_redis_data_v1
Source: /var/lib/docker/volumes/tradingagents-cn_tradingagents_redis_data_v1/_data
```

---

## 📋 docker-compose.yml 配置

当前 `docker-compose.yml` 中定义的数据卷：

```yaml
volumes:
  mongodb_data:
    driver: local
    name: tradingagents_mongodb_data
  redis_data:
    driver: local
    name: tradingagents_redis_data
```

**实际使用的数据卷名称**：
- MongoDB: `tradingagents-cn_tradingagents_mongodb_data_v1`
- Redis: `tradingagents-cn_tradingagents_redis_data_v1`

**差异原因**：
- Docker Compose 会在卷名前添加项目名称前缀（`tradingagents-cn_`）
- 实际使用的卷名包含 `_v1` 后缀

---

## 🗑️ 可以清理的数据卷

### 旧版本数据卷（可以删除）

这些数据卷来自旧的 Docker Compose 项目（`tradingagentscn`），已不再使用：

```bash
# MongoDB 旧数据卷
docker volume rm tradingagents_mongodb_data

# Redis 旧数据卷
docker volume rm tradingagents_redis_data
```

### 未使用的版本数据卷（可以删除）

```bash
docker volume rm tradingagents_mongodb_data_v1
docker volume rm tradingagents_redis_data_v1
```

### 匿名数据卷（可以删除）

这些是未命名的数据卷，通常是容器删除后遗留的：

```bash
# 删除所有未使用的匿名数据卷
docker volume prune -f
```

---

## 🔧 清理脚本

### 方法 1：手动清理（推荐）

```bash
# 1. 停止所有容器
docker-compose down

# 2. 删除旧版本数据卷
docker volume rm tradingagents_mongodb_data
docker volume rm tradingagents_redis_data
docker volume rm tradingagents_mongodb_data_v1
docker volume rm tradingagents_redis_data_v1

# 3. 删除所有未使用的匿名数据卷
docker volume prune -f

# 4. 重新启动容器
docker-compose up -d
```

### 方法 2：自动清理（谨慎使用）

```bash
# 删除所有未使用的数据卷（包括匿名卷）
docker volume prune -a -f
```

⚠️ **警告**：`docker volume prune -a` 会删除所有未被容器使用的数据卷，包括可能有用的数据卷！

---

## 📊 清理前后对比

### 清理前（16 个数据卷）

```
MongoDB 数据卷: 3 个
Redis 数据卷: 3 个
匿名数据卷: 10 个
总计: 16 个
```

### 清理后（2 个数据卷）

```
MongoDB 数据卷: 1 个 (tradingagents-cn_tradingagents_mongodb_data_v1)
Redis 数据卷: 1 个 (tradingagents-cn_tradingagents_redis_data_v1)
总计: 2 个
```

---

## 🎯 推荐操作

### 立即执行

1. **确认当前正在使用的数据卷**：
   ```bash
   docker inspect tradingagents-mongodb --format='{{json .Mounts}}' | ConvertFrom-Json
   docker inspect tradingagents-redis --format='{{json .Mounts}}' | ConvertFrom-Json
   ```

2. **备份重要数据**（可选）：
   ```bash
   # 导出 MongoDB 数据
   docker exec tradingagents-mongodb mongodump --out /tmp/backup
   docker cp tradingagents-mongodb:/tmp/backup ./mongodb_backup
   ```

3. **清理未使用的数据卷**：
   ```bash
   # 删除旧版本数据卷
   docker volume rm tradingagents_mongodb_data tradingagents_redis_data
   docker volume rm tradingagents_mongodb_data_v1 tradingagents_redis_data_v1
   
   # 删除匿名数据卷
   docker volume prune -f
   ```

4. **验证清理结果**：
   ```bash
   docker volume ls
   ```

---

## ✅ 总结

| 问题 | 答案 |
|------|------|
| **正在使用的 MongoDB 数据卷** | `tradingagents-cn_tradingagents_mongodb_data_v1` |
| **正在使用的 Redis 数据卷** | `tradingagents-cn_tradingagents_redis_data_v1` |
| **可以删除的数据卷** | 4 个旧版本数据卷 + 10 个匿名数据卷 |
| **清理后的数据卷数量** | 2 个（MongoDB + Redis） |
| **是否需要备份** | 建议备份 MongoDB 数据 |

**关键点**：
- ✅ 当前正在使用：`tradingagents-cn_tradingagents_mongodb_data_v1` 和 `tradingagents-cn_tradingagents_redis_data_v1`
- ⚠️ 旧版本数据卷可以安全删除
- 🗑️ 匿名数据卷可以使用 `docker volume prune` 清理
- 💾 建议在清理前备份 MongoDB 数据

---

## 🔍 如何查看数据卷内容

### 查看 MongoDB 数据卷

```bash
# 进入 MongoDB 容器
docker exec -it tradingagents-mongodb bash

# 查看数据目录
ls -lh /data/db

# 连接 MongoDB
mongosh -u admin -p CHANGE_ME_LOCAL_PASSWORD --authenticationDatabase admin

# 查看数据库
show dbs
use tradingagents
show collections
```

### 查看 Redis 数据卷

```bash
# 进入 Redis 容器
docker exec -it tradingagents-redis sh

# 查看数据目录
ls -lh /data

# 连接 Redis
redis-cli -a CHANGE_ME_LOCAL_PASSWORD

# 查看键
KEYS *
```

---

## 📝 注意事项

1. **不要删除正在使用的数据卷**：
   - `tradingagents-cn_tradingagents_mongodb_data_v1`
   - `tradingagents-cn_tradingagents_redis_data_v1`

2. **备份重要数据**：
   - 在删除旧数据卷前，确认其中没有重要数据
   - 建议先备份 MongoDB 数据

3. **停止容器后再清理**：
   - 使用 `docker-compose down` 停止所有容器
   - 清理完成后使用 `docker-compose up -d` 重新启动

4. **验证清理结果**：
   - 清理后检查容器是否正常运行
   - 检查数据是否完整

