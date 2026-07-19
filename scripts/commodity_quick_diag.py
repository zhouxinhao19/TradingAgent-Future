"""
commodity_quick_diag.py — 快速诊断单个品种各数据接口耗时

用法:
  cd D:\改造\TradingAgent-CN
  python scripts/commodity_quick_diag.py CU  # 品种代码
  python scripts/commodity_quick_diag.py --all  # 所有品种(精简版)
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

from tradingagents.dataflows.providers.commodity.commodity_metadata import EXCHANGES, list_varieties
from tradingagents.dataflows.providers.commodity.akshare_futures import AkshareFuturesProvider
from tradingagents.utils.commodity_utils import CommodityUtils

TRADE_DATE = datetime.now().strftime("%Y-%m-%d")
DATE_COMPACT = TRADE_DATE.replace("-", "")
TIMEOUT = 25  # 单接口超时


async def timed_call(label: str, coro_factory, timeout=TIMEOUT):
    """执行带超时的调用,返回 (label, ok, elapsed_ms, note)。"""
    t0 = time.time()
    try:
        result = await asyncio.wait_for(coro_factory(), timeout=timeout)
        elapsed = int((time.time() - t0) * 1000)
        return label, True, elapsed, type(result).__name__
    except asyncio.TimeoutError:
        elapsed = int((time.time() - t0) * 1000)
        return label, False, elapsed, "TIMEOUT"
    except Exception as e:
        elapsed = int((time.time() - t0) * 1000)
        return label, False, elapsed, f"{type(e).__name__}: {str(e)[:60]}"


async def diagnose_interface(full_symbol: str, underlying: str, exchange: str, provider: AkshareFuturesProvider):
    """诊断单个品种的每个数据接口耗时。"""
    calls = []
    exchange_ak = {"SHFE": "SHFE", "INE": "INE", "DCE": "DCE", "CZCE": "CZCE", "GFEX": "GFEX", "CFFEX": "CFFEX"}.get(exchange, "SHFE")

    # 1. 历史K线(主力连续)
    calls.append(timed_call("historical", lambda: provider.get_historical_data(full_symbol, "2025-01-01", TRADE_DATE)))
    # 2. 指数合约
    calls.append(timed_call("index", lambda: provider.get_historical_data_for_index(underlying, "2025-01-01", TRADE_DATE)))
    # 3. 基差历史
    calls.append(timed_call("basis", lambda: provider.get_basis_history("2025-01-01", TRADE_DATE, [underlying])))
    # 4. 现货价格(通用接口)
    calls.append(timed_call("spot", lambda: provider.get_spot_price(TRADE_DATE)))
    # 5. 库存
    calls.append(timed_call("inventory", lambda: provider.get_inventory(underlying)))
    # 6. 持仓排名
    calls.append(timed_call("position", lambda: provider.get_position_rank(exchange_ak, DATE_COMPACT, None, underlying)))
    # 7. 展期收益率
    calls.append(timed_call("roll_yield", lambda: provider.get_roll_yield("date", var=underlying, start_day="20260101", end_day=DATE_COMPACT)))
    # 8. 新闻
    calls.append(timed_call("news", lambda: provider.get_futures_news("all", 50)))

    results = await asyncio.gather(*calls, return_exceptions=True)
    return results


def resolve_symbol(variety):
    symbol = variety["symbol"]
    exchange = variety["exchange"]
    ex_info = EXCHANGES.get(exchange, {})
    suffix = ex_info.get("suffix", f".{exchange}")
    return f"{symbol}{suffix}"


async def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""

    if mode == "--all":
        # 轻量级全品种扫描: 只测数据接口,不做特征计算
        varieties = list_varieties()
        varieties = [v for v in varieties if v["exchange"] != "CFFEX"]
        exchange_order = {"SHFE": 0, "INE": 1, "DCE": 2, "CZCE": 3, "GFEX": 4}
        varieties.sort(key=lambda v: exchange_order.get(v["exchange"], 99))

        print(f"=== 全品种数据接口诊断 ===")
        print(f"品种: {len(varieties)} | 日期: {TRADE_DATE}")
        print(f"{'─'*80}")

        provider = AkshareFuturesProvider()
        t0 = time.time()
        await provider.connect()
        print(f"Provider 连接: {int((time.time()-t0)*1000)}ms\n")

        all_iface_stats = defaultdict(lambda: {"ok": 0, "fail": 0, "timeout": 0, "elapsed": [], "exceptions": []})
        t_start = time.time()

        for idx, v in enumerate(varieties):
            symbol = v["symbol"]
            full = resolve_symbol(v)
            underlying = symbol
            n = v.get("name_cn", symbol)
            exchange = v["exchange"]

            print(f"  [{idx+1:3d}/{len(varieties)}] {symbol:6s} {n:8s} ({exchange})  ", end="", flush=True)
            t0 = time.time()
            results = await diagnose_interface(full, underlying, exchange, provider)
            total_ms = int((time.time() - t0) * 1000)

            status_parts = []
            ok_count = 0
            for label, ok, ms, note in results:
                if isinstance(results[-1], BaseException):
                    continue  # shouldn't happen
                s = all_iface_stats[label]
                if ms >= TIMEOUT * 1000 * 0.9:
                    s["timeout"] += 1
                elif ok:
                    s["ok"] += 1
                else:
                    s["fail"] += 1
                s["elapsed"].append(ms)
                if ok and "NoneType" not in note and "DataFrame" in note:
                    ok_count += 1

            # fetch actual df lengths for display
            hist_ok = None
            for label, ok, ms, note in results:
                if label == "historical":
                    hist_ok = ok
                if label == "inventory" and ok:
                    inv_ok = ok

            print(f"  {total_ms:4d}ms  ok={ok_count}/8  {'OK' if ok_count >= 4 else '⚠️'}")

            # 进度
            if (idx + 1) % 10 == 0 or idx == len(varieties) - 1:
                elapsed = time.time() - t_start
                remaining = (len(varieties) - idx - 1) * (elapsed / (idx + 1))
                print(f"  进度 {idx+1}/{len(varieties)} | 已用 {elapsed:.0f}s ({elapsed/60:.1f}min) | 剩余 {remaining:.0f}s")

        # 汇总
        print(f"\n{'='*80}")
        print(f"  接口耗时汇总")
        print(f"{'─'*80}")
        print(f"  {'接口':<15s} {'成功率':>8s} {'超时率':>8s} {'平均':>8s} {'中位数':>8s} {'P95':>8s} {'最慢':>8s}")
        print(f"  {'─'*65}")
        for label in ["historical", "index", "basis", "spot", "inventory", "position", "roll_yield", "news"]:
            s = all_iface_stats[label]
            total = s["ok"] + s["fail"] + s["timeout"]
            if total == 0:
                continue
            ok_pct = s["ok"] / total * 100
            to_pct = s["timeout"] / total * 100
            avg = int(sum(s["elapsed"]) / len(s["elapsed"])) if s["elapsed"] else 0
            sorted_ms = sorted(s["elapsed"])
            med = sorted_ms[len(sorted_ms)//2] if sorted_ms else 0
            p95 = sorted_ms[int(len(sorted_ms)*0.95)] if sorted_ms else 0
            worst = max(s["elapsed"]) if s["elapsed"] else 0
            print(f"  {label:<15s} {ok_pct:>7.0f}% {to_pct:>7.0f}% {avg:>7}ms {med:>7}ms {p95:>7}ms {worst:>7}ms")

        print(f"\n  总耗时: {(time.time()-t_start)/60:.1f}分钟")

    else:
        # 单品种详细诊断
        symbol_input = mode.upper()
        # 查找品种信息
        all_v = list_varieties()
        v = None
        for vv in all_v:
            if vv["symbol"] == symbol_input:
                v = vv
                break
        if not v:
            print(f"未找到品种: {symbol_input}")
            print(f"可用品种示例: CU, RB, SC, M, TA, SI")
            return

        full = resolve_symbol(v)
        underlying = v["symbol"]
        exchange = v["exchange"]
        name = v.get("name_cn", "")

        print(f"\n{'='*70}")
        print(f"  数据接口逐项诊断")
        print(f"  品种: {v['symbol']} ({name}) | {full} | {exchange}")
        print(f"  日期: {TRADE_DATE}")
        print(f"{'='*70}")

        provider = AkshareFuturesProvider()
        t0 = time.time()
        await provider.connect()
        print(f"\nProvider 连接: {int((time.time()-t0)*1000)}ms")

        results = await diagnose_interface(full, underlying, exchange, provider)

        print(f"\n{'─'*60}")
        print(f"  接口            耗时    状态    说明")
        print(f"  {'─'*50}")
        for label, ok, ms, note in results:
            status = "✅ OK" if ok else "❌ FAIL" if "TIMEOUT" not in note else "⏰ TIMEOUT"
            print(f"  {label:<15s} {ms:>5}ms  {status:<8s} {note[:50]}")

        # 行数详情
        print(f"\n{'─'*60}")
        print(f"  数据详情")
        print(f"  {'─'*40}")
        for label, ok, ms, note in results:
            if not ok:
                continue
            # Fetch the actual data to show row counts
            t0 = time.time()
            try:
                if label == "historical":
                    df = await provider.get_historical_data(full, "2025-01-01", TRADE_DATE)
                    if df is not None and not df.empty:
                        print(f"  {label:<15s} {len(df):>5} rows  {df['日期'].min()[:10]} ~ {df['日期'].max()[:10]}")
                    else:
                        print(f"  {label:<15s} EMPTY")
                elif label == "index":
                    df = await provider.get_historical_data_for_index(underlying, "2025-01-01", TRADE_DATE)
                    print(f"  {label:<15s} {len(df) if df is not None else 0:>5} rows")
                elif label == "basis":
                    df = await provider.get_basis_history("2025-01-01", TRADE_DATE, [underlying])
                    print(f"  {label:<15s} {len(df) if df is not None else 0:>5} rows")
                elif label == "inventory":
                    df = await provider.get_inventory(underlying)
                    print(f"  {label:<15s} {len(df) if df is not None else 0:>5} rows")
                elif label == "position":
                    df = await provider.get_position_rank(
                        {"SHFE": "SHFE", "INE": "INE", "DCE": "DCE", "CZCE": "CZCE", "GFEX": "GFEX"}.get(exchange, "SHFE"),
                        DATE_COMPACT, None, underlying
                    )
                    rows = 0
                    if df is not None:
                        if isinstance(df, dict):
                            rows = sum(len(v) if v is not None else 0 for v in df.values())
                        else:
                            rows = len(df)
                    print(f"  {label:<15s} {rows:>5} rows")
                elif label == "roll_yield":
                    df = await provider.get_roll_yield("date", var=underlying, start_day="20260101", end_day=DATE_COMPACT)
                    print(f"  {label:<15s} {len(df) if df is not None else 0:>5} rows")
                elif label == "news":
                    news = await provider.get_futures_news("all", 50)
                    print(f"  {label:<15s} {len(news) if news else 0:>5} items")
            except Exception as e:
                print(f"  {label:<15s} ??  {e}")

        # 特征计算
        print(f"\n{'─'*60}")
        print(f"  特征计算 (compute_all_features_from_provider)")
        print(f"  {'─'*40}")
        from tradingagents.features import compute_all_features_from_provider
        t0 = time.time()
        try:
            agg = await asyncio.wait_for(
                compute_all_features_from_provider(provider, full, TRADE_DATE),
                timeout=60,
            )
            feat_elapsed = int((time.time() - t0) * 1000)
            features = agg.get("features", {}) or {}
            errors = agg.get("errors", {})
            print(f"  耗时: {feat_elapsed}ms")
            print(f"  Errors: {errors}")
            for mod in ["technical", "basis", "inventory", "positioning", "term_structure", "news_sentiment"]:
                m = features.get(mod, {})
                if m is None:
                    print(f"  {mod:<20s} 缺失")
                    continue
                q = m.get("quality", {})
                if q:
                    rows = q.get("rows", 0)
                    cov = q.get("coverage", 0)
                    print(f"  {mod:<20s} rows={rows} coverage={cov}")
                else:
                    print(f"  {mod:<20s} 无quality")
        except asyncio.TimeoutError:
            print(f"  特征计算超时(>60s)")
        except Exception as e:
            print(f"  特征计算异常: {e}")


if __name__ == "__main__":
    asyncio.run(main())
