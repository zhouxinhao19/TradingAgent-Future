# 商品期货多智能体分析链路 — 完整实施文档

> 版本: v2 (2026-07-21)
>
> 范围: `TradingAgent-CN` 项目从股票向大宗商品期货改造所实现的端到端多智能体分析链路,覆盖 **数据层 → 特征层 → L1 分析师 → L2 推理分析师 → L3 CIO → SafetyOverride 风控二审**。
>
> 代码基线: Phase 0–3b + Phase UI + Phase Agent 全部已合并(`fix/agent-data-layer-optimization` 分支,合并日期 2026-07-21)。

---

## 目录

1. [总体架构](#1-总体架构)
2. [数据层: Provider + Cache + Service](#2-数据层-provider--cache--service)
3. [特征工程层: 六个纯规则模块](#3-特征工程层六个纯规则模块)
4. [自定义数据分析师(用户上传 Excel/CSV)](#4-自定义数据分析师用户上传-excelcsv)
5. [多智能体决策链](#5-多智能体决策链)
6. [与股票框架的复用与差异](#6-与股票框架的复用与差异)
7. [提示词设计规范](#7-提示词设计规范)
8. [状态字段流转](#8-状态字段流转)
9. [输出 Schema 与风控二审](#9-输出-schema-与风控二审)
10. [测试覆盖与性能数据](#10-测试覆盖与性能数据)

---

## 1. 总体架构

商品期货分析链路按 **5 层 pipeline** 组织,从底层到顶层:

```
┌─────────────────────────────────────────────────────────────────────┐
│  1. 数据层  tradingagents/dataflows/providers/commodity/             │
│     BaseCommodityDataProvider (3 abstract + 13 扩展)                │
│     ├─ AkshareFuturesProvider (主,实现全部 13 个扩展)               │
│     ├─ commodity_metadata.py (6 交易所 + 80+ 品种 + 主力连续)       │
│     └─ CommodityCacheManager (三层: 内存+Parquet+增量合并)           │
│     ▼                                                              │
│  2. 特征层  tradingagents/features/commodity/                        │
│     6 个纯规则模块,产出统一的 {latest, stats, signals,              │
│     snapshot, quality} 结构,零 LLM 调用                              │
│     ▼                                                              │
│  3. L1 分析师  tradingagents/agents/analysts/commodity/              │
│     4 个 commodity analyst (技术/产业/持仓/新闻),并行 fan-out,       │
│     各读特征子模块,各输出 1 份结构化 + 1 份 Markdown 报告            │
│     ▼                                                              │
│  4. L2 推理分析师  tradingagents/agents/managers/research_manager.py │
│     压缩 4 份 L1 报告 → 1 次 LLM → 三模块 JSON (investment_plan)    │
│     ▼                                                              │
│  5. L3 CIO + 风控二审                                                │
│     tradingagents/agents/managers/investment_director.py             │
│     量化检查器(0 LLM) → 1 次 LLM → SafetyOverride(0 LLM 硬规则)    │
│     ▼                                                              │
│  6. 输出  final_decision (Markdown) + investment_memo +             │
│     risk_card (含 SafetyOverride 审计) + evidence_chain             │
└─────────────────────────────────────────────────────────────────────┘
```

入口: `app/services/commodity/unified_commodity_service.py` 中的 `service` 是全局单例,在 FastAPI lifespan 中初始化。所有 commodity 路由 (`/api/commodity/*`) 通过它对外暴露。

---

## 2. 数据层: Provider + Cache + Service

### 2.1 抽象接口

文件: `tradingagents/dataflows/providers/commodity/base_commodity_provider.py`

**4 个 `@abstractmethod` (强制实现)**:

| 方法 | 签名 |
|---|---|
| `connect` | `async def connect(self) -> bool` |
| `get_commodity_basic_info` | `async def get_commodity_basic_info(self, full_symbol=None)` |
| `get_commodity_quotes` | `async def get_commodity_quotes(self, full_symbol) -> Optional[Dict]` |
| `get_historical_data` | `async def get_historical_data(self, full_symbol, start_date, end_date=None, adjustment_mode="none")` |

`adjustment_mode` 取值 `"none"` / `"back"` / `"forward"`, DataFrame 含 `rollover_date` 换月标记列。

**13+ 个扩展接口** (默认 `NotImplementedError`, 子类按需重写; `AkshareFuturesProvider` 已全部实现):

| 接口 | 主要 AKShare 后端 | 典型返回列 |
|---|---|---|
| `get_fees_and_margin(exchange, symbol, date)` | `futures_comm_info` / `futures_comm_js` / `futures_fees_info` / `futures_settle` | 费用 + 保证金 |
| `get_inventory(symbol, start, end, no_cache)` | `futures_inventory_em` / `futures_inventory_99` | `[date, inventory, change_pct]` |
| `get_warehouse_receipt(exchange, date)` | `futures_warehouse_receipt_{shfe,dce,czce,gfex}` | `{variety: DataFrame}` |
| `get_position_rank(exchange, date, vars_list)` | `futures_dce_position_rank` 等 5 交易所分支 | 会员持仓排名 Top20 |
| `get_position_rank_history(exchange, end_date, lookback_days=30)` | 同上, `asyncio.gather` 并发 | 历史持仓排名 |
| `get_registered_receipt(start, end, vars_list)` | `get_receipt` | 注册仓单 |
| `get_spot_price(date, no_cache)` | `futures_spot_price` | symbol/spot/near/dom/basis |
| `get_basis_history(start, end, vars_list, no_cache)` | `futures_spot_price_daily` | 历史基差 |
| `get_basis_spot_previous(date)` | `futures_spot_price_previous` | 单日基差 + 180 日极值 |
| `get_roll_yield(type_method, var, date, ...)` | `get_roll_yield_bar` / `get_roll_yield` | 展期收益率 |
| `get_contract_info(exchange, date)` | `futures_contract_info_{shfe,ine,dce,czce,gfex,cffex}` | 上市/到期/挂牌基准价 |
| `get_trading_calendar(date)` | `futures_rule` | 涨跌停/保证金/合约乘数 |
| `get_realtime_quote(symbols, market="CF")` | `futures_zh_spot` / `hq.sinajs.cn` | CF 商品期货 / FF 金融期货 |
| `get_minute_kline(symbol, period=1)` | `futures_zh_minute_sina` | 1/5/15/30/60 min |
| `get_delivery_info(exchange, date)` | `futures_delivery_*` / `futures_to_spot_*` | 交割统计 / 期转现 |
| `get_holding_position(symbol, indicator, date)` | `futures_hold_pos_sina` | 成交量 / 多单 / 空单 |
| `get_futures_news(category="all", limit=50)` | `futures_news_shmet` + 6 源宏观聚合 | 见 §2.5 |
| `get_active_contract_history(symbol, start, end)` | 自合成: 基于 `get_contract_info` + 到期日排序 | `[date, active, exchange, days_to_expiry, last_delivery]` |

### 2.2 AkshareFuturesProvider 实现

文件: `tradingagents/dataflows/providers/commodity/akshare_futures.py`

**已实现全部 13+ 扩展, 无 NotImplementedError 占位**。关键技术点:

- **懒加载**: `connect()` 调 `import akshare as ak` + `CommodityCacheManager` (延迟到首次使用时)
- **降级链**: 每个 fetch 接口实现 2-4 级回退,例如:
  - `get_fees_and_margin`: `futures_comm_info → comm_js → fees_info → settle`
  - `get_inventory`: `em(代码) → em(中文) → inventory_99(中文) → inventory_99(原值)`
  - `get_basis_history`: `futures_spot_price_daily → spot_price_qh → 本地缓存`
- **`adjustment_mode` 实现**: 后复权/前复权采用比率法 (DataFrame 内部处理换月缺口)
- **换月检测**: `_mark_rollover_dates(df, gap_threshold=0.03)` (涨跌幅 + 持仓量突变)
- **主力连续回退**: `_try_continuous_fallback(full_symbol)` — 具体合约无数据 → 试 `<underlying>0` (例: `CU2501.SHF` → `CU0`)
- **新闻 shmet 18 → 12 映射**: `_NEWS_CATEGORY_MAP` 把 18 个入参 category 映射到 shmet 的 12 个 symbol
- **辅助**: `_symbol_to_chinese` (60+ 品种映射)、`_has_yyymm` (合约月份判断)、`_normalize_hist_em_df` (东财→新浪列名)、`_compute_roll_yield_from_exchange` (DIY 展期收益率)

### 2.3 commodity_metadata 静态元数据

文件: `tradingagents/dataflows/providers/commodity/commodity_metadata.py` (零依赖、可单测)

**六大交易所**:

| code | mic | suffix | 中文 | 简称 |
|---|---|---|---|---|
| `CFFEX` | CCFX | `.CFX` | 中国金融期货交易所 | cffex |
| `SHFE` | XSHG | `.SHF` | 上海期货交易所 | shfe |
| `INE` | XINE | `.INE` | 上海国际能源交易中心 | ine |
| `DCE` | XDCE | `.DCE` | 大连商品交易所 | dce |
| `CZCE` | XZCE | `.ZCE` | 郑州商品交易所 | czce |
| `GFEX` | XGFX | `.GFEX` | 广州期货交易所 | gfex |

**品类 (7 个) + 80+ 品种**:

| category | 典型品种 |
|---|---|
| `precious` | AU, AG |
| `metal` (有色) | CU, AL, ZN, PB, NI, SN, AO, BC, SI, LC, PS |
| `black` (黑色) | RB, WR, HC, SS, I, J, JM, SF, SM |
| `energy` | BU, FU, SC, LU, PG, ZC |
| `chemical` | RU, BR, SP, NR, L, V, PP, EG, EB, TA, MA, FG, SA, SH, UR, PF, PX, PR |
| `agricultural` | A, B, C, CS, M, Y, P, JD, RR, FB, BB, LH, LG, CF, SR, CY, AP, CJ, PK, RM, OI, RS, PM, WH, RI, LR, JR |
| `financial` (金融) | EC, IF, IH, IC, IM, TS, TF, T, TL |

**交易时间**: 日盘通用 `09:00-10:15, 10:30-11:30, 13:30-15:00`; CFFEX 股指 `09:30-11:30, 13:00-15:00`, 国债多 15 分钟收市; 夜盘 SHFE 金属 `21:00-01:00`, 贵金属/能源到 `02:30`, DCE 大部分 `21:00-23:00`; 无夜盘: WR/JD/LH/EC/GFEX 全系/CFFEX 全系。

**主力连续规则**: `MAIN_CONTINUOUS_SYMBOLS[var] = f"{var}0"`; 指数连续 = `f"{var}99"` (CFFEX 用标准 99 代码, 其他期货通过 `get_futures_daily` 获取)。

**`normalize_exchange_code` 5 级匹配**: 1. 别名表 (`CZC→CZCE`) → 2. 直接匹配 → 3. 后缀匹配 (`ZCE→CZCE`) → 4. 缩写匹配 → 5. `None`。

### 2.4 commodity_cache 三层缓存

文件: `tradingagents/dataflows/cache/commodity_cache.py`

| 层 | 类 | 作用域 |
|---|---|---|
| L1 | `InMemoryTTLCache` | 内存 (秒级) |
| L2 | `ParquetFileCache` | 磁盘 (`data_cache/commodity/` 子目录) |
| L3 | `incremental_merge` | 增量合并 (concat → drop_duplicates → sort) |

**默认 TTL (`TTL_CONFIG`)**:

| 类型 | TTL (秒) | | 类型 | TTL |
|---|---|---|---|---|
| `quotes` | 30 | | `positioning` | 21600 (6h) |
| `basic` | 43200 (12h) | | `roll_yield` | 21600 |
| `historical` | 3600 (1h) | | `spot_price` | 14400 (4h) |
| `inventory` | 21600 | | `news` | 7200 (2h) |
| `basis` | 14400 | | | |

**降级链**: L2 Parquet 命中 → 返回; 未命中 → Provider 在线 → 写 L2 → 写 L1。`no_cache=True` 时先 `delete_*(Parquet) + invalidate_mem(内存)` 再直连 Provider。

**辅助方法**: `get_or_fetch(key, fetcher, ttl_sec)` (短路 fetch)、`delete_inventory(symbol)` (旁路)、`invalidate_mem(key_prefix)`、`get_commodity_cache(cache_root=None)` (全局单例)。

### 2.5 新闻 6 类别

文件: `akshare_futures.py:get_futures_news` + `app/services/commodity/unified_commodity_service.py:get_futures_news`

| 路径 | 数据源 | 范围 |
|---|---|---|
| **A** | `futures_news_shmet` | 有色 + 贵金属 + 小金属 + 财经快讯 (12 symbol) |
| **B** | `_synth_global_macro_news` 聚合 6 源 | `global_macro` 类别: cls/eastmoney/ths/futu/cjzc/sina |
| **C** | 未识别 category | 警告 + 返回 `[]` |

服务层增强: MongoDB `commodity_news_annotations` 优先读; 不足 → Provider 实时 + `NewsAnnotator` (DeepSeek, `max_concurrent=3`) 实时标注。

**情感打分 (双层)**:
1. 商品专用关键词词典 (`BULLISH_KW` 30 / `BEARISH_KW` 30 / `IMPORTANCE_KW` 16)
2. `_to_sentiment_label(score)`: `>=0.3 → positive`, `<=-0.3 → negative`, 否则 `neutral`

### 2.6 unified_commodity_service 高层 API

文件: `app/services/commodity/unified_commodity_service.py`

模块级单例 `service = UnifiedCommodityService()`, 仅注册 `akshare_futures`。所有方法统一返回 `{"rows": [Dict], "count": N, ...}` 包装 (`_df_to_records` 把 NaN/NaT → None)。

高层方法对照表 (供上层 agent / router 调用):

| 服务方法 | Provider 方法 | 返回额外字段 |
|---|---|---|
| `get_basic_info` | `get_commodity_basic_info` | Dict |
| `get_quotes` | `get_commodity_quotes` | Dict |
| `get_historical` | `get_historical_data` | `rows/count/start_date/end_date/data_source_note` |
| `get_varieties` | `list_all_varieties` | List (支持 exchange/category 过滤) |
| `get_fees_and_margin` | `get_fees_and_margin` | List/Dict |
| `get_inventory` | `get_inventory` | `symbol/rows/count` |
| `get_warehouse_receipt` | `get_warehouse_receipt` | `exchange/date/by_variety/count` |
| `get_position_rank` | `get_position_rank` | `exchange/date/by_variety/count` |
| `get_spot_price` | `get_spot_price` | `date/rows/count` |
| `get_basis_history` | `get_basis_history` | `vars_list/start_day/end_day/rows/count` |
| `get_basis_spot_previous` | `get_basis_spot_previous` | `date/rows/count` |
| `get_roll_yield` | `get_roll_yield` | `type_method/var/rows/count` |
| `get_contract_info` | `get_contract_info` | `exchange/date/rows/count` |
| `get_contracts_list` | 自合成 (过滤到期) | `underlying/chinese_name/exchange/continuous/current/contracts` |
| `get_trading_calendar` | `get_trading_calendar` | `date/rows/count` |
| `get_realtime_quote` | `get_realtime_quote` | `symbols/market/rows/count` |
| `get_minute_kline` | `get_minute_kline` | `symbol/period/rows/count` |
| `get_delivery_info` | `get_delivery_info` | `exchange/date/rows/count` |
| `get_holding_position` | `get_holding_position` | `symbol/indicator/date/rows/count` |
| `get_futures_news` | `get_futures_news` + Mongo + LLM | List[Dict] |
| `get_categories` / `get_exchanges` / `get_news_categories` | 静态 | 7 / 6 / 5 |

---

## 3. 特征工程层: 六个纯规则模块

文件目录: `tradingagents/features/commodity/`

### 3.1 统一 Schema

每个 `compute_*` 函数返回同一结构 (technical 例外, 多 `{daily, weekly, combined}` 三层):

```python
{
  "latest":   Dict[str, float|str],   # 最新值 (最常用字段)
  "stats":    {"zscore_180d": ..., "slope_20d": ...},
  "signals":  List[str],              # 中文规则信号
  "snapshot": Dict[str, Any],         # 全量数值 (供 LLM 消费)
  "quality":  {"rows": int, "coverage": float, "data_freshness_days": int|None, ...}
}
```

### 3.2 共享辅助 (`_helpers.py`)

- `normalize_columns(df)` — 中英文列名 → canonical
- `safe_float / safe_int / to_numeric(series)`
- `zscore(series, window=180, min_periods=20)`
- `slope(series, window=20, min_periods=5)`
- `percentile_rank(series, window=180)`
- `wow_change(series, weeks=1)`
- `data_quality(df, value_col="value")`
- `empty_result(reason)`
- `extract_yyymm(symbol)` / `is_near_delivery(symbol, trade_date, days_threshold=30)`
- `normalize_multi_contract_input(main_df, index_df, contracts_dict)`

### 3.3 技术面 `technical.py`

**入口**:

```python
def compute_technical_metrics(df, include_weekly=True, weekly_min_rows=30) -> Dict
def compute_technical_metrics_multi_contract(main_df, index_df=None, include_weekly=True, weekly_min_rows=30) -> Dict
```

**支持的指标 (50+)**:

| 类别 | 指标 | 默认参数 |
|---|---|---|
| 基础 (复用 `tradingagents/tools/analysis/indicators`) | MA / EMA / MACD (12/26/9) / RSI (14) / BOLL (20,2.0) / ATR (14) / KDJ (9,3,3) | 标准 |
| 高级 (自补) | ADX/+DI/-DI (14) / OBV / PSAR (0.02/0.02/0.2) / Williams %R (14) / CCI (20) / StochRSI (14,3,3) / Ichimoku (9/26/52/26) / CMF (20) / VPT / TSI (25,13) / ADXR | 标准 |
| **期货特有** | OI: `oi_change / oi_change_pct / oi_ma5 / oi_ma20 / oi_position (20d 分位%) / oi_price_bull_div / oi_price_bear_div / oi_rsi14` | |
| | 资金流: `money_flow / money_flow_ma5` (价/仓同向=多/空建仓 1/-1, 反向=平仓 0.5/-0.5) | |
| | 量仓: `vol_oi_ratio / vol_oi_ratio_ma20 / composite_score` (Z 价 0.4+量 0.3+仓 0.3) / `oi_momentum_5d / price_momentum_5d / volume_momentum_5d` | |
| K 线 | `gap_pct / upper_shadow_ratio / lower_shadow_ratio / box20_flag` (20d 振幅<3%) | |
| 统计 | `atr_ratio / atr_ratio_pctl180 / volatility_20d / vol_z20 / vwap20 / hhv20 / llv20 / breakout_long20 / breakout_short20 / pullback20_pct / boll_bw` | |

**关键 snapshot 字段** (供 agent prompt 引用):

```
technical.close / ma20 / ma60 / ema20 / atr14 / atr_ratio / atr_ratio_pctl180
technical.rsi14 / macd / macd_signal / macd_hist
technical.boll_mid / boll_up / boll_low / boll_bw
technical.adx14 / adxr14 / plus_di14 / minus_di14
technical.kdj_k / kdj_d / kdj_j
technical.psar / psar_trend / williams_r14 / cci20
technical.stoch_rsi / stoch_k / stoch_d
technical.tenkan_sen / kijun_sen / senkou_span_a / senkou_span_b / kumo_thickness
technical.cmf20 / vpt / tsi
technical.oi_change_pct / oi_ma20 / oi_position / oi_rsi14
technical.oi_price_bull_div / oi_price_bear_div / money_flow / money_flow_ma5
technical.vol_oi_ratio / vol_oi_ratio_ma20 / composite_score / volatility_20d
technical.vol_z20 / vwap20 / obv / gap_pct
technical.hhv20 / llv20 / pullback20_pct / box20_flag
technical.breakout_long20 / breakout_short20
technical.upper_shadow_ratio / lower_shadow_ratio

# 顶层 combined
technical.combined.direction ("long/short/neutral")
technical.combined.strength (0~1)
technical.combined.oi_divergence ("confirm/conflict/neutral")
technical.combined.volatility.regime ("high/low")

# 多合约增强
technical.main_index_alignment ("aligned/divergent/partial")
technical.rollover_status.{detected, description, recent_rollover, rollover_dates}
```

**信号触发** (中文文本): 均线/布林带突破、MACD 金叉/死叉、RSI ≥ 70 / ≤ 30、ADX ≥ 25、K 线长上/下影、OI 增/减仓+看涨/看跌背离、资金流 ±0.5 / ±0.5、composite_score ±1.5、Ichimoku 云层穿越、Williams %R 阈值、CCI ±100、CMF ±0.1、TSI ±25、PSAR 趋势反转等共 30+ 条。

### 3.4 基差 `basis.py`

**入口**: `compute_basis_metrics(df, symbol=None)`

**输入**: `get_basis_history` 返回的 `near_basis / dom_basis / *_basis_rate` (AKShare 已计算原始 spread, 本模块做分位+斜率)。

**信号**:
- 近月基差率 < 0 且 180 日分位 ≤ 0.2 → `近月贴水处低分位,存在反弹概率`
- 近月基差率 > 0 且 180 日分位 ≥ 0.8 → `近月升水处高分位,回归风险上升`
- `|near_basis_rate| > 0.05` → `近月基差率偏离较大(N%)`
- 近月升 + 主力贴 → `近远月基差反向(Contango↔Backwardation)`

**snapshot 字段**: `basis.{near_basis, dom_basis, near_basis_rate, dom_basis_rate, *_rate_pctl_180d, *_rate_slope_20d, *_rate_dev_180d, near_contract, dominant_contract}`

### 3.5 库存 `inventory.py`

**入口**: `compute_inventory_metrics(df, symbol=None, weeks_in_year=52)`

**输入**: `get_inventory()` 返回的 `[date, value, delta?, symbol?]`。

**计算**:
- WoW/MoM: `wow_change(value, weeks=1/4)`
- 180 日分位 + Z-score
- 跳变: `(value.diff − rolling(20).mean) / rolling(20).std`, 绝对值 ≥ 3 → 跳变

**信号**: `库存环比上升/下降`、`月环比上升/下降`、`高分位/低分位`、`变化异常(跳变)`、`偏离均值(±N.NN σ)`。

**snapshot 字段**: `inventory.{value, delta, wow_change, mom_change, *_change_pct, zscore_180d, zscore_value, slope_20d, jump_flag, min_180d, max_180d, mean_180d}`

### 3.6 持仓 / 拥挤度 `positioning.py`

**入口**: 单/多合约版本

```python
def compute_positioning_metrics(
    df_or_dict,         # 单合约 DataFrame 或 {合约代码: DataFrame}
    symbol=None,
    price_direction=None,   # bullish/bearish/neutral
) -> Dict
```

**派生**:
- `total_oi`: 无列时 = `long_top20 + short_top20` (避免 NaN)
- `net_long_top20`: 缺则 = `long_top20 − short_top20`
- `concentration` (`conc_metric`): `long_top20 / (long + short)`, ∈ [0,1]; > 0.6 多头集中 / < 0.4 空头集中
- `long_share / short_share`: `long_top20 / (2 × total_oi)`
- 5 日变化: `net_long_change_5d / long_top20_change_5d / short_top20_change_5d / long_short_ratio_change_5d / oi_change_5d / oi_change_pct_5d`
- `consecutive_net_long_days` / `net_long_slope_20d`
- 拥挤度分位 `crowding_pctl_180d`

**四象限价仓分类** (`price_oi_regime`):

| 价格 | 持仓 | regime | 强度 |
|---|---|---|---|
| 涨 | 增 | 多头强势 (价涨仓增) | ★★★ |
| 涨 | 减 | 空头回补 (价涨仓减) | ★ |
| 跌 | 增 | 空头强势 (价跌仓增) | ★★★ |
| 跌 | 减 | 多头止损 (价跌仓减) | ★ |

**多合约增强 (`_aggregate_contracts`)**:
- `contracts[contract]` 快照: `{contract, oi, net_long, long_top20, short_top20, net_long_change_5d, is_dominant, rows, oi_share}`
- `variety_aggregate.{total_oi, total_net_long, active_contracts}`
- `rollover.detected`: 近月 OI < -2% 且次近月 OI > +2% → 移仓中
- `cross_contract.consistency`: `同向看多 / 同向看空 / 分化`

**信号 (中文)**: 前 20 净多增加/减少、连续 N 日净多增加/减少、拥挤度高/低分位 (警惕反转/关注建仓)、价仓共振/背离、移仓信号、跨合约一致性。

### 3.7 期限结构 `term_structure.py`

**入口**: `compute_term_structure_metrics(df, var=None)`

**输入**: `get_roll_yield` 返回的 `roll_yield / spread / near_price / dominant_price`, `_pick_metric` 按序匹配 8 种列名。

**判定**:
- `metric > 0` → `contango` (远月 > 近月, 正展期)
- `metric < 0` → `backwardation` (近月 > 远月, 负展期)
- `metric == 0` → `flat`

**`carry_score ∈ [-1, 1]`**: 越高越利好多头。基线 `(pctl_180d − 0.5) × 2.0`; backwardation +0.2, contango −0.2, clamp 到 [-1, 1]。

**信号**: `期限结构偏多 / 偏空 / 平坦`、`carry_score ≥ 0.5 → carry 友好(多头)`、`slope_20d > 0 → 向 Contango 走陡`。

**snapshot 字段**: `term_structure.{metric, structure, carry_score, <metric>, <metric>_pctl_180d, _slope_20d, _zscore_180d, _mean_180d, _std_180d, _min_180d, _max_180d, near_contract, dominant_contract, near_price, dominant_price}`

### 3.8 新闻情感 `news_sentiment.py` (规则降级兜底)

**入口**: `compute_news_sentiment_metrics(inp, source="all")`

> 主情感标注已迁移到 `NewsAnnotator` (LLM 驱动, DeepSeek), 本模块仅做兜底。

**输入**: DataFrame (`date / title / content`) 或 List[Dict] (provider `get_futures_news`) 或单 Dict。

**词典**:
- 多头 30: `上调/上涨/涨幅/扩大/改善/提振/好转/超预期/强势/看多/做多/利多/支撑/回升/反弹/突破/利好/紧缺/供给紧张/需求旺盛/增产不及预期/库存下降/去库/现货运费上涨`
- 空头 30: `下调/下跌/跌幅/收缩/恶化/承压/不及预期/弱势/看空/做空/利空/阻力/回落/跌破/过剩/供给宽松/需求疲软/增产超预期/库存上升/累库/现货运费下跌`
- 重要性 16: `央行/美联储/欧央行/降息/加息/决议/重要/重大/突发/OPEC/欧佩克/非农/CPI/PPI/GDP/PMI/紧急`

**打分**: `_sentiment(text)` = (BULLISH 命中数 − BEARISH 命中数), >0 → +1, <0 → −1, =0 → 0; 整体 = sum / total。

**信号** (QVIX 阈值):
- `n7 ≥ 50 → 近一周新闻热度高`, `≥ 20 → 热度中等`, `n3 ≥ 10 → 密集`
- 样本 ≥ 10 时, `ratio > 0.2 → 偏多`, `< -0.2 → 偏空`, 否则 `中性`
- `importance_count_7d ≥ 3 → 近 7 天 N 条重要事件`

**snapshot 字段**: `news.counts.{n1, n3, n7, n14, n30, total}`, `news.sentiment.{bullish, bearish, ratio}`, `news.categories.{metal, energy, agricultural, chemical, financial, macro, other}`, `news.importance_count`, `news.recent_top[5]` (近 3 天 Top), `news.stats.{n_total, avg_per_day_7d}`。

### 3.9 公共 API (`__init__.py`)

```python
from tradingagents.features.commodity import (
    _helpers,
    compute_technical_metrics,
    compute_basis_metrics,
    compute_inventory_metrics,
    compute_positioning_metrics,
    compute_term_structure_metrics,
    compute_news_sentiment_metrics,
)
```

主入口 `compute_all_features_from_provider(provider, full_symbol, trade_date)` (Propagator 的 `auto_features` 路径) 会一次性调上述 6 个 `compute_*` + 缓存 `commodity_features`, 供 L1 分析师消费。

---

## 4. 自定义数据分析师 (用户上传 Excel/CSV)

文件目录: `tradingagents/agents/custom_data/`

### 4.1 模块分层 (模态无关架构)

| 文件 | 角色 |
|---|---|
| `content/base.py` | `Content` 抽象基类 (`type_name / source_path / metadata / validate / to_dict`) |
| `content/tabular.py` | `TabularContent` (封装 DataFrame + columns + shape + dtypes + numeric_columns + missing_summary) |
| `readers/registry.py` | `ReaderRegistry` (扩展名 → Reader 类单例映射) |
| `readers/tabular_reader.py` | `TabularReader` (支持 `.xlsx/.xls/.csv`; CSV 自动探测 5 种编码 + 5 种分隔符; Excel 仅读第一个 sheet; >50w 行截断) |
| `summarizers/registry.py` | `SummarizerRegistry` (按 `Content.type_name` 派发) |
| `summarizers/tabular_summarizer.py` | `TabularSummarizer.summarize() → {type, source, overview{rows, columns, missing_cells, missing_ratio}, columns[{name, dtype, missing}], statistics{p5/p25/p50/p75/p95/mean/std/min/max}, time_columns, date_range, sample: 前 5 行, warnings}` |
| `skills/registry.py` | `SkillsRegistry` 从 `definitions/*.md` 加载所有 skill, 按 `__index__.json` 顺序 |
| `skills/loader.py` | `load_skill_from_md(path)` (解析 YAML frontmatter + body prompt 模板, 支持 `{data_summary} / {user_context} / {content_types} / {skill_name} / {title}` 占位符) |
| `engine.py` | 入口 `run_analysis(file_paths, skill_name, llm, ...)` + `AnalysisResult{success, skill_name, file_count, content_types, data_summary, report, fallback, error}` |

### 4.2 五步接入流程 (`engine.run_analysis`)

1. **Reader 派发**: 按文件扩展名查 `ReaderRegistry._readers` → `reader.read(path)` → 失败累积到 `errors` → `contents` 为空返回 `success=False`
2. **Summarizer 派发**: 每个 Content 调 `SummarizerRegistry.summarize(c)` → 输出 JSON 摘要
3. **Skill 加载**: `SkillsRegistry.load(skill_name)` → 无 → 兜底 `general-analysis` → 再无 → `_fallback_prompt`
4. **Prompt 构造**: `skill.render(data_summary=json.dumps(summaries), user_context, content_types)`; `max_summary_chars=20000` 自动截断到前 N 个文件 (默认 3)
5. **LLM 调用与降级**: `llm.invoke([HumanMessage])` → JSON 解析; 失败 → `_fallback_report` (纯数据概览 + "_LLM 可用后可重新提交_") → `fallback=True`; `llm=None` 直接走兜底

### 4.3 接入 L1 分析师的桥梁

`build_custom_data_context(features)` (`_base.py`) 从 `features['custom_data']` 提取 `summary_text`, 在每个 L1 分析师 prompt 的 `## 用户上传数据参考\n{custom_data_context}` 段落注入。Propagator 在 `auto_features` 阶段把用户的 Excel/CSV 经过 `run_analysis` 跑出 `data_summary`, 再以 `summary_text` 形式挂到 `commodity_features.custom_data`, **4 个 commodity 分析师 + research_manager + investment_director 都消费这个字段**, 把"用户私有数据"和"产业链 features"在同一 prompt 里并置。

**扩展新模态 (PDF/图片)**: 写 `content/pdf.py` 继承 `Content` + `readers/pdf_reader.py` 实现 `read()` + `summarizers/pdf_summarizer.py` + `ReaderRegistry.register(".pdf", PdfReader)` 即可, 引擎零修改。

---

## 5. 多智能体决策链

### 5.1 节点拓扑

```
                  START
        ┌────┬───┴────┬──────────────┐
        ▼    ▼        ▼              ▼
   Technical  Fundamentals Sentiment    News
   (技术)     (产业)      (持仓情绪)  (新闻)
   L1 quick  L1 quick    L1 quick    L1 quick
        │         │        │              │
        └─────────┴────────┼──────────────┘   ← LangGraph fan-in barrier
                          ▼
                  Research Manager
                  (推理分析师, L2 deep)
                          ▼
                  Investment Director
                  (投研总监 CIO, L3 deep)
                 ┌────┴────┐
                 │         │
          量化检查器    1 次 LLM
          (0 LLM)      (90s 超时)
                 │         │
                 └────┬────┘
                      ▼
              SafetyOverride
              (0 LLM 二审)
                      ▼
                     END
```

**与 stock 路径的关键差异**: commodity 路径砍掉了 stock 的 Bull/Bear 辩论 (2 节点 + N 轮循环)、Trader (1 节点)、3×Risk 辩论 (3 节点 + N 轮循环)、Risk Manager (1 节点) 共 7 个节点 + 多条循环边, 由 CIO 1 节点替代 L3–L5 全链路。

### 5.2 节点清单

| 层级 | 节点 | 文件 | LLM | 读 | 写 |
|---|---|---|---|---|---|
| L1 | `Technical Analyst` | `analysts/commodity/technical_analyst.py` | quick (60s, 3 次重试) | `commodity_features.technical` | `market_report` / `analyst_registry[REF-TECH-...]` |
| L1 | `Fundamentals Analyst` (产业) | `analysts/commodity/fundamental_analyst.py` | quick (60s, 3 次重试) | `commodity_features.{basis,inventory,term_structure}` | `fundamentals_report` / `fundamentals_structured` / `analyst_registry` |
| L1 | `Sentiment Analyst` (持仓情绪) | `analysts/commodity/position_analyst.py` | quick (60s, 3 次重试) | `commodity_features.positioning` + `latest_news` | `position_report` / `position_structured` / `analyst_registry` |
| L1 | `News Analyst` | `analysts/commodity/news_analyst.py` | quick (60s, 3 次重试) | `latest_news` + `news_summary` + `commodity_features.news_sentiment` | `news_report` / `analyst_registry` |
| L2 | `Research Manager` | `managers/research_manager.py` (commodity 分支) | deep (90s, 3 次重试) | 4 份 `*_report` + `commodity_features` + `analyst_registry` | `investment_plan` (三模块 JSON) / `investment_debate_state` |
| 量化 | `compute_risk_assessment` (纯规则, 0 LLM) | `managers/investment_director.py` | — | `commodity_features` | `risk_assessment` (7 维度 R1-R5 + flags + composite_risk_level) |
| L3 | `Investment Director` (CIO) | `managers/investment_director.py` | deep (90s, 3 次重试) | `investment_plan` + `risk_assessment` + `analyst_registry` | `investment_memo` / `risk_card` / `final_decision` / `cio_decision_timestamp` |
| 二审 | `safety_override` (纯规则) | `managers/investment_director.py` | — | `risk_assessment` + LLM 方向/置信度 + 分析师注册表 + 持仓结构化数据 | 覆盖 `final_decision` (action/confidence/max_position) + 审计元数据 |

### 5.3 入口与编排

文件: `tradingagents/graph/commodity_graph.py` (`CommodityTradingAgentsGraph`)

```python
class CommodityTradingAgentsGraph(TradingAgentsGraph):
    def __init__(self, debug=False, config=None):
        super().__init__(selected_analysts=["market"], debug=debug, config=config)
        # 给 LLM 加超时和重试包装 (应用层防御)
        self.quick_thinking_llm = _wrap_llm_with_retry(self.quick_thinking_llm, "快速", 60)
        self.deep_thinking_llm = _wrap_llm_with_retry(self.deep_thinking_llm, "深度(L2/L3)", 90)
        # 替换为 commodity setup + propagator
        self.graph_setup = CommodityGraphSetup(...)
        self.graph = self.graph_setup.setup_graph()
        self.propagator = CommodityPropagator()
```

**`_wrap_llm_with_retry`**: 给 LLM 对象的 `invoke`/`ainvoke` 方法加上超时和自动重试。通过 `object.__setattr__` 绕过 Pydantic 字段校验拦截。最大重试次数由环境变量 `LLM_MAX_RETRIES` (默认 2) 控制, 即最多调用 3 次。

**Checkpointer**: `_create_checkpointer()` 支持三种后端:
- `memory` (默认): `MemorySaver`, 仅存进程内存, 重启丢失
- `sqlite`: `SqliteSaver`, 持久化到 `checkpoints.sqlite` 文件, 重启可恢复
- `none`: 不创建 checkpointer (适用于 E2E 测试, 避免 numpy 类型 msgpack 序列化失败)

**stream 模式**: `progress_callback` 存在 → `stream_mode="updates"` (节点级增量, 逐 chunk 调 `_send_progress_update`, commodity 节点名映射为中文); 否则 `stream_mode="values"` (累积状态), 逐 chunk 追加到 `trace`, `final_state = trace[-1]`。

**后处理**:
1. `build_evidence_chain(final_state)`: 纯规则提取三层证据链 JSON (L1 分析师注册索引 + L2 investment_plan + L3 risk_assessment/safety_override/CIO memo)
2. `_extract_decision(final_state)`: 先检查 `risk_card.safety_override.executed`。若已执行二审, 以二审结果为准; 若未执行但存在 R5/near_delivery/data_insufficient, fail closed 为 flat/hold; 否则记录警告但继续使用 LLM 原始输出

**numpy 类型归一化**: `_to_native` 递归转换 `np.integer/float/ndarray → Python 原生`, 避免 MemorySaver msgpack 序列化失败。

### 5.4 初始化 State

文件: `graph/commodity_graph.py` (`CommodityPropagator.create_initial_state`)

```python
{
    "messages": [HumanMessage("请对大宗商品期货 {full_symbol} 进行全面分析,交易日期为 {trade_date}.")],
    "company_of_interest": full_symbol,    # 复用 stock 字段 (决策链节点读这个)
    "full_symbol": full_symbol,
    "asset_type": "commodity",             # 触发决策链 commodity prompt
    "variety_name": "...",
    "exchange": "SHF|DCE|CZCE|INE|GFEX|CFFEX",
    "category": "...",
    "quote_unit": "...",
    "trade_date": "...",
    "investment_debate_state": InvestDebateState({"history": "", "current_response": "", "count": 0}),
    "risk_debate_state": RiskDebateState({...}),  # 兼容 stock schema, commodity 不消费
    "market_report": "",
    "fundamentals_report": "",
    "sentiment_report": "",
    "position_report": "",
    "news_report": "",
    "fundamentals_structured": {},
    "position_structured": {},
    "commodity_features": {...},           # 6 模块 features 字典
    "latest_news": [Dict, ...],
    "analyst_registry": {},                # merge_dicts reducer
    "news_summary": "利多X条 利空Y条 高重要度Z条",
    "contract_expiry_warning": {days_to_expiry, warning, delivery_date},
}
```

**合约到期检测** (`_compute_contract_expiry`):
- 从合约代码正则提取 YYMM (如 CU2507.SHF → 25年7月)
- 假设交割日为每月 15 日
- 距到期 < 10 天: "临近交割月流动性风险高，建议切换主力连续合约"
- 距到期 10-30 天: "注意交割月限仓和保证金提高"
- 已到期: "建议使用主力连续合约"

---

## 6. 与股票框架的复用与差异

### 6.1 继承层次

```
TradingAgentsGraph (父类, stock + commodity 共用)
    └─ CommodityTradingAgentsGraph (子类, commodity 专用)
```

**复用层 (零改动)**:
- `TradingAgentsGraph.__init__` 父类初始化 (LLM 创建、内存初始化)
- Toolkit、Memories、ConditionalLogic 全套继承
- `AgentState` 基类字段 (`messages`, `company_of_interest`, `trade_date` 等)

**替换层**:

| 组件 | 文件 | stock | commodity |
|---|---|---|---|
| Graph 入口 | `commodity_graph.py` | `TradingAgentsGraph` | `CommodityTradingAgentsGraph` (子类) |
| 图结构 | `commodity_graph.py` | `GraphSetup` (含 Bull/Bear 辩论 + Trader + 3×Risk) | `CommodityGraphSetup` (L1 × 4 → L2 → L3, 砍掉 7 节点) |
| 状态初始化 | `commodity_graph.py` | `Propagator.create_initial_state` | `CommodityPropagator.create_initial_state` (注入 commodity 专属字段) |
| 进度映射 | `commodity_graph.py` | 父类默认映射 | `_COMMODITY_NODE_MAPPING` (技术/产业/持仓情绪/新闻/推理分析师/投研总监) |

### 6.2 拓扑差异

| 节点 | stock 子图 | commodity 子图 |
|---|---|---|
| 分析师 | 4 个 stock analyst (market/news/social_media/fundamentals) | 4 个 commodity analyst (technical/fundamental/position/news) |
| Bull/Bear 辩论 | 2 节点 + N 轮循环 | **已砍掉**, 不经过 |
| Research Manager | 有 | 有 (commodity prompt 分支) |
| Trader | 有 | **已砍掉**, 不经过 |
| Risk 辩论 (aggressive/conservative/neutral) | 3 节点 + N 轮循环 | **已砍掉**, 不经过 |
| Risk Manager | 有 | **已砍掉**, 不经过 |
| CIO / Investment Director | 无 | **新增**, 替代 L3-L5 全链路 |
| SafetyOverride | 无 | **新增**, 纯规则二审 |

### 6.3 决策链节点 if/else 分支

同一节点函数内部通过 `state["asset_type"]` 切换 `COMMODITY_*_PROMPT`:

| 文件 | 切换点 | commodity 路径 |
|---|---|---|
| `managers/research_manager.py:290-318` | `asset_type == "commodity"` → `COMMODITY_REASONING_PROMPT` | 只跑 1 次 LLM, 产出三模块 JSON |
| `managers/investment_director.py:1001-1003` | `if asset_type != "commodity": return` | CIO 是 commodity-only 节点 |

> 注意: commodity 子图在拓扑上已经绕过不需要的节点 (Bull/Bear/Trader/Risk), 所以 `risk_manager.py` / `trader.py` 中的 commodity prompt 分支在 commodity 子图中实际不会触发, 只服务于 stock 路径兜底与未来扩展。

---

## 7. 提示词设计规范

### 7.1 共享基础设施 (`_base.py`)

```python
ANALYST_PREFIXES = {technical: "TECH", fundamental: "FUND", position: "POSN", news: "NEWS"}
make_analyst_id(prefix) → "REF-{PREFIX}-{sha256[:8]}"   # 唯一引用 ID
quality_gate(features, min_rows=30) → True/False
build_custom_data_context(features) → "## 用户上传数据参考\n{summary_text}"
load_features(state, key) → Dict
empty_report(reason) / truncate_snapshot(snap, max_keys=30)
```

每个 L1 分析师在报告中注入 `REF-{PREFIX}-{hash}` 唯一引用 ID, 供上层 L2/L3 交叉引用。

### 7.2 L1 分析师 Prompt 风格

#### Technical Analyst (`TECHNICAL_SYSTEM_PROMPT`)

- **角色**: "你是一位资深的期货技术分析师,与基本面、持仓、新闻分析师协作。"
- **输入**: `full_symbol / variety_name / exchange / trade_date / contract_type_label` + features.technical 全部字段 (`combined.direction/strength` + `daily/weekly trend` + `main_index_alignment` + `index_ma60/120` + `relative_strength` + `rollover_status` + `oi_divergence` + `vol_regime` + `atr` + `atr_pctl` + `snapshot_excerpt` + `trigger_signals` + `quality_rows`) + `news_summary` + `custom_data_context`
- **合约类型自适应** (`_detect_contract_type(full_symbol)`): 自动区分主力连续策略 vs 期限合约策略, 切换关注点
- **输出格式**: Markdown 400-800 字, 六段 (综合判断/关键位/OI 背离/波动率策略适配/移仓换月/风险提示)
- **硬约束**: "不要使用 emoji; 所有数值保留 2 位小数"
- **降级**: 无 LLM → `_build_fallback_report` (features snapshot 直拼 Markdown); features 缺失/sparse → `empty_report("neutral", reason)`

#### Fundamentals Analyst (`FUNDAMENTAL_SYSTEM_PROMPT`)

- **角色**: "你是一位产业分析师,聚焦产业链研究,运用'估值+驱动'框架。"
- **输入**: `full_symbol / variety_name / exchange / trade_date` + 三模块数据 (basis/inventory/term_structure) + 规则预判 (`valuation_position` / `safety_margin` / `drive_direction` / `drive_strength` / `consistency`) + `news_summary` + `custom_data_context`
- **三段式框架**: 估值分析 → 驱动分析 → 交叉验证 (同向 / 强背离 / 弱背离 / 待定)
- **输出 schema (必须合法 JSON)**:

```json
{
  "valuation": {"level": "高估/低估/合理", "safety_margin": "string", "reasoning": "..."},
  "drive": {"direction": "bullish/bearish/neutral", "strength": "string", "dominant_factor": "string", "reasoning": "..."},
  "consistency": {"alignment": "一致/背离", "confidence": 0.0, "analysis": "...", "key_uncertainty": "..."},
  "summary": "150字内",
  "risk_flags": [],
  "data_quality": "..."
}
```

- **硬约束**: "所有数值引用必须与输入数据一致" / "缺失数据必须标注'数据不可得',禁止凭空编造" / "不得引入输入数据中未提供的外部信息" / "请严格按照上述 JSON 结构输出,不要包含其他文本"
- **降级**: LLM 失败 → `_build_fallback_structured` (纯规则 valuation_position/drive_direction) + `_build_fallback_report` (Markdown 兜底)

#### Position Analyst (`POSITION_SYSTEM_PROMPT`)

- **角色**: "你是一位资深的期货持仓分析师,擅长'总量判断→结构分析→交叉验证'三层递进框架。"
- **输入**: `full_symbol / variety_name / exchange / trade_date / contract_source` + **第一层** (`total_oi_variety` / `active_contracts` / `total_net_long_variety` / `oi_change_pct_5d` / `price_oi_regime`) + **第二层** (`contracts_table` / `cross_contract_consistency` / `rollover_status` / `net_long_change_5d` / `concentration` / `crowding_pctl` / `signals` / `long_change_5d` / `short_change_5d` / `lsr_change_5d` / `consecutive_days` / `slope_20d`) + **第三层** (`vol_z20` / `vol_regime` / `oi_divergence`) + `news_summary` + `custom_data_context`
- **输出 schema (必须 JSON)**:

```json
{
  "direction": {"value": "long|short|neutral", "confidence": 0.0},
  "market_regime": "...",
  "long_side": {...},
  "short_side": {...},
  "concentration": {...},
  "cross_contract": {...},
  "rollover": {...},
  "cross_validation": {...},
  "summary": "...",
  "risk_flags": [],
  "data_quality": "..."
}
```

- **硬约束**: "请严格按照上述 JSON 结构输出,不要包含其他文本"
- **集中度规则**: "前 20 多头份额 > 0.6 = 多头相对集中, < 0.4 = 空头相对集中; 180d 分位 > 0.9 过度拥挤"
- **降级**: `_build_fallback_structured` (纯规则推导方向) + `_build_fallback_report`

#### News Analyst (`NEWS_SYSTEM_PROMPT`)

- **角色**: "你是一位资深的期货新闻分析师,采用'情绪总览→宏观→产业→关键矛盾→综合判断'五层框架。"
- **输入**: `full_symbol / variety_name / exchange / category` (metal/chemical/energy/agricultural/financial) + LLM 预标注事件列表 `recent_events` (最多 50 条) + `custom_data_context`
- **分类要求** (按 `category` 切换关注点):
  - **金属**: 矿山产能 / 冶炼开工率 / LME 库存
  - **化工**: 炼厂检修 / PTA 负荷 / 聚酯需求
  - **能源**: 油田产量 / 炼油利润 / 天然气库存
  - **农产品**: 天气 / USDA 报告 / 压榨利润
  - **金融**: 股指估值 / 资金流向
- **预标注**: 注入 LLM 预标注的 `llm_sentiment / llm_importance / llm_summary / relevant_varieties`, 要求指出与自身判断的矛盾
- **输出**: Markdown 500-800 字, 六段 (情绪总览 / 宏观叙事 / 产业叙事 / 关键矛盾 / 综合判断 / 风险提示)
- **硬约束**: "禁止使用 emoji; 保持专业性"
- **降级**: `_build_fallback_report` (情感比 + 新闻原文前 200 字); 无 LLM 且无 latest_news → `empty_report`

### 7.3 Bull/Bear 辩论 Prompt (保留但 commodity 路径不走)

文件: `researchers/bull_researcher.py` + `researchers/bear_researcher.py`

**角色差异**:

| 维度 | COMMODITY_BULL_PROMPT | COMMODITY_BEAR_PROMPT |
|---|---|---|
| 任务 | 为做多机会建立强有力论证 | 论证放弃做多或做空的理由 |
| 期现结构利好 | 库存去化 + 现货升水 + Backwardation | 库存累积 + 现货贴水 + Contango |
| 杠杆定位 | 8-15 倍杠杆放大正向收益 | 8-15 倍杠杆反向放大亏损、穿仓风险 |
| 合约风险 | 主力换月跳空、展期收益 (正 carry) | 展期成本 (负 carry)、涨跌停无法平仓 |
| 反驳对象 | 反驳看跌担忧,看多过度悲观 | 反驳过度乐观,批判看涨过度自信 |

> commodity 路径**不实际走 Bull/Bear 辩论循环** (已砍节点); 这段 prompt 仍保留作为 fallback, 供研究分析摘要使用。

### 7.4 L2 Research Manager (`COMMODITY_REASONING_PROMPT`)

文件: `managers/research_manager.py` (commodity 分支)

- **输入**: 4 份 `*_report` + 7 维度 `commodity_features` summary + `analyst_registry` + `investment_debate_state`
- **两步执行**:
  1. `_build_analyst_summary(features, registry)`: 压缩 4 份 ~8000 字 Markdown → ~1500 字结构化摘要 (各 L1 的 direction/校准 confidence/top-3 signals/关键 metrics)。还包含 `_collect_forced_risk_signals`: 确定性从 features 和报告中提取明示风险信号
  2. 调 1 次 LLM (90s 超时) 走 `COMMODITY_REASONING_PROMPT`, 产出**三模块 JSON**:

```json
{
  "valuation_drive_matrix": "6 维度 (估值×驱动×市场情绪×持仓×期限结构×新闻)",
  "bull_bear_alignment": "...",
  "scenarios": {"conservative": {...}, "base": {...}, "optimistic": {...}}
}
```

- **写 `investment_plan`**: 三模块 JSON + 推理摘要

### 7.5 L3 Investment Director / CIO (`INVESTMENT_DIRECTOR_SYSTEM_PROMPT`)

文件: `managers/investment_director.py`

- **6 步执行流程**:
  1. **量化检查器** (0 LLM): `compute_risk_assessment(commodity_features)` → 7 维度 R1-R5 + flags + composite_risk_level
  2. **构建风险卡** (0 LLM): `_build_risk_card(risk_assessment)` → 纯规则风险矩阵
  3. **准备 LLM prompt**: 拼装 `investment_plan` + `risk_assessment_json` + `analyst_registry_summary` + `custom_data_context`
  4. **LLM 调用**: 1 次 deep (90s, 3 次重试), 输出顶层 JSON
  5. **解析 / Fallback**: JSON 解析成功 → 合并 LLM 定性风险到规则风险卡; 失败 → `_build_fallback_memo` + `_build_fallback_decision`
  6. **SafetyOverride** (0 LLM): 无论 LLM 成功还是 fallback, 强制执行二审

- **LLM 输出 schema**:

```json
{
  "投研备忘录": {
    "估值审核": {"波动率": {"判断": "同意/修正", "理由": "...", "引用ID": "REF-TECH-xxx"}, ...},
    "情景裁决": {"选定情景": "保守/基准/乐观", "排除理由": "...", "核心分歧处理": "..."},
    "投研结论": {"方向倾向": "做多/做空/持有/平仓", "置信度": 0.0-1.0, "核心逻辑": "...", "反向信号": [...], "逆向信号处理": "..."}
  },
  "风险评估卡": {
    "三方视角": {"激进": {"概率权重": 0.3, "条件": "..."}, ...},
    "风险裁定": {"建议动作": "开仓/观望/减仓/平仓", "仓位上限": "账户30%", "杠杆上限": "3倍"},
    "风险提示": ["风险1", "风险2", "风险3"]
  },
  "final_decision_markdown": "必须包含 **方向**: 做多/做空/持有/平仓 和 **置信度**: 0.00"
}
```

- **硬约束**: 纯 JSON 输出, 禁止 ` ```json ` 包裹; R5 → 强制平仓; near_delivery → 强制平仓; data_insufficient → 禁止单边

---

## 8. 状态字段流转

### 8.1 节点读写总表

| 节点 | 读字段 | 写字段 |
|---|---|---|
| **Technical Analyst** | `commodity_features.technical`, `asset_type`, `full_symbol`, `company_of_interest` | `market_report`, `analyst_registry[REF-TECH-...]` |
| **Fundamentals Analyst** | `commodity_features.{basis,inventory,term_structure}`, `asset_type`, `full_symbol` | `fundamentals_report`, `fundamentals_structured`, `analyst_registry[REF-FUND-...]` |
| **Sentiment Analyst** | `commodity_features.positioning`, `latest_news`, `asset_type` | `position_report`, `position_structured`, `analyst_registry[REF-POSN-...]` |
| **News Analyst** | `latest_news`, `news_summary`, `commodity_features.news_sentiment`, `asset_type` | `news_report`, `analyst_registry[REF-NEWS-...]` |
| **Research Manager** | `market_report`, `fundamentals_report`, `position_report`, `news_report`, `commodity_features`, `analyst_registry`, `investment_debate_state` | `investment_plan` (三模块 JSON), `investment_debate_state.judge_decision` |
| **Investment Director** | `investment_plan`, `commodity_features`, `analyst_registry`, `asset_type`, `full_symbol`, `contract_expiry_warning`, `position_structured` | `risk_assessment`, `risk_card` (含 `safety_override`), `investment_memo`, `final_decision`, `cio_decision_timestamp` |
| **后处理** (commodity_graph.py) | `final_state` | `evidence_chain`, `decision` (`_effective_decision` 解析) |

### 8.2 AgentState commodity 专属字段

`AgentState` (agent_states.py:97-123) 中 commodity 新增字段:

```python
asset_type: str                          # "stock"或"commodity"
full_symbol: str                         # 完整合约代码 (如 RB2501.SHF)
variety_name: str                        # 品种中文名 (如 螺纹钢)
exchange: str                            # 交易所代码
category: str                            # 行业分类
quote_unit: str                          # 报价单位
commodity_features: dict                 # 6 模块 features 字典
latest_news: list                        # 新闻列表
final_decision: str                      # CIO 最终决策 Markdown
cio_decision_timestamp: str              # CIO 决策 ISO 时间戳
analyst_registry: Annotated[dict, merge_dicts]  # L1 注册索引

# Phase 4: 投研总监字段
investment_memo: dict = {}
risk_card: dict = {}
risk_assessment: dict = {}

# Phase Agent 改造
contract_expiry_warning: dict = {}        # 合约到期警告
evidence_chain: dict = {}                 # 三层证据链
```

### 8.3 Reducer 语义

- `analyst_registry` 用 `merge_dicts` reducer: L1 4 个 analyst 写自己的 `REF-{PREFIX}-{hash}` key, 自动合并不互覆盖
- `messages` 追加
- 其余标量字段由后写入者覆盖 (最后一个完成的 L1 决定 `market_report` 等), 因此**各 analyst 必须写不同 key** (`market_report` / `fundamentals_report` / `position_report` / `news_report`)

---

## 9. 输出 Schema 与风控二审

### 9.1 CIO 输出字段

| 字段 | 类型 | 来源 |
|---|---|---|
| `investment_memo` | dict | LLM 解析的"投研备忘录"块, 或 `_build_fallback_memo` |
| `risk_card` | dict | 纯规则 `_build_risk_card` + LLM 增强 (`_merge_llm_risk_card`) + `safety_override` 审计 |
| `risk_assessment` | dict | `compute_risk_assessment` 纯规则 7 维度评估 |
| `final_decision` | str | CIO Markdown (经 `rewrite_decision_markdown` 规范化) |

### 9.2 决策提取 (`_effective_decision`)

文件: `commodity_graph.py:_effective_decision`

优先顺序: SafetyOverride 审计 → 纯规则 fail closed → LLM 原始输出:

1. 若 `risk_card.safety_override.executed == True`: 以二审的 `action/confidence` 为准, `rewrite_decision_markdown` 重写 final_decision
2. 若二审未执行但存在 R5 维度 / composite == 5 / near_delivery: fail closed → `flat/0.0`, 记录错误日志
3. 若二审未执行且 `data_insufficient`: fail closed → `hold/0.0`
4. 否则: 记录警告但继续使用 LLM 原始输出

```python
{
    "action":      "long|short|flat|hold",
    "confidence":  float,
    "reasoning":   str,               # 完整 final_decision 文本
    "raw_text":    str,
}
```

### 9.3 量化风险评估 (`compute_risk_assessment`, 纯规则 0 LLM)

从 `commodity_features` 抽 7 维度:

| 维度 | 来源 features | R 评级映射 |
|---|---|---|
| `volatility` | `technical.combined.volatility.atr_ratio_pctl180` | pctl<20→R1, <50→R2, <80→R3, <95→R4, ≥95→R5 |
| `basis` | `basis.stats.zscore_180d.dom_basis_rate` | z<1→R2, <2→R3, <3→R4, ≥3→R5 |
| `crowding` | `positioning.snapshot.crowding_pctl_180d` | pctl<20→R1, <50→R2, <80→R3, <95→R4, ≥95→R5 |
| `inventory` | `inventory.stats.zscore_180d` | z<1→R2, <2→R3, <3→R4, ≥3→R5 |
| `term_structure` | `term_structure.snapshot.carry_score` | >0.3→R2, >-0.3→R3, >-0.6→R4, ≤-0.6→R5 |
| `oi_divergence` | `technical.combined.oi_divergence` | confirm→R2, neutral→R3, conflict→R4 |
| `news_sentiment` | `news_sentiment.snapshot.sentiment.ratio` | 参考, 不参与等级计算 |

**综合等级**: R4 计数 × 1.0 + R3 计数 × 0.5, 结合 flags severity 调整, clamp 到 [1, 5]。

**跨维度 flag**: `basis_extreme` / `carry_cost` / `vol_crowding` / `oi_trap` / `multi_extreme` / `inventory_jump`。

### 9.4 SafetyOverride (纯规则二审)

文件: `managers/investment_director.py:safety_override`

LLM 输出后强制执行不可协商的纯规则二审, 返回完整审计记录。

**硬规则引擎**:

| 规则 | 触发条件 | 动作 |
|---|---|---|
| `R5_REJECT` | composite_risk_level == 5 或任一维度 R5 | `flat`, confidence=0, max_position=0 |
| `NEAR_DELIVERY_REJECT` | contract_expiry_warning.days_to_expiry ≤ 30 且含 near_delivery flag | 同上 (此规则在 CIO 节点中从 contract_expiry_warning 注入 risk_assessment.flags) |
| `DATA_INSUFFICIENT` | quality.coverage < 0.5 | 若原方向为 long/short → `hold`; confidence ≤ 0.2; max_position ≤ 0.3 |
| `NO_L1_DIRECTION_SUPPORT` | 没有 L1 分析师明确支持 LLM 的方向 | 加入 contradiction_rules, 后续联合处理 |
| `CROWDING_REVERSAL_RISK` | 持仓拥挤度 R4+ | 同上 |
| `STRONG_REVERSE_FLAG` | vol_crowding / oi_trap / multi_extreme | 同上 |
| `CARRY_COST_CONFLICT_LONG` | 深度 Contango + 做多方向 | 同上 |
| `POSITION_REVERSAL_RISK` | 持仓分析明确标记拥挤反转风险 | 同上 |
| `COUNTER_SIGNAL_EXPLANATION_REQUIRED` | 有反向信号但未在 memo 中解释 | `hold`, 禁止单边 |
| `R4_FLAG_HALF_POSITION` | composite == 4 且存在 high/critical flags | max_position × 0.5 |
| `R4_WARN_ONLY` | composite == 4 无高严重度 flags | 保留方向但记录警告 |
| `R4_PLUS_HIGH_VOL` | volatility R4+ + composite R4+ | max_position × 0.5 |

**contradiction_rules 联合逻辑**: 多条 contradiction 规则命中时:
- 若 `hard_flat` 已触发: 不额外处理
- 否则: confidence ≤ 0.3, max_position ≤ 0.5
- 若 `counter_signal_explanation` 为空: 追加 `COUNTER_SIGNAL_EXPLANATION_REQUIRED` → `action = "hold"`

**返回**:

```python
{
    "executed": True,
    "action": "flat",                        # 覆盖后的方向
    "confidence": 0.0,                       # 覆盖后的置信度
    "max_position": 0.0,                     # 仓位上限比例
    "overridden": True,                      # 是否发生了覆盖
    "override_reason": "R5_REJECT；NEAR_DELIVERY_REJECT",
    "override_rules_triggered": ["R5_REJECT", "NEAR_DELIVERY_REJECT"],
    "original_llm_direction": "long",
    "original_llm_confidence": 0.75,
    "overridden_action": "flat",
    "overridden_confidence": 0.0,
    "r5_dimensions": ["volatility", "crowding"],
    "max_position_pct": 0.0,                 # 百分比版本 (在 risk_card 中追加)
}
```

### 9.5 证据链 (`build_evidence_chain`, 纯规则)

文件: `commodity_graph.py:build_evidence_chain`

从最终 state 提取结构化三层证据链 JSON, 供前端 Timeline 渲染:

```python
{
    "summary": {"symbol", "variety", "date", "final_action", "confidence"},
    "layers": {
        "L1": [
            {
                "id": "REF-TECH-a1b2c3d4",
                "name": "技术分析师",
                "direction": "long",
                "confidence": 0.7,
                "calibrated_confidence": 0.7,  # confidence × quality_weight
                "status": "ok/degraded/skipped",
                "summary": "...",
                "key_metrics": {"composite_score": 1.2, "oi_divergence": "confirm", ...},
                "signals": ["信号1", "信号2", "信号3"],
            },
            # ... fundamental, position, news
        ],
        "L2": {
            "valuation_matrix": [...],
            "bull_bear_table": [...],
            "scenarios": {...},
        },
        "L3": {
            "risk_assessment": {...},
            "risk_card": {...},
            "final_decision_raw": "...",
            "safety_override": {...},
            "cio_memo": {...},
            "cio_risk_card": {...},
        },
    }
}
```

---

## 10. 测试覆盖与性能数据

### 10.1 测试覆盖汇总 (2026-07-19 状态)

| 层 | 测试文件 | 用例数 | 验证内容 |
|---|---|---|---|
| 数据层 | `tests/test_commodity_data_layer.py` | 90 | AKShare provider 35+ 函数 mock, 16 测试组; `_call()` 路径在 akshare 不可用时优雅返回 `None` |
| 特征层 | `tests/test_commodity_features.py` | 97 | 6 模块 schema + 信号 + 边界 |
| 分析师 | `tests/test_commodity_analyst.py` | 45 | 4 个 analyst MagicMock LLM + 边界 + fallback |
| 决策链 | `tests/test_commodity_decision_chain.py` | 32 | 8 节点 commodity 分支 + CIO + SafetyOverride |
| HTTP 端点 | `tests/test_phase3a_curl.py` | 24 调用 | 后端 22 端点 100% 200 OK |
| **全部** | | **288** | |

### 10.2 LLM 调用次数与端到端性能

按 CIO 一次完整 `propagate()` 调用估算:

| 阶段 | 节点 | LLM 调用 | 备注 |
|---|---|---|---|
| L1 | Technical Analyst | 1 次 quick (60s) | 仅在 features 充分时调; quality_gate 失败 → fallback |
| L1 | Fundamentals Analyst | 1 次 quick | 同上, JSON 输出 |
| L1 | Position Analyst | 1 次 quick | JSON 输出 |
| L1 | News Analyst | 1 次 quick | 无 LLM 时走情感统计 fallback |
| L2 | Research Manager | 1 次 deep (90s) | `_build_analyst_summary` 压缩 + LLM 三模块 JSON |
| 量化 | `compute_risk_assessment` | 0 | 纯规则 |
| L3 | Investment Director | 1 次 deep (90s) | 顶层 JSON, LLM 失败 → `_build_fallback_memo + _build_fallback_decision` |
| 二审 | `safety_override` | 0 | 纯规则 |
| **合计 (典型)** | | **6 次 LLM** | |
| **合计 (降级后)** | | **4-6 次 LLM** | |

**实测端到端** (deepseek v4-flash, 2026-07-20):
- 平均耗时: ~280 秒
- LLM 调用次数: 13 次 (用户上传 CSV + 4 个 extra 主动分析)
- CIO 输出含: 换月检测 + 基差/库存/杠杆决策
- 单任务内存峰值: ~600 MB (主力连续 K 线 8 年 + 持仓排名 30 天并发)

### 10.3 集成点速查

| 端点 | 入口 | 调用方 |
|---|---|---|
| `POST /api/commodity/{symbol}/analyze` | `CommodityTradingAgentsGraph.propagate` | 前端 Analysis.vue 分步轮询 |
| `POST /api/commodity/batch` | 共享 batch_id 创建 N 个 queued 任务 | 批量分析 |
| `GET /api/commodity/batch/{batch_id}` | 汇总状态 (单次 MongoDB aggregation) | 批量进度 |
| MongoDB `commodity_analysis_tasks` | `find_one_and_update` 原子消费, `asyncio.Semaphore(2)` 并发 | P0 异步队列 |
| 前端 | `frontend/src/stores/commodity.ts` (12 actions) + `api/commodity.ts` (25 async 方法) | Dashboard / Detail / Analysis / Favorites / Tasks |

---

## 附录 A: 契约与配置

### A.1 Environment Variables

```bash
# 必需
DEEP_SEEK_API_KEY=...                # 默认 LLM provider
LLM_PROVIDER=deepseek
TAVILY_API_KEY=...                   # News Analyst 联网搜索兜底

# LLM Retry/Timeout
LLM_MAX_RETRIES=2                    # 最大重试次数 (默认 2, 即最多调用 3 次)
LLM_L1_TIMEOUT=60                    # L1 分析师超时 (秒)
LLM_L2_TIMEOUT=90                    # L2 Research Manager 超时
LLM_L3_TIMEOUT=90                    # L3 CIO 超时

# Checkpointer
CHECKPOINTER_BACKEND=memory          # memory/sqlite/none

# Feature Flag (渐进开启)
FEATURE_COMMODITY_ENABLED=true       # Phase 3a 已翻 true
FEATURE_COMMODITY_DATA=true          # Phase 3a
FEATURE_COMMODITY_ANALYSIS=true      # Phase 3b (默认)
FEATURE_COMMODITY_PAPER=false        # Phase 4 翻 true
```

### A.2 关键文件索引

| 类别 | 路径 |
|---|---|
| 数据 Provider | `tradingagents/dataflows/providers/commodity/` |
| Provider 元数据 | `commodity_metadata.py` |
| 缓存 | `tradingagents/dataflows/cache/commodity_cache.py` |
| 特征 | `tradingagents/features/commodity/` |
| Analyst | `tradingagents/agents/analysts/commodity/{technical,fundamental,position,news}_analyst.py` |
| Analyst 共享 | `tradingagents/agents/analysts/commodity/_base.py` |
| Analyst Pydantic | `tradingagents/agents/analysts/commodity/reports.py` |
| 自定义数据 | `tradingagents/agents/custom_data/` |
| 决策链 | `tradingagents/agents/researchers/{bull,bear}_researcher.py`、`managers/{research_manager,risk_manager,investment_director,executive_decision_maker}.py`、`risk_mgmt/{aggresive,conservative,neutral}_debator.py` |
| Graph 接线 | `tradingagents/graph/commodity_graph.py` |
| State Schema | `tradingagents/agents/utils/agent_states.py` |
| 后端服务 | `app/services/commodity/unified_commodity_service.py` |
| 后端路由 | `app/routers/commodity/extended.py` |
| 前端 | `frontend/src/{api,stores,views,components}/commodity*` |
| 进度文档 | `docs/progress/phase-3b.md`、`docs/progress/phase-4.md` |
| 主计划 | `docs/plans/stock-to-commodity.md` |

### A.3 命令速查

```bash
# 后端开发
python -m app --reload

# 前端开发
cd frontend && npm run dev

# 跑全部 commodity 测试
python -m pytest tests/test_commodity_data_layer.py tests/test_commodity_features.py tests/test_commodity_analyst.py tests/test_commodity_decision_chain.py tests/test_phase3a_curl.py -v

# 跑单个测试
python -m pytest tests/test_commodity_analyst.py::test_technical_analyst_with_daily_weekly_features -v

# Lint / 类型检查
cd frontend && npm run lint && npm run type-check
```

---

## 附录 B: 变更与重构史

| 日期 | Commit/分支 | 关键变更 |
|---|---|---|
| 2026-07-13 | `checkpoints` | Phase 2 数据层完成; @abstractmethod + 13 扩展接口 |
| 2026-07-14 | `feat/agent-data-layer-optimization` | features 6 模块 + analyst 4 个 + 决策链 commodity 化 |
| 2026-07-18 | `feat/queue-and-stats` | Phase 3c 异步队列 + 批量任务 + 任务中心优化 |
| 2026-07-19 | `d31f9492` | 前端 UI 全面梳理 (品类修正 + Dashboard 重构 + 设置精简 + 侧边栏清理 + 新闻修复) |
| 2026-07-20 | `7269fedc` | Agent 层 10 项改进 (Checkpointer / SafetyOverride / L2 精简化 / L1 并行化 / 证据链) + 自定义数据分析师 + 前端重设计 |
| 2026-07-21 | `fix/agent-data-layer-optimization` (本分支) | 当前文档基线 |

---

> 配套文档: `docs/progress/phase-3b.md` (决策链交付细节)、`docs/plans/stock-to-commodity.md` (主计划)、`docs/progress/phase-4.md` (Paper Trading + IO 闭环)。
