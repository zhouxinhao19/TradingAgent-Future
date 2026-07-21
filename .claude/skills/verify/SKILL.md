---
name: verify
summary: Drive the commodity agent graph through its public propagate surface.
---

# Commodity agent runtime verification

Use this when commodity graph, analyst prompts, CIO rules, or evidence-chain logic changes.

1. Set `CHECKPOINTER_BACKEND=none` before graph construction so verification runs do not persist checkpoints.
2. Inject deterministic quick/deep LLM stubs through `CommodityGraphSetup`, but call the real public `CommodityTradingAgentsGraph.propagate()` implementation on a lightweight subclass. Do not call manager helpers directly.
3. Drive at least two flows:
   - A hard-risk flow where one risk dimension is R5 while CIO proposes `long`; observe `flat/0`, `max_position_pct=0`, the executed audit, rewritten Markdown, and matching evidence summary.
   - A CIO failure flow; observe three retries, fallback `hold/0`, and an executed SafetyOverride audit even when no rule changes the decision.
4. Include historical custom data with `time_columns/date_range` but no structured current observation; capture that both L2 and CIO prompts contain `无法获取当前时点数值，无法判断趋势`.
5. On Windows Git Bash run with `PYTHONUTF8=1` to prevent GBK/emoji logging noise:

```bash
PYTHONUTF8=1 python "$CLAUDE_JOB_DIR/tmp/verify_commodity_agent_runtime.py"
```

Capture the emitted decision/audit/evidence JSON and the `[投研总监|OVERRIDE] executed=True` log line.
