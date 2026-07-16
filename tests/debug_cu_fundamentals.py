"""
测试 CU (铜) 产业分析，输出产业分析报告（结构化和 Markdown 格式）。

用法:
    python tests/debug_cu_fundamentals.py

依赖:
    - .env 中 DEEPSEEK_API_KEY 已配置
    - 网络连接（用于 AKShare 数据 + DeepSeek API）
"""
import asyncio
import json
import os
import sys
from datetime import datetime

# Windows GBK 终端兼容
os.environ["PYTHONIOENCODING"] = "utf-8"


async def main():
    trade_date = datetime.now().strftime("%Y-%m-%d")
    full_symbol = "CU.SHF"  # CU 铜,主力连续

    print("=" * 60)
    print("产业分析测试: %s @ %s" % (full_symbol, trade_date))
    print("=" * 60)
    print()

    # 1. 初始化 Provider
    print("[1/5] 初始化 AkshareFuturesProvider...")
    from tradingagents.dataflows.providers.commodity.akshare_futures import (
        AkshareFuturesProvider,
    )
    provider = AkshareFuturesProvider()
    await provider.connect()
    print("  Provider 连接成功\n")

    # 2. 计算 Features
    print("[2/5] 计算特征层 (6 模块)...")
    from tradingagents.features import compute_all_features_from_provider
    aggregated = await compute_all_features_from_provider(provider, full_symbol, trade_date)
    features = aggregated.get("features", {}) or {}
    success = aggregated.get("success")
    modules = list(features.keys())
    print("  Features 计算完成: success=%s, modules=%s\n" % (success, modules))

    # 3. 获取新闻
    print("[3/5] 获取期货新闻...")
    try:
        latest_news = await provider.get_futures_news("all", 50) or []
    except Exception as e:
        print("  新闻获取失败: %s" % e)
        latest_news = []
    print("  获取 %d 条新闻\n" % len(latest_news))

    # 4. 打印特征摘要
    print("=" * 60)
    print("特征层摘要")
    print("=" * 60)

    feature_blocks = {
        "technical": "技术分析",
        "basis": "基差分析",
        "inventory": "库存分析",
        "positioning": "持仓分析",
        "term_structure": "期限结构",
        "news_sentiment": "新闻情感",
    }
    for key, cn_name in feature_blocks.items():
        block = features.get(key)
        if block and isinstance(block, dict):
            signals = block.get("signals", [])
            quality = block.get("quality", {})
            rows = quality.get("rows", 0)
            latest = block.get("latest", {})
            print("\n  [%s] (%s)" % (cn_name, key))
            print("     rows=%d, signals=%s" % (rows, signals))
            for k, v in latest.items():
                if v is not None:
                    print("     %s=%s" % (k, v))
        else:
            print("\n  [%s] (%s): 无数据\n" % (cn_name, key))

    # 5. 调用基本面分析师
    print("\n%s" % ("=" * 60))
    print("[4/5] 初始化 LLM + 基本面分析师...")
    print("%s\n" % ("=" * 60))

    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(
        model="deepseek-chat",
        openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
        openai_api_base=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        temperature=0.3,
        max_tokens=4096,
    )

    from tradingagents.agents.analysts.commodity.fundamental_analyst import (
        create_fundamental_analyst,
    )
    analyst_node = create_fundamental_analyst(llm)

    # 构造 state
    from tradingagents.utils.commodity_utils import CommodityUtils
    underlying = CommodityUtils.get_underlying_symbol(full_symbol) or "CU"
    variety_name = "铜"
    exchange = "SHFE"

    from tradingagents.dataflows.providers.commodity.commodity_metadata import (
        get_variety,
    )
    vinfo = get_variety(underlying, exchange)
    if vinfo:
        variety_name = vinfo.get("name_cn", "铜")
        exchange = vinfo.get("exchange", "SHFE")

    state = {
        "full_symbol": full_symbol,
        "trade_date": trade_date,
        "variety_name": variety_name,
        "exchange": exchange,
        "category": "metal",
        "quote_unit": "元/吨",
        "commodity_features": features,
        "latest_news": latest_news,
        "messages": [],
        "asset_type": "commodity",
        "company_of_interest": full_symbol,
    }

    print("   品种: %s (%s)" % (variety_name, underlying))
    print("   交易所: %s" % exchange)
    print("   分析日期: %s" % trade_date)
    print("   特征模块数: %d" % len(features))
    print("   新闻条数: %d" % len(latest_news))
    print()

    # 调用分析师节点
    print("[5/5] 调用基本面分析师 LLM...")
    print("   等待 LLM 响应（约 15-30 秒）...\n")
    try:
        result = analyst_node(state)
    except Exception as e:
        print("   分析师调用失败: %s" % e)
        import traceback
        traceback.print_exc()
        return

    # 6. 输出结果
    print("=" * 60)
    print("基本面分析结果")
    print("=" * 60)
    print()

    # Markdown 报告
    report_md = result.get("fundamentals_report", "")
    if report_md:
        print("--- Markdown 报告 ---")
        print(report_md[:2000])
        if len(report_md) > 2000:
            print("\n... (截断, 共 %d 字符)" % len(report_md))
        print()

    # 结构化输出
    structured = result.get("fundamentals_structured", {})
    if structured:
        print("--- 结构化输出 (JSON) ---")
        print(json.dumps(structured, ensure_ascii=False, indent=2))
        print()

    # 报告长度
    print("报告长度: %d 字符" % len(report_md))
    print("结构化键: %s" % (list(structured.keys()) if structured else "空"))

    # 验证关键字段
    if structured:
        val = structured.get("valuation", {})
        drv = structured.get("drive", {})
        cns = structured.get("consistency", {})
        print("\n估值: %s / %s" % (val.get("level", "N/A"), val.get("safety_margin", "N/A")))
        print("驱动: %s (%s)" % (drv.get("direction", "N/A"), drv.get("strength", "N/A")))
        print("一致性: %s / 置信度: %s" % (cns.get("alignment", "N/A"), cns.get("confidence", "N/A")))

    print("\n%s" % ("=" * 60))
    print("测试完成")
    print("%s" % ("=" * 60))


if __name__ == "__main__":
    asyncio.run(main())
