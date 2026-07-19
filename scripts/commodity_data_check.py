"""commodity_data_check.py — 仅验证数据层，不碰 LLM"""
import asyncio, sys, os

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
os.environ["USE_MONGODB_STORAGE"] = "false"

import logging
logging.basicConfig(level=logging.WARNING, stream=sys.stdout, force=True)
logging.getLogger("default").setLevel(logging.WARNING)


async def safe(label, coro):
    try:
        return await coro
    except Exception as e:
        print(f"  [FAIL] {e}")
        return None


async def main():
    symbol = "CU.SHF"
    underlying = "CU"
    trade_date = "2026-07-17"

    print("=" * 60)
    print("1. 初始化 Provider")
    print("=" * 60)
    from tradingagents.dataflows.providers.commodity.akshare_futures import AkshareFuturesProvider
    provider = AkshareFuturesProvider()
    ok = await provider.connect()
    print(f"  connect()={ok}, _ak={provider._ak is not None}")

    print("\n" + "=" * 60)
    print("2. 测试 futures_main_sina (主力连续)")
    print("=" * 60)
    try:
        import akshare as ak
        df = ak.futures_main_sina(symbol="CU0")
        print(f"  shape={df.shape}")
        print(f"  cols={list(df.columns)}")
        print(f"  最新行: {df.iloc[-1].to_dict()}")
    except Exception as e:
        print(f"  [FAIL] futures_main_sina CU0: {e}")

    print("\n" + "=" * 60)
    print("3. 测试 get_historical_data (CU.SHF)")
    print("=" * 60)
    df = await safe("hist", provider.get_historical_data(symbol, "2026-01-01", "2026-07-17"))
    if df is not None:
        print(f"  shape={df.shape}, 日期={df['日期'].min()} ~ {df['日期'].max()}")
        print(f"  最新收盘价={df.iloc[-1].get('收盘价','?')}")
    else:
        print("  [FAIL] 返回 None")

    print("\n" + "=" * 60)
    print("4. 测试 get_historical_data_for_index (CU 指数)")
    print("=" * 60)
    df = await safe("index", provider.get_historical_data_for_index(underlying, "2026-01-01", "2026-07-17"))
    if df is not None:
        print(f"  shape={df.shape}")
    else:
        print("  [FAIL] 返回 None")

    print("\n" + "=" * 60)
    print("5. 测试 get_spot_price")
    print("=" * 60)
    df = await safe("spot", provider.get_spot_price(trade_date))
    if df is not None:
        print(f"  shape={df.shape}")
        cu_rows = df[df.iloc[:, 0].astype(str).str.contains("CU|铜")] if len(df) > 0 else df
        print(f"  铜相关行: {len(cu_rows)}")
    else:
        print("  [FAIL] 返回 None")

    print("\n" + "=" * 60)
    print("6. 测试 get_basis_history")
    print("=" * 60)
    df = await safe("basis", provider.get_basis_history("2026-01-01", trade_date, [underlying]))
    if df is not None:
        print(f"  shape={df.shape}")
    else:
        print("  [FAIL] 返回 None")

    print("\n" + "=" * 60)
    print("7. 测试 get_inventory (库存)")
    print("=" * 60)
    df = await safe("inv", provider.get_inventory(underlying))
    if df is not None:
        print(f"  shape={df.shape}")
    else:
        print("  [FAIL] 返回 None")

    print("\n" + "=" * 60)
    print("8. 测试 get_position_rank (持仓排名)")
    print("=" * 60)
    df = await safe("pos", provider.get_position_rank("SHFE", "20260715"))
    if df is not None:
        if isinstance(df, dict):
            for k, v in df.items():
                print(f"  {k}: {v.shape if hasattr(v,'shape') else type(v).__name__}")
        else:
            print(f"  shape={df.shape}")
    else:
        print("  [FAIL] 返回 None")

    print("\n" + "=" * 60)
    print("9. 测试 get_roll_yield (期限结构)")
    print("=" * 60)
    df = await safe("roll", provider.get_roll_yield("date", var=underlying, start_day="20260101", end_day="20260715"))
    if df is not None:
        print(f"  shape={df.shape}")
    else:
        print("  [FAIL] 返回 None")

    print("\n" + "=" * 60)
    print("10. 测试 get_futures_news")
    print("=" * 60)
    news = await safe("news", provider.get_futures_news("all", 10))
    if news:
        print(f"  {len(news)} 条")
        print(f"  第一条: {news[0].get('title','')[:60]}")
    else:
        print("  [FAIL] 返回空")

    print("\n" + "=" * 60)
    print("11. compute_all_features_from_provider (6 模块)")
    print("=" * 60)
    from tradingagents.features import compute_all_features_from_provider
    aggregated = await safe("features", compute_all_features_from_provider(provider, symbol, trade_date))
    if aggregated:
        features = aggregated.get("features", {})
        errors = aggregated.get("errors", {})
        print(f"  success={aggregated.get('success')}")
        if errors:
            print(f"  errors: {errors}")
        for mod in ["technical", "basis", "inventory", "positioning", "term_structure", "news_sentiment"]:
            q = features.get(mod, {}).get("quality", {}) if features.get(mod) else {}
            if q:
                print(f"  {mod}: rows={q.get('rows')}")
            elif mod in features:
                print(f"  {mod}: 存在但无 quality")
            else:
                print(f"  {mod}: 缺失")

    print("\n✅ 数据层检查完成")


if __name__ == "__main__":
    asyncio.run(main())