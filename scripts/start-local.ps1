# TradingAgents-CN 本地开发环境一键启动
param([int]$BackendPort = 8002, [int]$FrontendPort = 3000)

$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$LogDir = Join-Path $Root "logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  TradingAgents-CN 本地环境启动" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 1. Kill stale port 8000
netstat -ano | Select-String ":8000 " | ForEach-Object {
  $p = [int]($_ -split ' +')[-1]
  if ($p -gt 0) { try { Stop-Process -Id $p -Force -ErrorAction SilentlyContinue } catch {} }
}

# 2. MongoDB
$mongoExe = @("C:\Program Files\MongoDB\Server\8.3\bin\mongod.exe","D:\MongoDB\Server\8.3\bin\mongod.exe","mongod") | Where-Object { Test-Path $_ -or $_ -eq "mongod" } | Select-Object -First 1
$mongoData = Join-Path $Root "data\mongodb"
if (-not (Test-Path $mongoData)) { New-Item -ItemType Directory -Path $mongoData -Force | Out-Null }
Write-Host "  [1/5] MongoDB..." -NoNewline
$p = Start-Process -FilePath $mongoExe -ArgumentList "--dbpath `"$mongoData`" --logpath `"$(Join-Path $mongoData 'mongod.log')`" --bind_ip 127.0.0.1" -WindowStyle Hidden -PassThru
Write-Host " PID $($p.Id)" -ForegroundColor Gray; Start-Sleep -Seconds 3

# 3. Redis
$redisExe = @("D:\Redis\redis-server.exe","redis-server") | Where-Object { Test-Path $_ -or $_ -eq "redis-server" } | Select-Object -First 1
if (Test-Path $redisExe) {
  Write-Host "  [2/5] Redis..." -NoNewline
  $p = Start-Process -FilePath $redisExe -ArgumentList '"D:\Redis\redis.windows.conf"' -WindowStyle Hidden -PassThru
  Write-Host " PID $($p.Id)" -ForegroundColor Gray; Start-Sleep -Seconds 2
}

# 4. Update vite proxy to match BackendPort
$viteConfig = Join-Path $Root "frontend\vite.config.ts"
if (Test-Path $viteConfig) {
  $content = Get-Content $viteConfig -Raw
  $newContent = $content -replace "target: 'http://localhost:\d+'", "target: 'http://localhost:$BackendPort'"
  if ($content -ne $newContent) { Set-Content $viteConfig -Value $newContent }
}

# 5. Backend
$env:PYTHONIOENCODING = "utf-8"; $env:PYTHONUTF8 = "1"
Write-Host "  [3/5] 后端 (:$BackendPort)..." -NoNewline
$p = Start-Process -FilePath "python" -ArgumentList "-m uvicorn app.main:app --host 0.0.0.0 --port $BackendPort" `
  -WorkingDirectory $Root -WindowStyle Hidden `
  -RedirectStandardOutput (Join-Path $LogDir "backend.log") -RedirectStandardError (Join-Path $LogDir "backend.log") -PassThru
Write-Host " PID $($p.Id)" -ForegroundColor Gray; Start-Sleep -Seconds 5

# 6. Frontend
Write-Host "  [4/5] 前端 (:$FrontendPort)..." -NoNewline
$p = Start-Process -FilePath "npm" -ArgumentList "run dev" -WorkingDirectory (Join-Path $Root "frontend") -WindowStyle Hidden `
  -RedirectStandardOutput (Join-Path $LogDir "frontend.log") -RedirectStandardError (Join-Path $LogDir "frontend.log") -PassThru
Write-Host " PID $($p.Id)" -ForegroundColor Gray; Start-Sleep -Seconds 8

# 7. Health check
Write-Host "  [5/5] 健康检查..."
try {
  $resp = Invoke-WebRequest -Uri "http://localhost:$BackendPort/api/health" -UseBasicParsing -TimeoutSec 5
  if (($resp.Content | ConvertFrom-Json).success) { Write-Host "  ✅ 后端 :$BackendPort OK" -ForegroundColor Green }
} catch { Write-Host "  ❌ 后端 :$BackendPort 未响应" -ForegroundColor Red }
try {
  $resp = Invoke-WebRequest -Uri "http://localhost:$FrontendPort" -UseBasicParsing -TimeoutSec 5
  if ($resp.StatusCode -eq 200) { Write-Host "  ✅ 前端 :$FrontendPort OK" -ForegroundColor Green }
} catch { Write-Host "  ⚠️  前端 :$FrontendPort 启动中" -ForegroundColor Yellow }

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  前端: http://localhost:$FrontendPort" -ForegroundColor Cyan
Write-Host "  后端: http://localhost:$BackendPort" -ForegroundColor Cyan
Write-Host "  Docs: http://localhost:$BackendPort/docs" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
