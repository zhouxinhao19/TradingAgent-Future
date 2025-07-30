#!/bin/bash
# Docker启动脚本 - 智能选择是否需要构建

echo "=== TradingAgents Docker 启动脚本 ==="

# 检查是否有镜像
if docker images | grep -q "tradingagents-cn"; then
    echo "✅ 发现现有镜像"
    
    # 检查代码是否有变化
    if git diff --quiet HEAD~1 HEAD -- . ':!*.md' ':!docs/' ':!scripts/'; then
        echo "📦 代码无变化，使用快速启动"
        docker-compose up -d
    else
        echo "🔄 检测到代码变化，重新构建"
        docker-compose up -d --build
    fi
else
    echo "🏗️ 首次运行，构建镜像"
    docker-compose up -d --build
fi

echo "🚀 启动完成！"
echo "Web界面: http://localhost:8501"
echo "Redis管理: http://localhost:8081"