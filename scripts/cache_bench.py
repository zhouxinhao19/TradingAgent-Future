"""缓存加速比基准测试"""
import os, sys, logging
logging.disable(logging.CRITICAL)
os.environ["PYTHONIOENCODING"] = "utf-8"
import time, asyncio
from pathlib import Path

# 日志输出到文件
root = Path(__file__).resolve().parent.parent
log_path = root / "cache_bench_result.txt"

async def test():
    from tradingagents.dataflows.providers.commodity.akshare_futures import AkshareFuturesProvider
    p = AkshareFuturesProvider()
    await p.connect()

    results = []

    # === quotes ===
    t0 = time.time()
    r1 = await p.get_commodity_quotes('CU.SHF')
    t1 = time.time()
    results.append(f"[quotes] 第1次(实调): {t1-t0:.3f}s")

    t2 = time.time()
    r2 = await p.get_commodity_quotes('CU.SHF')
    t3 = time.time()
    speed = (t1-t0)/(t3-t2) if (t3-t2) > 0 else 9999
    results.append(f"[quotes] 第2次(缓存): {t3-t2:.5f}s  加速 {speed:.0f}x")

    # === historical K 线 ===
    t0 = time.time()
    h1 = await p.get_historical_data('CU0.SHF', '2025-01-01', '2025-06-30')
    t1 = time.time()
    rows = len(h1) if h1 is not None else 0
    results.append(f"[hist]   第1次(实调): {t1-t0:.3f}s  行={rows}")

    t2 = time.time()
    h2 = await p.get_historical_data('CU0.SHF', '2025-01-01', '2025-06-30')
    t3 = time.time()
    speed = (t1-t0)/(t3-t2) if (t3-t2) > 0 else 9999
    results.append(f"[hist]   第2次(缓存): {t3-t2:.5f}s  行={len(h2) if h2 is not None else 0}  加速 {speed:.0f}x")

    # === inventory ===
    t0 = time.time()
    i1 = await p.get_inventory('CU')
    t1 = time.time()
    results.append(f"[inv]    第1次(实调): {t1-t0:.3f}s")

    t2 = time.time()
    i2 = await p.get_inventory('CU')
    t3 = time.time()
    speed = (t1-t0)/(t3-t2) if (t3-t2) > 0 else 9999
    results.append(f"[inv]    第2次(缓存): {t3-t2:.5f}s  加速 {speed:.0f}x")

    # stats
    stats = p._cache.stats() if p._cache else {}
    results.append(f"\n缓存统计: {stats.get('parquet_files', 0)} 个 Parquet 文件")
    results.append(f"缓存目录: {stats.get('cache_root', 'N/A')}")

    out = "\n".join(results)
    print(out)
    # 同时写文件
    log_path.write_text(out, encoding="utf-8")
    print(f"\n结果已写入: {log_path}", file=sys.stderr)

asyncio.run(test())
