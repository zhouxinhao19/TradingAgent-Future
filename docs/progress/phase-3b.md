# Phase 3b — 多源情报 + 分析师扩展(启动文档)

> 详见 plan: [`docs/plans/stock-to-commodity.md`](../plans/stock-to-commodity.md) §1.4 + §5
> 前置审计: [`docs/progress/phase-3a.md`](phase-3a.md) §八(合约生命周期 P0 三项)
> 架构参考: `TradingAgents_for_Futures-main/qihuo/features/` (纯规则特征工程层)

**创建日期**: 2026-07-14
**状态**: 🟡 **待启动** — 必须完成 P0 三项修复后才能开工

---

## 一、启动前提:必须先修 P0 三项

Phase 3a 审计(phase-3a.md §八)确认以下 P0 问题阻塞 Phase 3b:

| # | 缺口 | 影响 | 修复状态 |
|---|---|---|---|
| P0-1 | `get_historical_data` 忽略 YYMM,用户传具体合约被静默替换为主连 | 误导用户、破坏数据一致性 | ✅ 已修复 |
| P0-2 | 无换月标记/复权选项 | 3 年回溯分析无法解释价格跳变,技术指标(展期收益率、carry_score)不可解释 | ✅ 已修复 |
| P0-3 | 无 `get_active_contract_history()` | 期限结构、基差分析无法正确归因 | ✅ 已修复 |

---

## 七、3b-i 进度(2026-07-14 更新)

### 7.1 ✅ 全部 6 个 feature 模块已完成

| 模块 | 入口函数 | 关键输出 | 状态 |
|---|---|---|---|
| `technical.py` | `compute_technical_metrics(df, include_weekly=True)` | daily/weekly/combined 三层 + 50+ 指标 + OI 背离 + 资金流 + 综合评分 | ✅ |
| `basis.py` | `compute_basis_metrics(df, symbol=None)` | 现货/近月/主力价 + 基差率 + 180d 分位 + 升贴水信号 | ✅ |
| `inventory.py` | `compute_inventory_metrics(df, symbol=None)` | WoW/MoM 变化 + 180d 分位 + 跳变标志 + 偏离信号 | ✅ |
| `positioning.py` | `compute_positioning_metrics(df_or_dict, symbol=None)` | 前20净多变化 + 集中度 + 拥挤度分位 + 5d 净多变化 | ✅ |
| `term_structure.py` | `compute_term_structure_metrics(df, var=None)` | structure(contango/backwardation/flat) + carry_score + roll_yield/spread | ✅ |
| `news_sentiment.py` | `compute_news_sentiment_metrics(inp, source='all')` | 1/3/7/14/30 天计数 + 多空情感比 + 重要性事件 + 分类 | ✅ |

### 7.2 共享基础设施

- `_helpers.py` — 6 模块共用的工具:
  - `normalize_columns(df)` — 中文 / 英文 / 混合列名规范化(带去重,避免 "标题" 与 "内容" 同映射丢数据)
  - `safe_float` / `safe_int` — 安全类型转换(NaN → None / 0)
  - `zscore` / `slope` / `percentile_rank` — 统计特征
  - `data_quality(df, value_col)` — 数据质量(rows / coverage / freshness)
  - `empty_result(reason)` — 统一空结果 schema 工厂
  - `ensure_columns(df, required)` — 缺失列补 NA

### 7.3 输出 schema 统一(全部 6 模块一致)

```python
{
  "latest":   {指标名: float},          # 最常用值
  "stats":    {zscore_180d, slope_20d}, # 统计特征
  "signals":  [rule-based 信号文字],
  "snapshot": {全量指标},               # 供 LLM 消费
  "quality":  {rows, coverage, data_freshness_days, ...}
}
```

### 7.4 测试结果

- `tests/test_commodity_features.py` — **97 个测试全过**
  - TestNormalizeColumns (4)
  - TestComputeTechnicalMetricsBasic (4)
  - TestMultiTimeframe (4)
  - TestTrendDirection (3)
  - TestTriggers (4)
  - TestSnapshot (3)
  - TestOIDivergence (2)
  - TestVolatility (2)
  - TestEdgeCases (5)
  - TestProviderCompatibility (2)
  - TestLatest (2)
  - TestStats (3)
  - TestBasis (8)
  - TestInventory (8)
  - TestPositioning (7)
  - TestTermStructure (8)
  - TestNewsSentiment (10)
  - TestHelpers (12)
  - TestCrossModuleSchemaConsistency (6)
- 与 `test_commodity_data_layer.py` 合计 **182 个测试 0 失败**

### 7.5 关键约束已满足

- ✅ 纯函数,零 LLM,零外部 API
- ✅ 中文(provider 默认)/ 英文列名双向兼容
- ✅ 输出 schema 在全部 6 个模块一致(`TestCrossModuleSchemaConsistency` 验证)
- ✅ 数据不足 / 空输入时返回统一的 `empty_result` 结构
- ✅ 列存在但全 NaN 时(无 OI / 无总持仓)各依赖字段返回 None / 0,不抛错

---

## 二、架构调整说明

对照参考项目 `TradingAgents_for_Futures-main/` 后,Phase 3b 拆为**两个子阶段**:

```
旧: provider → LLM analyst (直接调 LLM, 又贵又不可控)
新: provider → features(纯规则) → analysis(聚合) → agents(可选LLM)
```

Phase 3b 不再直接让 LLM 算指标,而是先建 **Features 纯规则层**(零 LLM、零 API、纯 pandas),再把结构化数据喂给 LLM 做文字总结。

---

## 三、Phase 3b-i: Features 层(纯规则,无 LLM)

### 3.1 新增目录 `tradingagents/features/commodity/`

参考 `TradingAgents_for_Futures-main/qihuo/features/` 的**纯函数设计**:输入 DataFrame,输出结构化 Dict,**不调 LLM,不调数据 API**。

| 文件 | 核心函数 | 输入(从 provider 取) | 输出(结构化 Dict) |
|---|---|---|---|
| `technical.py` | `compute_technical_metrics()` | OHLCV DataFrame + `indicators.py` | direction/strength/triggers/volatility/oi_divergence/snapshot(含 50+ 指标) 多周期(日/周) |
| `basis.py` | `compute_basis_metrics()` | `get_spot_price` + `get_basis_history` → DataFrame | latest/zscore_180d/slope_20d/signals |
| `inventory.py` | `compute_inventory_metrics()` | `get_inventory` → DataFrame | latest/wow_change/mom_change/zscore_180d/jump_flag/signals |
| `positioning.py` | `compute_positioning_metrics()` | `get_position_rank` → DataFrame | latest/concentration/crowding_pctl_180d/net_long_change_5d/signals |
| `term_structure.py` | `compute_term_structure_metrics()` | `get_roll_yield` → DataFrame | latest/zscore_180d/slope_20d/structure(contango/backwardation)/carry_score/signals |
| `news_sentiment.py` | `compute_news_sentiment_metrics()` | `get_futures_news` → List[Dict] | counts_by_category/sentiment_ratio/recent_top/signals |

### 3.2 每个 feature 函数的输出约定

所有 feature 函数遵循统一 schema:

```python
{
    "latest": { "指标名": float },           # 最新值
    "stats": { "zscore_180d": float, "slope_20d": float },  # 统计特征
    "signals": ["rule-based 信号文字"],      # 触发信号(如"库存环比上升,180d 分位 > 0.8")
    "snapshot": { "指标名": float, ... },    # 全量数值快照(供 LLM 消费)
    "quality": { "data_freshness": int, "coverage": float },  # 数据质量
}
```

### 3.3 新增文件清单

| 文件 | 说明 |
|---|---|
| `tradingagents/features/__init__.py` | 包入口 |
| `tradingagents/features/commodity/__init__.py` | 包入口 |
| `tradingagents/features/commodity/technical.py` | 技术面特征(复用 `tools/analysis/indicators.py`) |
| `tradingagents/features/commodity/basis.py` | 基差特征 |
| `tradingagents/features/commodity/inventory.py` | 库存特征 |
| `tradingagents/features/commodity/positioning.py` | 持仓特征 |
| `tradingagents/features/commodity/term_structure.py` | 期限结构特征 |
| `tradingagents/features/commodity/news_sentiment.py` | 新闻情感特征 |
| `tests/test_commodity_features.py` | 全部 feature 的单元测试 |

### 3.4 验证标准

- [ ] 每个模块有纯函数单元测试(输入 mock DataFrame → 断言输出结构)
- [ ] 全部测试 `python -m pytest tests/test_commodity_features.py --tb=short -q` 通过
- [ ] 不依赖 LLM API,不依赖网络(除 provider 数据外)
- [ ] 6 个模块的输出 schema 稳定性测试

---

## 四、Phase 3b-ii: 分析师 + 决策链(LLM 驱动)

### 4.1 5 个分析师节点

在 `tradingagents/agents/analysts/commodity/` 下新建。每个 analyst 接收 features 层的结构化输出,可选调用 LLM 做文字总结。

| 分析师 | 输入(features 层) | LLM 用法 | 输出 |
|---|---|---|---|
| `technical_analyst` | `features.commodity.technical` 的 snapshot | 可选:LLM 总结技术形态 | `TechnicalReport`(方向/强度/关键位) |
| `fundamental_analyst` | `features.commodity.{basis, inventory, term_structure}` 聚合 | 可选:LLM 解读基差+库存+期限结构 | `FundamentalReport`(基差/库存/期限) |
| `position_analyst` | `features.commodity.positioning` | 可选:LLM 解读持仓变化 | `PositionReport`(集中度/拥挤度) |
| `news_analyst` | `features.commodity.news_sentiment` + `get_futures_news` 原文 | LLM 必调:生成叙事摘要+事件卡片 | `NewsReport`(叙事/情感/事件) |

**不再单独设 macro_analyst**。宏观数据(global_macro)融入 news_analyst 的 LLM prompt 和辩论阶段的 context。

### 4.2 四阶段决策链

分析师产出报告后,进入完整决策链:

```
阶段1: 分析师(4份平行报告)
         ↓
阶段2: 多空辩论
         ├── 看涨研究员(LLM,基于分析师报告构建看涨论点)
         ├── 看跌研究员(LLM,基于分析师报告构建看跌论点)
         └── 研究经理(LLM,裁判评分)
         ↓
阶段3: 交易员决策
         └── ProfessionalTrader(LLM + 凯利公式,输出 TradingDecision)
         ↓
阶段4: 风控评估 + CIO 最终决策
         ├── RiskManager(LLM,方向一致性检查+风险等级)
         └── CIO(LLM,综合 debate + risk + trading_decision)
```

相关类:

| 类/文件 | 位置 | 功能 |
|---|---|---|
| `CommodityTradingAgentsGraph` | `tradingagents/graph/commodity_graph.py` | 子图:注册 4 个 analyst + 决策链节点 |
| `BullishResearcher` / `BearishResearcher` | `tradingagents/agents/researchers/commodity/` | 多空辩论(复用现有研究员基类) |
| `ResearchManager` | `tradingagents/agents/managers/` | 辩论裁判(复用) |
| `ProfessionalTrader` | `tradingagents/agents/trader/` | 交易员(复用,加商品规则) |
| `RiskManager` | `tradingagents/agents/risk_mgmt/` | 风控(复用,加商品参数) |
| `ExecutiveDecisionMaker` | `tradingagents/agents/managers/` | CIO(复用) |

**尽量复用现有 `tradingagents/agents/` 基类**,只在 commodity 子目录加商品特定的 prompt 和参数。

### 4.3 路由层新增

`app/routers/commodity/analysis.py`:
- `POST /api/commodity/{full_symbol}/analyze` — 提交分析任务(走队列,异步 SSE 推送)
- `GET /api/commodity/{full_symbol}/reports` — 拉历史报告

queue_service 中加 `asset_type` 字段,使 worker 自动选 `CommodityTradingAgentsGraph`。

### 4.4 Feature Flag

翻 `FEATURE_COMMODITY_ANALYSIS=true` 后,详情页"分析"按钮可触发。

---

## 五、工作量估算

| 子阶段 | 工作量 | 依赖 | 验证方式 |
|---|---|---|---|
| **3b-i Features 层** | 3-4 天 | P0 已完成 | `pytest tests/test_commodity_features.py` 全绿,不调 LLM |
| **3b-ii 分析师+决策链** | 1 周 | 3b-i 完成 | `curl POST /analyze` 返回完整报告 |
| **总计** | ~2 周 | P0 + 3b-i → 3b-ii | — |

---

## 六、交付清单(汇总)

### Phase 3b-i 文件

| 文件 | status |
|---|---|
| `tradingagents/features/commodity/__init__.py` | ✅ |
| `tradingagents/features/commodity/_helpers.py` | ✅ |
| `tradingagents/features/commodity/technical.py` | ✅ 2026-07-14 |
| `tradingagents/features/commodity/basis.py` | ✅ 2026-07-14 |
| `tradingagents/features/commodity/inventory.py` | ✅ 2026-07-14 |
| `tradingagents/features/commodity/positioning.py` | ✅ 2026-07-14 |
| `tradingagents/features/commodity/term_structure.py` | ✅ 2026-07-14 |
| `tradingagents/features/commodity/news_sentiment.py` | ✅ 2026-07-14 |
| `tests/test_commodity_features.py` | ✅ 97 测试通过 |

### Phase 3b-ii 文件

| 文件 | status |
|---|---|
| `tradingagents/agents/analysts/commodity/technical_analyst.py` | 🟡 |
| `tradingagents/agents/analysts/commodity/fundamental_analyst.py` | 🟡 |
| `tradingagents/agents/analysts/commodity/position_analyst.py` | 🟡 |
| `tradingagents/agents/analysts/commodity/news_analyst.py` | 🟡 |
| `tradingagents/agents/researchers/commodity/` (bull/bear) | 🟡 |
| `tradingagents/graph/commodity_graph.py` | 🟡 |
| `app/routers/commodity/analysis.py` | 🟡 |
| `frontend/src/views/Commodity/Analysis.vue` | 🟡 |
| `tests/test_commodity_analyst.py` | 🟡 |

---

## 八、3b-ii-A 进度(2026-07-14 17:30 完成)

### 8.1 ✅ 4 个 commodity analyst 节点全部交付

| Analyst | 文件 | 输入 | 输出字段 | LLM 策略 |
|---|---|---|---|---|
| 技术 | `technical_analyst.py` | `features.technical` | `market_report` | 可选(失败降级) |
| 基本面 | `fundamental_analyst.py` | `features.{basis,inventory,term_structure}` | `fundamentals_report` | 可选(失败降级) |
| 持仓 | `position_analyst.py` | `features.positioning` | `sentiment_report` | 可选(失败降级) |
| 新闻 | `news_analyst.py` | `features.news_sentiment` + `state['latest_news']` | `news_report` | 必调(失败仅返回情感统计) |

### 8.2 共享基础设施

- `tradingagents/agents/analysts/commodity/__init__.py` — 包入口,导出 4 个工厂函数 + 4 个 Report 模型
- `tradingagents/agents/analysts/commodity/_base.py` — 共享工具:
  - `load_features(state)` — 从 `state['commodity_features']` 读取
  - `empty_report(direction, reason)` — 降级 Markdown 模板
  - `quality_gate(features_block)` — quality.rows ≥ 30 才走 LLM
  - `truncate_snapshot(snap, max_keys)` — 截断防 prompt 过长
  - `get_full_symbol(state)` — 兼容 `full_symbol` / `company_of_interest` 字段
- `tradingagents/agents/analysts/commodity/reports.py` — 4 个 Pydantic 模型:
  - `AnalystSignal` 基类(direction/strength/confidence/summary/signals)
  - `TechnicalReport` / `FundamentalReport` / `PositionReport` / `NewsReport`

### 8.3 关键设计决策

| 决策 | 原因 | 落地 |
|---|---|---|
| **复用 AgentState 字段名** | 决策链节点(Bull/Bear/Research Manager/Trader/Risk Manager)零改动 | 4 个 analyst 分别写入 `market_report` / `fundamentals_report` / `sentiment_report` / `news_report` |
| **features 层零依赖** | 3b-i 已验证 97 测试全过,analyst 只读 snapshot | 4 个 analyst 不调 provider,只在 state 读 `commodity_features` |
| **LLM 失败降级** | 商品 LLM 调用易因网络/限流失败,不能阻塞分析 | 3 个非必调 analyst 失败时输出"降级版本" Markdown,news 失败时仅返回情感统计 |
| **统一 LLM 调用方式** | 不用 chain,直接 `llm.invoke(messages)` | mock 行为可预测,测试 45 个 0 失败 |
| **Prompt partial 注入** | 避免在 invoke 时传 dict 报 INVALID_PROMPT_INPUT | `prompt.partial(**prompt_vars).format_messages(messages=...)` |

### 8.4 输出 schema 验证

| Analyst | 字段集合 | messages | tool_call_count |
|---|---|---|---|
| technical | `market_report` | `[AIMessage]` | 0 |
| fundamental | `fundamentals_report` | `[AIMessage]` | 0 |
| position | `sentiment_report` | `[AIMessage]` | 0 |
| news | `news_report` | `[AIMessage]` | 0 |

LLM 失败时,`messages=[]` 防止半成品 AIMessage 污染消息历史。

### 8.5 测试结果

- `tests/test_commodity_analyst.py` — **45 个测试全过**
  - `TestAnalystSignal` / `TestTechnicalReport` / `TestFundamentalReport` / `TestPositionReport` / `TestNewsReport` (10) — Pydantic 模型校验
  - `TestBase` (10) — `_base` 工具(load_features/empty_report/quality_gate/truncate_snapshot/get_full_symbol)
  - `TestTechnicalAnalystNode` (9) — features 缺失/稀疏/完整/LLM 失败/weekly=None
  - `TestFundamentalAnalystNode` (4) — features 缺失/完整/部分/LLM 失败
  - `TestPositionAnalystNode` (4) — features 缺失/完整/LLM 失败/极端拥挤
  - `TestNewsAnalystNode` (4) — features 缺失/完整/only_events/LLM 失败
  - `TestSchemaConsistency` (2) — 4 Report 公共字段一致
  - `TestOutputFieldMapping` (4) — 4 analyst 写入各自正确字段
- 与 `tests/test_commodity_features.py` 合计 **142 测试 0 失败**

### 8.6 已知约束与未交付项

#### ✅ 已交付
- 4 个 analyst 节点(代码 + 单元测试)
- 4 个 Pydantic Report 模型
- 共享 `_base` 工具集
- 输出字段映射(决策链零改动前提验证)
- LLM 失败降级 3 路径(features 缺失/数据稀疏/LLM 抛错)

#### 🟡 未交付(后续 3b-ii-B/C/D)
- 决策链节点 commodity 化(多空辩论 + Research Manager + Trader + 风控 + CIO)
- `CommodityTradingAgentsGraph` 子类 + Propagator 接线
- `app/routers/commodity/analysis.py` 路由
- `frontend/src/views/Commodity/Analysis.vue` 页面
- 端到端实测(LLM 真实调用 + 报告渲染)

#### ⚠️ 待验证项(代码完成 ≠ 用户可演示)
- 4 个 analyst 节点未在 LangGraph 中实际注册(仅单元测试覆盖)
- 真实 LLM 调用未做(测试用 MagicMock)
- 端到端流程未跑(需等 3b-ii-C 子图接线)

### 8.7 提交记录

- commit `41f7b939` — feat(phase-3b-ii-A): commodity technical analyst + features 层
- commit `2948afa8` — feat(phase-3b-ii-A): 完成 fundamental/position/news 三 analyst 节点
- 分支:`worktree-phase-3b-ii-technical-analyst`
- push:⏸ 用户授权前不推送到 origin
- PR:⏸ 未创建(待 push 后)

### 8.8 下一步计划

按 3b-ii-B/C/D 顺序:
1. **3b-ii-B 决策链节点**(2 天)— 多空辩论(bull/bear commodity 子目录)+ Trader + Risk Manager + CIO
2. **3b-ii-C 子图接线**(1.5 天)— `CommodityTradingAgentsGraph` + Propagator + GraphSetup asset_type 切换
3. **3b-ii-D 路由 + 前端**(1.5 天)— `analysis.py` 路由 + `Analysis.vue` 页面
4. **3b-ii-E 端到端实测 + 文档**(1 天)— 翻 `FEATURE_COMMODITY_ANALYSIS` + curl/浏览器验证
