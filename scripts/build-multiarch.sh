#!/bin/bash
# TradingAgents-CN 多架构 Docker 镜像构建脚本
# 支持 amd64 (x86_64) 和 arm64 (ARM) 架构

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 版本信息
VERSION="${VERSION:-v1.0.0-preview}"
REGISTRY="${REGISTRY:-}"  # 留空表示本地构建，设置为 Docker Hub 用户名可推送到远程

# 镜像名称
BACKEND_IMAGE="tradingagents-backend"
FRONTEND_IMAGE="tradingagents-frontend"

# 支持的架构
PLATFORMS="linux/amd64,linux/arm64"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}TradingAgents-CN 多架构镜像构建${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${GREEN}版本: ${VERSION}${NC}"
echo -e "${GREEN}架构: ${PLATFORMS}${NC}"
if [ -n "$REGISTRY" ]; then
    echo -e "${GREEN}仓库: ${REGISTRY}${NC}"
else
    echo -e "${YELLOW}仓库: 本地构建（不推送）${NC}"
fi
echo ""

# 检查 Docker 是否安装
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker 未安装${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Docker 已安装${NC}"

# 检查 Docker Buildx 是否可用
if ! docker buildx version &> /dev/null; then
    echo -e "${RED}❌ Docker Buildx 未安装或不可用${NC}"
    echo -e "${YELLOW}请升级到 Docker 19.03+ 或安装 Buildx 插件${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Docker Buildx 可用${NC}"

# 创建或使用 buildx builder
echo ""
echo -e "${BLUE}配置 Docker Buildx...${NC}"
BUILDER_NAME="tradingagents-builder"

if docker buildx inspect "$BUILDER_NAME" &> /dev/null; then
    echo -e "${GREEN}✅ Builder '$BUILDER_NAME' 已存在${NC}"
else
    echo -e "${YELLOW}创建新的 Builder '$BUILDER_NAME'...${NC}"
    docker buildx create --name "$BUILDER_NAME" --use --platform "$PLATFORMS"
    echo -e "${GREEN}✅ Builder 创建成功${NC}"
fi

# 使用指定的 builder
docker buildx use "$BUILDER_NAME"

# 启动 builder（如果未运行）
docker buildx inspect --bootstrap

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}开始构建镜像${NC}"
echo -e "${BLUE}========================================${NC}"

# 构建后端镜像
echo ""
echo -e "${YELLOW}📦 构建后端镜像...${NC}"
BACKEND_TAG="${BACKEND_IMAGE}:${VERSION}"
if [ -n "$REGISTRY" ]; then
    BACKEND_TAG="${REGISTRY}/${BACKEND_TAG}"
fi

BUILD_ARGS="--platform ${PLATFORMS} -f Dockerfile.backend -t ${BACKEND_TAG}"

if [ -n "$REGISTRY" ]; then
    # 推送到远程仓库
    BUILD_ARGS="${BUILD_ARGS} --push"
    echo -e "${YELLOW}将推送到: ${BACKEND_TAG}${NC}"
else
    # 本地构建并加载
    BUILD_ARGS="${BUILD_ARGS} --load"
    echo -e "${YELLOW}本地构建: ${BACKEND_TAG}${NC}"
    echo -e "${YELLOW}⚠️  注意: --load 只支持单一架构，将只构建当前平台${NC}"
    # 获取当前平台
    CURRENT_PLATFORM=$(docker version --format '{{.Server.Os}}/{{.Server.Arch}}')
    BUILD_ARGS="--platform ${CURRENT_PLATFORM} -f Dockerfile.backend -t ${BACKEND_TAG} --load"
fi

echo -e "${BLUE}构建命令: docker buildx build ${BUILD_ARGS} .${NC}"
docker buildx build $BUILD_ARGS .

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ 后端镜像构建成功${NC}"
else
    echo -e "${RED}❌ 后端镜像构建失败${NC}"
    exit 1
fi

# 构建前端镜像
echo ""
echo -e "${YELLOW}📦 构建前端镜像...${NC}"
FRONTEND_TAG="${FRONTEND_IMAGE}:${VERSION}"
if [ -n "$REGISTRY" ]; then
    FRONTEND_TAG="${REGISTRY}/${FRONTEND_TAG}"
fi

BUILD_ARGS="--platform ${PLATFORMS} -f Dockerfile.frontend -t ${FRONTEND_TAG}"

if [ -n "$REGISTRY" ]; then
    # 推送到远程仓库
    BUILD_ARGS="${BUILD_ARGS} --push"
    echo -e "${YELLOW}将推送到: ${FRONTEND_TAG}${NC}"
else
    # 本地构建并加载
    BUILD_ARGS="${BUILD_ARGS} --load"
    echo -e "${YELLOW}本地构建: ${FRONTEND_TAG}${NC}"
    echo -e "${YELLOW}⚠️  注意: --load 只支持单一架构，将只构建当前平台${NC}"
    # 获取当前平台
    CURRENT_PLATFORM=$(docker version --format '{{.Server.Os}}/{{.Server.Arch}}')
    BUILD_ARGS="--platform ${CURRENT_PLATFORM} -f Dockerfile.frontend -t ${FRONTEND_TAG} --load"
fi

echo -e "${BLUE}构建命令: docker buildx build ${BUILD_ARGS} .${NC}"
docker buildx build $BUILD_ARGS .

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ 前端镜像构建成功${NC}"
else
    echo -e "${RED}❌ 前端镜像构建失败${NC}"
    exit 1
fi

# 构建完成
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✅ 所有镜像构建完成！${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

if [ -n "$REGISTRY" ]; then
    echo -e "${GREEN}镜像已推送到远程仓库:${NC}"
    echo -e "  - ${BACKEND_TAG}"
    echo -e "  - ${FRONTEND_TAG}"
    echo ""
    echo -e "${YELLOW}使用方法:${NC}"
    echo -e "  docker pull ${BACKEND_TAG}"
    echo -e "  docker pull ${FRONTEND_TAG}"
else
    echo -e "${GREEN}镜像已构建到本地:${NC}"
    echo -e "  - ${BACKEND_TAG}"
    echo -e "  - ${FRONTEND_TAG}"
    echo ""
    echo -e "${YELLOW}使用方法:${NC}"
    echo -e "  docker-compose -f docker-compose.v1.0.0.yml up -d"
fi

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${YELLOW}💡 提示${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}1. 推送到 Docker Hub:${NC}"
echo -e "   REGISTRY=your-dockerhub-username VERSION=v1.0.0 ./scripts/build-multiarch.sh"
echo ""
echo -e "${YELLOW}2. 本地构建（当前架构）:${NC}"
echo -e "   ./scripts/build-multiarch.sh"
echo ""
echo -e "${YELLOW}3. 构建特定架构:${NC}"
echo -e "   docker buildx build --platform linux/arm64 -f Dockerfile.backend -t tradingagents-backend:arm64 ."
echo ""
echo -e "${YELLOW}4. 查看镜像信息:${NC}"
echo -e "   docker buildx imagetools inspect ${BACKEND_TAG}"
echo ""

