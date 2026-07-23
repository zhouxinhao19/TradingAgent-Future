# LLM 适配器测试指南与验证清单

## 📋 概述

本指南提供了完整的 LLM 适配器测试流程，确保新集成的大模型能够稳定运行并正确集成到 TradingAgents 系统中。

## 🧪 测试类型

### 1. 基础连接测试
验证适配器能够成功连接到 LLM 提供商的 API。

### 2. 工具调用测试
验证适配器能够正确执行 function calling，这是 TradingAgents 分析功能的核心。

### 3. Web 界面集成测试
验证新的 LLM 选项在前端界面中正确显示和工作。

### 4. 端到端分析测试
验证完整的期货分析流程能够使用新的 LLM 正常运行。

## 🔧 测试环境准备

### 第一步：设置 API 密钥

1. **复制环境变量模板**
   ```bash
   cp .env.example .env
   ```

2. **添加您的 API 密钥**
   ```bash
   # 在 .env 文件中添加
   YOUR_PROVIDER_API_KEY=your_actual_api_key_here
   ```

3. **验证环境变量加载**
   ```python
   import os
   from dotenv import load_dotenv
   
   load_dotenv()
   api_key = os.getenv("YOUR_PROVIDER_API_KEY")
   print(f"API Key 是否配置: {'是' if api_key else '否'}")
   ```

### 第二步：安装测试依赖

```bash
# 确保项目已安装
pip install -e .

# 安装测试相关依赖
pip install pytest pytest-asyncio
```

## 📝 测试脚本模板

### 基础连接测试

创建 `tests/test_your_provider_adapter.py`：

### 千帆模型专项测试（OpenAI 兼容模式）

创建 `tests/test_qianfan_adapter.py`：

```python
import os
from tradingagents.llm_adapters.openai_compatible_base import create_openai_compatible_llm
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage

def test_qianfan_api_key_config():
    """测试千帆 API Key 配置"""
    api_key = os.environ.get("QIANFAN_API_KEY")
    
    if not api_key:
        print("❌ 缺少千帆API密钥配置: QIANFAN_API_KEY")
        return False
    
    if not api_key.startswith("bce-v3/"):
        print("⚠️ 千帆API密钥格式可能不正确，建议使用 bce-v3/ 开头的格式")
        return False
    
    print(f"✅ 千帆API密钥配置正确 (格式: {api_key[:10]}...)")
    return True

def test_qianfan_basic_chat():
    """测试千帆基础对话（OpenAI 兼容模式）"""
    try:
        llm = create_openai_compatible_llm(
            provider="qianfan",
            model="ernie-3.5-8k",
            temperature=0.1,
            max_tokens=500
        )
        
        response = llm.invoke([
            HumanMessage(content="你好，请简单介绍一下你自己")
        ])
        
        print(f"✅ 千帆对话成功: {response.content[:100]}...")
        return True
    except Exception as e:
        print(f"❌ 千帆对话失败: {e}")
        return False

def test_qianfan_function_calling():
    """测试千帆工具调用功能"""
    try:
        @tool
        def get_stock_price(symbol: str) -> str:
            """获取期货价格
            
            Args:
                symbol: 品种代码，如 AAPL
            
            Returns:
                期货价格信息
            """
            return f"期货品种 {symbol} 的当前价格是 $150.00"
        
        llm = create_openai_compatible_llm(
            provider="qianfan",
            model="ernie-4.0-turbo-8k",
            temperature=0.1
        )
        
        llm_with_tools = llm.bind_tools([get_stock_price])
        
        response = llm_with_tools.invoke([
            HumanMessage(content="请帮我查询 AAPL 期货品种的价格")
        ])
        
        print(f"✅ 千帆工具调用成功: {response.content[:200]}...")
        
        # 检查是否包含工具调用结果
        if "150.00" in response.content or "AAPL" in response.content:
            print("✅ 工具调用结果正确返回")
            return True
        else:
            print("⚠️ 工具调用可能未正确执行")
            return False
            
    except Exception as e:
        print(f"❌ 千帆工具调用失败: {e}")
        return False

def test_qianfan_chinese_analysis():
    """测试千帆中文金融分析能力"""
    try:
        llm = create_openai_compatible_llm(
            provider="qianfan",
            model="ernie-3.5-8k",
            temperature=0.1
        )
        
        test_prompt = """请简要分析苹果公司（AAPL）的投资价值，包括：
        1. 公司基本面
        2. 技术面趋势
        3. 投资建议
        
        请用中文回答，字数控制在200字以内。"""
        
        response = llm.invoke([HumanMessage(content=test_prompt)])
        
        # 检查响应是否包含中文和关键分析要素
        content = response.content
        if (any('\u4e00' <= char <= '\u9fff' for char in content) and 
            ("苹果" in content or "AAPL" in content) and
            len(content) > 50):
            print("✅ 千帆中文金融分析能力正常")
            print(f"📄 分析内容预览: {content[:150]}...")
            return True
        else:
            print("⚠️ 千帆中文分析响应可能有问题")
            print(f"📄 实际响应: {content}")
            return False
            
    except Exception as e:
        print(f"❌ 千帆中文分析测试失败: {e}")
        return False

def test_qianfan_model_variants():
    """测试千帆不同模型变体"""
    models_to_test = ["ernie-3.5-8k", "ernie-4.0-turbo-8k", "ERNIE-Speed-8K"]
    
    for model in models_to_test:
        try:
            llm = create_openai_compatible_llm(
                provider="qianfan",
                model=model,
                temperature=0.1,
                max_tokens=100
            )
            
            response = llm.invoke([
                HumanMessage(content="简单说明一下你的能力特点")
            ])
            
            print(f"✅ 模型 {model} 连接成功: {response.content[:50]}...")
        except Exception as e:
            print(f"❌ 模型 {model} 测试失败: {e}")

if __name__ == "__main__":
    print("=== 千帆模型专项测试（OpenAI 兼容模式）===")
    print()
    
    # 基础配置测试
    test_qianfan_api_key_config()
    print()
    
    # 基础对话测试
    test_qianfan_basic_chat()
    print()
    
    # 工具调用测试
    test_qianfan_function_calling()
    print()
    
    # 中文分析测试
    test_qianfan_chinese_analysis()
    print()
    
    # 模型变体测试
    print("--- 测试不同模型变体 ---")
    test_qianfan_model_variants()
```

```python
#!/usr/bin/env python3
"""
{Provider} 适配器测试脚本
测试基础连接、工具调用和集成功能
"""

import os
import sys
import pytest
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage

# 加载环境变量
load_dotenv()

def test_api_key_configuration():
    """测试 API 密钥配置"""
    print("\n🔑 测试 API 密钥配置")
    print("=" * 50)
    
    api_key = os.getenv("YOUR_PROVIDER_API_KEY")
    assert api_key is not None, "YOUR_PROVIDER_API_KEY 环境变量未设置"
    assert len(api_key) > 10, "API 密钥长度不足，请检查是否正确"
    
    print(f"✅ API 密钥已配置 (长度: {len(api_key)})")
    return True

def test_adapter_import():
    """测试适配器导入"""
    print("\n📦 测试适配器导入")
    print("=" * 50)
    
    try:
        from tradingagents.llm_adapters.your_provider_adapter import ChatYourProvider
        print("✅ 适配器导入成功")
        return True
    except ImportError as e:
        print(f"❌ 适配器导入失败: {e}")
        pytest.fail(f"适配器导入失败: {e}")

def test_basic_connection():
    """测试基础连接"""
    print("\n🔗 测试基础连接")
    print("=" * 50)
    
    try:
        from tradingagents.llm_adapters.your_provider_adapter import ChatYourProvider
        
        # 创建适配器实例
        llm = ChatYourProvider(
            model="your-default-model",
            temperature=0.1,
            max_tokens=100
        )
        
        # 发送简单测试消息
        response = llm.invoke([
            HumanMessage(content="请回复'连接测试成功'")
        ])
        
        print(f"✅ 连接成功")
        print(f"📄 回复内容: {response.content[:100]}...")
        return True
        
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        pytest.fail(f"基础连接测试失败: {e}")

def test_function_calling():
    """测试工具调用功能"""
    print("\n🛠️ 测试工具调用功能")
    print("=" * 50)
    
    try:
        from tradingagents.llm_adapters.your_provider_adapter import ChatYourProvider
        
        # 定义测试工具
        @tool
        def get_stock_price(symbol: str) -> str:
            """获取期货价格
            
            Args:
                symbol: 品种代码，如 AAPL
            
            Returns:
                期货价格信息
            """
            return f"期货品种 {symbol} 的当前价格是 $150.00"
        
        # 创建带工具的适配器
        llm = ChatYourProvider(
            model="your-default-model",
            temperature=0.1,
            max_tokens=500
        )
        llm_with_tools = llm.bind_tools([get_stock_price])
        
        # 测试工具调用
        response = llm_with_tools.invoke([
            HumanMessage(content="请帮我查询 AAPL 期货品种的价格")
        ])
        
        print(f"✅ 工具调用成功")
        print(f"📄 回复内容: {response.content[:200]}...")
        
        # 检查是否包含工具调用
        if "150.00" in response.content or "AAPL" in response.content:
            print("✅ 工具调用结果正确返回")
            return True
        else:
            print("⚠️ 工具调用可能未正确执行")
            return False
            
    except Exception as e:
        print(f"❌ 工具调用失败: {e}")
        pytest.fail(f"工具调用测试失败: {e}")

def test_factory_function():
    """测试工厂函数"""
    print("\n🏭 测试工厂函数")
    print("=" * 50)
    
    try:
        from tradingagents.llm_adapters.openai_compatible_base import create_openai_compatible_llm
        
        # 使用工厂函数创建实例
        llm = create_openai_compatible_llm(
            provider="your_provider",
            model="your-default-model",
            temperature=0.1,
            max_tokens=100
        )
        
        # 测试简单调用
        response = llm.invoke([
            HumanMessage(content="测试工厂函数")
        ])
        
        print(f"✅ 工厂函数测试成功")
        print(f"📄 回复内容: {response.content[:100]}...")
        return True
        
    except Exception as e:
        print(f"❌ 工厂函数测试失败: {e}")
        pytest.fail(f"工厂函数测试失败: {e}")

def test_trading_graph_integration():
    """测试与 TradingGraph 的集成"""
    print("\n🔧 测试与 TradingGraph 的集成")
    print("=" * 50)
    
    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        
        # 创建配置
        config = {
            "llm_provider": "your_provider",
            "deep_think_llm": "your-default-model",
            "quick_think_llm": "your-default-model",
            "max_debate_rounds": 1,
            "online_tools": False,  # 关闭在线工具以加快测试
            "selected_analysts": ["fundamentals_analyst"]
        }
        
        print("🔄 创建 TradingGraph...")
        graph = TradingAgentsGraph(config)
        
        print("✅ TradingGraph 创建成功")
        print(f"   Deep thinking LLM: {type(graph.deep_thinking_llm).__name__}")
        print(f"   Quick thinking LLM: {type(graph.quick_thinking_llm).__name__}")
        
        return True
        
    except Exception as e:
        print(f"❌ TradingGraph 集成测试失败: {e}")
        pytest.fail(f"TradingGraph 集成测试失败: {e}")

def run_all_tests():
    """运行所有测试"""
    print("🚀 开始 {Provider} 适配器全套测试")
    print("=" * 60)
    
    tests = [
        test_api_key_configuration,
        test_adapter_import,
        test_basic_connection,
        test_function_calling,
        test_factory_function,
        test_trading_graph_integration
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except (AssertionError, Exception) as e:
            print(f"❌ 测试失败: {test.__name__}")
            print(f"   错误信息: {e}")
            failed += 1
        print()
    
    print("📊 测试结果摘要")
    print("=" * 60)
    print(f"✅ 通过: {passed}")
    print(f"❌ 失败: {failed}")
    print(f"📈 成功率: {passed/(passed+failed)*100:.1f}%")
    
    if failed == 0:
        print("\n🎉 所有测试通过！适配器可以正常使用")
    else:
        print(f"\n⚠️ 有 {failed} 个测试失败，请检查配置")

if __name__ == "__main__":
    run_all_tests()
```

## 🌐 Web 界面测试

### 手动测试步骤

1. **启动 Web 应用**
   ```bash
   python start_web.py
   ```

2. **检查模型选择器**
   - 在左侧边栏找到"LLM提供商"下拉菜单
   - 确认您的提供商出现在选项中
   - 选择您的提供商

3. **检查模型选项**
   - 选择提供商后，确认模型选择器显示正确的模型列表
   - 尝试选择不同的模型

4. **进行简单分析**
   - 输入品种代码（如 AAPL）
   - 选择一个分析师（建议选择"基本面分析师"）
   - 点击"开始分析"
   - 观察分析是否正常进行

### 自动化 Web 测试

创建 `tests/test_web_integration.py`：

```python
import streamlit as st
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_sidebar_integration():
    """测试侧边栏集成"""
    print("\n🔧 测试 Web 界面集成")
    print("=" * 50)
    
    try:
        # 模拟 Streamlit session state
        with patch('streamlit.session_state') as mock_state:
            mock_state.llm_provider = "your_provider"
            mock_state.llm_model = "your-default-model"
            
            # 导入侧边栏组件
            from web.components.sidebar import create_sidebar
            
            # 模拟 Streamlit 组件
            with patch('streamlit.selectbox') as mock_selectbox:
                mock_selectbox.return_value = "your_provider"
                
                # 测试侧边栏创建
                config = create_sidebar()
                
                print("✅ 侧边栏集成测试通过")
                return True
                
    except Exception as e:
        print(f"❌ Web 界面集成测试失败: {e}")
        return False

if __name__ == "__main__":
    test_sidebar_integration()
```

## 📊 完整验证清单

### ✅ 开发阶段验证

- [ ] **代码质量**
  - [ ] 适配器类继承自 `OpenAICompatibleBase`
  - [ ] 正确设置 `provider_name`、`api_key_env_var`、`base_url`
  - [ ] 模型配置添加到 `OPENAI_COMPATIBLE_PROVIDERS`
  - [ ] 适配器导出添加到 `__init__.py`

- [ ] **基础功能**
  - [ ] API 密钥环境变量正确配置
  - [ ] 基础连接测试通过
  - [ ] 简单文本生成正常工作
  - [ ] 错误处理机制有效

- [ ] **工具调用功能**
  - [ ] Function calling 正常工作
  - [ ] 工具参数正确解析
  - [ ] 工具结果正确返回
  - [ ] 复杂工具调用场景稳定

### ✅ 集成阶段验证

- [ ] **前端集成**
  - [ ] 提供商出现在下拉菜单中
  - [ ] 模型选择器正常工作
  - [ ] UI 格式化显示正确
  - [ ] 会话状态正确保存

- [ ] **后端集成**
  - [ ] 工厂函数正确创建实例
  - [ ] TradingGraph 正确使用适配器
  - [ ] 配置参数正确传递
  - [ ] 错误处理正确集成

- [ ] **系统集成**
  - [ ] 环境变量检查脚本支持新提供商
  - [ ] 日志记录正常工作
  - [ ] Token 使用统计正确
  - [ ] 内存管理正常

### ✅ 端到端验证

- [ ] **基本分析流程**
  - [ ] 能够进行简单期货分析
  - [ ] 分析师选择正常工作
  - [ ] 工具调用在分析中正常执行
  - [ ] 分析结果格式正确

- [ ] **高级功能**
  - [ ] 多轮对话正常工作
  - [ ] 记忆功能正常（如果启用）
  - [ ] 并发请求处理稳定
  - [ ] 长时间运行稳定

- [ ] **错误处理**
  - [ ] API 错误正确处理
  - [ ] 网络错误优雅降级
  - [ ] 配置错误清晰提示
  - [ ] 重试机制正常工作

### ✅ 性能与稳定性验证

- [ ] **性能指标**
  - [ ] 响应时间合理（< 30秒）
  - [ ] 内存使用稳定
  - [ ] CPU 使用率正常
  - [ ] 无内存泄漏

- [ ] **稳定性测试**
  - [ ] 连续运行 30 分钟无错误
  - [ ] 处理 50+ 请求无问题
  - [ ] 网络中断后能恢复
  - [ ] 并发请求处理正确

## 🐛 常见测试问题与解决方案

### 问题 1: API 密钥错误

**症状**: `AuthenticationError` 或 `InvalidAPIKey`

**解决方案**:
```bash
# 检查环境变量
echo $YOUR_PROVIDER_API_KEY

# 重新加载环境变量
source .env

# 验证 API 密钥格式
python -c "import os; print(f'API Key: {os.getenv(\"YOUR_PROVIDER_API_KEY\")[:10]}...')"
```

### 问题 2: 工具调用失败

**症状**: `ToolCallError` 或工具未被调用

**解决方案**:
```python
# 检查模型是否支持 function calling
from tradingagents.llm_adapters.openai_compatible_base import OPENAI_COMPATIBLE_PROVIDERS

provider_config = OPENAI_COMPATIBLE_PROVIDERS["your_provider"]
models = provider_config["models"]
print(f"模型支持 function calling: {models}")
```

### 问题 3: 前端集成失败

**症状**: 提供商不出现在下拉菜单中

**解决方案**:
```python
# 检查 sidebar.py 配置
# 确保在 options 列表中包含您的提供商
# 确保在 format_func 字典中包含格式化映射
```

### 问题 4: 导入错误

**症状**: `ModuleNotFoundError` 或 `ImportError`

**解决方案**:
```bash
# 确保项目已安装
pip install -e .

# 检查 __init__.py 导出
python -c "from tradingagents.llm_adapters import ChatYourProvider; print('导入成功')"
```

### 问题 5: 千帆模型认证失败

**症状**: `AuthenticationError` 或 `invalid_client`

**解决方案**:
```bash
# 检查千帆API密钥配置（仅需一个密钥）
echo $QIANFAN_API_KEY

# 验证密钥格式（应该以 bce-v3/ 开头）
python -c "import os; print(f'API Key格式: {os.getenv("QIANFAN_API_KEY", "未设置")[:10]}...')"

# 建议：使用 OpenAI 兼容路径进行连通性验证（无需 AK/SK 获取 Token）
python - << 'PY'
from tradingagents.llm_adapters.openai_compatible_base import create_openai_compatible_llm
llm = create_openai_compatible_llm(provider="qianfan", model="ernie-3.5-8k")
print(llm.invoke("ping").content)
PY
```

### 问题 6: 千帆模型中文乱码

**症状**: 返回内容包含乱码或编码错误

**解决方案**:
```python
# 检查系统编码设置
import locale
import sys
print(f"系统编码: {locale.getpreferredencoding()}")
print(f"Python编码: {sys.getdefaultencoding()}")

# 强制设置UTF-8编码
import os
os.environ['PYTHONIOENCODING'] = 'utf-8'

# 测试中文处理
test_text = "测试中文编码"
print(f"原文: {test_text}")
print(f"编码: {test_text.encode('utf-8')}")
print(f"解码: {test_text.encode('utf-8').decode('utf-8')}")
```

### 问题 7: 千帆调用失败（OpenAI 兼容路径）

**症状**: `AuthenticationError`、`RateLimitError` 或 `ModelNotFound`

**解决方案**:
```python
# 1) 检查 API Key 是否正确设置
action = "已设置" if os.getenv("QIANFAN_API_KEY") else "未设置"
print(f"QIANFAN_API_KEY: {action}")

# 2) 确认模型名称是否在映射列表
from tradingagents.llm_adapters.openai_compatible_base import OPENAI_COMPATIBLE_PROVIDERS
print(OPENAI_COMPATIBLE_PROVIDERS["qianfan"]["models"].keys())

# 3) 低并发/延时重试
from tradingagents.llm_adapters.openai_compatible_base import create_openai_compatible_llm
llm = create_openai_compatible_llm(provider="qianfan", model="ernie-3.5-8k", request_timeout=60)
print(llm.invoke("hello").content)
```

## 📝 测试报告模板

完成测试后，创建测试报告：

```markdown
# {Provider} 适配器测试报告

## 基本信息
- **提供商**: {Provider}
- **适配器类**: Chat{Provider}
- **测试日期**: {Date}
- **测试者**: {Name}

## 测试结果摘要
- ✅ 基础连接: 通过
- ✅ 工具调用: 通过  
- ✅ Web 集成: 通过
- ✅ 端到端: 通过

## 性能指标
- 平均响应时间: {X}秒
- 工具调用成功率: {X}%
- 内存使用: {X}MB
- 稳定性测试: 通过

## 已知问题
- 无重大问题

## 建议
- 适配器可以正常使用
- 建议合并到主分支
```

## 🎯 最佳实践

1. **测试驱动开发**: 先写测试，再实现功能
2. **小步快跑**: 每完成一个功能就进行测试
3. **自动化测试**: 使用脚本自动运行所有测试
4. **文档同步**: 测试通过后及时更新文档
5. **版本控制**: 每次测试创建 git 提交记录

## 🔄 持续验证

集成完成后，建议定期进行以下验证：

- **每周**: 运行基础连接测试
- **每月**: 运行完整测试套件
- **版本更新**: 重新运行所有测试
- **API 变更**: 重新验证工具调用功能

---

通过遵循这个完整的测试指南，您可以确保新集成的 LLM 适配器质量可靠，功能完整，能够稳定地为 TradingAgents 用户提供服务。