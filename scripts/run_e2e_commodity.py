"""
run_e2e_commodity.py — 投研总监改造端到端实测

用法:
  python scripts/run_e2e_commodity.py

通过真实 AKShare 数据 + DeepSeek LLM 运行完整决策链:
  L1(4) → L2 推理分析师 → 量化检查器(纯规则) → 投研总监(LLM) → END

依赖:
  - .env 中 DEEPSEEK_API_KEY 已配置
  - AKShare 可访问(国内网络)
  - uv pip install -e . 已安装
"""
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# 项目根加入 sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

os.environ["USE_MONGODB_STORAGE"] = "false"


def main():
    symbol = "RB.SHF"  # 螺纹钢主力连续(自动解析)
    trade_date = "2026-07-17"
    variety_name = "螺纹钢"
    exchange = "SHF"
    category = "black"
    quote_unit = "元/吨"

    print(f"{'='*60}")
    print(f"投研总监改造端到端实测")
    print(f"{'='*60}")
    print(f"标的: {symbol} ({variety_name})")
    print(f"交易日期: {trade_date}")
    print(f"开始时间: {datetime.now().strftime('%H:%M:%S')}")
    print()

    # ---- Step 1: 初始化 Provider ----
    print("[1/5] 初始化 AKShare Provider ... ", end="", flush=True)
    from tradingagents.dataflows.providers.commodity.akshare_futures import (
        AkshareFuturesProvider,
    )

    provider = AkshareFuturesProvider()
    provider.connect()
    print("OK")

    # ---- Step 2: 自动拉取 Features + 新闻 ----
    print("[2/5] 拉取 Features + 新闻 ... ", end="", flush=True)
    from tradingagents.features import compute_all_features_from_provider

    aggregated = asyncio.run(
        compute_all_features_from_provider(provider, symbol, trade_date)
    )
    commodity_features = aggregated.get("features", {}) or {}
    feature_modules = list(commodity_features.keys())
    print(f"{len(feature_modules)} 模块: {feature_modules}")

    latest_news = asyncio.run(provider.get_futures_news("all", 50)) or []
    print(f"新闻: {len(latest_news)} 条")

    # 打印 features 各模块的 quality
    for mod in ["technical", "basis", "inventory", "positioning", "term_structure", "news_sentiment"]:
        q = commodity_features.get(mod, {}).get("quality", {})
        if q:
            print(f"  {mod}: rows={q.get('rows')}, coverage={q.get('coverage')}, fresh={q.get('data_freshness_days')}d")
        else:
            print(f"  {mod}: (无数据)")

    # ---- Step 3: 构建 Graph 配置 ----
    print("[3/5] 初始化 CommodityTradingAgentsGraph ... ", end="", flush=True)
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

    from tradingagents.graph.commodity_graph import CommodityTradingAgentsGraph

    graph = CommodityTradingAgentsGraph(debug=False, config=config)
    print("OK")

    # ---- Step 4: 运行传播 ----
    print("[4/5] 运行全链路分析 (4 L1 → L2 推理 → 检查器 → 投研总监) ...")
    print(f"    预计耗时: 2-5 分钟 (6 次 LLM 调用)")
    print()

    completed_nodes = []
    t0 = time.time()

    def progress_callback(msg):
        elapsed = time.time() - t0
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

    elapsed_total = time.time() - t0
    print(f"\n  总耗时: {elapsed_total:.1f}s")
    print(f"  执行节点: {' → '.join(completed_nodes)}")

    # ---- Step 5: 验证输出 ----
    print("\n[5/5] 验证输出 ...")

    # 5a. 量化检查器
    risk_assessment = final_state.get("risk_assessment", {})
    has_quant = bool(risk_assessment)
    print(f"  risk_assessment: {'✓' if has_quant else '✗'} (composite_level={risk_assessment.get('composite_risk_level', 'N/A')})")

    if risk_assessment:
        dims = risk_assessment.get("dimensions", {})
        for name in ["volatility", "basis", "crowding", "inventory", "term_structure"]:
            d = dims.get(name, {})
            lvl = d.get("level", "?")
            val = d.get("value", "?")
            print(f"    {name}: level=R{lvl}, value={val}")
        flags = risk_assessment.get("flags", [])
        if flags:
            print(f"    硬拦截 flags ({len(flags)}):")
            for f in flags:
                print(f"      - [{f.get('severity')}] {f.get('name')}: {f.get('flag')}")

    # 5b. 风险评估卡
    risk_card = final_state.get("risk_card", {})
    has_card = bool(risk_card)
    card_summary = risk_card.get("风险裁定", {}).get("总体风险等级", "N/A") if risk_card else "N/A"
    print(f"  risk_card: {'✓' if has_card else '✗'} (等级={card_summary})")

    # 5c. 投研备忘录
    investment_memo = final_state.get("investment_memo", {})
    has_memo = bool(investment_memo)
    print(f"  investment_memo: {'✓' if has_memo else '✗'}")

    if investment_memo:
        conclusion = investment_memo.get("投研结论", {})
        direction = conclusion.get("方向倾向", "?")
        confidence = conclusion.get("置信度", "?")
        print(f"    结论: {direction} (置信度={confidence})")

    # 5d. final_decision + _extract_decision 兼容性
    final_decision_text = final_state.get("final_decision", "")
    has_fd = bool(final_decision_text and len(final_decision_text) > 20)
    print(f"  final_decision: {'✓' if has_fd else '✗'} ({len(final_decision_text)} 字符)")

    extract_result = decision  # 来自 _extract_decision()
    print(f"  _extract_decision():")
    print(f"    action={extract_result.get('action')}")
    print(f"    confidence={extract_result.get('confidence')}")

    if has_fd:
        print(f"\n--- final_decision 预览 ---")
        print(final_decision_text[:1500])
        if len(final_decision_text) > 1500:
            print(f"... (共 {len(final_decision_text)} 字符)")
        print("---")

    # ---- 汇总 ----
    print(f"\n{'='*60}")
    print(f"实测汇总")
    print(f"{'='*60}")

    status = "PASS" if (has_quant and has_fd) else "FAIL"
    llm_calls = len(completed_nodes) - 0  # 6 次: 4 L1 + 1 L2 + 1 ID

    metrics = {
        "status": status,
        "symbol": symbol,
        "trade_date": trade_date,
        "elapsed_seconds": round(elapsed_total, 1),
        "llm_calls_estimate": 6,
        "completed_nodes": completed_nodes,
        "risk_level": risk_assessment.get("composite_risk_level", "N/A"),
        "decision_action": extract_result.get("action", "N/A"),
        "decision_confidence": extract_result.get("confidence", "N/A"),
        "has_investment_memo": has_memo,
        "has_risk_card": has_card,
        "feature_modules": feature_modules,
        "news_count": len(latest_news),
        "timestamp": datetime.now().isoformat(),
    }
    print(f"\n状态: {status}")
    print(f"耗时: {elapsed_total:.1f}s")
    print(f"LLM 调用: 4 L1 + 1 L2 + 1 投研总监 = 6 次")
    print(f"决策: {extract_result.get('action')} @ {extract_result.get('confidence')}")
    print()

    # 写到结果文件
    result_path = PROJECT_ROOT / "results" / f"e2e_commodity_id_{symbol.replace('.', '_')}.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
    print(f"结果已保存: {result_path}")

    if status == "FAIL":
        sys.exit(1)


if __name__ == "__main__":
    main()
