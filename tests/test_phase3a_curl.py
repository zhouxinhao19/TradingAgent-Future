"""Phase 3a 端点实测 — 不跑 lifespan / TestClient."""
import sys
sys.path.insert(0, ".")

# **关键**:完全跳过 lifespan 里那些需要 MongoDB 的初始化
# 用一个独立的 mini FastAPI app,只 include 我们的 3 个 commodity router
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.routers.commodity import quotes_router, extended_router, news_router
from app.core.response import ok

mini = FastAPI(title="Phase 3a Smoke", version="1.0.0-test")
mini.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)
mini.include_router(quotes_router, prefix="/api")
mini.include_router(extended_router, prefix="/api")
mini.include_router(news_router, prefix="/api")

@mini.get("/")
async def root():
    return {"name": "phase3a-smoke", "version": "1.0.0"}

from fastapi.testclient import TestClient
client = TestClient(mini, raise_server_exceptions=False)

ENDPOINTS = [
    # categories / exchanges
    ("GET", "/api/commodity/categories", "枚举"),
    ("GET", "/api/commodity/exchanges", "枚举"),
    # varieties
    ("GET", "/api/commodity/varieties?exchange=SHFE", "字典-按交易所"),
    ("GET", "/api/commodity/varieties?category=metal", "字典-按品类"),
    # info / quotes / historical
    ("GET", "/api/commodity/CU2501.SHF/info", "基础信息"),
    ("GET", "/api/commodity/CU2501.SHF/quotes", "实时行情"),
    ("GET", "/api/commodity/CU2501.SHF/historical?start_date=2025-01-01", "历史K线"),
    # extended
    ("GET", "/api/commodity/CU2501.SHF/fees", "费用保证金"),
    ("GET", "/api/commodity/A.DCE/inventory", "库存"),
    ("GET", "/api/commodity/SHFE/warehouse-receipt", "仓单"),
    ("GET", "/api/commodity/DCE/position-rank", "持仓排名"),
    ("GET", "/api/commodity/spot-price", "现货"),
    ("GET", "/api/commodity/basis?vars_list=CU,AL&start_day=2025-06-01&end_day=2025-06-30", "基差历史"),
    ("GET", "/api/commodity/basis-spot-previous", "基差前一日"),
    ("GET", "/api/commodity/roll-yield?type_method=var&date=2025-07-10", "展期收益"),
    ("GET", "/api/commodity/SHFE/contract-info", "合约信息"),
    ("GET", "/api/commodity/trading-calendar", "交易日历"),
    ("GET", "/api/commodity/realtime-quote?symbols=CU2501", "实时行情多"),
    ("GET", "/api/commodity/RB0.SHF/minute-kline?period=5", "分时K线"),
    ("GET", "/api/commodity/DCE/delivery-info?date=202507", "交割"),
    ("GET", "/api/commodity/OI2501.CZC/holding-position", "持仓"),
    # news
    ("GET", "/api/commodity/news/categories", "新闻分类"),
    ("GET", "/api/commodity/news?category=metal&limit=10", "新闻-metal"),
    ("GET", "/api/commodity/news?category=global_macro&limit=10", "新闻-宏观"),
]


def safe_get(payload, *path):
    cur = payload
    for k in path:
        try:
            if isinstance(cur, dict):
                cur = cur.get(k)
            else:
                return None
        except Exception:
            return None
    return cur


def summarise(payload):
    if not isinstance(payload, dict):
        return "?"
    success = payload.get("success")
    message = payload.get("message", "")
    data = payload.get("data")
    if isinstance(data, dict):
        cnt = data.get("count")
        if cnt is None and "items" in data:
            cnt = len(data["items"]) if isinstance(data["items"], list) else "-"
        return f"{success}|{message[:20]}|count={cnt}"
    if isinstance(data, list):
        return f"{success}|{message[:20]}|len={len(data)}"
    return f"{success}|{message[:30]}"


print(f"\n[Phase 3a] {len(ENDPOINTS)} 个端点\n")
print(f"{'STATUS':<7} {'OUTCOME':<55} {'NOTE':<10} URL")
print("-" * 130)

results = []
for method, url, note in ENDPOINTS:
    r = client.get(url)
    try:
        payload = r.json()
    except Exception:
        payload = None
    sm = summarise(payload) if payload else "non-JSON"
    print(f"{r.status_code:<7} {sm:<55} {note:<10} {url}")
    results.append((r.status_code, url, note))

ok = sum(1 for s, _, _ in results if 200 <= s < 300)
client_err = sum(1 for s, _, _ in results if 400 <= s < 500)
server_err = sum(1 for s, _, _ in results if s >= 500)
print(f"\n[汇总] 2xx={ok}  4xx={client_err}  5xx={server_err}  共 {len(results)}")
