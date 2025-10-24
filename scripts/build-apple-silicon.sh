#!/bin/bash
# TradingAgents-CN Apple Silicon (M1/M2/M3/M4) 架构 Docker 镜像构建脚本
# 适用于：MacBook Pro/Air (M1/M2/M3/M4)、Mac Mini、Mac Studio、iMac (Apple Silicon)

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

# 目标架构（Apple Silicon 使用 ARM64）
PLATFORM="linux/arm64"
ARCH_SUFFIX="apple-silicon"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}TradingAgents-CN Apple Silicon 镜像构建${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${GREEN}版本: ${VERSION}${NC}"
echo -e "${GREEN}架构: ${PLATFORM} (Apple Silicon)${NC}"
echo -e "${GREEN}适用: MacBook Pro/Air (M1/M2/M3/M4)${NC}"
if [ -n "$REGISTRY" ]; then
    echo -e "${GREEN}仓库: ${REGISTRY}${NC}"
else
    echo -e "${YELLOW}仓库: 本地构建（不推送）${NC}"
fi
echo ""

# 检查是否在 macOS 上运行
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo -e "${YELLOW}⚠️  警告: 此脚本针对 macOS 优化，但也可在其他系统上运行${NC}"
fi

# 检查是否是 Apple Silicon
if [[ $(uname -m) == "arm64" ]]; then
    echo -e "${GREEN}✅ 检测到 Apple Silicon 处理器${NC}"
else
    echo -e "${YELLOW}⚠️  当前不是 Apple Silicon 处理器，将进行交叉编译${NC}"
fi

# 检查 Docker 是否安装
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker 未安装${NC}"
    echo -e "${YELLOW}请安装 Docker Desktop for Mac: https://www.docker.com/products/docker-desktop${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Docker 已安装${NC}"

# 检查 Docker Buildx 是否可用
if ! docker buildx version &> /dev/null; then
    echo -e "${RED}❌ Docker Buildx 未安装或不可用${NC}"
    echo -e "${YELLOW}请升级到 Docker Desktop 最新版本${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Docker Buildx 可用${NC}"

# 创建或使用 buildx builder
echo ""
echo -e "${BLUE}配置 Docker Buildx...${NC}"
BUILDER_NAME="tradingagents-builder-apple"

if docker buildx inspect "$BUILDER_NAME" &> /dev/null; then
    echo -e "${GREEN}✅ Builder '$BUILDER_NAME' 已存在${NC}"
else
    echo -e "${YELLOW}创建新的 Builder '$BUILDER_NAME'...${NC}"
    docker buildx create --name "$BUILDER_NAME" --use --platform "$PLATFORM"
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
echo -e "${YELLOW}📦 构建后端镜像 (Apple Silicon)...${NC}"
BACKEND_TAG="${BACKEND_IMAGE}:${VERSION}-${ARCH_SUFFIX}"
if [ -n "$REGISTRY" ]; then
    BACKEND_TAG="${REGISTRY}/${BACKEND_TAG}"
fi

BUILD_ARGS="--platform ${PLATFORM} -f Dockerfile.backend -t ${BACKEND_TAG}"

if [ -n "$REGISTRY" ]; then
    # 推送到远程仓库
    BUILD_ARGS="${BUILD_ARGS} --push"
    echo -e "${YELLOW}将推送到: ${BACKEND_TAG}${NC}"
else
    # 本地构建并加载
    BUILD_ARGS="${BUILD_ARGS} --load"
    echo -e "${YELLOW}本地构建: ${BACKEND_TAG}${NC}"
fi

# 同时打上不带架构后缀的标签（方便本地使用）
BACKEND_TAG_SIMPLE="${BACKEND_IMAGE}:${VERSION}"
if [ -n "$REGISTRY" ]; then
    BACKEND_TAG_SIMPLE="${REGISTRY}/${BACKEND_TAG_SIMPLE}"
fi
BUILD_ARGS="${BUILD_ARGS} -t ${BACKEND_TAG_SIMPLE}"

# 同时打上 arm64 标签（兼容性）
BACKEND_TAG_ARM64="${BACKEND_IMAGE}:${VERSION}-arm64"
if [ -n "$REGISTRY" ]; then
    BACKEND_TAG_ARM64="${REGISTRY}/${BACKEND_TAG_ARM64}"
fi
BUILD_ARGS="${BUILD_ARGS} -t ${BACKEND_TAG_ARM64}"

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
echo -e "${YELLOW}📦 构建前端镜像 (Apple Silicon)...${NC}"
FRONTEND_TAG="${FRONTEND_IMAGE}:${VERSION}-${ARCH_SUFFIX}"
if [ -n "$REGISTRY" ]; then
    FRONTEND_TAG="${REGISTRY}/${FRONTEND_TAG}"
fi

BUILD_ARGS="--platform ${PLATFORM} -f Dockerfile.frontend -t ${FRONTEND_TAG}"

if [ -n "$REGISTRY" ]; then
    # 推送到远程仓库
    BUILD_ARGS="${BUILD_ARGS} --push"
    echo -e "${YELLOW}将推送到: ${FRONTEND_TAG}${NC}"
else
    # 本地构建并加载
    BUILD_ARGS="${BUILD_ARGS} --load"
    echo -e "${YELLOW}本地构建: ${FRONTEND_TAG}${NC}"
fi

# 同时打上不带架构后缀的标签（方便本地使用）
FRONTEND_TAG_SIMPLE="${FRONTEND_IMAGE}:${VERSION}"
if [ -n "$REGISTRY" ]; then
    FRONTEND_TAG_SIMPLE="${REGISTRY}/${FRONTEND_TAG_SIMPLE}"
fi
BUILD_ARGS="${BUILD_ARGS} -t ${FRONTEND_TAG_SIMPLE}"

# 同时打上 arm64 标签（兼容性）
FRONTEND_TAG_ARM64="${FRONTEND_IMAGE}:${VERSION}-arm64"
if [ -n "$REGISTRY" ]; then
    FRONTEND_TAG_ARM64="${REGISTRY}/${FRONTEND_TAG_ARM64}"
fi
BUILD_ARGS="${BUILD_ARGS} -t ${FRONTEND_TAG_ARM64}"

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
echo -e "${GREEN}✅ Apple Silicon 镜像构建完成！${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

if [ -n "$REGISTRY" ]; then
    echo -e "${GREEN}镜像已推送到远程仓库:${NC}"
    echo -e "  - ${BACKEND_TAG}"
    echo -e "  - ${BACKEND_TAG_SIMPLE}"
    echo -e "  - ${BACKEND_TAG_ARM64}"
    echo -e "  - ${FRONTEND_TAG}"
    echo -e "  - ${FRONTEND_TAG_SIMPLE}"
    echo -e "  - ${FRONTEND_TAG_ARM64}"
    echo ""
    echo -e "${YELLOW}使用方法:${NC}"
    echo -e "  docker pull ${BACKEND_TAG}"
    echo -e "  docker pull ${FRONTEND_TAG}"
else
    echo -e "${GREEN}镜像已构建到本地:${NC}"
    echo -e "  - ${BACKEND_TAG}"
    echo -e "  - ${BACKEND_TAG_SIMPLE}"
    echo -e "  - ${BACKEND_TAG_ARM64}"
    echo -e "  - ${FRONTEND_TAG}"
    echo -e "  - ${FRONTEND_TAG_SIMPLE}"
    echo -e "  - ${FRONTEND_TAG_ARM64}"
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
echo -e "   REGISTRY=your-dockerhub-username VERSION=v1.0.0 ./scripts/build-apple-silicon.sh"
echo ""
echo -e "${YELLOW}2. 本地构建:${NC}"
echo -e "   ./scripts/build-apple-silicon.sh"
echo ""
echo -e "${YELLOW}3. 查看镜像:${NC}"
echo -e "   docker images | grep tradingagents"
echo ""
echo -e "${YELLOW}4. 构建其他架构:${NC}"
echo -e "   AMD64: ./scripts/build-amd64.sh"
echo -e "   ARM64: ./scripts/build-arm64.sh"
echo ""
echo -e "${YELLOW}5. Apple Silicon 优化:${NC}"
echo -e "   - 本地构建速度快（原生架构）"
echo -e "   - 镜像与 ARM64 通用（linux/arm64）"
echo -e "   - 可在 ARM 服务器上直接使用"
echo ""
echo -e "${GREEN}🍎 Apple Silicon 用户专属优势:${NC}"
echo -e "   - 原生性能，无需模拟"
echo -e "   - 构建速度比 x86 模拟快 3-5 倍"
echo -e "   - 运行效率高，功耗低"
echo ""

