# TradingAgents-CN 本地环境一键关闭

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  TradingAgents-CN 关闭所有服务" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 1. 关闭前端 (npm/vite)
Write-Host "  [1/4] Vue 前端..." -NoNewline
Get-Process node,npm -ErrorAction SilentlyContinue | ForEach-Object {
  try { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue; Write-Host "." -NoNewline } catch {}
}
Write-Host " done" -ForegroundColor Green

# 2. 关闭后端 (uvicorn/python on ports 8000-8002)
Write-Host "  [2/4] FastAPI 后端..." -NoNewline
foreach ($port in @(8000,8001,8002)) {
  netstat -ano | Select-String ":$port " | ForEach-Object {
    $pid = [int]($_ -split ' +')[-1]
    if ($pid -gt 0) { try { Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue; Write-Host "." -NoNewline } catch {} }
  }
}
Write-Host " done" -ForegroundColor Green

# 3. 关闭 MongoDB
Write-Host "  [3/4] MongoDB..." -NoNewline
Get-Process mongod -ErrorAction SilentlyContinue | ForEach-Object {
  try { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue; Write-Host "." -NoNewline } catch {}
}
Write-Host " done" -ForegroundColor Green

# 4. 关闭 Redis
Write-Host "  [4/4] Redis..." -NoNewline
Get-Process redis-server -ErrorAction SilentlyContinue | ForEach-Object {
  try { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue; Write-Host "." -NoNewline } catch {}
}
Write-Host " done" -ForegroundColor Green

Write-Host "`n  ✅ 所有服务已关闭" -ForegroundColor Green
