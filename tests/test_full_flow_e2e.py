"""
End-to-end full flow test - commodity data layer + API endpoints.
Covers AkshareFuturesProvider all methods and 53 HTTP endpoints.
"""
import asyncio, sys, json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, ".")

# Config
TEST_SYMBOLS = {
    "CU2508.SHF":   {"category": "metal",     "exchange": "SHFE", "name": "CU2508"},
    "AU2512.SHF":   {"category": "precious",  "exchange": "SHFE", "name": "AU2512"},
    "RB2510.SHF":   {"category": "black",     "exchange": "SHFE", "name": "RB2510"},
    "SC2509.INE":   {"category": "energy",    "exchange": "INE",  "name": "SC2509"},
    "A2509.DCE":    {"category": "agricultural", "exchange": "DCE", "name": "A2509"},
    "M2509.DCE":    {"category": "agricultural", "exchange": "DCE", "name": "M2509"},
    "TA2509.CZC":   {"category": "chemical",  "exchange": "CZCE", "name": "TA2509"},
    "SI2509.GFEX":  {"category": "minor",     "exchange": "GFEX", "name": "SI2509"},
}

MAIN_CONT = {"CU0.SHF": "CU main", "RB0.SHF": "RB main", "SC0.INE": "SC main"}
ALL_EXCHANGES = ["SHFE", "DCE", "CZCE", "INE", "GFEX", "CFFEX"]
TODAY = datetime.now().strftime("%Y-%m-%d")
TODAY_6 = datetime.now().strftime("%Y%m%d")[:6]

results: List[Dict[str, Any]] = []
errors: List[Dict[str, Any]] = []

def record(source: str, item: str, status: str, detail: str = "",
           data_count: Optional[int] = None):
    results.append({"source": source, "item": item, "status": status,
                    "detail": detail[:200], "data_count": data_count})

def record_error(source: str, item: str, exc: Exception):
    err_msg = f"{type(exc).__name__}: {exc}"[:200]
    errors.append({"source": source, "item": item, "error": err_msg})
    record(source, item, "ERROR", err_msg)

async def test_data_layer():
    print("\n" + "="*70)
    print("[A] Data Layer Test -- AkshareFuturesProvider")
    print("="*70)

    from tradingagents.dataflows.providers.commodity.akshare_futures import AkshareFuturesProvider
    provider = AkshareFuturesProvider()
    ok = await provider.connect()
    if not ok:
        record("data_layer", "connect", "FAIL", "connect() returned False")
        print("  [FAIL] Provider connect failed, skipping")
        return
    record("data_layer", "connect", "PASS")

    # A0: list_all_varieties
    print("\n  [A0] list_all_varieties")
    varieties = await provider.list_all_varieties()
    cnt = len(varieties) if varieties else 0
    record("data_layer", "list_all_varieties", "PASS" if cnt > 0 else "WARN",
           f"{cnt} varieties", data_count=cnt)
    print(f"    varieties: {cnt}")

    # A1: Core 4 methods
    print("\n  [A1] Core 4 methods")
    for sym, meta in TEST_SYMBOLS.items():
        info = await provider.get_commodity_basic_info(sym)
        ok_i = info is not None
        record("data_layer", f"basic_info({sym})", "PASS" if ok_i else "WARN",
               f"name={info.get('name','') if info else 'None'}")
        if not ok_i: print(f"    FAIL basic_info({meta['name']})")

        try:
            q = await provider.get_commodity_quotes(sym)
            ok_q = q is not None
            cp = q.get("current_price", 0) if q else 0
            record("data_layer", f"quotes({sym})", "PASS" if ok_q else "WARN",
                   f"price={cp}")
        except Exception as e:
            record("data_layer", f"quotes({sym})", "WARN", f"quote exception: {e}")

        try:
            df = await provider.get_historical_data(sym, "2025-06-01", TODAY)
            rows = len(df) if df is not None else 0
            record("data_layer", f"historical({sym})", "PASS" if rows > 0 else "WARN",
                   f"{rows} rows", data_count=rows)
        except Exception as e:
            record_error("data_layer", f"historical({sym})", e)

    # A2: Extended 13+ interfaces
    print("\n  [A2] Extended interfaces")

    # fees
    for ex in ["SHFE", "DCE"]:
        try:
            fm = await provider.get_fees_and_margin(exchange=ex)
            ok_f = fm is not None
            record("data_layer", f"fees({ex})", "PASS" if ok_f else "WARN")
        except Exception as e:
            record_error("data_layer", f"fees({ex})", e)

    # inventory
    for s in ["A", "RB"]:
        try:
            inv = await provider.get_inventory(s)
            rows = len(inv) if inv is not None and hasattr(inv, '__len__') else 0
            record("data_layer", f"inventory({s})", "PASS" if rows > 0 else "WARN",
                   f"{rows} rows", data_count=rows)
        except Exception as e:
            record_error("data_layer", f"inventory({s})", e)

    # warehouse receipt
    for ex in ["SHFE", "DCE"]:
        try:
            wh = await provider.get_warehouse_receipt(ex, TODAY)
            record("data_layer", f"warehouse_receipt({ex})", "PASS" if wh else "WARN")
        except Exception as e:
            record_error("data_layer", f"warehouse_receipt({ex})", e)

    # position rank
    for ex in ["DCE", "SHFE"]:
        try:
            pr = await provider.get_position_rank(ex, TODAY, vars_list=["A", "B"])
            record("data_layer", f"position_rank({ex})", "PASS" if pr else "WARN")
        except Exception as e:
            record_error("data_layer", f"position_rank({ex})", e)

    # spot price
    try:
        sp = await provider.get_spot_price(TODAY)
        rows = len(sp) if sp is not None and hasattr(sp, '__len__') else 0
        record("data_layer", "spot_price", "PASS" if rows > 0 else "WARN",
               f"{rows} rows", data_count=rows)
    except Exception as e:
        record_error("data_layer", "spot_price", e)

    # basis history
    try:
        bh = await provider.get_basis_history("2025-07-01", TODAY, ["CU", "AL"])
        rows = len(bh) if bh is not None and hasattr(bh, '__len__') else 0
        record("data_layer", "basis_history", "PASS" if rows > 0 else "WARN",
               f"{rows} rows", data_count=rows)
    except Exception as e:
        record_error("data_layer", "basis_history", e)

    # basis spot previous
    try:
        bsp = await provider.get_basis_spot_previous(TODAY)
        rows = len(bsp) if bsp is not None and hasattr(bsp, '__len__') else 0
        record("data_layer", "basis_spot_previous", "PASS" if rows > 0 else "WARN",
               f"{rows} rows", data_count=rows)
    except Exception as e:
        record_error("data_layer", "basis_spot_previous", e)

    # roll yield
    try:
        ry = await provider.get_roll_yield(type_method="var", date=TODAY)
        rows = len(ry) if ry is not None and hasattr(ry, '__len__') else 0
        record("data_layer", "roll_yield(var)", "PASS" if rows > 0 else "WARN",
               f"{rows} rows", data_count=rows)
    except Exception as e:
        record_error("data_layer", "roll_yield", e)

    # contract info -- all exchanges
    for ex in ["SHFE", "DCE", "CZCE", "INE", "GFEX", "CFFEX"]:
        try:
            ci = await provider.get_contract_info(ex, TODAY)
            rows = len(ci) if ci is not None and hasattr(ci, '__len__') else 0
            record("data_layer", f"contract_info({ex})", "PASS" if rows > 0 else "WARN",
                   f"{rows} rows", data_count=rows)
        except Exception as e:
            record_error("data_layer", f"contract_info({ex})", e)

    # trading calendar
    try:
        tc = await provider.get_trading_calendar(TODAY)
        rows = len(tc) if tc is not None and hasattr(tc, '__len__') else 0
        record("data_layer", "trading_calendar", "PASS" if rows > 0 else "WARN",
               f"{rows} rows", data_count=rows)
    except Exception as e:
        record_error("data_layer", "trading_calendar", e)

    # realtime quote
    for market in ["CF", "FF"]:
        try:
            sym_str = "CU2508,AU2512,RB2510" if market == "CF" else "IF,TF,IC"
            rq = await provider.get_realtime_quote(sym_str, market=market)
            rows = len(rq) if rq is not None and hasattr(rq, '__len__') else 0
            record("data_layer", f"realtime_quote({market})", "PASS" if rows > 0 else "WARN",
                   f"{rows} rows", data_count=rows)
        except Exception as e:
            record_error("data_layer", f"realtime_quote({market})", e)

    # minute kline
    for cont_sym in MAIN_CONT:
        sym_part = cont_sym.split(".")[0]
        try:
            mk = await provider.get_minute_kline(sym_part, period=5)
            rows = len(mk) if mk is not None and hasattr(mk, '__len__') else 0
            record("data_layer", f"minute_kline({cont_sym})", "PASS" if rows > 0 else "WARN",
                   f"{rows} rows", data_count=rows)
        except Exception as e:
            record_error("data_layer", f"minute_kline({cont_sym})", e)

    # delivery info
    for ex in ["DCE", "CZCE", "SHFE"]:
        try:
            di = await provider.get_delivery_info(ex, TODAY_6)
            record("data_layer", f"delivery_info({ex})", "PASS" if di else "WARN")
        except Exception as e:
            record_error("data_layer", f"delivery_info({ex})", e)

    # holding position
    for sym in ["CU2508", "RB2510"]:
        try:
            hp = await provider.get_holding_position(sym, indicator="成交量")
            rows = len(hp) if hp is not None and hasattr(hp, '__len__') else 0
            record("data_layer", f"holding_position({sym})", "PASS" if rows > 0 else "WARN",
                   f"{rows} rows", data_count=rows)
        except Exception as e:
            record_error("data_layer", f"holding_position({sym})", e)

    # A3: News
    print("\n  [A3] News categories")
    for cat in ["all", "metal", "precious", "global_macro",
                "chemical", "energy", "agricultural", "headline"]:
        try:
            news = await provider.get_futures_news(cat, limit=5)
            cnt = len(news) if news else 0
            warn_note = " (expected empty - no mapping)" if cat in ("chemical", "energy", "agricultural") else ""
            record("data_layer", f"news({cat})", "PASS" if cnt > 0 else "WARN",
                   f"{cnt} items{warn_note}", data_count=cnt)
        except Exception as e:
            record_error("data_layer", f"news({cat})", e)

    await provider.disconnect()


def test_api_endpoints():
    print("\n" + "="*70)
    print("[B] API Endpoint Test (TestClient)")
    print("="*70)

    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.testclient import TestClient

    mini = FastAPI(title="Full Flow Smoke")
    mini.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                        allow_methods=["*"], allow_headers=["*"])
    from app.routers.commodity import quotes_router, extended_router, news_router
    mini.include_router(quotes_router, prefix="/api")
    mini.include_router(extended_router, prefix="/api")
    mini.include_router(news_router, prefix="/api")

    client = TestClient(mini, raise_server_exceptions=False)

    def check(url: str, min_count: int = 0) -> Tuple[int, str, int]:
        try:
            r = client.get(url)
            if r.status_code != 200:
                return r.status_code, f"HTTP {r.status_code}", 0
            payload = r.json()
            success = payload.get("success", False)
            data = payload.get("data", {})
            if isinstance(data, dict):
                cnt = data.get("count", 0) or data.get("total", 0) or 0
            elif isinstance(data, list):
                cnt = len(data)
            else:
                cnt = 0
            if success:
                extra = f" (empty)" if cnt == 0 and min_count > 0 else ""
                return 200, f"OK count={cnt}{extra}", cnt
            else:
                return 200, f"success=False msg={payload.get('message','')[:30]}", cnt
        except Exception as e:
            return 0, f"EXCEPTION: {e}", 0

    def do(url: str, source: str, label: str, mc: int = 0):
        s, summary, cnt = check(url, min_count=mc)
        status = "PASS" if s == 200 else "FAIL"
        record(source, label, status, summary, data_count=cnt)

    # B1: Basic quotes (categories, exchanges)
    print("\n  [B1] Basic quotes endpoints")
    do("/api/commodity/categories", "api_quotes", "categories")
    do("/api/commodity/exchanges", "api_quotes", "exchanges")

    for sym in TEST_SYMBOLS:
        do(f"/api/commodity/{sym}/info", "api_quotes", f"info({sym})")
        do(f"/api/commodity/{sym}/quotes", "api_quotes", f"quotes({sym})")
        do(f"/api/commodity/{sym}/historical?start_date=2025-06-01",
           "api_quotes", f"historical({sym})", mc=1)

    # B2: Extended data endpoints
    print("\n  [B2] Extended data endpoints")
    do("/api/commodity/varieties", "api_extended", "varieties(all)")
    for ex in ALL_EXCHANGES:
        do(f"/api/commodity/varieties?exchange={ex}", "api_extended", f"varieties({ex})")

    for sym in ["CU2508.SHF", "RB2510.SHF", "SC2509.INE", "TA2509.CZC"]:
        do(f"/api/commodity/{sym}/fees", "api_extended", f"fees({sym})")

    for sym in ["A.DCE", "CU.SHF", "RB.SHF"]:
        do(f"/api/commodity/{sym}/inventory", "api_extended", f"inventory({sym})")

    for ex in ["SHFE", "DCE", "CZCE", "GFEX"]:
        do(f"/api/commodity/{ex}/warehouse-receipt?date={TODAY}",
           "api_extended", f"warehouse-receipt({ex})")

    for ex in ["DCE", "SHFE", "CZCE", "GFEX"]:
        do(f"/api/commodity/{ex}/position-rank?date={TODAY}",
           "api_extended", f"position-rank({ex})")

    do(f"/api/commodity/spot-price?date={TODAY}", "api_extended", "spot-price")
    do(f"/api/commodity/basis?vars_list=CU,AL&start_day=2025-07-01&end_day={TODAY}",
       "api_extended", "basis(CU,AL)")
    do(f"/api/commodity/basis-spot-previous?date={TODAY}", "api_extended", "basis-spot-previous")
    do(f"/api/commodity/roll-yield?type_method=var&date={TODAY}", "api_extended", "roll-yield(var)")

    for ex in ["SHFE", "DCE", "CZCE", "INE", "GFEX", "CFFEX"]:
        do(f"/api/commodity/{ex}/contract-info?date={TODAY}", "api_extended", f"contract-info({ex})")

    for sym in ["CU2508.SHF", "RB2510.SHF", "A2509.DCE", "SC2509.INE"]:
        do(f"/api/commodity/{sym}/contracts-list", "api_extended", f"contracts-list({sym})")

    do(f"/api/commodity/trading-calendar?date={TODAY}", "api_extended", "trading-calendar")
    do(f"/api/commodity/realtime-quote?symbols=CU2508,AU2512,RB2510&market=CF",
       "api_extended", "realtime-quote(CF)")

    for cont_sym in MAIN_CONT:
        do(f"/api/commodity/{cont_sym}/minute-kline?period=5", "api_extended", f"minute-kline({cont_sym})")

    for ex in ["DCE", "CZCE", "SHFE"]:
        do(f"/api/commodity/{ex}/delivery-info?date={TODAY_6}", "api_extended", f"delivery-info({ex})")

    for sym in ["CU2508.SHF", "RB2510.SHF", "OI2509.CZC"]:
        do(f"/api/commodity/{sym}/holding-position?indicator=成交量",
           "api_extended", f"holding-position({sym})")

    # B3: News
    print("\n  [B3] News endpoints")
    do("/api/commodity/news/categories", "api_news", "news-categories")
    for cat in ["all", "metal", "precious", "global_macro"]:
        do(f"/api/commodity/news?category={cat}&limit=5", "api_news", f"news({cat})")


def generate_report():
    print("\n" + "="*70)
    print("[C] Test Report")
    print("="*70)

    total = len(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    warned = sum(1 for r in results if r["status"] == "WARN")
    failed = sum(1 for r in results if r["status"] in ("FAIL", "ERROR"))

    source_groups: Dict[str, List[Dict]] = {}
    for r in results:
        source_groups.setdefault(r["source"], []).append(r)

    print(f"\n  Total: {total}  |  PASS: {passed}  |  WARN: {warned}  |  FAIL: {failed}")
    print(f"  Exceptions: {len(errors)}\n")

    # Summary table
    print(f"\n{'Source':<20} {'Total':>5} {'PASS':>5} {'WARN':>5} {'FAIL':>5}  {'Rate':>7}")
    print("-"*52)
    for source, items in sorted(source_groups.items()):
        p = sum(1 for i in items if i["status"] == "PASS")
        w = sum(1 for i in items if i["status"] == "WARN")
        f = sum(1 for i in items if i["status"] in ("FAIL", "ERROR"))
        rate = f"{p/len(items)*100:.0f}%" if items else "N/A"
        print(f"{source:<20} {len(items):>5} {p:>5} {w:>5} {f:>5}  {rate:>7}")
    print("-"*52)
    rate = f"{passed/total*100:.0f}%" if total else "N/A"
    print(f"{'TOTAL':<20} {total:>5} {passed:>5} {warned:>5} {failed:>5}  {rate:>7}")

    # Detail per source
    for source, items in sorted(source_groups.items()):
        non_pass = [i for i in items if i["status"] != "PASS"]
        if not non_pass:
            continue
        print(f"\n  [{source}] Non-PASS items:")
        for item in non_pass:
            dc = f" (data={item['data_count']})" if item.get('data_count') else ""
            print(f"    {item['status']:5s}  {item['item']:<50s} {item['detail'][:80]}{dc}")

    # Key findings
    warn_items = [r for r in results if r["status"] == "WARN"]
    fail_items = [r for r in results if r["status"] in ("FAIL", "ERROR")]

    if fail_items:
        print(f"\n  FAILED items ({len(fail_items)}):")
        for item in fail_items:
            print(f"    - {item['source']}/{item['item']}: {item['detail'][:100]}")
    if warn_items:
        print(f"\n  WARN items ({len(warn_items)}):")
        for item in warn_items:
            print(f"    - {item['source']}/{item['item']}: {item['detail'][:100]}")

    # Blocked paths summary
    blocked = [r for r in results if r["status"] in ("WARN", "FAIL", "ERROR")]
    if not blocked:
        print("\n  ALL DATA PATHS PASSED!")
    else:
        print(f"\n  PROBLEMATIC PATHS: {len(blocked)} items")
        for b in blocked:
            print(f"    {b['status']:5s}  {b['source']:<20s} {b['item']:<45s}")

    return passed, warned, failed


async def main():
    print("="*70)
    print("  TradingAgent-CN End-to-End Full Flow Test")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    await test_data_layer()
    test_api_endpoints()
    passed, warned, failed = generate_report()

    print("\n" + "="*70)
    print(f"  DONE | PASS: {passed} | WARN: {warned} | FAIL: {failed}")
    print("="*70)
    return passed, warned, failed

if __name__ == "__main__":
    asyncio.run(main())
