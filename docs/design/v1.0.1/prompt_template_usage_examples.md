# 提示词模版系统 - 使用示例

## 📚 使用场景示例

### 场景1: 基础使用 - 使用默认模版

```python
from tradingagents.config.prompt_manager import PromptTemplateManager
from tradingagents.agents import create_fundamentals_analyst

# 初始化模版管理器
template_manager = PromptTemplateManager()

# 创建分析师（使用默认模版）
analyst = create_fundamentals_analyst(
    llm=llm,
    toolkit=toolkit,
    template_name="default",
    template_manager=template_manager
)

# 执行分析
result = analyst(state)
```

### 场景2: 选择不同的模版

```python
# 保守分析风格
conservative_analyst = create_fundamentals_analyst(
    llm=llm,
    toolkit=toolkit,
    template_name="conservative",
    template_manager=template_manager
)

# 激进分析风格
aggressive_analyst = create_fundamentals_analyst(
    llm=llm,
    toolkit=toolkit,
    template_name="aggressive",
    template_manager=template_manager
)

# 对比两种分析结果
conservative_result = conservative_analyst(state)
aggressive_result = aggressive_analyst(state)
```

### 场景3: 列出所有可用模版

```python
# 列出基本面分析师的所有模版
templates = template_manager.list_templates("fundamentals")

for template in templates:
    print(f"模版: {template['name']}")
    print(f"描述: {template['description']}")
    print(f"标签: {template['tags']}")
    print(f"默认: {template['is_default']}")
    print("---")

# 输出示例：
# 模版: 基本面分析 - 默认模版
# 描述: 标准的基本面分析提示词，适合大多数期货分析场景
# 标签: ['default', 'fundamentals', 'standard']
# 默认: True
# ---
# 模版: 基本面分析 - 保守模版
# 描述: 保守的估值分析，强调风险控制
# 标签: ['conservative', 'fundamentals']
# 默认: False
```

### 场景4: 加载并查看模版详情

```python
# 加载完整的模版
template = template_manager.load_template("fundamentals", "conservative")

print("模版信息:")
print(f"版本: {template['version']}")
print(f"分析师类型: {template['analyst_type']}")
print(f"名称: {template['name']}")
print()

print("系统提示词:")
print(template['system_prompt'][:200] + "...")
print()

print("工具指导:")
print(template['tool_guidance'][:200] + "...")
print()

print("约束条件:")
print(f"禁止: {template['constraints']['forbidden']}")
print(f"必需: {template['constraints']['required']}")
```

### 场景5: 渲染模版变量

```python
# 加载模版
template = template_manager.load_template("fundamentals", "default")

# 准备变量
variables = {
    "ticker": "000001",
    "company_name": "平安银行",
    "market_name": "A股",
    "currency_name": "人民币",
    "currency_symbol": "¥",
    "current_date": "2024-01-15",
    "start_date": "2023-01-15"
}

# 渲染模版
rendered = template_manager.render_template(template, **variables)

print("渲染后的系统提示词:")
print(rendered['system_prompt'])
```

### 场景6: Web API 使用

```bash
# 1. 列出所有基本面分析师模版
curl -X GET "http://localhost:8000/api/prompts/templates/fundamentals"

# 响应:
# [
#   {
#     "name": "基本面分析 - 默认模版",
#     "description": "标准的基本面分析提示词",
#     "is_default": true,
#     "tags": ["default", "fundamentals"]
#   },
#   ...
# ]

# 2. 获取特定模版详情
curl -X GET "http://localhost:8000/api/prompts/templates/fundamentals/default"

# 3. 预览模版（渲染变量）
curl -X POST "http://localhost:8000/api/prompts/templates/fundamentals/default/preview" \
  -H "Content-Type: application/json" \
  -d '{
    "variables": {
      "ticker": "000001",
      "company_name": "平安银行",
      "market_name": "A股",
      "currency_name": "人民币",
      "currency_symbol": "¥",
      "current_date": "2024-01-15"
    }
  }'

# 4. 创建自定义模版
curl -X POST "http://localhost:8000/api/prompts/templates/fundamentals" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "我的自定义模版",
    "description": "基于个人偏好的模版",
    "system_prompt": "你是...",
    "tool_guidance": "...",
    "analysis_requirements": "...",
    "output_format": "...",
    "constraints": {...},
    "tags": ["custom", "personal"]
  }'

# 5. 更新模版
curl -X PUT "http://localhost:8000/api/prompts/templates/fundamentals/my-custom" \
  -H "Content-Type: application/json" \
  -d '{...更新的模版内容...}'

# 6. 删除模版
curl -X DELETE "http://localhost:8000/api/prompts/templates/fundamentals/my-custom"
```

### 场景7: 前端集成

```typescript
// 1. 获取可用模版列表
async function getAvailableTemplates(analystType: string) {
  const response = await fetch(`/api/prompts/templates/${analystType}`);
  return response.json();
}

// 2. 用户选择模版
const selectedTemplates = {
  fundamentals: "conservative",
  market: "short_term",
  news: "real_time",
  social: "sentiment_focus"
};

// 3. 发起分析请求
async function startAnalysis(ticker: string, templates: any) {
  const response = await fetch('/api/analysis', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ticker: ticker,
      selected_analysts: ["fundamentals", "market", "news", "social"],
      analyst_templates: templates
    })
  });
  return response.json();
}

// 4. 预览模版
async function previewTemplate(analystType: string, templateName: string, variables: any) {
  const response = await fetch(
    `/api/prompts/templates/${analystType}/${templateName}/preview`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ variables })
    }
  );
  return response.json();
}
```

### 场景8: 创建自定义模版

```python
# 创建一个针对科技股的特殊模版
custom_template = {
    "version": "1.0",
    "analyst_type": "fundamentals",
    "name": "科技股专用模版",
    "description": "针对科技行业的基本面分析模版，强调研发投入和市场前景",
    "system_prompt": """
    你是一位专业的科技股基本面分析师。
    
    科技股分析重点：
    1. 研发投入和创新能力
    2. 市场规模和增长潜力
    3. 竞争优势和护城河
    4. 管理团队和战略方向
    5. 现金流和盈利能力
    """,
    "tool_guidance": "立即调用 get_stock_fundamentals_unified 工具获取数据",
    "analysis_requirements": "重点分析科技行业特有的财务指标和竞争因素",
    "output_format": "# 科技股基本面分析\n## 行业地位\n## 创新能力\n## 财务表现",
    "constraints": {
        "forbidden": ["不允许忽视研发投入"],
        "required": ["必须分析市场前景"]
    },
    "tags": ["custom", "tech", "fundamentals"]
}

# 保存自定义模版
template_manager.save_custom_template("fundamentals", custom_template)

# 使用自定义模版
analyst = create_fundamentals_analyst(
    llm=llm,
    toolkit=toolkit,
    template_name="科技股专用模版",
    template_manager=template_manager
)
```

### 场景9: 模版版本管理

```python
# 获取模版的所有版本
versions = template_manager.get_template_versions("fundamentals", "default")
print(f"可用版本: {versions}")  # ['1.0', '1.1', '1.2']

# 加载特定版本
old_template = template_manager.load_template_version(
    "fundamentals", 
    "default", 
    version="1.0"
)

# 回滚到旧版本
template_manager.rollback_template(
    "fundamentals",
    "default",
    target_version="1.0"
)
```

### 场景10: A/B测试

```python
# 创建两个不同的模版进行A/B测试
template_a = template_manager.load_template("market", "short_term")
template_b = template_manager.load_template("market", "long_term")

# 使用模版A分析
analyst_a = create_market_analyst(
    llm=llm,
    toolkit=toolkit,
    template_name="short_term"
)
result_a = analyst_a(state)

# 使用模版B分析
analyst_b = create_market_analyst(
    llm=llm,
    toolkit=toolkit,
    template_name="long_term"
)
result_b = analyst_b(state)

# 对比结果
print("短期分析结果:", result_a)
print("长期分析结果:", result_b)
```

