# TradingAgents-CN 后端启动指南

## 🚀 启动方式

### 1. 推荐方式：使用 Python 模块启动

```bash
# 开发环境（推荐）
python -m app

# 或者使用完整路径
python -m app.main
```

### 2. 使用启动脚本

#### Windows
```cmd
# 批处理文件
start_backend.bat

# 或者 Python 脚本
python start_backend.py
```

#### Linux/macOS
```bash
# Shell 脚本
./start_backend.sh

# 或者 Python 脚本
python start_backend.py
```

### 3. 生产环境启动

```bash
# 生产环境优化启动
python start_production.py

# 或者直接使用 uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## 🔧 配置说明

### 开发环境特性
- ✅ **热重载**: 代码修改自动重启
- ✅ **详细日志**: 显示详细的调试信息
- ✅ **API文档**: 自动生成 Swagger 文档
- ✅ **文件监控优化**: 减少不必要的文件监控

### 生产环境特性
- ✅ **多进程**: 使用多个 worker 进程
- ✅ **性能优化**: 使用 uvloop 和 httptools
- ✅ **日志优化**: 减少日志输出
- ✅ **安全性**: 禁用调试功能

## 📁 项目结构

```
TradingAgentsCN/
├── app/                    # 后端应用目录（原webapi）
│   ├── __main__.py        # 模块启动入口
│   ├── main.py            # FastAPI 应用
│   ├── core/              # 核心配置
│   │   ├── config.py      # 主配置文件
│   │   └── dev_config.py  # 开发环境配置
│   ├── routers/           # API 路由
│   ├── services/          # 业务逻辑
│   └── models/            # 数据模型
├── start_backend.py       # 跨平台启动脚本
├── start_backend.bat      # Windows 启动脚本
├── start_backend.sh       # Linux/macOS 启动脚本
└── start_production.py    # 生产环境启动脚本
```

## 🛠️ 文件监控优化

### 问题解决
如果遇到频繁的文件变化检测日志：
```
watchfiles.main | INFO | 1 change detected
```

### 解决方案
1. **使用优化的启动方式**: `python -m app`
2. **配置文件排除**: 自动排除缓存、日志等文件
3. **监控延迟**: 设置合理的重载延迟
4. **日志级别**: 调整 watchfiles 日志级别

### 排除的文件类型
- Python 缓存文件 (`*.pyc`, `__pycache__`)
- 版本控制文件 (`.git`)
- IDE 配置文件 (`.vscode`, `.idea`)
- 日志文件 (`*.log`)
- 临时文件 (`*.tmp`, `*.swp`)
- 数据库文件 (`*.db`, `*.sqlite`)
- 前端文件 (`*.js`, `*.css`, `node_modules`)

## 🔍 故障排除

### 常见问题

#### 1. ModuleNotFoundError: No module named 'webapi'
**原因**: 旧的 import 语句未更新
**解决**: 运行 `python fix_imports.py` 批量修复

#### 2. 频繁的文件变化检测
**原因**: 文件监控过于敏感
**解决**: 使用 `python -m app` 启动，已优化监控配置

#### 3. 端口被占用
**原因**: 端口 8000 已被其他程序使用
**解决**: 
```bash
# 查看端口占用
netstat -ano | findstr :8000  # Windows
lsof -i :8000                 # Linux/macOS

# 修改端口
export PORT=8001
python -m app
```

#### 4. 权限问题
**原因**: 脚本没有执行权限
**解决**:
```bash
chmod +x start_backend.sh  # Linux/macOS
```

## 📊 性能监控

### 开发环境
- 访问 http://localhost:8000/docs 查看 API 文档
- 访问 http://localhost:8000/health 检查服务状态

### 生产环境
- 使用 `start_production.py` 启动
- 配置反向代理 (Nginx)
- 设置进程管理 (systemd, supervisor)

## 🔄 版本迁移

### 从旧版本迁移
1. **备份配置**: 备份 `.env` 文件
2. **更新代码**: 拉取最新代码
3. **修复导入**: 运行 `python fix_imports.py`
4. **测试启动**: 使用 `python -m app` 测试
5. **验证功能**: 检查 API 功能正常

### 配置迁移
- 旧的 `webapi` 配置自动兼容
- 环境变量保持不变
- 数据库连接配置不变

## 📝 开发建议

### 推荐的开发流程
1. **启动后端**: `python -m app`
2. **启动前端**: `npm run dev` (在 frontend 目录)
3. **开发调试**: 使用 API 文档测试接口
4. **代码提交**: 确保测试通过后提交

### 代码规范
- 使用 `from app.xxx import yyy` 导入模块
- 避免循环导入
- 保持代码格式一致

## 🎯 下一步

- [ ] 配置 Docker 容器化部署
- [ ] 设置 CI/CD 自动化部署
- [ ] 添加性能监控和日志收集
- [ ] 配置负载均衡和高可用

---

**🎉 现在您可以使用 `python -m app` 启动后端服务了！**
