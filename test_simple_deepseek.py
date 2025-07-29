#!/usr/bin/env python3
"""
最简单的DeepSeek测试
"""

import sys
from pathlib import Path
from dotenv import load_dotenv

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 加载环境变量
load_dotenv()

try:
    from tradingagents.llm_adapters.deepseek_direct_adapter import create_deepseek_direct_adapter
    
    print("正在创建DeepSeek适配器...")
    adapter = create_deepseek_direct_adapter()
    
    print("正在测试DeepSeek调用...")
    response = adapter.invoke("你好，请简单介绍一下你自己。")
    
    print(f"DeepSeek响应: {response}")
    print("✅ DeepSeek测试成功！")
    
except Exception as e:
    print(f"❌ DeepSeek测试失败: {e}")
    import traceback
    traceback.print_exc()