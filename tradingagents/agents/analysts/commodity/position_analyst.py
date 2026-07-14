"""
position_analyst.py — 商品期货持仓分析师节点 (Phase 3b-ii)

输入:state['commodity_features']['positioning']
输出:state['sentiment_report'] = Markdown 持仓分析报告

持仓分析关注:
  - 前 20 名净多头 5 日变化(主力加减仓)
  - 持仓集中度(前 5 名占比)
  - 拥挤度 180d 分位(>0.9 视为极端反向风险)

输出字段名复用心方案:
  - sentiment_report (持仓情绪/拥挤度类比市场情绪)

LLM 调用失败降级为 features 直拼 Markdown。
"""
from __future__ import annotations

from typing import Any, Dict

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import AIMessage

from tradingagents.utils.logging_init import get_logger

from ._base import (
    empty_report,
    get_full_symbol,
    load_features,
    quality_gate,
)

logger = get_logger("default")

POSITION_SYSTEM_PROMPT = """你是一位资深的期货持仓分析师,解读主力席位持仓变化与拥挤度信号。

## 分析对象
- 标的代码:{full_symbol}
- 品种:{variety_name}
- 交易所:{exchange}
- 分析日期:{trade_date}

## 特征层(已计算,直接消费)

### 前 20 名持仓
- 净多头 5 日变化:{net_long_change_5d}
- 持仓集中度(前 5 占比):{concentration}
- 拥挤度 180d 分位:{crowding_pctl}

### 触发信号
{signals}

## 数据质量
- 数据条数:{quality_rows}

---

## 分析要求

1. **主力加减仓方向**:前 20 名净多头变化的方向(加多/减多/加空/减空)与幅度
2. **集中度解读**:前 5 名占比 > 60% 视为高集中,需警惕一致性预期破裂风险
3. **拥挤度反转信号**:180d 分位 > 0.9 时持仓过度拥挤,反向风险加大
4. **风险提示**:数据稀疏或信号矛盾时,降低 confidence 并明确标注

## 输出格式

使用 Markdown,300-500 字,结构:
- ## 综合判断(方向+强度+一句话)
- ## 主力加减仓解读
- ## 集中度与拥挤度
- ## 风险提示
"""


def _fmt(v: Any) -> str:
    if v is None:
        return "N/A"
    if isinstance(v, float):
        if v != v:
            return "N/A"
        return f"{v:.4f}".rstrip("0").rstrip(".")
    return str(v)


def _format_signals(signals: Any) -> str:
    if isinstance(signals, list):
        if not signals:
            return "- (无触发信号)"
        return "\n".join(f"- {s}" for s in signals[:8])
    return f"- {signals}" if signals else "- (无触发信号)"


def _derive_direction(
    net_long_change_5d: float,
    crowding_pctl: float,
    signals: list,
) -> str:
    """从持仓指标推导方向。"""
    bull = any(("净多增加" in s or "主力加多" in s or "净多头加仓" in s) for s in signals)
    bear = any(("净多减少" in s or "主力减多" in s or "空头加仓" in s) for s in signals)
    if net_long_change_5d is not None:
        if net_long_change_5d > 0.05:
            bull = True
        elif net_long_change_5d < -0.05:
            bear = True
    if crowding_pctl is not None and crowding_pctl > 0.9:
        # 极端拥挤,反向风险
        if bull:
            return "看多(注意拥挤反向风险)"
        if bear:
            return "看空(注意拥挤反向风险)"
    if bull and not bear:
        return "看多"
    if bear and not bull:
        return "看空"
    return "中性"


def _build_fallback_report(
    full_symbol: str,
    pos_block: Dict[str, Any],
    direction: str,
    signals: list,
    quality_rows: int,
) -> str:
    md = (
        f"# {full_symbol} 持仓分析报告(降级版本 — LLM 不可用)\n\n"
        f"## 综合判断\n方向:{direction}\n\n"
        f"## 关键指标\n"
        f"- 前 20 名净多头 5 日变化:{_fmt(pos_block.get('latest', {}).get('net_long_change_5d'))}\n"
        f"- 集中度:{_fmt(pos_block.get('latest', {}).get('concentration'))}\n"
        f"- 拥挤度 180d 分位:{_fmt(pos_block.get('latest', {}).get('crowding_pctl_180d'))}\n\n"
        f"## 触发信号\n{_format_signals(signals)}\n\n"
        f"## 数据质量\n- 数据条数:{quality_rows}\n\n"
        f"---\n_LLM 故障恢复后请重新提交任务以获得完整分析。_\n"
    )
    return md


def create_position_analyst(llm):
    """持仓分析师工厂函数。"""

    def position_analyst_node(state: dict) -> dict:
        full_symbol = get_full_symbol(state)
        trade_date = state.get("trade_date", "")

        logger.info(f"🎯 [持仓分析师] 启动: {full_symbol} @ {trade_date}")

        features = load_features(state)
        pos_block = features.get("positioning")

        # --- 降级 1:features 缺失 ---
        if not isinstance(pos_block, dict):
            reason = "持仓 features 缺失(features['positioning'] 为空)"
            return {
                "sentiment_report": empty_report("neutral", reason),
                "messages": [],
                "sentiment_tool_call_count": 0,
            }

        # --- 降级 2:数据稀疏 ---
        if not quality_gate(pos_block):
            reason = "持仓数据稀疏"
            return {
                "sentiment_report": empty_report("neutral", reason),
                "messages": [],
                "sentiment_tool_call_count": 0,
            }

        signals = pos_block.get("signals", []) or []
        net_long_change = pos_block.get("latest", {}).get("net_long_change_5d")
        concentration = pos_block.get("latest", {}).get("concentration")
        crowding_pctl = pos_block.get("latest", {}).get("crowding_pctl_180d")
        direction = _derive_direction(net_long_change, crowding_pctl, signals)
        quality_rows = pos_block.get("quality", {}).get("rows", 0)

        variety_name = state.get("variety_name", full_symbol)
        exchange = state.get("exchange", "")

        prompt_vars = dict(
            full_symbol=full_symbol,
            variety_name=variety_name,
            exchange=exchange,
            trade_date=trade_date,
            net_long_change_5d=_fmt(net_long_change),
            concentration=_fmt(concentration),
            crowding_pctl=_fmt(crowding_pctl),
            signals=_format_signals(signals),
            quality_rows=quality_rows,
        )

        try:
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", POSITION_SYSTEM_PROMPT),
                    MessagesPlaceholder(variable_name="messages"),
                ]
            ).partial(**prompt_vars)

            messages_payload = prompt.format_messages(
                messages=state.get("messages", []) or []
            )

            logger.info(f"🎯 [持仓分析师] 调用 LLM,full_symbol={full_symbol}")
            result = llm.invoke(messages_payload)

            if hasattr(result, "content"):
                content = result.content
                if not isinstance(content, str):
                    content = str(content) if content is not None else ""
            else:
                content = str(result) if result is not None else ""

            report_md = content
            logger.info(f"✅ [持仓分析师] LLM 报告生成: {len(report_md)} 字符")

            msg_out = result if hasattr(result, "content") else AIMessage(content=report_md)
            return {
                "sentiment_report": report_md,
                "messages": [msg_out],
                "sentiment_tool_call_count": 0,
            }

        except Exception as e:
            logger.error(f"❌ [持仓分析师] LLM 调用失败: {e}")
            try:
                fallback_md = _build_fallback_report(
                    full_symbol, pos_block, direction, signals, quality_rows
                )
            except Exception as inner_e:
                logger.error(f"❌ [持仓分析师] fallback 也失败: {inner_e}")
                fallback_md = empty_report("neutral", f"LLM 失败且 fallback 异常: {inner_e}")

            return {
                "sentiment_report": fallback_md,
                "messages": [],
                "sentiment_tool_call_count": 0,
            }

    return position_analyst_node


__all__ = ["create_position_analyst"]