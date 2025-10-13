# 修复市场类型硬编码问题

## 问题描述

用户反馈：前端明明选择的是**港股**，但后端分析时却识别为**美股**。

**问题现象**：
```
前端选择: 港股 (00700)
↓
后端接收: market_type = "港股"
↓
分析配置: market_type = "A股"  ← ❌ 被硬编码覆盖
↓
分析执行: 使用 A股 的配置和工具
```

## 问题根源

在 `app/services/simple_analysis_service.py` 的 `_run_analysis_sync` 方法中，调用 `create_analysis_config` 时，`market_type` 参数被硬编码为 `"A股"`：

```python
# ❌ 错误代码 (第 994 行)
config = create_analysis_config(
    research_depth=research_depth,
    selected_analysts=request.parameters.selected_analysts if request.parameters else ["market", "fundamentals"],
    quick_model=quick_model,
    deep_model=deep_model,
    llm_provider=quick_provider,
    market_type="A股"  # ← 硬编码！忽略了前端传递的市场类型
)
```

**问题影响**：
1. ❌ 前端选择的市场类型被忽略
2. ❌ 所有分析都使用 A股 的配置
3. ❌ 港股、美股的分析结果不准确
4. ❌ 数据源选择错误

## 解决方案

从 `request.parameters` 中获取前端传递的 `market_type`，而不是硬编码：

```python
# ✅ 修复后的代码
# 获取市场类型
market_type = request.parameters.market_type if request.parameters else "A股"
logger.info(f"📊 [市场类型] 使用市场类型: {market_type}")

# 创建分析配置（支持混合模式）
config = create_analysis_config(
    research_depth=research_depth,
    selected_analysts=request.parameters.selected_analysts if request.parameters else ["market", "fundamentals"],
    quick_model=quick_model,
    deep_model=deep_model,
    llm_provider=quick_provider,
    market_type=market_type  # ← 使用前端传递的市场类型
)
```

## 修改文件

**文件**：`app/services/simple_analysis_service.py`

**位置**：`_run_analysis_sync` 方法，第 987-999 行

**修改内容**：
1. 添加从 `request.parameters` 获取 `market_type` 的逻辑
2. 添加日志记录市场类型
3. 将获取的 `market_type` 传递给 `create_analysis_config`

## 数据流追踪

### 1. 前端提交

<augment_code_snippet path="frontend/src/views/Analysis/SingleAnalysis.vue" mode="EXCERPT">
```typescript
const request: SingleAnalysisRequest = {
  symbol: analysisForm.symbol,
  stock_code: analysisForm.symbol,
  parameters: {
    market_type: analysisForm.market,  // ← 前端传递市场类型
    analysis_date: analysisDate.toISOString().split('T')[0],
    research_depth: getDepthDescription(analysisForm.researchDepth),
    // ...
  }
}
```
</augment_code_snippet>

### 2. 后端接收

<augment_code_snippet path="app/models/analysis.py" mode="EXCERPT">
```python
class AnalysisParameters(BaseModel):
    market_type: str = "A股"  # ← 接收前端传递的市场类型
    analysis_date: Optional[datetime] = None
    research_depth: str = "标准"
    # ...
```
</augment_code_snippet>

### 3. 验证阶段

<augment_code_snippet path="app/services/simple_analysis_service.py" mode="EXCERPT">
```python
# 获取市场类型
market_type = request.parameters.market_type if request.parameters else "A股"

# 验证股票代码并预获取数据
validation_result = await asyncio.to_thread(
    prepare_stock_data,
    stock_code=request.stock_code,
    market_type=market_type,  # ← 使用正确的市场类型验证
    period_days=30
)
```
</augment_code_snippet>

### 4. 配置创建（修复前）

```python
# ❌ 修复前：硬编码为 "A股"
config = create_analysis_config(
    research_depth=research_depth,
    selected_analysts=request.parameters.selected_analysts,
    quick_model=quick_model,
    deep_model=deep_model,
    llm_provider=quick_provider,
    market_type="A股"  # ← 硬编码，忽略前端传递的值
)
```

### 5. 配置创建（修复后）

```python
# ✅ 修复后：使用前端传递的市场类型
market_type = request.parameters.market_type if request.parameters else "A股"
logger.info(f"📊 [市场类型] 使用市场类型: {market_type}")

config = create_analysis_config(
    research_depth=research_depth,
    selected_analysts=request.parameters.selected_analysts,
    quick_model=quick_model,
    deep_model=deep_model,
    llm_provider=quick_provider,
    market_type=market_type  # ← 使用正确的市场类型
)
```

## 测试用例

### 测试 1：A股分析

```python
# 前端输入
analysisForm.market = "A股"
analysisForm.stockCode = "000001"

# 后端接收
request.parameters.market_type = "A股"

# 配置创建
market_type = "A股"  # ✅ 正确

# 日志输出
📊 [市场类型] 使用市场类型: A股
🔧 [3级-标准分析] A股平衡速度和质量（推荐）
```

### 测试 2：港股分析

```python
# 前端输入
analysisForm.market = "港股"
analysisForm.stockCode = "00700"

# 后端接收
request.parameters.market_type = "港股"

# 配置创建（修复前）
market_type = "A股"  # ❌ 错误！被硬编码覆盖

# 配置创建（修复后）
market_type = "港股"  # ✅ 正确

# 日志输出
📊 [市场类型] 使用市场类型: 港股
🔧 [3级-标准分析] 港股平衡速度和质量（推荐）
```

### 测试 3：美股分析

```python
# 前端输入
analysisForm.market = "美股"
analysisForm.stockCode = "AAPL"

# 后端接收
request.parameters.market_type = "美股"

# 配置创建（修复前）
market_type = "A股"  # ❌ 错误！被硬编码覆盖

# 配置创建（修复后）
market_type = "美股"  # ✅ 正确

# 日志输出
📊 [市场类型] 使用市场类型: 美股
🔧 [3级-标准分析] 美股平衡速度和质量（推荐）
```

## 影响范围

### 1. 数据源选择

不同市场使用不同的数据源：

```python
# A股
- Tushare
- AkShare
- 东方财富

# 港股
- Yahoo Finance
- AkShare (港股)
- 东方财富 (港股)

# 美股
- Yahoo Finance
- Alpha Vantage
- Finnhub
```

如果市场类型错误，会导致：
- ❌ 使用错误的数据源
- ❌ 获取不到数据或数据不准确
- ❌ 分析结果不可靠

### 2. 分析工具选择

不同市场使用不同的分析工具：

```python
# A股
- 技术指标分析（A股特有）
- 资金流向分析（A股特有）
- 北向资金分析（A股特有）

# 港股
- 港股通资金分析
- 恒生指数相关性分析

# 美股
- 期权分析
- 机构持仓分析
- SEC文件分析
```

### 3. 分析师配置

不同市场的分析师可能有不同的配置：

```python
# A股
- 社媒分析师：禁用（国内数据源限制）

# 港股
- 社媒分析师：启用

# 美股
- 社媒分析师：启用
```

## 日志对比

### 修复前

```
INFO  | 🚀 开始后台执行分析任务: xxx
INFO  | 🔍 开始验证股票代码: 00700
INFO  | 📊 [数据准备] 开始准备股票数据: 00700 (市场: 港股, 时长: 30天)
INFO  | ✅ 股票代码验证通过: 00700 - 腾讯控股
INFO  | 📊 市场类型: 港股
INFO  | 🔄 [线程池] 开始执行分析: xxx - 00700
INFO  | ⚙️ 配置分析参数
INFO  | 🔧 [3级-标准分析] A股平衡速度和质量（推荐）  ← ❌ 错误！应该是港股
```

### 修复后

```
INFO  | 🚀 开始后台执行分析任务: xxx
INFO  | 🔍 开始验证股票代码: 00700
INFO  | 📊 [数据准备] 开始准备股票数据: 00700 (市场: 港股, 时长: 30天)
INFO  | ✅ 股票代码验证通过: 00700 - 腾讯控股
INFO  | 📊 市场类型: 港股
INFO  | 🔄 [线程池] 开始执行分析: xxx - 00700
INFO  | ⚙️ 配置分析参数
INFO  | 📊 [市场类型] 使用市场类型: 港股  ← ✅ 新增日志
INFO  | 🔧 [3级-标准分析] 港股平衡速度和质量（推荐）  ← ✅ 正确！
```

## 相关代码检查

需要检查其他地方是否也有类似的硬编码问题：

### 1. `app/services/analysis_service.py`

```python
# 第 162 行
config = create_analysis_config(
    research_depth=task.parameters.research_depth,
    selected_analysts=task.parameters.selected_analysts or ["market", "fundamentals"],
    quick_model=quick_model,
    deep_model=deep_model,
    llm_provider=llm_provider,
    market_type=getattr(task.parameters, 'market_type', "A股"),  # ✅ 正确
    quick_model_config=quick_model_config,
    deep_model_config=deep_model_config
)
```

### 2. `web/utils/analysis_runner.py`

需要检查是否也有类似问题。

## 总结

### 问题
- ❌ `market_type` 被硬编码为 `"A股"`
- ❌ 忽略了前端传递的市场类型
- ❌ 导致港股、美股分析使用错误的配置

### 原因
- ❌ 没有从 `request.parameters` 获取 `market_type`
- ❌ 直接硬编码为 `"A股"`

### 修复
- ✅ 从 `request.parameters.market_type` 获取市场类型
- ✅ 添加日志记录市场类型
- ✅ 传递正确的市场类型给配置函数

### 效果
- ✅ 前端选择的市场类型被正确使用
- ✅ 不同市场使用正确的数据源和工具
- ✅ 分析结果更加准确

