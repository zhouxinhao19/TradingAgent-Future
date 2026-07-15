# Phase 1 - 数据闭环(行情)完成报告

> 详见 plan: [`docs/plans/stock-to-commodity.md`](../plans/stock-to-commodity.md) §1.4

**完成日期**: 2026-07-13
**状态**: ⚠️ **代码层完成;前端 UI 未交付;Feature Flag 未启用**

| 维度 | 状态 |
|---|---|
| 后端 commodity 数据 provider | ✅ 完成 |
| 后端 commodity service + router(5 端点) | ✅ 完成 |
| 后端 flag gating 逻辑 | ✅ 完成 |
| Feature Flag 启用(`.env`) | ❌ **仍是 false** |
| 前端 commodity 视图/路由/API 层 | ❌ **0 文件** |
| 浏览器端可演示 | ❌ **当前不能访问任何商品页面** |

---

## ✅ 已完成项(代码层)

### 1. 数据源层
- ✅ `tradingagents/dataflows/providers/commodity/base_commodity_provider.py` — 抽象基类
- ✅ `tradingagents/dataflows/providers/commodity/akshare_futures.py` — AKShare 国内期货主力数据源
  (`get_commodity_basic_info / get_commodity_quotes / get_historical_data`)

### 2. 服务层
- ✅ `app/services/commodity/unified_commodity_service.py` — 统一服务,懒加载 provider

### 3. API 路由
- ✅ `app/routers/commodity/quotes.py` — 5 个端点:
  - `GET /api/commodity/categories`
  - `GET /api/commodity/exchanges`
  - `GET /api/commodity/{full_symbol}/info`
  - `GET /api/commodity/{full_symbol}/quotes`
  - `GET /api/commodity/{full_symbol}/historical`
- ✅ `app/main.py:739-756` 增加 `if settings.FEATURE_COMMODITY_ENABLED and FEATURE_COMMODITY_DATA: include_router`
  条件加载

### 4. Feature Flag(代码)
- ✅ `.env` 已声明 4 个 `FEATURE_COMMODITY_*` 开关
- ✅ `app/main.py` 启动日志按 flag 输出"已注册"/"未启用"
- ❌ **`.env` 中 4 个 flag 当前仍是 false**(实测于 2026-07-13)

---

## ❌ 未完成项(必须诚实标注)

### 1. Feature Flag 未启用

```bash
$ grep -E "FEATURE_COMMODITY" .env
FEATURE_COMMODITY_ENABLED=false
FEATURE_COMMODITY_DATA=false
FEATURE_COMMODITY_ANALYSIS=false
FEATURE_COMMODITY_PAPER=false
```

**影响**:即使启后端,`/api/commodity/*` 全部 404(因为 `include_router` 没执行)。

### 2. 前端 commodity UI 0 交付

```bash
$ ls frontend/src/views/
About  Analysis  Auth  Dashboard  Error  Favorites  Learning  PaperTrading
Queue  Reports  Screening  Settings  Stocks  System  Tasks
# ↑ 没有 Commodity 目录

$ grep -rn "commodity\|商品" frontend/src/router/
# ↑ 无任何匹配

$ grep -l "commodity" frontend/src/api/*.ts
# ↑ 无任何匹配
```

**缺失文件**(Phase 3 必修):
- `frontend/src/views/Commodity/Detail.vue` — 商品详情页
- `frontend/src/views/Commodity/Analysis.vue` — 分析报告页
- `frontend/src/views/Commodity/News.vue` — 新闻页
- `frontend/src/router/` 增加 commodity 路由
- `frontend/src/api/commodity.ts` — axios 封装
- `frontend/src/stores/commodity.ts` — Pinia store

---

## 🔍 实测验证(2026-07-13)

### 数据层 Python 直调 ✅ OK

```python
>>> from tradingagents.dataflows.providers.commodity.akshare_futures import AkshareFuturesProvider
>>> AkshareFuturesProvider._build_basic_info('CU2501.SHF')
{'full_symbol': 'CU2501.SHF', 'name': 'CU期货2025年01月合约', 'exchange': 'SHF', 'underlying': 'CU',
 'unit': '吨', 'contract_size': 5.0, 'tick_size': 10, 'is_china_futures': True, ...}
```

### 后端 HTTP 调用 ❌ 失败(flag=false)

```bash
$ curl http://localhost:8000/api/commodity/CU2501.SHF/info
# 预期:真实行情 JSON
# 实际:404 Not Found(因为 include_router 未执行)
```

### 前端浏览器 ❌ 无法访问

```bash
$ open http://localhost:3000/commodity/detail/CU2501.SHF
# 预期:商品详情页(基础信息 + 行情 + K 线)
# 实际:前端 router 无 commodity 路由,Vue 跳转到 404 页
```

---

## 📁 本 Phase 文件清单(实测确认存在)

**新增(7 个)**:
- `tradingagents/dataflows/providers/commodity/__init__.py` ✅
- `tradingagents/dataflows/providers/commodity/base_commodity_provider.py` ✅
- `tradingagents/dataflows/providers/commodity/akshare_futures.py` ✅
- `app/services/commodity/__init__.py` ✅
- `app/services/commodity/unified_commodity_service.py` ✅
- `app/routers/commodity/__init__.py` ✅
- `app/routers/commodity/quotes.py` ✅

**修改(2 个)**:
- `app/main.py` — 增加 commodity 路由条件加载(只读,确认存在)✅
- `scripts/demo_phase0.py` — 扩展为 Phase 0 + Phase 1 演示(待确认是否真的扩展过)❓
- `.env` — **未翻 flag**(实测发现)

**未交付(原计划本应新增,实际未做)**:
- 6 个前端文件(见上文 § 2)

---

## 🚀 如何让本 Phase 真正"可演示"

```bash
# 1. 翻 flag
cd "C:\Users\59608\Desktop\TradingAgent-CN"
sed -i 's/^FEATURE_COMMODITY_ENABLED=false/FEATURE_COMMODITY_ENABLED=true/' .env
sed -i 's/^FEATURE_COMMODITY_DATA=false/FEATURE_COMMODITY_DATA=true/' .env

# 2. 启后端
python -m app --reload
# 日志应输出:✅ 大宗商品数据路由已注册(/api/commodity/*)

# 3. curl 验证(此时才有真实数据)
curl http://localhost:8000/api/commodity/CU2501.SHF/info
curl http://localhost:8000/api/commodity/CU2501.SHF/quotes

# 4. 前端 ❌ 仍无法看到(没有 UI)
# 前端 commodity UI 必须在 Phase 3 一起做
```

---

## 🟡 已知问题 / 限制

1. **延迟**:每次请求实时调 AKShare,首次 1-3 秒。Phase 2 接入 MongoDB + Redis 缓存可降到 <100ms
2. **MongoDB**:未连接,数据没持久化
3. **国际期货 / 现货**:Phase 1 仅支持国内期货
4. **实时性**:用最近日线 close 作为快照,非真正 tick 级实时
5. **前端**:商品 UI 整个未交付(已发现,需在 Phase 3 补齐)

---

## 🔜 下阶段计划(已修正)

Phase 2 重命名为"**数据层完备**(代码层 + 单测)"——本仓库今日已落地,详见 [`phase-2.md`](phase-2.md)。

Phase 3 计划必须包含**前端 commodity UI 补全**,否则后端能力再强用户也看不到:

1. 前端 commodity UI 6 个文件(view / router / api / store)
2. 5 个 analyst 节点 + `CommoditiesTradingAgentsGraph`
3. `app/routers/commodity/analysis.py`(走队列 + SSE)
4. 翻 `FEATURE_COMMODITY_ANALYSIS=true`,浏览器端可点击"分析"按钮跑图
5. 商品详情页 v2:基础信息 + 行情 + K 线 + 分析报告 + 新闻 + 持仓/基差

预计周期: **2 周**(原计划 1 周低估前端工作量)。