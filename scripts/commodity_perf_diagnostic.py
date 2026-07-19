"""
commodity_perf_diagnostic.py — 全品种数据层 + 特征层性能诊断 (Phase 3b)

对所有品种逐项测试(通过 compute_all_features_from_provider 一站式完成):
  1. 8 数据接口可用性 + 特征计算成功率
  2. 6 特征模块数据质量
  3. 识别慢品种、空数据模块、性能瓶颈

用法:
  cd D:\改造\TradingAgent-CN
  python scripts/commodity_perf_diagnostic.py
  python scripts/commodity_perf_diagnostic.py --limit 5
  python scripts/commodity_perf_diagnostic.py --categories metal,energy
  python scripts/commodity_perf_diagnostic.py --include-cffex
  python scripts/commodity_perf_diagnostic.py --output report.json  # 输出JSON
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import warnings
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("USE_MONGODB_STORAGE", "false")

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import logging
logging.basicConfig(level=logging.WARNING, stream=sys.stdout, force=True)
logging.getLogger("default").setLevel(logging.WARNING)

from tradingagents.dataflows.providers.commodity.commodity_metadata import (
    EXCHANGES, list_varieties,
)
from tradingagents.utils.commodity_utils import CommodityUtils
from tradingagents.dataflows.providers.commodity.akshare_futures import (
    AkshareFuturesProvider,
)
from tradingagents.features import compute_all_features_from_provider

TRADE_DATE = datetime.now().strftime("%Y-%m-%d")
ALERT_MIN_ROWS = 30

def _resolve_symbol(variety: Dict[str, Any]) -> str:
    symbol = variety["symbol"]
    exchange = variety["exchange"]
    ex_info = EXCHANGES.get(exchange, {})
    suffix = ex_info.get("suffix", f".{exchange}")
    return f"{symbol}{suffix}"

async def diagnose_one(
    provider: AkshareFuturesProvider,
    variety: Dict[str, Any],
) -> Dict[str, Any]:
    """对单个品种运行特征层诊断——一次 compute_all_features_from_provider 调用。"""
    symbol = variety["symbol"]
    full_symbol = _resolve_symbol(variety)
    t0 = time.time()

    aggregated = await asyncio.wait_for(
        compute_all_features_from_provider(provider, full_symbol, TRADE_DATE),
        timeout=90,
    )

    elapsed_ms = int(round((time.time() - t0) * 1000))
    warnings_list = []

    # 提取特征质量
    features = aggregated.get("features", {}) or {}
    errors = aggregated.get("errors", {}) or {}
    feature_details = {}
    modules_with_data = 0

    for mod_name in ["technical", "basis", "inventory", "positioning", "term_structure", "news_sentiment"]:
        mod = features.get(mod_name)
        if mod is None:
            feature_details[mod_name] = {"has_data": False, "rows": 0}
            warnings_list.append(f"模块 `{mod_name}` 缺失")
            continue
        q = mod.get("quality", {})
        if not q:
            feature_details[mod_name] = {"has_data": False, "rows": 0}
            warnings_list.append(f"模块 `{mod_name}` 无 quality 信息")
            continue
        rows = q.get("rows", 0) or 0
        cov = q.get("coverage", 0) or 0
        has_data = rows > 0
        feature_details[mod_name] = {"has_data": has_data, "rows": rows, "coverage": cov}
        if has_data:
            modules_with_data += 1
        if rows < ALERT_MIN_ROWS and rows > 0:
            warnings_list.append(f"模块 `{mod_name}` 数据稀疏 ({rows}行)")

    for k, v in errors.items():
        if k != "total":
            warnings_list.append(f"接口/错误: {k}={v!r}")

    if modules_with_data < 3:
        warnings_list.append(f"有效模块仅 {modules_with_data}/6")

    return {
        "symbol": symbol,
        "name_cn": variety.get("name_cn", symbol),
        "exchange": variety["exchange"],
        "category": variety.get("category", ""),
        "full_symbol": full_symbol,
        "elapsed_ms": elapsed_ms,
        "features_count": modules_with_data,
        "features": feature_details,
        "errors": errors,
        "warnings": warnings_list,
        "has_problems": len(warnings_list) > 0,
    }


def build_report(all_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(all_results)
    if total == 0:
        return {}

    # 按交易所/品类汇总
    by_exchange = defaultdict(list)
    by_category = defaultdict(list)
    for r in all_results:
        by_exchange[r["exchange"]].append(r)
        by_category[r["category"]].append(r)

    # 特征模块统计: 每模块在多大比例品种中有数据
    feature_stats = {}
    for mod in ["technical", "basis", "inventory", "positioning", "term_structure", "news_sentiment"]:
        has = sum(1 for r in all_results if r["features"].get(mod, {}).get("has_data"))
        total_rows = sum(r["features"].get(mod, {}).get("rows", 0) for r in all_results)
        total_elapsed = sum(r["elapsed_ms"] for r in all_results)
        feature_stats[mod] = {
            "coverage_pct": round(has / total * 100, 1) if total else 0,
            "avg_rows": round(total_rows / total, 0) if total else 0,
        }

    # 速度
    times = sorted(r["elapsed_ms"] for r in all_results)
    avg_ms = sum(times) / len(times)
    median_ms = times[len(times) // 2]
    p95_ms = times[int(len(times) * 0.95)]

    # 慢品种 top5
    slowest = sorted(all_results, key=lambda r: -r["elapsed_ms"])[:5]

    # 警告聚合
    warn_counter = defaultdict(int)
    for r in all_results:
        for w in r["warnings"]:
            warn_counter[w] += 1
    top_warnings = sorted(warn_counter.items(), key=lambda x: -x[1])[:20]

    # 交易所
    exchange_summary = {}
    for ex, items in sorted(by_exchange.items()):
        exchange_summary[ex] = {
            "count": len(items),
            "avg_ms": round(sum(r["elapsed_ms"] for r in items) / len(items), 0),
            "avg_features": round(sum(r["features_count"] for r in items) / len(items), 1),
            "problem_pct": round(sum(1 for r in items if r["has_problems"]) / len(items) * 100, 0),
        }

    # 品类
    category_summary = {}
    for cat, items in sorted(by_category.items()):
        category_summary[cat] = {
            "count": len(items),
            "avg_ms": round(sum(r["elapsed_ms"] for r in items) / len(items), 0),
            "avg_features": round(sum(r["features_count"] for r in items) / len(items), 1),
            "problem_pct": round(sum(1 for r in items if r["has_problems"]) / len(items) * 100, 0),
        }

    return {
        "total": total,
        "date": TRADE_DATE,
        "total_time_ms": sum(times),
        "avg_ms": round(avg_ms, 0),
        "median_ms": median_ms,
        "p95_ms": p95_ms,
        "problem_count": sum(1 for r in all_results if r["has_problems"]),
        "feature_stats": feature_stats,
        "exchange_summary": exchange_summary,
        "category_summary": category_summary,
        "slowest": [{"symbol": r["symbol"], "name_cn": r["name_cn"], "ms": r["elapsed_ms"], "features": r["features_count"]} for r in slowest],
        "top_warnings": [{"text": w, "count": c} for w, c in top_warnings],
    }


def print_report(all_results: List[Dict[str, Any]], report: Dict[str, Any], verbose: bool = False):
    print(f"\n{'='*72}")
    print(f"  全品种商品诊断报告  |  {report['date']}  |  {report['total']} 品种")
    print(f"{'='*72}")

    # 速度
    print(f"\n  ⏱  速度 (单品种)")
    print(f"  {'─'*36}")
    print(f"    平均:   {report['avg_ms']/1000:.1f}s")
    print(f"    中位数: {report['median_ms']/1000:.1f}s")
    print(f"    P95:    {report['p95_ms']/1000:.1f}s")
    total_min = report['total_time_ms'] / 1000 / 60
    print(f"    总耗时: {total_min:.0f}min  ({report['problem_count']}/{report['total']} 品种有问题)")

    # 特征模块
    print(f"\n  🧩  特征模块覆盖 (有数据品种占比)")
    print(f"  {'─'*44}")
    print(f"  {'模块':<18s} {'覆盖':>8s} {'平均行数':>10s}")
    print(f"  {'─'*38}")
    for mod, st in report["feature_stats"].items():
        cov = st["coverage_pct"]
        mark = " ❌" if cov < 20 else (" ⚠️" if cov < 60 else " ✅")
        print(f"  {mod:<18s} {cov:>6.1f}%{mark} {st['avg_rows']:>9.0f}")

    # 交易所
    print(f"\n  🏛  按交易所")
    print(f"  {'─'*56}")
    print(f"  {'交易所':<8s} {'品种':>5s} {'平均耗时':>10s} {'平均模块':>10s} {'问题率':>8s}")
    for ex, st in sorted(report["exchange_summary"].items()):
        print(f"  {ex:<8s} {st['count']:>5d} {st['avg_ms']/1000:>8.1f}s {st['avg_features']:>9.1f} {st['problem_pct']:>6.0f}%")

    # 品类
    cat_names = {"agricultural": "农产品", "metal": "金属", "chemical": "化工",
                 "energy": "能源", "precious": "贵金属", "financial": "金融"}
    print(f"\n  📂  按品类")
    print(f"  {'─'*58}")
    print(f"  {'品类':<10s} {'品种':>5s} {'平均耗时':>10s} {'平均模块':>10s} {'问题率':>8s}")
    for cat, st in sorted(report["category_summary"].items()):
        cn = cat_names.get(cat, cat)
        print(f"  {cn:<10s} {st['count']:>5d} {st['avg_ms']/1000:>8.1f}s {st['avg_features']:>9.1f} {st['problem_pct']:>6.0f}%")

    # 最慢品种
    print(f"\n  🐌  最慢品种 Top 5")
    for i, s in enumerate(report["slowest"], 1):
        mod_str = f"mod={s['features']}/6"
        print(f"    {i}. {s['symbol']:6s} ({s['name_cn']})  {s['ms']/1000:.1f}s  {mod_str}")

    # 最常见警告
    top_w = report.get("top_warnings", [])
    if top_w:
        print(f"\n  ⚠️  最常见问题 (Top 10)")
        for w in top_w[:10]:
            pct = w["count"] / report["total"] * 100
            print(f"    [{w['count']:3d}x {pct:3.0f}%] {w['text']}")

    # 详细列表
    if verbose:
        print(f"\n  📋  品种明细")
        print(f"  {'─'*65}")
        header = f"  {'品种':<10s} {'代码':<5s} {'交易所':<6s} {'有效模块':<7s} {'耗时':<7s} {'问题':<15s}"
        print(header)
        for r in all_results:
            mods = f"{r['features_count']}/6"
            status = "⚠️" if r["has_problems"] else "✅"
            issues = "; ".join(r["warnings"][:2]) if r["warnings"] else ""
            print(f"  {r['name_cn']:<10s} {r['symbol']:<5s} {r['exchange']:<6s} {mods:<7s} {r['elapsed_ms']/1000:<6.1f}s {status:<3s} {issues}")

    # 根因分析
    print(f"\n{'─'*40}")
    print("  🔍  根因分析与建议")
    print(f"{'─'*40}")

    # 特征缺失严重的模块
    low_modules = [(mod, st) for mod, st in report["feature_stats"].items() if st["coverage_pct"] < 50]
    if low_modules:
        print(f"\n  数据缺失严重的模块:")
        for mod, st in sorted(low_modules, key=lambda x: x[1]["coverage_pct"]):
            print(f"    - {mod}: 仅 {st['coverage_pct']:.0f}% 品种有数据")

    # 问题集中爆发的交易所
    bad_ex = [(ex, st) for ex, st in report["exchange_summary"].items() if st["problem_pct"] > 50]
    if bad_ex:
        print(f"\n  问题集中交易所:")
        for ex, st in sorted(bad_ex, key=lambda x: -x[1]["problem_pct"]):
            print(f"    - {ex}: {st['problem_pct']:.0f}% 品种有问题 (平均特征 {st['avg_features']}/6)")

    # 速度瓶颈
    if report["p95_ms"] > report["avg_ms"] * 2:
        print(f"\n  速度不均: P95 ({report['p95_ms']/1000:.1f}s) ≈ 平均的 {report['p95_ms']/max(report['avg_ms'],1):.1f}x")
        print(f"    说明少数品种接口极慢,拖累整体体验")

    # 总结性建议
    print(f"\n  建议:")
    suggestions = []
    if low_modules:
        suggestions.append(f"🔴 修复 {', '.join(m[0] for m in low_modules)} 模块的数据接口")
    if report["avg_ms"] / 1000 > 25:
        suggestions.append(f"🟠 单品种平均 {report['avg_ms']/1000:.0f}s,全量扫描需 {total_min:.0f}min,批量任务需控制并发+超时")
    if report["median_ms"] / 1000 > 15:
        suggestions.append(f"🟡 中位数 {report['median_ms']/1000:.0f}s 表明典型品种也需要较长时间,考虑缓存常用数据")
    for s in suggestions:
        print(f"    {s}")

    print()


def main():
    parser = argparse.ArgumentParser(description="全品种商品特征层诊断")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--categories", type=str)
    parser.add_argument("--include-cffex", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--output", "-o", type=str)
    parser.add_argument("--parallel", type=int, default=1, help="并行诊断品种数(默认1)")
    args = parser.parse_args()

    # 品种列表
    all_varieties = list_varieties()
    if not args.include_cffex:
        all_varieties = [v for v in all_varieties if v["exchange"] != "CFFEX"]
    if args.categories:
        cat_set = {c.strip().lower() for c in args.categories.split(",")}
        all_varieties = [v for v in all_varieties if v.get("category", "").lower() in cat_set]
    exchange_order = {"SHFE": 0, "INE": 1, "DCE": 2, "CZCE": 3, "GFEX": 4, "CFFEX": 5}
    all_varieties.sort(key=lambda v: exchange_order.get(v["exchange"], 99))
    if args.limit > 0:
        all_varieties = all_varieties[:args.limit]
    n = len(all_varieties)

    print(f"\n{'='*72}")
    print(f"  全品种商品性能诊断  |  {n} 品种  |  日期 {TRADE_DATE}")
    print(f"{'='*72}")

    # 初始化 provider
    print(f"[*] 初始化 Provider ... ", end="", flush=True)
    provider = AkshareFuturesProvider()
    t0 = time.time()
    ok = asyncio.run(provider.connect())
    print(f"{int((time.time()-t0)*1000)}ms {'OK' if ok else 'FAIL'}")
    if not ok:
        return

    # 逐个或并行诊断
    all_results = []
    t_start = time.time()

    # 逐一模式 (并行虽然快但 AKShare 有内部缓存/限速问题,逐一更可靠)
    for idx, v in enumerate(all_varieties):
        symbol = v["symbol"]
        name_cn = v.get("name_cn", symbol)
        r = asyncio.run(diagnose_one(provider, v))
        all_results.append(r)

        elapsed_s = r["elapsed_ms"] / 1000
        mods = r["features_count"]
        status = "⚠️" if r["has_problems"] else "✅"
        slow_tag = " 🐌" if r["elapsed_ms"] > 30000 else ""
        print(f"  [{idx+1:3d}/{n}] {symbol:6s} {name_cn:8s} {elapsed_s:5.1f}s mod={mods}{status}{slow_tag}")

        if (idx + 1) % 10 == 0 or idx == n - 1:
            elapsed = time.time() - t_start
            remaining = (n - idx - 1) * (elapsed / (idx + 1))
            print(f"  --- 进度 {idx+1}/{n} | 已用 {elapsed:.0f}s | 预期剩余 {remaining:.0f}s ---")

    # 报告
    report = build_report(all_results)
    print_report(all_results, report, verbose=args.verbose)

    if args.output:
        path = Path(args.output)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[*] 报告已保存: {path}")

    print(f"\n{'='*72}")
    print(f"  完成! 总耗时 {(time.time()-t_start)/60:.1f}分钟")
    print(f"{'='*72}")

if __name__ == "__main__":
    main()
