#!/usr/bin/env python
"""
batch_commodity_analysis.py — 批量商品分析脚本

对尽可能多的商品品种运行完整分析链 (真实数据 + LLM 决策)，保存报告，全程超时监控。

用法:
  python scripts/batch_commodity_analysis.py                      # 所有品种(不含金融期货)
  python scripts/batch_commodity_analysis.py --limit 5             # 只分析前5个
  python scripts/batch_commodity_analysis.py --categories metal,energy  # 按品类过滤
  python scripts/batch_commodity_analysis.py --timeout 300         # 单品种超时300秒(默认)
  python scripts/batch_commodity_analysis.py --dry-run             # 仅列出品种,不分析
  python scripts/batch_commodity_analysis.py --include-cffex       # 含金融期货
  python scripts/batch_commodity_analysis.py --start-from RB       # 从指定品种开始(断点续跑)

超时层级:
  L1: Provider 连接 — 15s
  L2: Features 计算 — 45s
  L3: 新闻拉取     — 30s
  L4: LLM 决策链   — 由 --timeout 控制(默认 300s/品种总计)
  L5: 品种总超时   — --timeout 硬上限(超时则跳过,继续下一个)

输出:
  data/analysis_results/commodity/{symbol}/{date}/{report_id}.json  — 每品种完整报告
  data/analysis_results/commodity/batch_summary_{timestamp}.json     — 批量汇总
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import traceback
import uuid
import warnings
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── 屏蔽 AKShare 内部噪音警告(非交易日日历等) ──
warnings.filterwarnings("ignore")
# 特别针对 AKShare futures_basis 模块的 UserWarning
warnings.filterwarnings("ignore", message=".*非交易日.*")
warnings.filterwarnings("ignore", category=UserWarning, module="akshare")

# ── 路径初始化 ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("USE_MONGODB_STORAGE", "false")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# 强制 stdout/stderr 使用 UTF-8 (Windows GBK 兼容)
import io
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name)
    if hasattr(_stream, "buffer"):
        try:
            setattr(sys, _stream_name, io.TextIOWrapper(
                _stream.buffer, encoding="utf-8", errors="replace"
            ))
        except Exception:
            pass

REPORTS_BASE = PROJECT_ROOT / "data" / "analysis_results" / "commodity"
REPORTS_BASE.mkdir(parents=True, exist_ok=True)

# ── 日志 ────────────────────────────────────────────────────
import logging

logging.basicConfig(
    level=logging.WARNING,  # 抑制 tradingagents 内部 debug 日志
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
# 但保留我们自己脚本的 print 输出
logger = logging.getLogger("batch_commodity")


# ╔══════════════════════════════════════════════════════════════╗
# ║                    工具函数                                  ║
# ╚══════════════════════════════════════════════════════════════╝

def _bj_now() -> str:
    """北京时间 ISO 字符串"""
    return datetime.now(timezone.utc).astimezone(
        timezone(timedelta(hours=8))
    ).strftime("%Y-%m-%d %H:%M:%S")


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _safe_filename(s: str) -> str:
    """净化文件名"""
    import re
    return re.sub(r'[^a-zA-Z0-9.\-_]', '', s)


# ╔══════════════════════════════════════════════════════════════╗
# ║                    品种加载                                  ║
# ╚══════════════════════════════════════════════════════════════╝

def load_varieties(
    categories: Optional[List[str]] = None,
    include_cffex: bool = False,
) -> List[Dict[str, Any]]:
    """从 commodity_metadata 加载所有品种列表。

    按交易所顺序排列(SHFE→INE→DCE→CZCE→GFEX→CFFEX),保证流动性好的先跑。
    默认排除 CFFEX 金融期货(不是商品)。
    """
    from tradingagents.dataflows.providers.commodity.commodity_metadata import list_varieties

    all_varieties = list_varieties()

    # 过滤
    if not include_cffex:
        all_varieties = [v for v in all_varieties if v["exchange"] != "CFFEX"]

    if categories:
        cat_set = {c.strip().lower() for c in categories}
        all_varieties = [v for v in all_varieties if v.get("category", "").lower() in cat_set]

    # 按交易所排序(保证 SHFE 先跑)
    exchange_order = {"SHFE": 0, "INE": 1, "DCE": 2, "CZCE": 3, "GFEX": 4, "CFFEX": 5}
    all_varieties.sort(key=lambda v: exchange_order.get(v["exchange"], 99))

    return all_varieties


def resolve_full_symbol(variety: Dict[str, Any]) -> str:
    """品种 → 完整合约代码(如 RB → RB.SHF)"""
    symbol = variety["symbol"]
    exchange = variety["exchange"]

    from tradingagents.dataflows.providers.commodity.commodity_metadata import EXCHANGES

    ex_info = EXCHANGES.get(exchange, {})
    suffix = ex_info.get("suffix", f".{exchange}")

    return f"{symbol}{suffix}"


# ╔══════════════════════════════════════════════════════════════╗
# ║              超时包装器                                      ║
# ╚══════════════════════════════════════════════════════════════╝

class StepTimeout(Exception):
    """单步超时异常"""
    pass


class VarietyTimeout(Exception):
    """品种总超时异常"""
    pass


def run_with_timeout(func, *args, timeout: float, description: str = "", **kwargs):
    """在线程池中运行同步函数,带超时。

    Args:
        func: 同步可调用对象
        timeout: 超时秒数
        description: 步骤描述(用于错误消息)

    Returns:
        func 的返回值

    Raises:
        StepTimeout: 超时
    """
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args, **kwargs)
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError:
            raise StepTimeout(f"⏰ 超时({timeout}s): {description}")
        except Exception:
            raise


async def async_run_with_timeout(coro, timeout: float, description: str = ""):
    """运行异步协程,带超时。"""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        raise StepTimeout(f"⏰ 超时({timeout}s): {description}")


# ╔══════════════════════════════════════════════════════════════╗
# ║              单品种分析(在独立线程中运行)                      ║
# ╚══════════════════════════════════════════════════════════════╝

def _analyze_one_sync(
    full_symbol: str,
    trade_date: str,
    variety: Dict[str, Any],
    step_timeouts: Dict[str, float],
) -> Tuple[bool, Dict[str, Any], Dict[str, Any]]:
    """同步分析单个品种(在线程中运行)。

    Returns:
        (success, result_dict, timings_dict)
    """
    timings: Dict[str, float] = {}
    t_start = time.time()

    variety_name = variety.get("name_cn", full_symbol)
    exchange = variety.get("exchange", "")
    category = variety.get("category", "")
    quote_unit = variety.get("unit", "")

    # ── Step 1: 初始化 Provider ──
    t0 = time.time()
    from tradingagents.dataflows.providers.commodity.akshare_futures import (
        AkshareFuturesProvider,
    )
    provider = AkshareFuturesProvider()

    try:
        connected = run_with_timeout(
            provider.connect, timeout=step_timeouts["connect"],
            description=f"{full_symbol} provider.connect()"
        )
    except StepTimeout as e:
        return False, {"error": str(e), "step": "connect"}, {"connect": time.time() - t0}

    timings["connect"] = round(time.time() - t0, 1)

    if not connected:
        return False, {"error": "provider.connect() 返回 False", "step": "connect"}, timings

    # ── Step 2: Features 计算 ──
    t0 = time.time()
    from tradingagents.features import compute_all_features_from_provider

    try:
        aggregated = asyncio.run(
            async_run_with_timeout(
                compute_all_features_from_provider(provider, full_symbol, trade_date),
                timeout=step_timeouts["features"],
                description=f"{full_symbol} features 计算",
            )
        )
    except StepTimeout as e:
        return False, {"error": str(e), "step": "features"}, timings

    commodity_features = aggregated.get("features", {}) or {}
    feature_modules = list(commodity_features.keys())
    timings["features"] = round(time.time() - t0, 1)

    # ── Step 3: 新闻拉取 ──
    t0 = time.time()
    latest_news: List[Dict] = []
    try:
        latest_news = asyncio.run(
            async_run_with_timeout(
                provider.get_futures_news("all", 50),
                timeout=step_timeouts["news"],
                description=f"{full_symbol} 新闻拉取",
            )
        ) or []
    except StepTimeout as e:
        # 新闻失败不致命,继续分析
        print(f"    ⚠️ 新闻超时,继续分析(无新闻数据)")
    except Exception as e:
        print(f"    ⚠️ 新闻拉取异常: {e}")

    timings["news"] = round(time.time() - t0, 1)

    # ── Step 4: LLM 决策链 ──
    t0 = time.time()

    from tradingagents.graph.commodity_graph import CommodityTradingAgentsGraph

    config = {
        "llm_provider": os.getenv("COMMODITY_LLM_PROVIDER", "deepseek"),
        "deep_think_llm": os.getenv("COMMODITY_DEEP_LLM", "deepseek-chat"),
        "quick_think_llm": os.getenv("COMMODITY_QUICK_LLM", "deepseek-chat"),
        "max_debate_rounds": 1,
        "max_risk_discuss_rounds": 0,
        "online_tools": False,
        "memory_enabled": False,
        "project_dir": str(PROJECT_ROOT),
    }

    graph = CommodityTradingAgentsGraph(debug=False, config=config)

    completed_nodes: List[str] = []

    def progress_callback(msg):
        completed_nodes.append(msg)

    try:
        final_state, decision = graph.propagate(
            full_symbol=full_symbol,
            trade_date=trade_date,
            commodity_features=commodity_features,
            latest_news=latest_news,
            variety_name=variety_name,
            exchange=exchange,
            category=category,
            quote_unit=quote_unit,
            auto_features=False,
            provider=None,
            progress_callback=progress_callback,
        )
    except Exception as e:
        timings["llm_chain"] = round(time.time() - t0, 1)
        full_tb = traceback.format_exc()
        # 提取 traceback 中有意义的帧（过滤掉 site-packages 中的通用帧）
        tb_lines = full_tb.split("\n")
        key_lines = [l for l in tb_lines if "TradingAgent" in l or "Error" in l or "NoneType" in l]
        key_part = "\n".join(key_lines[-20:]) if key_lines else full_tb[-2000:]
        return False, {
            "error": f"{e}\n---\n{key_part}" if key_part else str(e)[:500],
            "step": "propagate",
            "completed_nodes": completed_nodes,
        }, timings

    timings["llm_chain"] = round(time.time() - t0, 1)
    timings["total"] = round(time.time() - t_start, 1)

    # ── 组装结果 ──
    result = {
        "full_symbol": full_symbol,
        "trade_date": trade_date,
        "variety_name": variety_name,
        "exchange": exchange,
        "category": category,
        "quote_unit": quote_unit,
        "decision": decision,
        "market_report": final_state.get("market_report", ""),
        "fundamentals_report": final_state.get("fundamentals_report", ""),
        "fundamentals_structured": final_state.get("fundamentals_structured", {}),
        "sentiment_report": final_state.get("sentiment_report", ""),
        "news_report": final_state.get("news_report", ""),
        "investment_plan": final_state.get("investment_plan", ""),
        "trader_investment_plan": final_state.get("trader_investment_plan", ""),
        "final_trade_decision": final_state.get("final_trade_decision", ""),
        "final_decision": final_state.get("final_decision", ""),
        "risk_assessment": final_state.get("risk_assessment", {}),
        "risk_card": final_state.get("risk_card", {}),
        "investment_memo": final_state.get("investment_memo", {}),
        "completed_nodes": completed_nodes,
        "feature_modules": feature_modules,
        "news_count": len(latest_news),
        "timings": timings,
        "batch_run_at": _bj_now(),
    }

    return True, result, timings


# ╔══════════════════════════════════════════════════════════════╗
# ║              报告保存                                        ║
# ╚══════════════════════════════════════════════════════════════╝

def save_report(full_symbol: str, trade_date: str, result: Dict[str, Any]) -> str:
    """保存报告 JSON,返回 report_id"""
    safe_sym = _safe_filename(full_symbol)
    report_id = f"{safe_sym}_{trade_date}_{uuid.uuid4().hex[:8]}"

    report_dir = REPORTS_BASE / safe_sym / trade_date
    report_dir.mkdir(parents=True, exist_ok=True)

    report_path = report_dir / f"{report_id}.json"
    result["report_id"] = report_id
    result["task_id"] = f"batch_{report_id}"

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)

    return report_id


def save_batch_summary(
    summary: Dict[str, Any],
    timestamp: str,
) -> Path:
    """保存批量汇总"""
    path = REPORTS_BASE / f"batch_summary_{timestamp}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
    return path


# ╔══════════════════════════════════════════════════════════════╗
# ║              主流程                                          ║
# ╚══════════════════════════════════════════════════════════════╝

def main():
    parser = argparse.ArgumentParser(
        description="批量商品期货分析 — 真实数据 + LLM 决策链 + 报告保存",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/batch_commodity_analysis.py --dry-run            # 仅列出品种
  python scripts/batch_commodity_analysis.py --limit 5            # 前5个品种
  python scripts/batch_commodity_analysis.py --categories metal   # 仅金属
  python scripts/batch_commodity_analysis.py --start-from RB      # 断点续跑
  python scripts/batch_commodity_analysis.py --timeout 240        # 单品种4分钟超时
        """,
    )
    parser.add_argument("--limit", type=int, default=0,
                        help="最多分析 N 个品种(0=全部)")
    parser.add_argument("--categories", type=str, default="",
                        help="品类过滤,逗号分隔 (metal/energy/chemical/agricultural/precious)")
    parser.add_argument("--include-cffex", action="store_true",
                        help="包含中金所金融期货(默认排除)")
    parser.add_argument("--start-from", type=str, default="",
                        help="从指定品种代码开始(断点续跑,如 RB)")
    parser.add_argument("--timeout", type=int, default=300,
                        help="单品种总超时秒数(默认300)")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅列出品种,不执行分析")
    parser.add_argument("--trade-date", type=str, default="",
                        help="交易日期 YYYY-MM-DD(默认今天)")
    args = parser.parse_args()

    # ── 加载品种列表 ──
    categories = [c.strip() for c in args.categories.split(",") if c.strip()] if args.categories else None
    varieties = load_varieties(categories=categories, include_cffex=args.include_cffex)

    # ── 断点续跑:从指定品种开始 ──
    if args.start_from:
        start_sym = args.start_from.strip().upper()
        found = False
        for i, v in enumerate(varieties):
            if v["symbol"].upper() == start_sym:
                varieties = varieties[i:]
                found = True
                break
        if not found:
            print(f"❌ 未找到品种: {start_sym}")
            print(f"   可用品种: {', '.join(v['symbol'] for v in varieties)}")
            sys.exit(1)
        print(f"📍 断点续跑:从 {start_sym} 开始,剩余 {len(varieties)} 个品种")

    # ── 限制数量 ──
    if args.limit and args.limit > 0:
        varieties = varieties[:args.limit]

    trade_date = args.trade_date or _today_str()

    # ── Dry run ──
    if args.dry_run:
        print(f"\n{'='*70}")
        print(f"品种列表 (共 {len(varieties)} 个,交易日期: {trade_date})")
        print(f"{'='*70}")
        print(f"{'代码':<8} {'名称':<16} {'交易所':<8} {'品类':<14} {'报价单位':<10}")
        print("-" * 70)
        for v in varieties:
            fs = resolve_full_symbol(v)
            print(f"{v['symbol']:<8} {v['name_cn']:<16} {v['exchange']:<8} "
                  f"{v.get('category',''):<14} {v.get('unit',''):<10}")
        print("-" * 70)
        print(f"排除: CFFEX 金融期货(用 --include-cffex 包含)")
        print(f"超时设置: 单品种 {args.timeout}s")
        return

    # ── 确认开始 ──
    total = len(varieties)
    est_minutes = total * 3  # 每个品种平均预估 3 分钟
    print(f"\n{'='*70}")
    print(f"🚀 批量商品分析启动")
    print(f"{'='*70}")
    print(f"品种总数: {total}")
    print(f"交易日期: {trade_date}")
    print(f"单品种超时: {args.timeout}s")
    print(f"预估总耗时: ~{est_minutes} 分钟 (~{est_minutes/60:.1f} 小时)")
    print(f"报告目录: {REPORTS_BASE}")
    print(f"开始时间: {_bj_now()}")
    print(f"{'='*70}\n")

    # ── 步骤超时配置 ──
    # 由于 features 内部已并行拉取(单调用 15-20s),总超时可缩减
    step_timeouts = {
        "connect": min(15, args.timeout / 6),
        "features": min(35, args.timeout / 3),   # 8 调用并行,max 20s + buffer
        "news": min(20, args.timeout / 4),       # 补充新闻拉取
    }
    # LLM 链路超时为剩余时间
    llm_timeout = args.timeout - step_timeouts["connect"] - step_timeouts["features"] - step_timeouts["news"]
    llm_timeout = max(llm_timeout, 60)  # 最少给 60s

    # ── 批量执行 ──
    batch_start = time.time()
    batch_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    results: List[Dict[str, Any]] = []
    success_count = 0
    fail_count = 0
    timeout_count = 0

    for idx, variety in enumerate(varieties, 1):
        symbol = variety["symbol"]
        full_symbol = resolve_full_symbol(variety)
        name_cn = variety["name_cn"]
        exchange = variety["exchange"]
        category = variety.get("category", "")

        print(f"[{idx}/{total}] {full_symbol} ({name_cn}) "
              f"| {exchange} | {category} | {_bj_now()}")

        # 在线程中运行,带总超时
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                _analyze_one_sync,
                full_symbol, trade_date, variety, step_timeouts,
            )
            try:
                success, result, timings = future.result(timeout=args.timeout)
            except FutureTimeoutError:
                timeout_count += 1
                fail_count += 1
                print(f"  ❌ 品种总超时 ({args.timeout}s),跳过")
                results.append({
                    "symbol": symbol,
                    "full_symbol": full_symbol,
                    "name_cn": name_cn,
                    "exchange": exchange,
                    "category": category,
                    "status": "timeout",
                    "error": f"品种总超时 {args.timeout}s",
                })
                continue
            except Exception as e:
                fail_count += 1
                tb = traceback.format_exc()
                print(f"  ❌ 线程异常: {e}")
                print(f"  📋 Traceback:\n{tb[-500:]}")  # 最后 500 字符
                results.append({
                    "symbol": symbol,
                    "full_symbol": full_symbol,
                    "name_cn": name_cn,
                    "exchange": exchange,
                    "category": category,
                    "status": "error",
                    "error": str(e)[:500],
                })
                continue

        if success:
            # 保存报告
            report_id = save_report(full_symbol, trade_date, result)
            decision = result.get("decision", {})
            direction = decision.get("action", "?")
            confidence = decision.get("confidence", 0)
            nodes = result.get("completed_nodes", [])

            success_count += 1
            print(f"  ✅ {direction} (置信度={confidence}) "
                  f"| 耗时 {timings.get('total', '?')}s "
                  f"| nodes={len(nodes)} "
                  f"| report={report_id}")

            results.append({
                "symbol": symbol,
                "full_symbol": full_symbol,
                "name_cn": name_cn,
                "exchange": exchange,
                "category": category,
                "status": "success",
                "report_id": report_id,
                "direction": direction,
                "confidence": confidence,
                "timings": timings,
                "feature_modules": result.get("feature_modules", []),
                "news_count": result.get("news_count", 0),
                "nodes_count": len(nodes),
            })
        else:
            fail_count += 1
            error_info = result.get("error", "未知错误")
            step = result.get("step", "?")
            print(f"  ❌ 失败 @ {step}: {error_info[:120]}")
            results.append({
                "symbol": symbol,
                "full_symbol": full_symbol,
                "name_cn": name_cn,
                "exchange": exchange,
                "category": category,
                "status": "failed",
                "error": error_info[:500],
                "failed_step": step,
                "timings": timings,
            })

        # ── 每次分析后间隔 2 秒(避免 API 限流) ──
        if idx < total:
            time.sleep(2)

    # ── 汇总 ──
    batch_elapsed = time.time() - batch_start
    summary = {
        "batch_timestamp": batch_timestamp,
        "batch_start": _bj_now(),
        "batch_elapsed_seconds": round(batch_elapsed, 1),
        "trade_date": trade_date,
        "config": {
            "timeout_per_variety": args.timeout,
            "categories_filter": categories,
            "include_cffex": args.include_cffex,
        },
        "summary": {
            "total": total,
            "success": success_count,
            "failed": fail_count - timeout_count,
            "timeout": timeout_count,
            "success_rate": f"{success_count/total*100:.1f}%" if total > 0 else "N/A",
        },
        "results": results,
    }

    summary_path = save_batch_summary(summary, batch_timestamp)

    print(f"\n{'='*70}")
    print(f"📊 批量分析汇总")
    print(f"{'='*70}")
    print(f"总计: {total} 品种")
    print(f"成功: {success_count} ({success_count/total*100:.1f}%)" if total > 0 else "N/A")
    print(f"失败: {fail_count - timeout_count}")
    print(f"超时: {timeout_count}")
    print(f"总耗时: {batch_elapsed/60:.1f} 分钟")
    print(f"汇总文件: {summary_path}")
    print(f"报告目录: {REPORTS_BASE}")
    print(f"{'='*70}")

    # ── 按品类统计成功率 ──
    if success_count > 0:
        print(f"\n📈 按品类成功率:")
        by_cat: Dict[str, List] = {}
        for r in results:
            cat = r.get("category", "unknown")
            by_cat.setdefault(cat, []).append(r)
        for cat, items in sorted(by_cat.items()):
            ok = sum(1 for i in items if i["status"] == "success")
            print(f"  {cat:<14}: {ok}/{len(items)} ({ok/len(items)*100:.0f}%)")

    # ── 方向分布 ──
    if success_count > 0:
        print(f"\n📈 决策方向分布:")
        dirs: Dict[str, int] = {}
        for r in results:
            if r["status"] == "success":
                d = r.get("direction", "?")
                dirs[d] = dirs.get(d, 0) + 1
        for d, c in sorted(dirs.items(), key=lambda x: -x[1]):
            bar = "█" * c
            print(f"  {d:<8}: {c:>3} {bar}")

    # ── 失败/超时列表 ──
    failed = [r for r in results if r["status"] != "success"]
    if failed:
        print(f"\n⚠️ 失败/超时品种 ({len(failed)}):")
        for r in failed:
            err = r.get("error", "")[:80]
            print(f"  {r['full_symbol']:<14} ({r['name_cn']:<10}) [{r['status']}] {err}")

    print(f"\n完成时间: {_bj_now()}")


if __name__ == "__main__":
    main()
