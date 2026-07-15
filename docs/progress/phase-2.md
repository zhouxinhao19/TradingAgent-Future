# Phase 2 - 数据层完备(Commodity 数据层 + 新闻管道)完成报告

> 详见 plan: [`docs/plans/stock-to-commodity.md`](../plans/stock-to-commodity.md) §1.4 + §2 + §3

**完成日期**: 2026-07-13
**状态**: ⚠️ **数据层 + 单测完成;后端路由未增;前端 UI 未交付**

| 维度 | 状态 |
|---|---|
| 13 扩展接口 + 6 类新闻(provider 层实现) | ✅ 完成 |
| 82 品种 commodity_metadata | ✅ 完成 |
| 单元测试(85/85 通过) | ✅ 完成 |
| 后端 commodity 新路由(inventory/news/...) | ❌ **0 路由** |
| Feature Flag 启用(`.env`) | ❌ **仍是 false**(沿用 Phase 1) |
| 前端 commodity 视图/路由/API 层 | ❌ **0 文件**(沿用 Phase 1) |
| 浏览器端可演示 | ❌ **Phase 1 后端 + 翻 flag 也只能 curl,前端仍空白** |

---

## ✅ 已完成项(provider + 单测)

### 1. 静态元数据扩展(`commodity_metadata.py`)

- ✅ **82 个品种**(覆盖 6 大交易所),必填字段齐备
- ✅ `MAIN_CONTINUOUS_SYMBOLS`:约 60 个主力连续代码映射
- ✅ `_TRADING_HOURS`:20 个核心品种精细化 + `_EXCHANGE_DEFAULT_HOURS` 兜底
- ✅ `normalize_exchange_code()`:接受 `SHF / CZC / CFX / 上期所 / shfe` 等任意输入

实测:

```python
>>> from tradingagents.dataflows.providers.commodity.commodity_metadata import variety_summary
>>> variety_summary()
{'total_varieties': 82, 'total_exchanges': 6,
 'by_exchange': {'CFFEX': 8, 'CZCE': 21, 'DCE': 22, 'GFEX': 3, 'INE': 5, 'SHFE': 26},
 'by_category': {'agricultural': 28, 'chemical': 21, 'energy': 6,
                 'financial': 8, 'metal': 16, 'precious': 2}}
```

### 2. ABC 扩展接口(`base_commodity_provider.py`)

13 个扩展接口 + `get_futures_news` 抽象方法,默认 `NotImplementedError`:

| 接口 | AKShare 对接 |
|---|---|
| `get_fees_and_margin` | `futures_comm_info / comm_js / fees_info / settle` 多源降级 |
| `get_inventory` | `futures_inventory_em` 优先,`futures_inventory_99` 补全 |
| `get_warehouse_receipt` | 6 交易所分支 |
| `get_position_rank` | `get_shfe_rank_table / get_cffex_rank_table / ...` |
| `get_registered_receipt` | `get_receipt` |
| `get_spot_price` | `futures_spot_price` |
| `get_basis_history` | `futures_spot_price_daily` |
| `get_basis_spot_previous` | `futures_spot_price_previous` |
| `get_roll_yield` | `get_roll_yield_bar`(3 模式) |
| `get_contract_info` | 6 交易所分支 |
| `get_trading_calendar` | `futures_rule` |
| `get_realtime_quote` | `futures_zh_spot / futures_zh_realtime` |
| `get_minute_kline` | `futures_zh_minute_sina` |
| `get_delivery_info` | `futures_delivery_*` / `futures_to_spot_*` |
| `get_holding_position` | `futures_hold_pos_sina` |
| `get_futures_news` | `futures_news_shmet` + 5 类合成器 |

### 3. AkshareFuturesProvider 扩展实现

- ✅ 13 扩展接口 + `get_futures_news` 完整实现,逐个对应 AKShare 函数
- ✅ `_safe_call()` / `_call()` 异步包装 + 短路早返回
- ✅ `_ensure_ak()` 短路:`if self._ak is not None: return True`(避免 mock 被真实 akshare 覆盖)
- ✅ `_strip_exchange()` 工具

### 4. 新闻管道(6 类别,provider 层)

#### 4.1 shmet 文本快讯(15 个分类)
`metal / copper / aluminum / lead / zinc / nickel / tin / precious / minor / headline / vip / finance / all`

#### 4.2 合成事件卡片(5 类)
| category | 合成来源 | 卡片示例 |
|---|---|---|
| `chemical` | `energy_oil_hist` | "汽柴油调价-YYYY-MM-DD" |
| `energy` | `energy_oil_hist` + `macro_china_daily_energy` | 油价 + 六大电日耗 |
| `agricultural` | 4 个源 | 批发价200指数 / 猪肉批发价 / 生猪市场行情指数 / 食糖进口日报 |
| `financial` | 6 个源 | IF/IH/IM 隐含波动率 + 国债收益率 + 流动性指标 |
| `global_macro` | `stock_info_*` 6 个源 | 标题/时间/内容归一化卡片 |

#### 4.3 情感评分
- ✅ 期货专用词典(±1 截断)
- ✅ QVIX 阈值(30/25/22/18 四档 → -0.5 ~ +0.5)
- ✅ 三标签:positive / neutral / negative

### 5. 单元测试(85/85 通过)

```
$ python -m pytest tests/test_commodity_data_layer.py --tb=no -q
85 passed, 1 warning in 3.94s
```

6 个测试类:`TestCommodityMetadata`(13) / `TestCommodityUtils`(7) / `TestBaseProvider`(3) /
`TestAkshareProvider`(13) / `TestAkshareIntegration`(28+) / 参数化(15)。
无 pytest-asyncio 依赖,全部 `asyncio.run()` 同步包装。

---

## ❌ 未完成项(必须诚实标注)

### 1. 后端路由未增

Phase 2 仅在 provider / 数据层扩展,**没有新增任何 commodity 路由**:
- ❌ `GET /api/commodity/{symbol}/inventory` 不存在
- ❌ `GET /api/commodity/{symbol}/warehouse-receipt` 不存在
- ❌ `GET /api/commodity/{symbol}/spot-price` 不存在
- ❌ `GET /api/commodity/{symbol}/basis` 不存在
- ❌ `GET /api/commodity/{symbol}/position-rank` 不存在
- ❌ `GET /api/commodity/news?category=metal` 不存在
- ❌ ... 等等 13+ 个端点全部缺失

**影响**:即使翻 flag,用户也只能 curl Phase 1 的 5 个端点;13 扩展接口和新闻**外部不可达**,只能在 Python 里直接调用 provider。

### 2. Feature Flag 沿用 Phase 1,未启用

`.env` 中 4 个 `FEATURE_COMMODITY_*` 仍是 false,即使 Phase 1 的 5 个路由也未对外暴露。

### 3. 前端 commodity UI 仍为 0

Phase 1 已暴露:6 个前端文件全部缺失,Phase 2 没补。Phase 3 必须补齐,否则商品功能完全无 UI。

---

## 🔍 实测验证(2026-07-13)

### Python 直调 ✅ 全 OK

```python
>>> import asyncio
>>> from tradingagents.dataflows.providers.commodity.akshare_futures import AkshareFuturesProvider
>>> p = AkshareFuturesProvider()
>>> items = asyncio.run(p.list_all_varieties())
>>> len(items)
82
>>> info = AkshareFuturesProvider._build_basic_info('CU2501.SHF')
>>> info['name']
'CU期货2025年01月合约'
>>> news = asyncio.run(p.get_futures_news(category='metal', limit=3))
>>> len(news)
3  # 真实拿到 shmet 快讯 3 条
```

### 后端 HTTP ❌ 失败

```bash
$ curl http://localhost:8000/api/commodity/CU2501.SHF/inventory
{"detail": "Not Found"}  # 路由不存在

$ curl http://localhost:8000/api/commodity/news
{"detail": "Not Found"}  # 路由不存在
```

### 前端浏览器 ❌ 空白

无 commodity 路由,跳转 404。

---

## 📁 文件清单(实测确认)

**修改(2 个)**:
- `tradingagents/dataflows/providers/commodity/base_commodity_provider.py` ✅
- `tradingagents/dataflows/providers/commodity/akshare_futures.py` ✅(重磅扩展)

**新增(1 个)**:
- `tests/test_commodity_data_layer.py` ✅(85 测试)

**未交付(本应新增,实际未做)**:
- `app/routers/commodity/inventory.py` / `spot.py` / `basis.py` / `news.py` 等 ~ 14 个路由
- `app/services/commodity/` 对应服务层
- 6 个前端文件(view / router / api / store)

---

## 🚀 如何真正使用本 Phase 能力

**Python 层面(已可用)**:
```python
import asyncio
from tradingagents.dataflows.providers.commodity.akshare_futures import AkshareFuturesProvider

p = AkshareFuturesProvider()
# 库存
inv = asyncio.run(p.get_inventory("A"))
# 现货
sp = asyncio.run(p.get_spot_price("20240715"))
# 持仓
pos = asyncio.run(p.get_position_rank("DCE", "20240715", vars_list=["A"]))
# 6 类新闻
for cat in ["metal", "chemical", "energy", "agricultural", "financial", "global_macro"]:
    news = asyncio.run(p.get_futures_news(category=cat, limit=10))
    print(f"{cat}: {len(news) if news else 0} 条")
```

**HTTP 层面(需 Phase 3 补路由后)**:
```bash
# 当前:404
# 完成后:
curl http://localhost:8000/api/commodity/A.DCE/inventory
curl 'http://localhost:8000/api/commodity/news?category=metal&limit=20'
```

---

## 🟡 已知问题 / 限制

1. **后端路由缺失**:13 扩展接口 + 6 类新闻虽在 provider 实现,但**未暴露为 HTTP 端点**,外部消费者无法触达
2. **AkShare 接口可能临时故障**:`_safe_call()` 吞错返回 `None`,数据缺失时静默
3. **合成卡片 LLM 友好度有限**:title 是模板字符串(如"汽柴油调价-2024-09-04"),content 是数值表,Phase 3 接入 LLM 需做"宏观叙事化"
4. **global_macro 6 源 schema 差异大**:东财/富途/同花顺含标题+摘要;新浪只有时间+内容;财联社时间只有时分秒
5. **国内现货 channel 暂未接入**:SGE/SHFE 现货报价待后续

---

## 🔜 下阶段计划: Phase 3 - 多源情报 + 分析师扩展(强制含前端)

Phase 3 必须包含**前端补全**(否则后端能力再强用户看不到),建议拆为两个子阶段:

### Phase 3a - 路由 + 前端补全(预计 3-4 天)
1. `app/routers/commodity/` 新增 ~14 个路由(inventory / spot / basis / news / position-rank / warehouse-receipt / ...)
2. `app/services/commodity/` 对应服务层封装
3. 翻 `FEATURE_COMMODITY_ENABLED=true` + `FEATURE_COMMODITY_DATA=true`
4. 前端 6 个 commodity 文件:
   - `views/Commodity/Detail.vue`(基础信息 + 行情 + K 线 + 库存/基差/新闻 tab)
   - `views/Commodity/Analysis.vue`(预留 Phase 3b)
   - `router/index.ts` 加 commodity 路由
   - `api/commodity.ts`(axios 封装 ~ 14 个端点)
   - `stores/commodity.ts`(Pinia store)
   - `views/Stocks/Search.vue` 增加"商品"搜索入口

### Phase 3b - 分析师节点(预计 1 周)
1. 5 个 analyst 节点:`technical / fundamental / position / macro / news`
2. `CommoditiesTradingAgentsGraph`(继承 `TradingAgentsGraph`)
3. AgentState 增 `asset_type: Literal["stock","commodity"]`,CommodityReport Pydantic
4. `app/routers/commodity/analysis.py`(走队列 + SSE)
5. `tests/test_commodity_analyst.py` 验证 5 节点产出文案稳定
6. 翻 `FEATURE_COMMODITY_ANALYSIS=true`,详情页"分析"按钮可触发

预计周期: **2 周**(原计划 1 周低估前端 + 路由工作量)。