# TradingAgents-CN 环境准备指南

> 🛠️ 完整的环境准备和配置指南

## 📋 概述

本指南将帮助你准备运行TradingAgents-CN所需的完整环境。无论你选择Docker部署还是本地开发，都可以在这里找到详细的步骤。

---

## 🎯 选择部署方式

### 方式对比

| 特性 | Docker部署 | 本地开发 |
|------|-----------|---------|
| **难度** | ⭐ 简单 | ⭐⭐⭐ 中等 |
| **时间** | 15-30分钟 | 30-60分钟 |
| **灵活性** | 低 | 高 |
| **适合人群** | 普通用户 | 开发者 |
| **代码修改** | ❌ 不支持 | ✅ 支持 |
| **资源占用** | 中等 | 较高 |
| **维护成本** | 低 | 中等 |

### 推荐选择

- **🐳 Docker部署**: 如果你只是想使用TradingAgents-CN，不需要修改代码
- **💻 本地开发**: 如果你需要修改代码、进行二次开发或贡献代码

---

## 🐳 方式一：Docker部署

### 系统要求

| 项目 | 最低要求 | 推荐配置 |
|------|---------|---------|
| **操作系统** | Windows 10/macOS 11/Ubuntu 20.04 | Windows 11/macOS 13/Ubuntu 22.04 |
| **处理器** | 2核 | 4核+ |
| **内存** | 4GB | 8GB+ |
| **磁盘** | 20GB | 50GB+ |

### 安装步骤

#### 1. 安装Docker

根据你的操作系统选择：

**Windows**:

Docker Desktop支持两种后端：WSL 2（推荐）和Hyper-V

```powershell
# 方式A: 使用WSL 2后端（推荐，性能更好）
# 1. 启用WSL 2
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart

# 2. 重启电脑

# 3. 安装WSL 2内核更新
# 访问: https://aka.ms/wsl2kernel

# 4. 设置WSL 2为默认
wsl --set-default-version 2

# 方式B: 使用Hyper-V后端（无需WSL）
# 1. 启用Hyper-V
Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V -All

# 2. 重启电脑

# 通用步骤：
# 3. 下载并安装Docker Desktop
# 访问: https://www.docker.com/products/docker-desktop
# 下载并安装 Docker Desktop for Windows
# 安装时选择对应的后端引擎

# 4. 验证安装
docker --version
docker-compose --version
```

**macOS**:
```bash
# 1. 使用Homebrew安装（推荐）
brew install --cask docker

# 或下载安装包
# 访问: https://www.docker.com/products/docker-desktop
# 下载并安装 Docker Desktop for Mac

# 2. 启动Docker Desktop

# 3. 验证安装
docker --version
docker-compose --version
```

**Linux (Ubuntu)**:
```bash
# 1. 安装Docker
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 2. 启动Docker
sudo systemctl start docker
sudo systemctl enable docker

# 3. 添加用户到docker组
sudo usermod -aG docker $USER
newgrp docker

# 4. 验证安装
docker --version
docker-compose --version
```

**详细文档**: [Docker安装指南](docs/installation/01-install-docker.md)

#### 2. 配置环境变量

```bash
# 1. 克隆仓库
git clone https://github.com/hsliuping/TradingAgents-CN.git
cd TradingAgents-CN

# 2. 复制环境变量模板
cp .env.example .env

# 3. 编辑.env文件，配置必需的API密钥
# Windows: notepad .env
# macOS/Linux: nano .env
```

**必需配置**:
```bash
# LLM API密钥（至少配置一个）
DEEPSEEK_API_KEY=sk-your-deepseek-api-key-here
DEEPSEEK_ENABLED=true

# JWT密钥（生产环境必须修改）
JWT_SECRET=your-super-secret-jwt-key-change-in-production

# 数据源（可选，推荐）
TUSHARE_TOKEN=your-tushare-token-here
TUSHARE_ENABLED=true
```

#### 3. 一键部署

**Linux/macOS**:
```bash
# 运行初始化脚本
chmod +x scripts/docker-init.sh
./scripts/docker-init.sh
```

**Windows**:
```powershell
# 运行初始化脚本
.\scripts\docker-init.ps1
```

**手动部署**:
```bash
# 启动所有服务
docker-compose -f docker-compose.v1.0.0.yml up -d

# 查看日志
docker-compose -f docker-compose.v1.0.0.yml logs -f

# 查看服务状态
docker-compose -f docker-compose.v1.0.0.yml ps
```

#### 4. 访问应用

- **前端界面**: http://localhost:5173
- **后端API**: http://localhost:8000
- **API文档**: http://localhost:8000/docs

**默认账号**:
- 用户名: `admin`
- 密码: `admin123`

⚠️ **重要**: 请在首次登录后立即修改密码！

**详细文档**: [Docker部署指南](DOCKER_DEPLOYMENT_v1.0.0.md)

---

## 💻 方式二：本地开发

### 系统要求

| 项目 | 最低要求 | 推荐配置 |
|------|---------|---------|
| **操作系统** | Windows 10/macOS 11/Ubuntu 20.04 | Windows 11/macOS 13/Ubuntu 22.04 |
| **处理器** | 2核 | 4核+ |
| **内存** | 8GB | 16GB+ |
| **磁盘** | 30GB | 100GB+ |
| **Python** | 3.10+ | 3.10.x/3.11.x |
| **Node.js** | 18.x+ | **22.x（项目开发版本）** |
| **MongoDB** | 4.4+ | 5.0+ |
| **Redis** | 6.0+ | 7.0+ |

### 安装步骤

#### 1. 安装Python 3.10+

**Windows**:
```powershell
# 1. 下载Python
# 访问: https://www.python.org/downloads/
# 下载: python-3.10.x-amd64.exe

# 2. 安装时勾选 "Add Python to PATH"

# 3. 验证安装
python --version
pip --version
```

**macOS**:
```bash
# 使用Homebrew安装
brew install python@3.10

# 验证安装
python3.10 --version
pip3 --version
```

**Linux (Ubuntu)**:
```bash
# 安装Python 3.10
sudo apt update
sudo apt install -y software-properties-common
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.10 python3.10-venv python3.10-dev python3-pip

# 验证安装
python3.10 --version
pip3 --version
```

**详细文档**: [Python安装指南](docs/installation/02-install-python.md)

#### 2. 安装Node.js 22.x

**Windows**:
```powershell
# 1. 下载Node.js
# 访问: https://nodejs.org/
# 推荐下载: node-v22.x.x-x64.msi（与项目开发环境一致）

# 2. 安装Node.js

# 3. 验证安装
node --version  # 应该显示 v22.x.x
npm --version

# 4. 安装yarn（必需）
npm install -g yarn

# 验证
yarn --version
```

**macOS**:
```bash
# 使用Homebrew安装（推荐安装最新版本）
brew install node

# 验证安装
node --version  # 应该显示 v22.x.x
npm --version

# 安装yarn（必需）
npm install -g yarn
```

**Linux (Ubuntu)**:
```bash
# 添加NodeSource仓库（Node.js 22.x，推荐）
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -

# 安装Node.js
sudo apt install -y nodejs

# 验证安装
node --version  # 应该显示 v22.x.x
npm --version

# 安装yarn（必需）
npm install -g yarn
```

**详细文档**: [Node.js安装指南](docs/installation/03-install-nodejs.md)

#### 3. 安装MongoDB 4.4+

**Windows**:
```powershell
# 1. 下载MongoDB
# 访问: https://www.mongodb.com/try/download/community
# 下载: mongodb-windows-x86_64-x.x.x-signed.msi

# 2. 安装MongoDB（选择"Complete"安装）

# 3. 启动MongoDB服务
net start MongoDB

# 4. 验证安装
mongo --version
```

**macOS**:
```bash
# 使用Homebrew安装
brew tap mongodb/brew
brew install mongodb-community@4.4

# 启动MongoDB
brew services start mongodb-community@4.4

# 验证安装
mongo --version
```

**Linux (Ubuntu)**:
```bash
# 导入MongoDB公钥
wget -qO - https://www.mongodb.org/static/pgp/server-4.4.asc | sudo apt-key add -

# 添加MongoDB仓库
echo "deb [ arch=amd64,arm64 ] https://repo.mongodb.org/apt/ubuntu focal/mongodb-org/4.4 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-4.4.list

# 安装MongoDB
sudo apt update
sudo apt install -y mongodb-org

# 启动MongoDB
sudo systemctl start mongod
sudo systemctl enable mongod

# 验证安装
mongo --version
```

#### 4. 安装Redis 6.0+

**Windows**:
```powershell
# 使用WSL 2安装Redis
wsl --install -d Ubuntu
wsl

# 在WSL中安装Redis
sudo apt update
sudo apt install -y redis-server

# 启动Redis
sudo service redis-server start

# 验证安装
redis-cli --version
```

**macOS**:
```bash
# 使用Homebrew安装
brew install redis

# 启动Redis
brew services start redis

# 验证安装
redis-cli --version
```

**Linux (Ubuntu)**:
```bash
# 安装Redis
sudo apt update
sudo apt install -y redis-server

# 启动Redis
sudo systemctl start redis-server
sudo systemctl enable redis-server

# 验证安装
redis-cli --version
```

#### 5. 配置项目

```bash
# 1. 克隆仓库
git clone https://github.com/hsliuping/TradingAgents-CN.git
cd TradingAgents-CN

# 2. 配置环境变量
cp .env.example .env
# 编辑.env文件，配置API密钥和数据库连接

# 3. 创建Python虚拟环境
python -m venv .venv

# 4. 激活虚拟环境
# Windows:
.\.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 5. 安装Python依赖
pip install --upgrade pip
pip install -r requirements.txt

# 6. 安装前端依赖（必须使用yarn）
cd frontend
yarn install
cd ..

# 7. 初始化数据库
python scripts/init_system_data.py
```

#### 6. 启动服务

**启动后端**:
```bash
# 激活虚拟环境
source .venv/bin/activate  # macOS/Linux
.\.venv\Scripts\activate   # Windows

# 启动后端服务
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**启动前端**:
```bash
# 进入前端目录
cd frontend

# 启动开发服务器（使用yarn）
yarn dev
```

#### 7. 访问应用

- **前端界面**: http://localhost:5173
- **后端API**: http://localhost:8000
- **API文档**: http://localhost:8000/docs

**详细文档**: [本地开发指南](docs/v1.0.0-preview/02-development/01-local-setup.md)

---

## ✅ 验证安装

### Docker部署验证

```bash
# 1. 检查Docker服务
docker ps

# 2. 检查服务状态
docker-compose -f docker-compose.v1.0.0.yml ps

# 3. 访问前端
curl http://localhost:5173

# 4. 访问后端
curl http://localhost:8000/health

# 5. 查看日志
docker-compose -f docker-compose.v1.0.0.yml logs -f
```

### 本地开发验证

```bash
# 1. 检查Python
python --version  # 应该 >= 3.10

# 2. 检查Node.js
node --version  # 应该 >= 16.x

# 3. 检查MongoDB
mongo --eval "db.version()"

# 4. 检查Redis
redis-cli ping  # 应该返回 PONG

# 5. 检查后端
curl http://localhost:8000/health

# 6. 检查前端
curl http://localhost:5173
```

---

## 🐛 常见问题

### Docker相关

**问题**: Docker Desktop启动失败

**解决方案**:
- Windows: 检查WSL 2是否正确安装
- macOS: 检查系统版本是否满足要求
- 重启Docker Desktop
- 查看Docker日志

**问题**: 端口被占用

**解决方案**:
```bash
# 修改docker-compose.v1.0.0.yml中的端口映射
ports:
  - "5174:80"  # 改为其他端口
```

### Python相关

**问题**: 找不到python命令

**解决方案**:
- 确保安装时勾选了"Add Python to PATH"
- 手动添加Python到系统PATH
- 使用`python3`命令（macOS/Linux）

**问题**: pip安装包失败

**解决方案**:
```bash
# 使用国内镜像
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
```

### Node.js相关

**问题**: npm安装依赖失败

**解决方案**:
```bash
# 清除缓存
npm cache clean --force

# 使用国内镜像
npm config set registry https://registry.npmmirror.com
npm install
```

### 数据库相关

**问题**: MongoDB连接失败

**解决方案**:
- 检查MongoDB服务是否启动
- 检查端口27017是否被占用
- 检查.env中的连接字符串

**问题**: Redis连接失败

**解决方案**:
- 检查Redis服务是否启动
- 检查端口6379是否被占用
- 检查.env中的连接字符串

---

## 📚 更多资源

### 安装指南

- [Docker安装指南](docs/installation/01-install-docker.md)
- [Python安装指南](docs/installation/02-install-python.md)
- [Node.js安装指南](docs/installation/03-install-nodejs.md)

### 部署指南

- [Docker部署指南](DOCKER_DEPLOYMENT_v1.0.0.md)
- [快速开始指南](QUICKSTART_v1.0.0.md)
- [本地开发指南](docs/v1.0.0-preview/02-development/01-local-setup.md)

### 技术文档

- [完整技术文档](docs/v1.0.0-preview/)
- [API文档](http://localhost:8000/docs)
- [架构文档](docs/v1.0.0-preview/01-architecture/)

---

## 🤝 获取帮助

如有问题，请联系：

- **GitHub Issues**: https://github.com/hsliuping/TradingAgents-CN/issues
- **QQ群**: 782124367
- **邮箱**: hsliup@163.com

---

**更新日期**: 2025-10-15  
**适用版本**: TradingAgents-CN v1.0.0-preview  
**维护者**: TradingAgents-CN Team

