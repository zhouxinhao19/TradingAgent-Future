# 错误日志分离功能文档

## 📋 需求背景

用户反馈：警告日志和错误日志混在 `tradingagents.log` 中，不方便人工查找和排查问题。

**需求**：
- 将 WARNING、ERROR、CRITICAL 级别的日志单独输出到 `error.log`
- 保持原有的 `tradingagents.log` 记录所有级别的日志
- 方便快速定位和监控问题

## ✅ 实现方案

### 架构设计

采用 **双文件处理器** 方案：

1. **主日志文件**：`tradingagents.log`
   - 记录所有级别的日志（DEBUG, INFO, WARNING, ERROR, CRITICAL）
   - 用于完整的日志追踪和调试

2. **错误日志文件**：`error.log`
   - 只记录 WARNING 及以上级别（WARNING, ERROR, CRITICAL）
   - 用于快速定位问题和监控告警

### 日志级别说明

| 级别 | 说明 | tradingagents.log | error.log |
|------|------|-------------------|-----------|
| DEBUG | 调试信息 | ✅ | ❌ |
| INFO | 一般信息 | ✅ | ❌ |
| WARNING | 警告信息 | ✅ | ✅ |
| ERROR | 错误信息 | ✅ | ✅ |
| CRITICAL | 严重错误 | ✅ | ✅ |

## 🔧 实现细节

### 1. 修改日志管理器

**文件**：`tradingagents/utils/logging_manager.py`

#### 修改 1：添加错误处理器调用

**位置**：第 192-199 行

```python
# 添加处理器
self._add_console_handler(root_logger)

if not self.config['docker']['enabled'] or not self.config['docker']['stdout_only']:
    self._add_file_handler(root_logger)
    self._add_error_handler(root_logger)  # 🔧 添加错误日志处理器
    if self.config['handlers']['structured']['enabled']:
        self._add_structured_handler(root_logger)
```

#### 修改 2：实现错误处理器方法

**位置**：第 256-283 行

```python
def _add_error_handler(self, logger: logging.Logger):
    """添加错误日志处理器（只记录WARNING及以上级别）"""
    # 检查错误处理器是否启用
    error_config = self.config['handlers'].get('error', {})
    if not error_config.get('enabled', True):
        return
        
    log_dir = Path(error_config.get('directory', self.config['handlers']['file']['directory']))
    error_log_file = log_dir / error_config.get('filename', 'error.log')
    
    # 使用RotatingFileHandler进行日志轮转
    max_size = self._parse_size(error_config.get('max_size', '10MB'))
    backup_count = error_config.get('backup_count', 5)
    
    error_handler = logging.handlers.RotatingFileHandler(
        error_log_file,
        maxBytes=max_size,
        backupCount=backup_count,
        encoding='utf-8'
    )
    
    # 🔧 只记录WARNING及以上级别（WARNING, ERROR, CRITICAL）
    error_level = getattr(logging, error_config.get('level', 'WARNING'))
    error_handler.setLevel(error_level)
    
    formatter = logging.Formatter(self.config['format']['file'])
    error_handler.setFormatter(formatter)
    logger.addHandler(error_handler)
```

#### 修改 3：更新默认配置

**位置**：第 98-124 行

```python
'handlers': {
    'console': {
        'enabled': True,
        'colored': True,
        'level': log_level
    },
    'file': {
        'enabled': True,
        'level': 'DEBUG',
        'max_size': '10MB',
        'backup_count': 5,
        'directory': log_dir
    },
    'error': {
        'enabled': True,
        'level': 'WARNING',  # 只记录WARNING及以上级别
        'max_size': '10MB',
        'backup_count': 5,
        'directory': log_dir,
        'filename': 'error.log'
    },
    'structured': {
        'enabled': False,
        'level': 'INFO',
        'directory': log_dir
    }
},
```

### 2. 更新配置文件

**文件**：`config/logging.toml`

**位置**：第 25-40 行

```toml
# 文件处理器
[logging.handlers.file]
enabled = true
level = "DEBUG"
max_size = "10MB"
backup_count = 5
directory = "./logs"

# 错误日志处理器（只记录WARNING及以上级别）
[logging.handlers.error]
enabled = true
level = "WARNING"  # 只记录WARNING, ERROR, CRITICAL
max_size = "10MB"
backup_count = 5
directory = "./logs"
filename = "error.log"
```

## 📈 使用效果

### 日志文件结构

```
logs/
├── tradingagents.log       # 所有级别的日志
├── tradingagents.log.1     # 轮转备份
├── tradingagents.log.2
├── ...
├── error.log               # 只有WARNING及以上级别
├── error.log.1             # 轮转备份
├── error.log.2
└── ...
```

### 示例日志内容

#### tradingagents.log（所有日志）

```
2025-10-13 08:21:08,199 | dataflows            | INFO     | interface:get_china_stock_data_unified:1180 | 📊 [统一数据接口] 分析期货品种: 600519
2025-10-13 08:21:08,205 | dataflows            | WARNING  | data_source_manager:get_stock_data:461 | ⚠️ [数据来源: MongoDB] 未找到daily数据: 600519
2025-10-13 08:21:08,206 | dataflows            | ERROR    | data_source_manager:get_stock_data:512 | 🔄 mongodb失败，尝试备用数据源获取daily数据...
2025-10-13 08:21:08,207 | dataflows            | INFO     | data_source_manager:get_stock_data:520 | 🔄 尝试备用数据源获取daily数据: akshare
```

#### error.log（只有WARNING及以上）

```
2025-10-13 08:21:08,205 | dataflows            | WARNING  | data_source_manager:get_stock_data:461 | ⚠️ [数据来源: MongoDB] 未找到daily数据: 600519
2025-10-13 08:21:08,206 | dataflows            | ERROR    | data_source_manager:get_stock_data:512 | 🔄 mongodb失败，尝试备用数据源获取daily数据...
```

## 🎯 优势总结

### 1. 快速定位问题

**修改前**：
```bash
# 需要在所有日志中搜索错误
grep "ERROR\|WARNING" logs/tradingagents.log
```

**修改后**：
```bash
# 直接查看错误日志文件
cat logs/error.log
# 或者实时监控
tail -f logs/error.log
```

### 2. 方便监控告警

- 可以单独监控 `error.log` 文件
- 文件大小增长异常时触发告警
- 减少监控系统的噪音

### 3. 便于日志分析

- 错误日志文件更小，分析更快
- 可以单独归档和备份错误日志
- 便于统计错误频率和类型

### 4. 保持完整性

- `tradingagents.log` 仍然保留所有日志
- 不影响现有的调试和追踪流程
- 向后兼容，不破坏现有功能

## 📊 配置选项

### 启用/禁用错误日志

在 `config/logging.toml` 中：

```toml
[logging.handlers.error]
enabled = false  # 设置为false禁用错误日志
```

### 调整错误日志级别

```toml
[logging.handlers.error]
level = "ERROR"  # 只记录ERROR和CRITICAL，不记录WARNING
```

### 调整文件大小和备份数量

```toml
[logging.handlers.error]
max_size = "20MB"    # 单个文件最大20MB
backup_count = 10    # 保留10个备份文件
```

### 自定义文件名和路径

```toml
[logging.handlers.error]
directory = "./logs/errors"  # 自定义目录
filename = "warnings_and_errors.log"  # 自定义文件名
```

## 🔍 技术细节

### 日志轮转机制

使用 Python 标准库的 `RotatingFileHandler`：

- **按大小轮转**：文件达到 `max_size` 时自动轮转
- **备份管理**：保留 `backup_count` 个备份文件
- **自动清理**：超过备份数量的旧文件自动删除

**轮转示例**：
```
error.log       (当前文件，10MB)
error.log.1     (第1个备份，10MB)
error.log.2     (第2个备份，10MB)
error.log.3     (第3个备份，10MB)
error.log.4     (第4个备份，10MB)
error.log.5     (第5个备份，10MB，最旧的会被删除)
```

### 日志格式

错误日志使用与主日志相同的格式：

```
%(asctime)s | %(name)-20s | %(levelname)-8s | %(module)s:%(funcName)s:%(lineno)d | %(message)s
```

**示例**：
```
2025-10-13 08:21:08,205 | dataflows | WARNING | data_source_manager:get_stock_data:461 | ⚠️ [数据来源: MongoDB] 未找到daily数据: 600519
```

### 性能影响

- **磁盘I/O**：增加一个文件处理器，但只写入WARNING及以上级别，影响很小
- **内存占用**：每个处理器占用约几KB内存，可忽略不计
- **CPU开销**：日志格式化和写入的开销很小，对性能影响微乎其微

## 📝 最佳实践

### 1. 监控错误日志

使用 `tail -f` 实时监控：

```bash
tail -f logs/error.log
```

### 2. 定期检查错误日志

建议每天检查一次 `error.log`，及时发现和解决问题。

### 3. 错误日志告警

可以使用监控工具（如 Prometheus + Alertmanager）监控 `error.log` 的增长速度：

```bash
# 统计最近1小时的错误数量
tail -n 1000 logs/error.log | grep "$(date -d '1 hour ago' '+%Y-%m-%d %H')" | wc -l
```

### 4. 错误日志分析

使用工具分析错误类型和频率：

```bash
# 统计各类错误的数量
grep "ERROR" logs/error.log | awk -F'|' '{print $5}' | sort | uniq -c | sort -rn

# 统计各模块的错误数量
grep "ERROR" logs/error.log | awk -F'|' '{print $2}' | sort | uniq -c | sort -rn
```

## 🎉 总结

### 修改内容

1. ✅ 添加 `_add_error_handler()` 方法
2. ✅ 更新 `_setup_logging()` 调用错误处理器
3. ✅ 更新默认配置支持错误处理器
4. ✅ 更新 `config/logging.toml` 配置文件

### 修改效果

- ✅ 错误和警告日志单独输出到 `error.log`
- ✅ 保持 `tradingagents.log` 记录所有日志
- ✅ 支持配置文件自定义
- ✅ 支持日志轮转和备份
- ✅ 向后兼容，不影响现有功能

### 后续建议

1. 考虑添加日志监控和告警系统
2. 考虑添加日志分析和可视化工具
3. 考虑添加日志归档和清理策略
4. 考虑添加结构化日志（JSON格式）支持更好的分析

---

**修复日期**：2025-10-13

**相关文档**：
- `docs/trading_date_range_fix.md` - 交易日期范围修复
- `docs/estimated_total_time_fix.md` - 预估总时长修复
- `docs/research_depth_mapping_fix.md` - 研究深度映射修复

