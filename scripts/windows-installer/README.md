# TradingAgentsCN Windows 安装程序

本目录包含用于构建 TradingAgentsCN Windows 安装程序的脚本和配置文件。

## 目录结构

```
windows-installer/
├── build/                    # 安装程序构建脚本
│   └── build_installer.ps1  # NSIS 安装程序构建脚本
├── nsis/                     # NSIS 配置文件
│   └── installer.nsi        # NSIS 安装脚本
├── prepare/                  # 便携版本准备脚本
│   ├── build_portable.ps1   # 构建便携版本
│   └── probe_ports.ps1      # 端口探测脚本
├── build_all.ps1            # 完整构建脚本
├── test_installer.ps1       # 安装程序测试脚本
└── README.md                 # 本文件
```

## 前置要求

### 必需软件

1. **NSIS (Nullsoft Scriptable Install System)**
   - 下载: https://nsis.sourceforge.io/
   - 安装到默认位置或指定 `-NsisPath` 参数

2. **PowerShell 5.0+**
   - Windows 10/11 已内置

3. **Python 3.8+**
   - 用于构建便携版本

4. **Node.js 14+**
   - 用于构建前端（可选，如果已有前端构建）

### 系统要求

- Windows 10/11
- 管理员权限（用于安装服务）
- 至少 2GB 可用磁盘空间

## 使用方法

### 1. 构建完整安装程序

```powershell
# 基本用法（使用默认端口）
.\build_all.ps1

# 指定自定义端口
.\build_all.ps1 -BackendPort 8080 -MongoPort 27018 -RedisPort 6380 -NginxPort 8888

# 指定 NSIS 路径
.\build_all.ps1 -NsisPath "C:\Program Files\NSIS"

# 仅构建便携版本
.\build_all.ps1 -SkipInstaller

# 仅构建安装程序
.\build_all.ps1 -SkipPortable
```

### 2. 构建便携版本

```powershell
# 基本用法
.\prepare\build_portable.ps1

# 指定输出目录
.\prepare\build_portable.ps1 -OutputDir "D:\portable"
```

### 3. 构建安装程序

```powershell
# 基本用法
.\build\build_installer.ps1

# 指定自定义端口
.\build\build_installer.ps1 -BackendPort 8080 -MongoPort 27018

# 指定 NSIS 路径
.\build\build_installer.ps1 -NsisPath "C:\Program Files\NSIS"
```

### 4. 测试安装程序

```powershell
# 基本用法
.\test_installer.ps1

# 指定安装程序路径
.\test_installer.ps1 -InstallerPath "C:\path\to\installer.exe"
```

## 功能特性

### 端口配置

安装程序支持自定义以下服务的端口：

- **Backend**: FastAPI 后端服务（默认 8000）
- **MongoDB**: 数据库服务（默认 27017）
- **Redis**: 缓存服务（默认 6379）
- **Nginx**: Web 服务器（默认 80）

### 端口检测

安装程序包含自动端口检测功能：

- 检测端口是否被占用
- 自动建议可用的替代端口
- 验证端口号的有效性
- 防止端口重复配置

### 性能优化

- 使用并行 PowerShell 作业加快端口检测
- 优化 NSIS 脚本以提高 UI 响应性
- 添加详细日志输出便于调试

## 输出文件

构建完成后，输出文件位置：

- **便携版本**: `release/portable/`
- **安装程序**: `scripts/windows-installer/nsis/TradingAgentsCNSetup-{version}.exe`

## 故障排除

### NSIS 未找到

```powershell
# 指定 NSIS 安装路径
.\build_all.ps1 -NsisPath "C:\Program Files (x86)\NSIS"
```

### 端口被占用

安装程序会自动检测并建议可用端口。如果需要手动指定：

```powershell
.\build_all.ps1 -BackendPort 8080 -MongoPort 27018
```

### 构建失败

查看详细日志输出，检查：

1. 是否有足够的磁盘空间
2. 是否有管理员权限
3. 是否所有依赖都已安装

## 开发指南

### 修改安装脚本

编辑 `nsis/installer.nsi` 文件来自定义安装过程。

### 修改便携版本

编辑 `prepare/build_portable.ps1` 来改变便携版本的构建方式。

### 添加新的服务

1. 在 `installer.nsi` 中添加新的端口配置
2. 在 `probe_ports.ps1` 中添加端口检测逻辑
3. 在 `build_portable.ps1` 中添加相应的配置文件

## 许可证

MIT License

