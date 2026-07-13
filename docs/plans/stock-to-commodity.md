# TradingAgents-CN:股票 → 大宗商品 改造方案

## Context

TradingAgents-CN 当前是基于 LangGraph 的多智能体股票分析平台,核心入口 `tradingagents/graph/trading_graph.py:TradingAgentsGraph`,含 FastAPI 后端(`app/`)+ Vue3 前端(`frontend/`)+ MongoDB/Redis。

用户的目标:把整套系统从**股票分析**改造为**大宗商品分析**(能源/金属/农产品/化工等期货与现货)。

**已确认的改造策略**:
- 开发期间"股票"和"大宗商品"**并存**(增量开发,互不污染)
- 大宗商品模块开发**完成后**再统一删除股票代码

**用户尚未决定的开放项**(本方案作为可配置骨架提供,具体值留作 Phase 0 决策):
- 商品范围(全品类/能源/金属/农产品)
- 标的表示(期货合约/主力连续/现货)
- 数据源选型(纯 AKShare / +yfinance / +Wind+iFinD)

方案默认起点:**0 成本(方案 A = AKShare)+ 期货合约为标的(扩展主力连续)+ 全品类预留**。

---

## 1. 总体设计

### 1.1 命名规范

| 维度 | 规范 | 示例 |
|---|---|---|
| 模块/文件 | `commodity_*` | `app/routers/commodity/`, `tradingagents/dataflows/providers/commodity/` |
| MongoDB 集合 | `commodity_*` | `commodity_basic_info`, `commodity_quotes` |
| 标的代码 | `<SYMBOL><YYMM>.<EXCHANGE>` | `CU2501.SHF`, `CL=F`, `AU9999.SGE` |
| API 路径 | `/api/commodity/*` | `/api/commodity/analysis` |
| 前端视图 | `views/Commodity/*` | `Commodity/Detail.vue` |
| 路由 name | `Commodity*` | `CommodityDetail` |
| AgentState | `asset_type: Literal["stock","commodity"]` | 注入 state |

### 1.2 文件组织

平行建立 `commodity_*` 目录(不沿用 `stock_*` 复用),在路由层、状态层通过 `asset_type` 字段连接。删除股票阶段只需移除整组 `stock_*`,互不干扰。

### 1.3 共用层(零修改复用)

完整复用、不改一行:
- `tradingagents/llm_clients/`, `tradingagents/llm_adapters/` — LLM 抽象与标的无关
- `tradingagents/graph/conditional_logic.py`, `graph/reflection.py` — 状态路由/反思通用
- `tradingagents/tools/analysis/indicators.py`(MA/EMA/MACD/RSI/BOLL/ATR/KDJ)— `pd.Series` 计算与品种无关
- `tradingagents/dataflows/cache/*` — 缓存框架通用,仅传不同 collection 名
- `app/core/{database,response,config}.py` — 基础通用
- `app/models/{user,notification,operation_log,config}.py` — 通用模型
- 通用 router(`auth_db, health, sse, websocket_notifications, scheduler, ...`)
- 通用 Vue 组件(Global/通用、Layout/通用)
- 通用页面(`Dashboard`, `Queue`, `Tasks`, `Reports`, `Settings`, `About`, `Auth/*`, `Error/*`)

### 1.4 实施阶段(5 个 Phase)

> **关键约束(用户已确认)**:开发期间股票/商品并存,每个 Phase 都必须能 `docker compose up` 跑通并向你展示进度。

| Phase | 目标 | 周期 | 关键交付 | 可部署演示 | 验证标准 |
|---|---|---|---|---|---|
| **Phase 0 - 抽象统一** | 解耦 stock 概念,引入 `AssetType` / `Instrument` 抽象 | 1-2 周 | `tradingagents/core/instrument.py`、枚举扩展、单元测试 | `docker compose up` 启动 OK,日志显示"商品模块已注册(未启用)",**前端无任何变化** | `pytest tests/test_instrument.py` 全绿,`curl /api/health` 200 |
| **Phase 1 - 数据闭环(行情)** | 商品行情拉取 → MongoDB → API → 前端只读展示 | 2-3 周 | `commodity_*` 集合、3 个 API、详情页 | 开启 `FEATURE_COMMODITY_DATA` 重启,`curl /api/commodity/CU2501.SHF/info` 返回真实数据,前端访问 `/commodity/detail/CU2501.SHF` 显示详情 | 浏览器看到商品详情页 + 实时行情 |
| **Phase 2 - 技术分析闭环** | 复用 market_analyst 工具,完成商品技术分析最小 graph | 2 周 | `commodity/technical_analyst.py`、`CommodityTradingAgentsGraph` 子类、单商品分析 UI | 提交 `CU2501.SHF` + 日期 → 后台跑图 → 前端显示技术分析报告 | 截图:商品技术分析报告完整生成 |
| **Phase 3 - 多分析师扩展** | 供需/宏观/持仓/新闻 4 个商品专属分析师 | 3-4 周 | 4 个 analyst 模块、报告从 4 → 8 份 | 商品详情页"分析报告"tab 出现 5 个报告 | 截图:5 份报告 + 进度报告 |
| **Phase 4 - 模拟交易改写** | 商品交易规则:保证金/杠杆/涨跌停/T+0/到期 | 2 周 | `paper_rules.py`、商品下单页 | 下单 1 手 CU 多单 → 持仓列表显示 → 隔日盯市 | 截图:商品模拟交易全流程 |
| **Phase 5 - 删除股票(最终)** | 清理所有 stock_* 文件/集合/路由/视图 | 1-2 周 | 见 §5 清理清单 | `docker compose up` 启动后只剩商品功能 | `grep -rE "stock_basic_info" tradingagents/ app/ --include="*.py"` 为空 |

### 1.5 增量部署设计(边开发边展示)

为支持"一边开发,一边部署向我展示"的需求,采用 **Feature Flag + Docker 复用 + 进度文档** 三件套。

#### 1.5.1 Feature Flag 机制(开关默认关闭)

`.env` 增加 4 个开关(默认全部 false,严格渐进开启):

```bash
# 总开关(关闭时 commodity_* 路由返回 404)
FEATURE_COMMODITY_ENABLED=false
# Phase 1 起:商品数据可拉取/查询
FEATURE_COMMODITY_DATA=false
# Phase 2 起:商品技术分析任务可提交
FEATURE_COMMODITY_ANALYSIS=false
# Phase 4 起:商品模拟交易
FEATURE_COMMODITY_PAPER=false
```

`app/core/config.py` 读取这 4 个值。各 commodity 路由注册时检查 `settings.FEATURE_COMMODITY_ENABLED`,关闭时 `app.include_router(commodity_router)` 不执行,访问 `/api/commodity/*` 自动 404。路由内部按需再检查子开关。

前端通过 `VITE_FEATURE_COMMODITY_ENABLED` 控制菜单渲染。新增 `GET /api/config/features` 端点返回当前 flag 状态,前端 store 读取后控制菜单项显示。

**好处**:
- 商品功能未完成时,主流程不受影响
- 每个 Phase 完成后"开一个开关"就能演示新功能
- 生产环境可以彻底关闭(Phase 5 前)
- 任意 Phase 出问题,关闭 flag 即可回滚到稳定状态

#### 1.5.2 Docker 集成(零侵入复用)

**复用现有 `docker-compose.yml`**:后端/前端/mongodb/redis 三个服务**完全不变**。

- `Dockerfile.backend` 已经 `COPY tradingagents ./tradingagents` 和 `COPY app ./app`,新增 `tradingagents/core/instrument.py`、`app/routers/commodity/` 等会被自动包含
- `Dockerfile.frontend`(推测 `npm run build` + nginx),新增 `frontend/src/views/Commodity/` 自动打包
- 健康检查 `curl -f http://localhost:8000/api/health` 不变,新 flag 关闭时该端点仍返回 200

**新增可选覆盖文件 `docker-compose.override.yml`**(本地热重载用,不入生产):

```yaml
# docker-compose.override.yml (本地开发,自动加载)
services:
  backend:
    volumes:
      - ./tradingagents:/app/tradingagents
      - ./app:/app/app
  frontend:
    volumes:
      - ./frontend/src:/app/frontend/src
```

`docker compose up` 自动加载该文件,支持热重载。

#### 1.5.3 演示/进度报告机制

每个 Phase 完成后产出三类资产:

1. **进度报告 `docs/progress/phase-N.md`**:完成的清单、验证步骤、已知问题、下阶段计划
2. **截图 `docs/progress/screenshots/phase-N/`**:商品详情页、分析报告、模拟交易等关键界面
3. **一键体验命令**(写入每个 Phase 报告):
   ```bash
   # 复制 env 模板
   cp .env.example .env
   # 启用本 Phase 开关(示例:Phase 1)
   echo "FEATURE_COMMODITY_ENABLED=true" >> .env
   echo "FEATURE_COMMODITY_DATA=true" >> .env
   # 启动
   docker compose up -d
   # 等待 healthy
   docker compose ps
   # 浏览器访问
   # Web:    http://localhost:3000
   # API 文档: http://localhost:8000/docs
   # MongoDB 管理: docker compose --profile management up -d (8082 端口)
   ```

#### 1.5.4 CI 验证(每个 PR 必跑)

`.github/workflows/ci.yml` 增加:

- 后端 `pytest tests/test_instrument.py -v`(Phase 0+)
- 后端 `pytest tests/test_commodity_*.py -v`(Phase 1+)
- 前端 `npm run type-check`(commodity 组件编译无错)
- `docker compose config`(compose 文件语法正确)
- `bash scripts/verify_phase.sh <N>`(本 Phase 端到端冒烟)

#### 1.5.5 数据兼容(无破坏)

- 新建 `commodity_*` MongoDB 集合,**不修改**任何 `stock_*` 集合
- `commodity_*` 集合为空时,UI 显示"暂无数据,请运行同步任务"
- 同步任务 `app/services/commodity/sync_basics_service.py` 与 `sync_quotes_service.py` 单独存在,默认 cron 关闭,手动触发或 docker compose profile

#### 1.5.6 回滚策略

每个 Phase 部署后,如果发现问题:
1. 修改 `.env` 关闭对应 flag → `docker compose restart backend frontend` → 主流程恢复
2. MongoDB commodity 集合保留(不删除),不占用业务
3. 代码回滚通过 `git revert` 单 PR 即可

---

## 2. 关键改造点

### 2.1 数据源层

**核心入口**:`tradingagents/dataflows/data_source_manager.py`(`ChinaDataSource` / `USDataSource` 枚举附近追加)

**扩展**:
- `constants/data_sources.py:DataSourceCode` 新增 `AKSHARE_FUTURES / TUSHARE_FUTURES / YFINANCE_FUTURES / EASTMONEY_FUTURES / SINA_FUTURES`(基础数据源用现有 `LOCAL_FILE` / `MONGODB`)
- `data_source_manager.py` 增加 `CommodityDataSource` 枚举、`_get_commodity_priority_order()`、`_normalize_commodity_symbol()`
- `data_source_manager.py:_get_data_source_priority_order`(line 91)增加 commodity 分支
- `data_source_manager.py:DataSourceManager.__init__`(line 57)增加 `self.commodity_priority_order`

**新建**:`tradingagents/dataflows/providers/commodity/` 子包
- `akshare_futures.py`(国内期货主力 + 历史,优先 `futures_main_sina` / `futures_em`)
- `yfinance_futures.py`(国际主力合约 `CL=F` / `GC=F` / `SI=F` / `HG=F` / `ZC=F`)
- `eastmoney_futures.py`(备用)
- `base_commodity_provider.py`(参考 `base_provider.py`)

**新建**:`tradingagents/utils/commodity_utils.py`(`StockUtils` 镜像)
```python
class CommodityMarket(Enum):
    CHINA_FUTURES = "china_futures"    # SHFE/DCE/CZCE/INE/GFEX
    INTERNATIONAL = "international"    # CME/NYMEX/COMEX/LME/ICE
    SPOT_CN = "spot_cn"                # AU9999.SGE
    UNKNOWN = "unknown"

class CommodityUtils:
    @staticmethod
    def identify_market(code) -> CommodityMarket: ...   # 正则识别
    @staticmethod
    def get_commodity_category(code) -> str: ...        # 金属/能源/农产品/化工/贵金属
    @staticmethod
    def get_currency(code) -> str: ...                  # CNY / USD
    @staticmethod
    def get_unit(code) -> Tuple[str, float]: ...        # (单位, 每点价值)
```

**新建**:`tradingagents/core/instrument.py`(标的抽象 + 工厂)
```python
class Instrument:
    def __init__(self, code, market, category, currency, unit, exchange, ...): ...
    @staticmethod
    def of(code: str, prefer_main: bool = True) -> 'Instrument':
        # 先试股票(快路径),再 commodity
        ...
```

### 2.2 MongoDB 新集合

复用现有 MongoDB 连接,新建以下集合(对应 `stock_*`):

| 集合 | 用途 | 关键索引 |
|---|---|---|
| `commodity_basic_info` | 品种基础信息(替换 `stock_basic_info`) | `{full_symbol:1} unique`, `{exchange:1, category:1}`, `{is_main:1, expire_date:1}` |
| `commodity_quotes` | 实时行情(替换 `market_quotes`) | `{full_symbol:1, updated_at:-1}` |
| `commodity_daily_quotes` | 历史 K 线(替换 `stock_daily_quotes`) | `{full_symbol:1, trade_date:-1}` |
| `commodity_metadata` | 品类/单位/保证金率/涨跌停配置 | `{key:1} unique` |
| `commodity_news` | 商品新闻(替换 `stock_news`) | `{symbols:1, publish_time:-1}` |
| `commodity_supply_demand` | 供需平衡表(替代财报) | `{symbol:1, period:-1}` |
| `commodity_open_interest` | 持仓数据(CFTC/龙虎榜) | `{symbol:1, trade_date:-1}` |
| `commodity_screening_view` | 商品筛选视图(替代 `stock_screening_view`) | `{category:1, exchange:1}` |
| `commodity_sync_meta` | 同步元数据 | `{source:1, last_sync_at:-1}` |

`commodity_basic_info` 关键字段(参考 `app/models/stock_models.py:54`):
```json
{
  "symbol": "CU2501", "full_symbol": "CU2501.SHF",
  "name": "沪铜2501", "english_name": "Copper Futures Jan 2025",
  "category": "metal", "sub_category": "non_ferrous",
  "exchange": "SHFE", "currency": "CNY",
  "underlying": "CU", "underlying_name": "阴极铜",
  "delivery_unit": "吨", "contract_size": 5, "tick_size": 10, "point_value": 50,
  "margin_rate_long": 0.07, "margin_rate_short": 0.07,
  "limit_up": 0.06, "limit_down": 0.06,
  "list_date": "...", "expire_date": "2025-01-15",
  "is_main": false, "main_contract": "CU2502.SHF",
  "source": "akshare", "data_version": 1, "updated_at": ISODate
}
```

`commodity_quotes` / `commodity_daily_quotes` 字段差异:
- 删除 `total_mv` / `circ_mv`(市值对商品无意义)
- **新增** `settlement_price`(结算价,商品交易核心)、`open_interest`(持仓量)、`volume_unit`(手数 + 实际吨数)

### 2.3 智能体层

**现有股票分析师 → 改造方案**:

| 现有分析师 | 改造方案 | 新建商品分析师 |
|---|---|---|
| `market_analyst.py`(技术) | **零修改复用工具绑定**,提示词改写 | `commodity/technical_analyst.py` |
| `fundamentals_analyst.py`(财报/PE/PB) | **不复用**(财报对商品无意义) | `commodity/supply_demand_analyst.py`(供需平衡表) |
| `social_media_analyst.py`(雪球/股吧) | **不复用** | `commodity/position_analyst.py`(CFTC/龙虎榜) |
| `news_analyst.py` | 复用框架,数据源过滤 | `commodity/news_analyst.py` |
| `china_market_analyst.py`(涨跌停/T+1) | **不直接复用** | `commodity/macro_analyst.py`(美元/利率/相关性) |

**新键**:`tradingagents/agents/analysts/commodity/` 子包
- `__init__.py`、`base.py`(`CommodityAnalystBuilder` 抽象基类)
- `technical_analyst.py`、`supply_demand_analyst.py`、`macro_analyst.py`、`position_analyst.py`、`news_analyst.py`

**抽出 `market_analyst.py` 工厂函数**(扩展点):
```python
# tradingagents/agents/analysts/market_analyst.py 抽出
def create_market_analyst_node(llm, toolkit, asset_type="stock"):
    tools = _resolve_tools(toolkit, asset_type)  # commodity 路径加载 commodity/tools/*
    return _build_node(llm, tools, asset_type)
```

**State 扩展**:`tradingagents/agents/utils/agent_states.py:53 AgentState`
- **不删除**现有字段
- **新增**:`asset_type`、`asset_metadata`、`technical_commodity_report`、`supply_demand_report`、`macro_report`、`position_report`、`commodity_news_report`、5 个工具调用计数

**`graph/propagation.py:22 create_initial_state`**:
- 新增 `asset_type` 参数
- HumanMessage 文案根据 `asset_type` 切换(`"请对大宗商品 ... 进行全面分析"`)

**`graph/signal_processing.py:69`**:
- `price_patterns` 扩展支持商品价格区间 + 计量单位(`元/吨` / `元/克` / `美元/盎司` / `美元/桶` / 结算价 `settlement:`)

### 2.4 多智能体图

**决策:新建 `CommodityTradingAgentsGraph`(优于开关切换)**

`tradingagents/graph/trading_graph.py:TradingAgentsGraph` 子类化 + 工厂方法:

```python
# tradingagents/graph/commodity_trading_graph.py (新建)
class CommodityTradingAgentsGraph(TradingAgentsGraph):
    COMMODITY_ANALYST_MAP = {
        "technical": create_commodity_technical_analyst,
        "supply_demand": create_supply_demand_analyst,
        "macro": create_macro_analyst,
        "position": create_position_analyst,
        "news": create_commodity_news_analyst,
    }
```

**`graph/setup.py:65 setup_graph` 扩展**:`selected_analysts` 支持 `commodity.*` 前缀(避免命名冲突)。

### 2.5 后端 API

**新建** `app/routers/commodity/` 子包:
```
commodity/
├── __init__.py        # 统一注册 router
├── analysis.py        # 单商品/批量分析(对标 analysis.py)
├── detail.py          # 商品详情/搜索(对标 stocks.py)
├── quotes.py          # 行情拉取(对标 stock_data.py)
├── screening.py       # 商品筛选(对标 screening.py)
├── sync.py            # 同步任务
├── favorites.py       # 自选商品
├── paper_rules.py     # 商品交易规则(保证金/涨跌停/T+0)
└── historical.py      # 历史 K 线
```

**关键端点**:
- `GET /api/commodity/search?q=&exchange=`
- `GET /api/commodity/{full_symbol}/info` / `quotes` / `historical`
- `POST /api/commodity/analysis/single` / `batch`
- `GET /api/commodity/screening/presets`、`POST /api/commodity/screening/run`
- `GET /api/commodity/categories`(金属/能源/...)、`/exchanges`
- `GET /api/commodity/main-contract/{underlying}`(主力连续)
- `GET /api/commodity/supply-demand/{symbol}`、`/position/{symbol}`

**Feature Flag 集成**(关键):
- `app/main.py` 在 `include_router` 时检查 `settings.FEATURE_COMMODITY_ENABLED`
- `app/routers/commodity/__init__.py` 内部按子开关细分:
  ```python
  if settings.FEATURE_COMMODITY_DATA:
      router.include_router(quotes_router)        # info / quotes / historical
      router.include_router(screening_router)
  if settings.FEATURE_COMMODITY_ANALYSIS:
      router.include_router(analysis_router)      # analysis/single / batch
  if settings.FEATURE_COMMODITY_PAPER:
      router.include_router(paper_rules_router)   # 模拟交易规则
  ```
- 关闭时访问 `/api/commodity/*` 自动返回 404
- 前端 `GET /api/config/features` 返回 `{commodity_enabled, commodity_data, commodity_analysis, commodity_paper}` 4 个 boolean,前端 store 据此显示/隐藏菜单

**新建** `app/services/commodity/` 子包(`unified_commodity_service.py`、`analysis_service.py`、`screening_service.py`、`quotes_service.py`、`paper_rules_service.py`、`supply_demand_service.py`、`position_service.py` 等)

**新建** `app/models/commodity_models.py`:
```python
MarketType = Literal["CN_FUTURES", "INT_FUTURES", "SPOT_CN", "COMMODITY"]
ExchangeType = Literal["SHFE", "DCE", "CZCE", "INE", "GFEX", "NYMEX", "COMEX", "CME", "LME", "ICE", "SGE", ...]
CurrencyType = Literal["CNY", "USD"]
CategoryType = Literal["metal", "energy", "agricultural", "chemical", "precious"]

CommodityBasicInfoExtended:    # 对应 StockBasicInfoExtended
CommodityQuotesExtended:        # 对应 MarketQuotesExtended(新增 settlement_price / open_interest)
```

### 2.6 前端

**新建** `frontend/src/views/Commodity/`:
```
Commodity/
├── Detail.vue                      # 对标 Stocks/Detail.vue
├── Analysis/{Single.vue,Batch.vue} # 对标 Analysis/
├── Screening.vue                   # 对标 Screening/
├── Favorites.vue                   # 对标 Favorites/
├── Quotes.vue                      # 行情中心(可选)
└── Position.vue                    # 持仓龙虎榜(可选)
```

**`router/index.ts` 新增**:`/commodity/...` 路由块(name: `Commodity*`)

**`components/Global/MarketSelector.vue:57` 扩展**:
```typescript
const markets: Market[] = [
  { code: 'CN', label: 'A股', flag: '🇨🇳' },
  { code: 'HK', label: '港股', flag: '🇭🇰' },
  { code: 'US', label: '美股', flag: '🇺🇸' },
  // 新增
  { code: 'COMMODITY_CN', label: '国内商品', flag: '🛢️' },
  { code: 'COMMODITY_INT', label: '国际商品', flag: '🌐' },
  { code: 'COMMODITY_SPOT', label: '现货商品', flag: '💰' },
]
```

**`components/Layout/SidebarMenu.vue` 新增**:`/commodity` sub-menu(单商品/批量/筛选/自选)

**`stores/app.ts` 扩展**:`defaultMarket` 持久化新增 `COMMODITY_*` 值

**`api/commodity.ts`(新建)**:聚合 commodity 后端路由,参考 `stocks.ts` / `screening.ts`

### 2.7 模拟交易改写

**`app/routers/paper.py` 重大改造**(商品规则与股票完全不同):
- **T+0**(可日内平仓)vs A 股 T+1
- **保证金制度**(7%-15% 杠杆)
- **涨跌停**(国内期货 4%-8%,各品种不同)
- **到期交割**(不能无限持有)
- **每日无负债结算**(盯市)
- **手续费 + 保证金利息 + 强平机制**

具体动作:
1. `INITIAL_CASH_BY_MARKET`(line 17)增加 `CNY_FUTURES` / `USD_FUTURES` 键值
2. `_detect_market_and_code` 增加 commodity 分支
3. 新增 `paper_commodity_orders` 集合(字段含 `margin_used` / `leverage` / `force_close_price`)
4. 新增"盯市"函数:每日 `unrealized_pnl` 重算 + `margin_call` 检测
5. 新增 `auto_rollover`(主力合约到期自动移仓)开关

---

## 3. 复用 vs 新建清单

### 3.1 零修改复用(完全共享)

- `tradingagents/llm_clients/`, `tradingagents/llm_adapters/`
- `tradingagents/graph/conditional_logic.py`, `graph/reflection.py`
- `tradingagents/tools/analysis/indicators.py`
- `tradingagents/dataflows/cache/*`
- `app/core/{database,response,config,redis_client,unified_config,config_bridge,logging_config,startup_validator,rate_limiter}.py`
- `app/models/{user,notification,operation_log,config}.py`
- 通用 router(`auth_db, health, sse, websocket_notifications, scheduler, ...`)
- 通用 Vue 组件 + `Dashboard, Queue, Tasks, Reports, Settings, About, Auth/*, Error/*`
- 通用 store / api

### 3.2 扩展(轻改)

| 文件 | 扩展点 |
|---|---|
| `tradingagents/constants/data_sources.py` | `DataSourceCode` 新增 4 个商品源,`DATA_SOURCE_REGISTRY` 新增条目 |
| `tradingagents/dataflows/data_source_manager.py` | `CommodityDataSource` 枚举、`_get_commodity_priority_order`、`_normalize_commodity_symbol` |
| `tradingagents/agents/utils/agent_states.py:53` | 新增 `asset_type` / `asset_metadata` / 5 个 commodity_report 字段 / 5 个工具调用计数 |
| `tradingagents/agents/utils/instrument_utils.py` | 重写支持股票+商品双标的 |
| `tradingagents/graph/propagation.py:22` | 新增 `asset_type` 参数 |
| `tradingagents/graph/signal_processing.py:69` | 扩展 `price_patterns` |
| `tradingagents/graph/setup.py:65` | 解析 `commodity.*` 前缀 |
| `tradingagents/graph/trading_graph.py:TradingAgentsGraph` | 子类化 `CommodityTradingAgentsGraph` |
| `app/services/data_sources/akshare_adapter/` | 增加 commodity 接口封装 |
| `frontend/src/components/Global/MarketSelector.vue:57` | markets 数组 + 3 个商品项 |
| `frontend/src/components/Layout/SidebarMenu.vue` | 新增 `/commodity` sub-menu |
| `frontend/src/stores/app.ts` | 扩展 `defaultMarket` 持久化值 |
| `frontend/src/router/index.ts` | 新增 commodity 路由块 |
| `tradingagents/default_config.py` | 新增 `commodity_*` 默认配置项 |
| `app/routers/paper.py` | 模拟交易改写(保证金/涨跌停/T+0) |

### 3.3 新建

**后端 Python**:
```
tradingagents/core/instrument.py
tradingagents/utils/commodity_utils.py
tradingagents/dataflows/providers/commodity/{akshare_futures,yfinance_futures,eastmoney_futures,base_commodity_provider}.py
tradingagents/agents/analysts/commodity/{base,technical_analyst,supply_demand_analyst,macro_analyst,position_analyst,news_analyst}.py
tradingagents/graph/commodity_trading_graph.py
app/models/commodity_models.py
app/routers/commodity/{__init__,analysis,detail,quotes,screening,sync,favorites,paper_rules,historical}.py
app/services/commodity/{unified_commodity_service,commodity_data_service,analysis_service,screening_service,quotes_service,quotes_ingestion_service,favorites_service,paper_rules_service,supply_demand_service,position_service}.py
```

**前端 Vue/TS**:
```
frontend/src/views/Commodity/
frontend/src/api/commodity.ts
frontend/src/types/commodity.ts(可选)
frontend/src/constants/commodity.ts(可选)
```

**部署/演示配置(增量部署关键)**:
```
.env.example                          # 增加 4 个 FEATURE_COMMODITY_* 默认值
.env.docker                           # 同上,跟随 Dockerfile.backend
docker-compose.override.yml           # 本地热重载卷映射(不入生产)
docs/progress/phase-0.md ... phase-5.md    # 每 Phase 进度报告
docs/progress/screenshots/phase-N/    # 关键界面截图
scripts/verify_phase.sh               # 端到端冒烟脚本(每 Phase 一份)
.github/workflows/ci.yml              # 增加 commodity 单测 + docker compose config
```

---

## 4. 数据源选型(待用户决策)

| 方案 | 国内期货 | 国际主力 | 持仓/库存/基本面 | 成本 | 适合阶段 |
|---|---|---|---|---|---|
| **A. 仅 AKShare** | 完整 | 部分 | 无 | 0 元 | Phase 1-2 MVP |
| **B. AKShare + yfinance** | 完整 | 20+ 主力 | 无 | 0 元 | Phase 2-3 国际商品 |
| **C. + Tushare/Wind/iFinD** | 完整 | 完整 | 完整 | 数万/年 | Phase 3+ 持仓/库存分析师 |

**推荐路径**:A 起步(Phase 1-2)→ B(Phase 2-3)→ C(Phase 3+,持仓/供需分析师需要数据时)。

---

## 5. 风险与陷阱

### 5.1 标的表示
- 合约(`CU2501.SHF`)vs 主力连续(`CU0.SHF` / `CU.SHF`)的区分
- **解决**:数据库存原始合约 + `is_main` + `main_contract` 字段,分析层用 `Instrument.of(code, prefer_main=True)` 自动转主力连续

### 5.2 商品基本面提示词
- 商品基本面与股票财报差异巨大(供需平衡表 vs PE/PB)
- **解决**:5 个商品分析师的提示词需**领域专家 review 环节**,Phase 3 预留 review 时间
- **工作量**:每个分析师 50-100 行提示词 + 工具文档,Phase 3 整体 3-4 周

### 5.3 模拟交易改写
- 股票 T+1 制度、A 股涨跌停完全不适用商品
- **解决**:见 §2.7

### 5.4 删除股票的清理成本
| 类型 | 数量 |
|---|---|
| Python 文件 | ~50 |
| Vue/TS 文件 | ~42 |
| MongoDB 集合 | 9 |
| 代码行数 | ~3 万行 |
| 配置项 | ~80 |
| 工时 | 5-7 工作日 |

**清理脚本策略**:
```bash
grep -rE "stock_basic_info|stock_quotes|stock_daily" tradingagents/ app/ --include="*.py" -l | wc -l
grep -rE "StockMarket|stock_utils\.StockUtils" tradingagents/ app/ --include="*.py" -l | wc -l
```

### 5.5 其他
- **主力合约换月**:商品有"换月"现象,数据需拼接,可用 MongoDB aggregate pipeline 或维护 `commodity_main_daily_quotes` 集合
- **数据延迟**:商品夜盘(21:00-02:30)与日盘不同,调度任务需分夜盘/日盘
- **缓存失效**:主力合约切换日强制刷新,TTL 缩短到 1 天
- **LLM Token 成本**:商品分析师 prompt 较长(供需数据),工具调用分阶段(先技术 + 新闻,再基本面)

---

## 6. 关键文件清单

**改造文件(扩展点)**:
- `C:\Users\59608\Desktop\TradingAgent-CN\tradingagents\dataflows\data_source_manager.py`
- `C:\Users\59608\Desktop\TradingAgent-CN\tradingagents\graph\trading_graph.py`
- `C:\Users\59608\Desktop\TradingAgent-CN\tradingagents\graph\propagation.py`
- `C:\Users\59608\Desktop\TradingAgent-CN\tradingagents\graph\signal_processing.py`
- `C:\Users\59608\Desktop\TradingAgent-CN\tradingagents\graph\setup.py`
- `C:\Users\59608\Desktop\TradingAgent-CN\tradingagents\agents\utils\agent_states.py`
- `C:\Users\59608\Desktop\TradingAgent-CN\tradingagents\agents\utils\instrument_utils.py`
- `C:\Users\59608\Desktop\TradingAgent-CN\tradingagents\agents\analysts\market_analyst.py`(抽出工厂函数)
- `C:\Users\59608\Desktop\TradingAgent-CN\tradingagents\utils\stock_utils.py`(保留不动)
- `C:\Users\59608\Desktop\TradingAgent-CN\tradingagents\constants\data_sources.py`
- `C:\Users\59608\Desktop\TradingAgent-CN\tradingagents\default_config.py`
- `C:\Users\59608\Desktop\TradingAgent-CN\app\routers\paper.py`
- `C:\Users\59608\Desktop\TradingAgent-CN\frontend\src\components\Global\MarketSelector.vue`
- `C:\Users\59608\Desktop\TradingAgent-CN\frontend\src\components\Layout\SidebarMenu.vue`
- `C:\Users\59608\Desktop\TradingAgent-CN\frontend\src\router\index.ts`
- `C:\Users\59608\Desktop\TradingAgent-CN\frontend\src\stores\app.ts`

**Phase 1 启动新建文件**:
- `C:\Users\59608\Desktop\TradingAgent-CN\tradingagents\core\instrument.py`
- `C:\Users\59608\Desktop\TradingAgent-CN\tradingagents\utils\commodity_utils.py`
- `C:\Users\59608\Desktop\TradingAgent-CN\tradingagents\dataflows\providers\commodity\akshare_futures.py`
- `C:\Users\59608\Desktop\TradingAgent-CN\tradingagents\dataflows\providers\commodity\base_commodity_provider.py`
- `C:\Users\59608\Desktop\TradingAgent-CN\app\models\commodity_models.py`
- `C:\Users\59608\Desktop\TradingAgent-CN\app\routers\commodity\__init__.py` + 子路由文件
- `C:\Users\59608\Desktop\TradingAgent-CN\app\services\commodity\unified_commodity_service.py`
- `C:\Users\59608\Desktop\TradingAgent-CN\frontend\src\views\Commodity\Detail.vue`
- `C:\Users\59608\Desktop\TradingAgent-CN\frontend\src\api\commodity.ts`

**部署/演示配置文件(增量部署关键)**:
- `C:\Users\59608\Desktop\TradingAgent-CN\app\core\config.py`(扩展,读取 4 个 `FEATURE_COMMODITY_*`)
- `C:\Users\59608\Desktop\TradingAgent-CN\app\main.py`(include_router 时检查 flag)
- `C:\Users\59608\Desktop\TradingAgent-CN\.env.example`(增加 4 个 flag 默认 false)
- `C:\Users\59608\Desktop\TradingAgent-CN\.env.docker`(同步)
- `C:\Users\59608\Desktop\TradingAgent-CN\docker-compose.override.yml`(本地热重载,新建)
- `C:\Users\59608\Desktop\TradingAgent-CN\app\routers\config.py`(新增,返回 `/api/config/features`)
- `C:\Users\59608\Desktop\TradingAgent-CN\docs\progress\phase-N.md`(进度报告)
- `C:\Users\59608\Desktop\TradingAgent-CN\scripts\verify_phase.sh`(端到端冒烟脚本)

---

## 7. 验证方法

### 7.1 各 Phase 端到端验证

**Phase 0**:
- `tests/test_instrument.py`:`Instrument.of('000001.SZ').asset_type == 'stock'`;`Instrument.of('CU2501.SHF').asset_type == 'commodity'`
- `curl localhost:8000/api/health` → 200
- **部署验证**:`docker compose up -d` → `docker compose ps` 显示 backend/frontend/mongodb/redis 全部 healthy
- **前端不变**:浏览器访问 `http://localhost:3000` 看到原股票分析平台,无任何商品入口
- **后端日志**:`grep "commodity" logs/tradingagents.log` 应看到"商品模块已注册(未启用)"
- **演示快照**:`docs/progress/phase-0/screenshots/backend_log.png`

**Phase 1**:
- `python -c "from tradingagents.dataflows.providers.commodity.akshare_futures import fetch_quotes; print(fetch_quotes('CU2501.SHF'))"`
- MongoDB:`db.commodity_basic_info.findOne({full_symbol: 'CU2501.SHF'})` 返回完整字段
- `curl http://localhost:8000/api/commodity/CU2501.SHF/info` → JSON
- `curl http://localhost:8000/api/commodity/CU2501.SHF/quotes` → 实时行情
- 浏览器 `http://localhost:5173/commodity/detail/CU2501.SHF` → 显示详情页

**Phase 2**:
- `python -c "from tradingagents.graph.commodity_trading_graph import CommodityTradingAgentsGraph; g = CommodityTradingAgentsGraph.create_default(selected_analysts=['technical']); g.analyze('CU2501.SHF', '2025-01-15')"`
- API:`curl -X POST http://localhost:8000/api/commodity/analysis/single -d '{"full_symbol":"CU2501.SHF","trade_date":"2025-01-15","analysts":["technical"]}'` → task_id
- MongoDB `commodity_analysis_results` 含 `technical_report`
- 前端:单商品分析页提交 → 等待 → 报告显示

**Phase 3**:
- 端到端:提交 `CL=F`(WTI)+ 5 个分析师 → 5 份报告齐全(技术/供需/宏观/持仓/新闻)
- UI:商品详情页"分析报告"标签页 5 个 tab
- 人工抽查 3 个不同商品(铜/原油/豆粕)的报告,确认非"模板化"

**Phase 4**:
- 单元:`tests/test_paper_rules.py` 验证保证金计算、涨跌停检测、强平计算
- API:`POST /api/paper/order` 下单 1 手 CU2501 多单,验证 `margin_used` 字段
- API:持仓查询返回 `unrealized_pnl`;模拟主力合约到期,触发 `auto_rollover`

**Phase 5**:
- `grep -rE "stock_basic_info" tradingagents/ app/ --include="*.py"` → 空
- `pytest tests/` → 全绿
- `npm run build` → 成功
- `db.stock_basic_info` → 集合已删除

### 7.2 推荐开发顺序(最小闭环优先)

```
Phase 0
  ↓
Phase 1.1: 单数据源(akshare_futures.py)+ 单商品(CU2501.SHF)+ 静态详情页
  ↓
Phase 1.2: 扩展到 3 个国内商品(CU/AU/AG)+ 搜索 + 列表
  ↓
Phase 2.1: technical_analyst 单分析师跑通最小图
  ↓
Phase 2.2: 单商品分析 UI 完整
  ↓
Phase 3.1~3.4: news → supply_demand → macro → position
  ↓
Phase 4.1~4.2: 保证金/涨跌停/T+0 → 到期日/强平
  ↓
Phase 5: 清理股票(7 工作日)
```

### 7.3 调试命令速查

```bash
# 启动后端
uv run uvicorn app.main:app --reload --port 8000

# 启动前端
cd frontend && npm run dev

# 单元测试
uv run pytest tests/ -v

# MongoDB 查看
mongosh
> use tradingagents
> db.commodity_basic_info.find().limit(5)
> db.commodity_quotes.findOne({full_symbol: 'CU2501.SHF'})

# Redis 缓存查看
redis-cli
> KEYS commodity:*
> TTL commodity:quotes:CU2501.SHF

# 主力合约切换检测
mongosh --eval "db.commodity_basic_info.find({is_main: false, expire_date: {\$lte: new Date()}}).count()"
```

---

## 8. 待用户决策的关键选项(进入 Phase 0 前确认)

| 选项 | 当前默认 | 替代方案 |
|---|---|---|
| **商品范围** | 全品类预留(在 `commodity_basic_info` 集合动态配置) | 限定品类(能源/贵金属+有色/农产品) |
| **标的表示** | `<SYMBOL><YYMM>.<EXCHANGE>`(主力连续用 `<SYMBOL>.MAIN`) | 仅现货 / 期货+现货混合 |
| **数据源选型** | 方案 A(AKShare 起步) | 方案 B(加 yfinance)/ 方案 C(加 Wind+iFinD) |
| **主力合约策略** | `Instrument.of(code, prefer_main=True)` 自动转 | 用户手动选择 / 强制合约模式 |
| **模拟交易** | Phase 4 全改写(保证金/涨跌停/T+0) | 简化版(无保证金,只记盈亏) |
| **Feature Flag 默认值** | 4 个 flag 全部 `false`,严格渐进开启 | 全部默认 `true`(激进) / 调试模式(默认开 + 日志更详细) |
| **进度报告位置** | `docs/progress/phase-N.md` 提交到 git | 单独仓库 / 微信群 / Notion |
| **演示方式** | 本地 `docker compose up` + 截图 + 进度报告 Markdown | 部署到云服务器 / 自动截图 CI |

**推荐默认组合**(除非你有其他偏好):
- 商品范围:全品类
- 标的表示:期货合约(主力连续通过 `prefer_main=True` 自动转)
- 数据源:Phase 1-2 用 AKShare,Phase 3+ 加 yfinance
- 模拟交易:Phase 4 完整改写
- Feature Flag:默认全 false,完成对应 Phase 时翻 true
- 进度报告:Markdown 进 git,截图存 `docs/progress/screenshots/`
- 演示方式:本地 docker compose + 截图 + 进度报告(你已安装 Docker Desktop)

确认后即可进入 Phase 0 实施(预计 1-2 周完成标的抽象与枚举扩展 + 每个 Phase 都可 `docker compose up` 跑通)。

---

## 9. 新会话恢复执行(关掉窗口后怎么续)

**Plan 文件位置**:`C:\Users\59608\.claude\plans\encapsulated-forging-hoare.md`(持久化磁盘,关掉窗口不丢)

### 9.1 启动新会话后第一句话模板

直接复制粘贴(替换 `Phase N` 为当前阶段):

> "请按 plan 文件 `C:\Users\59608\.claude\plans\encapsulated-forging-hoare.md` 执行 Phase 0。当前进度:Phase 0 未开始。"

或更短的:

> "继续执行 `C:\Users\59608\.claude\plans\encapsulated-forging-hoare.md` Phase 0"

### 9.2 让 plan 跨机器/重装也能找到(可选迁移)

当前 plan 在 `~/.claude/plans/` 下,不在 git 仓库内。建议执行以下操作(plan 批准后):

```bash
# 1. 移动到项目 docs 目录(进 git,跨机器可用)
mkdir -p "C:\Users\59608\Desktop\TradingAgent-CN\docs\plans"
mv "C:\Users\59608\.claude\plans\encapsulated-forging-hoare.md" \
   "C:\Users\59608\Desktop\TradingAgent-CN\docs\plans\stock-to-commodity.md"

# 2. 在项目 CLAUDE.md 末尾加引用,新会话自动加载
cat >> "C:\Users\59608\Desktop\TradingAgent-CN\CLAUDE.md" << 'EOF'

## 当前进行中的任务
按 [`docs/plans/stock-to-commodity.md`](docs/plans/stock-to-commodity.md) 推进"股票→大宗商品"改造。
- 当前阶段:Phase N (待确认)
- 启动开关:`FEATURE_COMMODITY_*` 严格按 plan §1.5 渐进开启
- 部署验证:每个 Phase 必须 `docker compose up` 跑通
- 进度产出:`docs/progress/phase-N.md` + 截图
EOF

# 3. 提交
cd "C:\Users\59608\Desktop\TradingAgent-CN"
git add docs/plans/ CLAUDE.md
git commit -m "docs: 引入大宗商品改造方案"
```

迁移后,新会话**不需要再手输 plan 路径** —— `CLAUDE.md` 启动时自动加载,Claude 看到"按 docs/plans/stock-to-commodity.md 推进"就知道要读那个文件。

### 9.3 当前进度怎么追踪

每个 Phase 完成后,在 `docs/progress/phase-N.md` 写:
- ✅ 已完成项
- 🟡 进行中项
- ❌ 已知问题
- 🔜 下阶段计划

新会话第一句话先看 `docs/progress/`,就能立即接上。

### 9.4 如果 plan 文件丢失

plan 文件全部内容也在本次对话的"Plan 文件"system-reminder 里,可以从那里重新写入 `docs/plans/stock-to-commodity.md`,或用以下命令从 plan 文件夹恢复:

```bash
ls "C:\Users\59608\.claude\plans\"     # 找到最新 plan
```

如果整个 `.claude/plans/` 被清理了(重装系统),就只能从对话历史里复制。**所以建议尽快执行 §9.2 的迁移,把 plan 提交到 git**。
