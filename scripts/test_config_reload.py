#!/usr/bin/env python3
"""
测试配置重载功能

这个脚本会：
1. 调用配置重载 API
2. 检查响应
3. 显示重载结果
"""

import requests
import json
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# API 配置
BASE_URL = "http://localhost:8001"
API_URL = f"{BASE_URL}/api/config/reload"

# 测试用户的 token（需要先登录获取）
# 这里使用一个测试 token，实际使用时需要替换
TOKEN = None


def get_test_token():
    """获取测试用户的 token"""
    login_url = f"{BASE_URL}/api/auth/login"
    
    # 尝试使用测试用户登录
    test_users = [
        {"username": "admin", "password": "CHANGE_ME_ADMIN_PASSWORD"},
        {"username": "test", "password": "test123"},
    ]
    
    for user in test_users:
        try:
            response = requests.post(login_url, json=user)
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    token = data.get("data", {}).get("access_token")
                    print(f"✅ 使用用户 '{user['username']}' 登录成功")
                    return token
        except Exception as e:
            continue
    
    print("❌ 无法获取测试 token，请先创建测试用户或手动设置 TOKEN")
    return None


def test_config_reload():
    """测试配置重载"""
    global TOKEN
    
    print("=" * 60)
    print("🧪 测试配置重载功能")
    print("=" * 60)
    print()
    
    # 获取 token
    if not TOKEN:
        TOKEN = get_test_token()
        if not TOKEN:
            print("❌ 无法获取 token，测试终止")
            return False
    
    print(f"📡 调用 API: POST {API_URL}")
    print()
    
    # 调用配置重载 API
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(API_URL, headers=headers)
        
        print(f"📊 响应状态码: {response.status_code}")
        print()
        
        if response.status_code == 200:
            data = response.json()
            print("📦 响应数据:")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            print()
            
            if data.get("success"):
                print("✅ 配置重载成功！")
                print()
                
                # 显示重载时间
                reloaded_at = data.get("data", {}).get("reloaded_at")
                if reloaded_at:
                    print(f"⏰ 重载时间: {reloaded_at}")
                
                return True
            else:
                print(f"❌ 配置重载失败: {data.get('message')}")
                return False
        else:
            print(f"❌ API 调用失败: {response.status_code}")
            print(f"响应内容: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ 发生错误: {e}")
        return False


def check_backend_logs():
    """提示检查后端日志"""
    print()
    print("=" * 60)
    print("📋 请检查后端日志")
    print("=" * 60)
    print()
    print("在后端日志中查找以下内容：")
    print()
    print("1. 配置重载开始:")
    print("   🔄 重新加载配置桥接...")
    print()
    print("2. 清除旧配置:")
    print("   清除环境变量: TRADINGAGENTS_DEFAULT_MODEL")
    print("   清除环境变量: DEEPSEEK_API_KEY")
    print("   ...")
    print()
    print("3. 桥接新配置:")
    print("   🔧 开始桥接配置到环境变量...")
    print("   ✓ 桥接默认模型: xxx")
    print("   ✓ 桥接快速分析模型: xxx")
    print("   ...")
    print()
    print("4. 完成:")
    print("   ✅ 配置桥接完成，共桥接 X 项配置")
    print()


def main():
    """主函数"""
    print()
    print("🚀 配置重载测试脚本")
    print()
    
    # 测试配置重载
    success = test_config_reload()
    
    # 提示检查日志
    if success:
        check_backend_logs()
    
    print()
    print("=" * 60)
    print("🎯 测试完成")
    print("=" * 60)
    print()
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())

