#!/usr/bin/env python3
"""
简单测试：验证API提交任务后立即响应
"""

import requests
import time

def test_api_responsiveness():
    """测试API响应性"""
    
    base_url = "http://localhost:8000"
    
    # 1. 登录
    print("🔐 登录中...")
    login_response = requests.post(f"{base_url}/api/auth/login", json={
        "username": "admin",
        "password": "admin123"
    })
    
    if login_response.status_code != 200:
        print(f"❌ 登录失败: {login_response.status_code}")
        return
    
    token = login_response.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("✅ 登录成功")
    
    # 2. 提交分析任务（应该立即返回）
    print("\n📊 提交分析任务...")
    start_time = time.time()
    
    analysis_response = requests.post(f"{base_url}/api/analysis/single", 
                                    json={
                                        "stock_code": "000001",
                                        "parameters": {
                                            "market_type": "A股",
                                            "research_depth": "标准",
                                            "selected_analysts": ["market"]
                                        }
                                    }, 
                                    headers=headers)
    
    submit_time = time.time() - start_time
    print(f"⏱️ 任务提交耗时: {submit_time:.2f}秒")
    
    if analysis_response.status_code == 200:
        task_id = analysis_response.json()["data"]["task_id"]
        print(f"✅ 任务提交成功: {task_id}")
        
        # 如果提交时间很短（<2秒），说明API没有阻塞
        if submit_time < 2.0:
            print("🎉 API响应迅速，没有阻塞！")
        else:
            print("⚠️ API响应较慢，可能仍有阻塞")
            
    else:
        print(f"❌ 任务提交失败: {analysis_response.status_code}")
        print(f"错误信息: {analysis_response.text}")
        return
    
    # 3. 立即测试其他API（应该正常响应）
    print("\n🔍 测试其他API...")
    
    # 健康检查
    health_start = time.time()
    health_response = requests.get(f"{base_url}/api/health")
    health_time = time.time() - health_start
    print(f"🏥 健康检查: {health_response.status_code} - {health_time:.2f}秒")
    
    # 用户信息
    me_start = time.time()
    me_response = requests.get(f"{base_url}/api/auth/me", headers=headers)
    me_time = time.time() - me_start
    print(f"👤 用户信息: {me_response.status_code} - {me_time:.2f}秒")
    
    # 任务状态
    status_start = time.time()
    status_response = requests.get(f"{base_url}/api/analysis/tasks/{task_id}/status", 
                                  headers=headers)
    status_time = time.time() - status_start
    print(f"📋 任务状态: {status_response.status_code} - {status_time:.2f}秒")
    
    if status_response.status_code == 200:
        status_data = status_response.json()["data"]
        print(f"📊 当前状态: {status_data['status']}")
    
    # 总结
    print(f"\n📈 性能总结:")
    print(f"  - 任务提交: {submit_time:.2f}秒")
    print(f"  - 健康检查: {health_time:.2f}秒") 
    print(f"  - 用户信息: {me_time:.2f}秒")
    print(f"  - 任务状态: {status_time:.2f}秒")
    
    if all(t < 1.0 for t in [submit_time, health_time, me_time, status_time]):
        print("🎉 所有API响应都很快，后端非阻塞工作正常！")
    else:
        print("⚠️ 某些API响应较慢，可能需要进一步优化")

if __name__ == "__main__":
    print("🧪 测试API响应性")
    print("=" * 40)
    test_api_responsiveness()
