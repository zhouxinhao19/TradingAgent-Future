#!/usr/bin/env python3
"""
直接测试DeepSeek API调用，不使用langchain
"""

import os
import openai
from openai import OpenAI
from dotenv import load_dotenv

# 加载.env文件
load_dotenv()

def test_deepseek_direct():
    """直接使用OpenAI库调用DeepSeek API"""
    
    # 获取API密钥
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("❌ 未找到DEEPSEEK_API_KEY环境变量")
        return False
    
    try:
        # 创建OpenAI客户端，指向DeepSeek API
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )
        
        print("🤖 正在调用DeepSeek API...")
        
        # 发送请求
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "user", "content": "请简单介绍一下股票投资的基本概念，用中文回答，控制在100字以内。"}
            ],
            temperature=0.1,
            max_tokens=200
        )
        
        print(f"✅ DeepSeek响应: {response.choices[0].message.content}")
        return True
        
    except Exception as e:
        print(f"❌ DeepSeek API调用失败: {e}")
        print(f"错误类型: {type(e).__name__}")
        import traceback
        print(f"详细错误: {traceback.format_exc()}")
        return False

if __name__ == "__main__":
    print("🧪 测试直接调用DeepSeek API")
    print("=" * 50)
    
    success = test_deepseek_direct()
    
    if success:
        print("\n🎉 DeepSeek API调用成功！")
        print("问题可能出在langchain_openai的兼容性上")
    else:
        print("\n❌ DeepSeek API调用失败")
        print("请检查API密钥和网络连接")