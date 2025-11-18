param(
    [string]$InstallerPath,
    [string]$TestDir = "C:\TradingAgentsCN_Test"
)

$ErrorActionPreference = "Stop"

# 日志函数
function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$timestamp] [$Level] $Message"
}

Write-Log "=========================================="
Write-Log "TradingAgentsCN 安装程序测试"
Write-Log "=========================================="

# 检查安装程序
if (-not $InstallerPath) {
    $root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
    $InstallerPath = Join-Path $root "scripts\windows-installer\nsis\TradingAgentsCNSetup-1.0.0.exe"
}

Write-Log "安装程序路径: $InstallerPath"

if (-not (Test-Path $InstallerPath)) {
    Write-Log "安装程序未找到: $InstallerPath" "ERROR"
    exit 1
}

Write-Log "安装程序已找到"

# 检查安装程序文件大小
$fileSize = (Get-Item $InstallerPath).Length / 1MB
Write-Log "安装程序大小: $([Math]::Round($fileSize, 2)) MB"

# 检查 NSIS 是否安装
Write-Log ""
Write-Log "检查 NSIS 安装..."
$nsisPath = $null
$candidates = @()
if ($env:ProgramFiles) { $candidates += (Join-Path $env:ProgramFiles 'NSIS') }
$pf86 = ${env:ProgramFiles(x86)}
if ($pf86) { $candidates += (Join-Path $pf86 'NSIS') }

foreach ($p in $candidates) {
    $exe = Join-Path $p 'makensis.exe'
    if (Test-Path -LiteralPath $exe) {
        $nsisPath = $p
        Write-Log "找到 NSIS: $nsisPath"
        break
    }
}

if (-not $nsisPath) {
    Write-Log "NSIS 未安装，无法验证安装程序内容" "WARNING"
} else {
    Write-Log "NSIS 已安装，可以进行完整测试"
}

# 检查便携版本
Write-Log ""
Write-Log "检查便携版本..."
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$portableDir = Join-Path $root "release\portable"

if (Test-Path $portableDir) {
    Write-Log "便携版本目录已存在: $portableDir"
    
    # 检查关键文件
    $requiredDirs = @("app", "scripts\installer", "runtime", "logs", "data")
    foreach ($dir in $requiredDirs) {
        $fullPath = Join-Path $portableDir $dir
        if (Test-Path $fullPath) {
            Write-Log "✓ $dir 目录存在"
        } else {
            Write-Log "✗ $dir 目录缺失" "WARNING"
        }
    }
    
    # 检查关键文件
    $requiredFiles = @(".env.example", "runtime\nginx.conf")
    foreach ($file in $requiredFiles) {
        $fullPath = Join-Path $portableDir $file
        if (Test-Path $fullPath) {
            Write-Log "✓ $file 文件存在"
        } else {
            Write-Log "✗ $file 文件缺失" "WARNING"
        }
    }
} else {
    Write-Log "便携版本目录不存在: $portableDir" "WARNING"
}

Write-Log ""
Write-Log "=========================================="
Write-Log "测试完成"
Write-Log "=========================================="
Write-Log "建议："
Write-Log "1. 运行安装程序进行完整安装测试"
Write-Log "2. 验证所有服务是否正常启动"
Write-Log "3. 检查 Web 界面是否可访问"
Write-Log "4. 测试卸载功能"

