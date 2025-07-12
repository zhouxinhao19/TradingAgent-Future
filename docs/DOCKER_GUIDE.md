# 🐳 TradingAgents-CN Docker 部署指南

## 📋 概述

本指南介绍如何使用Docker部署TradingAgents-CN，包括完整的服务栈：Web应用、MongoDB数据库、Redis缓存以及管理界面。

## 🎯 Docker部署优势

- ✅ **一键部署**: 无需手动安装依赖
- ✅ **环境隔离**: 避免环境冲突
- ✅ **服务编排**: 自动管理数据库和缓存
- ✅ **易于扩展**: 支持水平扩展
- ✅ **生产就绪**: 包含健康检查和数据持久化

## 🛠️ 前置要求

### 系统要求
- Docker Desktop 4.0+ 
- Docker Compose 2.0+
- 至少 4GB 可用内存
- 至少 10GB 可用磁盘空间

### 检查Docker环境
```bash
# 检查Docker版本
docker --version
docker-compose --version

# 检查Docker是否运行
docker info
```

## 🚀 快速开始

### 1. 克隆项目
```bash
git clone https://github.com/hsliuping/TradingAgents.git
cd TradingAgents
```

### 2. 配置环境变量
```bash
# 复制环境变量模板
cp .env.example .env

# 编辑配置文件
# Windows: notepad .env
# Linux/macOS: nano .env
```

### 3. Docker环境配置
在 `.env` 文件中修改以下配置：

```bash
# 启用数据库
MONGODB_ENABLED=true
REDIS_ENABLED=true

# Docker服务主机名
MONGODB_HOST=mongodb
REDIS_HOST=redis

# 数据库端口（Docker默认端口）
MONGODB_PORT=27017
REDIS_PORT=6379

# 至少配置一个LLM API密钥
TRADINGAGENTS_DEEPSEEK_API_KEY=your_deepseek_api_key
# 或者
TRADINGAGENTS_DASHSCOPE_API_KEY=your_dashscope_api_key
```

### 4. 构建和启动服务
```bash
# 构建应用镜像
docker build -t tradingagents-cn .

# 启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps
```

### 5. 访问应用
- **Web应用**: http://localhost:8501
- **Redis管理界面**: http://localhost:8081
- **MongoDB管理界面**: http://localhost:8082

## 📊 服务架构

### 服务组件
```
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   Web应用       │  │   MongoDB       │  │   Redis         │
│  (端口: 8501)   │  │  (端口: 27017)  │  │  (端口: 6379)   │
└─────────────────┘  └─────────────────┘  └─────────────────┘
         │                     │                     │
         └─────────────────────┼─────────────────────┘
                               │
┌─────────────────┐  ┌─────────────────┐
│ Redis Commander │  │  Mongo Express  │
│  (端口: 8081)   │  │  (端口: 8082)   │
└─────────────────┘  └─────────────────┘
```

### 数据持久化
- **MongoDB数据**: `tradingagents_mongodb_data` 卷
- **Redis数据**: `tradingagents_redis_data` 卷

## 🔧 常用命令

### 服务管理
```bash
# 启动所有服务
docker-compose up -d

# 停止所有服务
docker-compose down

# 重启服务
docker-compose restart

# 查看服务状态
docker-compose ps

# 查看服务日志
docker-compose logs web
docker-compose logs mongodb
docker-compose logs redis
```

### 数据管理
```bash
# 备份MongoDB数据
docker exec tradingagents-mongodb mongodump --out /backup

# 备份Redis数据
docker exec tradingagents-redis redis-cli BGSAVE

# 清理数据卷（谨慎使用）
docker-compose down -v
```

### 镜像管理
```bash
# 重新构建应用镜像
docker-compose build web

# 拉取最新基础镜像
docker-compose pull

# 清理未使用的镜像
docker image prune
```

## 🐛 故障排除

### 常见问题

#### 1. 端口冲突
**问题**: 端口已被占用
```
Error: bind: address already in use
```

**解决方案**: 修改 `docker-compose.yml` 中的端口映射
```yaml
ports:
  - "8502:8501"  # 改为其他端口
```

#### 2. 内存不足
**问题**: 容器启动失败
```
Error: cannot allocate memory
```

**解决方案**: 增加Docker内存限制或关闭其他应用

#### 3. 数据库连接失败
**问题**: Web应用无法连接数据库

**解决方案**: 检查 `.env` 配置
```bash
# 确保使用Docker服务名
MONGODB_HOST=mongodb
REDIS_HOST=redis
```

#### 4. 权限问题
**问题**: 文件权限错误

**解决方案**: 
```bash
# Linux/macOS
sudo chown -R $USER:$USER .

# Windows
# 在Docker Desktop中启用文件共享
```

### 调试命令
```bash
# 进入Web应用容器
docker exec -it TradingAgents-web bash

# 查看容器内环境变量
docker exec TradingAgents-web env

# 测试数据库连接
docker exec TradingAgents-web python -c "
from tradingagents.utils.database import test_connections
test_connections()
"
```

## 🔒 安全配置

### 生产环境建议
1. **修改默认密码**
```bash
# 在.env中修改
MONGODB_PASSWORD=your_secure_password
REDIS_PASSWORD=your_secure_password
```

2. **限制网络访问**
```yaml
# 在docker-compose.yml中
ports:
  - "127.0.0.1:8501:8501"  # 只允许本地访问
```

3. **启用SSL/TLS**
```yaml
# 添加SSL证书卷映射
volumes:
  - ./ssl:/app/ssl
```

## 📈 性能优化

### 资源限制
```yaml
# 在docker-compose.yml中添加
services:
  web:
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '1.0'
        reservations:
          memory: 1G
          cpus: '0.5'
```

### 缓存优化
```bash
# 在.env中配置
TRADINGAGENTS_CACHE_TTL=7200  # 增加缓存时间
TRADINGAGENTS_MAX_WORKERS=8   # 增加工作线程
```

## 🔄 更新和维护

### 更新应用
```bash
# 拉取最新代码
git pull origin main

# 重新构建镜像
docker-compose build web

# 重启服务
docker-compose up -d
```

### 定期维护
```bash
# 清理日志
docker system prune

# 备份数据
./scripts/backup-docker-data.sh

# 监控资源使用
docker stats
```

## 📞 技术支持

如果遇到问题，请：
1. 查看 [故障排除](#故障排除) 部分
2. 检查 [GitHub Issues](https://github.com/hsliuping/TradingAgents/issues)
3. 提交新的Issue并附上日志信息

---

**祝您使用愉快！** 🎉
