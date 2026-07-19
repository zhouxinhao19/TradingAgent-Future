import time
import json

from typing import Any, Dict, List

# 导入统一日志系统
from tradingagents.utils.logging_init import get_logger
from tradingagents.agents.utils.instrument_utils import build_instrument_context
logger = get_logger("default")


# =============================================================================
# _build_analyst_summary — 结构化摘要替代完整 Markdown（Phase Agent 改造）
# =============================================================================

def _build_analyst_summary(
    features: Dict[str, Any],
    registry: Dict[str, Any],
    news_summary: str = "",
) -> str:
    """从 analyst_registry + commodity_features 构建结构化摘要。

    替换 4 份完整 Markdown（~8000 字），输出约 1500 字的精简摘要。
    每个 L1 分析师输出: direction / calibrated_confidence / top-3 signals / key_metrics。

    附带修正:
      - #9 技术分析数据截断: 注入 composite_score/key_levels/oi_divergence/volatility_regime
      - #13 新闻摘要为空: news_summary 升级为含分类统计 + 情感比 + 事件标题
      - #14 features 字段未被消费: 补入 inventory.mom_change/term_structure.roll_yield/basis.spot_price
      - #16 置信度校准: 基于 data_quality 加权归一化
    """
    lines: List[str] = []
    lines.append("## L1 分析师结构化摘要")

    tech = features.get("technical", {})
    daily = tech.get("daily", {}) if isinstance(tech, dict) else {}
    snap = daily.get("snapshot", {}) if isinstance(daily, dict) else {}

    # --- 技术分析师摘要 ---
    tech_reg = _find_registry_entry(registry, "tech")
    tech_dir = tech_reg.get("direction") if tech_reg else "?"
    tech_conf = tech_reg.get("confidence", 0.0) if tech_reg else 0.0
    tech_status = tech_reg.get("status", "ok") if tech_reg else "ok"
    tech_weight = _data_quality_weight(tech_status)
    tech_calibrated = round(tech_conf * tech_weight, 2) if isinstance(tech_conf, (int, float)) else 0.0
    tech_signals = (tech_reg or {}).get("signals", [])

    lines.append(f"\n### 技术分析师 | {tech_dir} | 原始置信度 {tech_conf} | 校准后 {tech_calibrated} | status={tech_status}")
    if tech_signals:
        lines.append(f"信号: {'; '.join(tech_signals[:3])}")
    lines.append(f"composite_score={snap.get('composite_score', 'N/A')}, "
                 f"oi_divergence={snap.get('oi_divergence', snap.get('oi_position', 'N/A'))}, "
                 f"volatility_regime={snap.get('volatility_20d', snap.get('volatility_regime', 'N/A'))}, "
                 f"atr_ratio_pctl180={snap.get('atr_ratio_pctl180', 'N/A')}, "
                 f"支撑={snap.get('boll_low', 'N/A')}, 阻力={snap.get('boll_up', 'N/A')}")

    # --- 产业分析师（基差+库存+期限结构）摘要 ---
    fund_reg = _find_registry_entry(registry, "fund")
    fund_dir = fund_reg.get("direction") if fund_reg else "?"
    fund_conf = fund_reg.get("confidence", 0.0) if fund_reg else 0.0
    fund_status = fund_reg.get("status", "ok") if fund_reg else "ok"
    fund_weight = _data_quality_weight(fund_status)
    fund_calibrated = round(fund_conf * fund_weight, 2) if isinstance(fund_conf, (int, float)) else 0.0
    fund_signals = (fund_reg or {}).get("signals", [])

    basis = features.get("basis", {})
    inventory = features.get("inventory", {})
    term = features.get("term_structure", {})

    lines.append(f"\n### 产业分析师 | {fund_dir} | 原始置信度 {fund_conf} | 校准后 {fund_calibrated} | status={fund_status}")
    if fund_signals:
        lines.append(f"信号: {'; '.join(fund_signals[:3])}")

    # 基差（补 spot_price 字段）
    if isinstance(basis, dict):
        basis_latest = basis.get("latest", {}) if isinstance(basis.get("latest"), dict) else basis
        lines.append(f"基差: latest={basis_latest.get('value', basis_latest.get('basis', 'N/A'))}, "
                     f"zscore={basis_latest.get('zscore', 'N/A')}, "
                     f"spot_price={basis_latest.get('spot_price', 'N/A')}")

    # 库存（补 mom_change/jump_flag 字段）
    if isinstance(inventory, dict):
        inv_latest = inventory.get("latest", {}) if isinstance(inventory.get("latest"), dict) else inventory
        inv_snap = inventory.get("snapshot", {}) if isinstance(inventory.get("snapshot"), dict) else {}
        lines.append(f"库存: wow_change={inv_latest.get('wow_change', inv_snap.get('wow_change', 'N/A'))}, "
                     f"mom_change={inv_latest.get('mom_change', inv_snap.get('mom_change', 'N/A'))}, "
                     f"jump_flag={inv_latest.get('jump_flag', inv_snap.get('jump_flag', 'N/A'))}")

    # 期限结构（补 roll_yield/spread 字段）
    if isinstance(term, dict):
        lines.append(f"期限结构: structure={term.get('structure', term.get('term_structure', 'N/A'))}, "
                     f"carry_score={term.get('carry_score', 'N/A')}, "
                     f"roll_yield={term.get('roll_yield', 'N/A')}, "
                     f"spread={term.get('spread', 'N/A')}")

    # --- 持仓分析师摘要 ---
    pos_reg = _find_registry_entry(registry, "pos")
    pos_dir = pos_reg.get("direction") if pos_reg else "?"
    pos_conf = pos_reg.get("confidence", 0.0) if pos_reg else 0.0
    pos_status = pos_reg.get("status", "ok") if pos_reg else "ok"
    pos_weight = _data_quality_weight(pos_status)
    pos_calibrated = round(pos_conf * pos_weight, 2) if isinstance(pos_conf, (int, float)) else 0.0
    pos_signals = (pos_reg or {}).get("signals", [])

    positioning = features.get("positioning", {})
    pos_latest = positioning.get("latest", {}) if isinstance(positioning.get("latest"), dict) else positioning

    lines.append(f"\n### 持仓分析师 | {pos_dir} | 原始置信度 {pos_conf} | 校准后 {pos_calibrated} | status={pos_status}")
    if pos_signals:
        lines.append(f"信号: {'; '.join(pos_signals[:3])}")
    lines.append(f"net_long_change_5d={pos_latest.get('net_long_change_5d', 'N/A')}, "
                 f"long_short_ratio={pos_latest.get('long_short_ratio', 'N/A')}, "
                 f"crowding={pos_latest.get('crowding_status', 'N/A')}")

    # --- 新闻分析师摘要（升级版: 含分类统计 + 情感比 + 事件标题） ---
    news_reg = _find_registry_entry(registry, "news")
    news_dir = news_reg.get("direction") if news_reg else "?"
    news_conf = news_reg.get("confidence", 0.0) if news_reg else 0.0
    news_status = news_reg.get("status", "ok") if news_reg else "ok"
    news_weight = _data_quality_weight(news_status)
    news_calibrated = round(news_conf * news_weight, 2) if isinstance(news_conf, (int, float)) else 0.0
    news_signals = (news_reg or {}).get("signals", [])

    lines.append(f"\n### 新闻分析师 | {news_dir} | 原始置信度 {news_conf} | 校准后 {news_calibrated} | status={news_status}")
    if news_signals:
        lines.append(f"信号: {'; '.join(news_signals[:3])}")

    # 新闻摘要替代 #13: 精确分类统计 + 情感比 + 事件标题
    news_sent = features.get("news_sentiment", {})
    ns_latest = news_sent.get("latest", {}) if isinstance(news_sent.get("latest"), dict) else news_sent
    ns_events = ns_latest.get("recent_events", ns_latest.get("events", []))
    if isinstance(ns_events, list) and ns_events:
        pos_count = sum(1 for e in ns_events if isinstance(e, dict) and e.get("sentiment") == "positive")
        neg_count = sum(1 for e in ns_events if isinstance(e, dict) and e.get("sentiment") == "negative")
        neutral_count = sum(1 for e in ns_events if isinstance(e, dict) and e.get("sentiment") == "neutral")
        total_events = pos_count + neg_count + neutral_count
        sentiment_ratio = round((pos_count - neg_count) / max(total_events, 1), 2) if total_events > 0 else 0.0
        lines.append(f"新闻情感: pos={pos_count}, neg={neg_count}, neutral={neutral_count}, ratio={sentiment_ratio}")
        # 高重要度事件标题
        high_events = [
            e.get("title", e.get("summary", "?"))[:60]
            for e in ns_events[:5]
            if isinstance(e, dict) and e.get("llm_importance") == "high"
        ]
        if high_events:
            lines.append(f"高重要度事件: {'; '.join(high_events)}")
    else:
        lines.append(f"新闻情感: {news_summary[:80] if news_summary else '(无新闻)'}")

    # --- 置信度校准汇总 ---
    calibrated = {
        "technical": tech_calibrated,
        "fundamental": fund_calibrated,
        "position": pos_calibrated,
        "news": news_calibrated,
    }
    lines.append(f"\n校准置信度汇总: {json.dumps(calibrated, ensure_ascii=False)}")

    # --- L1 冲突检测（跳过 analyst 不计入） ---
    active_dirs = []
    for r_key, r_dir in [("tech", tech_dir), ("fund", fund_dir), ("pos", pos_dir), ("news", news_dir)]:
        if r_dir not in ("skip", "?", None):
            active_dirs.append(r_dir)
    bullish_count = sum(1 for d in active_dirs if d in ("bullish", "long"))
    bearish_count = sum(1 for d in active_dirs if d in ("bearish", "short"))
    lines.append(f"\nL1 冲突: 看多={bullish_count}, 看空={bearish_count}, 活跃分析师={len(active_dirs)}")

    return "\n".join(lines)


def _find_registry_entry(registry: Dict[str, Any], prefix: str) -> Dict[str, Any]:
    """从 analyst_registry 中按前缀查找第一个匹配项。"""
    for key, entry in registry.items():
        if key.startswith(f"REF-{prefix.upper()}") or key.startswith(prefix.upper()):
            if isinstance(entry, dict):
                return entry
    return {}


def _data_quality_weight(status: str) -> float:
    """置信度权重校准：基于数据质量。"""
    return {
        "ok": 1.0,
        "degraded": 0.5,
        "skipped": 0.3,
        "": 0.5,
    }.get(status, 0.5)


# =============================================================================
# COMMODITY_REASONING_PROMPT — 精简版（结构化摘要替代完整 Markdown）
# =============================================================================

COMMODITY_REASONING_PROMPT = """你是期货推理分析师。在单次分析中完成多空双向推理，输出结构化分析报告。

⚠️ 本报告是投研辅助工具，**不是交易指令**。严禁输出具体交易价位。

## 分析对象
- 合约: {full_symbol}
- 品种: {variety_name}
- 分析日期: {analysis_date}

## 标的约束
{instrument_context}

## L1 分析师结构化摘要（含校准置信度 + 关键数据）
{structured_summary}

## L1 分析师报告引用 ID
{analyst_registry_summary}

## 历史经验教训
{past_memory_str}

---

## 输出要求

输出包含以下三大模块的复合 JSON。

**JSON 顶级 key 必须严格使用以下名称（不要用"模块A/B/C"作为 key）：**

### 估值驱动矩阵

评估以下维度的当前状态、估值判断和驱动方向：
1. 基差（估值）
2. 库存（驱动）
3. 期限结构（估值+驱动）
4. 技术面（择时信号）
5. 持仓情绪（验证信号）
6. 宏观/新闻（外部驱动）

每个维度必须包含：
- "维度": 维度名称
- "当前状态": 简练描述
- "估值判断": 低估/合理/高估
- "驱动方向": bullish/bearish/neutral
- "驱动因素": 关键驱动列表
- "置信度": 0~1 浮点数
- "数据来源": [引用至少 1 个分析师报告 ID，如 "REF-TECH-a1b2c3d4"]

### 多空对照表

每个关键分歧包含看涨/看跌双方逻辑，每个逻辑后标注引用 ID。

### 三种情景推演

三种情景（保守/基准/乐观），每个包含：
- "推演方向": 做多/做空/中性
- "触发条件": 可观测的市场信号列表
- "关注焦点": 应关注的关键变量
- "风险节点": 情景失效条件
- "置信度": 0~1 浮点数
- "数据来源": [引用至少 2 个不同分析师报告 ID]

### 禁止项
- ❌ 禁止 "买入"/"卖出"，统一用 "做多"/"做空"
- ❌ 禁止具体交易价位（入场价/止损价/目标价/手数）
- ❌ 禁止保证金占用比例
- ❌ 禁止虚构未提供的分析师报告 ID

### 允许项
- ✅ 三种情景允许方向不同（如保守=做多、基准=中性、乐观=做空）
- ✅ 方向不同时须在"综合情景判断"中标注核心分歧
- ✅ 触发条件必须是可观测、可验证的市场信号

请输出**纯 JSON**（无 Markdown 代码块包裹），包含以上三大模块。"""


def create_research_manager(llm, memory):
    def research_manager_node(state) -> dict:
        ticker = state["company_of_interest"]
        instrument_context = build_instrument_context(ticker)
        market_research_report = state["market_report"]
        sentiment_report = state.get("position_report") or state.get("sentiment_report", "")
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        # === Phase 3b-ii-B:检测 asset_type ===
        asset_type = state.get("asset_type", "stock")

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"

        # 安全检查：确保memory不为None
        # Phase Agent: 降级策略 — ChromaDB 连接失败时静默降级
        past_memories = []
        if memory is not None:
            try:
                past_memories = memory.get_memories(curr_situation, n_matches=2)
            except Exception as e:
                logger.warning(
                    f"⚠️ [Memory] ChromaDB 检索失败，静默降级: {e}"
                )
                past_memories = []
        else:
            logger.warning(f"⚠️ [DEBUG] memory为None，跳过历史记忆检索")
            past_memories = []

        past_memory_str = ""
        if past_memories:
            for i, rec in enumerate(past_memories, 1):
                past_memory_str += rec["recommendation"] + "\n\n"
        else:
            # 冷启动处理：无历史记忆时提示
            past_memory_str = "（历史相似情景：无（首次分析或记忆服务暂不可用，暂无历史参考））"

        if asset_type == "commodity":
            # ===== 新推理分析师路径 =====
            full_symbol = state.get("full_symbol") or ticker
            variety_name = state.get("variety_name", "")
            trade_date = state.get("trade_date", "")

            features = state.get("commodity_features", {}) or {}
            news_summary = state.get("news_summary", "")
            # 提前读取 registry（第 322 行需此变量）
            registry = state.get("analyst_registry", {}) or {}
            # Phase Agent: 结构化摘要替代 4 份完整 Markdown
            structured_summary = _build_analyst_summary(features, registry, news_summary)
            logger.info(
                f"[推理分析师] 结构化摘要={len(structured_summary)} 字符, "
                f"报告数={len(registry)}"
            )
            # 构建 analyst_registry_summary (短引用列表,供 LLM 输出引用)
            if registry:
                registry_lines = []
                for ref_id, entry in registry.items():
                    cn_name = entry.get("cn_name", entry.get("analyst", "?"))
                    direction = entry.get("direction", "?")
                    summary = entry.get("summary", "")
                    registry_lines.append(f"- [{ref_id}] {cn_name}: {direction} — {summary}")
                analyst_registry_summary = "\n".join(registry_lines)
            else:
                analyst_registry_summary = "(暂无分析师报告索引)"

            prompt = COMMODITY_REASONING_PROMPT.format(
                full_symbol=full_symbol,
                variety_name=variety_name,
                analysis_date=trade_date,
                instrument_context=instrument_context,
                structured_summary=structured_summary,
                analyst_registry_summary=analyst_registry_summary,
                past_memory_str=past_memory_str,
            )
            # 直接调用 llm（不做 chain）
            response = llm.invoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)

            # 写入：简化 investment_debate_state（无辩论历史）
            return {
                "investment_debate_state": {
                    "judge_decision": content,
                    "history": "",
                    "count": 0,
                },
                "investment_plan": content,
            }
        else:
            history = state["investment_debate_state"].get("history", "")
            investment_debate_state = state["investment_debate_state"]

            prompt = f"""作为投资组合经理和辩论主持人，您的职责是批判性地评估这轮辩论并做出明确决策：支持看跌分析师、看涨分析师，或者仅在基于所提出论点有强有力理由时选择持有。

简洁地总结双方的关键观点，重点关注最有说服力的证据或推理。您的建议——买入、卖出或持有——必须明确且可操作。避免仅仅因为双方都有有效观点就默认选择持有；要基于辩论中最强有力的论点做出承诺。

此外，为交易员制定详细的投资计划。这应该包括：

您的建议：基于最有说服力论点的明确立场。
理由：解释为什么这些论点导致您的结论。
战略行动：实施建议的具体步骤。
📊 目标价格分析：基于所有可用报告（基本面、新闻、情绪），提供全面的目标价格区间和具体价格目标。考虑：
- 基本面报告中的基本估值
- 新闻对价格预期的影响
- 情绪驱动的价格调整
- 技术支撑/阻力位
- 风险调整价格情景（保守、基准、乐观）
- 价格目标的时间范围（1个月、3个月、6个月）
💰 您必须提供具体的目标价格 - 不要回复"无法确定"或"需要更多信息"。

考虑您在类似情况下的过去错误。利用这些见解来完善您的决策制定，确保您在学习和改进。以对话方式呈现您的分析，就像自然说话一样，不使用特殊格式。

以下是您对错误的过去反思：
\"{past_memory_str}\"

标的约束：
{instrument_context}

以下是综合分析报告：
市场研究：{market_research_report}

持仓分析：{sentiment_report}

新闻分析：{news_report}

基本面分析：{fundamentals_report}

以下是辩论：
辩论历史：
{history}

请用中文撰写所有分析内容和建议。"""

        # 📊 统计 prompt 大小
        prompt_length = len(prompt)
        estimated_tokens = int(prompt_length / 1.8)

        logger.info(f"📊 [Research Manager] Prompt 统计:")
        logger.info(f"   - 辩论历史长度: {len(history)} 字符")
        logger.info(f"   - 总 Prompt 长度: {prompt_length} 字符")
        logger.info(f"   - 估算输入 Token: ~{estimated_tokens} tokens")

        # ⏱️ 记录开始时间
        start_time = time.time()

        response = llm.invoke(prompt)

        # ⏱️ 记录结束时间
        elapsed_time = time.time() - start_time

        # 📊 统计响应信息
        response_length = len(response.content) if response and hasattr(response, 'content') else 0
        estimated_output_tokens = int(response_length / 1.8)

        logger.info(f"⏱️ [Research Manager] LLM调用耗时: {elapsed_time:.2f}秒")
        logger.info(f"📊 [Research Manager] 响应统计: {response_length} 字符, 估算~{estimated_output_tokens} tokens")

        new_investment_debate_state = {
            "judge_decision": response.content,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": response.content,
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": response.content,
        }

    return research_manager_node
