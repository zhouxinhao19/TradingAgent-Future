# 成交额单位修复文档

## 📋 问题描述

### 现象
在期货品种详情页面，成交额显示错误：
- **实际值**: 90.92亿元
- **显示值**: 909.18万元
- **错误倍数**: 10,000倍（差了4个数量级）

### 影响范围
- 期货品种详情页面的成交额显示
- 所有使用 Tushare 数据源的期货品种
- `market_quotes` 集合中的成交额数据
- `stock_daily_quotes` 集合中的成交额数据

---

## 🔍 根本原因

### Tushare API 单位说明

根据 Tushare 官方文档和实际测试：

| 接口 | 字段 | 单位 | 说明 |
|------|------|------|------|
| `daily()` | `amount` | **千元** | 日线数据的成交额 |
| `weekly()` | `amount` | **千元** | 周线数据的成交额 |
| `monthly()` | `amount` | **千元** | 月线数据的成交额 |

### 数据流程

```
Tushare API (千元)
    ↓
TushareProvider.get_historical_data()
    ↓ (未转换)
HistoricalDataService._standardize_record()
    ↓ (未转换)
stock_daily_quotes 集合 (千元)
    ↓
QuotesIngestionService._backfill_from_historical()
    ↓ (未转换)
market_quotes 集合 (千元)
    ↓
前端 fmtAmount() (按元处理)
    ↓
显示错误：909.18万 (应该是 90.92亿)
```

### 问题代码

#### 1. `app/services/historical_data_service.py` (第 223 行)

```python
# ❌ 错误：直接存储，未转换单位
doc.update({
    "amount": self._safe_float(row.get('amount') or row.get('turnover'))
})
```

#### 2. `tradingagents/dataflows/providers/china/tushare.py` (第 1177 行)

```python
# ❌ 错误：直接返回，未转换单位
"amount": self._convert_to_float(raw_data.get('amount')),
```

---

## ✅ 修复方案

### 修复原则

**在数据入库时统一转换为元**，确保数据库中存储的单位一致。

### 修复位置

#### 1. `app/services/historical_data_service.py`

**修改前**:
```python
# OHLCV数据
doc.update({
    "open": self._safe_float(row.get('open')),
    "high": self._safe_float(row.get('high')),
    "low": self._safe_float(row.get('low')),
    "close": self._safe_float(row.get('close')),
    "pre_close": self._safe_float(row.get('pre_close') or row.get('preclose')),
    "volume": self._safe_float(row.get('volume') or row.get('vol')),
    "amount": self._safe_float(row.get('amount') or row.get('turnover'))
})
```

**修改后**:
```python
# OHLCV数据
# 🔥 成交额单位转换：Tushare 返回的是千元，需要转换为元
amount_value = self._safe_float(row.get('amount') or row.get('turnover'))
if amount_value is not None and data_source == "tushare":
    amount_value = amount_value * 1000  # 千元 -> 元
    logger.debug(f"📊 [单位转换] Tushare成交额: {amount_value/1000:.2f}千元 -> {amount_value:.2f}元")

doc.update({
    "open": self._safe_float(row.get('open')),
    "high": self._safe_float(row.get('high')),
    "low": self._safe_float(row.get('low')),
    "close": self._safe_float(row.get('close')),
    "pre_close": self._safe_float(row.get('pre_close') or row.get('preclose')),
    "volume": self._safe_float(row.get('volume') or row.get('vol')),
    "amount": amount_value
})
```

#### 2. `tradingagents/dataflows/providers/china/tushare.py`

**修改前**:
```python
# 成交数据
"volume": self._convert_to_float(raw_data.get('vol')),
"amount": self._convert_to_float(raw_data.get('amount')),
```

**修改后**:
```python
# 成交数据
# 🔥 成交额单位转换：Tushare daily 接口返回的是千元，需要转换为元
"volume": self._convert_to_float(raw_data.get('vol')),
"amount": self._convert_to_float(raw_data.get('amount')) * 1000 if raw_data.get('amount') else None,
```

---

## 🧪 测试方法

### 1. 运行测试脚本

```bash
python test_amount_fix.py
```

**预期输出**:
```
================================================================================
测试成交额单位修复
================================================================================

1️⃣ 测试 Tushare Provider 标准化
   品种代码: 300750

2️⃣ 获取历史数据
   日期范围: 2025-10-30 ~ 2025-11-04
   ✅ 获取到 5 条记录

3️⃣ 最新数据（已标准化）
   日期: 2025-11-04
   收盘价: 350.50
   成交量: 25000000
   成交额(元): 9,091,800,000
   成交额(亿元): 90.92
   成交额(万元): 909180.00

4️⃣ 检查数据库 stock_daily_quotes 集合
   ✅ 找到数据库记录
   交易日期: 2025-11-04
   收盘价: 350.50
   成交额(元): 9,091,800,000
   成交额(亿元): 90.92
   成交额(万元): 909180.00

5️⃣ 检查数据库 market_quotes 集合
   ✅ 找到行情记录
   交易日期: 2025-11-04
   收盘价: 350.50
   成交额(元): 9,091,800,000
   成交额(亿元): 90.92
   成交额(万元): 909180.00

================================================================================
✅ 测试完成
================================================================================

💡 验证标准:
   - 如果成交额显示为 90.92亿 左右，说明修复成功 ✅
   - 如果成交额显示为 909.18万 或 0.0091亿，说明仍有问题 ❌
================================================================================
```

### 2. 重新同步历史数据

修复代码后，需要重新同步历史数据以更新数据库中的成交额：

```bash
# 方法1：使用 Tushare 同步服务（推荐）
python -m app.worker.tushare_sync_service

# 方法2：使用 CLI 工具
python cli/tushare_init.py --full --historical-days 30
```

### 3. 验证前端显示

1. 打开期货品种详情页面：`http://localhost:8000/stocks/300750`
2. 查看成交额字段
3. **预期显示**: `90.92亿` ✅
4. **错误显示**: `909.18万` ❌

---

## 📊 影响分析

### 修复前后对比

| 项目 | 修复前 | 修复后 |
|------|--------|--------|
| 数据库存储单位 | 千元 | 元 |
| 前端显示 | 909.18万 | 90.92亿 |
| 数据准确性 | ❌ 错误 | ✅ 正确 |

### 数据一致性

修复后，所有数据源的成交额单位统一为**元**：

| 数据源 | 原始单位 | 转换后单位 | 转换系数 | 官方文档 |
|--------|---------|-----------|---------|---------|
| Tushare | **千元** | 元 | × 1000 | [Tushare日线行情](https://tushare.pro/document/2?doc_id=27) |
| AKShare | 元 | 元 | × 1 | [AKShare期货数据](https://akshare.akfamily.xyz/data/stock/stock.html) |
| BaoStock | 元 | 元 | × 1 | [BaoStock API文档](http://baostock.com/baostock/index.php/Python_API%E6%96%87%E6%A1%A3) |

**官方文档说明**：
- **Tushare**: `daily()` 接口的 `amount` 字段单位是**千元**
- **AKShare**: `stock_zh_a_spot_em()` 和 `stock_zh_a_hist()` 的成交额单位是**元**
- **BaoStock**: `query_history_k_data_plus()` 的 `amount` 字段单位是**人民币元**

---

## 🔄 升级指引

### 1. 更新代码

```bash
git pull origin v1.0.0-preview
```

### 2. 重新同步数据

**选项 A：增量同步（推荐）**
```bash
# 只同步最近30天的数据
python cli/tushare_init.py --full --historical-days 30
```

**选项 B：全量同步**
```bash
# 同步所有历史数据（耗时较长）
python cli/tushare_init.py --full --historical-days 3650
```

### 3. 重启服务

```bash
# 重启 Web 服务
python run.py
```

### 4. 验证修复

访问期货品种详情页面，检查成交额显示是否正确。

---

## 📝 相关文件

### 修改文件
- `app/services/historical_data_service.py` (第 215-230 行)
- `tradingagents/dataflows/providers/china/tushare.py` (第 1175-1178 行)

### 测试文件
- `test_amount_fix.py` (新增)

### 文档文件
- `docs/fixes/amount-unit-fix.md` (本文档)

---

## 🎯 总结

### 问题
- Tushare API 返回的成交额单位是**千元**
- 代码未进行单位转换，直接存储到数据库
- 前端按**元**处理，导致显示错误（差10,000倍）

### 修复
- 在数据入库时，将 Tushare 的成交额从**千元**转换为**元**
- 确保数据库中所有数据源的成交额单位统一为**元**
- 前端无需修改，按**元**处理即可正确显示

### 效果
- ✅ 成交额显示正确：90.92亿（而非 909.18万）
- ✅ 数据单位统一：所有数据源均为元
- ✅ 前端无需修改：保持现有逻辑

---

## 📚 参考资料

- [Tushare 日线行情接口文档](https://tushare.pro/document/2?doc_id=27)
- [AKShare 期货数据文档](https://akshare.akfamily.xyz/data/stock/stock.html)
- [MongoDB 数据库集合对比文档](../architecture/database/MONGODB_COLLECTIONS_COMPARISON.md)

