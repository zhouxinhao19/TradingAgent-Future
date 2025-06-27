#!/usr/bin/env python3
"""
测试CLI修复是否成功
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from tradingagents.graph.trading_graph import TradingAgentsGraph

# 加载环境变量
load_dotenv()

def test_dashscope_integration():
    """测试阿里百炼集成是否正常"""
    
    print("🧪 测试阿里百炼集成修复")
    print("=" * 50)
    
    # 模拟CLI传递的配置
    config = {
        'project_dir': str(project_root / 'tradingagents'),
        'results_dir': './results',
        'data_dir': '/Users/yluo/Documents/Code/ScAI/FR1-data',
        'data_cache_dir': str(project_root / 'tradingagents/dataflows/data_cache'),
        'llm_provider': 'dashscope',  # 修复后应该正确识别
        'deep_think_llm': 'qwen-plus',
        'quick_think_llm': 'qwen-plus',
        'backend_url': 'https://dashscope.aliyuncs.com/api/v1',
        'max_debate_rounds': 3,
        'max_risk_discuss_rounds': 3,
        'memory_enabled': False
    }
    
    try:
        print("🔧 正在初始化TradingAgentsGraph...")
        graph = TradingAgentsGraph(['market'], config=config, debug=True)
        print("✅ TradingAgentsGraph初始化成功!")
        
        print("🤖 检查LLM实例...")
        print(f"   深度思考LLM: {type(graph.deep_thinking_llm).__name__}")
        print(f"   快速思考LLM: {type(graph.quick_thinking_llm).__name__}")
        
        # 测试简单的LLM调用
        print("📝 测试LLM调用...")
        from langchain_core.messages import HumanMessage
        
        response = graph.quick_thinking_llm.invoke([
            HumanMessage(content="请简单介绍一下股票投资的基本概念，用中文回答，不超过100字。")
        ])
        
        print("✅ LLM调用成功!")
        print(f"   响应内容: {response.content[:50]}...")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_different_provider_names():
    """测试不同的提供商名称是否都能正确识别"""

    print("\n🔍 测试不同提供商名称识别")
    print("=" * 50)

    test_cases = [
        "阿里百炼 (dashscope)",
        "dashscope",
        "DashScope",
        "阿里百炼",
        "alibaba"
    ]

    base_config = {
        'project_dir': str(project_root / 'tradingagents'),
        'results_dir': './results',
        'data_dir': '/Users/yluo/Documents/Code/ScAI/FR1-data',
        'data_cache_dir': str(project_root / 'tradingagents/dataflows/data_cache'),
        'deep_think_llm': 'qwen-plus',
        'quick_think_llm': 'qwen-plus',
        'backend_url': 'https://dashscope.aliyuncs.com/api/v1',
        'max_debate_rounds': 1,  # 减少测试时间
        'max_risk_discuss_rounds': 1,
        'memory_enabled': False  # 禁用内存系统避免冲突
    }
    
    success_count = 0
    
    for provider_name in test_cases:
        try:
            config = base_config.copy()
            config['llm_provider'] = provider_name
            
            print(f"🧪 测试提供商名称: '{provider_name}'")
            graph = TradingAgentsGraph(['market'], config=config, debug=False)
            print(f"   ✅ 成功识别")
            success_count += 1
            
        except Exception as e:
            print(f"   ❌ 识别失败: {e}")
    
    print(f"\n📊 测试结果: {success_count}/{len(test_cases)} 成功")
    return success_count == len(test_cases)

def main():
    """主测试函数"""
    
    print("🚀 TradingAgents-CN CLI修复验证")
    print("=" * 60)
    
    # 检查API密钥
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        print("❌ 请设置 DASHSCOPE_API_KEY 环境变量")
        return
    
    print(f"✅ API密钥已配置: {api_key[:12]}...")
    
    # 运行测试
    test1_result = test_dashscope_integration()
    test2_result = test_different_provider_names()
    
    print("\n" + "=" * 60)
    print("📋 测试总结:")
    print(f"   基础集成测试: {'✅ 通过' if test1_result else '❌ 失败'}")
    print(f"   提供商名称测试: {'✅ 通过' if test2_result else '❌ 失败'}")
    
    if test1_result and test2_result:
        print("\n🎉 所有测试通过！CLI修复成功")
        print("💡 现在可以正常使用: python -m cli.main analyze")
    else:
        print("\n⚠️ 部分测试失败，需要进一步检查")

if __name__ == "__main__":
    main()
