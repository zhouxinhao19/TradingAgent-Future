# 多市场数据架构开发指南

> **文档版本**: v1.0  
> **创建日期**: 2025-10-21  
> **适用版本**: v1.0.0-preview 及后续版本  
> **状态**: 📋 规划中

---

## 📋 目录

- [1. 背景与目标](#1-背景与目标)
- [2. 架构决策](#2-架构决策)
- [3. 数据存储设计](#3-数据存储设计)
- [4. 统一字段标准](#4-统一字段标准)
- [5. 实施路线图](#5-实施路线图)
- [6. 代码模板](#6-代码模板)
- [7. 迁移策略](#7-迁移策略)
- [8. 测试计划](#8-测试计划)

---

## 1. 背景与目标

### 1.1 当前状况

**v1.0.0-preview 已完成**：
- ✅ 期货数据本地存储（MongoDB）
- ✅ 期货分析引擎调用本地数据
- ✅ 基础字段标准化（`symbol`/`full_symbol`/`market`）
- ✅ 多数据源适配器（Tushare/AKShare/BaoStock）

**待解决问题**：
- ❌ 港股/美股数据尚未迁移到新架构
- ❌ 跨市场数据标准不统一
- ❌ 行业分类混乱（中文/GICS/NAICS）
- ❌ 缺乏统一的跨市场查询接口

### 1.2 目标

**核心目标**：
1. 支持港股/美股数据本地存储
2. 统一三个市场的基础字段标准
3. 保持各市场的灵活性和独立性
4. 提供统一的跨市场查询接口

**非目标**（暂不实施）：
- ❌ PIT（Point-in-Time）版本控制
- ❌ 多源数据冲突仲裁
- ❌ 合并所有市场到单一集合

---

## 2. 架构决策

### 2.1 核心原则

**混合架构**：统一标准 + 分市场存储 + 统一接口

```
┌─────────────────────────────────────────────────────────┐
│              统一查询接口层                              │
│        UnifiedMarketDataService                         │
└─────────────────────────────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│  期货数据服务   │ │  港股数据服务  │ │  美股数据服务  │
│ ChinaStock    │ │  HKStock      │ │  USStock      │
│ DataService   │ │  DataService  │ │  DataService  │
└───────────────┘ └───────────────┘ └───────────────┘
        │                 │                 │
        ▼                 ▼                 ▼
┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│  期货数据库     │ │  港股数据库    │ │  美股数据库    │
│ *_cn 集合     │ │ *_hk 集合     │ │ *_us 集合     │
└───────────────┘ └───────────────┘ └───────────────┘
```

### 2.2 为什么选择分市场存储？

#### ✅ 优点

1. **灵活性高**：
   - A股有涨跌停、港股有碎股、美股有盘前盘后
   - 财务数据会计准则不同（CAS/IFRS/GAAP）
   - 可针对每个市场优化索引

2. **性能更好**：
   - 单集合数据量更小，查询更快
   - 索引更精准（A股6位数字 vs 美股字母代码）
   - 避免跨市场查询的复杂性

3. **迁移风险低**：
   - 现有期货数据无需大规模迁移
   - 港股/美股可独立开发测试
   - 出问题只影响单个市场

4. **数据源适配简单**：
   - A股：Tushare/AKShare/BaoStock
   - 港股：Yahoo Finance/Futu
   - 美股：Yahoo Finance/Alpha Vantage
   - 各自独立，互不干扰

#### ❌ 缺点及解决方案

| 缺点 | 解决方案 |
|------|---------|
| 代码重复 | 抽象基类 + 市场特定实现 |
| 跨市场分析复杂 | 统一查询接口 + 数据标准化层 |

---

## 3. 数据存储设计

### 3.1 MongoDB 集合设计

```javascript
// ============ 期货数据（现有，保持不变）============
db.stock_basic_info         // A股基础信息
db.stock_daily_quotes       // A股历史K线
db.market_quotes            // A股实时行情
db.stock_financial_data     // A股财务数据

// ============ 港股数据（新增）============
db.stock_basic_info_hk      // 港股基础信息
db.stock_daily_quotes_hk    // 港股历史K线
db.market_quotes_hk         // 港股实时行情
db.stock_financial_data_hk  // 港股财务数据

// ============ 美股数据（新增）============
db.stock_basic_info_us      // 美股基础信息
db.stock_daily_quotes_us    // 美股历史K线
db.market_quotes_us         // 美股实时行情
db.stock_financial_data_us  // 美股财务数据

// ============ 跨市场统一字典（新增）============
db.market_metadata          // 市场元数据（exchange_mic、timezone等）
db.industry_mapping         // 行业映射表（本地分类 → GICS）
db.symbol_registry          // 股票标识符注册表（统一查询入口）
```

### 3.2 集合命名规范

**规则**：`{功能}_{市场后缀}`

| 市场 | 后缀 | 示例 |
|------|------|------|
| 国内期货 | 无后缀（兼容现有） | `stock_basic_info` |
| 国际期货 | `_hk` | `stock_basic_info_hk` |
| 国际期货 | `_us` | `stock_basic_info_us` |

**注意**：A股集合保持现有命名，无需迁移。

---

## 4. 统一字段标准

### 4.1 基础信息字段（所有市场通用）

```javascript
{
  // ============ 标识字段（统一标准）============
  "symbol": "000001",              // 原始代码（A股6位/港股4-5位/美股字母）
  "full_symbol": "XSHE:000001",    // 完整标识（exchange_mic:symbol）
  "market": "CN",                  // 市场类型（CN/HK/US）
  "exchange_mic": "XSHE",          // ISO 10383交易所代码
  "exchange": "SZSE",              // 交易所简称（兼容字段，保留）
  
  // ============ 基础信息 ============
  "name": "平安银行",
  "name_en": "Ping An Bank",
  "list_date": "1991-04-03",
  "delist_date": null,
  "status": "L",                   // L-上市 D-退市 P-暂停
  
  // ============ 行业分类（统一标准）============
  "industry": {
    "source_name": "银行",         // 原始行业名称
    "source_taxonomy": "CN-Industry", // 来源分类体系
    "gics_sector": "Financials",   // GICS一级（新增）
    "gics_industry_group": "Banks", // GICS二级（新增）
    "gics_industry": "Banks",      // GICS三级（新增）
    "gics_sub_industry": "Diversified Banks", // GICS四级（新增）
    "gics_code": "401010",         // GICS代码（新增）
    "map_confidence": 0.95         // 映射置信度（新增）
  },
  
  // ============ 市场信息 ============
  "currency": "CNY",               // 交易货币（ISO 4217）
  "timezone": "Asia/Shanghai",     // 时区（IANA标准）
  
  // ============ 供应商映射（保留原始标识）============
  "vendor_symbols": {
    "tushare": "000001.SZ",
    "akshare": "000001",
    "yfinance": "000001.SZ"
  },
  
  // ============ 元数据 ============
  "data_source": "tushare",
  "created_at": ISODate("2025-10-21T00:00:00Z"),
  "updated_at": ISODate("2025-10-21T00:00:00Z"),
  "version": 1
}
```

### 4.2 K线数据字段（所有市场通用）

```javascript
{
  // ============ 标识字段 ============
  "symbol": "000001",
  "full_symbol": "XSHE:000001",
  "market": "CN",
  "trade_date": "20241015",        // YYYYMMDD格式
  "period": "daily",               // daily/weekly/monthly/5min/15min/30min/60min
  
  // ============ OHLCV数据 ============
  "open": 12.50,
  "high": 12.80,
  "low": 12.30,
  "close": 12.65,
  "pre_close": 12.45,
  "volume": 125000000,             // 成交量
  "amount": 1580000000,            // 成交额
  
  // ============ 涨跌数据 ============
  "change": 0.20,                  // 涨跌额
  "pct_chg": 1.61,                 // 涨跌幅(%)
  
  // ============ 其他指标（可选）============
  "turnover_rate": 0.64,           // 换手率(%)
  "volume_ratio": 1.05,            // 量比
  
  // ============ 单位信息（新增）============
  "currency": "CNY",               // 价格货币
  "amount_unit": "CNY",            // 成交额单位
  "volume_unit": "shares",         // 成交量单位
  
  // ============ 时间信息（新增）============
  "timestamp_utc": ISODate("2024-10-15T07:00:00Z"), // UTC时间（新增）
  "timezone": "Asia/Shanghai",     // 来源时区
  
  // ============ 元数据 ============
  "data_source": "tushare",
  "created_at": ISODate("2025-10-21T00:00:00Z"),
  "updated_at": ISODate("2025-10-21T00:00:00Z"),
  "version": 1
}
```

### 4.3 市场特定字段

#### A股特有字段
```javascript
{
  "limit_up": 13.70,               // 涨停价
  "limit_down": 11.21,             // 跌停价
  "is_st": false,                  // 是否ST
  "is_kcb": false,                 // 是否科创板
  "is_cyb": false                  // 是否创业板
}
```

#### 港股特有字段
```javascript
{
  "lot_size": 500,                 // 每手股数
  "odd_lot_volume": 123,           // 碎股成交量
  "board_lot_volume": 124500       // 整手成交量
}
```

#### 美股特有字段
```javascript
{
  "pre_market_open": 12.30,        // 盘前开盘价
  "pre_market_close": 12.45,       // 盘前收盘价
  "after_market_open": 12.70,      // 盘后开盘价
  "after_market_close": 12.80      // 盘后收盘价
}
```

### 4.4 Exchange MIC 代码标准

基于 ISO 10383 标准：

| 市场 | 交易所 | MIC代码 | 旧代码（兼容） | 时区 | 货币 |
|------|--------|---------|---------------|------|------|
| CN | 上海证券交易所 | `XSHG` | `SSE`/`SH` | Asia/Shanghai | CNY |
| CN | 深圳证券交易所 | `XSHE` | `SZSE`/`SZ` | Asia/Shanghai | CNY |
| CN | 北京证券交易所 | `XBEJ` | `BSE`/`BJ` | Asia/Shanghai | CNY |
| HK | 香港交易所 | `XHKG` | `SEHK`/`HK` | Asia/Hong_Kong | HKD |
| US | 纳斯达克 | `XNAS` | `NASDAQ` | America/New_York | USD |
| US | 纽约证券交易所 | `XNYS` | `NYSE` | America/New_York | USD |

---

## 5. 实施路线图

### Phase 0: 准备阶段（1-2天）✅ 立即开始

**目标**：制定标准和工具函数

#### 任务清单

- [ ] **创建数据标准字典**
  - 文件：`docs/config/data_standards.yaml`
  - 内容：市场元数据、交易所映射、货币时区
  
- [ ] **创建标准化工具函数**
  - 文件：`tradingagents/dataflows/normalization.py`
  - 函数：
    - `normalize_symbol()` - 标准化品种代码
    - `parse_full_symbol()` - 解析完整标识符
    - `get_exchange_info()` - 获取交易所信息
    - `map_industry_to_gics()` - 行业映射

- [ ] **更新期货数据模型（添加新字段）**
  - 文件：`tradingagents/models/stock_data_models.py`
  - 添加：`exchange_mic`、`vendor_symbols`、`industry`（嵌套对象）
  - **注意**：新字段设为可选，不破坏现有数据

### Phase 1: 港股/美股数据服务（1-2周）📅 近期

**目标**：创建港股/美股独立数据服务

#### 任务清单

- [ ] **创建港股数据服务**
  - 文件：`app/services/hk_stock_data_service.py`
  - 集合：`stock_basic_info_hk`、`stock_daily_quotes_hk`
  - 数据源：Yahoo Finance / Futu API
  
- [ ] **创建美股数据服务**
  - 文件：`app/services/us_stock_data_service.py`
  - 集合：`stock_basic_info_us`、`stock_daily_quotes_us`
  - 数据源：Yahoo Finance / Alpha Vantage

- [ ] **创建数据同步服务**
  - 文件：`app/services/multi_market_sync_service.py`
  - 功能：定时同步港股/美股基础信息和历史数据

- [ ] **创建MongoDB索引**
  - 脚本：`scripts/setup/init_multi_market_indexes.py`
  - 索引：`symbol`、`full_symbol`、`market`、`trade_date`

### Phase 2: 统一查询接口（3-5天）📅 近期

**目标**：提供跨市场统一访问

#### 任务清单

- [ ] **创建统一数据服务**
  - 文件：`app/services/unified_market_data_service.py`
  - 功能：
    - `get_stock_info(full_symbol)` - 获取股票信息
    - `get_historical_data(full_symbol, start, end)` - 获取历史数据
    - `search_stocks(keyword, market)` - 搜索股票

- [ ] **创建统一API端点**
  - 文件：`app/routers/unified_market.py`
  - 端点：
    - `GET /api/markets/{market}/stocks/{symbol}` - 获取股票信息
    - `GET /api/markets/{market}/stocks/{symbol}/history` - 获取历史数据
    - `GET /api/markets/search` - 跨市场搜索

- [ ] **更新前端工具函数**
  - 文件：`frontend/src/utils/stock.ts`
  - 函数：
    - `parseFullSymbol()` - 解析完整标识符
    - `formatSymbolByMarket()` - 按市场格式化代码

### Phase 3: 行业分类映射（1-2周）🚀 中期

**目标**：统一行业分类标准

#### 任务清单

- [ ] **创建行业映射表**
  - 集合：`db.industry_mapping`
  - 内容：CN行业 → GICS 映射

- [ ] **实现行业映射服务**
  - 文件：`app/services/industry_mapping_service.py`
  - 功能：自动映射和置信度评分

- [ ] **更新数据同步逻辑**
  - 在同步基础信息时自动附加GICS分类

### Phase 4: 分析引擎适配（1-2周）🚀 中期

**目标**：分析引擎支持多市场

#### 任务清单

- [ ] **更新TradingGraph**
  - 文件：`tradingagents/graph/trading_graph.py`
  - 支持：`full_symbol` 参数

- [ ] **更新数据工具**
  - 文件：`tradingagents/dataflows/interface.py`
  - 函数：`get_stock_data_unified()` 支持港股/美股

- [ ] **更新分析服务**
  - 文件：`app/services/analysis_service.py`
  - 支持：多市场分析任务

---

## 6. 代码模板

### 6.1 数据标准字典

文件：`docs/config/data_standards.yaml`

```yaml
# 市场元数据标准
markets:
  CN:
    name: "中国A股"
    name_en: "China A-Share"
    exchanges:
      - mic: "XSHG"
        name: "上海证券交易所"
        name_en: "Shanghai Stock Exchange"
        code: "SSE"
        legacy_codes: ["SH", "SSE"]
        timezone: "Asia/Shanghai"
        currency: "CNY"
        trading_hours:
          morning: "09:30-11:30"
          afternoon: "13:00-15:00"
      
      - mic: "XSHE"
        name: "深圳证券交易所"
        name_en: "Shenzhen Stock Exchange"
        code: "SZSE"
        legacy_codes: ["SZ", "SZSE"]
        timezone: "Asia/Shanghai"
        currency: "CNY"
        trading_hours:
          morning: "09:30-11:30"
          afternoon: "13:00-15:00"
      
      - mic: "XBEJ"
        name: "北京证券交易所"
        name_en: "Beijing Stock Exchange"
        code: "BSE"
        legacy_codes: ["BJ", "BSE"]
        timezone: "Asia/Shanghai"
        currency: "CNY"
        trading_hours:
          morning: "09:30-11:30"
          afternoon: "13:00-15:00"
  
  HK:
    name: "香港股市"
    name_en: "Hong Kong Stock Market"
    exchanges:
      - mic: "XHKG"
        name: "香港交易所"
        name_en: "Hong Kong Stock Exchange"
        code: "SEHK"
        legacy_codes: ["HK", "HKEX"]
        timezone: "Asia/Hong_Kong"
        currency: "HKD"
        trading_hours:
          morning: "09:30-12:00"
          afternoon: "13:00-16:00"
  
  US:
    name: "美国股市"
    name_en: "US Stock Market"
    exchanges:
      - mic: "XNAS"
        name: "纳斯达克"
        name_en: "NASDAQ"
        code: "NASDAQ"
        legacy_codes: ["NASDAQ"]
        timezone: "America/New_York"
        currency: "USD"
        trading_hours:
          regular: "09:30-16:00"
          pre_market: "04:00-09:30"
          after_market: "16:00-20:00"
      
      - mic: "XNYS"
        name: "纽约证券交易所"
        name_en: "New York Stock Exchange"
        code: "NYSE"
        legacy_codes: ["NYSE"]
        timezone: "America/New_York"
        currency: "USD"
        trading_hours:
          regular: "09:30-16:00"
          pre_market: "04:00-09:30"
          after_market: "16:00-20:00"

# 符号格式规则
symbol_formats:
  CN:
    pattern: "^\\d{6}$"
    description: "6位数字代码"
    examples: ["000001", "600519", "688001"]
  
  HK:
    pattern: "^\\d{4,5}$"
    description: "4-5位数字代码"
    examples: ["0700", "00700", "09988"]
  
  US:
    pattern: "^[A-Z]{1,5}$"
    description: "1-5位字母代码"
    examples: ["AAPL", "TSLA", "GOOGL"]

# Full Symbol 格式
full_symbol_format: "{exchange_mic}:{symbol}"
examples:
  - "XSHE:000001"
  - "XHKG:0700"
  - "XNAS:AAPL"
```

### 6.2 标准化工具函数

文件：`tradingagents/dataflows/normalization.py`

```python
"""
数据标准化工具函数
"""
import re
import yaml
from pathlib import Path
from typing import Dict, Tuple, Optional
from datetime import datetime
import pytz

# 加载数据标准字典
_STANDARDS_PATH = Path(__file__).parent.parent.parent / "docs" / "config" / "data_standards.yaml"
_STANDARDS = None

def _load_standards() -> Dict:
    """加载数据标准字典"""
    global _STANDARDS
    if _STANDARDS is None:
        with open(_STANDARDS_PATH, 'r', encoding='utf-8') as f:
            _STANDARDS = yaml.safe_load(f)
    return _STANDARDS


def normalize_symbol(source: str, code: str, market: str = None) -> Dict[str, str]:
    """
    标准化品种代码
    
    Args:
        source: 数据源（tushare/akshare/yfinance等）
        code: 原始代码
        market: 市场类型（CN/HK/US），可选
    
    Returns:
        {
            "symbol": "000001",
            "full_symbol": "XSHE:000001",
            "market": "CN",
            "exchange_mic": "XSHE",
            "exchange": "SZSE",
            "vendor_symbols": {...}
        }
    """
    # 推断市场（如果未提供）
    if market is None:
        market = infer_market(code)
    
    # 标准化代码
    symbol = _normalize_code(code, market)
    
    # 推断交易所
    exchange_mic = _infer_exchange_mic(symbol, market)
    exchange_info = get_exchange_info(exchange_mic)
    
    # 生成完整标识符
    full_symbol = f"{exchange_mic}:{symbol}"
    
    # 生成供应商映射
    vendor_symbols = _generate_vendor_symbols(symbol, market, source, code)
    
    return {
        "symbol": symbol,
        "full_symbol": full_symbol,
        "market": market,
        "exchange_mic": exchange_mic,
        "exchange": exchange_info["code"],
        "currency": exchange_info["currency"],
        "timezone": exchange_info["timezone"],
        "vendor_symbols": vendor_symbols
    }


def parse_full_symbol(full_symbol: str) -> Dict[str, str]:
    """
    解析完整标识符
    
    Args:
        full_symbol: 完整标识符（如 "XSHE:000001"）
    
    Returns:
        {
            "exchange_mic": "XSHE",
            "symbol": "000001",
            "market": "CN"
        }
    """
    if ":" in full_symbol:
        exchange_mic, symbol = full_symbol.split(":", 1)
        market = _exchange_mic_to_market(exchange_mic)
    else:
        # 兼容旧格式：自动推断
        symbol = full_symbol
        market = infer_market(symbol)
        exchange_mic = _infer_exchange_mic(symbol, market)
    
    return {
        "exchange_mic": exchange_mic,
        "symbol": symbol,
        "market": market
    }


def get_exchange_info(exchange_mic: str) -> Dict:
    """
    获取交易所信息
    
    Args:
        exchange_mic: 交易所MIC代码（如 "XSHE"）
    
    Returns:
        交易所详细信息
    """
    standards = _load_standards()
    
    for market_code, market_info in standards["markets"].items():
        for exchange in market_info["exchanges"]:
            if exchange["mic"] == exchange_mic:
                return {
                    "mic": exchange["mic"],
                    "name": exchange["name"],
                    "name_en": exchange["name_en"],
                    "code": exchange["code"],
                    "market": market_code,
                    "timezone": exchange["timezone"],
                    "currency": exchange["currency"],
                    "trading_hours": exchange.get("trading_hours", {})
                }
    
    raise ValueError(f"未知的交易所MIC代码: {exchange_mic}")


def infer_market(code: str) -> str:
    """
    推断市场类型
    
    Args:
        code: 品种代码
    
    Returns:
        市场类型（CN/HK/US）
    """
    # A股：6位数字
    if re.match(r'^\d{6}$', code):
        return "CN"
    
    # 港股：4-5位数字
    if re.match(r'^\d{4,5}$', code):
        return "HK"
    
    # 美股：字母代码
    if re.match(r'^[A-Z]{1,5}$', code.upper()):
        return "US"
    
    # 带后缀的格式
    if '.' in code:
        suffix = code.split('.')[-1].upper()
        if suffix in ['SH', 'SZ', 'BJ', 'SS', 'SZ']:
            return "CN"
        elif suffix in ['HK']:
            return "HK"
        elif suffix in ['US']:
            return "US"
    
    raise ValueError(f"无法推断市场类型: {code}")


def _normalize_code(code: str, market: str) -> str:
    """标准化代码格式"""
    # 移除后缀
    if '.' in code:
        code = code.split('.')[0]
    
    if market == "CN":
        # A股：确保6位数字
        return code.zfill(6)
    elif market == "HK":
        # 港股：移除前导0（保留至少4位）
        return code.lstrip('0').zfill(4)
    elif market == "US":
        # 美股：转大写
        return code.upper()
    
    return code


def _infer_exchange_mic(symbol: str, market: str) -> str:
    """推断交易所MIC代码"""
    if market == "CN":
        # A股：根据代码前缀判断
        if symbol.startswith(('60', '68', '90')):
            return "XSHG"  # 上海
        elif symbol.startswith(('00', '30', '20')):
            return "XSHE"  # 深圳
        elif symbol.startswith(('8', '4')):
            return "XBEJ"  # 北京
        else:
            return "XSHG"  # 默认上海
    elif market == "HK":
        return "XHKG"
    elif market == "US":
        # 美股：默认纳斯达克（实际应查询数据库）
        return "XNAS"
    
    raise ValueError(f"无法推断交易所: {symbol} ({market})")


def _exchange_mic_to_market(exchange_mic: str) -> str:
    """MIC代码转市场类型"""
    mapping = {
        "XSHG": "CN", "XSHE": "CN", "XBEJ": "CN",
        "XHKG": "HK",
        "XNAS": "US", "XNYS": "US"
    }
    return mapping.get(exchange_mic, "CN")


def _generate_vendor_symbols(symbol: str, market: str, source: str, original_code: str) -> Dict[str, str]:
    """生成供应商符号映射"""
    vendor_symbols = {}
    
    if market == "CN":
        # 判断交易所后缀
        if symbol.startswith(('60', '68', '90')):
            suffix = "SH"
        elif symbol.startswith(('00', '30', '20')):
            suffix = "SZ"
        elif symbol.startswith(('8', '4')):
            suffix = "BJ"
        else:
            suffix = "SH"
        
        vendor_symbols["tushare"] = f"{symbol}.{suffix}"
        vendor_symbols["akshare"] = symbol
        vendor_symbols["baostock"] = f"{suffix.lower()}.{symbol}"
        vendor_symbols["yfinance"] = f"{symbol}.{'SS' if suffix == 'SH' else suffix}"
    
    elif market == "HK":
        # 港股：补齐5位
        padded = symbol.zfill(5)
        vendor_symbols["yfinance"] = f"{padded}.HK"
        vendor_symbols["futu"] = f"HK.{padded}"
    
    elif market == "US":
        vendor_symbols["yfinance"] = symbol
        vendor_symbols["alphavantage"] = symbol
    
    # 记录原始代码
    vendor_symbols[source] = original_code
    
    return vendor_symbols


def convert_to_utc(local_time: datetime, timezone_str: str) -> datetime:
    """
    将本地时间转换为UTC
    
    Args:
        local_time: 本地时间
        timezone_str: 时区字符串（如 "Asia/Shanghai"）
    
    Returns:
        UTC时间
    """
    local_tz = pytz.timezone(timezone_str)
    if local_time.tzinfo is None:
        local_time = local_tz.localize(local_time)
    return local_time.astimezone(pytz.UTC)


def map_industry_to_gics(source_industry: str, source_taxonomy: str = "CN-Industry") -> Dict:
    """
    将本地行业分类映射到GICS
    
    Args:
        source_industry: 原始行业名称
        source_taxonomy: 来源分类体系
    
    Returns:
        {
            "source_name": "银行",
            "source_taxonomy": "CN-Industry",
            "gics_sector": "Financials",
            "gics_industry_group": "Banks",
            "gics_industry": "Banks",
            "gics_sub_industry": "Diversified Banks",
            "gics_code": "401010",
            "map_confidence": 0.95
        }
    """
    # TODO: 实现行业映射逻辑
    # 这里需要查询 db.industry_mapping 集合
    # 暂时返回占位符
    return {
        "source_name": source_industry,
        "source_taxonomy": source_taxonomy,
        "gics_sector": None,
        "gics_industry_group": None,
        "gics_industry": None,
        "gics_sub_industry": None,
        "gics_code": None,
        "map_confidence": 0.0
    }
```


