"""
fundamental_analyst.py — 商品期货基本面分析师节点 (Phase 3b-ii)

聚合 features 层三个模块:
  - basis:基差(现货 - 期货主力)
  - inventory:库存(周/月变化 + 180d 分位)
  - term_structure:期限结构(contango/backwardation/flat + carry_score)

输出:state['fundamentals_report'] = Markdown 基本面分析报告

决策规则(三因子矩阵):
  - 贴水 + 去库 + Backwardation → 强看多
  - 升水 + 累库 + Contango → 强看空
  - 信号冲突 → 中性,confidence 降低

LLM 调用失败降级为 features 直拼 Markdown。
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

FUNDAMENTAL_SYSTEM_PROMPT = """你是一位资深的期货基本面分析师,聚焦基差、库存、期限结构三因子。

## 分析对象
- 标的代码:{full_symbol}
- 品种:{variety_name}
- 交易所:{exchange}
- 分析日期:{trade_date}

## 特征层(已计算,直接消费)

### 基差
- 最新值:{basis_latest}
- 180d 分位:{basis_zscore}
- 20d 斜率:{basis_slope}
- 信号:{basis_signals}

### 库存
- 最新值:{inventory_latest}
- 环比变化:{inventory_wow}
- 180d 分位:{inventory_zscore}
- 信号:{inventory_signals}

### 期限结构
- 结构:{term_structure_type}
- Carry Score:{carry_score}
- 180d 分位:{term_zscore}
- 信号:{term_signals}

## 三因子矩阵判断

```
              库存去化          库存累库
基差贴水       强看多            看多(信号冲突)
基差升水       看空(信号冲突)    强看空
```

当前组合:**{combined_signal}**

## 数据质量
- 数据条数:{quality_rows}
- 覆盖率:{quality_coverage}

---

## 分析要求

1. **三因子解读**:基差(代表现货-期货预期)、库存(代表供需松紧)、期限结构(代表市场对未来供需预期)
2. **矛盾信号识别**:信号冲突时降低 confidence,在结论中明确说明
3. **基本面结论**:给出方向(看多/看空/中性)+ 强度 + 关键证据 3-5 条
4. **风险提示**:数据稀疏或信号矛盾时,在风险段标注

## 输出格式

使用 Markdown,400-700 字,结构:
- ## 综合判断(方向+强度+一句话)
- ## 三因子解读(基差/库存/期限结构各一段)
- ## 信号冲突与置信度
- ## 风险提示
"""


def _format_signal_list(signals: Any) -> str:
    """把 list[str] 格式化为多行 markdown,非 list 转 str。"""
    if isinstance(signals, list):
        if not signals:
            return "- (无触发信号)"
        return "\n".join(f"- {s}" for s in signals[:8])
    if signals is None:
        return "- (无触发信号)"
    return f"- {signals}"


def _fmt(v: Any) -> str:
    """数值安全格式化。"""
    if v is None:
        return "N/A"
    if isinstance(v, float):
        if v != v:
            return "N/A"
        return f"{v:.4f}".rstrip("0").rstrip(".")
    return str(v)


def _three_factor_signal(
    basis_signals: List[str],
    inventory_signals: List[str],
    term_signals: List[str],
) -> str:
    """三因子矩阵判断,返回中文结论。

    简化规则:用 keyword 命中判断方向。
    """
    basis_bull = any(("贴水" in s or "升水" in s and "低" in s) for s in basis_signals)
    basis_bear = any("升水" in s and "低" not in s for s in basis_signals)
    inv_bull = any("去库" in s or "库存下降" in s for s in inventory_signals)
    inv_bear = any("累库" in s or "库存上升" in s for s in inventory_signals)
    term_bull = any("Backwardation" in s or "贴水" in s for s in term_signals)
    term_bear = any("Contango" in s or "升水" in s for s in term_signals)

    bull_count = sum([basis_bull, inv_bull, term_bull])
    bear_count = sum([basis_bear, inv_bear, term_bear])

    if bull_count >= 2 and bear_count == 0:
        return "强看多(贴水+去库/Backwardation 至少 2 项支持)"
    if bear_count >= 2 and bull_count == 0:
        return "强看空(升水+累库/Contango 至少 2 项支持)"
    if bull_count > bear_count:
        return "看多(信号部分支持)"
    if bear_count > bull_count:
        return "看空(信号部分支持)"
    return "中性(信号冲突或不足)"


def _build_fallback_report(
    full_symbol: str,
    basis_block: Dict[str, Any],
    inventory_block: Dict[str, Any],
    term_block: Dict[str, Any],
    combined_signal: str,
    quality_rows: int,
) -> str:
    """LLM 失败时,直接用 features 拼 Markdown。"""
    md = (
        f"# {full_symbol} 基本面分析报告(降级版本 — LLM 不可用)\n\n"
        f"## 综合判断\n{combined_signal}\n\n"
        f"## 三因子解读\n\n"
        f"### 基差\n{_format_signal_list(basis_block.get('signals', []))}\n\n"
        f"### 库存\n{_format_signal_list(inventory_block.get('signals', []))}\n\n"
        f"### 期限结构\n{_format_signal_list(term_block.get('signals', []))}\n\n"
        f"## 数据质量\n"
        f"- 数据条数:{quality_rows}\n\n"
        f"---\n_LLM 故障恢复后请重新提交任务以获得完整分析。_\n"
    )
    return md


def create_fundamental_analyst(llm):
    """基本面分析师工厂函数。"""

    def fundamental_analyst_node(state: dict) -> dict:
        full_symbol = get_full_symbol(state)
        trade_date = state.get("trade_date", "")

        logger.info(f"💼 [基本面分析师] 启动: {full_symbol} @ {trade_date}")

        features = load_features(state)

        basis_block = features.get("basis")
        inventory_block = features.get("inventory")
        term_block = features.get("term_structure")

        # --- 降级 1:三个模块全部缺失 ---
        if not any(isinstance(b, dict) for b in [basis_block, inventory_block, term_block]):
            reason = "基差/库存/期限结构三因子 features 全部缺失"
            return {
                "fundamentals_report": empty_report("neutral", reason),
                "messages": [],
                "fundamentals_tool_call_count": 0,
            }

        # --- 准备信号聚合 ---
        basis_signals = (basis_block or {}).get("signals", []) if isinstance(basis_block, dict) else []
        inventory_signals = (inventory_block or {}).get("signals", []) if isinstance(inventory_block, dict) else []
        term_signals = (term_block or {}).get("signals", []) if isinstance(term_block, dict) else []
        combined_signal = _three_factor_signal(basis_signals, inventory_signals, term_signals)

        # 取 quality(任一模块)
        quality_rows = (
            (basis_block or inventory_block or term_block or {}).get("quality", {}).get("rows", 0)
        )

        # --- 数据稀疏判断(三个模块加起来 rows < 30) ---
        total_rows = sum(
            int((b or {}).get("quality", {}).get("rows", 0) or 0)
            for b in [basis_block, inventory_block, term_block]
            if isinstance(b, dict)
        )
        if total_rows < 30:
            reason = f"三因子数据稀疏(total_rows={total_rows} < 30)"
            return {
                "fundamentals_report": empty_report("neutral", reason),
                "messages": [],
                "fundamentals_tool_call_count": 0,
            }

        # --- 主路径:features 可信,LLM 调用 ---
        basis_latest = _fmt((basis_block or {}).get("latest", {}).get("basis_rate"))
        basis_zscore = _fmt((basis_block or {}).get("stats", {}).get("zscore_180d"))
        basis_slope = _fmt((basis_block or {}).get("stats", {}).get("slope_20d"))

        inv_latest = _fmt((inventory_block or {}).get("latest", {}).get("inventory"))
        inv_wow = _fmt((inventory_block or {}).get("latest", {}).get("wow_change"))
        inv_zscore = _fmt((inventory_block or {}).get("stats", {}).get("zscore_180d"))

        term_type = (term_block or {}).get("latest", {}).get("structure", "N/A")
        carry_score = _fmt((term_block or {}).get("latest", {}).get("carry_score"))
        term_zscore = _fmt((term_block or {}).get("stats", {}).get("zscore_180d"))

        variety_name = state.get("variety_name", full_symbol)
        exchange = state.get("exchange", "")

        prompt_vars = dict(
            full_symbol=full_symbol,
            variety_name=variety_name,
            exchange=exchange,
            trade_date=trade_date,
            basis_latest=basis_latest,
            basis_zscore=basis_zscore,
            basis_slope=basis_slope,
            basis_signals=_format_signal_list(basis_signals),
            inventory_latest=inv_latest,
            inventory_wow=inv_wow,
            inventory_zscore=inv_zscore,
            inventory_signals=_format_signal_list(inventory_signals),
            term_structure_type=term_type,
            carry_score=carry_score,
            term_zscore=term_zscore,
            term_signals=_format_signal_list(term_signals),
            combined_signal=combined_signal,
            quality_rows=quality_rows,
            quality_coverage=_fmt((basis_block or {}).get("quality", {}).get("coverage")),
        )

        try:
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", FUNDAMENTAL_SYSTEM_PROMPT),
                    MessagesPlaceholder(variable_name="messages"),
                ]
            ).partial(**prompt_vars)

            messages_payload = prompt.format_messages(
                messages=state.get("messages", []) or []
            )

            logger.info(f"💼 [基本面分析师] 调用 LLM,full_symbol={full_symbol}")
            result = llm.invoke(messages_payload)

            if hasattr(result, "content"):
                content = result.content
                if not isinstance(content, str):
                    content = str(content) if content is not None else ""
            else:
                content = str(result) if result is not None else ""

            report_md = content
            logger.info(f"✅ [基本面分析师] LLM 报告生成: {len(report_md)} 字符")

            msg_out = result if hasattr(result, "content") else AIMessage(content=report_md)
            return {
                "fundamentals_report": report_md,
                "messages": [msg_out],
                "fundamentals_tool_call_count": 0,
            }

        except Exception as e:
            logger.error(f"❌ [基本面分析师] LLM 调用失败: {e}")
            try:
                fallback_md = _build_fallback_report(
                    full_symbol,
                    basis_block or {},
                    inventory_block or {},
                    term_block or {},
                    combined_signal,
                    quality_rows,
                )
            except Exception as inner_e:
                logger.error(f"❌ [基本面分析师] fallback 也失败: {inner_e}")
                fallback_md = empty_report("neutral", f"LLM 失败且 fallback 异常: {inner_e}")

            return {
                "fundamentals_report": fallback_md,
                "messages": [],
                "fundamentals_tool_call_count": 0,
            }

    return fundamental_analyst_node


__all__ = ["create_fundamental_analyst"]