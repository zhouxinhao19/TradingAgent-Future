# 错误处理改进文档

## 📋 概述

本次改进旨在将技术性错误信息转换为用户友好的提示，明确指出问题所在（数据源、大模型、配置等），并提供可操作的解决建议。

## 🎯 改进目标

### 改进前的问题

用户看到的错误信息类似：
```
分析失败：Error code: 401 - {'error': {'message': 'Incorrect API key provided.', 'type': 'invalid_request_error'}}
```

这种错误信息存在以下问题：
1. **技术性太强**：普通用户看不懂 "Error code: 401" 是什么意思
2. **缺乏上下文**：不知道是哪个组件出错（数据源？大模型？）
3. **没有指导**：不知道如何解决问题

### 改进后的效果

用户现在看到的错误信息：
```
❌ Google Gemini API Key 无效

Google Gemini 的 API Key 无效或未配置。

💡 请检查以下几点：
1. 在「系统设置 → 大模型配置」中检查 Google Gemini 的 API Key 是否正确
2. 确认 API Key 是否已激活且有效
3. 尝试重新生成 API Key 并更新配置
4. 或者切换到其他可用的大模型
```

改进后的优势：
1. **清晰的标题**：一眼看出是哪个组件的什么问题
2. **简洁的描述**：用通俗语言解释问题
3. **可操作的建议**：提供具体的解决步骤

## 🛠️ 技术实现

### 1. 错误分类器 (`app/utils/error_formatter.py`)

#### 错误类别

```python
class ErrorCategory(str, Enum):
    # 大模型相关
    LLM_API_KEY = "llm_api_key"          # API Key 错误
    LLM_NETWORK = "llm_network"          # 网络错误
    LLM_QUOTA = "llm_quota"              # 配额/限流错误
    LLM_OTHER = "llm_other"              # 其他错误
    
    # 数据源相关
    DATA_SOURCE_API_KEY = "data_source_api_key"      # API Key 错误
    DATA_SOURCE_NETWORK = "data_source_network"      # 网络错误
    DATA_SOURCE_NOT_FOUND = "data_source_not_found"  # 数据未找到
    DATA_SOURCE_OTHER = "data_source_other"          # 其他错误
    
    # 其他
    STOCK_CODE_INVALID = "stock_code_invalid"  # 品种代码无效
    NETWORK = "network"                        # 网络连接错误
    SYSTEM = "system"                          # 系统错误
    UNKNOWN = "unknown"                        # 未知错误
```

#### 支持的厂商/数据源

**大模型厂商**：
- Google Gemini
- 阿里百炼（通义千问）
- 百度千帆
- DeepSeek
- OpenAI
- OpenRouter
- Anthropic Claude
- 智谱AI
- 月之暗面（Kimi）

**数据源**：
- Tushare
- AKShare
- BaoStock
- Finnhub
- MongoDB缓存

#### 使用方法

```python
from app.utils.error_formatter import ErrorFormatter

# 基本使用
formatted_error = ErrorFormatter.format_error(
    error_message="Error code: 401 - Invalid API key",
    context={"llm_provider": "google"}
)

# 返回结果
{
    "category": "大模型配置错误",
    "title": "❌ Google Gemini API Key 无效",
    "message": "Google Gemini 的 API Key 无效或未配置。",
    "suggestion": "请检查以下几点：\n1. ...\n2. ...",
    "technical_detail": "Error code: 401 - Invalid API key"
}
```

### 2. 后端集成

#### 分析服务 (`app/services/simple_analysis_service.py`)

在异常处理中使用错误格式化器：

```python
except Exception as e:
    logger.error(f"❌ 后台分析任务失败: {task_id} - {e}")

    # 格式化错误信息为用户友好的提示
    from ..utils.error_formatter import ErrorFormatter
    
    # 收集上下文信息
    error_context = {}
    if hasattr(request, 'parameters') and request.parameters:
        if hasattr(request.parameters, 'quick_model'):
            error_context['model'] = request.parameters.quick_model
    
    # 格式化错误
    formatted_error = ErrorFormatter.format_error(str(e), error_context)
    
    # 构建用户友好的错误消息
    user_friendly_error = (
        f"{formatted_error['title']}\n\n"
        f"{formatted_error['message']}\n\n"
        f"💡 {formatted_error['suggestion']}"
    )

    # 更新任务状态
    await self.memory_manager.update_task_status(
        task_id=task_id,
        status=TaskStatus.FAILED,
        error_message=user_friendly_error
    )
```

修改的文件：
- `app/services/simple_analysis_service.py` (第 880-919 行, 737-765 行, 1614-1639 行)

### 3. 前端集成

#### 单次分析页面 (`frontend/src/views/Analysis/SingleAnalysis.vue`)

**错误消息显示**：

```typescript
// 显示友好的错误提示（使用 dangerouslyUseHTMLString 支持换行）
ElMessage({
  type: 'error',
  message: errorMessage.replace(/\n/g, '<br>'),
  dangerouslyUseHTMLString: true,
  duration: 10000, // 显示10秒，让用户有时间阅读
  showClose: true
})
```

**进度区域显示**：

```vue
<div 
  class="task-description" 
  style="white-space: pre-wrap; line-height: 1.6;"
>
  {{ progressInfo.message }}
</div>
```

修改的文件：
- `frontend/src/views/Analysis/SingleAnalysis.vue` (第 1117-1141 行, 291-305 行)

#### 任务中心页面 (`frontend/src/views/Tasks/TaskCenter.vue`)

**添加"查看错误"按钮**：

```vue
<el-button 
  v-if="row.status==='failed'" 
  type="text" 
  size="small" 
  @click="showErrorDetail(row)"
>
  查看错误
</el-button>
```

**错误详情弹窗**：

```typescript
const showErrorDetail = async (row: any) => {
  const taskId = row.task_id || row.analysis_id || row.id
  const res = await analysisApi.getTaskStatus(taskId)
  const task = (res as any)?.data?.data || row
  const errorMessage = task.error_message || task.message || '未知错误'
  
  await ElMessageBox.alert(
    errorMessage,
    '错误详情',
    {
      confirmButtonText: '确定',
      type: 'error',
      dangerouslyUseHTMLString: true,
      message: errorMessage.replace(/\n/g, '<br>')
    }
  )
}
```

修改的文件：
- `frontend/src/views/Tasks/TaskCenter.vue` (第 106-115 行, 372-411 行)

## 📊 错误类型示例

### 1. 大模型 API Key 错误

**原始错误**：
```
Error code: 401 - {'error': {'message': 'Incorrect API key provided.'}}
```

**格式化后**：
```
❌ Google Gemini API Key 无效

Google Gemini 的 API Key 无效或未配置。

💡 请检查以下几点：
1. 在「系统设置 → 大模型配置」中检查 Google Gemini 的 API Key 是否正确
2. 确认 API Key 是否已激活且有效
3. 尝试重新生成 API Key 并更新配置
4. 或者切换到其他可用的大模型
```

### 2. 大模型配额不足

**原始错误**：
```
Error: Resource exhausted. Quota exceeded for model qwen-plus.
```

**格式化后**：
```
⚠️ 阿里百炼（通义千问） 配额不足或限流

阿里百炼（通义千问） 的调用配额已用完或触发了限流。

💡 请尝试以下解决方案：
1. 检查 阿里百炼（通义千问） 账户余额和配额
2. 等待一段时间后重试（可能是限流）
3. 升级账户套餐以获取更多配额
4. 切换到其他可用的大模型
```

### 3. 数据源 Token 错误

**原始错误**：
```
❌ [数据来源: Tushare失败] Token无效或未配置
```

**格式化后**：
```
❌ Tushare Token/API Key 无效

Tushare 的 Token 或 API Key 无效或未配置。

💡 请检查以下几点：
1. 在「系统设置 → 数据源配置」中检查 Tushare 的配置
2. 确认 Token/API Key 是否正确且有效
3. 检查账户是否已激活
4. 系统会自动尝试使用备用数据源
```

### 4. 数据源未找到数据

**原始错误**：
```
❌ [数据来源: AKShare失败] 未找到品种代码 999999 的数据
```

**格式化后**：
```
📊 AKShare 未找到数据

从 AKShare 获取期货数据失败，可能是品种代码不存在或数据暂未更新。

💡 建议：
1. 检查品种代码是否正确
2. 确认该期货品种是否已上市
3. 系统会自动尝试使用其他数据源
4. 如果是新股，可能需要等待数据更新
```

### 5. 品种代码无效

**原始错误**：
```
品种代码格式不正确: ABC123。品种代码应为6位数字。
```

**格式化后**：
```
❌ 品种代码无效

输入的品种代码格式不正确或不存在。

💡 请检查：
1. 品种代码格式：6位数字（如 000001、600000）
2. 港股代码格式：5位数字（如 00700）
3. 美股代码格式：品种代码（如 AAPL、TSLA）
4. 确认期货品种是否已上市
```

## 🧪 测试

运行测试脚本验证错误格式化功能：

```bash
.\.venv\Scripts\python scripts/test_error_formatter.py
```

测试覆盖：
- ✅ Google Gemini API Key 错误
- ✅ 阿里百炼配额不足
- ✅ DeepSeek 网络错误
- ✅ Tushare Token 错误
- ✅ AKShare 数据未找到
- ✅ 品种代码无效
- ✅ 网络连接错误
- ✅ 系统内部错误
- ✅ 未知错误
- ✅ 自动识别厂商（从错误信息中提取）

## 📝 使用指南

### 用户视角

1. **分析失败时**：
   - 在单次分析页面，错误信息会自动显示在进度区域和弹窗中
   - 错误信息包含清晰的标题、描述和解决建议
   - 可以根据建议检查配置或切换服务

2. **查看历史失败任务**：
   - 在任务中心页面，点击失败任务的"查看错误"按钮
   - 弹窗显示详细的错误信息和解决建议
   - 可以根据建议修复问题后重试

### 开发者视角

1. **添加新的错误类型**：
   - 在 `ErrorCategory` 枚举中添加新类别
   - 在 `_categorize_error` 方法中添加识别逻辑
   - 在 `_generate_friendly_message` 方法中添加友好提示

2. **添加新的厂商/数据源**：
   - 在 `LLM_PROVIDERS` 或 `DATA_SOURCES` 字典中添加映射
   - 错误分类器会自动识别

3. **在新的服务中使用**：
   ```python
   from app.utils.error_formatter import ErrorFormatter
   
   try:
       # 业务逻辑
       pass
   except Exception as e:
       formatted = ErrorFormatter.format_error(str(e), context)
       user_message = f"{formatted['title']}\n\n{formatted['message']}\n\n💡 {formatted['suggestion']}"
       # 返回给用户
   ```

## 🔄 后续改进

1. **国际化支持**：
   - 支持多语言错误提示
   - 根据用户语言设置显示对应语言

2. **错误统计**：
   - 统计各类错误的发生频率
   - 帮助识别系统瓶颈

3. **智能建议**：
   - 根据用户历史错误提供更精准的建议
   - 自动检测配置问题并提示修复

4. **错误恢复**：
   - 某些错误可以自动恢复（如自动切换数据源）
   - 提供一键修复功能

## 📚 相关文件

### 新增文件
- `app/utils/error_formatter.py` - 错误格式化器
- `scripts/test_error_formatter.py` - 测试脚本
- `docs/error-handling-improvement.md` - 本文档

### 修改文件
- `app/services/simple_analysis_service.py` - 集成错误格式化
- `frontend/src/views/Analysis/SingleAnalysis.vue` - 改进错误显示
- `frontend/src/views/Tasks/TaskCenter.vue` - 添加错误详情查看

## ✅ 验收标准

- [x] 错误信息包含清晰的标题（指明组件和问题类型）
- [x] 错误信息包含简洁的描述（用通俗语言）
- [x] 错误信息包含可操作的建议（具体步骤）
- [x] 支持主流大模型厂商识别
- [x] 支持主流数据源识别
- [x] 前端正确显示多行错误信息
- [x] 任务中心可查看失败任务的错误详情
- [x] 测试脚本验证通过

