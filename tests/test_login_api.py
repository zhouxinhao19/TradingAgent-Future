import asyncio
import aiohttp
import json

async def test_login_api():
    """测试登录API是否正常工作"""
    url = "http://localhost:8001/api/auth/login"
    
    # 测试数据
    login_data = {
        "username": "admin",
        "password": "CHANGE_ME_ADMIN_PASSWORD"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=login_data) as response:
                print(f"状态码: {response.status}")
                print(f"响应头: {dict(response.headers)}")
                
                if response.status == 200:
                    result = await response.json()
                    print(f"登录成功!")
                    print(f"完整响应: {json.dumps(result, indent=2, ensure_ascii=False)}")
                    print(f"访问令牌: {result.get('access_token', 'N/A')[:50]}...")
                    print(f"刷新令牌: {result.get('refresh_token', 'N/A')[:50]}...")
                    print(f"过期时间: {result.get('expires_in', 'N/A')} 秒")
                    print(f"用户信息: {result.get('user', 'N/A')}")
                    return True
                else:
                    error_text = await response.text()
                    print(f"登录失败: {error_text}")
                    return False
                    
    except Exception as e:
        print(f"请求异常: {e}")
        return False

if __name__ == "__main__":
    print("🔐 测试登录API...")
    success = asyncio.run(test_login_api())
    if success:
        print("✅ 登录API测试成功")
    else:
        print("❌ 登录API测试失败")