"""
technical_analyst.py — 商品期货技术分析师节点 (Phase 3b-ii)

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
    empty_report,
    get_full_symbol,
    load_features,
    quality_gate,
    truncate_snapshot,
)

logger = get_logger("default")

# 技术分析师系统 prompt(中文,期货特定)
# - 不调工具,所有数据已由 features 层算好注入
# - 强调多周期(日+周)、OI 背离、波动率、关键位
TECHNICAL_SYSTEM_PROMPT = """你是一位资深的期货技术分析师,与基本面、持仓、新闻分析师协作。

## 分析对象
- 标的代码:{full_symbol}
- 品种名称:{variety_name}
- 交易所:{exchange}
- 分析日期:{trade_date}

## 特征层(已计算,直接消费)

### 综合判断
- 综合方向:{combined_direction}(强度 {combined_strength:.2f})
- 日线方向:{daily_direction}(强度 {daily_strength:.2f})
- 周线方向:{weekly_direction}(强度 {weekly_strength:.2f})

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
- 覆盖率:{quality_coverage}
- 数据时效:{quality_freshness_days} 天

---

## 分析要求

1. **技术形态解读**:基于日/周双周期综合判断趋势方向与强度,说明两周期是否同向
2. **关键位识别**:从价格区间、均线、布林带提炼 2-3 个支撑位与阻力位
3. **OI 背离分析**:持仓量与价格背离的方向含义(看多/看空/中性)
4. **波动率评估**:当前波动率历史分位,适合突破策略还是震荡策略
5. **风险提示**:数据稀疏、信号冲突时降低 confidence,在结论中明确标注

## 输出格式

使用 Markdown,400-800 字。结构:
- ## 综合判断(方向+强度+一句话)
- ## 关键位(支撑/阻力表格)
- ## OI 背离解读
- ## 波动率与策略适配
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
        f"- 波动率:{vol.get('regime', 'low')} (ATR={_fmt(vol.get('atr'))})\n\n"
        f"## 触发信号\n"
    )
    md += "\n".join(f"- {s}" for s in signals) or "- (无触发信号)"
    md += "\n\n## 数据质量\n"
    md += f"- 数据条数:{quality.get('rows', 0)}\n"
    md += f"- 覆盖率:{_fmt(quality.get('coverage'))}\n"
    md += f"- 数据时效:{_fmt(quality.get('data_freshness_days'))} 天\n"
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
        tech = features.get("technical")

        # --- 降级路径 1:features 完全缺失 ---
        if not isinstance(tech, dict):
            reason = "特征层技术数据缺失(features['technical'] 为空)"
            report_md = empty_report("neutral", reason)
            logger.warning(f"⚠️ [技术分析师] {reason}")
            return {
                "market_report": report_md,
                "messages": [],
                "market_tool_call_count": 0,
            }

        # --- 降级路径 2:数据稀疏(quality.rows < 阈值) ---
        if not quality_gate(tech):
            quality = tech.get("quality", {}) if isinstance(tech, dict) else {}
            rows = quality.get("rows", 0)
            reason = f"特征层技术数据稀疏(quality.rows={rows} < {30})"
            report_md = empty_report("neutral", reason)
            logger.warning(f"⚠️ [技术分析师] {reason}")
            return {
                "market_report": report_md,
                "messages": [],
                "market_tool_call_count": 0,
            }

        # --- 主路径:features 可信,准备 LLM prompt ---
        combined = tech.get("combined", {}) or {}
        daily = tech.get("daily", {}) or {}
        weekly = tech.get("weekly") or {}
        quality = tech.get("quality", {}) or {}

        snapshot_excerpt = _format_snapshot_excerpt(truncate_snapshot(daily.get("snapshot", {}), max_keys=15))
        trigger_signals = "\n".join(
            f"- {s}" for s in (combined.get("signals", []) or [])[:10]
        ) or "- (无触发信号)"

        variety_name = state.get("variety_name", full_symbol)
        exchange = state.get("exchange", "")
        daily_trend = daily.get("trend", {}) or {}
        weekly_trend = weekly.get("trend", {}) or {} if weekly else {}
        vol = combined.get("volatility", {}) or {}

        prompt_vars = dict(
            full_symbol=full_symbol,
            variety_name=variety_name,
            exchange=exchange,
            trade_date=trade_date,
            combined_direction=combined.get("direction", "neutral"),
            combined_strength=float(combined.get("strength", 0.0) or 0.0),
            daily_direction=daily_trend.get("direction", "neutral"),
            daily_strength=float(daily_trend.get("strength", 0.0) or 0.0),
            weekly_direction=(weekly_trend.get("direction", "neutral") if weekly else "N/A"),
            weekly_strength=(float(weekly_trend.get("strength", 0.0) or 0.0) if weekly else 0.0),
            oi_divergence=combined.get("oi_divergence", "neutral") or "neutral",
            vol_regime=vol.get("regime", "low") or "low",
            atr=_fmt(vol.get("atr")),
            atr_pctl=_fmt(vol.get("atr_ratio_pctl180")),
            snapshot_excerpt=snapshot_excerpt,
            trigger_signals=trigger_signals,
            quality_rows=quality.get("rows", 0),
            quality_coverage=_fmt(quality.get("coverage")),
            quality_freshness_days=_fmt(quality.get("data_freshness_days")),
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

            return {
                "market_report": report_md,
                "messages": [msg_out],
                "market_tool_call_count": 0,
            }

        except Exception as e:
            # --- 降级路径 3:LLM 调用抛错(网络/超时/限流) ---
            logger.error(f"❌ [技术分析师] LLM 调用失败,降级为 features 直拼: {e}")
            try:
                fallback_md = _build_fallback_report(full_symbol, combined, daily, weekly, quality)
            except Exception as inner_e:
                logger.error(f"❌ [技术分析师] fallback 也失败: {inner_e}")
                fallback_md = empty_report("neutral", f"features 与 LLM 均不可用: {e}; fallback 异常: {inner_e}")

            return {
                "market_report": fallback_md,
                "messages": [],
                "market_tool_call_count": 0,
            }

    return technical_analyst_node


__all__ = ["create_technical_analyst"]