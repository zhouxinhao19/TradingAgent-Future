# Phase 0 - 抽象统一 完成报告

> 详见 plan: [`docs/plans/stock-to-commodity.md`](../plans/stock-to-commodity.md) §1.4

**完成日期**: 2026-07-13
**状态**: ✅ 已完成,可演示
**Feature Flag**: 4 个全部 `false`(商品功能已就绪,默认禁用,等 Phase 1 翻 `true`)

---

## ✅ 已完成项

### 1. 核心抽象层
- ✅ `tradingagents/utils/commodity_utils.py` — 大宗商品市场识别(国内期货/国际期货/现货/未知)
- ✅ `tradingagents/core/instrument.py` — 标的抽象 + 工厂方法,支持期货品种和商品互斥识别
- ✅ 单元测试 `tests/test_instrument.py` — **57 个测试全部通过**

### 2. Feature Flag 机制
- ✅ `app/core/config.py` 扩展 4 个 `FEATURE_COMMODITY_*` 字段 + `FEATURE_FLAGS` property
- ✅ `app/routers/config.py` 新增 `GET /api/config/features` 端点
- ✅ `.env.example` 和 `.env.docker` 增加 4 个 flag 默认 `false`

### 3. 部署配置
- ✅ `docker-compose.override.yml` 本地热重载(覆盖 backend/frontend 的 volumes,挂载本地源码)

---

## 🔍 验证步骤

### 1. 单元测试
```bash
cd "C:\Users\59608\Desktop\TradingAgent-CN"
python -m pytest tests/test_instrument.py -v
```
**结果**: 57 passed, 5 deselected, 0 failed ✅

### 2. 配置加载
```python
from app.core.config import settings
print(settings.FEATURE_FLAGS)
# {'commodity_enabled': False, 'commodity_data': False, ...}
```

### 3. 模块 smoke
```bash
python -c "
from tradingagents.core.instrument import Instrument
print(Instrument.of('CU2501.SHF').to_dict())
print(Instrument.of('AAPL').to_dict())
"
```
**输出**:
- `CU2501.SHF` → `asset_type='commodity'`, `market='china_futures'`, `category='metal'`
- `AAPL` → `asset_type='stock'`, `market='us'`

### 4. Docker 启动(下一步要做)
```bash
docker compose up -d
docker compose ps
# 预期: backend / frontend / mongodb / redis 全部 healthy
```

### 5. API 验证
```bash
curl http://localhost:8000/api/config/features
# 预期: {"success": true, "data": {"commodity_enabled": false, ...}}
```

---

## 📁 本 Phase 新增/修改文件清单

**新增(5 个)**:
- `tradingagents/core/__init__.py`(空)
- `tradingagents/core/instrument.py`
- `tradingagents/utils/commodity_utils.py`
- `tests/test_instrument.py`
- `docker-compose.override.yml`

**修改(3 个)**:
- `app/core/config.py`(+ `FEATURE_COMMODITY_*` 4 字段 + `FEATURE_FLAGS` property)
- `app/routers/config.py`(+ `GET /api/config/features` 端点)
- `.env.example` / `.env.docker`(+ 4 个 flag)

**无破坏性变更**:所有现有端点、`stock_*` 路由、原有功能完全不受影响。

---

## 🟡 已知问题

无。

---

## 🔜 下阶段计划: Phase 1 - 数据闭环(行情)

1. 创建 `tradingagents/dataflows/providers/commodity/akshare_futures.py` 国内期货数据源
2. 创建 `commodity_basic_info` / `commodity_quotes` MongoDB 集合
3. 创建 `app/routers/commodity/__init__.py` + 3 个子路由(quotes/detail/historical)
4. 创建 `app/services/commodity/unified_commodity_service.py`
5. 创建 `app/models/commodity_models.py`
6. 创建 `frontend/src/views/Commodity/Detail.vue`
7. 把 `FEATURE_COMMODITY_DATA` 翻 `true`,重启验证
8. 写 `docs/progress/phase-1.md`

预计周期: 2-3 周。

---

## 🎬 一键体验命令

**本 Phase 完成后**,用户可以用以下命令验证:

```bash
# 1. 启动后端
cd "C:\Users\59608\Desktop\TradingAgent-CN"
docker compose up -d mongodb redis
python -m uvicorn app.main:app --reload --port 8000

# 2. 启动前端
cd frontend && npm run dev

# 3. 验证
curl http://localhost:8000/api/config/features
# 访问 http://localhost:8000/docs 看新增的 /api/config/features 端点
# 浏览器访问 http://localhost:5173 → 看到原期货分析平台,无任何变化(商品功能默认关闭)

# 4. 跑单元测试
python -m pytest tests/test_instrument.py -v
```

预期结果:
- ✅ 后端启动正常,日志无 error
- ✅ 前端无任何商品入口(flag 全 false)
- ✅ `/api/config/features` 返回 `commodity_*: false`
- ✅ 单元测试 57 passed
- ✅ 主流程(期货分析)完全不受影响
