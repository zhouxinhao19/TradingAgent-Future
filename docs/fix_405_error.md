# 修复前端访问后端 405 错误

## 问题描述

前端访问后端 API 时报错：
```
POST http://34.92.173.2/api/auth/login 405 (Not Allowed)
```

## 问题原因

前端 Docker 镜像在构建时，`VITE_API_BASE_URL` 已经固化为 `http://localhost:8000`。当前端容器运行时，它尝试访问 `http://34.92.173.2/api/auth/login`（80端口），但后端实际运行在 8000 端口，导致请求被拒绝。

**核心问题**：
1. 前端镜像构建时的 API 地址已固化
2. 前端和后端使用不同端口（80 vs 8000）
3. 存在跨域访问问题

---

## 解决方案

### 方案 1：使用 Nginx 反向代理（推荐）⭐

**优势**：
- ✅ 前端和后端通过同一端口访问，无跨域问题
- ✅ 统一入口，便于后续配置 HTTPS
- ✅ 可以添加负载均衡、缓存等功能
- ✅ 生产环境最佳实践

**步骤**：

#### 1. 停止当前服务

```bash
cd /home/hsliup/TradingAgents-CN
docker-compose -f docker-compose.hub.yml down
```

#### 2. 使用带 Nginx 的配置启动

```bash
# 使用 Nginx 反向代理配置
docker-compose -f docker-compose.hub.nginx.yml up -d

# 查看服务状态
docker-compose -f docker-compose.hub.nginx.yml ps
```

#### 3. 访问系统

- **前端**：`http://34.92.173.2/`（80端口）
- **后端 API**：`http://34.92.173.2/api/`（通过 Nginx 代理到后端 8000 端口）

**架构**：
```
用户浏览器
    ↓
Nginx (80端口)
    ├─→ / → Frontend (内部80端口)
    └─→ /api/ → Backend (内部8000端口)
```

---

### 方案 2：重新构建前端镜像（适合开发环境）

如果需要自定义 API 地址，需要重新构建前端镜像。

#### 1. 修改前端环境变量

编辑 `frontend/.env.production`：

```bash
VITE_API_BASE_URL=http://34.92.173.2:8000
```

#### 2. 重新构建前端镜像

```bash
cd frontend
docker build -t hsliup/tradingagents-frontend:custom .
docker push hsliup/tradingagents-frontend:custom
```

#### 3. 修改 docker-compose.hub.yml

```yaml
frontend:
  image: hsliup/tradingagents-frontend:custom  # 使用自定义镜像
  ports:
    - "3000:80"  # 前端使用 3000 端口
```

#### 4. 启动服务

```bash
docker-compose -f docker-compose.hub.yml up -d
```

#### 5. 访问系统

- **前端**：`http://34.92.173.2:3000`
- **后端 API**：`http://34.92.173.2:8000`

---

### 方案 3：临时解决方案（仅用于测试）

如果只是临时测试，可以使用浏览器插件绕过 CORS 限制。

**不推荐用于生产环境！**

---

## 推荐配置

### 使用 Nginx 反向代理（方案 1）

这是生产环境的最佳实践，配置文件已经准备好：

```bash
# 1. 停止当前服务
docker-compose -f docker-compose.hub.yml down

# 2. 启动带 Nginx 的服务
docker-compose -f docker-compose.hub.nginx.yml up -d

# 3. 等待服务启动
sleep 15

# 4. 验证服务
curl http://localhost/health
curl http://localhost/api/health

# 5. 导入配置数据（如果还没导入）
python3 scripts/import_config_and_create_user.py

# 6. 重启后端
docker restart tradingagents-backend

# 7. 访问前端
# 浏览器打开: http://34.92.173.2
```

---

## 验证部署

### 1. 检查容器状态

```bash
docker-compose -f docker-compose.hub.nginx.yml ps
```

**预期输出**：
```
NAME                      STATUS          PORTS
tradingagents-mongodb     Up (healthy)    0.0.0.0:27017->27017/tcp
tradingagents-redis       Up (healthy)    0.0.0.0:6379->6379/tcp
tradingagents-backend     Up (healthy)    8000/tcp
tradingagents-frontend    Up (healthy)    80/tcp
tradingagents-nginx       Up (healthy)    0.0.0.0:80->80/tcp
```

### 2. 测试 API 访问

```bash
# 测试健康检查
curl http://localhost/health

# 测试后端 API
curl http://localhost/api/health

# 测试前端
curl -I http://localhost/
```

### 3. 浏览器测试

1. 打开浏览器：`http://34.92.173.2`
2. 打开开发者工具（F12）→ Network 标签
3. 尝试登录（admin/admin123）
4. 检查请求：
   - ✅ 请求地址应该是：`http://34.92.173.2/api/auth/login`
   - ✅ 状态码应该是：`200 OK`（而不是 405）

---

## 常见问题

### Q1: 为什么不能直接修改 docker-compose.hub.yml 中的 VITE_API_BASE_URL？

**A**: 因为 Vue 3 使用 Vite 构建工具，环境变量在**构建时**就已经被替换到 JavaScript 代码中了。Docker 镜像已经包含了构建好的静态文件，运行时修改环境变量不会生效。

### Q2: Nginx 反向代理会影响性能吗？

**A**: 不会。Nginx 是高性能的反向代理服务器，反而可以：
- 提供静态文件缓存
- 启用 Gzip 压缩
- 实现负载均衡
- 提供 SSL/TLS 终止

### Q3: 如何配置 HTTPS？

**A**: 使用 Nginx 反向代理后，只需要：
1. 获取 SSL 证书（Let's Encrypt）
2. 修改 `nginx/nginx.conf` 添加 SSL 配置
3. 重启 Nginx 容器

详细步骤参考：`docs/deploy_demo_system.md` 的"安全加固"章节。

### Q4: 可以同时暴露 8000 端口吗？

**A**: 可以，但不推荐。如果需要直接访问后端 API（用于调试），可以在 `docker-compose.hub.nginx.yml` 中添加：

```yaml
backend:
  ports:
    - "8000:8000"  # 添加这一行
```

但生产环境应该只通过 Nginx 访问。

---

## 架构对比

### 原配置（有问题）

```
浏览器 → http://34.92.173.2:80 → Frontend (容器)
浏览器 → http://34.92.173.2:8000 → Backend (容器)
         ❌ 跨域问题
         ❌ 前端镜像中的 API 地址不匹配
```

### Nginx 反向代理（推荐）

```
浏览器 → http://34.92.173.2:80 → Nginx (容器)
                                    ├─→ / → Frontend (容器)
                                    └─→ /api/ → Backend (容器)
         ✅ 同源访问，无跨域问题
         ✅ 统一入口
         ✅ 便于配置 HTTPS
```

---

## 总结

**立即执行**：

```bash
# 1. 停止当前服务
cd /home/hsliup/TradingAgents-CN
docker-compose -f docker-compose.hub.yml down

# 2. 启动 Nginx 反向代理配置
docker-compose -f docker-compose.hub.nginx.yml up -d

# 3. 等待服务启动
sleep 15

# 4. 导入配置数据（如果还没导入）
python3 scripts/import_config_and_create_user.py

# 5. 重启后端
docker restart tradingagents-backend

# 6. 访问系统
echo "前端地址: http://34.92.173.2"
echo "默认账号: admin / admin123"
```

**问题解决！** 🎉

