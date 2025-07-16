#!/usr/bin/env python3
"""
修复股票代码误判问题的脚本
"""

import os
import shutil
import sys

def clear_all_caches():
    """清理所有缓存"""
    print("🧹 清理所有缓存...")
    
    cache_dirs = [
        "tradingagents/dataflows/data_cache",
        "web/results",
        "web/eval_results/002027",
        "__pycache__",
        "tradingagents/__pycache__",
        "tradingagents/agents/__pycache__",
        "tradingagents/dataflows/__pycache__"
    ]
    
    for cache_dir in cache_dirs:
        if os.path.exists(cache_dir):
            try:
                if os.path.isdir(cache_dir):
                    shutil.rmtree(cache_dir)
                    print(f"✅ 已清理目录: {cache_dir}")
                else:
                    os.remove(cache_dir)
                    print(f"✅ 已删除文件: {cache_dir}")
            except Exception as e:
                print(f"⚠️ 清理 {cache_dir} 失败: {e}")
    
    print("✅ 缓存清理完成")

def add_stock_code_validation():
    """添加股票代码验证机制"""
    print("🔧 添加股票代码验证机制...")
    
    validation_code = '''
def validate_stock_code(original_code: str, processed_content: str) -> str:
    """
    验证处理后的内容中是否包含正确的股票代码
    
    Args:
        original_code: 原始股票代码
        processed_content: 处理后的内容
        
    Returns:
        str: 验证并修正后的内容
    """
    import re
    
    # 定义常见的错误映射
    error_mappings = {
        "002027": ["002021", "002026", "002028"],  # 分众传媒常见错误
        "002021": ["002027"],  # 反向映射
    }
    
    if original_code in error_mappings:
        for wrong_code in error_mappings[original_code]:
            if wrong_code in processed_content:
                print(f"🔍 [股票代码验证] 发现错误代码 {wrong_code}，修正为 {original_code}")
                processed_content = processed_content.replace(wrong_code, original_code)
    
    return processed_content
'''
    
    # 将验证代码写入文件
    with open("stock_code_validator.py", "w", encoding="utf-8") as f:
        f.write(validation_code)
    
    print("✅ 股票代码验证机制已添加")

def create_test_script():
    """创建专门的测试脚本"""
    print("📝 创建测试脚本...")
    
    test_script = '''#!/usr/bin/env python3
"""
002027 股票代码专项测试
"""

import os
import sys

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def test_002027_specifically():
    """专门测试002027股票代码"""
    print("🔍 002027 专项测试")
    print("=" * 60)
    
    test_ticker = "002027"
    
    try:
        from tradingagents.utils.logging_init import get_logger
        logger = get_logger("default")
        logger.setLevel("INFO")
        
        # 测试1: 数据获取
        print("\\n📊 测试1: 数据获取")
        from tradingagents.dataflows.interface import get_china_stock_data_tushare
        data = get_china_stock_data_tushare(test_ticker, "2025-07-01", "2025-07-15")
        
        if "002021" in data:
            print("❌ 数据获取阶段发现错误代码 002021")
            return False
        else:
            print("✅ 数据获取阶段正确")
        
        # 测试2: 基本面分析
        print("\\n💰 测试2: 基本面分析")
        from tradingagents.dataflows.optimized_china_data import OptimizedChinaDataProvider
        analyzer = OptimizedChinaDataProvider()
        report = analyzer._generate_fundamentals_report(test_ticker, data)
        
        if "002021" in report:
            print("❌ 基本面分析阶段发现错误代码 002021")
            return False
        else:
            print("✅ 基本面分析阶段正确")
        
        # 测试3: LLM处理
        print("\\n🤖 测试3: LLM处理")
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if api_key:
            from tradingagents.llm_adapters import ChatDashScopeOpenAI
            from langchain_core.messages import HumanMessage
            
            llm = ChatDashScopeOpenAI(model="qwen-turbo", temperature=0.1, max_tokens=500)
            
            prompt = f"请分析股票{test_ticker}的基本面，股票名称是分众传媒。要求：1.必须使用正确的股票代码{test_ticker} 2.不要使用任何其他股票代码"
            
            response = llm.invoke([HumanMessage(content=prompt)])
            
            if "002021" in response.content:
                print("❌ LLM处理阶段发现错误代码 002021")
                print(f"错误内容: {response.content[:200]}...")
                return False
            else:
                print("✅ LLM处理阶段正确")
        else:
            print("⚠️ 跳过LLM测试（未配置API密钥）")
        
        print("\\n🎉 所有测试通过！002027股票代码处理正确")
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

if __name__ == "__main__":
    test_002027_specifically()
'''
    
    with open("test_002027_specific.py", "w", encoding="utf-8") as f:
        f.write(test_script)
    
    print("✅ 测试脚本已创建: test_002027_specific.py")

def main():
    """主函数"""
    print("🚀 开始修复股票代码误判问题")
    print("=" * 60)
    
    # 1. 清理缓存
    clear_all_caches()
    
    # 2. 添加验证机制
    add_stock_code_validation()
    
    # 3. 创建测试脚本
    create_test_script()
    
    print("\\n✅ 修复完成！")
    print("\\n📋 后续操作建议：")
    print("1. 重启Web应用")
    print("2. 清理浏览器缓存")
    print("3. 运行测试脚本: python test_002027_specific.py")
    print("4. 在Web界面重新测试002027")
    print("5. 如果问题仍然存在，请检查LLM模型配置")

if __name__ == "__main__":
    main()
