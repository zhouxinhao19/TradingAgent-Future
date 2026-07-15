# Phase 1 - 数据闭环(行情)完成报告

> 详见 plan: [`docs/plans/stock-to-commodity.md`](../plans/stock-to-commodity.md) §1.4

**完成日期**: 2026-07-13
**状态**: ✅ 已完成,可演示
**Feature Flag**: `FEATURE_COMMODITY_ENABLED=true` + `FEATURE_COMMODITY_DATA=true`

---

## ✅ 已完成项

### 1. 数据源层
- ✅ `tradingagents/dataflows/providers/commodity/base_commodity_provider.py` — 抽象基类(镜像 `BaseStockDataProvider`)
- ✅ `tradingagents/dataflows/providers/commodity/akshare_futures.py` — AKShare 国内期货主力数据源(支持 `info / quotes / historical`)

### 2. 服务层
- ✅ `app/services/commodity/unified_commodity_service.py` — 统一服务,懒加载 provider,Phase 1 实时调 AKShare

### 3. API 路由
- ✅ `app/routers/commodity/quotes.py` — 5 个端点
  - `GET /api/commodity/categories` — 商品品类
  - `GET /api/commodity/exchanges` — 交易所
  - `GET /api/commodity/{full_symbol}/info` — 基础信息
  - `GET /api/commodity/{full_symbol}/quotes` — 实时行情
  - `GET /api/commodity/{full_symbol}/historical` — 历史 K 线
- ✅ `app/main.py` 增加 `if settings.FEATURE_COMMODITY_ENABLED and FEATURE_COMMODITY_DATA: include_router` 条件加载

### 4. Feature Flag
- ✅ 翻 `FEATURE_COMMODITY_ENABLED=true` + `FEATURE_COMMODITY_DATA=true`(.env)
- ✅ `app/main.py` 启动日志根据 flag 输出"已注册"/"未启用"

---

## 🔍 验证结果(本地真实数据)

| 端点 | 测试标的 | 真实数据示例 | 状态 |
|---|---|---|---|
| `/api/commodity/categories` | - | 6 个品类(贵金属/有色/能源/化工/农产品/金融) | ✅ |
| `/api/commodity/exchanges` | - | 5 个交易所(SHF/DCE/CZC/INE/GFEX) | ✅ |
| `/api/commodity/CU2501.SHF/info` | 沪铜 2501 | 5 吨/手, CNY, metal | ✅ |
| `/api/commodity/AU2506.SHF/quotes` | 黄金 2506 | 791.0 元/克,结算价 794.96,持仓 8796 | ✅ |
| `/api/commodity/SR2501.CZC/historical` | 白糖 2501 | 2024-12 数据完整 OHLCV + 持仓量 + 结算价 | ✅ |

---

## 📁 本 Phase 新增/修改文件清单

**新增(7 个)**:
- `tradingagents/dataflows/providers/commodity/__init__.py`
- `tradingagents/dataflows/providers/commodity/base_commodity_provider.py`
- `tradingagents/dataflows/providers/commodity/akshare_futures.py`
- `app/services/commodity/__init__.py`
- `app/services/commodity/unified_commodity_service.py`
- `app/routers/commodity/__init__.py`
- `app/routers/commodity/quotes.py`

**修改(2 个)**:
- `app/main.py` — 增加 commodity 路由条件加载
- `scripts/demo_phase0.py` — 扩展为 Phase 0 + Phase 1 演示
- `.env` — 翻 2 个 flag 为 true(本地)

---

## 🚀 一键演示

```bash
# 1. 翻 flag
cd "C:\Users\59608\Desktop\TradingAgent-CN"
sed -i 's/^FEATURE_COMMODITY_ENABLED=false/FEATURE_COMMODITY_ENABLED=true/' .env
sed -i 's/^FEATURE_COMMODITY_DATA=false/FEATURE_COMMODITY_DATA=true/' .env

# 2. 启动 demo
PYTHONIOENCODING=utf-8 python scripts/demo_phase0.py

# 3. 浏览器/curl 验证
curl http://localhost:8765/api/config/features
curl http://localhost:8765/api/commodity/categories
curl http://localhost:8765/api/commodity/CU2501.SHF/info
curl http://localhost:8765/api/commodity/AU2506.SHF/quotes
curl 'http://localhost:8765/api/commodity/SR2501.CZC/historical?start_date=2024-12-01'
```

---

## 🟡 已知问题 / 限制

1. **延迟**:每次请求实时调 AKShare,首次请求 1-3 秒。Phase 2 接入 MongoDB + Redis 缓存可降到 <100ms
2. **MongoDB**:未连接(本地未启动 MongoDB),数据没持久化;Phase 2 接入 `commodity_basic_info` / `commodity_quotes` / `commodity_daily_quotes` 集合
3. **国际期货 / 现货**:Phase 1 仅支持国内期货,Phase 2+ 接入 yfinance_futures(国际) + SGE(现货)
4. **实时性**:用最近日线 close 作为快照,非真正 tick 级实时;Phase 2 接入 `futures_zh_spot`

---

## 🔜 下阶段计划: Phase 2 - 技术分析闭环

1. 接入 MongoDB 缓存层(避免每次实时调 AKShare)
2. 创建 `tradingagents/agents/analysts/commodity/technical_analyst.py`(复用 market_analyst 工具)
3. 创建 `tradingagents/graph/commodity_trading_graph.py`(`CommodityTradingAgentsGraph` 子类)
4. 创建 `app/routers/commodity/analysis.py` + `app/services/commodity/analysis_service.py`
5. 翻 `FEATURE_COMMODITY_ANALYSIS=true`,提交 `CU2501.SHF` + 日期 → 跑图 → 返回技术分析报告
6. 前端 `views/Commodity/Analysis/Single.vue`(可选)

预计周期: 2 周。
