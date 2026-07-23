# Phase 3a 大宗商品部署指南

> 适用版本:TradingAgents-CN v1.0.1-commodity-phase3a(及以后)
> 文档日期:2026-07-14
> 关联文档:[Phase 3a 完成报告](../progress/phase-3a.md)|[大宗商品改造 plan](../plans/stock-to-commodity.md)|[通用 Docker 部署](DOCKER_DEPLOYMENT_v1.0.0.md)

**两种部署方式**:
- **第三章起** → `docker compose up -d`(团队统一 / 生产)
- **第九章** → Python 本地部署(个人开发 / 镜像源 429 时)

---

## 一、环境要求

### 1.1 必装

| 组件 | 最低版本 | 验证命令 |
|---|---|---|
| **Docker Desktop** | 4.x(含 Compose V2) | `docker --version` / `docker compose version` |
| **WSL 2** 后端(Windows) | 内核 5.10+ | `wsl --status` |
| **磁盘空间** | ≥ 10 GB | 镜像 + MongoDB 数据卷 |
| **内存** | ≥ 8 GB(开发模式推荐 16 GB) | `wsl -d docker-desktop` 内存上限 |

### 1.2 可选(仅本地编译/调试前端需要)

| 组件 | 用途 |
|---|---|
| **Node.js** 22.x | 本地 `cd frontend && yarn install` |
| **Python** 3.11+ | 本地后端调试(可绕过 Docker) |
| **yarn** 1.22+ | `npm install -g yarn`(项目锁文件是 yarn.lock) |

> 💡 **Docker 镜像已自带 Node.js 22 + yarn(corepack 启用)**,本地不装 yarn 也能跑 docker。

### 1.3 镜像源提醒(常见坑)

中国大陆用户常配 `https://docker.xuanyuan.me` 等镜像源,**首次 build 可能因 429 限流失败**。详见 §六排错。

---

## 二、克隆与配置

### 2.1 拉取代码

```bash
git clone https://github.com/hsliuping/TradingAgents-CN.git
cd TradingAgents-CN
git checkout v1.0.1-commodity-phase3a    # 或 main(若 phase3a 已合并)
```

### 2.2 创建 `.env`

```bash
# Windows PowerShell
Copy-Item .env.example .env
# Linux/macOS
cp .env.example .env
```

### 2.3 **关键:打开 commodity flag**(Phase 3a)

Phase 3a 必须翻两个开关,后端才会 include_router:

```bash
# .env
FEATURE_COMMODITY_ENABLED=true
FEATURE_COMMODITY_DATA=true
FEATURE_COMMODITY_ANALYSIS=false   # 保留 false,Phase 3b 再开
FEATURE_COMMODITY_PAPER=false       # 保留 false,Phase 4 再开
```

> ⚠️ **重点提醒**:`docker-compose.override.yml` 里的 `environment` 段优先级 > `.env`。详见 §二.4。

### 2.4 Docker Compose 配置层级(避坑必读)

按优先级从高到低:

| 优先级 | 来源 | 说明 |
|---|---|---|
| 1(最高) | `docker-compose.yml` / `docker-compose.override.yml` 的 `environment:` 段 | **覆盖一切** |
| 2 | `docker-compose.yml` 的 `env_file:` 段(读 `.env`) | 仅在 1 未设置时生效 |
| 3 | `Dockerfile` 内 `ENV` / `COPY .env.docker ./.env` | 镜像内默认值,基本被覆盖 |

`docker-compose.override.yml` 已在 v1.0.1-commodity-phase3a 默认翻 `FEATURE_COMMODITY_ENABLED=true / DATA=true`,**本地开发开箱即用**。

如需临时关闭 commodity 模块(比如排查其他问题):

```yaml
# docker-compose.override.yml(临时)
services:
  backend:
    environment:
      FEATURE_COMMODITY_ENABLED: "false"   # ← 改这里
      FEATURE_COMMODITY_DATA: "false"
```

---

## 三、启动

### 3.1 一键启动(开发模式)

```bash
# 在项目根目录
docker compose up -d

# 查看日志(等 30s 启动)
docker compose logs -f backend | head -100
```

正常启动标志(backend 日志中):

```
✅ 大宗商品数据路由已注册(/api/commodity/* 共 22 端点)
```

### 3.2 仅后端启动(跳过前端 build)

```bash
docker compose up -d mongodb redis backend
# 后端跑在 http://localhost:8000
```

### 3.3 端口说明

| 服务 | 宿主机端口 | 容器端口 | 用途 |
|---|---|---|---|
| backend | 8000 | 8000 | FastAPI 后端 |
| frontend (prod) | 3000 | 80 | Nginx 静态文件 |
| frontend (dev override) | 5173 | 5173 | Vite HMR(override 改了) |
| mongodb | 27017 | 27017 | 数据库 |
| redis | 6379 | 6379 | 缓存 |
| redis-commander(可选) | 8081 | 8081 | `--profile management` 启用 |
| mongo-express(可选) | 8082 | 8081 | `--profile management` 启用 |

### 3.4 健康检查

```bash
# 后端
curl http://localhost:8000/api/health

# 商品端点(至少 1 个应 200)
curl http://localhost:8000/api/commodity/categories

# 前端(prod 镜像)
curl -I http://localhost:3000/
```

---

## 四、Phase 3a 验证清单

### 4.1 后端验证(curl 22 端点)

```bash
# 字典
curl http://localhost:8000/api/commodity/categories
curl http://localhost:8000/api/commodity/exchanges
curl http://localhost:8000/api/commodity/varieties?exchange=SHFE

# 单标
curl http://localhost:8000/api/commodity/CU2501.SHF/info
curl http://localhost:8000/api/commodity/CU2501.SHF/quotes
curl 'http://localhost:8000/api/commodity/CU2501.SHF/historical?start_date=2025-01-01'

# 扩展
curl http://localhost:8000/api/commodity/SHFE/contract-info
curl http://localhost:8000/api/commodity/realtime-quote?symbols=CU2501

# 新闻
curl http://localhost:8000/api/commodity/news/categories
curl 'http://localhost:8000/api/commodity/news?category=metal&limit=10'
```

### 4.2 前端验证(浏览器)

| 路径 | 预期 |
|---|---|
| `http://localhost:3000/` | 登录页 |
| `http://localhost:3000/commodity/list` | **80+ 品种表格,交易所/品类筛选可用** |
| `http://localhost:3000/commodity/CU2501.SHF` | **详情页 7 个 tab,echarts K 线/库存图渲染** |
| 侧边菜单 | **"大宗商品" 子菜单显示,内含"商品列表"** |

### 4.3 Feature Flag 同步验证

```bash
# 后端 /api/config/features(后端读 .env,前端可读此端点控制菜单)
curl http://localhost:8000/api/config/features | jq .data
```

预期:
```json
{
  "commodity_enabled": true,
  "commodity_data": true,
  "commodity_analysis": false,
  "commodity_paper": false
}
```

---

## 五、停止与清理

### 5.1 停止

```bash
docker compose down          # 停止但保留数据卷
docker compose down -v       # 停止并删除所有数据卷(MongoDB 数据会清空!)
```

### 5.2 仅重启后端(代码改动后)

```bash
docker compose restart backend
# 后端日志看 reload
docker compose logs -f backend --tail=50
```

> 💡 override.yml 已挂载 `./tradingagents` 和 `./app` 到容器内,**uvicorn --reload 自动热重载**。改完代码几秒后生效。

### 5.3 前端 HMR(开发模式)

`docker-compose.override.yml` 默认用 `npm run dev` + 端口 5173 + 挂载 `./frontend/src`,**改前端文件自动刷新**。

---

## 六、排错(常见问题)

### 6.1 镜像拉取 429 Too Many Requests

**症状**(用户实际遇到的):
```
ERROR: failed to solve: nginx:alpine: failed to resolve source metadata for docker.io/library/nginx:alpine:
unexpected status from GET request to https://docker.xuanyuan.me/v2/library/nginx/manifests/alpine?ns=docker.io:
429 Too Many Requests
```

**原因**:Docker Desktop 配置的 registry-mirror(国内源)被限流。

**解法**:

**A. 等 5-10 分钟重试**(429 通常自动解除):
```bash
docker compose up -d
```

**B. 改镜像源**(Docker Desktop → Settings → Docker Engine):
```json
{
  "registry-mirrors": [
    "https://docker.1ms.run",
    "https://docker.m.daocloud.io"
  ]
}
```
点 Apply & restart,然后 `docker compose up -d`。

**C. 拉基础镜像时绕过 mirror**(临时):
```bash
docker pull --platform=linux/amd64 nginx:alpine
docker pull --platform=linux/amd64 node:22-alpine
docker pull --platform=linux/amd64 python:3.10-slim-bookworm
# 拉完后重新 build
docker compose build --no-cache
docker compose up -d
```

### 6.2 后端启动后立即退出(常见)

**症状**:`docker compose logs backend` 显示 "Application startup failed. Exiting." 或 pymongo "Authentication failed"

**原因**:MongoDB 健康检查还没就绪,或 `.env` 里的 MongoDB 认证串错误。

**解法**:
```bash
# 1. 检查 mongodb 是否就绪
docker compose logs mongodb | tail -20

# 2. 确认 .env 中:
#    MONGODB_HOST=localhost           # 开发模式 OK
#    MONGODB_PORT=27017
#    MONGODB_USERNAME=admin
#    MONGODB_PASSWORD=tradingagents123
#    MONGODB_AUTH_SOURCE=admin

# 3. docker compose down && docker compose up -d(完整重启)
```

### 6.3 浏览器访问 `/commodity/*` 跳 dashboard / 菜单不见

**症状**:菜单没"大宗商品",URL 直接 `/commodity/list` 也跳 `/dashboard`

**原因**:前端 `featureStore.commodityEnabled=false`(后端没读到 flag=true)。

**解法**:
```bash
# 1. 验证后端配置
curl http://localhost:8000/api/config/features | jq .data.commodity_enabled
# 期望 true;false 则继续 ↓

# 2. 检查 docker-compose.override.yml 的 environment 段
#    FEATURE_COMMODITY_ENABLED: "true"

# 3. 重启后端
docker compose restart backend

# 4. 浏览器硬刷新(Ctrl+F5 / Cmd+Shift+R)
```

### 6.4 K 线图/库存图空白

**症状**:详情页 echarts 区域一片空白

**原因**:对应品种/日期无数据(如非交易日、品种不支持接口)。

**解法**:
- 详情页默认跳 `CU2501.SHF`,周末不交易 → K 线仍可能有数据(最近一周),但库存/基差可能空
- 切换为日内时间(工作日 9:00-15:00 北京时间),或在非交易日看到 "暂无数据" 是正常

### 6.5 前端 yarn install 找不到 yarn(本地开发)

**症状**(本地非 docker):
```
yarn: 无法将"yarn"项识别为 cmdlet、函数、脚本文件或可运行程序的名称
```

**解法**:
```bash
# 方案 1:用 npm
cd frontend && npm install

# 方案 2:装 yarn(推荐)
npm install -g yarn
cd frontend && yarn install
```

**docker 内部不受影响**:Dockerfile.frontend 第 11 行 `corepack enable && corepack prepare yarn@1.22.22 --activate`,镜像自带 yarn。

---

## 七、生产部署(非开发模式)

### 7.1 仅用基础 compose,不用 override

```bash
# 不加载 override.yml
docker compose -f docker-compose.yml up -d
```

此时:
- 后端用镜像内置 `.env.docker`(FEATURE_COMMODITY_* 默认 false)
- 前端用生产 nginx 镜像(非 Vite HMR)
- 端口:backend 8000 / frontend 3000

### 7.2 翻 flag(生产)

**方式 1**:build 前改 `Dockerfile.backend` 第 80 行对应的 `.env.docker`,翻 flag 后 build。
**方式 2**:run 时覆盖:
```bash
docker run -e FEATURE_COMMODITY_ENABLED=true -e FEATURE_COMMODITY_DATA=true ...
```

### 7.3 多架构镜像(arm64 服务器)

```bash
# 用项目提供的脚本
./scripts/build-multiarch.sh
# 或参见 docs/deployment/docker/MULTIARCH_BUILD.md
```

---

## 八、Phase 3a 与 Phase 4/5 兼容性

| 当前 Phase | 启用 flag | 关闭 flag |
|---|---|---|
| **Phase 3a(本阶段)** | `ENABLE=true / DATA=true` | `ANALYSIS=false / PAPER=false` |
| **Phase 3b(下一步)** | + `ANALYSIS=true` | `PAPER=false` |
| **Phase 4** | + `PAPER=true` | - |
| **Phase 5(清期货品种)** | 移除所有期货品种侧 | 商品完全替代 |

升级到下一 Phase 时,只需翻一个 flag,然后 `docker compose restart backend`,前端无需重新 build(HMR 自动接)。

---

## 九、Python 本地部署(绕开 Docker)

> **适用场景**:Docker 镜像源限流(轩辕/网易等 429)/ 不想装 Docker Desktop / 想直接调后端 Python 代码 / WSL 资源不够
> **架构**:本地 Python 跑后端 + Node 跑前端,MongoDB/Redis 仍可用 docker(只跑 2 个容器)或本机原生安装

### 9.1 环境要求

| 组件 | 最低版本 | 说明 |
|---|---|---|
| Python | 3.10+ | 后端 |
| Node.js | 22.x | 前端构建(Vite) |
| 包管理器 | uv(推荐)/ pip / npm | uv 是项目 pyproject.toml 的约定 |
| MongoDB | 6.x+ | 本地或 docker 容器二选一 |
| Redis | 7.x+ | 本地或 docker 容器二选一 |

### 9.2 一键启动(本机原生 Mongo + Redis)

#### A. 后端

```powershell
# 1. 装依赖
uv pip install -e .
uv pip install -e ".[qianfan]"   # 可选依赖

# 2. 准备 .env(注意与 docker 部署的差异)
Copy-Item .env.example .env
```

`.env` 关键配置(本机原生,非 docker 容器):

```bash
# 数据库连接(本机原生时直接 localhost)
MONGODB_HOST=localhost
MONGODB_PORT=27017
MONGODB_USERNAME=admin
MONGODB_PASSWORD=tradingagents123
MONGODB_DATABASE=tradingagentscn
MONGODB_AUTH_SOURCE=admin

REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=tradingagents123

# Phase 3a flag
FEATURE_COMMODITY_ENABLED=true
FEATURE_COMMODITY_DATA=true
FEATURE_COMMODITY_ANALYSIS=false
FEATURE_COMMODITY_PAPER=false
```

```powershell
# 3. 启动后端(开发模式热重载)
python -m app --reload
# 等价命令:uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 成功标志:
# ✅ 大宗商品数据路由已注册(/api/commodity/* 共 22 端点)
```

#### B. 前端

```powershell
cd frontend

# 装依赖(项目锁文件是 yarn.lock,但 npm 也兼容)
npm install
# 或 yarn install(若装了 yarn)

# 启动 Vite 开发服务器
npm run dev
# 默认 http://localhost:5173(Vite 默认端口)
```

前端 `.env.development`(可选,在 `frontend/.env.development` 创建):

```bash
# Vite 代理到后端
VITE_API_BASE_URL=http://localhost:8000
```

### 9.3 混合部署:本地后端 + docker 数据库

> **推荐**:MongoDB / Redis 还是用 docker 跑,简单稳定;只把后端和前端放本机。

```powershell
# 1. 只启 Mongo + Redis 容器
docker compose up -d mongodb redis

# 2. .env 用上面的"本机原生"配置(MONGODB_HOST=localhost)

# 3. 启后端 + 前端
python -m app --reload          # 终端 1
cd frontend && npm run dev      # 终端 2
```

### 9.4 端口冲突处理

| 服务 | 默认端口 | 修改方式 |
|---|---|---|
| 后端 | 8000 | `python -m app --port 9000` 或 `uvicorn ... --port 9000` |
| 前端 | 5173 | `cd frontend && npm run dev -- --port 3000` |
| MongoDB | 27017 | 改 docker compose 或本机 mongod 配置 |
| Redis | 6379 | 同上 |

如果改了后端端口,前端 `.env.development` 也要同步改 `VITE_API_BASE_URL`。

### 9.5 验证(同 docker 部署)

```powershell
# 后端 22 端点
curl http://localhost:8000/api/commodity/categories
curl http://localhost:8000/api/commodity/CU2501.SHF/info
curl http://localhost:8000/api/commodity/news/categories

# 浏览器
# http://localhost:5173/commodity/list
```

### 9.6 排错(本机部署常见)

#### A. `pymongo.errors.ServerSelectionTimeoutError: localhost:27017`

**原因**:MongoDB 没启。

**解法**:
```powershell
# 选项 1:启 docker Mongo
docker compose up -d mongodb

# 选项 2:本机 mongod(若已装)
mongod --dbpath ./data/db
```

#### B. `pymongo.errors.OperationFailure: Authentication failed`

**原因**:MongoDB 认证串与 `.env` 不一致。

**解法**:确认 `.env` 三者匹配
- `MONGODB_USERNAME` / `MONGODB_PASSWORD`
- `MONGODB_AUTH_SOURCE`(默认 `admin`)
- docker compose 里 `MONGO_INITDB_ROOT_USERNAME` / `PASSWORD`(若用 docker)

#### C. 前端 `npm install` 报网络错(EACCES / ETIMEDOUT)

**解法**:
```powershell
# 国内镜像
npm config set registry https://registry.npmmirror.com

# 重装
cd frontend
rm -rf node_modules package-lock.json
npm install
```

#### D. 前端 `npm run dev` 后浏览器 404

**原因**:vite proxy 没生效或后端没启。

**解法**:
```powershell
# 检查 vite.config.ts 是否有 proxy 配置(vite.config.ts 应有类似):
#   server: { proxy: { '/api': 'http://localhost:8000' } }

# 检查后端
curl http://localhost:8000/api/health
```

#### E. 后端改了 .env 不生效

**原因**:uvicorn --reload 只 reload Python 代码,不重读 .env(进程级)。

**解法**:完全重启
```powershell
Ctrl+C  # 停
python -m app --reload  # 重启
```

### 9.7 docker 部署 vs Python 本地部署 对比

| 维度 | docker compose | Python 本地 |
|---|---|---|
| **环境一致性** | ✅ 镜像固化 | ⚠️ 取决于本机 Python 版本 |
| **资源占用** | ⚠️ 4 容器 ≈ 4 GB | ✅ 2 进程 ≈ 1 GB |
| **冷启动速度** | ⚠️ 首次 build 5-10 分钟 | ✅ 30 秒 |
| **镜像源依赖** | ⚠️ 限流时痛苦 | ✅ 纯 npm/pip |
| **代码热重载** | ✅ 后端 uvicorn --reload + 前端 Vite HMR(override 模式) | ✅ 同 |
| **生产部署** | ✅ docker compose 上服务器 | ❌ 仅开发用 |
| **适用人群** | 团队统一 / 生产 | 个人开发 / 镜像限流 |

> 💡 **建议**:日常开发用 **§9.3 混合部署**(本地后端 + docker DB),生产用 **第三章 docker compose**。

---

## 十、参考

- [Phase 3a 完成报告](../progress/phase-3a.md)— 22 端点 + 4 前端文件实测细节
- [大宗商品改造 plan](../plans/stock-to-commodity.md)— 5-Phase 完整设计
- [通用 Docker 部署指南](DOCKER_DEPLOYMENT_v1.0.0.md)— Phase 3a 之前的 docker 配置
- [通用 Docker Compose 拆分](docker-compose.split.yml)— 前后端分离多机部署
- [多架构构建](MULTIARCH_BUILD.md)— arm64 服务器
- [Docker Hub 发布](DOCKER_HUB_PUBLISH_GUIDE.md)— 自定义镜像发布
- [项目根 CLAUDE.md](../../CLAUDE.md)— 开发与运行(本地命令速查)
- [pyproject.toml](../../pyproject.toml)— Python 依赖列表