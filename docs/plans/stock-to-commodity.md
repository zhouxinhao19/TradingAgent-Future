# TradingAgent-Future:股票 → 大宗商品 改造方案

> **版本快照**:v5 — 反映 2026-07-18 实际进度(Phase 0/1/2/3a/3b/3c 全部完成)。
> Phase 3b 六个子阶段(3b-i → 3b-ii-E)已全部交付,Phase 3c(队列+批量+任务中心优化)已完成,
> Four-Phase 剩余 Phase 4(模拟交易)+ Phase 5(删股票)。

## Context

TradingAgent-Future 当前是基于 LangGraph 的多智能体股票分析平台,核心入口
`tradingagents/graph/trading_graph.py:TradingAgentsGraph`,含 FastAPI 后端(`app/`)+ Vue3
前端(`frontend/`)+ MongoDB/Redis。

用户的目标:把整套系统从**股票分析**改造为**大宗商品分析**(能源/金属/农产品/化工/金融期货
与现货)。商品数据层已就绪(Phase 0/1/2 完成),后续聚焦**多源情报聚合 + 分析师扩展 + 模拟交易 + 清股票**。

**已确认的改造策略**:
- 开发期间"股票"和"大宗商品"**并存**(增量开发,互不污染)
- 大宗商品模块开发**完成后**再统一删除股票代码
- 数据源**首选 AKShare**(零成本、覆盖国内 6 大期交所全品种),`yfinance_futures` 作为
  国际(CL/GC/SI)回退,实际数据接入 13+ 扩展接口 + 80+ 静态品种
- 商品层与股票层**目录完全隔离**(`commodity_*` vs `stock_*`),删除股票阶段无副作用

**关键约束**:
1. **每个 Phase 都能 `docker compose up` 跑通**
2. **Feature Flag 渐进开启**:4 个开关默认全 false,完成后翻 true 演示
3. **新闻管道优先**:商品分析师比股票更需要"基本面叙事",因此 Phase 2 先把 5 类别新闻(金属
   shmet + 化工/能源/农产品/金融 合成器 + 全球宏观聚合)做扎实
4. **`base_commodity_provider` 扩展接口默认 `NotImplementedError`**:Phase 2 之后新增的方法先上
   ABC 桩,provider 渐进实现,不阻塞股票侧

---

## 1. 总体设计

### 1.1 命名规范

| 维度 | 规范 | 示例 |
|---|---|---|
| 模块/文件 | `commodity_*` | `app/routers/commodity/`, `tradingagents/dataflows/providers/commodity/` |
| MongoDB 集合 | `commodity_*` | `commodity_basic_info`, `commodity_quotes`, `commodity_news` |
| 标的代码 | `<SYMBOL><YYMM>.<EXCHANGE>` | `CU2501.SHF`, `CL=F`, `AU9999.SGE` |
| API 路径 | `/api/commodity/*` | `/api/commodity/analysis`, `/api/commodity/news` |
| 前端视图 | `views/Commodity/*` | `Commodity/Detail.vue`, `Commodity/Analysis.vue` |
| 路由 name | `Commodity*` | `CommodityDetail`, `CommodityNews` |
| AgentState | `asset_type: Literal["stock","commodity"]` | 注入 state |
| 新闻分类 | `category ∈ {metal, copper, aluminum, lead, zinc, nickel, tin, precious, minor, headline, vip, finance, chemical, energy, agricultural, financial, global_macro, all}` | 由 `_NEWS_CATEGORY_MAP` 标准化 |

### 1.2 文件组织

平行建立 `commodity_*` 目录(不沿用 `stock_*` 复用),在路由层、状态层通过
`asset_type` 字段连接。删除股票阶段只需移除整组 `stock_*`,互不干扰。

### 1.3 共用层(零修改复用)

完整复用、不改一行:
- `tradingagents/llm_clients/`, `tradingagents/llm_adapters/` — LLM 抽象与标的无关
- `tradingagents/graph/conditional_logic.py`, `graph/reflection.py` — 状态路由/反思通用
- `tradingagents/tools/analysis/indicators.py`(MA/EMA/MACD/RSI/BOLL/ATR/KDJ)— `pd.Series` 计算
  与品种无关
- `tradingagents/dataflows/cache/*` — 缓存框架通用,仅传不同 collection 名
- `app/core/{database,response,config}.py` — 基础通用
- `app/models/{user,notification,operation_log,config}.py` — 通用模型
- 通用 router(`auth_db, health, sse, websocket_notifications, scheduler, ...`)
- 通用 Vue 组件(Global/通用、Layout/通用)
- 通用页面(`Dashboard`, `Queue`, `Tasks`, `Reports`, `Settings`, `About`, `Auth/*`, `Error/*`)

### 1.4 实施阶段(5 个 Phase;Phase 0/1/2 部分完成)

> **审计日期 2026-07-18**:Phase 0/1/2/3a/3b/3c 全部完成。
> Phase 3b 六个子阶段(3b-i Features 层 + 3b-ii 分析师+决策链+子图+路由+E2E)已全部交付并实测验证。
> Phase 3c(异步队列+批量任务+任务中心优化)已完成。
> Phase 4 待启动,前置依赖:在 `commodity_metadata.py` 补齐合约规格字段。

| Phase | 目标 | 状态 | 周期 | 关键交付 | 演示步骤 | 验证标准 |
|---|---|---|---|---|---|---|
| **Phase 0 — 抽象统一** | 解耦 stock 概念,引入 `AssetType`/`Instrument` | ✅ 完成 | 1-2 周 | `tradingagents/core/instrument.py`、枚举扩展、单元测试 | `docker compose up` 启动 OK,日志显示"商品模块已注册(未启用)" | `pytest tests/test_instrument.py` 57 passed |
| **Phase 1 — 数据闭环(行情)** | 行情拉取 → API → 前端只读 | ✅ 完成(flags/前端由 3a 补齐) | 2-3 周 | 后端 `commodity_*` provider/service/router 5 个端点 | 翻 flag → `curl /api/commodity/CU2501.SHF/info` | curl 验证 OK |
| **Phase 2 — 数据层完备** | 13 扩展接口 + 82 品种 + 6 类新闻 + 全测试 | ✅ 完成(路由/前端由 3a 补齐) | 1 周 | provider 层 13 扩展接口 + 6 类新闻 + 5 合成器 + 情感评分 | `pytest tests/test_commodity_data_layer.py` 全绿 | 85 个单元测试全部通过 |
| **Phase 3a — 路由 + 前端补全** | 22 后端端点 + 前端 commodity UI | ✅ **完成** | 1 天 | 22 HTTP 端点(5+15+2) + `views/Commodity/{List,Detail}.vue` + `api/commodity.ts` + `stores/commodity.ts` | 翻 flag + 浏览器访问 `/commodity/list` 看到品种列表 | 详见 [`docs/progress/phase-3a.md`](../progress/phase-3a.md) |
| **Phase 3b — 多源情报 + 分析师扩展** | Features 层(纯规则) + 4 分析师 + 四阶段决策链 | ✅ **全部完成** | 2 周(实际约 5 天) | `tradingagents/features/commodity/` 6 模块 + 4 分析师 + 多空辩论→交易员→风控→CIO + 子图+路由+E2E | `curl /api/commodity/CU2501.SHF/analyze` 返回完整报告 + DeepSeek 实测 ~280 秒 | 174+ commodity 测试 0 失败,E2E CIO 含换月检测 |
| **Phase 3c — 异步队列 + 批量任务** | 队列系统取代 BackgroundTasks + 批量任务 + 删除优化 | ✅ **完成** | 1 天 | MongoDB 队列 + Semaphore 并发 + batch 端点 + 聚合 stats + 删除直接用 `report_file_path` | curl stats/batch/submit/list/delete 全部 200 OK | 队列消费不丢任务、不重复消费;批量 POST/GET 端点工作正常 |

---

**Phase 3b 内部分阶段(已完成)**:

- **3b-i Features 层**:6 个纯规则模块(technical/basis/inventory/positioning/term_structure/news_sentiment),97 测试全过,零 LLM
- **3b-ii-A 4 个 commodity analyst**:technical/fundamental/position/news,复用 stock AgentState 字段名,45 测试
- **3b-ii-B 决策链 8 节点 commodity 化 + CIO**:bull/bear/manager/trader/3×risk/risk_manager/executive_decision_maker,最小侵入 asset_type 分支,32 测试
- **3b-ii-C 子图接线**:`CommodityTradingAgentsGraph` + `CommodityPropagator` + `CommodityGraphSetup`,测试覆盖
- **3b-ii-D 路由+Vue**:`POST /api/commodity/{symbol}/analyze` + `frontend Analysis.vue` + 分步轮询
- **3b-ii-E 端到端实测**:DeepSeek v4-flash,13 次 LLM 调用 ~280 秒,CIO 输出含 CU2501→CU2504 换月检测
| **Phase 4 — 模拟交易改写** | 商品交易规则:保证金/杠杆/涨跌停/T+0/到期 | 🟡 **待启动(下一阶段)** | 2-3 周 | `tradingagents/paper/{spec,matcher,pnl,account,risk,repo}.py` + 下单页 + from_decision | 下单 1 手 CU 多单 → 持仓列表 → 隔日盯市 | screenshot:商品模拟交易全流程 |
| **Phase 5 — 删除股票(最终)** | 清理所有 stock_* 文件/集合/路由/视图 | 🟡 待启动 | 1-2 周 | 见 §6 清理清单 | `docker compose up` 启动后只剩商品功能 | `grep -rE "stock_basic_info" tradingagents/ app/ --include="*.py"` 为空 |

### 1.5 增量部署设计(边开发边展示)

为支持"一边开发,一边部署向我展示"的需求,采用 **Feature Flag + Docker 复用 + 进度文档**
三件套。

#### 1.5.1 Feature Flag 机制(开关默认关闭)

`.env` 增加 4 个开关(默认全部 false,严格渐进开启):

```bash
# 总开关(关闭时 commodity_* 路由返回 404)
FEATURE_COMMODITY_ENABLED=false
# Phase 1 起:商品数据可拉取/查询
FEATURE_COMMODITY_DATA=false
# Phase 3 起:商品分析师任务可提交(原 Phase 2 改名为 analysis)
FEATURE_COMMODITY_ANALYSIS=false
# Phase 4 起:商品模拟交易
FEATURE_COMMODITY_PAPER=false
```

`app/core/config.py` 读取这 4 个值。各 commodity 路由注册时检查
`settings.FEATURE_COMMODITY_ENABLED`,关闭时 `app.include_router(commodity_router)` 不执行,
访问 `/api/commodity/*` 自动 404。路由内部按需再检查子开关。

前端通过 `VITE_FEATURE_COMMODITY_ENABLED` 控制菜单渲染。新增 `GET /api/config/features`
端点返回当前 flag 状态,前端 store 读取后控制菜单项显示。

**好处**:
- 商品功能未完成时,主流程不受影响
- 每个 Phase 完成后"开一个开关"就能演示新功能
- 生产环境可以彻底关闭(Phase 5 前)
- 任意 Phase 出问题,关闭 flag 即可回滚到稳定状态

#### 1.5.2 Docker 集成(零侵入复用)

复用现有 `docker-compose.yml`:后端/前端/mongodb/redis 三个服务**完全不变**。

- `Dockerfile.backend` 已经 `COPY tradingagents ./tradingagents` 和 `COPY app ./app`,新增
  `tradingagents/core/instrument.py`、`app/routers/commodity/` 等会被自动包含
- `Dockerfile.frontend`(推测 `npm run build` + nginx),新增 `frontend/src/views/Commodity/`
  自动打包
- 构建镜像版本号:`VERSION=1.0.1-commodity-phase2`(附录 A 集中管理)

#### 1.5.3 进度文档

每个 Phase 完成时,新建 `docs/progress/phase-N.md`,记录:
- 完成项清单(明确**已交付** vs **未交付**)
- 修改/新增文件
- 真实数据验证截图或 curl 输出(**必须实测,不夸大**)
- 一键演示脚本命令
- 已知问题 / 限制
- 下阶段计划

**诚实约定**(2026-07-13 教训):文档必须区分
1. **代码完成** — 单元测试通过、函数签名正确
2. **后端路由完成** — HTTP 端点可访问,curl 能拿到数据
3. **前端完成** — 浏览器能看到 UI,Axios 调用返回真实数据
4. **用户可演示** — 翻 flag + 浏览器访问有数据

不达标的项目必须标 ❌ 并说明影响范围。

现已存在:
- [`docs/progress/phase-0.md`](../progress/phase-0.md) — 抽象统一 ✅
- [`docs/progress/phase-1.md`](../progress/phase-1.md) — 数据闭环-行情 ✅(3a 补齐 flags/前端)
- [`docs/progress/phase-2.md`](../progress/phase-2.md) — 数据层完备 ✅(3a 补齐路由/前端)
- [`docs/progress/phase-3a.md`](../progress/phase-3a.md) — 路由 + 前端补全 ✅
- [`docs/progress/phase-3b.md`](../progress/phase-3b.md) — 多源情报 + 分析师扩展 🟡 待启动

---

## 2. Commodity 数据源设计(Phase 2 落定)

### 2.1 目录结构

```
tradingagents/dataflows/providers/commodity/
├── __init__.py
├── base_commodity_provider.py    # ABC,4 个 @abstractmethod + 13 扩展接口
├── commodity_metadata.py         # 6 交易所 + 80 品种 + 主力连续 + 交易时间
├── commodity_utils.py            # CommodityMarket 枚举 + 标的识别
└── akshare_futures.py            # 主 provider(13 扩展接口 + 6 类新闻)
```

**新 provider 接入约定**(未来扩展 yfinance_futures / tushare_futures 等):
- 新建 `tradingagents/dataflows/providers/commodity/<name>.py`,继承
  `BaseCommodityDataProvider`,至少实现 3 个 `@abstractmethod`(connect /
  get_commodity_basic_info / get_commodity_quotes / get_historical_data)
- 13 个扩展接口按需实现;不实现的保留父类默认 `NotImplementedError`
- 在 `app/services/commodity/unified_commodity_service.py` 注册 provider key 与优先级

### 2.2 ABC 强约束 vs 扩展可选

**强制(`@abstractmethod`,不实现则无法实例化)**:
- `async connect()`
- `async get_commodity_basic_info(full_symbol=None)` — 基础信息
- `async get_commodity_quotes(full_symbol)` — 实时行情
- `async get_historical_data(full_symbol, start_date, end_date=None)` — 日线 K 线

**扩展(默认 `NotImplementedError`,子类按需重写)**:
| 接口 | AKShare 函数 | 用途 |
|---|---|---|
| `get_fees_and_margin` | `futures_comm_info` / `futures_comm_js` / `futures_fees_info` / `futures_settle` | 手续费/保证金/结算价(多源降级) |
| `get_inventory` | `futures_inventory_em` / `futures_inventory_99` | 库存(EM 优先,99 补全) |
| `get_warehouse_receipt` | `futures_warehouse_receipt_shfe/czce/dce/gfex` | 仓单日报 |
| `get_position_rank` | `futures_dce_position_rank` 等 5 个 | 会员持仓排名 |
| `get_registered_receipt` | `get_receipt` | 注册仓单 |
| `get_spot_price` | `futures_spot_price` | 当日现货+基差 |
| `get_basis_history` | `futures_spot_price_daily` | 历史基差 |
| `get_basis_spot_previous` | `futures_spot_price_previous` | 历史某日基差汇总 |
| `get_roll_yield` | `get_roll_yield_bar` / `get_roll_yield` | 展期收益率(`date` / `symbol` / `var` 三模式) |
| `get_contract_info` | `futures_contract_info_shfe/ine/dce/czce/gfex/cffex` | 合约信息(6 交易所分支) |
| `get_trading_calendar` | `futures_rule` | 交易日历 |
| `get_realtime_quote` | `futures_zh_spot` / `futures_zh_realtime` | 实时行情(CF/FF market) |
| `get_minute_kline` | `futures_zh_minute_sina` | 1/5/15/30/60 分钟 K 线 |
| `get_delivery_info` | `futures_delivery_dce/czce/shfe` 或 `futures_to_spot_*` | 交割统计/期转现 |
| `get_holding_position` | `futures_hold_pos_sina` | 期货成交持仓 |
| `get_futures_news` | `futures_news_shmet` + 5 类合成器 | 资讯(详见 §3) |

### 2.3 commodity_metadata 静态字典

**6 大交易所**(CFFEX / SHFE / INE / DCE / CZCE / GFEX),每个交易所含
`code / suffix / name_cn / homepage / abbreviation_akshare`。

**80+ 品种字典**(以 2024-11-18 AKShare 期货快照为准,关键统计数据):
| 类别 | 数量 | 典型品种 |
|---|---|---|
| 金属(贵金属 + 有色 + 黑色) | ~28 | CU/AU/AG/RB/HC/NI/SN |
| 能化(化工 + 能源) | ~22 | SC/FU/BU/TA/MA/EG/PTA/PVC/PP |
| 农产品(粮油 + 农副) | ~24 | A/C/M/Y/P/RB/JD/LH/AP/CJ/SR |
| 金融期货(股指 + 国债) | 8 | IF/IH/IC/IM/TS/TF/T/TL |
| 国际能源(INE) | 5 | SC/NR/LU/EC/BC |
| 广期所 | 3 | SI/LC/PS |

每个品种字段:`variety_code / symbol / name_cn / abbreviation_akshare / category / unit /
contract_size / tick_size / list_date / exchange`。

**主力连续代码对照表**(`MAIN_CONTINUOUS_SYMBOLS`):约 60 个品种的"代码 + 0"主力连续代码,
供 `futures_main_sina` / 历史 K 线接口使用。

**交易时间表**(部分品种,其他用交易所默认):
- 有夜盘(21:00 开):CU/AL/AU/AG/RB/HC/SC/BC/NR/LU 等
- 无夜盘:CFFEX 股指/国债、CZCE 苹果红枣、DCE 生猪鸡蛋、GFEX 全部
- 夜盘结束时间:SHFE 金属/贵金属 01:00-02:30 不等,DCE/CZCE 默认 23:00

**归一化工具**:`normalize_exchange_code()` 接受 `SHF` / `CZC` / `CFX` / `上期所` / `shfe`
等任意形式的输入,统一输出 `SHFE` / `CZCE` / `CFFEX` 等。

### 2.4 Provider 调用约定

**懒加载**:`AkshareFuturesProvider.connect()` 不会在 import 时加载,首次 `_call` 才触发
`import akshare as ak`。`_ak` 字段缓存引用,短路避免重复加载。

**短路 `_ensure_ak()`(关键)**:`if self._ak is not None: return True` — 单元测试注入 mock 时
不会被真实 akshare 覆盖。

**Mock 友好**:所有 provider 都依赖 `self._call(func_name, *args, **kwargs)`,单元测试用
`MagicMock` 注入 `provider._ak`,然后断言 `mock.futures_xxx.assert_called_with(...)`,
不需要真实网络。

**`_safe_call()` 全局吞错**:每个 AKShare 接口都可能因接口降级 / 数据缺失 / 网络异常而抛错,
统一返回 `None`,不污染调用方。

---

## 3. Commodity 新闻管道设计(Phase 2 核心交付)

> **为什么这层很关键**:股票侧有 `stock_info_*` 系列(>30 个资讯源),商品侧可用文本快讯只有
> `futures_news_shmet`(覆盖有色金属 + 贵金属 + 小金属 + 财经 + 要闻 + VIP)。化工 / 能源 /
> 农产品 / 金融期货的文本快讯**AKShare 没有**,只能从宏观 + 产业数据接口**合成"基本面事件卡片"**。
>
> 因此 news 不是一个 list endpoint,而是一个**多源聚合 + 情感评分**的统一通道。

### 3.1 6 类别接口

| `category` 参数 | 数据路径 | AKShare 接口 | 输出形态 |
|---|---|---|---|
| `metal` / `copper` / `aluminum` / `lead` / `zinc` / `nickel` / `tin` / `precious` / `minor` / `headline` / `vip` / `finance` | **shmet 文本快讯** | `futures_news_shmet` | 标题/内容/发布时间 + 情感分 |
| `chemical` | **油价调整合成器** | `energy_oil_hist` | "汽柴油调价-YYYY-MM-DD" 卡片 |
| `energy` | **油价 + 六大电日耗** | `energy_oil_hist` + `macro_china_daily_energy` | "汽柴油调价-..." + "电厂日耗煤-..." 卡片 |
| `agricultural` | **批发价 200 指数 + 生猪 + 糖进口** | `macro_china_agricultural_product` + `futures_hog_supply` + `index_hog_spot_price` + `index_outer_quote_sugar_msweet` | 4 类卡片(指数日报 / 猪肉批发价日报 / 生猪市场行情指数 / 食糖进口日报) |
| `financial` | **QVIX + 美债 + SHIBOR + LPR** | `index_option_*_qvix` + `bond_zh_us_rate` + `macro_china_shibor_all` + `macro_china_lpr` | IF/IH/IM 隐含波动率 + 国债收益率 + 流动性指标 |
| `global_macro` | **6 源宏观聚合** | `stock_info_cjzc_em` + `stock_info_global_em` + `stock_info_global_futu` + `stock_info_global_ths` + `stock_info_global_sina` + `stock_info_global_cls` | 标题/时间/内容归一化卡片(重点/全部) |

### 3.2 标准化字段

每个新闻字典统一字段(供 AgentState / 前端展示直接消费):

```python
{
    "published_at": "...",     # ISO 字符串(可解析为 datetime)
    "title": "...",            # shmet 解析【标题】
    "content": "...",          # 正文
    "category": "...",         # 标准分类
    "metal": "...",            # 中文标签(供前端展示,如 "有色金属" / "能化")
    "sentiment": "positive" | "negative" | "neutral",
    "sentiment_score": float,  # -1.0 ~ 1.0
    "source": "shmet" | "akshare_synth" | "macro_news_em" | ...,
    "url": "...",              # 可选,global_macro 才有
}
```

### 3.3 情感评分模型

**关键词词典(`_POS_NEWS_KEYWORDS` / `_NEG_NEWS_KEYWORDS`)**:从期货侧常见语料整理,如
"涨停/暴涨/大涨/创新高/突破/上涨" → 正分;"跌停/暴跌/跳水/累库/利空/看空" → 负分。
**截断到 [-1, 1]**,阈值 `±0.3` 切 positive/negative/中性。

**QVIX 阈值(IF/IH/IM 专用)**:
- `QVIX > 30` → -0.5(恐慌,负面)
- `> 25` → -0.4
- `< 22` → +0.2(平稳,正面)
- `< 18` → +0.5(极低,明显正面)

**返回结构**:`get_futures_news(category, limit=50)` → `Optional[List[Dict]]`,任何
category 失败返回 `[]` + warning,不抛异常。

### 3.4 已知 trade-off

| 问题 | 当前策略 | 未来优化 |
|---|---|---|
| 合成卡片无文本叙事,不便 LLM 直接消化 | 卡片内含完整数值,LLM 可自行摘要 | Phase 3 接入 Qwen/DeepSeek 生成"宏观摘要" |
| shmet 仅覆盖有色,化工/能源/农产品/金融无文本快讯 | 5 个合成器从宏观+产业数据合成"事件卡片" | 接入 Wind/iFinD 文本流(Phase 4+) |
| global_macro 6 个源的 schema 差异大 | 6 套 `_parse_*_time()` 归一化为 ISO 字符串 | 统一 MCP 化数据接入,前端按 source 折叠渲染 |
| 时间戳格式各异(财联社只到时分,东财含秒级 ISO) | `_parse_global_macro_time` 6 种格式 fallback | 时间归一为 UTC,前端按交易所 timezone 展示 |

---

## 4. 关键技术决策与理由

### 4.1 为什么 AKShare 而不是 Wind / iFinD / Tushare

- **AKShare**:开源免费,覆盖国内 6 大期交所,**含实时/历史/库存/基差/持仓**,`futures_news_shmet`
  是股票侧没有的独有能力
- **Tushare Pro**:需 token,期货接口不如股票丰富(主要是日线和基础信息)
- **Wind / iFinD**:商业付费,本研究框架"仅用于学习"的目标下成本不可接受

**结论**:AKShare 作为主 provider,加 `yfinance_futures`(国际原油/黄金)作为辅助。

### 4.2 为什么 `asset_type: Literal[...]` 注入而非独立子图

- 同一 LangGraph 的 ConditionalLogic / Propagator / Reflector 完全复用,无需复制
- AgentState 一处加字段,所有节点自然可见
- Phase 5 删除股票时,只需把相关路由/节点从注册表移除

### 4.3 为什么 4 个 FEATURE flag,而不是 1 个总开关

- 子功能可独立灰度:Phase 2 关闭 analyzer 只读数据,Phase 4 关闭 paper 只读分析
- 故障隔离:分析节点 crash 时关闭 `FEATURE_COMMODITY_ANALYSIS`,数据 / 行情仍可用
- 渐进交付给真实用户:运营人员可单独打开"商品详情"给一部分用户,逐步放量

### 4.4 为什么 commodity_metadata 用静态字典而非数据库

- 期货合约规格半年才变(新品种上市偶发),DB 化收益小、运维成本高
- 静态字典方便 codegen(未来可用脚本从交易所官网抓)
- 测试用例只用 `importlib` 加载,无需 MongoDB

### 4.5 为什么 13 扩展接口默认 `NotImplementedError`

- Phase 2 之后实现新 provider(如 `yfinance_futures`)只需重写需要的方法,无需全部实现
- 单元测试可针对**任意扩展接口**断言"未实现 → NotImplementedError",确保 ABC 契约正确
- 防止以后 provider 默默漏实现某个方法

---

## 5. Phase 3+ 详细设计(分析师扩展 + LLM 集成)

### 5.1 多分析师节点

复用现有 LangGraph 节点架构,在 `tradingagents/agents/analysts/commodity/` 下新建:

| 文件 | 功能 | 输入(数据源) | 输出(报告) |
|---|---|---|---|
| `technical_analyst.py` | K 线技术分析 | `get_historical_data` + `indicators.py` | MA/MACD/RSI/BOLL 信号汇总 |
| `fundamental_analyst.py` | 现货 + 基差 | `get_spot_price` + `get_basis_history` | 基差趋势 / 现货升贴水 |
| `position_analyst.py` | 持仓 + 仓单 | `get_position_rank` + `get_warehouse_receipt` + `get_inventory` | 主力席位持仓变化 / 库存去化速率 |
| `macro_analyst.py` | 全球宏观 + 行业情报 | `get_futures_news(global_macro)` + LLM 摘要 | 多空叙事 + 情感评分 |
| `news_analyst.py` | 行业快讯合成 | `get_futures_news(metal/chemical/...)` | 行业事件卡片列表 |

每个 analyst 节点输出一个 `CommodityReport` 对象(Pydantic),`SignalProcessor` 汇总。

### 5.2 CommoditiesTradingAgentsGraph 子类

```python
class CommoditiesTradingAgentsGraph(TradingAgentsGraph):
    """商品图:节点注册替换 + AgentState.asset_type 注入"""

    def _build_analyst_nodes(self):
        return [
            self._make_analyst("technical", commodity_technical_analyst),
            self._make_analyst("fundamental", commodity_fundamental_analyst),
            self._make_analyst("position", commodity_position_analyst),
            self._make_analyst("macro", commodity_macro_analyst),
            self._make_analyst("news", commodity_news_analyst),
        ]

    def propagate(self, full_symbol: str, date: str):
        state = AgentState(
            asset_type="commodity",
            full_symbol=full_symbol,
            trade_date=date,
            ...
        )
        # 现有 Propagator.astream 完全复用,商品侧只在节点层扩展
        return super().propagate(state)
```

### 5.3 路由层集成

> **现状**:Phase 3a 已补齐 22 个数据端点(5 Phase 1 + 15 扩展 + 2 新闻),见
> [`docs/progress/phase-3a.md`](../progress/phase-3a.md) §三。
> Phase 3b 需新增以下分析路由:

新增 `app/routers/commodity/analysis.py`:
- `POST /api/commodity/{full_symbol}/analyze` — 提交分析任务(走队列,异步 SSE 推送)
- `GET /api/commodity/{full_symbol}/reports` — 拉历史报告

queue_service 中加 `asset_type` 字段,使 worker 自动选 graph 子类。

**前置依赖**:必须在 §八 P0 三项修复完成后启动,否则分析师节点产出不可解释。

---

## 6. Phase 4 + Phase 5 设计(后续展望)

### 6.1 Phase 4 - 模拟交易改写

> **完整设计稿**:[`docs/progress/phase-4.md`](../progress/phase-4.md)
> **核心结构**:在 `tradingagents/paper/` 下新建纯规则引擎(spec/matcher/pnl/account/risk/repo),
> 通过 15 个 HTTP 端点暴露,与 Phase 3b CIO 输出通过 `from_decision` 联动。

商品交易规则要点:
- **保证金**:12-20%(品种不同),按 `lots × price × contract_size × margin_rate` 计算占用
- **杠杆**:反向计算 / 实际占用
- **涨跌停板**:±3% / ±5% / ±7% / ±8%(品种不同),下单前预检
- **T+0**:当日可平仓,无交割前的持仓过夜成本
- **到期**:主力合约最后交易日(代码中 `list_date + 12M` 估算,实际取 `get_contract_info`)
- **持仓限额**:单边 / 跨期 / 跨品种都有上限

#### 6.1.1 必须先补的合约规格字段

`tradingagents/dataflows/providers/commodity/commodity_metadata.py` 现有字段:
`variety_code / symbol / name_cn / abbreviation_akshare / category / unit / contract_size / tick_size / list_date`

**Phase 4 前必须新增 4 个字段**(每个品种都要补):
- `multiplier`(= `contract_size`,1 手多少吨) — 已有,语义复用
- `margin_rate`(0~1,按品种)
- `commission_rate`(0~1,双边)
- `limit_up_down_pct`(0~1,如 0.07 表示 ±7%)

参考项目给的 8 个品种保证金率:`RB 8% / CU 7% / AU 6% / AG 8% / I 8% / J 8% / M 6% / Y 6%`,
其余按"交易所保证金 + 3%"(期货公司默认)估算。

#### 6.1.2 模块分层

```
tradingagents/paper/         ← 纯规则引擎(零 LLM)
  spec.py                    合约规格 + 保证金/手续费/涨跌停计算
  matcher.py                 撮合引擎(market/limit/stop + next-bar / current_price 双模式)
  pnl.py                     浮动 / 已实现 PnL
  account.py                 余额/可用/占用/净值/风险度聚合
  risk.py                    止损止盈 + 保证金追缴 + 强平
  repo.py                    MongoDB 4 集合(paper_accounts/orders/positions/fills)

app/routers/commodity/paper_rules.py   ← 15 HTTP 端点
app/services/commodity/paper_trading_service.py  ← 业务编排 + from_decision
```

#### 6.1.3 MongoDB 数据模型(4 集合)

- `paper_accounts` — 账户主表(余额/可用/占用/净值/风险度)
- `paper_orders` — 订单表(pending/filled/partial/cancelled/rejected + source=manual/agent_decision)
- `paper_positions` — 净持仓表(avg_cost / current_price / floating_pnl)
- `paper_fills` — 成交明细表(append-only)
- `paper_daily_snapshots` — 日终快照(供 PnL 折线图)

#### 6.1.4 联动 Phase 3b

`POST /api/commodity/paper/from-decision` 接 CIO 输出:
- neutral 决策不下单
- direction=long/short → 计算手数(Kelly / fixed / volatility / risk_parity)
- entry_price_range 中点 → 限价单
- stop_loss / take_profit → 订单附带字段

#### 6.1.5 Feature Flag

```bash
# .env(Phase 4 完成后翻 true)
FEATURE_COMMODITY_PAPER=true
```

```python
# app/main.py(在 FEATURE_COMMODITY_ANALYSIS 注册段之后)
if settings.FEATURE_COMMODITY_PAPER:
    from app.routers.commodity import paper_router
    app.include_router(paper_router, prefix="/api")
```

#### 6.1.6 关键参考点

借鉴参考项目 `期货TradingAgents系统_交易员.py` 的:
- `_kelly_criterion_sizing` (line 633) — 凯利公式 + 分数凯利(0.25x)
- `_volatility_based_sizing` (line 656) — 目标波动率 / 预期波动率
- `OrderType` 枚举 (line 64-69) — market / limit / stop / stop_limit
- `RiskParameters` (line 92-103) — stop_loss_price / take_profit_price 字段名

不复用参考项目的:
- 模拟撮合 / 账户体系 / 持仓跟踪 / PnL 演化 / 强平 / 多用户 — **参考项目完全没有,Phase 4 从零设计**

### 6.2 Phase 5 - 删除股票(最终)

清理清单:
1. `tradingagents/agents/analysts/{market,news,social_media,fundamentals,china_market}.py`(股票侧 analyst)
2. `tradingagents/agents/utils/{stock_toolkit,memory}.py`
3. `tradingagents/dataflows/providers/{china,us,examples}/`(股票 providers)
4. `app/routers/` 全部 `stock_*` 路由
5. `app/services/stock_*` / `app/models/stock_*`
6. `frontend/src/views/Stock/*`
7. MongoDB 集合:`stock_basic_info / stock_quotes / ...` 全部 drop
8. `.env` 移除 `TUSHARE_TOKEN / AKSHARE_TOKEN` 等已废弃项

最终 `grep -rE "stock_basic_info" tradingagents/ app/ --include="*.py"` 为空。

---

## 附录 A:版本与 Feature Flag 映射

| Phase | flag | 默认值 | 完成后(实际状态) | docker 镜像 tag |
|---|---|---|---|---|
| 0 | `FEATURE_COMMODITY_ENABLED` | false | ✅ true(已翻)| `1.0.1-commodity-phase0` |
| 1 | `+ FEATURE_COMMODITY_DATA` | false | ✅ true(Phase 3a 一并翻) | `1.0.1-commodity-phase1` |
| 2 | (路由层不变,数据层升级) | - | ✅ provider 完成(Phase 3a 补齐路由/前端) | `1.0.1-commodity-phase2` |
| 3a | `+ FEATURE_COMMODITY_DATA` 启用 + 22 路由 + 前端 | - | ✅ **完成**(后端 22 端点全 200 + 前端 4 文件) | `1.0.1-commodity-phase3a` |
| 3b | `+ FEATURE_COMMODITY_ANALYSIS` 启用 + 6 子阶段(Features→分析师→决策链→子图→路由→E2E) | false | ✅ **全部完成**(174+ 测试 0 失败,E2E DeepSeek 实测通过) | `1.0.1-commodity-phase3b` |
| 4 | `+ FEATURE_COMMODITY_PAPER` | false | 🟡 **待启动(下一阶段)** | `1.0.1-commodity-phase4` |
| 5 | 商品完全替代股票 | - | 🟡 待启动 | `2.0.0-commodity-only` |

**flag 启用步骤**(任何 Phase 都必须先翻 flag 才能验证):
```bash
sed -i 's/^FEATURE_COMMODITY_ENABLED=false/FEATURE_COMMODITY_ENABLED=true/' .env
sed -i 's/^FEATURE_COMMODITY_DATA=false/FEATURE_COMMODITY_DATA=true/' .env
# Phase 3b 额外:
sed -i 's/^FEATURE_COMMODITY_ANALYSIS=false/FEATURE_COMMODITY_ANALYSIS=true/' .env
```

## 附录 B:命名示例速查

```python
# 数据访问
quotes = await akshare_provider.get_commodity_quotes("CU2501.SHF")
history = await akshare_provider.get_historical_data("CU2501.SHF", "2024-01-01")
inventory = await akshare_provider.get_inventory("A")
news = await akshare_provider.get_futures_news("metal", limit=20)

# 标的识别
CommodityMarket.CHINA_FUTURES == CommodityUtils.identify_market("CU2501.SHF")  # True
is_china_futures("CU2501.SHF")  # True
is_international_futures("CL=F")  # True

# AgentState(待 Phase 3)
state = AgentState(asset_type="commodity", full_symbol="CU2501.SHF", trade_date="2024-12-20")
```
