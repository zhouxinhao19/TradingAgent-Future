# TradingAgents-CN Docker 快速开始

使用Docker快速部署TradingAgents-CN v1.0.0-preview版本。

## 📦 Docker镜像

- **后端**: `hsliup/tradingagents-backend:latest`
- **前端**: `hsliup/tradingagents-frontend:latest`

## 🚀 三步部署

### 1. 下载配置文件

```bash
# 下载docker-compose配置
wget https://raw.githubusercontent.com/hsliuping/TradingAgents-CN/v1.0.0-preview/docker-compose.hub.yml

# 下载环境变量模板
wget https://raw.githubusercontent.com/hsliuping/TradingAgents-CN/v1.0.0-preview/.env.example -O .env
```

### 2. 配置环境变量

编辑`.env`文件，配置必要的API密钥：

```bash
nano .env
```

最少需要配置：
```env
# JWT密钥（必需，请修改为随机字符串）
JWT_SECRET=your-random-secret-key-here

# 至少配置一个AI服务的API密钥
OPENAI_API_KEY=sk-...
# 或
DEEPSEEK_API_KEY=sk-...
# 或
DASHSCOPE_API_KEY=sk-...
```

### 3. 启动服务

```bash
docker-compose -f docker-compose.hub.yml up -d
```

等待1-2分钟后访问：
- **前端**: http://localhost:3000
- **后端API**: http://localhost:8000
- **API文档**: http://localhost:8000/docs

## 📝 常用命令

```bash
# 查看服务状态
docker-compose -f docker-compose.hub.yml ps

# 查看日志
docker-compose -f docker-compose.hub.yml logs -f

# 停止服务
docker-compose -f docker-compose.hub.yml down

# 更新镜像
docker-compose -f docker-compose.hub.yml pull
docker-compose -f docker-compose.hub.yml up -d
```

## 🔧 故障排除

### 查看后端日志
```bash
docker logs -f tradingagents-backend
```

### 查看前端日志
```bash
docker logs -f tradingagents-frontend
```

### 重启服务
```bash
docker-compose -f docker-compose.hub.yml restart
```

## 📚 完整文档

详细文档请参考：
- [Docker发布指南](docs/DOCKER_PUBLISH_GUIDE.md)
- [Linux构建指南](docs/LINUX_BUILD_GUIDE.md)
- [项目主页](https://github.com/hsliuping/TradingAgents-CN)

