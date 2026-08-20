"""commodity_debug.py — 商品分析链路逐步骤调试

用法:
    cd <project-root>
  python scripts/commodity_debug.py
"""
import asyncio
import sys
import os

# 修复 Windows 控制台编码
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

os.environ["USE_MONGODB_STORAGE"] = "false"

# 抑制日志乱码: 只显示 WARNING 以上
import logging
logging.basicConfig(level=logging.WARNING, stream=sys.stdout, force=True)
logging.getLogger("default").setLevel(logging.WARNING)


async def step(label: str, coro):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    try:
        result = await coro
        return result
    except Exception as e:
        print(f"  [ERROR] {type(e).__name__}: {e}")
        return None


async def main():
    symbol = "CU.SHF"
    trade_date = "2026-07-17"

    # ===== Step 1: Provider 初始化 =====
    print("\n\n[1/6] 初始化 AkshareFuturesProvider")
    from tradingagents.dataflows.providers.commodity.akshare_futures import (
        AkshareFuturesProvider,
    )

    provider = AkshareFuturesProvider()
    ok = await provider.connect()
    print(f"  connect() = {ok}")
    print(f"  connected = {provider.connected}")
    print(f"  _ak loaded = {provider._ak is not None}")

    # ===== Step 2: 逐个测试数据接口 =====
    print("\n\n[2/6] 测试数据接口")

    # 2a. futures_main_sina 直接测
    print("\n  --- 2a. futures_main_sina(CU0) ---")
    try:
        import akshare as ak
        df_sina = ak.futures_main_sina(symbol="CU0")
        print(f"  shape={df_sina.shape}, cols={list(df_sina.columns)}")
        print(f"  最新: {df_sina.iloc[-1].to_dict()}")
    except Exception as e:
        print(f"  [FAIL] {e}")

    # 2b. get_historical_data (主力连续路径)
    print("\n  --- 2b. get_historical_data(CU.SHF) ---")
    df_hist = await provider.get_historical_data(symbol, "2026-01-01", "2026-07-17")
    if df_hist is not None:
        print(f"  shape={df_hist.shape}, cols={list(df_hist.columns)}")
        print(f"  日期范围: {df_hist['日期'].min()} ~ {df_hist['日期'].max()}")
        print(f"  最新: {df_hist.iloc[-1].to_dict()}")
    else:
        print("  [FAIL] 返回 None")

    # 2c. get_historical_data_for_index
    print("\n  --- 2c. get_historical_data_for_index(CU) ---")
    df_idx = await provider.get_historical_data_for_index("CU", "2026-01-01", "2026-07-17")
    if df_idx is not None:
        print(f"  shape={df_idx.shape}")
    else:
        print("  [FAIL] 返回 None")

    # 2d. get_spot_price
    print("\n  --- 2d. get_spot_price(2026-07-17) ---")
    spot = await provider.get_spot_price(trade_date)
    if spot is not None:
        print(f"  shape={spot.shape}, cols={list(spot.columns)[:6]}")
    else:
        print("  [FAIL] 返回 None")

    # 2e. get_basis_history
    print("\n  --- 2e. get_basis_history ---")
    basis = await provider.get_basis_history("2026-01-01", trade_date, ["CU"])
    if basis is not None:
        print(f"  shape={basis.shape}")
    else:
        print("  [FAIL] 返回 None")

    # 2f. get_inventory
    print("\n  --- 2f. get_inventory(CU) ---")
    inv = await provider.get_inventory("CU")
    if inv is not None:
        print(f"  shape={inv.shape}")
    else:
        print("  [FAIL] 返回 None")

    # 2g. get_position_rank
    print("\n  --- 2g. get_position_rank(SHFE) ---")
    pos = await provider.get_position_rank("SHFE", "20260715")
    if pos is not None:
        if isinstance(pos, dict):
            for k, v in pos.items():
                if hasattr(v, "shape"):
                    print(f"  {k}: {v.shape}")
        else:
            print(f"  shape={pos.shape}")
    else:
        print("  [FAIL] 返回 None")

    # 2h. get_roll_yield
    print("\n  --- 2h. get_roll_yield ---")
    roll = await provider.get_roll_yield("date", var="CU", start_day="20260101", end_day="20260715")
    if roll is not None:
        print(f"  shape={roll.shape}")
    else:
        print("  [FAIL] 返回 None")

    # 2i. get_futures_news
    print("\n  --- 2i. get_futures_news(all) ---")
    news = await provider.get_futures_news("all", 10)
    if news:
        print(f"  {len(news)} 条")
        print(f"  第一条: {news[0].get('title', '')[:60]}")
    else:
        print("  [FAIL] 返回空")

    # ===== Step 3: compute_all_features_from_provider =====
    print("\n\n[3/6] compute_all_features_from_provider")
    from tradingagents.features import compute_all_features_from_provider

    aggregated = await compute_all_features_from_provider(provider, symbol, trade_date)
    features = aggregated.get("features", {})
    errors = aggregated.get("errors", {})
    print(f"  success={aggregated.get('success')}")
    print(f"  modules={list(features.keys())}")
    if errors:
        print(f"  errors: {errors}")
    for mod in ["technical", "basis", "inventory", "positioning", "term_structure", "news_sentiment"]:
        q = features.get(mod, {}).get("quality", {})
        if q:
            print(f"  {mod}: rows={q.get('rows')}, coverage={q.get('coverage')}")
        elif mod in features:
            print(f"  {mod}: 存在但无 quality 字段")
        else:
            print(f"  {mod}: (缺失)")

    # ===== Step 4: 初始化 CommodityTradingAgentsGraph =====
    print("\n\n[4/6] 初始化 CommodityTradingAgentsGraph")
    from tradingagents.graph.commodity_graph import CommodityTradingAgentsGraph

    config = {
        "llm_provider": "deepseek",
        "deep_think_llm": "deepseek-chat",
        "quick_think_llm": "deepseek-chat",
        "max_debate_rounds": 1,
        "max_risk_discuss_rounds": 0,
        "online_tools": False,
        "memory_enabled": False,
        "project_dir": os.getcwd(),
    }
    graph = CommodityTradingAgentsGraph(debug=False, config=config)
    print("  OK")

    # ===== Step 5: propagate (auto_features=False, 传入已算好的 features) =====
    print("\n\n[5/6] propagate (已算好 features, auto_features=False)")
    final_state, decision = graph.propagate(
        full_symbol=symbol,
        trade_date=trade_date,
        commodity_features=features,
        latest_news=news,
        variety_name="铜",
        exchange="SHF",
        category="nonferrous",
        quote_unit="元/吨",
        auto_features=False,
        provider=None,
    )
    print(f"  decision: {decision}")

    # ===== Step 6: 查看各分析师报告 =====
    print("\n\n[6/6] 各分析师报告摘要")
    for key, label in [
        ("market_report", "技术分析师"),
        ("fundamentals_report", "产业分析师"),
        ("position_report", "持仓分析师"),
        ("news_report", "新闻分析师"),
    ]:
        text = final_state.get(key, "")
        if text:
            lines = text.strip().split("\n")
            preview = lines[0][:80] if lines else "(空)"
            print(f"  {label}({len(text)} 字符): {preview}")
        else:
            print(f"  {label}: (空)")

    print("\n\n✅ 测试完成")
    return final_state, decision


if __name__ == "__main__":
    final_state, decision = asyncio.run(main())