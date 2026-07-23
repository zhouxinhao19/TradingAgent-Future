# 如何访问使用统计页面

## 🎯 快速访问

### 方式 1：通过导航菜单（推荐）

1. **登录系统**
   - 访问 `http://localhost:3001`（或您的前端地址）
   - 使用用户名和密码登录

2. **进入设置页面**
   - 点击左侧导航栏的 **"设置"** 图标

3. **选择系统配置**
   - 在设置页面顶部，确认当前在 **"系统配置"** 标签
   - 如果不在，点击切换到"系统配置"

4. **点击使用统计**
   - 在左侧菜单中找到 **"使用统计"** 菜单项（带有 📊 图标）
   - 点击该菜单项

5. **查看使用统计**
   - 点击 **"查看使用统计"** 按钮
   - 页面会跳转到使用统计界面

### 方式 2：直接访问 URL

直接在浏览器地址栏输入：

```
http://localhost:3001/settings/usage
```

按回车即可直接访问使用统计页面。

## 📊 页面功能

访问成功后，您将看到：

### 1. 统计概览（顶部）
```
┌─────────────┬─────────────┬─────────────┬─────────────┐
│ 总请求数     │ 总输入Token │ 总输出Token │ 总成本      │
│ 📄 0        │ ⬆️ 0        │ ⬇️ 0        │ 💰 ¥0.00   │
└─────────────┴─────────────┴─────────────┴─────────────┘
```

### 2. 时间范围选择器（右上角）
- 最近 7 天
- 最近 30 天
- 最近 90 天

### 3. 图表展示（中间）
- **按供应商统计**（饼图）
- **按模型统计**（柱状图）
- **每日成本趋势**（折线图）

### 4. 使用记录表格（底部）
- 详细的 API 调用记录
- 支持分页查看

### 5. 操作按钮
- **刷新** - 重新加载数据
- **清理旧记录** - 删除 90 天前的数据

## 🔧 配置模型定价

在查看使用统计之前，建议先配置模型定价：

1. **访问配置管理**
   ```
   设置 > 系统配置 > 配置管理
   ```

2. **选择大模型配置**
   - 点击"大模型配置"标签

3. **编辑模型**
   - 找到要配置的模型（如 qwen-max）
   - 点击"编辑"按钮

4. **填写定价信息**
   - 滚动到"定价配置"部分
   - 填写：
     - **输入价格**: 每 1000 个输入 token 的价格（如 0.0200）
     - **输出价格**: 每 1000 个输出 token 的价格（如 0.0600）
     - **货币单位**: 选择 CNY（人民币）

5. **保存配置**
   - 点击"保存"按钮

6. **查看定价**
   - 保存后，模型卡片会显示定价信息：
     ```
     💰 定价:
       输入: 0.0200 CNY/1K
       输出: 0.0600 CNY/1K
     ```

## 📝 常见问题

### Q1: 看不到"使用统计"菜单项？

**解决方案**：
1. 确认您在"系统配置"标签，而不是"个人设置"或"系统管理"
2. 刷新浏览器页面（Ctrl+F5 或 Cmd+Shift+R）
3. 检查前端是否正在运行（应该在 http://localhost:3001）

### Q2: 点击"使用统计"后没有反应？

**解决方案**：
1. 打开浏览器开发者工具（F12）
2. 查看 Console 标签是否有错误信息
3. 尝试直接访问 URL：`http://localhost:3001/settings/usage`

### Q3: 页面显示"暂无数据"？

**原因**：这是正常的，因为还没有使用记录。

**解决方案**：
1. 运行一些期货分析，生成使用记录
2. 或者使用测试脚本生成测试数据（见下文）

### Q4: 图表不显示？

**解决方案**：
1. 检查是否有使用数据
2. 尝试切换时间范围
3. 点击"刷新"按钮
4. 检查浏览器控制台是否有错误

### Q5: 成本显示为 0？

**原因**：模型定价未配置。

**解决方案**：
1. 访问"配置管理 > 大模型配置"
2. 为每个模型配置定价信息
3. 返回使用统计页面刷新

## 🧪 生成测试数据

如果想测试使用统计功能，可以：

### 方法 1：运行期货分析

1. 访问"期货分析 > 单股分析"
2. 输入品种代码（如 600519）
3. 点击"开始分析"
4. 等待分析完成
5. 返回使用统计页面查看数据

### 方法 2：使用测试脚本

创建测试脚本 `scripts/add_test_usage_data.py`：

```python
import asyncio
from datetime import datetime, timedelta
import random
from app.services.usage_statistics_service import usage_statistics_service
from app.models.config import UsageRecord

async def add_test_data():
    """添加测试使用数据"""
    providers = ['dashscope', 'openai', 'google']
    models = {
        'dashscope': ['qwen-max', 'qwen-plus', 'qwen-turbo'],
        'openai': ['gpt-4', 'gpt-3.5-turbo'],
        'google': ['gemini-pro']
    }
    
    # 生成最近 30 天的数据
    for i in range(30):
        date = datetime.now() - timedelta(days=i)
        
        # 每天生成 5-10 条记录
        for _ in range(random.randint(5, 10)):
            provider = random.choice(providers)
            model = random.choice(models[provider])
            
            input_tokens = random.randint(500, 3000)
            output_tokens = random.randint(200, 1500)
            
            # 假设价格
            input_price = 0.02
            output_price = 0.06
            cost = (input_tokens / 1000) * input_price + (output_tokens / 1000) * output_price
            
            record = UsageRecord(
                timestamp=date.isoformat(),
                provider=provider,
                model_name=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
                session_id=f"test_session_{i}_{_}",
                analysis_type="stock_analysis"
            )
            
            await usage_statistics_service.add_usage_record(record)
    
    print("✅ 测试数据添加完成！")

if __name__ == "__main__":
    asyncio.run(add_test_data())
```

运行脚本：
```powershell
.\.venv\Scripts\python scripts/add_test_usage_data.py
```

## 🔍 验证访问

### 检查清单

- [ ] 后端服务正在运行（http://localhost:8000）
- [ ] 前端服务正在运行（http://localhost:3001）
- [ ] 已登录系统
- [ ] 在"系统配置"标签下
- [ ] 可以看到"使用统计"菜单项
- [ ] 点击后可以跳转到使用统计页面

### 后端 API 验证

访问 Swagger 文档：
```
http://localhost:8000/docs
```

找到"使用统计"标签，应该看到以下 API：
- GET `/api/usage/records` - 获取使用记录
- GET `/api/usage/statistics` - 获取使用统计
- GET `/api/usage/cost/by-provider` - 按供应商统计
- GET `/api/usage/cost/by-model` - 按模型统计
- GET `/api/usage/cost/daily` - 每日成本统计
- DELETE `/api/usage/records/old` - 删除旧记录

## 📞 需要帮助？

如果仍然无法访问使用统计页面，请检查：

1. **浏览器控制台**（F12）
   - 查看是否有 JavaScript 错误
   - 查看 Network 标签，检查 API 请求是否成功

2. **后端日志**
   - 查看终端输出
   - 检查是否有错误信息

3. **前端日志**
   - 查看 Vite 开发服务器输出
   - 检查是否有编译错误

4. **路由配置**
   - 确认 `frontend/src/router/index.ts` 中有 `/settings/usage` 路由
   - 确认 `frontend/src/views/Settings/index.vue` 中有使用统计菜单项

## 🎉 成功访问

如果您能看到使用统计页面，恭喜！您已经成功访问了使用统计功能。

现在您可以：
- 📊 查看模型使用情况
- 💰 监控成本支出
- 📈 分析使用趋势
- 🧹 管理历史数据

享受使用统计功能吧！

