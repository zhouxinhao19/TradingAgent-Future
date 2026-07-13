"""
Phase 0 + Phase 1 演示脚本
- 验证 Instrument.of() 工厂方法
- 验证 CommodityUtils 识别能力
- 启动 mini FastAPI 服务:
  - /api/config/features - Feature flag
  - /api/instrument/{code} - 标的识别
  - /api/commodity/* (Phase 1,需 FEATURE_COMMODITY_DATA=true)
"""
import sys
import os

# 把项目根目录加到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn

from app.core.config import settings
from tradingagents.core.instrument import (
    Instrument, ASSET_TYPE_STOCK, ASSET_TYPE_COMMODITY
)
from tradingagents.utils.commodity_utils import (
    CommodityUtils, CommodityMarket
)
from tradingagents.utils.stock_utils import StockUtils, StockMarket

print("=" * 60)
print("Phase 0 + Phase 1 演示:股票/大宗商品抽象 + Feature Flag + 行情 API")
print("=" * 60)

# 1. 验证 Instrument 工厂方法
print("\n[1] Instrument 工厂方法")
test_codes = [
    "000001", "0700.HK", "AAPL",
    "CU2501.SHF", "CL=F", "GC=F", "AU9999.SGE",
]
for code in test_codes:
    inst = Instrument.of(code)
    print(f"  {code:15s} -> asset_type={inst.asset_type:8s} market={inst.market:15s} category={inst.category:15s} currency={inst.currency}")

# 2. 验证 CommodityUtils
print("\n[2] CommodityUtils 商品识别")
for code in ["CU2501.SHF", "CL=F", "AU9999.SGE"]:
    market = CommodityUtils.identify_market(code)
    info = CommodityUtils.get_market_info(code)
    print(f"  {code:15s} -> {market.value:15s} category={info['category']:15s} currency={info['currency']}")

# 3. 验证 Feature Flag
print("\n[3] Feature Flag 当前状态")
flags = settings.FEATURE_FLAGS
for k, v in flags.items():
    print(f"  {k:30s} = {v}")

# 4. 启动 mini FastAPI 服务
print("\n[4] 启动 mini FastAPI 服务(端口 8765)")
app = FastAPI(title="Phase 0 + Phase 1 演示", version="1.1.0")

@app.get("/")
def root():
    return {
        "message": "Phase 0 + Phase 1 演示服务",
        "phase": "0 抽象统一 + 1 行情闭环",
        "status": "running",
        "feature_flags": settings.FEATURE_FLAGS,
        "endpoints": [
            "GET /api/health - 健康检查",
            "GET /api/config/features - Feature flag 状态",
            "GET /api/instrument/{code} - 识别任意标的代码",
            "GET /api/commodity/categories - 商品品类(Phase 1)",
            "GET /api/commodity/exchanges - 交易所(Phase 1)",
            "GET /api/commodity/{full_symbol}/info - 基础信息(Phase 1)",
            "GET /api/commodity/{full_symbol}/quotes - 实时行情(Phase 1)",
            "GET /api/commodity/{full_symbol}/historical?start_date=YYYY-MM-DD - 历史 K 线(Phase 1)",
        ]
    }

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "phase-0-1-demo"}

@app.get("/api/config/features")
def get_features():
    return JSONResponse(content={
        "success": True,
        "data": settings.FEATURE_FLAGS,
        "message": "获取功能开关成功"
    })

@app.get("/api/instrument/{code}")
def identify_instrument(code: str):
    inst = Instrument.try_of(code)
    if inst is None:
        return JSONResponse(status_code=400, content={"success": False, "error": f"无法识别代码: {code}"})
    return {"success": True, "data": inst.to_dict()}

# ===== Phase 1: 大宗商品路由(条件加载) =====
if settings.FEATURE_COMMODITY_ENABLED and settings.FEATURE_COMMODITY_DATA:
    try:
        from app.routers.commodity import quotes_router
        app.include_router(quotes_router, prefix="/api")
        print("\n[5] 已挂载 /api/commodity/* 路由(Phase 1 数据闭环)")
    except Exception as e:
        print(f"\n[!] 挂载 commodity 路由失败: {e}")
else:
    print("\n[5] commodity 路由未挂载(flag 关闭)")

if __name__ == "__main__":
    print(f"\n服务地址: http://localhost:8765")
    print(f"   健康检查: http://localhost:8765/api/health")
    print(f"   Feature flags: http://localhost:8765/api/config/features")
    print(f"   识别标的: http://localhost:8765/api/instrument/CU2501.SHF")
    if settings.FEATURE_COMMODITY_ENABLED and settings.FEATURE_COMMODITY_DATA:
        print(f"   商品品类: http://localhost:8765/api/commodity/categories")
        print(f"   基础信息: http://localhost:8765/api/commodity/CU2501.SHF/info")
        print(f"   实时行情: http://localhost:8765/api/commodity/AU2506.SHF/quotes")
        print(f"   历史K线: http://localhost:8765/api/commodity/SR2501.CZC/historical?start_date=2025-01-01")
    print(f"\nCtrl+C 停止\n")
    uvicorn.run(app, host="0.0.0.0", port=8765, log_level="warning")
