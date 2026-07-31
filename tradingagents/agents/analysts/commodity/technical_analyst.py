"""
technical_analyst.py — 商品期货技术分析师节点 (Phase 3b-ii + P0 schema validation 决策)

⚠️ P0 决策:技术分析师输出是 Markdown 文本(report_md = content),不接入 Pydantic 校验。

原因：
  1. 技术分析师 LLM 输出是连续 Markdown（含表格/列表），不是结构化 JSON
  2. Pydantic schema 校验 Markdown 几乎 100% 失败（缺必填字段）
  3. 校验失败时降级 raw markdown 等于没校验，反而增加日志噪音
  4. 现有 direction 由 features 层 combined.get("direction") 兜底（line 448），已稳定

如果未来 LLM 在 Markdown 末尾追加结构化 JSON 块，可启用 TechnicalNodeOutput 校验。
（参考 TechnicalNodeOutput schema + parse_and_validate 接入模式）

输入:state['commodity_features']['technical'] (由 3b-i features 层算好)
输出:state['market_report'] = Markdown 技术分析报告 (复用现有字段名,决策链节点零改动)

与 stock market_analyst 区别:
  - 不依赖 toolkit(features 层已 all-in-one 算完)
  - 不调工具,纯文本生成
  - 不需要 GoogleToolCallHandler(无 tool_calls)
  - LLM 调用失败时,降级为 features snapshot 直拼 Markdown(永不抛错)

输出字段约定:
  - state["market_report"]:Markdown 字符串(决策链节点读取)
  - state["messages"]:List,追加 AIMessage
  - state["market_tool_call_count"]:int,Phase 3a 沿用字段,标记未调工具
"""
from __future__ import annotations

from typing import Any, Dict, List

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import AIMessage

from tradingagents.utils.logging_init import get_logger

from ._base import (
    build_custom_data_context,
    empty_report,
    extract_first_sentence,
    get_full_symbol,
    inject_analyst_id,
    load_features,
    make_analyst_id,
    make_conclusion_id,
    make_registry_entry,
    quality_gate,
    truncate_snapshot,
)

logger = get_logger("default")

# 合约分析策略(主力连续)
MAIN_CONTINUOUS_STRATEGY = """你是基于品种级技术分析的期货分析师。技术分析遵循以下合约层级:

1. **主力连续合约(Primary)**: 持仓量最大的合约的拼接序列。
   所有技术指标(均线、MACD、RSI、BOLL)基于此计算。这是技术分析的主战场。

2. **指数合约(Auxiliary)**: 所有合约持仓量加权平均的连续序列。
   用于验证长期趋势(MA60/MA120)、过滤主力合约换月噪音。

3. **近月合约(Avoid)**: 距到期不足 30 天的合约。
   价格向现货回归、持仓限制导致技术图形失真,不用于纯技术分析。

4. **移仓换月预警**: 当新主力 OI 连续超过旧主力时发出预警,确保分析标的已更新。"""

# 合约分析策略(期限合约)
TERM_CONTRACT_STRATEGY = """你是基于期货合约技术分析的期货分析师。当前分析的是一张具体合约(非主力连续)。分析遵循以下框架:

1. **期限合约(Primary)**: 锁定特定到期月的合约。
   所有技术指标(均线、MACD、RSI、BOLL)基于此合约的 K 线计算。价格体现市场对该到期月供需的预期。

2. **指数合约(Auxiliary)**: 所有可交易合约持仓量加权平均的连续序列。
   用于验证长期趋势(MA60/MA120)、判断该期限合约与品种整体趋势是否一致。

3. **基差/升贴水**: 期限合约价格相对于现货价格存在升贴水。
   合约临近到期时价格向现货回归,到期前基差趋向收敛,这是期限合约独有的分析要点。

4. **无需讨论移仓换月**: 期限合约不存在换月问题(一张合约到期即退市)。"""


def _detect_contract_type(full_symbol: str) -> tuple:
    """检测合约类型,返回 (is_main_continuous, contract_type_label)。

    Args:
        full_symbol: 完整标的代码(如 CU2501.SHF / CU0.SHF)

    Returns:
        (is_main_continuous, label)
        - 主力连续(CU0.SHF) → (True, "主力连续合约")
        - 期限合约(CU2501.SHF) → (False, "期限合约(到期月:2025-01)")
        - 无法识别(CU) → (True, "主力连续合约")  # fallback 保持现有行为
    """
    import re
    symbol_body = full_symbol.split(".")[0] if "." in full_symbol else full_symbol
    match = re.match(r"^([A-Za-z]+)(\d+)$", symbol_body)
    if match:
        digits = match.group(2)
        if digits == "0":
            return True, "主力连续合约"
        # 期限合约: 格式化 YYMM → YYYY-MM
        if len(digits) == 4:
            try:
                year = "20" + digits[:2]
                month = digits[2:]
                return False, f"期限合约(到期月:{year}-{month})"
            except Exception:
                pass
        return False, f"期限合约(代码:{symbol_body})"
    # fallback: 无法识别时按主力连续处理
    return True, "主力连续合约"

# 技术分析师系统 prompt(中文,期货特定)
# - 不调工具,所有数据已由 features 层算好注入
# - 强调多周期(日+周)、OI 背离、波动率、关键位
TECHNICAL_SYSTEM_PROMPT = """你是一位资深的期货技术分析师,与基本面、持仓、新闻分析师协作。

## 分析对象
- 标的代码:{full_symbol}
- 品种名称:{variety_name}
- 交易所:{exchange}
- 分析日期:{trade_date}
- 合约类型:{contract_type_label}

## 合约分析策略

{contract_strategy}

## 特征层(已计算,直接消费)

### 综合判断
- 综合方向:{combined_direction}(强度 {combined_strength:.2f})
- 日线方向:{daily_direction}(强度 {daily_strength:.2f})
- 周线方向:{weekly_direction}(强度 {weekly_strength:.2f})

### 主力-指数一致性
- 状态:{main_index_alignment}
  - aligned = 主力与指数同向,趋势共识强
  - divergent = 主力与指数反向,短期噪音或换月干扰
  - partial = 一方信号不足

### 指数合约长期趋势
- 指数合约代码:{index_symbol}
- 长期均线:MA60={index_ma60}, MA120={index_ma120}
- 长期趋势:{index_long_term_trend}
- 主力相对指数强弱(z-score):{relative_strength}

### 移仓换月状态
{rollover_status}

### 持仓量(OI)与价格背离
{oi_divergence}

### 波动率
- 状态:{vol_regime}
- ATR:{atr}
- ATR/价格 180 日分位:{atr_pctl}

## 关键指标(snapshot 摘录)
{snapshot_excerpt}

## 已触发的 rule-based 信号
{trigger_signals}

## 数据质量
- 数据条数:{quality_rows}
- {contract_type_label}:{main_available}
- 指数合约:{index_available}

## 新闻摘要(跨分析师参考)
{news_summary}

## 用户上传数据参考
{custom_data_context}

---

## 分析要求

1. **技术形态解读**:基于日/周双周期综合判断趋势方向与强度,说明两周期是否同向
2. **关键位识别**:从价格区间、均线、布林带提炼 2-3 个支撑位与阻力位
3. **主力指数交叉验证**:当主力信号冲突时,以指数长期趋势过滤噪音
   - 主力看多 + 指数 MA120 上方 → 高置信度顺势
   - 主力看多 + 指数 MA120 下方 → 警惕逆大趋势的假突破
4. **OI 背离分析**:持仓量与价格背离的方向含义(看多/看空/中性)
5. **波动率评估**:当前波动率历史分位,适合突破策略还是震荡策略
6. **移仓检测**:报告含 rollover 预警时,判断历史信号是否因换月而失真
7. **风险提示**:数据稀疏、信号冲突、指数不可用时降低 confidence,在结论中明确标注

## 输出格式

使用 Markdown,400-800 字。结构:
- ## 综合判断(方向+强度+一句话)
- ## 关键位(支撑/阻力表格)
- ## OI 背离解读
- ## 波动率与策略适配
- ## 移仓换月(如有预警)
- ## 风险提示

不要使用 emoji;所有数值保留 2 位小数。
"""


def _format_snapshot_excerpt(snapshot: Dict[str, Any], max_keys: int = 15) -> str:
    """把 snapshot dict 格式化为多行 markdown。"""
    if not snapshot:
        return "(无 snapshot 数据)"
    items = list(snapshot.items())[:max_keys]
    lines = [f"- {k}: {_fmt(v)}" for k, v in items]
    return "\n".join(lines)


def _fmt(v: Any) -> str:
    """数值安全格式化。"""
    if v is None:
        return "N/A"
    if isinstance(v, float):
        if v != v:  # NaN
            return "N/A"
        return f"{v:.4f}".rstrip("0").rstrip(".")
    return str(v)


def _build_fallback_report(
    full_symbol: str,
    combined: Dict[str, Any],
    daily: Dict[str, Any],
    weekly: Dict[str, Any],
    quality: Dict[str, Any],
    index_contract: Optional[Dict[str, Any]] = None,
    rollover: Optional[Dict[str, Any]] = None,
    contract_type_label: str = "主力连续合约",
) -> str:
    """LLM 调用失败时,直接用 features snapshot 拼 Markdown 报告。

    永不抛错,作为节点的最后防线。
    """
    direction = combined.get("direction", "neutral")
    direction_cn = {"bullish": "看多", "bearish": "看空", "neutral": "中性"}.get(direction, direction)
    strength = combined.get("strength", 0.0)
    signals = combined.get("signals", [])[:8]
    vol = combined.get("volatility", {}) or {}

    md = (
        f"# {full_symbol} 技术分析报告(降级版本 — LLM 不可用)\n\n"
        f"## 综合判断\n"
        f"- 方向:{direction_cn}\n"
        f"- 强度:{strength:.2f}\n"
        f"- OI 背离:{combined.get('oi_divergence', 'neutral')}\n"
        f"- 波动率:{vol.get('regime', 'low')} (ATR={_fmt(vol.get('atr'))})\n"
    )

    md += f"- 合约类型:{contract_type_label}\n"

    # 指数合约摘要
    if index_contract:
        lt = index_contract.get("long_term_trend", "neutral")
        lt_cn = {"bullish": "看多", "bearish": "看空", "neutral": "中性"}.get(lt, lt)
        md += f"- 指数合约趋势:{lt_cn} (MA60={_fmt(index_contract.get('ma60'))}, MA120={_fmt(index_contract.get('ma120'))})\n"
        rs = index_contract.get("relative_strength")
        if rs is not None:
            md += f"- 主力相对指数强弱:z-score={rs:.3f}\n"
    alignment = combined.get("main_index_alignment", "N/A")
    md += f"- 主力-指数一致性:{alignment}\n\n"

    # 移仓换月
    if rollover and rollover.get("detected"):
        md += f"## 移仓换月预警\n"
        md += f"- {rollover.get('description', '检测到换月')}\n"
        if rollover.get("recent_rollover"):
            md += "- ⚠ 近期发生换月,历史信号可能失真\n"
        md += "\n"

    md += f"## 触发信号\n"
    md += "\n".join(f"- {s}" for s in signals) or "- (无触发信号)"
    md += "\n\n## 数据质量\n"
    md += f"- 数据条数:{quality.get('rows', 0)}\n"
    md += f"- {contract_type_label}:{quality.get('main_continuous_available', 'N/A')}\n"
    md += f"- 指数合约:{quality.get('index_contract_available', 'N/A')}\n"
    md += (
        f"\n---\n"
        f"_本报告由 features 层直接生成,未经过 LLM 文字总结;"
        f"LLM 故障恢复后请重新提交任务以获得完整分析。_\n"
    )
    return md


def create_technical_analyst(llm):
    """技术分析师工厂函数。

    Args:
        llm: LangChain 兼容的 LLM 实例(BaseChatModel 子类)
             commodity 节点不调工具,直接 invoke() 即可

    Returns:
        technical_analyst_node(state: dict) -> dict
        节点函数读取 state['commodity_features']['technical'],
        调用 LLM 生成 Markdown 报告,落到 state['market_report']
    """

    def technical_analyst_node(state: dict) -> dict:
        full_symbol = get_full_symbol(state)
        trade_date = state.get("trade_date", "")

        logger.info(f"📈 [技术分析师] 启动: {full_symbol} @ {trade_date}")

        features = load_features(state)
        custom_data_context = build_custom_data_context(features)
        tech = features.get("technical")

        # --- 降级路径 1:features 完全缺失 ---
        if not isinstance(tech, dict):
            reason = "特征层技术数据缺失(features['technical'] 为空)"
            report_md = empty_report("neutral", reason, custom_data_context=custom_data_context)
            logger.warning(f"⚠️ [技术分析师] {reason}")
            analyst_id = make_analyst_id("TECH", full_symbol, trade_date, seed="empty")
            conclusion_id = make_conclusion_id("TECH", 1)
            tagged_report = inject_analyst_id(report_md, analyst_id)
            registry_entry = make_registry_entry(analyst_id, conclusion_id, "TECH", "technical", "market_report", "skip", "(数据缺失: 跳过)", status="skipped")
            return {
                "market_report": tagged_report,
                "messages": [],
                "market_tool_call_count": 0,
                "analyst_registry": registry_entry,
            }

        # --- 降级路径 2:数据稀疏(quality.rows < 阈值) ---
        if not quality_gate(tech):
            quality = tech.get("quality", {}) if isinstance(tech, dict) else {}
            rows = quality.get("rows", 0)
            reason = f"特征层技术数据稀疏(quality.rows={rows} < {30})"
            report_md = empty_report("neutral", reason, custom_data_context=custom_data_context)
            logger.warning(f"⚠️ [技术分析师] {reason}")
            analyst_id = make_analyst_id("TECH", full_symbol, trade_date, seed="sparse")
            conclusion_id = make_conclusion_id("TECH", 1)
            tagged_report = inject_analyst_id(report_md, analyst_id)
            registry_entry = make_registry_entry(analyst_id, conclusion_id, "TECH", "technical", "market_report", "skip", "(数据稀疏: 跳过)", status="skipped")
            return {
                "market_report": tagged_report,
                "messages": [],
                "market_tool_call_count": 0,
                "analyst_registry": registry_entry,
            }

        # --- 主路径:features 可信,准备 LLM prompt ---
        combined = tech.get("combined", {}) or {}
        main_cont = tech.get("main_continuous", {}) or {}
        daily = main_cont.get("daily", {}) or {}
        weekly = main_cont.get("weekly") or {}
        quality = tech.get("quality", {}) or {}
        index_contract = tech.get("index_contract", {}) or {}
        rollover = tech.get("rollover", {}) or {}

        snapshot_excerpt = _format_snapshot_excerpt(truncate_snapshot(daily.get("snapshot", {}), max_keys=15))
        trigger_signals = "\n".join(
            f"- {s}" for s in (combined.get("signals", []) or [])[:10]
        ) or "- (无触发信号)"

        # 指数合约字段
        index_symbol = index_contract.get("symbol") or "N/A"
        index_ma60 = _fmt(index_contract.get("ma60"))
        index_ma120 = _fmt(index_contract.get("ma120"))
        index_long_term_trend = index_contract.get("long_term_trend", "neutral")
        rel_strength = _fmt(index_contract.get("relative_strength"))

        # 移仓换月字段
        if rollover and rollover.get("detected"):
            rollover_status = f"- 检测到换月: {rollover.get('description', '')}"
            if rollover.get("recent_rollover"):
                rollover_status += "\n- ⚠ 近期发生换月,注意历史信号失真"
        else:
            rollover_status = "- 未检测到换月"

        variety_name = state.get("variety_name", full_symbol)
        exchange = state.get("exchange", "")
        daily_trend = daily.get("trend", {}) or {}
        weekly_trend = weekly.get("trend", {}) or {} if weekly else {}
        vol = combined.get("volatility", {}) or {}

        # --- 合约类型检测 ---
        is_main_continuous, contract_type_label = _detect_contract_type(full_symbol)
        if is_main_continuous:
            contract_strategy = MAIN_CONTINUOUS_STRATEGY
        else:
            contract_strategy = TERM_CONTRACT_STRATEGY
        logger.info(f"📈 [技术分析师] 合约类型: {contract_type_label} (full_symbol={full_symbol})")

        prompt_vars = dict(
            full_symbol=full_symbol,
            variety_name=variety_name,
            exchange=exchange,
            trade_date=trade_date,
            contract_type_label=contract_type_label,
            contract_strategy=contract_strategy,
            combined_direction=combined.get("direction", "neutral"),
            combined_strength=float(combined.get("strength", 0.0) or 0.0),
            daily_direction=daily_trend.get("direction", "neutral"),
            daily_strength=float(daily_trend.get("strength", 0.0) or 0.0),
            weekly_direction=(weekly_trend.get("direction", "neutral") if weekly else "N/A"),
            weekly_strength=(float(weekly_trend.get("strength", 0.0) or 0.0) if weekly else 0.0),
            main_index_alignment=combined.get("main_index_alignment", "partial"),
            index_symbol=index_symbol,
            index_ma60=index_ma60,
            index_ma120=index_ma120,
            index_long_term_trend=index_long_term_trend,
            relative_strength=rel_strength,
            rollover_status=rollover_status,
            oi_divergence=combined.get("oi_divergence", "neutral") or "neutral",
            vol_regime=vol.get("regime", "low") or "low",
            atr=_fmt(vol.get("atr")),
            atr_pctl=_fmt(vol.get("atr_ratio_pctl180")),
            snapshot_excerpt=snapshot_excerpt,
            trigger_signals=trigger_signals,
            quality_rows=quality.get("rows", 0),
            main_available=str(quality.get("main_continuous_available", "N/A")),
            index_available=str(quality.get("index_contract_available", "N/A")),
            news_summary=state.get("news_summary", ""),
            custom_data_context=build_custom_data_context(features),
        )

        try:
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", TECHNICAL_SYSTEM_PROMPT),
                    MessagesPlaceholder(variable_name="messages"),
                ]
            ).partial(**prompt_vars)
            # 直接 format 成消息列表,然后 llm.invoke(messages) — 不走 chain
            # 这样 mock 行为可预测(result.content 一定是字符串)
            messages_payload = prompt.format_messages(
                messages=state.get("messages", []) or []
            )

            logger.info(f"📈 [技术分析师] 调用 LLM,prompt 变量: full_symbol={full_symbol}")
            result = llm.invoke(messages_payload)

            # 安全提取 content(可能是 AIMessage / str / MagicMock)
            if hasattr(result, "content"):
                content = result.content
                if not isinstance(content, str):
                    # MagicMock 等情况
                    content = str(content) if content is not None else ""
            else:
                content = str(result) if result is not None else ""

            report_md = content
            logger.info(f"✅ [技术分析师] LLM 报告生成: {len(report_md)} 字符")

            # 构造 messages 字段(优先复用原 result,否则包装 AIMessage)
            if hasattr(result, "content") and isinstance(result, AIMessage):
                msg_out = result
            elif hasattr(result, "content"):
                # MagicMock 等具有 content 属性的对象 — 直接复用
                msg_out = result
            else:
                msg_out = AIMessage(content=report_md)

            direction = combined.get("direction", "neutral") or "neutral"
            analyst_id = make_analyst_id("TECH", full_symbol, trade_date)
            conclusion_id = make_conclusion_id("TECH", 1)
            tagged_report = inject_analyst_id(report_md, analyst_id)
            registry_entry = make_registry_entry(analyst_id, conclusion_id, "TECH", "technical", "market_report", direction, extract_first_sentence(report_md))

            return {
                "market_report": tagged_report,
                "messages": [msg_out],
                "market_tool_call_count": 0,
                "analyst_registry": registry_entry,
            }

        except Exception as e:
            # --- 降级路径 3:LLM 调用抛错(网络/超时/限流) ---
            logger.error(f"❌ [技术分析师] LLM 调用失败,降级为 features 直拼: {e}")
            try:
                fallback_md = _build_fallback_report(
                    full_symbol, combined, daily, weekly, quality,
                    index_contract=index_contract,
                    rollover=rollover,
                    contract_type_label=contract_type_label,
                )
                if custom_data_context:
                    fallback_md += f"\n\n## 用户上传数据参考\n{custom_data_context}\n"
            except Exception as inner_e:
                logger.error(f"❌ [技术分析师] fallback 也失败: {inner_e}")
                fallback_md = empty_report("neutral", f"features 与 LLM 均不可用: {e}; fallback 异常: {inner_e}", custom_data_context=custom_data_context)

            analyst_id = make_analyst_id("TECH", full_symbol, trade_date, seed="fallback")
            conclusion_id = make_conclusion_id("TECH", 1)
            tagged_report = inject_analyst_id(fallback_md, analyst_id)
            registry_entry = make_registry_entry(analyst_id, conclusion_id, "TECH", "technical", "market_report", "neutral", "(降级: LLM 不可用)", status="degraded")
            return {
                "market_report": tagged_report,
                "messages": [],
                "market_tool_call_count": 0,
                "analyst_registry": registry_entry,
            }

    return technical_analyst_node


__all__ = ["create_technical_analyst"]