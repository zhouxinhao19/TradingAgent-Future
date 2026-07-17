"""
executive_decision_maker.py — CIO 最终决策节点 (Phase 3b-ii + L2-L4 合并)

[DEPRECATED — commodity 路径]

该文件的 commodity 分支（Phase 3b-ii-B）已被 Phase 4 投研总监节点替代。
commodity_graph.py 已不再将 CIO 注册为节点，commodity 分支仅作为 fallback 保留。

CIO 整合两层决策,输出最终可执行决策:
  - 推理分析师报告 → investment_plan
  - 风控评估       → final_trade_decision

输出 state['final_decision'] = Markdown 报告(决策方向 + 合约 + 入场 + 止损 + 目标 + 持仓手数 + 风险敞口)
"""
from __future__ import annotations

from typing import Any, Dict

from tradingagents.utils.logging_init import get_logger

logger = get_logger("default")


COMMODITY_CIO_SYSTEM_PROMPT = """你是大宗商品期货投资决策委员会(CIO)的最终决策者。

你的职责是综合以下两层决策,给出**明确可执行**的最终指令:

### 1. 推理分析师综合报告（估值-驱动矩阵 + 多空对照 + 情景推演）
{investment_plan}

推理分析师的 `investment_plan` 是 JSON 格式，包含"估值驱动矩阵"、"多空对照表"、"三种情景推演"三大模块。请重点关注：
- 估值驱动矩阵中的"综合估值判断"和"核心驱动"→ 作为你的方向判断基准
- 多空对照表中的"关键分歧"→ 识别最核心的争议点
- 情景推演中的"触发条件"和"风险节点"→ 作为决策边界和风险控制依据

### 2. 风控评估(激进 / 中性 / 保守三方意见)
{final_trade_decision}

---

## 决策要素(必须明确给出)

1. **方向**:做多 / 做空 / 平仓(明确,不允许模棱两可)
2. **合约**:主力合约代码(如 RB2501.SHF),不允许模糊指代
3. **入场价位**:具体数值(以交易所报价单位)
4. **止损价位**:具体数值(单笔最大亏损不超过账户 1-2%)
5. **目标价位**:具体数值(分批止盈:1R / 2R / 3R)
6. **持仓手数**:具体数量(保证金占用不超过账户 20%)
7. **持有周期**:日内 / 短线(1-5 日) / 波段(1-4 周) / 趋势(1-3 月)
8. **置信度**:0-1 之间的数值
9. **风险敞口**:账户百分比 + 杠杆倍数
10. **决策理由**:基于以上两层证据,300-500 字综合论证

## ⚠️ 严格要求

- 决策必须**明确可执行**,不允许"建议观望"或"需要更多信息"
- 入场/止损/目标价位**必须具体数值**,绝对不能 null 或"待定"
- 合约代码必须来自研究报告中的真实数据
- 决策理由必须直接回应两层证据,不得凭空捏造

## 输出格式

使用 Markdown,结构:
```
# {full_symbol} 最终决策

## 决策摘要
- **方向**:做多 / 做空 / 平仓
- **合约**:主力合约代码
- **入场**:xxx 元/吨
- **止损**:xxx 元/吨
- **目标**:xxx 元/吨(1R / 2R / 3R)
- **持仓**:x 手
- **持有周期**:xxx
- **置信度**:0.xx
- **风险敞口**:账户 x%,杠杆 x 倍

## 决策理由
(300-500 字综合论证)

## 风险提示
(列出 2-3 条主要风险)
```

请用中文撰写。"""


COMMODITY_DEFAULT_DECISION = """# {full_symbol} 最终决策(默认)

## 决策摘要
- **方向**:平仓
- **合约**:—
- **入场**:—
- **止损**:—
- **目标**:—
- **持仓**:0 手
- **持有周期**:—
- **置信度**:0.00
- **风险敞口**:0%

## 决策理由
由于技术原因无法生成综合决策(LLM 不可用或证据不完整),基于风险控制原则,默认采取平仓策略,等待三层证据(研究/交易/风控)完备后重新评估。

## 风险提示
1. 信息不足,避免盲目操作
2. 保持现有仓位退出,等待更明确的市场信号
3. 控制保证金占用,避免在不确定性高的情况下做出激进决策
"""


def create_executive_decision_maker(llm):
    """CIO 最终决策工厂函数。"""

    def cio_node(state: dict) -> dict:
        full_symbol = state.get("full_symbol") or state.get("company_of_interest", "Unknown")
        asset_type = state.get("asset_type", "stock")

        logger.info(f"👔 [CIO] 最终决策启动: {full_symbol} (asset_type={asset_type})")

        # 收集两层决策
        investment_plan = state.get("investment_plan", "(空)")
        final_trade_decision = state.get("final_trade_decision", "(空)")

        # === Commodity 路径: DEPRECATED (Phase 4 已改用投研总监) ===
        if asset_type == "commodity":
            logger.warning(
                f"⚠️ [CIO] commodity 路径已被 Phase 4 投研总监替代"
                f"(commodity_graph 中已不再路由到 CIO 节点)"
            )
            return {
                "final_decision": COMMODITY_DEFAULT_DECISION.format(full_symbol=full_symbol),
                "messages": [],
                "cio_decision_timestamp": "now",
            }

        # === Stock 路径:占位(Phase 3b-ii 不实现,CIO 由现有 decision 节点处理) ===
        logger.warning(f"⚠️ [CIO] stock 路径未实现(Phase 3b-ii 仅交付 commodity),返回 None")
        return {
            "final_decision": None,
            "messages": [],
            "cio_decision_timestamp": "now",
        }

    return cio_node