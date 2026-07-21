"""
debug_commodity_e2e_full.py — Commodity 全链路端到端测试

使用真实 AKShare 数据 + DeepSeek LLM 跑通决策链：
  Custom Data → 4 L1 → Bull → Bear → RM → ID

输出:
  - 控制台打印各节点进度
  - reports/ 目录保存完整 JSON 报告

用法:
  python tests/debug_commodity_e2e_full.py
"""
import asyncio
import json
import os
import sys
from datetime import datetime

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main():
    trade_date = datetime.now().strftime("%Y-%m-%d")
    full_symbol = "CU.SHF"  # 铜主力连续
    variety_name = "铜"
    exchange = "SHF"
    category = "metal"
    quote_unit = "元/吨"

    print("=" * 70)
    print(f"[Commodity E2E] {full_symbol} @ {trade_date}")
    print("=" * 70)

    # ---- Step 1: 初始化 Provider ----
    print("\n[1/6] 初始化 AkshareFuturesProvider...")
    from tradingagents.dataflows.providers.commodity.akshare_futures import (
        AkshareFuturesProvider,
    )
    provider = AkshareFuturesProvider()
    await provider.connect()
    if not provider.connected:
        print("❌ Provider 连接失败")
        return
    print("✅ Provider 连接成功")

    # ---- Step 2: 计算 Features ----
    print("\n[2/6] 计算特征层 (6 基础模块 + 3 衍生模块)...")
    from tradingagents.features import compute_all_features_from_provider

    aggregated = await compute_all_features_from_provider(provider, full_symbol, trade_date)
    features = aggregated.get("features", {}) or {}
    success = aggregated.get("success")
    modules = list(features.keys())
    print(f"  ✅ success={success}, modules({len(modules)}): {modules}")
    for key in modules:
        blk = features.get(key, {})
        if isinstance(blk, dict):
            q = blk.get("quality", {})
            sigs = blk.get("signals", [])
            rows = q.get("rows", 0)
            print(f"     {key}: rows={rows}, signals={len(sigs)}")

    # ---- Step 3: 获取新闻 ----
    print("\n[3/6] 获取期货新闻...")
    try:
        latest_news = await provider.get_futures_news("all", 50) or []
    except Exception as e:
        print(f"  ⚠️ 新闻获取失败: {e}")
        latest_news = []
    print(f"  ✅ {len(latest_news)} 条新闻")

    # ---- Step 4: 初始化 Graph ----
    print("\n[4/6] 初始化 CommodityTradingAgentsGraph...")
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.commodity_graph import CommodityTradingAgentsGraph

    config = DEFAULT_CONFIG.copy()

    # 从 .env 读取 provider 配置
    import os
    if "DEEPSEEK_API_KEY" in os.environ:
        config["llm_provider"] = "deepseek"
        config["deep_think_llm"] = "deepseek-chat"
        config["quick_think_llm"] = "deepseek-chat"
    else:
        config["llm_provider"] = os.environ.get("LLM_PROVIDER", "openai")
        config["deep_think_llm"] = os.environ.get("DEEP_LLM", "gpt-4o")
        config["quick_think_llm"] = os.environ.get("QUICK_LLM", "gpt-4o-mini")

    print(f"  LLM provider={config['llm_provider']}, deep={config['deep_think_llm']}, quick={config['quick_think_llm']}")

    graph = CommodityTradingAgentsGraph(debug=False, config=config)
    print("  ✅ Graph 初始化完成")

    # ---- Step 5: 运行 propagate（真实 LLM） ----
    print("\n[5/6] 运行 propagate（调用 ~10 次 LLM）...")
    start_ts = datetime.now()

    # 进度回调
    last_msg = ""
    def progress(msg):
        nonlocal last_msg
        if msg != last_msg:
            print(f"  → {msg}")
            last_msg = msg

    final_state, decision = graph.propagate(
        full_symbol=full_symbol,
        trade_date=trade_date,
        commodity_features=features,
        latest_news=latest_news,
        variety_name=variety_name,
        exchange=exchange,
        category=category,
        quote_unit=quote_unit,
        progress_callback=progress,
    )
    elapsed = (datetime.now() - start_ts).total_seconds()
    print(f"\n  ✅ propagate 完成 ({elapsed:.1f}s)")

    # ---- Step 6: 输出结果 ----
    print("\n[6/6] 提取决策结果...")

    # 决策摘要
    print("\n" + "=" * 70)
    print("📊 决策摘要")
    print("=" * 70)
    print(f"  Action:     {decision.get('action', 'N/A')}")
    print(f"  Confidence: {decision.get('confidence', 'N/A')}")
    print(f"  Risk Tier:  {decision.get('risk_tier', 'N/A')}")
    print(f"  Allowed:    {decision.get('allowed_strategies', [])}")
    print(f"  Forbidden:  {decision.get('forbidden_strategies', [])}")
    print(f"  Core:       {decision.get('core_narrative', '')[:120]}")

    # 证据链摘要
    evidence = final_state.get("evidence_chain", {})
    layers = evidence.get("layers", {})
    l1 = layers.get("L1", [])
    print(f"\n  L1 分析师 ({len(l1)}):")
    for entry in l1:
        print(f"    {entry.get('name','?'):>8} | {entry.get('direction','?'):>8} | "
              f"conf={entry.get('confidence',0):.2f} | {entry.get('status','?'):>8} | "
              f"{entry.get('summary','')[:60]}")

    # SafetyOverride 审计
    risk_card = final_state.get("risk_card", {}) or {}
    override = risk_card.get("safety_override", {}) or {}
    if override.get("executed"):
        print(f"\n  🔒 SafetyOverride:")
        print(f"      input:    {override.get('original_llm_direction')} / {override.get('original_llm_confidence')}")
        print(f"      output:   {override.get('overridden_action')} / {override.get('overridden_confidence')}")
        print(f"      rules:    {override.get('override_rules_triggered', [])}")

    # Research Manager 结构
    inv_plan = final_state.get("investment_plan", "")
    if inv_plan:
        try:
            parsed = json.loads(inv_plan)
            print(f"\n  📋 推理分析师(RM):")
            print(f"      估值矩阵: {str(parsed.get('估值驱动矩阵', {}))[:80]}")
            print(f"      多空对照: {str(parsed.get('多空对照表', {}))[:80]}")
            print(f"      情景推演: {str(parsed.get('三种情景推演', {}))[:80]}")
        except json.JSONDecodeError:
            print(f"\n  📋 RM 输出: {inv_plan[:100]}...")

    # ---- 保存报告 ----
    report_dir = "reports"
    os.makedirs(report_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(report_dir, f"commodity_e2e_{full_symbol}_{timestamp}.json")

    # 保存关键字段（避免保存整个 state 过大）
    snapshot = {
        "timestamp": timestamp,
        "full_symbol": full_symbol,
        "trade_date": trade_date,
        "elapsed_seconds": round(elapsed, 1),
        "config": config,
        "decision": decision,
        "evidence_summary": {
            "symbol": evidence.get("summary", {}),
            "l1_count": len(l1),
        },
        "safety_override": {
            k: v for k, v in override.items()
            if not isinstance(v, (dict, list)) or k in ("override_rules_triggered", "allowed_strategies", "forbidden_strategies", "r5_dimensions")
        } if override else {},
        "research_brief_preview": (final_state.get("research_brief", "") or "")[:500],
        "bull_history_preview": (final_state.get("investment_debate_state", {}).get("bull_history", "") or "")[:300],
        "bear_history_preview": (final_state.get("investment_debate_state", {}).get("bear_history", "") or "")[:300],
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    print(f"\n  💾 报告已保存: {report_path}")

    # 关闭 provider
    await provider.disconnect()
    print("\n✅ 端到端测试完成")


if __name__ == "__main__":
    asyncio.run(main())
