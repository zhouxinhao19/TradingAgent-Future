#!/bin/bash
# TradingAgents Docker服务启动脚本
# 启动MongoDB、Redis和Redis Commander

echo "========================================"
echo "TradingAgents Docker服务启动脚本"
echo "========================================"

# 检查Docker是否运行
echo "检查Docker服务状态..."
if ! docker version >/dev/null 2>&1; then
    echo "❌ Docker未运行或未安装，请先启动Docker"
    exit 1
fi
echo "✅ Docker服务正常"

echo ""
echo "🚀 启动数据库服务..."

# 启动MongoDB
echo "📊 启动MongoDB..."
docker run -d \
    --name tradingagents-mongodb \
    -p 27017:27017 \
    -e MONGO_INITDB_ROOT_USERNAME=admin \
    -e MONGO_INITDB_ROOT_PASSWORD=CHANGE_ME_LOCAL_PASSWORD \
    -e MONGO_INITDB_DATABASE=tradingagents \
    -v mongodb_data:/data/db \
    --restart unless-stopped \
    mongo:4.4

if [ $? -eq 0 ]; then
    echo "✅ MongoDB启动成功 - 端口: 27017"
else
    echo "⚠️ MongoDB可能已在运行或启动失败"
fi

# 启动Redis
echo "📦 启动Redis..."
docker run -d \
    --name tradingagents-redis \
    -p 6379:6379 \
    -v redis_data:/data \
    --restart unless-stopped \
    redis:latest redis-server --appendonly yes --requirepass CHANGE_ME_LOCAL_PASSWORD

if [ $? -eq 0 ]; then
    echo "✅ Redis启动成功 - 端口: 6379"
else
    echo "⚠️ Redis可能已在运行或启动失败"
fi

# 等待服务启动
echo "⏳ 等待服务启动..."
sleep 5

# 启动Redis Commander (可选的Redis管理界面)
echo "🖥️ 启动Redis Commander..."
docker run -d \
    --name tradingagents-redis-commander \
    -p 8081:8081 \
    -e REDIS_HOSTS=local:tradingagents-redis:6379:0:CHANGE_ME_LOCAL_PASSWORD \
    --link tradingagents-redis:redis \
    --restart unless-stopped \
    rediscommander/redis-commander:latest

if [ $? -eq 0 ]; then
    echo "✅ Redis Commander启动成功 - 访问地址: http://localhost:8081"
else
    echo "⚠️ Redis Commander可能已在运行或启动失败"
fi

echo ""
echo "📋 服务状态检查..."
docker ps --filter "name=tradingagents-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo ""
echo "========================================"
echo "🎉 Docker服务启动完成！"
echo "========================================"
echo ""
echo "📊 MongoDB:"
echo "   - 连接地址: mongodb://admin:CHANGE_ME_LOCAL_PASSWORD@localhost:27017/tradingagents"
echo "   - 端口: 27017"
echo "   - 用户名: admin"
echo "   - 密码: CHANGE_ME_LOCAL_PASSWORD"
echo ""
echo "📦 Redis:"
echo "   - 连接地址: redis://localhost:6379"
echo "   - 端口: 6379"
echo "   - 密码: CHANGE_ME_LOCAL_PASSWORD"
echo ""
echo "🖥️ Redis Commander:"
echo "   - 管理界面: http://localhost:8081"
echo ""
echo "💡 提示:"
echo "   - 使用 ./stop_docker_services.sh 停止所有服务"
echo "   - 使用 docker logs [容器名] 查看日志"
echo "   - 数据将持久化保存在Docker卷中"
echo ""
