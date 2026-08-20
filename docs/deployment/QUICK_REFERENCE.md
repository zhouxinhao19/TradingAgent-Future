# 绿色版部署快速参考

## 🚀 常用命令

### 1. 只同步文件（不打包）

```powershell
# 完整同步和构建
powershell -ExecutionPolicy Bypass -File scripts\deployment\sync_and_build_only.ps1

# 只同步代码（跳过前端）
powershell -ExecutionPolicy Bypass -File scripts\deployment\sync_and_build_only.ps1 -SkipFrontend

# 只构建前端（跳过同步）
powershell -ExecutionPolicy Bypass -File scripts\deployment\sync_and_build_only.ps1 -SkipSync
```

---

### 2. 迁移到嵌入式 Python

```powershell
# 一键迁移（推荐）
powershell -ExecutionPolicy Bypass -File scripts\deployment\migrate_to_embedded_python.ps1

# 分步执行
powershell -ExecutionPolicy Bypass -File scripts\deployment\setup_embedded_python.ps1
powershell -ExecutionPolicy Bypass -File scripts\deployment\update_scripts_for_embedded_python.ps1
```

---

### 3. 打包完整版本

```powershell
# 完整打包（包含嵌入式 Python）
powershell -ExecutionPolicy Bypass -File scripts\deployment\build_portable_package.ps1

# 跳过同步（使用现有文件）
powershell -ExecutionPolicy Bypass -File scripts\deployment\build_portable_package.ps1 -SkipSync

# 跳过嵌入式 Python（如果已安装）
powershell -ExecutionPolicy Bypass -File scripts\deployment\build_portable_package.ps1 -SkipEmbeddedPython
```

---

### 4. 启动绿色版服务

```powershell
cd C:\TradingAgentsCN\release\TradingAgentsCN-portable

# 启动所有服务
powershell -ExecutionPolicy Bypass -File .\start_all.ps1

# 只启动 MongoDB 和 Redis
powershell -ExecutionPolicy Bypass -File .\start_services_clean.ps1

# 停止所有服务
powershell -ExecutionPolicy Bypass -File .\stop_all.ps1
```

---

## 📊 工作流程

### 开发阶段

```
修改代码
    ↓
同步到绿色版（不打包）
    ↓
测试
    ↓
发现问题 → 修改代码（循环）
```

**命令**：
```powershell
# 1. 同步
powershell -ExecutionPolicy Bypass -File scripts\deployment\sync_and_build_only.ps1

# 2. 测试
cd release\TradingAgentsCN-portable
.\start_all.ps1
```

---

### 发布阶段

```
确认功能正常
    ↓
迁移到嵌入式 Python（首次）
    ↓
打包完整版本
    ↓
测试安装包
    ↓
发布
```

**命令**：
```powershell
# 1. 迁移到嵌入式 Python（首次）
powershell -ExecutionPolicy Bypass -File scripts\deployment\migrate_to_embedded_python.ps1

# 2. 打包
powershell -ExecutionPolicy Bypass -File scripts\deployment\build_portable_package.ps1

# 3. 测试（在干净系统）
# 解压 ZIP → 运行 start_all.ps1
```

---

## 🎯 脚本功能对比

| 脚本 | 同步 | 构建前端 | 嵌入式Python | 打包ZIP | 用途 |
|------|------|---------|-------------|---------|------|
| `sync_and_build_only.ps1` | ✅ | ✅ | ❌ | ❌ | 开发测试 |
| `migrate_to_embedded_python.ps1` | ❌ | ❌ | ✅ | ❌ | 首次迁移 |
| `build_portable_package.ps1` | ✅ | ✅ | ✅ | ✅ | 发布版本 |
| `setup_embedded_python.ps1` | ❌ | ❌ | ✅ | ❌ | 单独安装Python |
| `update_scripts_for_embedded_python.ps1` | ❌ | ❌ | ❌ | ❌ | 更新脚本 |

---

## 📁 目录结构

```
TradingAgentsCN/
├── scripts/
│   └── deployment/
│       ├── sync_and_build_only.ps1              # 只同步不打包
│       ├── migrate_to_embedded_python.ps1       # 一键迁移
│       ├── setup_embedded_python.ps1            # 安装嵌入式Python
│       ├── update_scripts_for_embedded_python.ps1  # 更新脚本
│       ├── build_portable_package.ps1           # 完整打包
│       └── sync_to_portable.ps1                 # 同步文件
├── release/
│   ├── TradingAgentsCN-portable/                # 绿色版目录
│   │   ├── vendors/
│   │   │   └── python/                          # 嵌入式Python
│   │   ├── app/
│   │   ├── start_all.ps1
│   │   └── start_services_clean.ps1
│   └── packages/                                # 打包输出
│       └── TradingAgentsCN-Portable-*.zip
└── docs/
    └── deployment/
        ├── EMBEDDED_PYTHON_GUIDE.md             # 详细指南
        ├── PORTABLE_FAQ.md                      # 常见问题
        └── QUICK_REFERENCE.md                   # 本文档
```

---

## 🔧 常见任务

### 任务 1：修改后端代码后测试

```powershell
# 1. 同步（跳过前端构建）
powershell -ExecutionPolicy Bypass -File scripts\deployment\sync_and_build_only.ps1 -SkipFrontend

# 2. 重启后端
cd release\TradingAgentsCN-portable
.\stop_all.ps1
.\start_all.ps1
```

---

### 任务 2：修改前端代码后测试

```powershell
# 1. 只构建前端
powershell -ExecutionPolicy Bypass -File scripts\deployment\sync_and_build_only.ps1 -SkipSync

# 2. 重启 Nginx
cd release\TradingAgentsCN-portable
# 找到 nginx 进程并重启
```

---

### 任务 3：首次创建绿色版

```powershell
# 1. 完整打包（自动安装嵌入式Python）
powershell -ExecutionPolicy Bypass -File scripts\deployment\build_portable_package.ps1

# 2. 测试
cd release\TradingAgentsCN-portable
.\start_all.ps1
```

---

### 任务 4：更新现有绿色版

```powershell
# 1. 同步最新代码
powershell -ExecutionPolicy Bypass -File scripts\deployment\sync_and_build_only.ps1

# 2. 如果需要，重新打包
powershell -ExecutionPolicy Bypass -File scripts\deployment\build_portable_package.ps1 -SkipSync
```

---

## 🧪 测试检查清单

### 开发测试

- [ ] 后端 API 正常响应（http://localhost:8000/docs）
- [ ] 前端页面正常加载（http://localhost）
- [ ] MongoDB 连接正常
- [ ] Redis 连接正常
- [ ] 日志无错误

### 发布前测试

- [ ] 在干净的 Windows 系统测试（无 Python）
- [ ] 所有功能正常
- [ ] 包大小合理（~430 MB）
- [ ] 解压路径包含中文/空格也能运行
- [ ] 文档齐全

---

## 💡 提示和技巧

### 提示 1：加速前端构建

```powershell
# 使用 Yarn 缓存
cd frontend
yarn install --frozen-lockfile --prefer-offline
```

---

### 提示 2：使用国内镜像加速 pip

```powershell
# 在 setup_embedded_python.ps1 中添加
& $pythonExe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

---

### 提示 3：并行打包多个版本

```powershell
# 使用不同的 Python 版本
Start-Job { powershell -ExecutionPolicy Bypass -File scripts\deployment\build_portable_package.ps1 -PythonVersion "3.10.11" }
Start-Job { powershell -ExecutionPolicy Bypass -File scripts\deployment\build_portable_package.ps1 -PythonVersion "3.11.7" }
```

---

### 提示 4：快速清理

```powershell
# 清理所有生成的文件
Remove-Item release\TradingAgentsCN-portable -Recurse -Force
Remove-Item release\packages\* -Force
```

---

## 📞 获取帮助

### 查看脚本帮助

```powershell
Get-Help scripts\deployment\migrate_to_embedded_python.ps1 -Detailed
```

### 查看详细文档

- **嵌入式 Python 指南**：`docs/deployment/EMBEDDED_PYTHON_GUIDE.md`
- **常见问题解答**：`docs/deployment/PORTABLE_FAQ.md`
- **Python 独立性分析**：`docs/deployment/portable-python-independence.md`

---

## 🎉 快速开始（新用户）

```powershell
# 1. 克隆项目
git clone <repository-url>
cd TradingAgentsCN

# 2. 一键创建绿色版
powershell -ExecutionPolicy Bypass -File scripts\deployment\build_portable_package.ps1

# 3. 测试
cd release\TradingAgentsCN-portable
.\start_all.ps1

# 4. 访问
# 浏览器打开: http://localhost
# 默认账号: admin/CHANGE_ME_ADMIN_PASSWORD
```

---

## 📊 性能参考

| 操作 | 时间 | 说明 |
|------|------|------|
| 同步代码 | ~30秒 | 取决于文件数量 |
| 构建前端 | ~2-3分钟 | 首次较慢，后续有缓存 |
| 安装嵌入式Python | ~5-10分钟 | 取决于网速 |
| 打包ZIP | ~2-3分钟 | 取决于磁盘速度 |
| **总计（首次）** | **~15-20分钟** | 包含所有步骤 |
| **总计（更新）** | **~5分钟** | 跳过Python安装 |

---

## 🔗 相关链接

- [Python 官方下载](https://www.python.org/downloads/windows/)
- [pip 文档](https://pip.pypa.io/)
- [PowerShell 文档](https://docs.microsoft.com/powershell/)

