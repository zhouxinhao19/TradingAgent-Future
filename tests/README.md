# TradingAgents 测试程序

本目录包含了 TradingAgents 框架的各种测试程序，用于验证功能正确性和集成测试。

## 目录结构

```
tests/
├── README.md                    # 本文件
├── integration/                 # 集成测试
│   └── test_dashscope_integration.py  # 阿里百炼集成测试
├── unit/                        # 单元测试（待添加）
└── performance/                 # 性能测试（待添加）
```

## 集成测试

### 阿里百炼集成测试

`test_dashscope_integration.py` 是一个综合性的测试脚本，用于验证阿里百炼大模型的集成是否正常工作。

#### 测试内容

1. **模块导入测试**
   - 验证 `ChatDashScope` 适配器是否正确导入
   - 验证 `TradingAgentsGraph` 是否正常导入

2. **API密钥配置测试**
   - 检查 `DASHSCOPE_API_KEY` 环境变量
   - 检查 `FINNHUB_API_KEY` 环境变量

3. **阿里百炼连接测试**
   - 测试与阿里百炼API的连接
   - 验证简单的文本生成功能

4. **LangChain适配器测试**
   - 测试 `ChatDashScope` 与LangChain的兼容性
   - 验证消息格式转换

5. **TradingGraph配置测试**
   - 测试TradingAgentsGraph的初始化
   - 验证阿里百炼模型配置

#### 运行测试

```bash
# 确保已配置API密钥
set DASHSCOPE_API_KEY=your_api_key
set FINNHUB_API_KEY=your_api_key

# 运行集成测试
python tests/integration/test_dashscope_integration.py
```

#### 测试结果解读

- **5/5 通过**：所有功能正常，可以使用完整的TradingAgents功能
- **4/5 通过**：基本功能正常，可能需要检查配置
- **3/5 或更少**：存在问题，需要排查

### 测试输出示例

```
🚀 阿里百炼大模型集成测试
==================================================

🔍 测试1: 检查模块导入...
✅ ChatDashScope 导入成功
✅ TradingAgentsGraph 导入成功

🔍 测试2: 检查API密钥配置...
✅ DASHSCOPE_API_KEY: sk-9905476...
✅ FINNHUB_API_KEY: d1el869r01...

🔍 测试3: 检查阿里百炼连接...
✅ 阿里百炼连接成功: 连接成功

🔍 测试4: 检查LangChain适配器...
✅ LangChain适配器工作正常: 适配器工作正常

🔍 测试5: 检查TradingGraph配置...
✅ TradingGraph 配置成功
   深度思考模型: qwen-plus
   快速思考模型: qwen-turbo

==================================================
📊 测试结果: 5/5 通过
🎉 所有测试通过！阿里百炼集成工作正常
```

## 运行所有测试

```bash
# 运行集成测试
python tests/integration/test_dashscope_integration.py

# 未来可能添加的测试
# python -m pytest tests/unit/
# python -m pytest tests/performance/
```

## 添加新测试

### 集成测试

在 `tests/integration/` 目录下添加新的测试文件：

```python
#!/usr/bin/env python3
"""
新功能集成测试
"""

def test_new_feature():
    """测试新功能"""
    # 测试代码
    pass

def main():
    """主测试函数"""
    tests = [test_new_feature]
    # 运行测试逻辑
    pass

if __name__ == "__main__":
    main()
```

### 单元测试

使用 pytest 框架：

```python
import pytest
from tradingagents.some_module import SomeClass

def test_some_function():
    """测试某个函数"""
    result = SomeClass().some_method()
    assert result == expected_value
```

## 持续集成

### GitHub Actions

项目可以配置GitHub Actions来自动运行测试：

```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v2
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: 3.9
    - name: Install dependencies
      run: pip install -r requirements.txt
    - name: Run tests
      run: python tests/integration/test_dashscope_integration.py
```

## 测试最佳实践

1. **测试隔离**：每个测试应该独立运行
2. **清晰命名**：测试函数名应该清楚描述测试内容
3. **错误处理**：测试应该能够处理各种错误情况
4. **文档化**：为复杂的测试添加详细注释
5. **快速反馈**：测试应该尽快给出结果

## 故障排除

### 测试失败的常见原因

1. **API密钥问题**
   - 检查环境变量是否正确设置
   - 确认API密钥有效且有足够额度

2. **网络连接问题**
   - 检查网络连接
   - 确认防火墙设置

3. **依赖包问题**
   - 确保所有依赖包已安装
   - 检查包版本兼容性

4. **环境问题**
   - 确认Python版本兼容
   - 检查虚拟环境配置

### 调试技巧

1. **启用详细输出**：在测试中添加更多打印信息
2. **单独运行测试**：逐个运行测试函数
3. **检查日志**：查看详细的错误日志
4. **使用调试器**：在IDE中设置断点调试

## 贡献

欢迎贡献新的测试用例！请确保：

1. 测试覆盖重要功能
2. 测试代码清晰易懂
3. 包含适当的错误处理
4. 提供测试文档

## 许可证

本项目遵循项目根目录的LICENSE文件。
