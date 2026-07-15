"""Debug:为什么 /api/commodity/categories 返回 500?"""
import sys
sys.path.insert(0, ".")

# 先看 import 阶段能不能拿到 app
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app, raise_server_exceptions=True)
try:
    r = client.get("/api/commodity/categories")
    print("status:", r.status_code)
    print("body:", r.text[:500])
except Exception as e:
    import traceback
    traceback.print_exc()
