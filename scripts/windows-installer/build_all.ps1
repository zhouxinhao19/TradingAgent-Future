param(
    [string]$Version = "1.0.0",
    [int]$BackendPort = 8000,
    [int]$MongoPort = 27017,
    [int]$RedisPort = 6379,
    [int]$NginxPort = 80,
    [string]$NsisPath,
    [string]$OutputDir = "release\portable",
    [switch]$SkipPortable = $false,
    [switch]$SkipInstaller = $false
)

$ErrorActionPreference = "Stop"

# 日志函数
function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$timestamp] [$Level] $Message"
}

Write-Log "=========================================="
Write-Log "TradingAgentsCN Windows 安装程序构建"
Write-Log "=========================================="
Write-Log "版本: $Version"
Write-Log "后端端口: $BackendPort"
Write-Log "MongoDB 端口: $MongoPort"
Write-Log "Redis 端口: $RedisPort"
Write-Log "Nginx 端口: $NginxPort"
Write-Log "输出目录: $OutputDir"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Write-Log "项目根目录: $root"

# 第一步：构建便携版本
if (-not $SkipPortable) {
    Write-Log ""
    Write-Log "========== 步骤 1: 构建便携版本 =========="
    $portableScript = Join-Path $PSScriptRoot "prepare\build_portable.ps1"
    
    if (-not (Test-Path $portableScript)) {
        Write-Log "build_portable.ps1 未找到: $portableScript" "ERROR"
        exit 1
    }
    
    try {
        Write-Log "执行 build_portable.ps1..."
        $portableDir = & $portableScript -OutputDir $OutputDir
        Write-Log "便携版本构建完成: $portableDir"
    } catch {
        Write-Log "便携版本构建失败: $_" "ERROR"
        exit 1
    }
} else {
    Write-Log "跳过便携版本构建"
    $portableDir = Join-Path $root $OutputDir
}

# 第二步：构建安装程序
if (-not $SkipInstaller) {
    Write-Log ""
    Write-Log "========== 步骤 2: 构建安装程序 =========="
    $installerScript = Join-Path $PSScriptRoot "build\build_installer.ps1"
    
    if (-not (Test-Path $installerScript)) {
        Write-Log "build_installer.ps1 未找到: $installerScript" "ERROR"
        exit 1
    }
    
    try {
        Write-Log "执行 build_installer.ps1..."
        $args = @(
            "-Version", $Version,
            "-BackendPort", $BackendPort,
            "-MongoPort", $MongoPort,
            "-RedisPort", $RedisPort,
            "-NginxPort", $NginxPort
        )
        
        if ($NsisPath) {
            $args += "-NsisPath", $NsisPath
        }
        
        & $installerScript @args
        Write-Log "安装程序构建完成"
    } catch {
        Write-Log "安装程序构建失败: $_" "ERROR"
        exit 1
    }
} else {
    Write-Log "跳过安装程序构建"
}

Write-Log ""
Write-Log "=========================================="
Write-Log "构建完成！"
Write-Log "=========================================="
Write-Log "便携版本位置: $portableDir"
Write-Log "安装程序位置: $(Join-Path $PSScriptRoot "nsis\TradingAgentsCNSetup-$Version.exe")"

