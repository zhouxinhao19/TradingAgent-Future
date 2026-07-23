# 代理配置指南

## 📋 问题描述

当系统配置了 HTTP/HTTPS 代理时，访问国内数据源（如东方财富、新浪财经等）可能会出现以下错误：

### 错误 1：代理连接失败
```
ProxyError('Unable to connect to proxy', RemoteDisconnected('Remote end closed connection without response'))
```

### 错误 2：SSL 解密失败
```
SSLError(SSLError(1, '[SSL: DECRYPTION_FAILED_OR_BAD_RECORD_MAC] decryption failed or bad record mac'))
```

### 根本原因

- **代理服务器**：配置了 HTTP/HTTPS 代理（用于访问 Google 等国外服务）
- **国内数据源**：东方财富、新浪财经等国内接口不需要代理
- **冲突**：代理服务器无法正确处理国内 HTTPS 连接，导致 SSL 错误

---

## 🎯 解决方案：选择性代理配置

### 方案 1：在 .env 文件中配置（推荐，自动加载）

**✨ 新功能**：系统已支持自动从 `.env` 文件加载代理配置到环境变量！

在 `.env` 文件中添加以下配置：

```bash
# ===== 代理配置 =====
# 配置代理服务器（用于访问 Google 等国外服务）
HTTP_PROXY=http://127.0.0.1:10809
HTTPS_PROXY=http://127.0.0.1:10809

# 配置需要绕过代理的域名（国内数据源）
# 多个域名用逗号分隔
# ⚠️ Windows 不支持通配符 *，必须使用完整域名
NO_PROXY=localhost,127.0.0.1,eastmoney.com,push2.eastmoney.com,82.push2.eastmoney.com,82.push2delay.eastmoney.com,gtimg.cn,sinaimg.cn,api.tushare.pro,baostock.com
```

**说明**：
- `HTTP_PROXY`：HTTP 代理服务器地址
- `HTTPS_PROXY`：HTTPS 代理服务器地址
- `NO_PROXY`：需要绕过代理的域名列表
  - `localhost,127.0.0.1`：本地地址
  - `eastmoney.com`：东方财富主域名
  - `push2.eastmoney.com`：东方财富推送服务
  - `82.push2.eastmoney.com`：东方财富推送服务（IP 前缀）
  - `82.push2delay.eastmoney.com`：东方财富延迟推送服务
  - `gtimg.cn`：腾讯财经
  - `sinaimg.cn`：新浪财经
  - `api.tushare.pro`：Tushare 数据接口
  - `baostock.com`：BaoStock 数据接口

**⚠️ 重要提示**：
- **Windows 系统不支持通配符 `*`**，必须使用完整域名
- 如果发现新的东方财富域名（如 `83.push2.eastmoney.com`），需要手动添加到 `NO_PROXY` 列表

**工作原理**：
1. ✅ `app/core/config.py` 从 `.env` 文件加载配置
2. ✅ 自动将 `HTTP_PROXY`、`HTTPS_PROXY`、`NO_PROXY` 设置到环境变量
3. ✅ `requests` 库自动读取环境变量，实现选择性代理

**启动后端**：
```powershell
# 直接启动即可，无需手动设置环境变量
python -m app
```

### 方案 2：测试代理配置

在启动后端前，可以先测试代理配置是否正确：

```powershell
.\scripts\test_proxy_config.ps1
```

**测试内容**：
1. ✅ 检查 `.env` 文件中的配置
2. ✅ 检查 `Settings` 是否正确加载配置
3. ✅ 测试 AKShare 连接是否正常

**预期输出**：
```
🧪 测试代理配置...

📋 测试 1: 检查 .env 文件中的配置
✅ .env 文件中找到 NO_PROXY 配置:
   localhost,127.0.0.1,*.eastmoney.com,...

📋 测试 2: 检查 Settings 是否正确加载配置
Settings 配置:
  HTTP_PROXY: http://127.0.0.1:10809
  HTTPS_PROXY: http://127.0.0.1:10809
  NO_PROXY: localhost,127.0.0.1,*.eastmoney.com,...

环境变量:
  HTTP_PROXY: http://127.0.0.1:10809
  HTTPS_PROXY: http://127.0.0.1:10809
  NO_PROXY: localhost,127.0.0.1,*.eastmoney.com,...

📋 测试 3: 测试 AKShare 连接
✅ AKShare 连接成功，获取到 5000 条期货数据

🎉 所有测试通过！代理配置正确。
```

---

## 📊 数据源与代理关系

| 数据源 | 域名 | 是否需要代理 | NO_PROXY 配置 |
|--------|------|-------------|--------------|
| **AKShare** | `*.eastmoney.com` | ❌ 否 | ✅ 需要配置 |
| **AKShare** | `*.push2.eastmoney.com` | ❌ 否 | ✅ 需要配置 |
| **Tushare** | `api.tushare.pro` | ❌ 否 | ✅ 需要配置 |
| **BaoStock** | `*.baostock.com` | ❌ 否 | ✅ 需要配置 |
| **新浪财经** | `*.sinaimg.cn` | ❌ 否 | ✅ 需要配置 |
| **腾讯财经** | `*.gtimg.cn` | ❌ 否 | ✅ 需要配置 |
| **Google AI** | `generativelanguage.googleapis.com` | ✅ 是 | ❌ 不配置 |
| **OpenAI** | `api.openai.com` | ✅ 是 | ❌ 不配置 |

---

## 🧪 测试验证

### 测试 1：检查代理配置

```powershell
# 查看当前代理配置
echo $env:HTTP_PROXY
echo $env:HTTPS_PROXY
echo $env:NO_PROXY
```

**预期输出**：
```
HTTP_PROXY: http://your-proxy:port
HTTPS_PROXY: http://your-proxy:port
NO_PROXY: localhost,127.0.0.1,*.eastmoney.com,...
```

### 测试 2：测试 AKShare 连接

```powershell
# 设置 NO_PROXY
$env:NO_PROXY = "localhost,127.0.0.1,*.eastmoney.com,*.push2.eastmoney.com"

# 测试 AKShare
python -c "import akshare as ak; print(ak.stock_zh_a_spot_em().head())"
```

**预期结果**：
- ✅ 成功返回期货数据
- ❌ 如果仍然失败，检查代理配置是否正确

### 测试 3：测试 Google AI 连接

```powershell
# 测试 Google AI（应该使用代理）
python -c "import requests; print(requests.get('https://www.google.com').status_code)"
```

**预期结果**：
- ✅ 返回 200（通过代理访问成功）

---

## 🔧 常见问题

### Q1：NO_PROXY 配置后仍然出现 SSL 错误

**原因**：
- **Windows 系统不支持通配符 `*`**（这是最常见的原因）
- 某些代理软件（如 Clash、V2Ray）可能会拦截所有 HTTPS 流量
- 东方财富使用了多个子域名（如 `82.push2.eastmoney.com`、`82.push2delay.eastmoney.com`）

**解决方案**：
1. **使用完整域名**（不使用通配符）：
   ```bash
   NO_PROXY=localhost,127.0.0.1,eastmoney.com,push2.eastmoney.com,82.push2.eastmoney.com,82.push2delay.eastmoney.com
   ```

2. **如果发现新的域名**：
   - 查看错误日志中的域名（如 `83.push2.eastmoney.com`）
   - 添加到 `NO_PROXY` 列表
   - 重启后端

3. **在代理软件中配置规则**（推荐）：
   - **Clash**：在 `config.yaml` 中添加 `rules`
     ```yaml
     rules:
       - DOMAIN-SUFFIX,eastmoney.com,DIRECT
       - DOMAIN-SUFFIX,gtimg.cn,DIRECT
       - DOMAIN-SUFFIX,sinaimg.cn,DIRECT
       - DOMAIN,api.tushare.pro,DIRECT
       - DOMAIN-SUFFIX,baostock.com,DIRECT
     ```
   - **V2Ray**：在配置文件中添加 `routing` 规则
     ```json
     {
       "routing": {
         "rules": [
           {
             "type": "field",
             "domain": ["eastmoney.com", "gtimg.cn", "sinaimg.cn", "api.tushare.pro", "baostock.com"],
             "outboundTag": "direct"
           }
         ]
       }
     }
     ```

4. **临时禁用代理**（测试用）：
   ```powershell
   $env:HTTP_PROXY = ""
   $env:HTTPS_PROXY = ""
   python -m app
   ```

### Q2：如何在 Docker 中配置代理？

在 `docker-compose.yml` 中添加环境变量：

```yaml
services:
  backend:
    environment:
      - HTTP_PROXY=http://your-proxy:port
      - HTTPS_PROXY=http://your-proxy:port
      - NO_PROXY=localhost,127.0.0.1,*.eastmoney.com,*.push2.eastmoney.com
```

### Q3：如何验证 NO_PROXY 是否生效？

使用 Python 测试：

```python
import os
import requests

# 显示代理配置
print(f"HTTP_PROXY: {os.environ.get('HTTP_PROXY')}")
print(f"HTTPS_PROXY: {os.environ.get('HTTPS_PROXY')}")
print(f"NO_PROXY: {os.environ.get('NO_PROXY')}")

# 测试连接
try:
    response = requests.get('https://82.push2.eastmoney.com')
    print(f"✅ 连接成功: {response.status_code}")
except Exception as e:
    print(f"❌ 连接失败: {e}")
```

---

## 📝 推荐配置

### 开发环境（本地）

在 `.env` 文件中配置：

```bash
# 代理配置（用于访问 Google 等国外服务）
HTTP_PROXY=http://127.0.0.1:7890
HTTPS_PROXY=http://127.0.0.1:7890

# 绕过代理的域名（国内数据源）
NO_PROXY=localhost,127.0.0.1,*.eastmoney.com,*.push2.eastmoney.com,*.gtimg.cn,*.sinaimg.cn,api.tushare.pro,*.baostock.com
```

### 生产环境（Docker）

在 `docker-compose.yml` 中配置：

```yaml
services:
  backend:
    environment:
      # 如果服务器在国内，不需要配置代理
      # 如果服务器在国外，配置代理访问国内数据源
      - NO_PROXY=localhost,127.0.0.1,*.eastmoney.com,*.push2.eastmoney.com
```

---

## 🎉 总结

### 问题

- ✅ 需要代理访问 Google 等国外服务
- ✅ 国内数据源（东方财富等）不需要代理
- ❌ 代理服务器无法正确处理国内 HTTPS 连接

### 解决方案

- ✅ 配置 `NO_PROXY` 环境变量
- ✅ 让国内数据源绕过代理
- ✅ 保留代理用于访问国外服务

### 配置方法

1. **在 `.env` 文件中添加 `NO_PROXY` 配置**
2. **使用 `scripts/start_backend_with_proxy.ps1` 启动后端**
3. **验证配置是否生效**

---

## 📚 相关文档

- [AKShare 官方文档](https://akshare.akfamily.xyz/)
- [Tushare 官方文档](https://tushare.pro/document/1)
- [BaoStock 官方文档](http://baostock.com/baostock/index.php/Python_API%E6%96%87%E6%A1%A3)
- [Python Requests 代理配置](https://requests.readthedocs.io/en/latest/user/advanced/#proxies)

