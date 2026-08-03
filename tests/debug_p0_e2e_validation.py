"""
debug_p0_e2e_validation.py — P0 真实 LLM 端到端验证脚本

目标：跑真实 LLM 端到端，提取 6 个节点的 validation_status，统计 Pydantic 校验通过率。

设计原则：
  - 复用 debug_commodity_e2e_full.py 的 propagate 调用模式
  - 5 个代表性标的 × 3 次同 seed 重复 = 15 次 propagate
  - 每个标的跑前 ~30 秒（features 计算），跑中 ~200 秒（10 次 LLM 调用）
  - 单次失败不中断，记录到 reports/p0_validation_failures.json
  - 汇总报告：reports/p0_validation_summary.json（含每节点通过率）

用法：
  python tests/debug_p0_e2e_validation.py [--symbol RB2510.SHF] [--rounds 1]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# 5 个 plan 指定品种 × 交易所 + 品种覆盖（主力连续代码,不带 YYMM 自动触发 provider 主力连续路径）
DEFAULT_SYMBOLS = [
    {"full_symbol": "RB.SHF", "variety_name": "螺纹钢", "exchange": "SHF",  "category": "black",       "quote_unit": "元/吨"},
    {"full_symbol": "CU.SHF", "variety_name": "铜",      "exchange": "SHF",  "category": "metal",       "quote_unit": "元/吨"},
    {"full_symbol": "AU.SHF", "variety_name": "黄金",    "exchange": "SHF",  "category": "precious",    "quote_unit": "元/克"},
    {"full_symbol": "M.DCE",  "variety_name": "豆粕",    "exchange": "DCE",  "category": "agricultural","quote_unit": "元/吨"},
    {"full_symbol": "Y.DCE",  "variety_name": "豆油",    "exchange": "DCE",  "category": "agricultural","quote_unit": "元/吨"},
]

# 6 个节点 schema 校验状态字段映射
NODE_STATUS_FIELDS = {
    "fundamental": "fundamentals_validation_status",
    "position":    "position_validation_status",
    "technical":   "technical_validation_status",
    "news":        "news_validation_status",
    "research_manager": "research_plan_validation_status",
    "investment_director": "cio_validation_status",
}


def extract_validation_status(final_state: Dict[str, Any]) -> Dict[str, str]:
    """从 final_state 提取 6 节点的 validation_status。"""
    out: Dict[str, str] = {}
    for node, field in NODE_STATUS_FIELDS.items():
        v = final_state.get(field)
        out[node] = v if v in {"passed", "failed", "legacy", "degraded"} else "unknown"
    return out


async def run_one_round(
    symbol_cfg: Dict[str, str],
    trade_date: str,
    round_idx: int,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """跑单次 commodity 端到端 propagate，返回单次结果记录。"""
    full_symbol = symbol_cfg["full_symbol"]
    start_ts = datetime.now()
    record: Dict[str, Any] = {
        "full_symbol": full_symbol,
        "variety_name": symbol_cfg.get("variety_name", ""),
        "round": round_idx,
        "trade_date": trade_date,
        "started_at": start_ts.isoformat(),
        "elapsed_seconds": 0.0,
        "ok": False,
        "error": None,
        "validation_status": {},
        "llm_calls": 0,
    }

    try:
        # ---- 1. Provider ----
        from tradingagents.dataflows.providers.commodity.akshare_futures import AkshareFuturesProvider
        provider = AkshareFuturesProvider()
        await provider.connect()
        if not provider.connected:
            record["error"] = "Provider connect failed"
            return record

        # ---- 2. Features ----
        from tradingagents.features import compute_all_features_from_provider
        aggregated = await compute_all_features_from_provider(provider, full_symbol, trade_date)
        features = aggregated.get("features", {}) or {}

        # ---- 3. News ----
        latest_news: List[Dict[str, Any]] = []
        try:
            latest_news = await provider.get_futures_news("all", 50) or []
        except Exception:  # noqa: BLE001
            latest_news = []

        # ---- 4. Graph ----
        from tradingagents.graph.commodity_graph import CommodityTradingAgentsGraph
        graph = CommodityTradingAgentsGraph(debug=False, config=config)

        # ---- 5. Propagate ----
        propagate_start = time.time()
        llm_call_count = {"n": 0}

        def progress(msg: str) -> None:
            # 简易 LLM 调用计数器（从消息里识别）
            if isinstance(msg, str) and ("LLM 调用" in msg or "LLM调用" in msg):
                llm_call_count["n"] += 1

        final_state, decision = graph.propagate(
            full_symbol=full_symbol,
            trade_date=trade_date,
            commodity_features=features,
            latest_news=latest_news,
            variety_name=symbol_cfg.get("variety_name", ""),
            exchange=symbol_cfg.get("exchange", ""),
            category=symbol_cfg.get("category", ""),
            quote_unit=symbol_cfg.get("quote_unit", ""),
            progress_callback=progress,
        )
        record["elapsed_seconds"] = round(time.time() - propagate_start, 1)
        record["llm_calls"] = llm_call_count["n"]

        # ---- 6. Extract ----
        record["validation_status"] = extract_validation_status(final_state)
        record["decision_action"] = decision.get("action", "N/A")
        record["ok"] = True

        await provider.disconnect()
    except Exception as e:  # noqa: BLE001
        record["error"] = f"{type(e).__name__}: {str(e)[:200]}"
        record["traceback"] = traceback.format_exc()[:500]

    record["total_elapsed_seconds"] = round((datetime.now() - start_ts).total_seconds(), 1)
    return record


def build_config() -> Dict[str, Any]:
    """构建真实 LLM config（DeepSeek 优先）。"""
    from tradingagents.default_config import DEFAULT_CONFIG
    config = DEFAULT_CONFIG.copy()

    if os.environ.get("DEEPSEEK_API_KEY"):
        config["llm_provider"] = "deepseek"
        # DeepSeek 文档：https://api.deepseek.com (OpenAI 兼容)，模型 deepseek-v4-flash/pro
        config["deep_think_llm"] = os.environ.get("DEEP_LLM", "deepseek-v4-flash")
        config["quick_think_llm"] = os.environ.get("QUICK_LLM", "deepseek-v4-flash")
    else:
        config["llm_provider"] = os.environ.get("LLM_PROVIDER", "openai")
        config["deep_think_llm"] = os.environ.get("DEEP_LLM", "gpt-4o")
        config["quick_think_llm"] = os.environ.get("QUICK_LLM", "gpt-4o-mini")
    return config


def aggregate(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """汇总每节点通过率。"""
    counters: Dict[str, Dict[str, int]] = {
        node: {"passed": 0, "failed": 0, "legacy": 0, "degraded": 0, "unknown": 0}
        for node in NODE_STATUS_FIELDS
    }
    success_count = 0
    error_count = 0
    elapsed_total = 0.0
    for r in records:
        if r["ok"]:
            success_count += 1
        else:
            error_count += 1
        elapsed_total += r.get("total_elapsed_seconds", 0.0)
        for node, status in (r.get("validation_status") or {}).items():
            if node in counters:
                counters[node].setdefault(status, 0)
                counters[node][status] += 1

    summary: Dict[str, Any] = {
        "total_runs": len(records),
        "successful_runs": success_count,
        "error_runs": error_count,
        "total_elapsed_seconds": round(elapsed_total, 1),
        "avg_elapsed_seconds": round(elapsed_total / max(1, len(records)), 1),
        "node_pass_rates": {},
        "node_counters": counters,
        "target_pass_rate": 0.80,
        "meets_target": {},
    }
    for node, ctr in counters.items():
        total = sum(ctr.values())
        passed = ctr.get("passed", 0)
        rate = passed / total if total > 0 else 0.0
        summary["node_pass_rates"][node] = round(rate, 3)
        summary["meets_target"][node] = rate >= 0.80
    return summary


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default=None, help="单标的测试（如 RB2510.SHF）")
    parser.add_argument("--symbols", default=None,
                        help="多标的逗号分隔（如 RB2510.SHF,CU2507.SHF,M2509.DCE）")
    parser.add_argument("--rounds", type=int, default=3, help="每个标的重复次数（默认 3）")
    parser.add_argument("--trade-date", default=None, help="交易日期（默认今天）")
    args = parser.parse_args()

    trade_date = args.trade_date or datetime.now().strftime("%Y-%m-%d")
    config = build_config()
    print(f"[P0 E2E] LLM provider={config['llm_provider']}, "
          f"deep={config['deep_think_llm']}, quick={config['quick_think_llm']}, "
          f"date={trade_date}, rounds={args.rounds}")

    # 选择标的
    symbols: List[Dict[str, str]]
    if args.symbols:
        wanted = set(s.strip() for s in args.symbols.split(",") if s.strip())
        symbols = [s for s in DEFAULT_SYMBOLS if s["full_symbol"] in wanted]
        # 任意不在表中的标的也接受（用元数据兜底）
        known = {s["full_symbol"] for s in symbols}
        for w in wanted - known:
            symbols.append({"full_symbol": w, "variety_name": "", "exchange": "", "category": "", "quote_unit": ""})
    elif args.symbol:
        symbols = [s for s in DEFAULT_SYMBOLS if s["full_symbol"] == args.symbol]
        if not symbols:
            symbols = [{"full_symbol": args.symbol, "variety_name": "", "exchange": "", "category": "", "quote_unit": ""}]
    else:
        symbols = DEFAULT_SYMBOLS

    # 跑
    all_records: List[Dict[str, Any]] = []
    for sym in symbols:
        for r in range(args.rounds):
            print(f"\n{'='*70}\n[{sym['full_symbol']}] round {r+1}/{args.rounds}\n{'='*70}")
            rec = await run_one_round(sym, trade_date, r + 1, config)
            all_records.append(rec)
            if rec["ok"]:
                vs = rec["validation_status"]
                vs_str = ", ".join(f"{k}={v}" for k, v in vs.items())
                print(f"  ✅ OK ({rec['elapsed_seconds']}s, llm_calls~{rec['llm_calls']}) | {vs_str}")
            else:
                print(f"  ❌ FAIL: {rec['error']}")

    # 汇总
    summary = aggregate(all_records)
    summary["records"] = all_records
    summary["config_used"] = {
        "llm_provider": config["llm_provider"],
        "deep_think_llm": config["deep_think_llm"],
        "quick_think_llm": config["quick_think_llm"],
        "trade_date": trade_date,
        "feature_flag_schema_validation": os.environ.get("FEATURE_COMMODITY_SCHEMA_VALIDATION", "true"),
    }

    # 保存
    report_dir = "reports"
    os.makedirs(report_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(report_dir, f"p0_validation_summary_{timestamp}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n📊 汇总报告: {out_path}")

    # 控制台打印通过率
    print(f"\n{'='*70}\n📈 各节点 Pydantic 校验通过率（目标 ≥80%）\n{'='*70}")
    for node, rate in summary["node_pass_rates"].items():
        ctr = summary["node_counters"][node]
        meets = "✅" if summary["meets_target"][node] else "⚠️"
        print(f"  {meets} {node:>20s}: {rate*100:5.1f}% "
              f"(passed={ctr.get('passed',0)}, failed={ctr.get('failed',0)}, "
              f"legacy={ctr.get('legacy',0)}, degraded={ctr.get('degraded',0)})")

    if summary["error_runs"]:
        print(f"\n⚠️ 失败次数: {summary['error_runs']}/{summary['total_runs']}")


if __name__ == "__main__":
    asyncio.run(main())
