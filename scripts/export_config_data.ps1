# 导出 MongoDB 配置数据（用于演示系统部署）
#
# 这个脚本会导出以下配置数据：
# - system_configs (系统配置，包括 LLM 配置)
# - users (用户数据)
# - llm_providers (LLM 提供商)
# - market_categories (市场分类)
# - user_tags (用户标签)
# - datasource_groupings (数据源分组)
# - platform_configs (平台配置)
# - market_quotes (实时行情数据)
# - stock_basic_info (股票基础信息)
#
# 不导出的数据：
# - 分析报告 (analysis_reports)
# - 分析任务 (analysis_tasks)
# - 历史K线数据 (stock_daily_quotes)
# - 财务数据 (financial_data_cache, financial_metrics_cache)
# - 日志和历史记录

$ErrorActionPreference = "Stop"

Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "导出 MongoDB 配置数据（用于演示系统部署）" -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan

# 配置
$containerName = "tradingagents-mongodb"
$dbName = "tradingagents"
$username = "admin"
$password = "CHANGE_ME_LOCAL_PASSWORD"
$authDb = "admin"
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$exportDir = "mongodb_config_export_$timestamp"

# 需要导出的集合（仅配置数据）
$collectionsToExport = @(
    "system_configs",           # 系统配置（包括 LLM 配置）
    "users",                    # 用户数据
    "llm_providers",            # LLM 提供商
    "market_categories",        # 市场分类
    "user_tags",                # 用户标签
    "datasource_groupings",     # 数据源分组
    "platform_configs",         # 平台配置
    "user_configs",             # 用户配置
    "model_catalog",            # 模型目录
    "market_quotes",            # 实时行情数据
    "stock_basic_info"          # 股票基础信息
)

Write-Host "`n[1] 检查 MongoDB 容器..." -ForegroundColor Yellow

$container = docker ps --filter "name=$containerName" --format "{{.Names}}"
if (-not $container) {
    Write-Host "错误: MongoDB 容器 '$containerName' 未运行" -ForegroundColor Red
    exit 1
}
Write-Host "  MongoDB 容器正在运行: $container" -ForegroundColor Green

Write-Host "`n[2] 创建导出目录..." -ForegroundColor Yellow
New-Item -ItemType Directory -Path $exportDir -Force | Out-Null
Write-Host "  导出目录: $exportDir" -ForegroundColor Green

Write-Host "`n[3] 导出配置集合..." -ForegroundColor Yellow

$successCount = 0
$failCount = 0

foreach ($collection in $collectionsToExport) {
    Write-Host "  导出: $collection" -ForegroundColor Cyan
    
    # 先检查集合是否存在
    $exists = docker exec $containerName mongo $dbName `
        -u $username -p $password --authenticationDatabase $authDb `
        --quiet --eval "db.getCollectionNames().includes('$collection')" 2>$null
    
    if ($exists -eq "true") {
        # 导出集合
        docker exec $containerName mongodump `
            -u $username -p $password --authenticationDatabase $authDb `
            -d $dbName -c $collection `
            -o /tmp/export 2>$null | Out-Null
        
        if ($LASTEXITCODE -eq 0) {
            # 从容器复制到本地
            docker cp "${containerName}:/tmp/export/$dbName/$collection.bson" "$exportDir/" 2>$null | Out-Null
            docker cp "${containerName}:/tmp/export/$dbName/$collection.metadata.json" "$exportDir/" 2>$null | Out-Null
            
            if ($LASTEXITCODE -eq 0) {
                Write-Host "    ✅ 成功" -ForegroundColor Green
                $successCount++
            } else {
                Write-Host "    ⚠️  复制失败" -ForegroundColor Yellow
                $failCount++
            }
        } else {
            Write-Host "    ⚠️  导出失败" -ForegroundColor Yellow
            $failCount++
        }
    } else {
        Write-Host "    ⚠️  集合不存在，跳过" -ForegroundColor Yellow
    }
}

# 清理容器中的临时文件
docker exec $containerName rm -rf /tmp/export 2>$null | Out-Null

Write-Host "`n[4] 导出统计..." -ForegroundColor Yellow
Write-Host "  成功: $successCount 个集合" -ForegroundColor Green
Write-Host "  失败/跳过: $failCount 个集合" -ForegroundColor Yellow

Write-Host "`n[5] 创建导入脚本..." -ForegroundColor Yellow

# 创建 PowerShell 导入脚本
$importScriptPS = @"
# 导入 MongoDB 配置数据到新服务器
#
# 使用方法:
# 1. 将整个导出目录复制到新服务器
# 2. 在新服务器上运行此脚本

`$ErrorActionPreference = "Stop"

Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "导入 MongoDB 配置数据" -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan

# 配置（根据新服务器环境修改）
`$containerName = "tradingagents-mongodb"
`$dbName = "tradingagents"
`$username = "admin"
`$password = "CHANGE_ME_LOCAL_PASSWORD"
`$authDb = "admin"

Write-Host "`n[1] 检查 MongoDB 容器..." -ForegroundColor Yellow

`$container = docker ps --filter "name=`$containerName" --format "{{.Names}}"
if (-not `$container) {
    Write-Host "错误: MongoDB 容器 '`$containerName' 未运行" -ForegroundColor Red
    Write-Host "请先启动 MongoDB 容器" -ForegroundColor Yellow
    exit 1
}
Write-Host "  MongoDB 容器正在运行: `$container" -ForegroundColor Green

Write-Host "`n[2] 复制文件到容器..." -ForegroundColor Yellow
docker cp . "`${containerName}:/tmp/import/"
Write-Host "  文件已复制到容器" -ForegroundColor Green

Write-Host "`n[3] 导入配置集合..." -ForegroundColor Yellow

`$bsonFiles = Get-ChildItem -Filter "*.bson"
`$successCount = 0
`$failCount = 0

foreach (`$file in `$bsonFiles) {
    `$collection = `$file.BaseName
    Write-Host "  导入: `$collection" -ForegroundColor Cyan
    
    docker exec `$containerName mongorestore ``
        -u `$username -p `$password --authenticationDatabase `$authDb ``
        -d `$dbName -c `$collection ``
        --drop ``
        /tmp/import/`$(`$file.Name) 2>`$null | Out-Null
    
    if (`$LASTEXITCODE -eq 0) {
        Write-Host "    ✅ 成功" -ForegroundColor Green
        `$successCount++
    } else {
        Write-Host "    ❌ 失败" -ForegroundColor Red
        `$failCount++
    }
}

# 清理容器中的临时文件
docker exec `$containerName rm -rf /tmp/import 2>`$null | Out-Null

Write-Host "`n[4] 导入统计..." -ForegroundColor Yellow
Write-Host "  成功: `$successCount 个集合" -ForegroundColor Green
Write-Host "  失败: `$failCount 个集合" -ForegroundColor Red

Write-Host "`n[5] 验证导入..." -ForegroundColor Yellow

# 验证 system_configs
`$configCount = docker exec `$containerName mongo `$dbName ``
    -u `$username -p `$password --authenticationDatabase `$authDb ``
    --quiet --eval "db.system_configs.countDocuments()" 2>`$null

Write-Host "  system_configs 文档数: `$configCount" -ForegroundColor Cyan

# 验证 LLM 配置
docker exec `$containerName mongo `$dbName ``
    -u `$username -p `$password --authenticationDatabase `$authDb ``
    --quiet --eval "var config = db.system_configs.findOne({is_active: true}); if (config && config.llm_configs) { print('启用的 LLM 数量: ' + config.llm_configs.filter(c => c.enabled).length); }" 2>`$null

Write-Host "`n================================================================================" -ForegroundColor Cyan
Write-Host "导入完成！" -ForegroundColor Green
Write-Host "================================================================================" -ForegroundColor Cyan

Write-Host "`n后续步骤:" -ForegroundColor Yellow
Write-Host "  1. 重启后端服务: docker restart tradingagents-backend" -ForegroundColor Cyan
Write-Host "  2. 检查系统配置: 访问前端配置页面" -ForegroundColor Cyan
Write-Host "  3. 测试 LLM 连接: 运行测试任务" -ForegroundColor Cyan
"@

$importScriptPS | Out-File -FilePath "$exportDir/import_config.ps1" -Encoding UTF8

# 创建 Bash 导入脚本（Linux 服务器）
$importScriptBash = @"
#!/bin/bash
# 导入 MongoDB 配置数据到新服务器（Linux 版本）

set -e

echo "================================================================================"
echo "导入 MongoDB 配置数据"
echo "================================================================================"

# 配置（根据新服务器环境修改）
CONTAINER_NAME="tradingagents-mongodb"
DB_NAME="tradingagents"
USERNAME="admin"
PASSWORD="CHANGE_ME_LOCAL_PASSWORD"
AUTH_DB="admin"

echo ""
echo "[1] 检查 MongoDB 容器..."

if ! docker ps --filter "name=`$CONTAINER_NAME" --format "{{.Names}}" | grep -q .; then
    echo "错误: MongoDB 容器 '`$CONTAINER_NAME' 未运行"
    echo "请先启动 MongoDB 容器"
    exit 1
fi
echo "  MongoDB 容器正在运行"

echo ""
echo "[2] 复制文件到容器..."
docker cp . "`${CONTAINER_NAME}:/tmp/import/"
echo "  文件已复制到容器"

echo ""
echo "[3] 导入配置集合..."

SUCCESS_COUNT=0
FAIL_COUNT=0

for file in *.bson; do
    if [ -f "`$file" ]; then
        collection=`${file%.bson}
        echo "  导入: `$collection"
        
        if docker exec `$CONTAINER_NAME mongorestore \
            -u `$USERNAME -p `$PASSWORD --authenticationDatabase `$AUTH_DB \
            -d `$DB_NAME -c `$collection \
            --drop \
            /tmp/import/`$file 2>/dev/null; then
            echo "    ✅ 成功"
            ((SUCCESS_COUNT++))
        else
            echo "    ❌ 失败"
            ((FAIL_COUNT++))
        fi
    fi
done

# 清理容器中的临时文件
docker exec `$CONTAINER_NAME rm -rf /tmp/import 2>/dev/null || true

echo ""
echo "[4] 导入统计..."
echo "  成功: `$SUCCESS_COUNT 个集合"
echo "  失败: `$FAIL_COUNT 个集合"

echo ""
echo "[5] 验证导入..."

# 验证 system_configs
CONFIG_COUNT=`$(docker exec `$CONTAINER_NAME mongo `$DB_NAME \
    -u `$USERNAME -p `$PASSWORD --authenticationDatabase `$AUTH_DB \
    --quiet --eval "db.system_configs.countDocuments()" 2>/dev/null)

echo "  system_configs 文档数: `$CONFIG_COUNT"

echo ""
echo "================================================================================"
echo "导入完成！"
echo "================================================================================"

echo ""
echo "后续步骤:"
echo "  1. 重启后端服务: docker restart tradingagents-backend"
echo "  2. 检查系统配置: 访问前端配置页面"
echo "  3. 测试 LLM 连接: 运行测试任务"
"@

$importScriptBash | Out-File -FilePath "$exportDir/import_config.sh" -Encoding UTF8

Write-Host "  ✅ 导入脚本已创建" -ForegroundColor Green
Write-Host "    - import_config.ps1 (Windows/PowerShell)" -ForegroundColor Cyan
Write-Host "    - import_config.sh (Linux/Bash)" -ForegroundColor Cyan

Write-Host "`n[6] 创建 README..." -ForegroundColor Yellow

$readme = @"
# MongoDB 配置数据导出

**导出时间**: $timestamp
**导出服务器**: $(hostname)

## 📋 导出的集合

$(foreach ($col in $collectionsToExport) { "- $col`n" })

## 📦 文件说明

- `*.bson` - 集合数据文件
- `*.metadata.json` - 集合元数据文件
- `import_config.ps1` - Windows/PowerShell 导入脚本
- `import_config.sh` - Linux/Bash 导入脚本
- `README.md` - 本文件

## 🚀 使用方法

### 在新服务器上导入（Windows）

1. 将整个导出目录复制到新服务器
2. 确保 MongoDB 容器正在运行
3. 在导出目录中运行：
   ``````powershell
   .\import_config.ps1
   ``````

### 在新服务器上导入（Linux）

1. 将整个导出目录复制到新服务器
2. 确保 MongoDB 容器正在运行
3. 在导出目录中运行：
   ``````bash
   chmod +x import_config.sh
   ./import_config.sh
   ``````

## ⚠️ 注意事项

1. **导入前备份**: 建议在新服务器上先备份现有数据
2. **覆盖数据**: 导入脚本使用 `--drop` 参数，会覆盖同名集合
3. **用户密码**: 导入后，用户密码保持原样（已加密）
4. **API 密钥**: LLM 和数据源的 API 密钥会一起导入
5. **重启服务**: 导入后需要重启后端服务

## 📝 导入后验证

1. 检查系统配置：
   ``````bash
   docker exec tradingagents-mongodb mongo tradingagents \
     -u admin -p CHANGE_ME_LOCAL_PASSWORD --authenticationDatabase admin \
     --eval "db.system_configs.find({is_active: true}).pretty()"
   ``````

2. 检查 LLM 配置数量：
   ``````bash
   docker exec tradingagents-mongodb mongo tradingagents \
     -u admin -p CHANGE_ME_LOCAL_PASSWORD --authenticationDatabase admin \
     --eval "var config = db.system_configs.findOne({is_active: true}); print('LLM 数量: ' + config.llm_configs.filter(c => c.enabled).length);"
   ``````

3. 检查用户数量：
   ``````bash
   docker exec tradingagents-mongodb mongo tradingagents \
     -u admin -p CHANGE_ME_LOCAL_PASSWORD --authenticationDatabase admin \
     --eval "db.users.countDocuments()"
   ``````

## 🔧 故障排除

### 问题：导入失败

**解决方案**：
1. 检查 MongoDB 容器是否运行：`docker ps | grep mongodb`
2. 检查用户名密码是否正确
3. 检查数据库名称是否正确

### 问题：导入后配置不生效

**解决方案**：
1. 重启后端服务：`docker restart tradingagents-backend`
2. 检查配置桥接日志
3. 清除浏览器缓存

## 📞 支持

如有问题，请查看项目文档或联系技术支持。
"@

$readme | Out-File -FilePath "$exportDir/README.md" -Encoding UTF8

Write-Host "  ✅ README 已创建" -ForegroundColor Green

Write-Host "`n================================================================================" -ForegroundColor Cyan
Write-Host "导出完成！" -ForegroundColor Green
Write-Host "================================================================================" -ForegroundColor Cyan

Write-Host "`n📦 导出目录: $exportDir" -ForegroundColor Cyan
Write-Host "`n📋 导出的文件:" -ForegroundColor Yellow
Get-ChildItem $exportDir | ForEach-Object {
    $size = if ($_.Length -gt 1MB) { "{0:N2} MB" -f ($_.Length / 1MB) } else { "{0:N2} KB" -f ($_.Length / 1KB) }
    Write-Host "  - $($_.Name) ($size)" -ForegroundColor Cyan
}

Write-Host "`n📝 后续步骤:" -ForegroundColor Yellow
Write-Host "  1. 将 '$exportDir' 目录复制到新服务器" -ForegroundColor Cyan
Write-Host "  2. 在新服务器上运行导入脚本:" -ForegroundColor Cyan
Write-Host "     Windows: .\import_config.ps1" -ForegroundColor White
Write-Host "     Linux:   ./import_config.sh" -ForegroundColor White
Write-Host "  3. 重启后端服务并验证配置" -ForegroundColor Cyan

Write-Host "`n💡 提示:" -ForegroundColor Yellow
Write-Host "  - 导出包含 LLM API 密钥，请妥善保管" -ForegroundColor Yellow
Write-Host "  - 导入会覆盖新服务器上的同名集合" -ForegroundColor Yellow
Write-Host "  - 建议在新服务器上先备份现有数据" -ForegroundColor Yellow

