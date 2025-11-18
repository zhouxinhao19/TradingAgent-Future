param(
    [int]$BackendPort = 8000,
    [int]$MongoPort = 27017,
    [int]$RedisPort = 6379,
    [int]$NginxPort = 80,
    [int]$TimeoutSeconds = 10
)

$ErrorActionPreference = "SilentlyContinue"

function Probe-Port {
    param(
        [int]$Port,
        [int]$MaxAttempts = 100,
        [int]$TimeoutMs = 500
    )

    try {
        # 快速检查端口是否被占用
        $connection = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
        if ($connection) {
            # 端口被占用，寻找可用端口
            for ($i = $Port + 1; $i -le ($Port + $MaxAttempts); $i++) {
                $available = Get-NetTCPConnection -LocalPort $i -ErrorAction SilentlyContinue
                if (-not $available) {
                    return $i
                }
            }
            # 如果找不到可用端口，返回原端口
            return $Port
        }
        return $Port
    }
    catch {
        # 如果出错，返回原端口
        return $Port
    }
}

# 并行探测所有端口以提高性能
$result = [ordered]@{}

# 使用后台作业并行探测
$jobs = @()
$jobs += Start-Job -ScriptBlock { param($p) Probe-Port $p } -ArgumentList $BackendPort
$jobs += Start-Job -ScriptBlock { param($p) Probe-Port $p } -ArgumentList $MongoPort
$jobs += Start-Job -ScriptBlock { param($p) Probe-Port $p } -ArgumentList $RedisPort
$jobs += Start-Job -ScriptBlock { param($p) Probe-Port $p } -ArgumentList $NginxPort

# 等待所有作业完成（带超时）
$timeout = (Get-Date).AddSeconds($TimeoutSeconds)
$completed = 0
while ((Get-Date) -lt $timeout -and $completed -lt 4) {
    $completed = ($jobs | Where-Object { $_.State -eq "Completed" }).Count
    Start-Sleep -Milliseconds 100
}

# 收集结果
$result.BackendPort = (Receive-Job -Job $jobs[0] -ErrorAction SilentlyContinue) -as [int]
$result.MongoPort = (Receive-Job -Job $jobs[1] -ErrorAction SilentlyContinue) -as [int]
$result.RedisPort = (Receive-Job -Job $jobs[2] -ErrorAction SilentlyContinue) -as [int]
$result.NginxPort = (Receive-Job -Job $jobs[3] -ErrorAction SilentlyContinue) -as [int]

# 清理作业
$jobs | Remove-Job -Force -ErrorAction SilentlyContinue

# 如果结果为空，使用默认值
if (-not $result.BackendPort) { $result.BackendPort = $BackendPort }
if (-not $result.MongoPort) { $result.MongoPort = $MongoPort }
if (-not $result.RedisPort) { $result.RedisPort = $RedisPort }
if (-not $result.NginxPort) { $result.NginxPort = $NginxPort }

Write-Output (ConvertTo-Json $result)