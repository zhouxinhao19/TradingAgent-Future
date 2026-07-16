# Phase 3b — 多源情报 + 分析师扩展(进度文档)

> 对应 plan: [`docs/plans/stock-to-commodity.md`](../plans/stock-to-commodity.md) §1.4
> 创建日期: 2026-07-14 | 最后更新: 2026-07-16
> **状态: ✅ 全部完成**

---

## 一、总览

Phase 3b 是"股票→大宗商品"改造的第五个阶段,核心目标是为商品品种建立 **Features 纯规则层 + 多分析师LLM决策链**,使系统能从数据层能力升级为可自动生成交易决策的分析平台。

**架构演进**: provider → **features(纯规则)** → **analyst(可选LLM)** → **四阶段决策链(多空辩论→交易员→风控→CIO)**

### 1.1 六个子阶段

| 子阶段 | 目标 | 关键文件 | 状态 |
|---|---|---|---|
| **3b-i Features 层** | 纯规则特征工程(零LLM) | `tradingagents/features/commodity/` 6 模块 | ✅ 完成 |
| **3b-ii-A 4 个 commodity analyst** | LLM 驱动的技术/基本面/持仓/新闻分析师 | `tradingagents/agents/analysts/commodity/` | ✅ 完成 |
| **3b-ii-B 决策链 8 节点 commodity 化** | 多空辩论→交易员→风控→CIO 全线接入商品 | 8 个 stock 节点加 `COMMODITY_*_PROMPT` 分支 | ✅ 完成 |
| **3b-ii-C 子图接线** | `CommodityTradingAgentsGraph` 子类 | `tradingagents/graph/commodity_graph.py` | ✅ 完成 |
| **3b-ii-D 路由 + Vue** | 分析提交/查询 API + 前端 UI | `app/routers/commodity/analysis.py` + `Analysis.vue` | ✅ 完成 |
| **3b-ii-E 端到端实测** | DeepSeek 实测全链路 | `tests/test_commodity_decision_chain.py` | ✅ 完成 |

### 1.2 累计测试结果

| 测试文件 | 数量 | 覆盖率 |
|---|---|---|
| `tests/test_commodity_features.py` | 97 | 6 模块 schema + 信号 + 边界 + 跨模块一致性 |
| `tests/test_commodity_analyst.py` | 45 | 4 个 analyst MagicMock LLM + 边界 + Pydantic |
| `tests/test_commodity_decision_chain.py` | 26 | 8 节点 commodity 分支 + full chain + edge |
| `tests/test_commodity_cio.py` | 6 | CIO 节点 commodity 分支 |
| **合计** | **174** | **全部 0 失败** |

> 另有 `test_commodity_data_layer.py` 90 测试(独立于 Phase 3b),合并测试时 **264 测试全过**。

---

## 二、3b-i Features 层(纯规则,零 LLM)

### 2.1 文件清单

| 文件 | 入口函数 | 输入 | 关键输出 | 状态 |
|---|---|---|---|---|
| `_helpers.py` | `normalize_columns` / `safe_float` / `zscore` / `percentile_rank` | DataFrame | 列名归一化 + 统计工具 | ✅ |
| `technical.py` | `compute_technical_metrics(df, include_weekly=True)` | 日线 OHLCV | 50+ 指标 + OI 背离 + 三层周期 + 综合评分 | ✅ |
| `basis.py` | `compute_basis_metrics(df, symbol=None)` | 基差历史 | 180d 分位 + 升贴水信号 | ✅ |
| `inventory.py` | `compute_inventory_metrics(df, symbol=None)` | 库存数据 | WoW/MoM 变化 + 跳变标志 | ✅ |
| `positioning.py` | `compute_positioning_metrics(df_or_dict, symbol=None)` | 持仓排名 | 前20净多变化 + 拥挤度 | ✅ |
| `term_structure.py` | `compute_term_structure_metrics(df, var=None)` | 展期收益率 | contango/backwardation + carry_score | ✅ |
| `news_sentiment.py` | `compute_news_sentiment_metrics(inp, source='all')` | 新闻列表 | 多空比 + 分类计数 | ✅ |

### 2.2 统一输出 schema

```python
{
  "latest":   {指标名: float},           # 最常用值
  "stats":    {zscore_180d, slope_20d}, # 统计特征
  "signals":  ["rule-based 信号文字"],  # 触发的规则信号
  "snapshot": {全量指标},               # 供 LLM 消费
  "quality":  {rows, coverage, data_freshness_days}
}
```

### 2.3 关键约束已满足

- ✅ 纯函数,零 LLM,零外部 API
- ✅ 中文/英文列名双向兼容
- ✅ 输出 schema 跨 6 模块一致(`TestCrossModuleSchemaConsistency` 验证)
- ✅ 数据不足/空输入时返回 `empty_result` 结构
- ✅ 列存在但全 NaN 时不抛错

---

## 三、3b-ii-A 4 个 Commodity Analyst

### 3.1 设计原则

- **字段复用**:analyst 写 `market_report` / `fundamentals_report` / `sentiment_report` / `news_report` 四个 stock 字段名
- **LLM 非必须**:technical/fundamental/position 可直接复用 features 结构化数据;news_analyst 必须调 LLM 做叙事摘要
- **测试模式**:MagicMock LLM,`llm.invoke = MagicMock(return_value=MagicMock(content="[MOCK] 文本"))`

### 3.2 分析师节点

| 分析师 | 文件 | 输入(features) | 输出 Pydantic |
|---|---|---|---|
| Technical | `technical_analyst.py` | `commodity_features.technical.snapshot` | `TechnicalReport`(方向/强度/关键位) |
| Fundamental | `fundamental_analyst.py` | `{basis, inventory, term_structure}` 聚合 | `FundamentalReport`(基差/库存/期限) |
| Position | `position_analyst.py` | `commodity_features.positioning.snapshot` | `PositionReport`(集中度/拥挤度) |
| News | `news_analyst.py` | `commodity_features.news_sentiment` + 新闻原文 | `NewsReport`(叙事/情感/事件) |

---

## 四、3b-ii-B 决策链 Commodity 化

### 4.1 最小侵入方案(asset_type 分支)

在每个 stock 节点文件顶部加 `COMMODITY_*_PROMPT` 常量 + 节点函数体内 `if asset_type == "commodity"` 分支:

```python
if asset_type == "commodity":
    prompt = COMMODITY_BULL_PROMPT.format(
        full_symbol=state.get("full_symbol") or ticker,
        variety_name=state.get("variety_name", ""),
        **features_data
    )
else:
    prompt = f"""原 stock prompt (不变)"""
```

### 4.2 已 commodity 化的 8 个节点

| # | 节点 | 文件 | COMMODITY 常量 |
|---|---|---|---|
| 1 | 看涨研究员 | `bull_researcher.py` | `COMMODITY_BULL_PROMPT` |
| 2 | 看跌研究员 | `bear_researcher.py` | `COMMODITY_BEAR_PROMPT` |
| 3 | 研究经理(裁判) | `research_manager.py` | `COMMODITY_RESEARCH_MANAGER_PROMPT` |
| 4 | 交易员 | `trader.py` | `COMMODITY_TRADER_SYSTEM_PROMPT` |
| 5 | 激进风控 | `aggresive_debator.py` | `COMMODITY_AGGRESSIVE_PROMPT` |
| 6 | 保守风控 | `conservative_debator.py` | `COMMODITY_CONSERVATIVE_PROMPT` |
| 7 | 中性风控 | `neutral_debator.py` | `COMMODITY_NEUTRAL_PROMPT` |
| 8 | 风控经理 | `risk_manager.py` | `COMMODITY_RISK_MANAGER_PROMPT` + `COMMODITY_DEFAULT_DECISION` |

### 4.3 CIO 节点

`tradingagents/agents/managers/executive_decision_maker.py` 新增 `ExecutiveDecisionMaker`:
- 综合三层决策(研究员→交易员→风控)
- commodity 分支:考虑基差/库存/期限结构/杠杆/换月
- 输出 `final_decision`(action/confidence/entry/stop_loss/targets)

---

## 五、3b-ii-C 子图接线

### 5.1 文件

`tradingagents/graph/commodity_graph.py` 包含 3 个类:

| 类 | 继承自 | 功能 |
|---|---|---|
| `CommodityPropagator` | `Propagator` | 创建含 `asset_type="commodity"` 的初始 AgentState |
| `CommodityGraphSetup` | `GraphSetup` | 注册 4 个 commodity analyst + 8 个决策链节点 + CIO |
| `CommodityTradingAgentsGraph` | `TradingAgentsGraph` | 重写 `setup_graph()` + `propagate(full_symbol, date, ...)` |

### 5.2 关键设计

- `propagate()` 的 `auto_features` 参数:如果为 `True`,自动调用 `compute_all_features_from_provider` 填充 `commodity_features`
- `provider` 参数:调用方可传入 mock provider 用于测试/离线模式
- 父类 `TradingAgentsGraph.propagate` 完全复用(stock 路径零改动)

---

## 六、3b-ii-D 路由 + Vue

### 6.1 后端路由

`app/routers/commodity/analysis.py`:

| 端点 | 方法 | 功能 |
|---|---|---|
| `POST /api/commodity/{full_symbol}/analyze` | POST | 提交分析任务(后台队列,异步完成) |
| `GET /api/commodity/{full_symbol}/reports` | GET | 查历史报告列表 |
| `GET /api/commodity/reports/recent` | GET | 查最近 N 个报告(全局) |

支持参数: `trade_date`(默认当天) / `force`(强制重分析) / `auto_features`(是否自动拉 features)

**前端的提交→轮询分离**:`submitAnalysis()` 立即释放按钮 → `startPolling()` 后台每 5s 检查结果,互不阻塞。`onUnmounted` 清理轮询定时器,防止组件销毁后继续轮询。

### 6.2 前端 Vue

`frontend/src/views/Commodity/Analysis.vue`:
- 合约下拉选择(从品种列表获取)
- 交易日期输入(默认当天)
- 提交按钮(15 秒安全兜底,防止 API 卡死)
- 结果展示区(最新报告内容 + 历史报告列表)

---

## 七、3b-ii-E 端到端实测

### 7.1 测试入口

```python
from tradingagents.graph.commodity_graph import CommodityTradingAgentsGraph
g = CommodityTradingAgentsGraph(config={
    "llm_provider": "deepseek",
    "deep_think_llm": "deepseek-v4-flash",
    "quick_think_llm": "deepseek-v4-flash",
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "online_tools": False,
    "memory_enabled": False,
    "project_dir": str(Path.cwd()),
})
state, decision = g.propagate(
    full_symbol="CU2501.SHF", trade_date="2026-07-14",
    auto_features=True, provider=MockProvider(),
)
```

### 7.2 链路日志

| 节点 | 输出长度 | LLM |
|---|---|---|
| 4 个 commodity analyst | 1001 / 1225 / 791 / 986 字符 | features 结构化 + LLM 可选 |
| Bull / Bear Researcher | ~3000 字 / ~3000 字 | DeepSeek v4-flash |
| Research Manager | 1800 字 | DeepSeek v4-flash |
| Trader | 1570 字(含凯利公式) | DeepSeek v4-flash |
| 3× Risk Debator | 28.4s / 23.0s / 50.6s | DeepSeek v4-flash |
| Risk Judge | 3537 字 | DeepSeek v4-flash |
| CIO | 1383 字(commodity 风格) | DeepSeek v4-flash |

### 7.3 性能

| 指标 | 值 |
|---|---|
| LLM 模型 | `deepseek / deepseek-v4-flash` |
| API base | `https://api.deepseek.com` |
| 总耗时 | ~280 秒(约 4 分 40 秒) |
| 总 LLM 调用 | **13 次**(4 analyst + 2 researcher + 1 manager + 1 trader + 3 risk + 1 judge + 1 CIO) |
| 估算总 token | ~42k 输入 / ~18k 输出 |

### 7.4 CIO 实测决策摘要(CU2504.SHF)

```json
{
  "action": "short",
  "confidence": 0.65,
  "key_levels": {
    "entry_range": "70800–71200 元/吨",
    "stop_loss": "72200 元/吨",
    "targets": ["69500 (1R)", "68500 (2R)"]
  },
  "size": "1 手 × 15 倍杠杆",
  "holding_period": "1–2 周",
  "highlights": [
    "CIO 自动检测 CU2501.SHF 已过期,切换到 CU2504.SHF",
    "引用库存 180d 分位 0.9333 + 技术面日线空头占优",
    "风险敞口按账户 6% 反推仓位和杠杆"
  ]
}
```

### 7.5 链路修复记录

- **问题**:首轮实测 `asset_type` 字段缺失 → CIO 走 stock prompt,生成 stock 风格决策
- **修复**:`AgentState` TypedDict 补 10 个 commodity 字段(`asset_type` 等)
- **验证**:修复后 CIO 输出 1383 字 commodity 风格决策,涵盖基差/库存/期限结构/杠杆

---

## 八、关键 Commit 历史

| SHA | 内容 | 子阶段 |
|---|---|---|
| `41f7b939` | feat(phase-3b-ii-A): commodity technical analyst + features 层 | 3b-i + 3b-ii-A |
| `2948afa8` | feat(phase-3b-ii-A): 完成 fundamental/position/news 三 analyst | 3b-ii-A |
| `3c8a4cd7` | feat(phase-3b-ii-B): 决策链节点 commodity 化 + CIO | 3b-ii-B |
| `8e130fa7` | (features 修复) | 3b-i |
| `3d5dc602` | feat(phase-3b-ii-C): 子图 + Propagator | 3b-ii-C |
| `93930dff` | feat(phase-3b-ii-D/E): 路由 + Vue + E2E | 3b-ii-D/E |
| `bb34fbb9` | fix: 主力连续 fallback(280 测试) | P0 修复 |
| `792a9083` | fix: 详情页 5 UX bug | 详情页修复 |
| `8b8a7f0c` | fix(features): 修复 6 个 feature 模块的数据兼容性问题 | 3b-i 后修 |

---

## 九、Phase 3b 交付清单(全部 ✅)

### Phase 3b-i 文件

| 文件 | 状态 |
|---|---|
| `tradingagents/features/commodity/__init__.py` | ✅ |
| `tradingagents/features/commodity/_helpers.py` | ✅ |
| `tradingagents/features/commodity/technical.py` | ✅ |
| `tradingagents/features/commodity/basis.py` | ✅ |
| `tradingagents/features/commodity/inventory.py` | ✅ |
| `tradingagents/features/commodity/positioning.py` | ✅ |
| `tradingagents/features/commodity/term_structure.py` | ✅ |
| `tradingagents/features/commodity/news_sentiment.py` | ✅ |
| `tests/test_commodity_features.py` | ✅ 97 测试 |

### Phase 3b-ii 文件

| 文件 | 状态 |
|---|---|
| `tradingagents/agents/analysts/commodity/technical_analyst.py` | ✅ |
| `tradingagents/agents/analysts/commodity/fundamental_analyst.py` | ✅ |
| `tradingagents/agents/analysts/commodity/position_analyst.py` | ✅ |
| `tradingagents/agents/analysts/commodity/news_analyst.py` | ✅ |
| `tradingagents/agents/analysts/commodity/_base.py` | ✅ |
| `tradingagents/agents/analysts/commodity/reports.py` | ✅ |
| `tradingagents/graph/commodity_graph.py` | ✅ |
| `app/routers/commodity/analysis.py` | ✅ |
| `frontend/src/views/Commodity/Analysis.vue` | ✅ |
| `tests/test_commodity_analyst.py` | ✅ 45 测试 |
| `tests/test_commodity_decision_chain.py` | ✅ 26 测试 |
| `tests/test_commodity_cio.py` | ✅ 6 测试 |

---

## 十、关键教训

- **最小侵入 commodity 化成功**:8 个决策链节点只需文件顶 `COMMODITY_*_PROMPT` + `if/else` 分支,stock 路径零改动
- **MagicMock 不兼容 `prompt \| llm` 链式调用**:必须用 `llm.invoke(messages_payload)` 而非 `chain.invoke`
- **asset_type 传递至关重要**:`AgentState` 必须默认 `"stock"`,commodity 路径在 Propagator 中注入 `"commodity"`
- **CIO 换月检测**:实际 E2E 测试发现 `CU2501.SHF` 已过期,CIO 自动切换到 `CU2504.SHF` — 证明决策链能正确使用合约字段
- **全链路 13 次 LLM 调用**:~280 秒,用户需有耐心等待,可考虑未来加 SSE 进度推送

---

## 十一、Phase 4 衔接

### 启动前置条件

在 `commodity_metadata.py` 补齐每个品种的合约规格字段:
- `margin_rate`(保证金率,如 0.08=8%)
- `commission_rate`(手续费率,如 0.0001=万分之一)
- `limit_up_down_pct`(涨跌停幅度,如 0.07=±7%)

### 实施步骤

| 步骤 | 模块 | 时间 |
|---|---|---|
| Phase 4-1 | 合约规格补齐(`commodity_metadata.py` 新增字段) | 0.5 天 |
| Phase 4-2 | 纯规则引擎(`tradingagents/paper/{spec,matcher,pnl,account,risk,repo}.py`) | 3-4 天 |
| Phase 4-3 | HTTP 路由 + Vue 下单页(`paper_rules.py` + `PaperTrading.vue`) | 2 天 |
| Phase 4-4 | CIO→Paper 联动(`POST /api/commodity/paper/from-decision`) | 1 天 |
| Phase 4-5 | E2E 实测(下单→持仓→隔日盯市) | 1 天 |

### 参考

- 细节设计: `docs/plans/stock-to-commodity.md` §6.1
- 模拟交易路由设计: `docs/progress/phase-4.md`(启动后创建)
