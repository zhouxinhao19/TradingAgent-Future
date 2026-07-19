"""
commodity_scan_timing.py — 轻量级全品种接口耗时扫描

只测 7 个接口的耗时和成败，不做重复读取。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import warnings
from collections import defaultdict
from datetime import datetime
from pathlib import Path

warnings.filterwarnings("ignore")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("USE_MONGODB_STORAGE", "false")
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import logging
logging.basicConfig(level=logging.WARNING, stream=sys.stdout, force=True)
logging.getLogger("default").setLevel(logging.ERROR)  # suppress cache logs

from tradingagents.dataflows.providers.commodity.commodity_metadata import EXCHANGES, list_varieties
from tradingagents.dataflows.providers.commodity.akshare_futures import AkshareFuturesProvider

TRADE_DATE = datetime.now().strftime("%Y-%m-%d")
DATE_COMPACT = TRADE_DATE.replace("-", "")
TIMEOUT = 25


async def safe_call(label: str, coro, timeout=TIMEOUT):
    t0 = time.time()
    try:
        result = await asyncio.wait_for(coro, timeout=timeout)
        ms = int((time.time() - t0) * 1000)
        if result is None:
            return {"label": label, "ok": False, "ms": ms, "note": "None"}
        # Get row count
        if isinstance(result, list):
            rows = len(result)
        elif hasattr(result, "shape"):
            rows = result.shape[0]
        elif isinstance(result, dict):
            rows = len(result)
        else:
            rows = 0
        return {"label": label, "ok": True, "ms": ms, "rows": rows}
    except asyncio.TimeoutError:
        ms = int((time.time() - t0) * 1000)
        return {"label": label, "ok": False, "ms": ms, "note": "TIMEOUT"}
    except Exception as e:
        ms = int((time.time() - t0) * 1000)
        return {"label": label, "ok": False, "ms": ms, "note": f"{type(e).__name__}: {str(e)[:60]}"}


async def scan_variety(v, provider):
    symbol = v["symbol"]
    exchange = v["exchange"]
    full_symbol = symbol
    ex_info = EXCHANGES.get(exchange, {})
    suffix = ex_info.get("suffix", f".{exchange}")
    full_symbol = f"{symbol}{suffix}"
    underlying = symbol
    exchange_ak = {"SHFE": "SHFE", "INE": "INE", "DCE": "DCE", "CZCE": "CZCE", "GFEX": "GFEX"}.get(exchange, "SHFE")

    results = await asyncio.gather(
        safe_call("historical", provider.get_historical_data(full_symbol, "2025-01-01", TRADE_DATE)),
        safe_call("index", provider.get_historical_data_for_index(underlying, "2025-01-01", TRADE_DATE)),
        safe_call("basis", provider.get_basis_history("2025-01-01", TRADE_DATE, [underlying])),
        safe_call("spot", provider.get_spot_price(TRADE_DATE)),
        safe_call("inventory", provider.get_inventory(underlying)),
        safe_call("position", provider.get_position_rank(exchange_ak, DATE_COMPACT, None, underlying)),
        safe_call("roll_yield", provider.get_roll_yield("date", var=underlying, start_day="20260101", end_day=DATE_COMPACT)),
        safe_call("news", provider.get_futures_news("all", 50)),
        return_exceptions=False,
    )

    total_ms = sum(r["ms"] for r in results)
    ok_count = sum(1 for r in results if r["ok"])

    return {
        "symbol": symbol,
        "name_cn": v.get("name_cn", symbol),
        "exchange": exchange,
        "category": v.get("category", ""),
        "total_ms": total_ms,
        "ok": ok_count,
        "results": {r["label"]: r for r in results},
    }


async def main():
    varieties = list_varieties()
    varieties = [v for v in varieties if v["exchange"] != "CFFEX"]
    exchange_order = {"SHFE": 0, "INE": 1, "DCE": 2, "CZCE": 3, "GFEX": 4}
    varieties.sort(key=lambda v: exchange_order.get(v["exchange"], 99))
    n = len(varieties)

    print(f"\n{'='*72}")
    print(f"  全品种接口速度扫描 | {n} 品种 | {TRADE_DATE}")
    print(f"{'='*72}")

    provider = AkshareFuturesProvider()
    t0 = time.time()
    await provider.connect()
    print(f"  Provider: {int((time.time()-t0)*1000)}ms")
    print(f"  {'─'*60}")

    all_results = []
    t_start = time.time()

    for idx, v in enumerate(varieties):
        symbol = v["symbol"]
        name_cn = v.get("name_cn", symbol)
        r = await scan_variety(v, provider)
        all_results.append(r)

        # Print compact status
        res = r["results"]
        h = res.get("historical", {})
        b = res.get("basis", {})
        r2 = res.get("roll_yield", {})
        i = res.get("inventory", {})
        p = res.get("position", {})
        status = "✅" if r["ok"] >= 5 else ("⚠️" if r["ok"] >= 3 else "❌")
        flags = []
        if b.get("ms", 0) > 5000: flags.append(f"基差{b['ms']}ms")
        if r2.get("ms", 0) > 5000: flags.append(f"展期{r2['ms']}ms")
        flag_str = f" [{' '.join(flags)}]" if flags else ""
        print(f"  [{idx+1:3d}/{n}] {symbol:6s} {name_cn:8s} {r['total_ms']:5d}ms ok={r['ok']}/8{status}{flag_str}")

    # Summarize
    print(f"\n{'='*72}")
    print(f"  汇总")
    print(f"{'='*72}")
    all_times = [r["total_ms"] for r in all_results]
    avg = sum(all_times) / len(all_times)
    sorted_t = sorted(all_times)
    median = sorted_t[len(sorted_t)//2]
    p95 = sorted_t[int(len(sorted_t)*0.95)]
    print(f"  单品种总耗时: 平均={avg/1000:.1f}s 中位数={median/1000:.1f}s P95={p95/1000:.1f}s")
    print(f"  总耗时: {(time.time()-t_start)/60:.1f}分钟")

    # Per-interface stats
    print(f"\n  {'接口':<15s} {'成功率':>8s} {'平均':>8s} {'中位数':>8s} {'P95':>8s} {'最慢':>8s} {'空行':>8s}")
    print(f"  {'─'*70}")
    for label in ["historical", "index", "basis", "spot", "inventory", "position", "roll_yield", "news"]:
        ms_list = []
        ok = 0
        fail = 0
        zero = 0
        for r in all_results:
            res_data = r["results"].get(label, {})
            if res_data.get("ok", False):
                ok += 1
            else:
                fail += 1
            ms_list.append(res_data.get("ms", 0))
            if res_data.get("rows", -1) == 0:
                zero += 1
        if not ms_list:
            continue
        total = ok + fail
        ok_pct = ok / total * 100
        avg_ms = sum(ms_list) / len(ms_list)
        sorted_ms = sorted(ms_list)
        med_ms = sorted_ms[len(sorted_ms)//2]
        p95_ms = sorted_ms[int(len(sorted_ms)*0.95)]
        worst_ms = max(ms_list)
        print(f"  {label:<15s} {ok_pct:>7.0f}% {avg_ms:>7.0f}ms {med_ms:>7.0f}ms {p95_ms:>7.0f}ms {worst_ms:>7.0f}ms {zero:>6d}/{total}")

    # Slow varieties
    slowest = sorted(all_results, key=lambda r: -r["total_ms"])[:5]
    print(f"\n  最慢品种 Top 5:")
    for s in slowest:
        print(f"    {s['symbol']:6s} {s['name_cn']:8s} {s['total_ms']/1000:5.1f}s ok={s['ok']}/8")

    print(f"\n  完成! {(time.time()-t_start)/60:.1f}分钟")

if __name__ == "__main__":
    asyncio.run(main())
