# 审查问题修复计划（修订版）

## 审查范围

基于 `main` 分支（2026-07-22），对 4 个 QA 问题进行代码级审查，追溯数据链路。

---

## 问题 1（🔴 高）：拥挤度 0.4762 判为 R5

### 审查结论

**确认存在系统性单位不匹配 bug**，影响两个维度（拥挤度 + 波动率）。

### 数据链路

```
percentile_rank() [_helpers.py:224]
  → 返回 float((tail <= last).mean())，值域 [0, 1]
  → 存入 snapshot.crowding_pctl_180d [positioning.py:673]

atr_ratio.rolling(180).apply(mean) [technical.py:397-400]
  → 返回 0~1
  → 存入 technical.combined.volatility.atr_ratio_pctl180

compute_risk_assessment() [investment_director.py:384 / 438]
  → 将 0~1 的值直接传入 _rate_crowding() / _rate_percentile()
  → 这两个函数阈值按 0-100 写
```

### 影响

| 维度 | 真实值 | 当前评级 | 正确评级 | 影响 |
|---|---|---|---|---|
| 持仓拥挤度 0.4762 | 47.62% | **R5**（`0.4762 < 10`） | R2 | 风控卡死所有交易 |
| 波动率 0.9 | 90% | **R1**（`0.9 < 20`） | R4 | 高波动被判极低风险 |

### 测试问题

`test_commodity_decision_chain.py` 中所有 `crowding_pctl_180d` 和 `atr_ratio_pctl180` 的测试值都按 0-100 传入（如 `10.0`, `98.0`, `90.0`），与真实数据 0~1 不匹配。测试通过只是自洽，不代表生产正确。

### 需修改

| 文件 | 行 | 修改 |
|---|---|---|
| `investment_director.py` | 299-310 | `_rate_crowding()` 入口加 `if pctl <= 1: pctl *= 100` |
| 同上 | 283-296 | `_rate_percentile()` 入口加 `if pctl <= 1: pctl *= 100` |
| `test_commodity_decision_chain.py` | 多处 | 所有 `crowding_pctl_180d`/`atr_ratio_pctl180` 测试值改为 0~1 比例 |

---

## 问题 2（🟡 中 → **🔴 高**）：持仓数据 1,870 vs 22,205

### 审查结论

**发现深层 bug**：评估后提升为 🔴 高。`_prepare()` 列名规范化缺陷导致 AKShare 持仓排名数据（SHFE/INE/CZCE 等）的 `"多单持仓"`/`"空单持仓"` 列无法映射到 `"long_top20"`/`"short_top20"`，所有持仓指标全为 NaN。

### 数据链路（两条独立路径）

**路径 A：前端持仓 Tab（`get_holding_position` → `futures_hold_pos_sina`）**
```
ak.futures_hold_pos_sina(symbol=indicator, contract=symbol, date=d)
  → 返回 DataFrame: [会员简称, 成交量, 多单持仓, 空单持仓]
  → 前端 loadHoldingPositionAll() 合并 3 个指标，按会员汇总
  → totals: {成交量, 多单持仓, 空单持仓, 净持仓}
  → 22,205 很可能 = 多单持仓 totals（所有会员合计）
  → 1,870 很可能 = 成交量 totals（所有会员合计）
```

**路径 B：持仓特征（`get_position_rank_history` → 各交易所 rank table）**
```
ak.get_shfe_rank_table(date=date_str) [SHFE/INE]
  → 返回 Dict[contract, DataFrame]
  → 每合约 DataFrame: [会员简称, 总成交量, 多单持仓, 空单持仓, ...]
  → 经过 _prepare() 列名规范化

ak.futures_dce_position_rank(date=date_str, vars_list=...) [DCE/GFEX]
  → 返回 Dict[contract, DataFrame]（列名与 SHFE 不同）

ak.get_rank_table_czce(date=date_str) [CZCE]
  → 返回 Dict[contract, DataFrame]
```

### 根因：列名规范化缺失

`COLUMN_ALIASES` [_helpers.py:41-42] 中没有包含 `"多单持仓"` / `"空单持仓"`：

```python
"long_top20": ["long_top20", "long_open_interest_top20", "long_open_interest", "前20多头"],
"short_top20": ["short_top20", "short_open_interest_top20", "short_open_interest", "前20空头"],
```

添加 `"多单持仓"` 和 `"空单持仓"` 即可修复。但注意：这些是**每行一个会员的长表**，需要按合约聚合（sum）才能得到前 20 名合计。

### 测试覆盖缺失

`test_commodity_features.py` 中 positioning 测试直接使用英文列名 `"long_top20"`/`"short_top20"`，没有测试中文列名输入。所以 `normalize_columns` 的中文映射缺陷从未被触发。

### 需修改

| 文件 | 行 | 修改 |
|---|---|---|
| `_helpers.py` | 41-42 | 在 `COLUMN_ALIASES` 的 `long_top20`/`short_top20` 别名中加 `"多单持仓"`/`"空单持仓"` |
| 同上 | 51-71 | 或在 `CHINESE_TO_CANONICAL` 中加 `"多单持仓" → "long_top20"`/`"空单持仓" → "short_top20"` |
| `positioning.py` | 227 (in `_aggregate_contracts`) | 在 `_prepare` 之后加一步：按合约对每个会员汇总行求和（`groupby("symbol")` 或取 rank=999 的合计行） |
| `test_commodity_features.py` | 794-801 | 新增测试用例：用中文列名 `"多单持仓"`/`"空单持仓"` 输入，验证 `long_top20`/`short_top20` 正确 |

---

## 问题 3（🟡 中）：`research_brief_raw` 截断

### 审查结论

确认存在，规模型问题。

### 数据链路

`commodity_graph.py` 中 `_build_conclusion()` 和 `_build_layers()` 函数：

| 位置 | 行 | 当前截断 | 建议值 |
|---|---|---|---|
| `_build_conclusion → research_brief_raw` | 470 | 500 | **2000** |
| `_build_conclusion → reasoning` | 476 | 200 | 保持 200（仅核心叙事） |
| `_build_conclusion → raw_text` | 477 | 500 | **2000** |
| `_build_layers → L2 raw` | 1131 | 500 | 保持 500（仅回退路径） |
| `_build_layers → L3 research_brief_raw` | 1164 | 1000 | **3000** |
| `_build_layers → L3 final_decision_raw` | 1172 | 500 | **2000** |

CIO 完整分析通常 2000+ 字符，500 字符截断丢掉了大部分推理内容。

### 需修改

| 文件 | 行 | 修改 |
|---|---|---|
| `commodity_graph.py` | 470, 477, 1164, 1172 | 截断值提升 |

---

## 问题 4（🟢 低）：新闻分析师 bullish 但 L2 判定 neutral

### 审查结论

确认存在，属于设计阈值差异，非 bug。

### 数据链路

```
L1 新闻分析师: news_analyst.py:412-427
  _derive_news_direction()
    threshold = 0.25  →  |ratio| > 0.25 → bullish/bearish

L2 投资总监: investment_director.py:540-560
  sentiment_ratio > 0.6 → 偏多
  sentiment_ratio >= 0.4 → 中性（0.4-0.6 区间）
  else → 偏空
```

当 `sentiment_ratio = 0.3`（31% 净多，已偏多但不算强），L1 输出 bullish，L2 判为中性（0.3 < 0.4）。

### 需修改

| 文件 | 行 | 修改 |
|---|---|---|
| `investment_director.py` | 545-550 | 阈值从 0.6/0.4 改为 0.25/-0.25（与 L1 对齐） |

---

## 修复优先级

```
P0 ─── 问题 1（单位不匹配 bug → 错误的风险评级）
P0 ─── 问题 2（列名规范化缺失 → 持仓特征全 NaN）
P1 ─── 问题 3（截断 → 用户看不到完整分析）
P2 ─── 问题 4（阈值对齐 → 分析师输出与风控不一致）
```

### 验证方式

1. 问题 1: 运行 `pytest tests/test_commodity_decision_chain.py -k "crowding" -v` 确认测试通过
2. 问题 2: 运行 `pytest tests/test_commodity_features.py -k "positioning" -v` 确认中文列名测试通过
3. 问题 3: 检查 `commodity_graph.py` 截断值是否提升
4. 问题 4: 运行 `pytest tests/test_commodity_decision_chain.py -k "sentiment" -v` 确认