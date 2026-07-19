"""
cache_e2e_bench.py — 两次 E2E 对比: 冷启动 vs 缓存命中

第一次: 清空缓存, 完整实调 AKShare
第二次: 所有 AKShare 数据从缓存读取 (quotes/hist/inventory/basis/spot_price)

结果写入 results/cache_e2e_bench.json
"""
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

os.environ["USE_MONGODB_STORAGE"] = "false"

# 禁用大部分日志防 GBK 编码错误
import logging
logging.getLogger("default").setLevel(logging.WARNING)
logging.getLogger("tradingagents").setLevel(logging.WARNING)

# 测试参数
symbol = "RB.SHF"
trade_date = "2026-07-17"
variety_name = "螺纹钢"
exchange = "SHF"
category = "black"
quote_unit = "元/吨"


def run_one(label: str) -> dict:
    """运行一次端到端分析, 返回耗时指标字典。"""
    from tradingagents.dataflows.providers.commodity.akshare_futures import AkshareFuturesProvider
    from tradingagents.features import compute_all_features_from_provider
    from tradingagents.graph.commodity_graph import CommodityTradingAgentsGraph

    print(f"\n{'='*60}")
    print(f"{label}")
    print(f"{'='*60}")
    print(f"标的: {symbol} ({variety_name})")
    print(f"交易日期: {trade_date}")
    print(f"开始时间: {datetime.now().strftime('%H:%M:%S')}")
    print()

    times = {}
    t_global_start = time.time()

    # ---- Step 1: 初始化 ----
    ts = time.time()
    provider = AkshareFuturesProvider()
    provider.connect()
    times["1_init"] = round(time.time() - ts, 2)

    # ---- Step 2: 拉取 Features + 新闻 ----
    ts = time.time()
    aggregated = asyncio.run(
        compute_all_features_from_provider(provider, symbol, trade_date)
    )
    commodity_features = aggregated.get("features", {}) or {}
    feature_modules = list(commodity_features.keys())

    latest_news = asyncio.run(provider.get_futures_news("all", 50)) or []
    times["2_data_fetch"] = round(time.time() - ts, 2)

    # 打印 features 质量
    for mod in ["technical", "basis", "inventory", "positioning", "term_structure", "news_sentiment"]:
        q = commodity_features.get(mod, {}).get("quality", {})
        if q:
            print(f"  {mod}: rows={q.get('rows')}, coverage={q.get('coverage')}")
        else:
            print(f"  {mod}: (无数据)")

    # 统计 news 来源
    news_sources = {}
    for n in (latest_news or []):
        src = n.get("source", "unknown")
        news_sources[src] = news_sources.get(src, 0) + 1
    print(f"  新闻: {len(latest_news)} 条 ({news_sources})")

    # ---- Step 3: 构建 Graph ----
    ts = time.time()
    config = {
        "llm_provider": "deepseek",
        "deep_think_llm": "deepseek-chat",
        "quick_think_llm": "deepseek-chat",
        "max_debate_rounds": 1,
        "max_risk_discuss_rounds": 0,
        "online_tools": False,
        "memory_enabled": False,
        "project_dir": str(PROJECT_ROOT),
    }
    graph = CommodityTradingAgentsGraph(debug=False, config=config)
    times["3_graph_init"] = round(time.time() - ts, 2)

    # ---- Step 4: 运行传播 ----
    print("\n[4/5] 运行全链路分析 (6 次 LLM 调用)...")
    completed_nodes = []
    t_prop_start = time.time()

    def progress_callback(msg):
        elapsed = time.time() - t_prop_start
        completed_nodes.append(msg)
        print(f"  [{elapsed:6.1f}s] {msg}")

    final_state, decision = graph.propagate(
        full_symbol=symbol,
        trade_date=trade_date,
        commodity_features=commodity_features,
        latest_news=latest_news,
        variety_name=variety_name,
        exchange=exchange,
        category=category,
        quote_unit=quote_unit,
        auto_features=True,
        provider=provider,
        progress_callback=progress_callback,
    )

    times["4_propagate"] = round(time.time() - t_prop_start, 2)
    times["total"] = round(time.time() - t_global_start, 2)
    print(f"\n  传播耗时: {times['4_propagate']:.1f}s")
    print(f"  执行节点: {' → '.join(completed_nodes)}")

    # ---- Step 5: 输出验证 ----
    risk_assessment = final_state.get("risk_assessment", {})
    risk_card = final_state.get("risk_card", {})
    investment_memo = final_state.get("investment_memo", {})
    final_decision_text = final_state.get("final_decision", "")
    extract_result = decision

    has_quant = bool(risk_assessment)
    has_fd = bool(final_decision_text and len(final_decision_text) > 20)
    status = "PASS" if (has_quant and has_fd) else "FAIL"

    # 缓存统计
    cache_stats = {}
    if provider._cache:
        s = provider._cache.stats()
        cache_stats = {"parquet_files": s["parquet_files"], "memory_active": s["memory"]["active"]}

    metrics = {
        "label": label,
        "status": status,
        "symbol": symbol,
        "trade_date": trade_date,
        "elapsed_seconds": times["total"],
        "data_fetch_seconds": times["2_data_fetch"],
        "propagate_seconds": times["4_propagate"],
        "llm_calls_estimate": 6,
        "completed_nodes": completed_nodes,
        "risk_level": risk_assessment.get("composite_risk_level", "N/A"),
        "decision_action": extract_result.get("action", "N/A"),
        "decision_confidence": extract_result.get("confidence", "N/A"),
        "has_investment_memo": bool(investment_memo),
        "has_risk_card": bool(risk_card),
        "final_decision_len": len(final_decision_text),
        "feature_modules": feature_modules,
        "news_count": len(latest_news),
        "cache_stats": cache_stats,
        "timestamp": datetime.now().isoformat(),
    }

    # 直接打印汇总
    print(f"\n{'='*40}")
    print(f" 耗时分解")
    print(f"{'='*40}")
    for k, v in times.items():
        print(f"  {k}: {v:.1f}s")
    print(f"\n 决策: {extract_result.get('action')} @ {extract_result.get('confidence')}")
    print(f" 状态: {status}")
    print(f" 缓存文件: {cache_stats.get('parquet_files', 0)}")

    return metrics


def main():
    result_file = PROJECT_ROOT / "results" / "cache_e2e_bench.json"

    # ===== 第一次: 冷启动 =====
    print("\n" + "★" * 30)
    print("  第一轮: 冷启动 (无缓存)")
    print("★" * 30)
    m1 = run_one("第1轮 — 冷启动 (无缓存)")

    # 写中间结果
    (PROJECT_ROOT / "results").mkdir(parents=True, exist_ok=True)
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump({"cold": m1}, f, ensure_ascii=False, indent=2)

    # ===== 第二次: 缓存命中 =====
    print("\n" + "★" * 30)
    print("  第二轮: 缓存命中")
    print("★" * 30)
    m2 = run_one("第2轮 — 缓存命中 (所有数据从缓存读取)")

    # 写最终结果
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump({"cold": m1, "warm": m2}, f, ensure_ascii=False, indent=2)

    # 打印对比
    print("\n" + "█" * 50)
    print("  缓存加速效果汇总")
    print("█" * 50)
    print(f"{'指标':<22} {'冷启动':>10} {'缓存命中':>10} {'加速':>10}")
    print("-" * 55)

    def fmt(v):
        return f"{v:.1f}s" if v else "N/A"

    def ratio(a, b):
        if b and b > 0:
            return f"{(a/b):.1f}x"
        return "N/A"

    items = [
        ("数据获取", "data_fetch_seconds"),
        ("LLM+决策链", "propagate_seconds"),
        ("总耗时", "elapsed_seconds"),
    ]
    for label, key in items:
        c = m1.get(key, 0)
        w = m2.get(key, 0)
        print(f"  {label:<20} {fmt(c):>10} {fmt(w):>10} {ratio(c, w):>10}")

    print(f"\n  Parquet 缓存文件: {m2.get('cache_stats', {}).get('parquet_files', 0)}")
    print(f"\n  result saved: {result_file}")


if __name__ == "__main__":
    main()
