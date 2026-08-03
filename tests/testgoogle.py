import json
import os

import requests

# 配置
API_KEY = os.getenv("GOOGLE_API_KEY", "").strip()
if not API_KEY:
    raise SystemExit("请先设置 GOOGLE_API_KEY 环境变量")

MODEL_NAME = "gemini-2.0-flash"  # 指定使用的模型
url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent"

# 请求头
headers = {
    "Content-Type": "application/json",
    "x-goog-api-key": API_KEY,
}

# 请求数据
data = {
    "contents": [
        {
            "parts": [{"text": "请用一句话解释人工智能。"}],
        }
    ]
}

# 发送请求
response = requests.post(url, headers=headers, data=json.dumps(data), timeout=30)

# 处理响应
if response.status_code == 200:
    result = response.json()
    print(result["candidates"][0]["content"]["parts"][0]["text"])
else:
    print(f"请求失败，状态码: {response.status_code}")
    print(response.text)