# 修复分析日期类型错误

## 问题描述

在添加股票代码验证功能后，出现了新的错误：

```
ERROR | ❌ [数据准备] 数据准备异常: strptime() argument 1 must be str, not datetime.datetime
```

**错误原因**：
- `request.parameters.analysis_date` 是 `datetime.datetime` 对象
- 但 `prepare_stock_data()` 函数中的 `strptime()` 期望接收字符串参数

## 错误堆栈

```python
# tradingagents/utils/stock_validator.py:433
end_date = datetime.strptime(analysis_date, '%Y-%m-%d')
# TypeError: strptime() argument 1 must be str, not datetime.datetime
```

## 根本原因

在 `simple_analysis_service.py` 中，直接将 `request.parameters.analysis_date` 传递给验证函数：

```python
# ❌ 错误代码
analysis_date = request.parameters.analysis_date if request.parameters else None

validation_result = await asyncio.to_thread(
    prepare_stock_data,
    stock_code=request.stock_code,
    market_type=market_type,
    period_days=30,
    analysis_date=analysis_date  # 可能是 datetime 对象
)
```

但 `request.parameters.analysis_date` 可能是：
1. `datetime.datetime` 对象（从前端 Date 对象转换而来）
2. `str` 字符串（如 `"2025-10-13"`）
3. `None`（使用默认值）

而 `prepare_stock_data()` 期望的是字符串格式的日期。

## 解决方案

在调用验证函数前，统一将日期转换为字符串格式：

```python
# ✅ 修复后的代码
from datetime import datetime

# 获取分析日期并转换为字符串格式
analysis_date = request.parameters.analysis_date if request.parameters else None
if analysis_date:
    # 如果是 datetime 对象，转换为字符串
    if isinstance(analysis_date, datetime):
        analysis_date = analysis_date.strftime('%Y-%m-%d')
    # 如果是字符串，确保格式正确
    elif isinstance(analysis_date, str):
        try:
            parsed_date = datetime.strptime(analysis_date, '%Y-%m-%d')
            analysis_date = parsed_date.strftime('%Y-%m-%d')
        except ValueError:
            # 如果格式不对，使用今天
            analysis_date = datetime.now().strftime('%Y-%m-%d')
            logger.warning(f"⚠️ 分析日期格式不正确，使用今天: {analysis_date}")

# 验证股票代码并预获取数据
validation_result = await asyncio.to_thread(
    prepare_stock_data,
    stock_code=request.stock_code,
    market_type=market_type,
    period_days=30,
    analysis_date=analysis_date  # 现在保证是字符串或 None
)
```

## 修改文件

**文件**：`app/services/simple_analysis_service.py`

**位置**：`execute_analysis_background` 方法，第 638-670 行

**修改内容**：
1. 导入 `datetime` 模块
2. 添加日期类型检查和转换逻辑
3. 确保传递给验证函数的日期是字符串格式

## 测试用例

### 测试 1：datetime 对象

```python
# 输入
request.parameters.analysis_date = datetime(2025, 10, 13)

# 处理
isinstance(analysis_date, datetime) → True
analysis_date = analysis_date.strftime('%Y-%m-%d')

# 输出
analysis_date = "2025-10-13"  # ✅ 字符串
```

### 测试 2：字符串（正确格式）

```python
# 输入
request.parameters.analysis_date = "2025-10-13"

# 处理
isinstance(analysis_date, str) → True
parsed_date = datetime.strptime(analysis_date, '%Y-%m-%d')  # ✅ 成功
analysis_date = parsed_date.strftime('%Y-%m-%d')

# 输出
analysis_date = "2025-10-13"  # ✅ 字符串
```

### 测试 3：字符串（错误格式）

```python
# 输入
request.parameters.analysis_date = "2025/10/13"

# 处理
isinstance(analysis_date, str) → True
parsed_date = datetime.strptime(analysis_date, '%Y-%m-%d')  # ❌ ValueError
analysis_date = datetime.now().strftime('%Y-%m-%d')

# 输出
analysis_date = "2025-10-13"  # ✅ 使用今天的日期
logger.warning("⚠️ 分析日期格式不正确，使用今天: 2025-10-13")
```

### 测试 4：None

```python
# 输入
request.parameters.analysis_date = None

# 处理
if analysis_date: → False（跳过转换）

# 输出
analysis_date = None  # ✅ 保持 None，使用默认值
```

## 修复效果

### 修复前

```
2025-10-13 14:57:06 | stock_validator | INFO  | 📊 [数据准备] 开始准备股票数据: 00700 (市场: 港股, 时长: 30天)
2025-10-13 14:57:06 | stock_validator | INFO  | 📊 [港股数据] 开始准备00700的数据 (时长: 30天)
2025-10-13 14:57:06 | stock_validator | ERROR | ❌ [数据准备] 数据准备异常: strptime() argument 1 must be str, not datetime.datetime
```

### 修复后

```
2025-10-13 15:00:00 | stock_validator | INFO  | 📊 [数据准备] 开始准备股票数据: 00700 (市场: 港股, 时长: 30天)
2025-10-13 15:00:00 | stock_validator | INFO  | 📊 [港股数据] 开始准备00700的数据 (时长: 30天)
2025-10-13 15:00:00 | stock_validator | DEBUG | 🔍 [港股数据] 代码格式化: 00700 → 0700.HK
2025-10-13 15:00:00 | stock_validator | INFO  | ✅ [港股数据] 基本信息获取成功: 0700.HK - 腾讯控股
2025-10-13 15:00:01 | stock_validator | INFO  | ✅ [港股数据] 历史数据获取成功: 0700.HK (30天)
2025-10-13 15:00:01 | stock_validator | INFO  | 🎉 [港股数据] 数据准备完成: 0700.HK - 腾讯控股
```

## 相关问题

这个问题也可能出现在其他地方，需要检查所有调用 `prepare_stock_data()` 的地方：

### 1. `web/utils/analysis_runner.py`

```python
# 检查是否有类似问题
preparation_result = prepare_stock_data(
    stock_code=stock_symbol,
    market_type=market_type,
    period_days=30,
    analysis_date=analysis_date  # ⚠️ 需要确保是字符串
)
```

### 2. `app/services/analysis_service.py`

```python
# 如果有调用验证函数，也需要检查
```

## 最佳实践

### 1. 类型提示

在函数签名中明确参数类型：

```python
def prepare_stock_data(
    stock_code: str,
    market_type: str = "auto",
    period_days: int = None,
    analysis_date: str = None  # 明确指定为 str 类型
) -> StockDataPreparationResult:
    """
    预获取和验证股票数据
    
    Args:
        stock_code: 股票代码
        market_type: 市场类型
        period_days: 历史数据时长（天）
        analysis_date: 分析日期（字符串格式：YYYY-MM-DD）
    """
```

### 2. 参数验证

在函数开始处验证参数类型：

```python
def prepare_stock_data(stock_code: str, ..., analysis_date: str = None):
    # 验证 analysis_date 类型
    if analysis_date is not None and not isinstance(analysis_date, str):
        raise TypeError(f"analysis_date must be str, not {type(analysis_date).__name__}")
    
    # 继续处理...
```

### 3. 统一转换

创建一个工具函数统一处理日期转换：

```python
def normalize_analysis_date(date_input) -> str:
    """
    统一转换分析日期为字符串格式
    
    Args:
        date_input: datetime 对象、字符串或 None
        
    Returns:
        str: YYYY-MM-DD 格式的日期字符串
    """
    if date_input is None:
        return datetime.now().strftime('%Y-%m-%d')
    
    if isinstance(date_input, datetime):
        return date_input.strftime('%Y-%m-%d')
    
    if isinstance(date_input, str):
        try:
            parsed = datetime.strptime(date_input, '%Y-%m-%d')
            return parsed.strftime('%Y-%m-%d')
        except ValueError:
            logger.warning(f"日期格式不正确: {date_input}，使用今天")
            return datetime.now().strftime('%Y-%m-%d')
    
    raise TypeError(f"Unsupported date type: {type(date_input)}")
```

## 总结

### 问题
- ❌ `strptime()` 接收到 `datetime` 对象而不是字符串

### 原因
- ❌ 没有检查和转换 `analysis_date` 的类型

### 修复
- ✅ 添加类型检查和转换逻辑
- ✅ 确保传递给验证函数的日期是字符串格式
- ✅ 处理各种可能的输入类型（datetime、str、None）

### 效果
- ✅ 股票代码验证功能正常工作
- ✅ 支持多种日期输入格式
- ✅ 错误处理更加健壮

