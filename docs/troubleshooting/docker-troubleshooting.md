# Docker容器启动失败排查指南

## 🔍 快速排查步骤

### 1. 基础检查

```bash
# 检查容器状态
docker-compose ps -a

# 检查Docker服务
docker version

# 检查系统资源
docker system df
```

### 2. 查看日志

```bash
# 查看所有服务日志
docker-compose logs

# 查看特定服务日志
docker-compose logs web
docker-compose logs mongodb
docker-compose logs redis

# 实时查看日志
docker-compose logs -f web

# 查看最近的日志
docker-compose logs --tail=50 web
```

### 3. 常见问题排查

#### 🔴 端口冲突
```bash
# Windows检查端口占用
netstat -an | findstr :8501
netstat -an | findstr :27017
netstat -an | findstr :6379

# 杀死占用端口的进程
taskkill /PID <进程ID> /F
```

#### 🔴 数据卷问题
```bash
# 查看数据卷
docker volume ls | findstr tradingagents

# 删除有问题的数据卷（会丢失数据）
docker volume rm tradingagents_mongodb_data
docker volume rm tradingagents_redis_data

# 重新创建数据卷
docker volume create tradingagents_mongodb_data
docker volume create tradingagents_redis_data
```

#### 🔴 网络问题
```bash
# 查看网络
docker network ls | findstr tradingagents

# 删除网络
docker network rm tradingagents-network

# 重新创建网络
docker network create tradingagents-network
```

#### 🔴 镜像问题
```bash
# 查看镜像
docker images | findstr tradingagents

# 强制重新构建
docker-compose build --no-cache

# 删除镜像重新构建
docker rmi tradingagents-cn:latest
docker-compose up -d --build
```

### 4. 环境变量检查

```bash
# 检查.env文件是否存在
ls .env

# 检查环境变量
docker-compose config
```

### 5. 磁盘空间检查

```bash
# 检查Docker磁盘使用
docker system df

# 清理无用资源
docker system prune -f

# 清理所有未使用资源（谨慎使用）
docker system prune -a -f
```

## 🛠️ 具体服务排查

### Web服务 (Streamlit)
```bash
# 查看Web服务日志
docker-compose logs web

# 进入容器调试
docker-compose exec web bash

# 检查Python环境
docker-compose exec web python --version
docker-compose exec web pip list
```

### MongoDB服务
```bash
# 查看MongoDB日志
docker-compose logs mongodb

# 连接MongoDB测试
docker-compose exec mongodb mongo -u admin -p CHANGE_ME_LOCAL_PASSWORD

# 检查数据库状态
docker-compose exec mongodb mongo --eval "db.adminCommand('ping')"
```

### Redis服务
```bash
# 查看Redis日志
docker-compose logs redis

# 连接Redis测试
docker-compose exec redis redis-cli -a CHANGE_ME_LOCAL_PASSWORD

# 检查Redis状态
docker-compose exec redis redis-cli -a CHANGE_ME_LOCAL_PASSWORD ping
```

## 🚨 紧急修复命令

### 完全重置（会丢失数据）
```bash
# 停止所有容器
docker-compose down

# 删除所有相关资源
docker-compose down -v --remove-orphans

# 清理系统
docker system prune -f

# 重新启动
docker-compose up -d --build
```

### 保留数据重启
```bash
# 停止容器
docker-compose down

# 重新启动
docker-compose up -d
```

## 📝 日志分析技巧

### 常见错误模式

1. **端口占用**: `bind: address already in use`
2. **权限问题**: `permission denied`
3. **磁盘空间**: `no space left on device`
4. **内存不足**: `out of memory`
5. **网络问题**: `network not found`
6. **镜像问题**: `image not found`

### 日志过滤
```bash
# 只看错误日志
docker-compose logs | findstr ERROR

# 只看警告日志
docker-compose logs | findstr WARN

# 查看特定时间段日志
docker-compose logs --since="2025-01-01T00:00:00"
```

## 🔧 预防措施

1. **定期清理**: `docker system prune -f`
2. **监控资源**: `docker system df`
3. **备份数据**: 定期备份数据卷
4. **版本控制**: 记录工作的配置版本
5. **健康检查**: 配置容器健康检查

## 📞 获取帮助

如果以上方法都无法解决问题，请：

1. 收集完整的错误日志
2. 记录系统环境信息
3. 描述具体的操作步骤
4. 提供docker-compose.yml配置