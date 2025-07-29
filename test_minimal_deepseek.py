#!/usr/bin/env python3
"""
最小化DeepSeek测试 - 完全独立，不依赖项目内部模块
"""

import os
from dotenv import load_dotenv
from openai import OpenAI

# 加载环境变量
load_dotenv()

def test_minimal_deepseek():
    """最小化DeepSeek测试"""
    try:
        # 获取API密钥
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            print("❌ 未找到DEEPSEEK_API_KEY环境变量")
            return False
        
        print(f"✅ 找到API密钥: {api_key[:10]}...")
        
        # 创建OpenAI客户端
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )
        
        print("✅ OpenAI客户端创建成功")
        
        # 测试简单调用
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "user", "content": "你好，请简单介绍一下你自己。"}
            ],
            temperature=0.1,
            max_tokens=200
        )
        
        result = response.choices[0].message.content
        print(f"✅ DeepSeek API调用成功")
        print(f"响应: {result}")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("开始最小化DeepSeek测试...")
    success = test_minimal_deepseek()
    if success:
        print("\n🎉 测试成功！DeepSeek API工作正常")
    else:
        print("\n💥 测试失败！请检查配置")