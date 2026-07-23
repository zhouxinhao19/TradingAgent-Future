# 分析师提示词模版系统设计方案

## 📋 概述

为每个分析师智能体提供可配置的提示词模版系统，允许用户选择、编辑和自定义分析师的行为指导。

## 🎯 核心目标

1. **模版管理**: 为4个分析师（基本面、市场、新闻、社媒）提供预设模版
2. **用户自定义**: 用户可以编辑、创建、保存自定义模版
3. **版本控制**: 支持模版版本管理和回滚
4. **动态加载**: 分析师在运行时动态加载选定的模版
5. **前端集成**: Web界面支持模版选择和编辑

## 📁 系统架构

### 1. 目录结构

```
prompts/
├── templates/                    # 模版定义
│   ├── fundamentals/            # 基本面分析师模版
│   │   ├── default.yaml         # 默认模版
│   │   ├── conservative.yaml    # 保守模版
│   │   └── aggressive.yaml      # 激进模版
│   ├── market/                  # 市场分析师模版
│   ├── news/                    # 新闻分析师模版
│   └── social/                  # 社媒分析师模版
├── schema/                       # 模版schema定义
│   └── prompt_template_schema.json
└── README.md

tradingagents/
├── config/
│   └── prompt_manager.py        # 提示词管理器
└── agents/
    └── analysts/
        └── prompt_templates.py  # 提示词模版工具函数
```

### 2. 模版文件格式 (YAML)

```yaml
# prompts/templates/fundamentals/default.yaml
version: "1.0"
analyst_type: "fundamentals"
name: "基本面分析 - 默认模版"
description: "标准的基本面分析提示词"
created_at: "2024-01-01"
tags: ["default", "fundamentals"]

# 系统提示词 - 定义分析师角色和职责
system_prompt: |
  你是一位专业的期货品种基本面分析师。
  [详细的系统提示词内容]

# 工具调用指导 - 指导如何使用工具
tool_guidance: |
  1. 立即调用 get_stock_fundamentals_unified 工具
  2. 等待工具返回真实数据
  [详细的工具使用指导]

# 分析要求 - 具体的分析维度
analysis_requirements: |
  - 基于真实数据进行深度基本面分析
  - 计算并提供合理价位区间
  [详细的分析要求]

# 输出格式 - 期望的输出结构
output_format: |
  # 公司基本信息
  ## 财务数据分析
  ## 估值指标分析
  [详细的输出格式]

# 约束条件 - 禁止和强制要求
constraints:
  forbidden:
    - "不允许假设数据"
    - "不允许编造信息"
  required:
    - "必须调用工具"
    - "必须使用中文"
```

## 🔧 核心模块设计

### 1. PromptTemplateManager (提示词管理器)

```python
class PromptTemplateManager:
    """提示词模版管理器"""
    
    def __init__(self, template_dir: str):
        """初始化管理器"""
        
    def load_template(self, analyst_type: str, template_name: str) -> Dict:
        """加载指定的模版"""
        
    def list_templates(self, analyst_type: str) -> List[Dict]:
        """列出某个分析师的所有模版"""
        
    def save_custom_template(self, analyst_type: str, template: Dict) -> str:
        """保存自定义模版"""
        
    def get_template_versions(self, analyst_type: str, template_name: str) -> List[Dict]:
        """获取模版版本历史"""
        
    def validate_template(self, template: Dict) -> bool:
        """验证模版格式"""
```

### 2. 分析师集成

每个分析师在初始化时：
1. 接收 `template_name` 参数
2. 通过 PromptTemplateManager 加载模版
3. 将模版内容注入到提示词中
4. 运行时使用自定义的提示词

### 3. 数据模型

```python
class PromptTemplate(BaseModel):
    """提示词模版数据模型"""
    id: str                          # 唯一标识
    analyst_type: str                # 分析师类型
    name: str                        # 模版名称
    description: str                 # 模版描述
    version: str                     # 版本号
    system_prompt: str               # 系统提示词
    tool_guidance: str               # 工具使用指导
    analysis_requirements: str       # 分析要求
    output_format: str               # 输出格式
    constraints: Dict[str, List]     # 约束条件
    tags: List[str]                  # 标签
    created_at: datetime             # 创建时间
    updated_at: datetime             # 更新时间
    is_default: bool = False         # 是否为默认模版
```

## 🌐 Web API 接口

```
GET    /api/prompts/templates/{analyst_type}
       - 获取某个分析师的所有模版

GET    /api/prompts/templates/{analyst_type}/{template_name}
       - 获取指定模版详情

POST   /api/prompts/templates/{analyst_type}
       - 创建新模版

PUT    /api/prompts/templates/{analyst_type}/{template_name}
       - 更新模版

DELETE /api/prompts/templates/{analyst_type}/{template_name}
       - 删除模版

POST   /api/prompts/templates/{analyst_type}/{template_name}/preview
       - 预览模版（渲染变量）

GET    /api/prompts/templates/{analyst_type}/{template_name}/versions
       - 获取模版版本历史
```

## 📊 4个分析师的模版设计

### 基本面分析师 (Fundamentals)
- **default**: 标准基本面分析
- **conservative**: 保守估值分析
- **aggressive**: 激进成长分析

### 市场分析师 (Market)
- **default**: 标准技术分析
- **short_term**: 短期交易分析
- **long_term**: 长期趋势分析

### 新闻分析师 (News)
- **default**: 标准新闻分析
- **real_time**: 实时新闻快速分析
- **deep**: 深度新闻影响分析

### 社媒分析师 (Social)
- **default**: 标准情绪分析
- **sentiment_focus**: 情绪导向分析
- **trend_focus**: 趋势导向分析

## 🔄 使用流程

1. **用户选择模版**: 在Web界面选择分析师和模版
2. **发起分析**: 调用API发起分析，传递 `template_name`
3. **加载模版**: 分析师加载对应的模版
4. **执行分析**: 使用模版中的提示词执行分析
5. **返回结果**: 返回分析结果

## ✅ 实现优先级

1. **Phase 1**: 创建模版存储结构和管理器
2. **Phase 2**: 集成到分析师代码
3. **Phase 3**: 创建Web API接口
4. **Phase 4**: 前端集成和文档

