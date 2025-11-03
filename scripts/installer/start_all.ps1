<#
TradingAgents-CN Windows Portable Starter
Starts MongoDB, Redis, backend (FastAPI), optional Nginx.
Encoding-safe version: ASCII-only output.
#>

[CmdletBinding()]
param(
    [switch]$SkipMongo,
    [switch]$SkipRedis,
    [switch]$SkipNginx
)

$ErrorActionPreference = 'Stop'

function Read-DotEnv {
    param([string]$Path)
    $result = @{}
    if (-not (Test-Path -LiteralPath $Path)) { return $result }
    Get-Content -LiteralPath $Path | ForEach-Object {
        $line = $_.Trim()
        if ($line -eq '' -or $line.StartsWith('#')) { return }
        $kv = $line -split '=', 2
        if ($kv.Count -eq 2) { $result[$kv[0]] = $kv[1] }
    }
    return $result
}

function Ensure-Dir {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { New-Item -ItemType Directory -Path $Path | Out-Null }
}

function Write-Ascii {
    param([string]$Path, [string]$Content)
    Set-Content -Path $Path -Value $Content -Encoding ASCII
}

function Find-FreePort {
    param([int]$Preferred, [int]$MaxTries = 20)
    $ports = @($Preferred)
    for ($i = 1; $i -le $MaxTries; $i++) { $ports += ($Preferred + $i) }
    foreach ($p in $ports) {
        $tcpClient = New-Object System.Net.Sockets.TcpClient
        try {
            $tcpClient.Connect('127.0.0.1', $p)
            $tcpClient.Close()
        } catch {
            return $p
        }
    }
    return $Preferred
}

function Start-Proc {
    param(
        [string]$FilePath,
        [string]$Arguments = '',
        [string]$WorkingDirectory = '',
        [string]$Name = 'process'
    )
    Write-Host "Starting $Name ..."
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FilePath
    $psi.Arguments = $Arguments
    if ($WorkingDirectory -ne '') { $psi.WorkingDirectory = $WorkingDirectory }
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $proc = [System.Diagnostics.Process]::Start($psi)
    Start-Sleep -Milliseconds 100
    return $proc
}

$root = (Get-Location).Path
$envFile = Join-Path $root '.env'
$env = Read-DotEnv $envFile

Ensure-Dir (Join-Path $root 'runtime')
Ensure-Dir (Join-Path $root 'logs')

$vendors = Join-Path $root 'vendors'
$mongoExeCandidates = Get-ChildItem -LiteralPath (Join-Path $vendors 'mongodb') -Recurse -Filter 'mongod.exe' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName
$mongoExe = $mongoExeCandidates | Select-Object -First 1

$redisExeCandidates = Get-ChildItem -LiteralPath (Join-Path $vendors 'redis') -Recurse -Filter 'redis-server.exe' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName
$redisExe = $redisExeCandidates | Select-Object -First 1

$nginxExeCandidates = Get-ChildItem -LiteralPath (Join-Path $vendors 'nginx') -Recurse -Filter 'nginx.exe' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName
$nginxExe = $nginxExeCandidates | Select-Object -First 1

$mongoData = Join-Path $root 'data\mongodb\db'
$redisData = Join-Path $root 'data\redis\data'
$runtimePid = Join-Path $root 'runtime\pids.json'

$backendHost = if ($env.ContainsKey('HOST')) { $env['HOST'] } else { '127.0.0.1' }
$port = if ($env.ContainsKey('PORT')) { [int]$env['PORT'] } else { 8000 }
$debug = if ($env.ContainsKey('DEBUG')) { $env['DEBUG'] } else { $null }
$serveFrontend = ($env['SERVE_FRONTEND'] -eq 'true')
$frontendPath = if ($env.ContainsKey('FRONTEND_STATIC')) { $env['FRONTEND_STATIC'] } else { 'frontend\dist' }
$autoOpen = ($env['AUTO_OPEN_BROWSER'] -eq 'true')

$selectedPort = Find-FreePort -Preferred $port
if ($selectedPort -ne $port) {
    Write-Host "Backend port $port is busy, using $selectedPort"
}

$procs = @{}

if (-not $SkipMongo -and $mongoExe -and (Test-Path -LiteralPath $mongoExe)) {
    Ensure-Dir $mongoData
    $mongoArgs = "--dbpath `"$mongoData`" --bind_ip 127.0.0.1 --port 27017"
    $p = Start-Proc -FilePath $mongoExe -Arguments $mongoArgs -Name 'MongoDB'
    $procs['mongodb'] = $p.Id
} else { Write-Host "MongoDB skipped or binary not found" }

if (-not $SkipRedis -and $redisExe -and (Test-Path -LiteralPath $redisExe)) {
    Ensure-Dir $redisData
    $redisConf = Join-Path $root 'runtime\redis.conf'
    $conf = @(
        "bind 127.0.0.1",
        "port 6379",
        "dir `"$redisData`"",
        "save 900 1",
        "save 300 10",
        "save 60 10000"
    )
    Set-Content -Path $redisConf -Value ($conf -join "`n") -Encoding ASCII
    $p = Start-Proc -FilePath $redisExe -Arguments "`"$redisConf`"" -Name 'Redis'
    $procs['redis'] = $p.Id
} else { Write-Host "Redis skipped or binary not found" }

# Backend
$pythonExe = Join-Path $root 'venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { $pythonExe = 'python' }
$backendArgs = "-m app"
$env:PORT = $selectedPort
$env:HOST = $backendHost
if ($debug -ne $null) { $env:DEBUG = $debug }
$p = Start-Proc -FilePath $pythonExe -Arguments $backendArgs -Name 'Backend'
$procs['backend'] = $p.Id

Start-Sleep -Seconds 2
if ($autoOpen) {
    $url = "http://${backendHost}:$selectedPort"
    Write-Host "Opening browser: $url"
    Start-Process $url | Out-Null
}

if (-not $SkipNginx -and $nginxExe -and (Test-Path -LiteralPath $nginxExe)) {
    $nginxRoot = Split-Path -Parent $nginxExe
    $confDir = Join-Path $nginxRoot 'conf'
    Ensure-Dir $confDir
    $nginxConf = Join-Path $confDir 'nginx.conf'
    if (-not (Test-Path -LiteralPath $nginxConf)) {
        $relRoot = '../../frontend/dist'
        $conf = @"
worker_processes  1;

events { worker_connections 1024; }

http {
    include       mime.types;
    default_type  application/octet-stream;
    sendfile      on;
    keepalive_timeout 65;

    map \$http_upgrade \$connection_upgrade { default close; 'websocket' upgrade; }

    server {
        listen 80;
        server_name localhost;

        root $relRoot;
        index index.html;

        gzip on;
        gzip_types text/plain text/css application/json application/javascript application/xml image/svg+xml;

        location = /index.html { add_header Cache-Control "no-cache, no-store, must-revalidate"; }
        location /assets/ { expires 7d; add_header Cache-Control "public, max-age=604800, immutable"; }
        location /favicon.ico { expires 7d; }

        location / { try_files \$uri \$uri/ /index.html; }

        location /api/ {
            proxy_pass http://${backendHost}:${selectedPort}/api/;
            proxy_http_version 1.1;
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header Upgrade \$http_upgrade;
            proxy_set_header Connection \$connection_upgrade;
            proxy_read_timeout 600s;
            proxy_send_timeout 600s;
        }

        location = /health { return 200 'ok'; add_header Content-Type text/plain; }
    }
}
"@
        Write-Ascii -Path $nginxConf -Content $conf
    }
    $p = Start-Proc -FilePath $nginxExe -Arguments '' -WorkingDirectory $nginxRoot -Name 'Nginx'
    $procs['nginx'] = $p.Id
} else { Write-Host "Nginx skipped or binary not found" }

# Save pids.json (ASCII)
Set-Content -Path $runtimePid -Value (ConvertTo-Json $procs -Compress) -Encoding ASCII
Write-Host "All components started. PID file: runtime\pids.json"
Write-Host "Backend: http://${backendHost}:${selectedPort}"