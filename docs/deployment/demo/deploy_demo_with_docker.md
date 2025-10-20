# 🚀 TradingAgents-CN 演示环境快速部署指南

> 使用 Docker Compose + Nginx 一键部署完整的 AI 股票分析系统

## 📋 目录

- [系统简介](#系统简介)
- [部署架构](#部署架构)
- [前置要求](#前置要求)
- [快速开始](#快速开始)
- [详细步骤](#详细步骤)
- [配置说明](#配置说明)
- [常见问题](#常见问题)
- [进阶配置](#进阶配置)

---

## 🎯 系统简介

**TradingAgents-CN** 是一个基于多智能体架构的 AI 股票分析系统，支持：

- 🤖 **15+ AI 模型**：集成国内外主流大语言模型
- 📊 **多维度分析**：基本面、技术面、情绪面、宏观面分析
- 🔄 **实时数据**：支持 AKShare、Tushare、BaoStock 等数据源
- 🎨 **现代化界面**：Vue 3 + Element Plus 前端
- 🐳 **容器化部署**：Docker + Docker Compose 一键部署

---

## 🏗️ 部署架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Nginx (端口 80)                           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  前端静态资源 (/)                                      │   │
│  │  API 反向代理 (/api → backend:8000)                   │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            ↓
        ┌───────────────────┴───────────────────┐
        ↓                                       ↓
┌──────────────────┐                  ┌──────────────────┐
│  Frontend        │                  │  Backend         │
│  (Vue 3)         │                  │  (FastAPI)       │
│  端口: 3000      │                  │  端口: 8000      │
└──────────────────┘                  └──────────────────┘
                                              ↓
                        ┌─────────────────────┴─────────────────────┐
                        ↓                                           ↓
                ┌──────────────────┐                      ┌──────────────────┐
                │  MongoDB         │                      │  Redis           │
                │  端口: 27017     │                      │  端口: 6379      │
                │  数据持久化      │                      │  缓存加速        │
                └──────────────────┘                      └──────────────────┘
```

**访问方式**：
- 用户只需访问 `http://服务器IP` 即可使用完整系统
- Nginx 自动处理前端页面和 API 请求的路由

---

## ✅ 前置要求

### 硬件要求

| 组件 | 最低配置 | 推荐配置 |
|------|---------|---------|
| CPU | 2 核 | 4 核+ |
| 内存 | 4 GB | 8 GB+ |
| 磁盘 | 20 GB | 50 GB+ |
| 网络 | 10 Mbps | 100 Mbps+ |

### 软件要求

- **操作系统**：Linux (Ubuntu 20.04+, CentOS 7+) / Windows 10+ / macOS
- **Docker**：20.10+ ([安装指南](https://docs.docker.com/engine/install/))
- **Docker Compose**：2.0+ (通常随 Docker 一起安装)

### 验证安装

```bash
# 检查 Docker 版本
docker --version
# 输出示例: Docker version 24.0.7, build afdd53b

# 检查 Docker Compose 版本
docker-compose --version
# 输出示例: Docker Compose version v2.23.0

# 检查 Docker 服务状态
docker ps
# 应该能正常列出容器（即使为空）
```

---

## 🚀 快速开始

### 一键部署（5 分钟）

```bash
# 1. 下载部署文件
wget https://raw.githubusercontent.com/hsliuping/TradingAgents-CN/v1.0.0-preview/docker-compose.hub.nginx.yml

# 2. 下载环境配置文件
wget https://raw.githubusercontent.com/hsliuping/TradingAgents-CN/v1.0.0-preview/.env.docker -O .env

# 3. 下载 Nginx 配置文件
mkdir -p nginx
wget https://raw.githubusercontent.com/hsliuping/TradingAgents-CN/v1.0.0-preview/nginx/nginx.conf -O nginx/nginx.conf

# 4. 下载初始配置数据（可选，包含预配置的 LLM 和示例数据）
mkdir -p install
wget https://github.com/hsliuping/TradingAgents-CN/releases/download/v1.0.0-preview/database_export_config.json -O install/database_export_config.json

# 5. 启动所有服务
docker-compose -f docker-compose.hub.nginx.yml up -d

# 6. 等待服务启动（约 30-60 秒）
docker-compose -f docker-compose.hub.nginx.yml ps

# 7. 导入初始配置（首次部署必须执行）
docker exec -it tradingagents-backend python scripts/import_config_and_create_user.py

# 8. 访问系统
# 浏览器打开: http://你的服务器IP
# 默认账号: admin / admin123
```

---

## 📖 详细步骤

### 步骤 1：准备服务器

#### Linux 服务器

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y  # Ubuntu/Debian
# 或
sudo yum update -y  # CentOS/RHEL

# 安装 Docker
curl -fsSL https://get.docker.com | bash -s docker

# 启动 Docker 服务
sudo systemctl start docker
sudo systemctl enable docker

# 将当前用户添加到 docker 组（避免每次使用 sudo）
sudo usermod -aG docker $USER
# 注销并重新登录以使更改生效
```

#### Windows 服务器

1. 下载并安装 [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)
2. 启动 Docker Desktop
3. 打开 PowerShell（管理员模式）

#### macOS

1. 下载并安装 [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/)
2. 启动 Docker Desktop
3. 打开终端

### 步骤 2：下载部署文件

创建项目目录并下载必要文件：

```bash
# 创建项目目录
mkdir -p ~/tradingagents-demo
cd ~/tradingagents-demo

# 下载 Docker Compose 配置文件
wget https://raw.githubusercontent.com/hsliuping/TradingAgents-CN/v1.0.0-preview/docker-compose.hub.nginx.yml

# 下载环境配置文件
wget https://raw.githubusercontent.com/hsliuping/TradingAgents-CN/v1.0.0-preview/.env.docker -O .env

# 创建 Nginx 配置目录并下载配置文件
mkdir -p nginx
wget https://raw.githubusercontent.com/hsliuping/TradingAgents-CN/v1.0.0-preview/nginx/nginx.conf -O nginx/nginx.conf


```

**Windows PowerShell**：

```powershell
# 创建项目目录
New-Item -ItemType Directory -Path "$env:USERPROFILE\tradingagents-demo" -Force
Set-Location "$env:USERPROFILE\tradingagents-demo"

# 下载文件
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/hsliuping/TradingAgents-CN/v1.0.0-preview/docker-compose.hub.nginx.yml" -OutFile "docker-compose.hub.nginx.yml"
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/hsliuping/TradingAgents-CN/v1.0.0-preview/.env.docker" -OutFile ".env"

# 创建目录并下载配置
New-Item -ItemType Directory -Path "nginx" -Force
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/hsliuping/TradingAgents-CN/v1.0.0-preview/nginx/nginx.conf" -OutFile "nginx\nginx.conf"

```

### 步骤 3：配置 API 密钥（重要）

编辑 `.env` 文件，配置至少一个 AI 模型的 API 密钥：

```bash
# 使用文本编辑器打开
nano .env  # 或 vim .env
```

**必需配置**（至少配置一个）：

```bash
# 阿里百炼（推荐，国产模型，中文优化）
DASHSCOPE_API_KEY=sk-your-dashscope-api-key-here

# 或 DeepSeek（推荐，性价比高）
DEEPSEEK_API_KEY=sk-your-deepseek-api-key-here
DEEPSEEK_ENABLED=true

# 或 OpenAI（需要国外网络）
OPENAI_API_KEY=sk-your-openai-api-key-here
OPENAI_ENABLED=true
```

**可选配置**：

```bash
# Tushare 数据源（专业金融数据，需要注册）
TUSHARE_TOKEN=your-tushare-token-here
TUSHARE_ENABLED=true

# 其他 AI 模型
QIANFAN_API_KEY=your-qianfan-api-key-here  # 百度文心一言
GOOGLE_API_KEY=your-google-api-key-here    # Google Gemini
```

**获取 API 密钥**：

| 服务 | 注册地址 | 说明 |
|------|---------|------|
| 阿里百炼 | https://dashscope.aliyun.com/ | 国产模型，中文优化，推荐 |
| DeepSeek | https://platform.deepseek.com/ | 性价比高，推荐 |
| OpenAI | https://platform.openai.com/ | 需要国外网络 |
| Tushare | https://tushare.pro/register?reg=tacn | 专业金融数据 |

### 步骤 4：启动服务

```bash
# 拉取最新镜像
docker-compose -f docker-compose.hub.nginx.yml pull

# 启动所有服务（后台运行）
docker-compose -f docker-compose.hub.nginx.yml up -d

# 查看服务状态
docker-compose -f docker-compose.hub.nginx.yml ps
```

**预期输出**：

```
NAME                       IMAGE                                    STATUS
tradingagents-backend      hsliup/tradingagents-backend:latest      Up (healthy)
tradingagents-frontend     hsliup/tradingagents-frontend:latest     Up (healthy)
tradingagents-mongodb      mongo:4.4                                Up (healthy)
tradingagents-nginx        nginx:alpine                             Up
tradingagents-redis        redis:7-alpine                           Up (healthy)
```

### 步骤 5：导入初始配置

**首次部署必须执行此步骤**，导入系统配置和创建管理员账号：

```bash
# 导入配置数据（包含 15 个预配置的 LLM 模型和示例数据）
docker exec -it tradingagents-backend python scripts/import_config_and_create_user.py
```

**预期输出**：

```
================================================================================
📦 导入配置数据并创建默认用户
================================================================================

✅ MongoDB 连接成功
✅ 文件加载成功
   导出时间: 2025-10-17T05:50:07
   集合数量: 11

🚀 开始导入...
   ✅ 插入 79 个系统配置
   ✅ 插入 8 个 LLM 提供商
   ✅ 插入 5760 个实时行情数据
   ✅ 插入 5684 个股票基础信息

👤 创建默认管理员用户...
   ✅ 用户创建成功

🔐 登录信息:
   用户名: admin
   密码: admin123
```

### 步骤 6：访问系统

打开浏览器，访问：

```
http://你的服务器IP
```

**默认登录信息**：
- 用户名：`admin`
- 密码：`admin123`

**首次登录后建议**：
1. 修改默认密码
2. 检查 LLM 配置是否正确
3. 测试运行一个简单的分析任务

---

## ⚙️ 配置说明

### 目录结构

```
~/tradingagents-demo/
├── docker-compose.hub.nginx.yml  # Docker Compose 配置文件
├── .env                          # 环境变量配置
├── nginx/
│   └── nginx.conf                # Nginx 配置文件
├── install/
│   └── database_export_config.json  # 初始配置数据
├── logs/                         # 日志目录（自动创建）
├── data/                         # 数据目录（自动创建）
└── config/                       # 配置目录（自动创建）
```

### 端口说明

| 服务 | 容器内端口 | 宿主机端口 | 说明 |
|------|-----------|-----------|------|
| Nginx | 80 | 80 | 统一入口，处理前端和 API |
| Backend | 8000 | - | 内部端口，通过 Nginx 访问 |
| Frontend | 80 | - | 内部端口，通过 Nginx 访问 |
| MongoDB | 27017 | 27017 | 数据库（可选暴露） |
| Redis | 6379 | 6379 | 缓存（可选暴露） |

### 数据持久化

系统使用 Docker Volume 持久化数据：

```bash
# 查看数据卷
docker volume ls | grep tradingagents

# 备份数据卷
docker run --rm -v tradingagents_mongodb_data:/data -v $(pwd):/backup alpine tar czf /backup/mongodb_backup.tar.gz /data

# 恢复数据卷
docker run --rm -v tradingagents_mongodb_data:/data -v $(pwd):/backup alpine tar xzf /backup/mongodb_backup.tar.gz -C /
```

---

## 🔧 常见问题

### 1. 服务启动失败

**问题**：`docker-compose up` 报错

**解决方案**：

```bash
# 查看详细日志
docker-compose -f docker-compose.hub.nginx.yml logs

# 查看特定服务日志
docker-compose -f docker-compose.hub.nginx.yml logs backend

# 重启服务
docker-compose -f docker-compose.hub.nginx.yml restart
```

### 2. 无法访问系统

**问题**：浏览器无法打开 `http://服务器IP`

**检查清单**：

```bash
# 1. 检查服务状态
docker-compose -f docker-compose.hub.nginx.yml ps

# 2. 检查端口占用
sudo netstat -tulpn | grep :80

# 3. 检查防火墙
sudo ufw status  # Ubuntu
sudo firewall-cmd --list-all  # CentOS

# 4. 开放 80 端口
sudo ufw allow 80  # Ubuntu
sudo firewall-cmd --add-port=80/tcp --permanent && sudo firewall-cmd --reload  # CentOS
```

### 3. API 请求失败

**问题**：前端显示"网络错误"或"API 请求失败"

**解决方案**：

```bash
# 检查后端日志
docker logs tradingagents-backend

# 检查 Nginx 日志
docker logs tradingagents-nginx

# 测试后端健康检查
curl http://localhost:8000/api/health
```

### 4. 数据库连接失败

**问题**：后端日志显示"MongoDB connection failed"

**解决方案**：

```bash
# 检查 MongoDB 状态
docker exec -it tradingagents-mongodb mongo -u admin -p tradingagents123 --authenticationDatabase admin

# 重启 MongoDB
docker-compose -f docker-compose.hub.nginx.yml restart mongodb

# 检查数据卷
docker volume inspect tradingagents_mongodb_data
```

### 5. 内存不足

**问题**：系统运行缓慢或容器被杀死

**解决方案**：

```bash
# 查看资源使用情况
docker stats

# 清理未使用的资源
docker system prune -a

# 限制容器内存（编辑 docker-compose.hub.nginx.yml）
services:
  backend:
    deploy:
      resources:
        limits:
          memory: 2G
```

---

## 🎓 进阶配置

### 使用自定义域名

编辑 `nginx/nginx.conf`：

```nginx
server {
    listen 80;
    server_name your-domain.com;  # 修改为你的域名
    
    # ... 其他配置保持不变
}
```

配置 DNS 解析，将域名指向服务器 IP，然后重启 Nginx：

```bash
docker-compose -f docker-compose.hub.nginx.yml restart nginx
```

### 启用 HTTPS

1. 获取 SSL 证书（推荐使用 Let's Encrypt）：

```bash
# 安装 certbot
sudo apt install certbot

# 获取证书
sudo certbot certonly --standalone -d your-domain.com
```

2. 修改 `nginx/nginx.conf`：

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    
    # ... 其他配置
}

# HTTP 重定向到 HTTPS
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}
```

3. 挂载证书目录并重启：

```yaml
# docker-compose.hub.nginx.yml
services:
  nginx:
    volumes:
      - /etc/letsencrypt:/etc/letsencrypt:ro
```

### 性能优化

#### 1. 启用 Redis 持久化

编辑 `docker-compose.hub.nginx.yml`：

```yaml
services:
  redis:
    command: redis-server --appendonly yes --requirepass tradingagents123 --maxmemory 2gb --maxmemory-policy allkeys-lru
```

#### 2. MongoDB 索引优化

```bash
# 进入 MongoDB
docker exec -it tradingagents-mongodb mongo -u admin -p tradingagents123 --authenticationDatabase admin

# 创建索引
use tradingagents
db.market_quotes.createIndex({code: 1, timestamp: -1})
db.stock_basic_info.createIndex({code: 1})
db.analysis_results.createIndex({user_id: 1, created_at: -1})
```

#### 3. 日志轮转

创建 `logrotate` 配置：

```bash
sudo nano /etc/logrotate.d/tradingagents
```

```
/path/to/tradingagents-demo/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
}
```

---

## 📊 监控和维护

### 查看系统状态

```bash
# 查看所有容器状态
docker-compose -f docker-compose.hub.nginx.yml ps

# 查看资源使用
docker stats

# 查看日志
docker-compose -f docker-compose.hub.nginx.yml logs -f --tail=100
```

### 备份数据

```bash
# 导出配置数据
docker exec -it tradingagents-backend python -c "
from app.services.database.backups import export_data
import asyncio
asyncio.run(export_data(
    collections=['system_configs', 'users', 'llm_providers', 'market_quotes', 'stock_basic_info'],
    export_dir='/app/data',
    format='json'
))
"

# 复制备份文件到宿主机
docker cp tradingagents-backend:/app/data/export_*.json ./backup/
```

### 更新系统

```bash
# 拉取最新镜像
docker-compose -f docker-compose.hub.nginx.yml pull

# 重启服务
docker-compose -f docker-compose.hub.nginx.yml up -d
```

### 清理和重置

```bash
# 停止所有服务
docker-compose -f docker-compose.hub.nginx.yml down

# 删除数据卷（⚠️ 会删除所有数据）
docker-compose -f docker-compose.hub.nginx.yml down -v

# 清理未使用的镜像
docker image prune -a
```

---

## 🆘 获取帮助

- **GitHub Issues**: https://github.com/hsliuping/TradingAgents-CN/issues
- **文档**: https://github.com/hsliuping/TradingAgents-CN/tree/v1.0.0-preview/docs
- **示例**: https://github.com/hsliuping/TradingAgents-CN/tree/v1.0.0-preview/examples

---

## 📝 总结

通过本指南，你应该能够：

✅ 在 5 分钟内完成系统部署  
✅ 理解系统架构和组件关系  
✅ 配置 AI 模型和数据源  
✅ 解决常见部署问题  
✅ 进行系统监控和维护  

**下一步**：
1. 探索系统功能，运行第一个股票分析
2. 配置更多 AI 模型，对比分析效果
3. 自定义分析策略和参数
4. 集成到你的投资决策流程

祝你使用愉快！🎉

