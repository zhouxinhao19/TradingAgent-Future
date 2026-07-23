# 模型路由修复文档

## 📋 问题描述

用户报告在使用 `gemini-2.5-flash` 进行期货分析时，系统错误地使用了阿里百炼的 API：

```
✅ 阿里百炼 OpenAI 兼容适配器初始化成功
   模型: gemini-2.5-flash
   API Base: https://dashscope.aliyuncs.com/compatible-mode/v1
```

但是用户在数据库中配置的 `gemini-2.5-flash` 应该使用 Google 的 API。

## 🔍 问题分析

### 数据结构

系统使用两个 MongoDB 集合存储配置：

1. **`system_configs.llm_configs`**：存储模型配置
   ```json
   {
     "provider": "google",
     "model_name": "gemini-2.5-flash",
     "api_base": null,
     "enabled": true,
     ...
   }
   ```

2. **`llm_providers`**：存储厂家配置
   ```json
   {
     "name": "google",
     "display_name": "Google AI",
     "default_base_url": "https://generativelanguage.googleapis.com/v1",
     ...
   }
   ```

### 正确的逻辑

1. 从 `llm_configs` 中找到模型的 `provider`（如 `"google"`）
2. 如果模型的 `api_base` 为空，从 `llm_providers` 中查找该 provider 的 `default_base_url`
3. 使用查找到的 provider 和 backend_url 创建 LLM 实例

### 问题根源

在 `app/services/simple_analysis_service.py` 第 801 行：

```python
config = create_analysis_config(
    ...
    llm_provider="dashscope",  # ❌ 硬编码为 dashscope
    ...
)
```

无论用户选择什么模型，`llm_provider` 都被硬编码为 `"dashscope"`，导致所有模型都被路由到阿里百炼的 API。

## ✅ 修复方案

### 1. 创建同步查询函数

在 `app/services/simple_analysis_service.py` 中添加：

```python
def get_provider_and_url_by_model_sync(model_name: str) -> dict:
    """
    根据模型名称从数据库配置中查找对应的供应商和 API URL（同步版本）
    
    Returns:
        dict: {"provider": "google", "backend_url": "https://..."}
    """
    try:
        from pymongo import MongoClient
        from app.core.config import settings
        
        client = MongoClient(settings.MONGO_URI)
        db = client[settings.MONGO_DB]
        
        # 1. 查询模型配置
        configs_collection = db.system_configs
        doc = configs_collection.find_one({"is_active": True}, sort=[("version", -1)])
        
        if doc and "llm_configs" in doc:
            for config_dict in doc["llm_configs"]:
                if config_dict.get("model_name") == model_name:
                    provider = config_dict.get("provider")
                    api_base = config_dict.get("api_base")
                    
                    # 2. 如果有自定义 API 地址，直接使用
                    if api_base:
                        return {"provider": provider, "backend_url": api_base}
                    
                    # 3. 否则从 llm_providers 查找默认 URL
                    providers_collection = db.llm_providers
                    provider_doc = providers_collection.find_one({"name": provider})
                    
                    if provider_doc and provider_doc.get("default_base_url"):
                        backend_url = provider_doc["default_base_url"]
                        return {"provider": provider, "backend_url": backend_url}
        
        client.close()
        
        # 4. 回退到默认映射
        provider = _get_default_provider_by_model(model_name)
        return {"provider": provider, "backend_url": _get_default_backend_url(provider)}
        
    except Exception as e:
        logger.error(f"❌ 查找失败: {e}")
        provider = _get_default_provider_by_model(model_name)
        return {"provider": provider, "backend_url": _get_default_backend_url(provider)}
```

### 2. 修改分析配置创建

在 `_run_analysis_sync` 函数中：

```python
# 🔧 根据快速模型名称查找对应的供应商和 API URL
provider_info = get_provider_and_url_by_model_sync(quick_model)
llm_provider = provider_info["provider"]
backend_url = provider_info["backend_url"]

# 创建分析配置
config = create_analysis_config(
    ...
    llm_provider=llm_provider,  # ✅ 使用从数据库查找的供应商
    ...
)

# 🔧 覆盖 backend_url
config["backend_url"] = backend_url
```

### 3. 修复 ChatGoogleOpenAI 的 model_name 属性

在 `tradingagents/llm_adapters/google_openai_adapter.py` 中添加：

```python
@property
def model_name(self) -> str:
    """
    返回模型名称（兼容性属性）
    移除 'models/' 前缀，返回纯模型名称
    """
    model = self.model
    if model and model.startswith("models/"):
        return model[7:]  # 移除 "models/" 前缀
    return model or "unknown"
```

### 4. 修复错误处理代码

修复 `_generate` 方法中的列表遍历问题：

```python
# 注意：result.generations 是二维列表 [[ChatGeneration]]
if result and result.generations:
    for generation_list in result.generations:
        if isinstance(generation_list, list):
            for generation in generation_list:
                if hasattr(generation, 'message') and generation.message:
                    self._optimize_message_content(generation.message)
```

## 📊 修复效果

### 修复前

```
❌ llm_provider: "dashscope" (硬编码)
❌ backend_url: "https://dashscope.aliyuncs.com/api/v1"
❌ 日志显示: "阿里百炼 OpenAI 兼容适配器初始化成功"
❌ 模型名称: "unknown"
```

### 修复后

```
✅ llm_provider: "google" (从数据库查询)
✅ backend_url: "https://generativelanguage.googleapis.com/v1" (从 llm_providers 查询)
✅ 日志显示: "Google AI OpenAI 兼容适配器初始化成功"
✅ 模型名称: "gemini-2.5-flash"
```

## 🧪 测试验证

运行测试脚本：

```bash
.\.venv\Scripts\python scripts/test_provider_lookup.py
```

测试结果：

```
模型: gemini-2.5-flash
  -> 供应商: google
  -> API URL: https://generativelanguage.googleapis.com/v1

模型: qwen-plus
  -> 供应商: dashscope
  -> API URL: https://dashscope.aliyuncs.com/api/v1
```

## ⚠️ 注意事项

### Google API 网络问题

如果出现以下错误：

```
Connection to generativelanguage.googleapis.com timed out
```

**原因**：
1. Google API 需要科学上网才能访问
2. 防火墙阻止了连接
3. 网络不稳定

**解决方案**：
1. 配置科学上网工具
2. 检查防火墙设置
3. 使用国内可访问的模型（如阿里百炼、DeepSeek）

### API Key 配置

确保设置了正确的环境变量：

```bash
# Google AI
export GOOGLE_API_KEY="your-google-api-key"

# 阿里百炼
export DASHSCOPE_API_KEY="your-dashscope-api-key"

# DeepSeek
export DEEPSEEK_API_KEY="your-deepseek-api-key"
```

## 📁 修改的文件

1. ✅ `app/services/simple_analysis_service.py`
   - 添加 `get_provider_and_url_by_model_sync()` 函数
   - 添加 `_get_default_backend_url()` 函数
   - 修改 `_run_analysis_sync()` 函数

2. ✅ `tradingagents/llm_adapters/google_openai_adapter.py`
   - 添加 `model_name` 属性
   - 修复 `_generate()` 方法的错误处理

3. ✅ `app/services/model_capability_service.py`
   - 修改 `get_model_config()` 从 MongoDB 读取配置
   - 添加字符串到枚举的转换

## 🎯 总结

这次修复解决了三个关键问题：

1. **模型路由错误**：从硬编码改为从数据库动态查询
2. **模型能力验证失败**：从文件读取改为从 MongoDB 读取
3. **日志显示问题**：添加 `model_name` 属性和修复错误处理

修复后，系统可以正确地根据数据库配置路由模型请求到对应的 API，实现了真正的"配置驱动"。

## 📅 修复日期

2025-10-12

