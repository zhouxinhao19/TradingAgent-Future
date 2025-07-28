# 新闻过滤功能使用指南

## 概述

为了解决东方财富新闻API返回低质量、不相关新闻的问题，我们开发了一套完整的新闻过滤解决方案。该方案可以有效提高新闻分析师的分析质量，过滤掉ETF、指数基金等不相关的新闻内容。

## 功能特点

### 1. 基础新闻过滤器
- **快速高效**: 基于关键词规则的快速过滤
- **针对性强**: 专门针对A股新闻质量问题设计
- **易于使用**: 简单的API接口，易于集成

### 2. 增强新闻过滤器
- **多策略支持**: 规则过滤 + 语义相似度 + 本地模型分类
- **综合评分**: 多维度评分机制，更精确的过滤结果
- **可扩展性**: 支持添加新的过滤策略

### 3. 集成功能
- **无缝集成**: 可直接替换现有新闻获取函数
- **向后兼容**: 保持原有API接口不变
- **智能切换**: 根据股票类型自动选择最佳过滤策略

## 使用方法

### 方法1: 基础过滤器（推荐）

```python
from tradingagents.utils.news_filter import create_news_filter

# 创建过滤器
filter = create_news_filter('600036')  # 招商银行

# 获取原始新闻
from tradingagents.dataflows.akshare_utils import get_stock_news_em
original_news = get_stock_news_em('600036')

# 过滤新闻
filtered_news = filter.filter_news(original_news, min_score=30)

# 查看过滤统计
stats = filter.get_filter_statistics(original_news, filtered_news)
print(f"过滤率: {stats['filter_rate']:.1f}%")
```

### 方法2: 增强过滤器

```python
from tradingagents.utils.enhanced_news_filter import create_enhanced_news_filter

# 创建增强过滤器
enhanced_filter = create_enhanced_news_filter(
    '600036',
    use_semantic=False,      # 是否使用语义相似度
    use_local_model=False    # 是否使用本地分类模型
)

# 执行增强过滤
enhanced_result = enhanced_filter.filter_news_enhanced(news_data, min_score=40)
```

### 方法3: 集成功能（最简单）

```python
from tradingagents.utils.news_filter_integration import create_filtered_realtime_news_function

# 创建增强版实时新闻函数
enhanced_news_func = create_filtered_realtime_news_function()

# 直接获取过滤后的新闻报告
filtered_report = enhanced_news_func(
    ticker="600036",
    curr_date="2025-07-28",
    enable_filter=True,      # 启用过滤
    min_score=30            # 最低评分阈值
)
```

## 过滤效果

### 测试结果
- **原始新闻**: 100条
- **过滤后新闻**: 通常保留10-30条高质量新闻
- **过滤率**: 70-90%
- **处理速度**: 毫秒级响应

### 过滤示例

**过滤前**:
```
1. 上证180ETF指数基金（530280）自带杠铃策略
2. 银行ETF指数(512730)多只成分股上涨
3. 无标题
4. 招商银行发布2024年第三季度业绩报告
5. 招商银行与科技公司签署战略合作协议
```

**过滤后**:
```
1. 招商银行发布2024年第三季度业绩报告 (评分: 85.0)
2. 招商银行与科技公司签署战略合作协议 (评分: 75.0)
```

## 评分机制

### 基础评分规则
- **强相关关键词**: +30分（如"招商银行"、"600036"）
- **包含关键词**: +20分（如"银行"、"金融"）
- **排除关键词**: -50分（如"ETF"、"指数基金"）
- **无标题**: -30分

### 评分阈值建议
- **宽松过滤**: min_score=20（保留更多新闻）
- **标准过滤**: min_score=30（推荐设置）
- **严格过滤**: min_score=50（只保留高度相关新闻）

## 性能优化

### 1. 缓存机制
- 过滤器实例可重复使用
- 避免重复创建过滤器对象

### 2. 批量处理
- 支持DataFrame批量过滤
- 比逐条过滤效率更高

### 3. 内存管理
- 及时释放大型DataFrame
- 使用生成器处理大量数据

## 故障排除

### 常见问题

1. **导入错误**
   ```
   ModuleNotFoundError: No module named 'tradingagents.utils.news_filter'
   ```
   **解决**: 确保文件路径正确，检查sys.path设置

2. **过滤结果为空**
   ```
   过滤后新闻数量为0
   ```
   **解决**: 降低min_score阈值，检查新闻数据格式

3. **性能问题**
   ```
   过滤速度较慢
   ```
   **解决**: 使用基础过滤器，避免启用语义分析

### 调试技巧

```python
# 启用详细日志
import logging
logging.basicConfig(level=logging.INFO)

# 查看过滤详情
filter.debug_mode = True
filtered_news = filter.filter_news(news_data, min_score=30)
```

## 扩展开发

### 添加新的过滤规则

```python
class CustomNewsFilter(NewsRelevanceFilter):
    def __init__(self, ticker):
        super().__init__(ticker)
        # 添加自定义关键词
        self.exclude_keywords.extend(['自定义排除词'])
        self.include_keywords.extend(['自定义包含词'])
    
    def calculate_custom_score(self, title, content):
        # 实现自定义评分逻辑
        score = 0
        # ... 自定义逻辑
        return score
```

### 集成外部模型

```python
# 集成sentence-transformers
from sentence_transformers import SentenceTransformer

class SemanticNewsFilter:
    def __init__(self, ticker):
        self.model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        self.ticker = ticker
    
    def calculate_semantic_score(self, text):
        # 实现语义相似度计算
        pass
```

## 最佳实践

1. **选择合适的过滤器**
   - 日常使用: 基础过滤器
   - 重要分析: 增强过滤器
   - 生产环境: 集成功能

2. **设置合理的阈值**
   - 根据业务需求调整min_score
   - 定期评估过滤效果

3. **监控过滤质量**
   - 记录过滤统计信息
   - 定期人工检查过滤结果

4. **性能优化**
   - 复用过滤器实例
   - 合理设置批处理大小

## 更新日志

### v1.0.0 (2025-07-28)
- 初始版本发布
- 基础新闻过滤器
- 增强新闻过滤器
- 集成功能
- 完整测试套件

## 技术支持

如有问题或建议，请参考：
- 测试脚本: `test_news_filtering.py`
- 演示脚本: `demo_news_filtering.py`
- 问题分析报告: `NEWS_QUALITY_ANALYSIS_REPORT.md`
- 方案设计文档: `NEWS_FILTERING_SOLUTION_DESIGN.md`