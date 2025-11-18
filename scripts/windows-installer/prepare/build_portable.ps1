param(
  [string]$OutputDir = "release\portable",
  [switch]$Verbose = $false
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$out = Join-Path $root $OutputDir

# 日志函数
function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$timestamp] [$Level] $Message"
}

Write-Log "开始构建便携版本..."
Write-Log "输出目录: $out"

$frontendDir = Join-Path $root "frontend"
$frontendDist = Join-Path $frontendDir "dist"
$requirements = Join-Path $root "requirements.txt"

Write-Log "创建目录结构..."
New-Item -ItemType Directory -Force -Path $out | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $out "runtime") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $out "logs") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $out "data\mongodb\db") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $out "data\redis\data") | Out-Null
Write-Log "目录结构创建完成"

Write-Log "复制配置文件..."
if (Test-Path (Join-Path $root ".env.example")) {
  Copy-Item -Force (Join-Path $root ".env.example") (Join-Path $out ".env.example")
  Write-Log ".env.example 已复制"
}

Write-Log "复制应用文件..."
Copy-Item -Recurse -Force (Join-Path $root "app") (Join-Path $out "app")
Write-Log "app 目录已复制"

Copy-Item -Recurse -Force (Join-Path $root "scripts\installer") (Join-Path $out "scripts\installer")
Write-Log "scripts\installer 目录已复制"

if (Test-Path (Join-Path $root "vendors")) {
  Copy-Item -Recurse -Force (Join-Path $root "vendors") (Join-Path $out "vendors")
  Write-Log "vendors 目录已复制"
}

Write-Log "检查前端构建..."
if (-not (Test-Path $frontendDist)) {
  Write-Log "前端未构建，开始构建..."
  try {
    Push-Location $frontendDir
    if (Test-Path (Join-Path $frontendDir "yarn.lock")) {
      Write-Log "使用 yarn 安装依赖..."
      yarn install --frozen-lockfile
      Write-Log "使用 yarn 构建前端..."
      yarn build
    } else {
      Write-Log "使用 npm 安装依赖..."
      npm ci
      Write-Log "使用 npm 构建前端..."
      npm run build
    }
    Pop-Location
    Write-Log "前端构建完成"
  } catch {
    Write-Log "前端构建失败或工具未安装，跳过复制" "WARNING"
  }
} else {
  Write-Log "前端已构建，跳过构建步骤"
}

if (Test-Path $frontendDist) {
  Write-Log "复制前端文件..."
  New-Item -ItemType Directory -Force -Path (Join-Path $out "frontend") | Out-Null
  Copy-Item -Recurse -Force $frontendDist (Join-Path $out "frontend\dist")
  Write-Log "前端文件已复制"
} else {
  Write-Log "前端构建目录不存在，跳过复制" "WARNING"
}

Write-Log "创建 Python 虚拟环境..."
$venvDir = Join-Path $out "venv"
if (-not (Test-Path $venvDir)) {
  $vendorPy = Join-Path $out "vendors\python\python.exe"
  $pyExe = $null

  if (Test-Path $vendorPy) {
    $pyExe = $vendorPy
    Write-Log "找到供应商 Python: $vendorPy"
  } elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pyExe = (Get-Command python).Source
    Write-Log "找到系统 Python: $pyExe"
  } elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $pyExe = "py -3"
    Write-Log "找到 py 命令"
  }

  if ($pyExe) {
    Write-Log "使用 $pyExe 创建虚拟环境..."
    try {
      if ($pyExe -like "py -3") {
        & py -3 -m venv $venvDir
      } else {
        & $pyExe -m venv $venvDir
      }
      Write-Log "虚拟环境创建完成"
    } catch {
      Write-Log "虚拟环境创建失败: $_" "ERROR"
    }
  } else {
    Write-Log "未找到 Python，虚拟环境未创建" "WARNING"
  }
} else {
  Write-Log "虚拟环境已存在，跳过创建"
}

Write-Log "安装后端依赖..."
if ((Test-Path $requirements) -and (Test-Path (Join-Path $venvDir "Scripts\pip.exe"))) {
  try {
    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"
    Write-Log "从 $requirements 安装依赖..."
    & (Join-Path $venvDir "Scripts\pip.exe") install -r $requirements
    Write-Log "后端依赖安装完成"
  } catch {
    Write-Log "后端依赖安装失败: $_" "ERROR"
  }
} else {
  Write-Log "requirements.txt 或 pip 不存在，跳过依赖安装" "WARNING"
}

Write-Log "生成 Nginx 配置..."
$nginxConf = Join-Path $out "runtime\nginx.conf"
if (-not (Test-Path $nginxConf)) {
  try {
    $frontendRoot = (Join-Path $out "frontend\dist").Replace('\\','/')
    $logsDir = (Join-Path $out "logs").Replace('\\','/')
    $content = @()
    $content += "worker_processes  1;"
    $content += "events { worker_connections 1024; }"
    $content += "http {"
    $content += "  include       mime.types;"
    $content += "  default_type  application/octet-stream;"
    $content += "  sendfile      on;"
    $content += "  keepalive_timeout  65;"
    $content += "  access_log  $logsDir/nginx_access.log;"
    $content += "  error_log   $logsDir/nginx_error.log;"
    $content += "  server {"
    $content += "    listen 80;"
    $content += "    server_name localhost;"
    $content += "    location / {"
    $content += "      root $frontendRoot;"
    $content += "      index index.html;"
    $content += "      try_files `$uri `$uri/ /index.html;"
    $content += "    }"
    $content += "    location /api/ {"
    $content += "      proxy_set_header Host `$host;"
    $content += "      proxy_set_header X-Real-IP `$remote_addr;"
    $content += "      proxy_set_header X-Forwarded-For `$proxy_add_x_forwarded_for;"
    $content += "      proxy_set_header X-Forwarded-Proto `$scheme;"
    $content += "      proxy_pass http://127.0.0.1:8000;"
    $content += "    }"
    $content += "  }"
    $content += "}"
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllLines($nginxConf, $content, $utf8NoBom)
    Write-Log "Nginx 配置已生成: $nginxConf"
  } catch {
    Write-Log "Nginx 配置生成失败: $_" "ERROR"
  }
} else {
  Write-Log "Nginx 配置已存在，跳过生成"
}

Write-Log "便携版本构建完成"
Write-Log "输出目录: $out"
Write-Output $out