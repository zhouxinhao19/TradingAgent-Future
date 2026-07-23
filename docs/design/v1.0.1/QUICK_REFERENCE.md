# 提示词模版系统 - 快速参考指南

## 📋 核心概念速览

| 概念 | 说明 | 示例 |
|------|------|------|
| **分析师类型** | 4种分析师 | fundamentals, market, news, social |
| **模版** | 分析师的提示词配置 | default, conservative, aggressive |
| **模版变量** | 动态注入的参数 | {ticker}, {company_name} |
| **模版版本** | 模版的历史版本 | v1.0, v1.1, v1.2 |
| **自定义模版** | 用户创建的模版 | 保存到数据库 |

## 🚀 快速开始

### 1. 加载默认模版
```python
from tradingagents.config.prompt_manager import PromptTemplateManager

manager = PromptTemplateManager()
template = manager.load_template("fundamentals", "default")
```

### 2. 列出所有模版
```python
templates = manager.list_templates("fundamentals")
for t in templates:
    print(f"{t['name']} - {t['description']}")
```

### 3. 创建分析师（使用模版）
```python
from tradingagents.agents import create_fundamentals_analyst

analyst = create_fundamentals_analyst(
    llm=llm,
    toolkit=toolkit,
    template_name="conservative"
)
```

### 4. 渲染模版变量
```python
rendered = manager.render_template(
    template,
    ticker="000001",
    company_name="平安银行"
)
```

## 📊 4个分析师的模版

### 基本面分析师 (fundamentals)
- **default**: 标准基本面分析
- **conservative**: 保守估值分析
- **aggressive**: 激进成长分析

### 市场分析师 (market)
- **default**: 标准技术分析
- **short_term**: 短期交易分析
- **long_term**: 长期趋势分析

### 新闻分析师 (news)
- **default**: 标准新闻分析
- **real_time**: 实时新闻快速分析
- **deep**: 深度新闻影响分析

### 社媒分析师 (social)
- **default**: 标准情绪分析
- **sentiment_focus**: 情绪导向分析
- **trend_focus**: 趋势导向分析

## 🔌 API快速参考

### 列表查询
```bash
GET /api/prompts/templates/fundamentals
```

### 获取详情
```bash
GET /api/prompts/templates/fundamentals/default
```

### 创建模版
```bash
POST /api/prompts/templates/fundamentals
Content-Type: application/json

{
  "name": "我的模版",
  "description": "...",
  "system_prompt": "...",
  "tool_guidance": "...",
  "analysis_requirements": "...",
  "output_format": "...",
  "constraints": {...}
}
```

### 更新模版
```bash
PUT /api/prompts/templates/fundamentals/my-template
```

### 删除模版
```bash
DELETE /api/prompts/templates/fundamentals/my-template
```

### 预览模版
```bash
POST /api/prompts/templates/fundamentals/default/preview
Content-Type: application/json

{
  "variables": {
    "ticker": "000001",
    "company_name": "平安银行"
  }
}
```

## 📁 文件结构速览

```
prompts/
├── templates/
│   ├── fundamentals/
│   │   ├── default.yaml
│   │   ├── conservative.yaml
│   │   └── aggressive.yaml
│   ├── market/
│   ├── news/
│   └── social/
└── schema/
    └── prompt_template_schema.json
```

## 🎯 常见任务

### 任务1: 使用保守模版分析
```python
analyst = create_fundamentals_analyst(
    llm, toolkit, template_name="conservative"
)
result = analyst(state)
```

### 任务2: 对比两个模版
```python
analyst_a = create_market_analyst(llm, toolkit, "short_term")
analyst_b = create_market_analyst(llm, toolkit, "long_term")

result_a = analyst_a(state)
result_b = analyst_b(state)
```

### 任务3: 创建自定义模版
```python
custom = {
    "version": "1.0",
    "analyst_type": "fundamentals",
    "name": "我的模版",
    "description": "...",
    "system_prompt": "...",
    "tool_guidance": "...",
    "analysis_requirements": "...",
    "output_format": "...",
    "constraints": {...}
}
manager.save_custom_template("fundamentals", custom)
```

### 任务4: 获取模版版本
```python
versions = manager.get_template_versions("fundamentals", "default")
print(versions)  # ['1.0', '1.1', '1.2']
```

## 🔑 关键变量

所有模版支持以下变量：
- `{ticker}` - 品种代码
- `{company_name}` - 公司名称
- `{market_name}` - 市场名称
- `{currency_name}` - 货币名称
- `{currency_symbol}` - 货币符号
- `{current_date}` - 当前日期
- `{start_date}` - 开始日期
- `{tool_names}` - 可用工具列表

## 📊 模版YAML结构

```yaml
version: "1.0"
analyst_type: "fundamentals"
name: "模版名称"
description: "模版描述"
system_prompt: |
  系统提示词内容
tool_guidance: |
  工具使用指导
analysis_requirements: |
  分析要求
output_format: |
  输出格式
constraints:
  forbidden:
    - "禁止项1"
    - "禁止项2"
  required:
    - "必需项1"
    - "必需项2"
tags:
  - "tag1"
  - "tag2"
is_default: true
```

## 🧪 测试命令

```bash
# 列出基本面分析师的所有模版
curl http://localhost:8000/api/prompts/templates/fundamentals

# 获取默认模版
curl http://localhost:8000/api/prompts/templates/fundamentals/default

# 预览模版
curl -X POST http://localhost:8000/api/prompts/templates/fundamentals/default/preview \
  -H "Content-Type: application/json" \
  -d '{"variables": {"ticker": "000001", "company_name": "平安银行"}}'
```

## 💡 最佳实践

1. **使用默认模版**: 大多数场景下使用default模版
2. **A/B测试**: 对比不同模版找到最优方案
3. **版本控制**: 保留模版历史便于回滚
4. **文档注释**: 在模版中清楚说明用途
5. **标签分类**: 使用标签便于查找和管理

## 🔗 相关文档

- 完整设计: `docs/design/PROMPT_TEMPLATE_SYSTEM_SUMMARY.md`
- 系统设计: `docs/design/prompt_template_system_design.md`
- 实现指南: `docs/design/prompt_template_implementation_guide.md`
- 技术规范: `docs/design/prompt_template_technical_spec.md`
- 使用示例: `docs/design/prompt_template_usage_examples.md`
- 架构图: `docs/design/prompt_template_architecture_diagram.md`

## ❓ 常见问题

**Q: 如何修改现有模版?**
A: 编辑对应的YAML文件，或通过API更新

**Q: 如何回滚到旧版本?**
A: 使用 `manager.rollback_template(analyst_type, name, version)`

**Q: 自定义模版保存在哪里?**
A: 保存到数据库 (PromptTemplateDB表)

**Q: 模版变量如何注入?**
A: 使用 `manager.render_template(template, **variables)`

**Q: 支持多语言吗?**
A: 可以创建不同语言的模版，通过标签区分

