# 🚀 快速构建参考

## 📦 分架构独立仓库策略

### 核心理念

- **AMD64 仓库**：`tradingagents-backend-amd64` - 频繁更新
- **ARM64 仓库**：`tradingagents-backend-arm64` - 按需更新
- **独立发布**：互不影响，提高效率

---

## ⚡ 快速命令

### AMD64 构建（推荐，最常用）

```bash
# Linux/macOS
REGISTRY=TradingAgent-Future VERSION=v1.0.1 ./scripts/build-amd64.sh

# Windows
.\scripts\build-amd64.ps1 -Registry TradingAgent-Future -Version v1.0.1
```

**时间**：5-10 分钟 ⚡

---

### ARM64 构建（按需）

```bash
# Linux/macOS
REGISTRY=TradingAgent-Future VERSION=v1.0.1 ./scripts/build-arm64.sh

# Windows
.\scripts\build-arm64.ps1 -Registry TradingAgent-Future -Version v1.0.1
```

**时间**：10-20 分钟

---

### Apple Silicon 构建

```bash
# macOS（使用 ARM64 脚本）
REGISTRY=TradingAgent-Future VERSION=v1.0.1 ./scripts/build-arm64.sh
```

**时间**：5-8 分钟 ⚡

**说明**：Apple Silicon 使用 ARM64 架构，与 ARM 服务器镜像完全通用

---

## 📊 使用场景

| 场景 | 命令 | 时间 |
|------|------|------|
| **小更新（推荐）** | `./scripts/build-amd64.sh` | 5-10分钟 |
| **ARM64 更新** | `./scripts/build-arm64.sh` | 10-20分钟 |
| **重大版本** | 两个都运行 | 15-30分钟 |

---

## 🎯 发布策略

### 日常开发（高频）

```bash
# 只更新 AMD64（大部分用户）
REGISTRY=TradingAgent-Future VERSION=v1.0.1 ./scripts/build-amd64.sh
```

### 月度更新（低频）

```bash
# 更新 ARM64（积累多个更新）
REGISTRY=TradingAgent-Future VERSION=v1.0.5 ./scripts/build-arm64.sh
```

### 重大版本（同步）

```bash
# 两个架构都更新
REGISTRY=TradingAgent-Future VERSION=v2.0.0 ./scripts/build-amd64.sh
REGISTRY=TradingAgent-Future VERSION=v2.0.0 ./scripts/build-arm64.sh
```

---

## 👥 用户使用

### AMD64 用户

```bash
docker pull TradingAgent-Future/tradingagents-backend-amd64:latest
docker pull TradingAgent-Future/tradingagents-frontend-amd64:latest
```

### ARM64 用户

```bash
docker pull TradingAgent-Future/tradingagents-backend-arm64:latest
docker pull TradingAgent-Future/tradingagents-frontend-arm64:latest
```

---

## 📝 docker-compose.yml 配置

### AMD64

```yaml
services:
  backend:
    image: TradingAgent-Future/tradingagents-backend-amd64:latest
  frontend:
    image: TradingAgent-Future/tradingagents-frontend-amd64:latest
```

### ARM64

```yaml
services:
  backend:
    image: TradingAgent-Future/tradingagents-backend-arm64:latest
  frontend:
    image: TradingAgent-Future/tradingagents-frontend-arm64:latest
```

---

## 🔍 验证

```bash
# 查看本地镜像
docker images | grep tradingagents

# 查看镜像架构
docker inspect TradingAgent-Future/tradingagents-backend-amd64:latest | grep Architecture
```

---

## 📚 详细文档

- [构建指南](./BUILD_GUIDE.md)
- [仓库策略](./DOCKER_REGISTRY_STRATEGY.md)

---

**最后更新**：2025-10-24

