#!/bin/bash
# TradingAgents-CN Docker镜像构建和发布脚本（Linux服务器版）
# 使用方法: ./scripts/build-and-publish-linux.sh <dockerhub-username>

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 参数检查
if [ $# -lt 1 ]; then
    echo -e "${RED}错误: 缺少必需参数${NC}"
    echo "使用方法: $0 <dockerhub-username> [version]"
    echo "示例: $0 myusername v1.0.0-preview"
    exit 1
fi

DOCKERHUB_USERNAME=$1
VERSION=${2:-"v1.0.0-preview"}

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}TradingAgents-CN Docker构建和发布${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""
echo -e "${BLUE}Docker Hub用户名: ${DOCKERHUB_USERNAME}${NC}"
echo -e "${BLUE}版本: ${VERSION}${NC}"
echo ""

# 配置
BACKEND_IMAGE_LOCAL="tradingagents-backend:$VERSION"
FRONTEND_IMAGE_LOCAL="tradingagents-frontend:$VERSION"
BACKEND_IMAGE_REMOTE="$DOCKERHUB_USERNAME/tradingagents-backend"
FRONTEND_IMAGE_REMOTE="$DOCKERHUB_USERNAME/tradingagents-frontend"

# 步骤1: 检查环境
echo -e "${YELLOW}步骤1: 检查环境...${NC}"

# 检查Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker未安装！${NC}"
    echo "请先安装Docker: sudo apt-get install docker.io"
    exit 1
fi
echo -e "${GREEN}  ✅ Docker已安装: $(docker --version)${NC}"

# 检查Git
if ! command -v git &> /dev/null; then
    echo -e "${RED}❌ Git未安装！${NC}"
    echo "请先安装Git: sudo apt-get install git"
    exit 1
fi
echo -e "${GREEN}  ✅ Git已安装: $(git --version)${NC}"

# 检查是否在正确的目录
if [ ! -f "pyproject.toml" ] || [ ! -f "Dockerfile.backend" ]; then
    echo -e "${RED}❌ 请在项目根目录运行此脚本！${NC}"
    exit 1
fi
echo -e "${GREEN}  ✅ 当前目录正确${NC}"

# 检查Git分支（可选）
if git rev-parse --git-dir > /dev/null 2>&1; then
    CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
    echo -e "${BLUE}  当前分支: ${CURRENT_BRANCH}${NC}"
else
    echo -e "${YELLOW}  ⚠️  不是Git仓库，跳过分支检查${NC}"
fi

echo ""

# 步骤2: 清理旧镜像（可选）
echo -e "${YELLOW}步骤2: 清理旧镜像...${NC}"
read -p "是否清理旧的本地镜像？(y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    docker rmi -f $BACKEND_IMAGE_LOCAL 2>/dev/null || true
    docker rmi -f $FRONTEND_IMAGE_LOCAL 2>/dev/null || true
    echo -e "${GREEN}  ✅ 旧镜像已清理${NC}"
else
    echo -e "${BLUE}  跳过清理${NC}"
fi
echo ""

# 步骤3: 构建后端镜像
echo -e "${YELLOW}步骤3: 构建后端镜像...${NC}"
echo -e "${CYAN}  镜像名称: ${BACKEND_IMAGE_LOCAL}${NC}"
echo -e "${CYAN}  开始时间: $(date '+%Y-%m-%d %H:%M:%S')${NC}"

START_TIME=$(date +%s)
docker build -f Dockerfile.backend -t $BACKEND_IMAGE_LOCAL .
if [ $? -ne 0 ]; then
    echo -e "${RED}❌ 后端镜像构建失败！${NC}"
    exit 1
fi
END_TIME=$(date +%s)
BUILD_TIME=$((END_TIME - START_TIME))

echo -e "${GREEN}  ✅ 后端镜像构建成功！${NC}"
echo -e "${BLUE}  构建耗时: ${BUILD_TIME}秒${NC}"

# 获取镜像大小
BACKEND_SIZE=$(docker images $BACKEND_IMAGE_LOCAL --format "{{.Size}}")
echo -e "${BLUE}  镜像大小: ${BACKEND_SIZE}${NC}"
echo ""

# 步骤4: 构建前端镜像
echo -e "${YELLOW}步骤4: 构建前端镜像...${NC}"
echo -e "${CYAN}  镜像名称: ${FRONTEND_IMAGE_LOCAL}${NC}"
echo -e "${CYAN}  开始时间: $(date '+%Y-%m-%d %H:%M:%S')${NC}"

START_TIME=$(date +%s)
docker build -f Dockerfile.frontend -t $FRONTEND_IMAGE_LOCAL .
if [ $? -ne 0 ]; then
    echo -e "${RED}❌ 前端镜像构建失败！${NC}"
    exit 1
fi
END_TIME=$(date +%s)
BUILD_TIME=$((END_TIME - START_TIME))

echo -e "${GREEN}  ✅ 前端镜像构建成功！${NC}"
echo -e "${BLUE}  构建耗时: ${BUILD_TIME}秒${NC}"

# 获取镜像大小
FRONTEND_SIZE=$(docker images $FRONTEND_IMAGE_LOCAL --format "{{.Size}}")
echo -e "${BLUE}  镜像大小: ${FRONTEND_SIZE}${NC}"
echo ""

# 步骤5: 登录Docker Hub
echo -e "${YELLOW}步骤5: 登录Docker Hub...${NC}"
docker login -u $DOCKERHUB_USERNAME
if [ $? -ne 0 ]; then
    echo -e "${RED}❌ 登录失败！请检查用户名和密码是否正确。${NC}"
    exit 1
fi
echo -e "${GREEN}✅ 登录成功！${NC}"
echo ""

# 步骤6: 标记镜像
echo -e "${YELLOW}步骤6: 标记镜像...${NC}"

echo -e "${CYAN}  标记后端镜像: $BACKEND_IMAGE_REMOTE:$VERSION${NC}"
docker tag $BACKEND_IMAGE_LOCAL "$BACKEND_IMAGE_REMOTE:$VERSION"
if [ $? -ne 0 ]; then
    echo -e "${RED}❌ 后端镜像标记失败！${NC}"
    exit 1
fi

echo -e "${CYAN}  标记后端镜像: $BACKEND_IMAGE_REMOTE:latest${NC}"
docker tag $BACKEND_IMAGE_LOCAL "$BACKEND_IMAGE_REMOTE:latest"
if [ $? -ne 0 ]; then
    echo -e "${RED}❌ 后端镜像标记失败！${NC}"
    exit 1
fi

echo -e "${CYAN}  标记前端镜像: $FRONTEND_IMAGE_REMOTE:$VERSION${NC}"
docker tag $FRONTEND_IMAGE_LOCAL "$FRONTEND_IMAGE_REMOTE:$VERSION"
if [ $? -ne 0 ]; then
    echo -e "${RED}❌ 前端镜像标记失败！${NC}"
    exit 1
fi

echo -e "${CYAN}  标记前端镜像: $FRONTEND_IMAGE_REMOTE:latest${NC}"
docker tag $FRONTEND_IMAGE_LOCAL "$FRONTEND_IMAGE_REMOTE:latest"
if [ $? -ne 0 ]; then
    echo -e "${RED}❌ 前端镜像标记失败！${NC}"
    exit 1
fi

echo -e "${GREEN}✅ 镜像标记成功！${NC}"
echo ""

# 步骤7: 推送镜像
echo -e "${YELLOW}步骤7: 推送镜像到Docker Hub...${NC}"

echo -e "${CYAN}  推送后端镜像: $BACKEND_IMAGE_REMOTE:$VERSION${NC}"
docker push "$BACKEND_IMAGE_REMOTE:$VERSION"
if [ $? -ne 0 ]; then
    echo -e "${RED}❌ 后端镜像推送失败！${NC}"
    exit 1
fi

echo -e "${CYAN}  推送后端镜像: $BACKEND_IMAGE_REMOTE:latest${NC}"
docker push "$BACKEND_IMAGE_REMOTE:latest"
if [ $? -ne 0 ]; then
    echo -e "${RED}❌ 后端镜像推送失败！${NC}"
    exit 1
fi

echo -e "${CYAN}  推送前端镜像: $FRONTEND_IMAGE_REMOTE:$VERSION${NC}"
docker push "$FRONTEND_IMAGE_REMOTE:$VERSION"
if [ $? -ne 0 ]; then
    echo -e "${RED}❌ 前端镜像推送失败！${NC}"
    exit 1
fi

echo -e "${CYAN}  推送前端镜像: $FRONTEND_IMAGE_REMOTE:latest${NC}"
docker push "$FRONTEND_IMAGE_REMOTE:latest"
if [ $? -ne 0 ]; then
    echo -e "${RED}❌ 前端镜像推送失败！${NC}"
    exit 1
fi

echo -e "${GREEN}✅ 镜像推送成功！${NC}"
echo ""

# 完成
echo -e "${CYAN}========================================${NC}"
echo -e "${GREEN}🎉 Docker镜像构建和发布完成！${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""
echo -e "${YELLOW}已发布的镜像：${NC}"
echo -e "${CYAN}  后端: $BACKEND_IMAGE_REMOTE:$VERSION (${BACKEND_SIZE})${NC}"
echo -e "${CYAN}  后端: $BACKEND_IMAGE_REMOTE:latest (${BACKEND_SIZE})${NC}"
echo -e "${CYAN}  前端: $FRONTEND_IMAGE_REMOTE:$VERSION (${FRONTEND_SIZE})${NC}"
echo -e "${CYAN}  前端: $FRONTEND_IMAGE_REMOTE:latest (${FRONTEND_SIZE})${NC}"
echo ""
echo -e "${YELLOW}用户可以通过以下命令拉取镜像：${NC}"
echo -e "${CYAN}  docker pull $BACKEND_IMAGE_REMOTE:latest${NC}"
echo -e "${CYAN}  docker pull $FRONTEND_IMAGE_REMOTE:latest${NC}"
echo ""
echo -e "${YELLOW}或使用docker-compose启动：${NC}"
echo -e "${CYAN}  docker-compose -f docker-compose.hub.yml up -d${NC}"
echo ""
echo -e "${YELLOW}下一步：${NC}"
echo "  1. 访问 https://hub.docker.com/repositories/$DOCKERHUB_USERNAME"
echo "  2. 查看已发布的镜像"
echo "  3. 更新README.md添加镜像拉取说明"
echo "  4. 在GitHub Release中添加Docker镜像信息"
echo ""

