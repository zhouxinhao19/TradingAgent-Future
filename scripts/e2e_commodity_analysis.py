"""
E2E 全流程测试 — 真实数据 + DeepSeek API

直接调用 CommodityTradingAgentsGraph，不经过 FastAPI/MongoDB/Redis，
快速验证分支 feat/agent-layer-improvements 上的 AI Agent 改造是否有效。

用法:
    python scripts/e2e_commodity_analysis.py [--symbol RB2501.SHF] [--date 2026-07-17] [--debug]
"""

# ---- Windows GBK 终端兼容 ----
import io
import sys
if sys.stdout.encoding and sys.stdout.encoding.lower() in ("gbk", "gb2312", "gb18030"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import argparse
import json
import os
import sys
import time
from pathlib import Path

# 确保项目根在 sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# ---- 加载 .env ----
from dotenv import load_dotenv
dotenv_path = PROJECT_ROOT / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)
    print(f"[INFO] 已加载环境变量: {dotenv_path}")

# ---- 解析参数 ----
parser = argparse.ArgumentParser(description="Feat/agent-layer-improvements E2E test")
parser.add_argument("--symbol", default="RB2507.SHF", help="合约代码(默认 RB2507.SHF)")
parser.add_argument("--date", default="2026-07-17", help="交易日期(默认 2026-07-17)")
parser.add_argument("--variety", default="螺纹钢", help="品种中文名(默认 螺纹钢)")
parser.add_argument("--exchange", default="SHF", help="交易所(默认 SHF)")
parser.add_argument("--category", default="black_metals", help="行业分类(默认 black_metals)")
parser.add_argument("--quote-unit", default="元/吨", help="报价单位(默认 元/吨)")
parser.add_argument("--debug", action="store_true", help="启用 debug 模式")
args = parser.parse_args()

OUTPUT_DIR = PROJECT_ROOT / "data" / "e2e_test_output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print("=" * 80)
print("[E2E] 全流程测试 -- feat/agent-layer-improvements")
print(f"  合约:     {args.symbol}")
print(f"  日期:     {args.date}")
print(f"  品种:     {args.variety}")
print(f"  交易所:   {args.exchange}")
print("=" * 80)

# ---- Step 1: 检查环境变量 ----
DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY")
if not DEEPSEEK_KEY:
    print("[FAIL] 需要设置 DEEPSEEK_API_KEY 环境变量")
    sys.exit(1)
print(f"[OK] DeepSeek API Key: {DEEPSEEK_KEY[:8]}...")

# ---- Step 2: 连接 provider 并计算 features ----
print("\n[Step 2] 连接 AKShare provider + 计算 6 模块 features ...")
t0 = time.time()

from tradingagents.dataflows.providers.commodity.akshare_futures import AkshareFuturesProvider
from tradingagents.features import compute_all_features_from_provider

import asyncio

async def load_data():
    provider = AkshareFuturesProvider()
    connected = await provider.connect()
    if not connected:
        print("  [WARN] provider.connect() 返回 False, 继续尝试...")

    aggregated = await compute_all_features_from_provider(
        provider, args.symbol, args.date
    )
    success = aggregated.get("success", False)
    features = aggregated.get("features", {})
    print(f"  features success={success}, modules={list(features.keys()) if features else '空'}")

    # 加载新闻
    news = []
    try:
        news = await provider.get_futures_news("all", 100) or []
        print(f"  新闻加载: {len(news)} 条")
    except Exception as e:
        print(f"  [WARN] 新闻加载失败: {e}")

    # provider 无 close 方法, 用 del 回收
    return features, news

features_dict, latest_news = asyncio.run(load_data())
print(f"[OK] Step 2 耗时: {time.time() - t0:.1f}s")
print(f"  features 包含模块: {list(features_dict.keys())}")

# ---- Step 3: 初始化 CommodityTradingAgentsGraph ----
print("\n[Step 3] 初始化 CommodityTradingAgentsGraph (DeepSeek) ...")
t0 = time.time()

# 构建 config（与 app/routers/commodity/analysis.py _build_config 保持一致）
config = {
    "llm_provider": "deepseek",
    "deep_think_llm": "deepseek-chat",
    "quick_think_llm": "deepseek-chat",
    "max_debate_rounds": 0,  # 单轮分析，无需辩论
    "max_risk_discuss_rounds": 0,
    "online_tools": False,
    "memory_enabled": False,
    "project_dir": str(PROJECT_ROOT),
    "backend_url": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
}

from tradingagents.graph.commodity_graph import CommodityTradingAgentsGraph

graph = CommodityTradingAgentsGraph(debug=args.debug, config=config)

# 验证 LLM 不为 None
if graph.quick_thinking_llm is None:
    print("[FAIL] quick_thinking_llm 为 None -- _wrap_llm_with_retry 返回值缺失")
    sys.exit(1)
if graph.deep_thinking_llm is None:
    print("[FAIL] deep_thinking_llm 为 None -- _wrap_llm_with_retry 返回值缺失")
    sys.exit(1)
print(f"[OK] LLM 初始化成功: quick={type(graph.quick_thinking_llm).__name__}, deep={type(graph.deep_thinking_llm).__name__}")
print(f"[OK] Step 3 耗时: {time.time() - t0:.1f}s")

# ---- Step 4: 运行 propagate ----
print("\n[Step 4] 运行 propagate (全链路: 4 L1 -> 推理分析师 -> 投研总监) ...")
t0 = time.time()

def progress_callback(msg: str):
    print(f"  [Progress] {msg}")

final_state, decision = graph.propagate(
    full_symbol=args.symbol,
    trade_date=args.date,
    commodity_features=features_dict,
    latest_news=latest_news,
    variety_name=args.variety,
    exchange=args.exchange,
    category=args.category,
    quote_unit=args.quote_unit,
    progress_callback=progress_callback,
    provider=None,
    auto_features=False,
)

elapsed = time.time() - t0
print(f"\n[OK] 全链路耗时: {elapsed:.1f}s ({elapsed/60:.1f}min)")

# ---- Step 5: 验证输出 ----
print("\n[Step 5] 验证输出...")
checks = []

# 5a: L1 分析师报告
for field, label in [("market_report", "技术分析师"), ("fundamentals_report", "产业分析师"),
                       ("position_report", "持仓分析师"), ("news_report", "新闻分析师")]:
    val = final_state.get(field, "")
    ok = bool(val and len(str(val)) > 50)
    checks.append((label, ok, len(str(val))))
    print(f"  {label}: {'[OK]' if ok else '[FAIL]'} ({len(str(val))} 字符)")

# 5b: L2 推理分析师
inv_plan = final_state.get("investment_plan", "")
ok = bool(inv_plan and len(str(inv_plan)) > 100)
checks.append(("推理分析师(investment_plan)", ok, len(str(inv_plan))))
print(f"  推理分析师(investment_plan): {'[OK]' if ok else '[FAIL]'} ({len(str(inv_plan))} 字符)")

# 5c: L4 投研总监(CIO)
final_decision = final_state.get("final_decision", "")
ok = bool(final_decision and len(str(final_decision)) > 50)
checks.append(("投研总监(final_decision)", ok, len(str(final_decision))))
print(f"  投研总监(final_decision): {'[OK]' if ok else '[FAIL]'} ({len(str(final_decision))} 字符)")

# 5d: decision 摘要
print(f"  决策摘要: {decision}")
print(f"  方向={decision.get('action')}, 置信度={decision.get('confidence')}")

# 5e: analyst_registry
registry = final_state.get("analyst_registry", {})
ok = len(registry) >= 3
checks.append(("analyst_registry(>=3条目)", ok, len(registry)))
print(f"  analyst_registry: {'[OK]' if ok else '[FAIL]'} ({len(registry)} 条)")

# ---- Step 6: 保存报告 ----
print(f"\n[Step 6] 保存报告...")
timestamp = time.strftime("%Y%m%d_%H%M%S")
report = {
    "full_symbol": args.symbol,
    "trade_date": args.date,
    "variety_name": args.variety,
    "exchange": args.exchange,
    "category": args.category,
    "quote_unit": args.quote_unit,
    "total_time_s": round(elapsed, 1),
    "total_time_min": round(elapsed / 60, 1),
    "decision": decision,
    "llm_config": {
        "provider": "deepseek",
        "model": "deepseek-chat",
    },
    "feature_modules": list(features_dict.keys()),
    "news_count": len(latest_news),
    # 分析师输出
    "market_report": final_state.get("market_report", ""),
    "fundamentals_report": final_state.get("fundamentals_report", ""),
    "sentiment_report": final_state.get("sentiment_report", ""),
    "position_report": final_state.get("position_report", ""),
    "news_report": final_state.get("news_report", ""),
    # 推理分析师输出
    "investment_plan": inv_plan,
    # CIO 决策
    "final_decision": final_decision,
    "risk_assessment": final_state.get("risk_assessment", ""),
    # 证据链
    "evidence_chain": final_state.get("evidence_chain", {}),
    "analyst_registry": registry,
    # 检查点
    "checks": {label: "PASS" if ok else "FAIL" for label, ok, _ in checks},
}

report_path = OUTPUT_DIR / f"e2e_{args.symbol}_{timestamp}.json"
with open(report_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2, default=str)
print(f"[OK] 报告已保存: {report_path}")

# ---- Step 7: 结果汇总 ----
print("\n" + "=" * 80)
print("[E2E] 测试汇总")
print("=" * 80)
all_pass = True
for label, ok, detail in checks:
    status = "[OK] PASS" if ok else "[FAIL] FAIL"
    all_pass = all_pass and ok
    print(f"  {status} | {label} ({detail})")

if all_pass:
    print(f"\n[PASS] 全链路测试通过!")
else:
    print(f"\n[FAIL] 存在失败的检查项")
print(f"  总耗时: {elapsed:.1f}s ({elapsed/60:.1f}min)")
print(f"  报告: {report_path}")
print("=" * 80)
