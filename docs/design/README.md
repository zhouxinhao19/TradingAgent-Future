# TradingAgents 设计文档目录

本目录包含 TradingAgents 项目的核心设计文档，涵盖系统架构、数据模型、API规范等重要设计内容。

## 📋 文档索引

### 🏗️ 系统架构设计

| 文档 | 描述 | 状态 |
|------|------|------|
| [stock_analysis_system_design.md](stock_analysis_system_design.md) | 股票分析系统整体架构设计 | ✅ 完成 |
| [api_specification.md](api_specification.md) | API接口规范和设计 | ✅ 完成 |
| [configuration_management.md](configuration_management.md) | 配置管理系统设计 | ✅ 完成 |
| [timezone-strategy.md](timezone-strategy.md) | 时区处理策略设计 | ✅ 完成 |

### 📊 数据模型设计

| 文档 | 描述 | 状态 |
|------|------|------|
| [stock_data_model_design.md](stock_data_model_design.md) | **股票数据模型设计方案** | ✅ 最新 |
| [stock_data_methods_analysis.md](stock_data_methods_analysis.md) | 股票数据获取方法整理分析 | ✅ 完成 |
| [stock_data_quick_reference.md](stock_data_quick_reference.md) | 股票数据方法快速参考手册 | ✅ 完成 |

### 📚 版本化设计

| 目录 | 描述 |
|------|------|
| [v0.1.16/](v0.1.16/) | v0.1.16 版本的设计文档 |

## 🎯 重点设计文档

### 1. 股票数据模型设计 (最新)

**文档**: [stock_data_model_design.md](stock_data_model_design.md)

**核心内容**:
- 📊 **8个核心数据表设计**: 基础信息、历史行情、实时数据、财务数据、新闻、技术指标等
- 🌍 **多市场支持**: CN(A股)/HK(港股)/US(美股) 统一架构
- 🚀 **技术指标扩展**: 分类扩展机制，支持无限扩展新指标
- 💾 **索引优化**: 针对查询性能优化的复合索引设计
- 🔧 **数据标准化**: 统一的数据格式和字段命名规范

**设计亮点**:
```javascript
// 市场区分设计
"market_info": {
  "market": "CN",               // 市场标识
  "exchange": "SZSE",           // 交易所
  "currency": "CNY",            // 货币
  "timezone": "Asia/Shanghai"   // 时区
}

// 技术指标分类扩展
"indicators": {
  "trend": {...},      // 趋势指标
  "oscillator": {...}, // 震荡指标  
  "channel": {...},    // 通道指标
  "volume": {...},     // 成交量指标
  "custom": {...}      // 自定义指标
}
```

### 2. 股票数据方法分析

**文档**: [stock_data_methods_analysis.md](stock_data_methods_analysis.md)

**核心内容**:
- 🏗️ **5层架构分析**: 用户接口层 → 统一接口层 → 优化提供器层 → 数据源适配器层 → 缓存层
- 📊 **数据类型分类**: 基础信息、历史数据、财务数据、实时数据、新闻情绪
- 🔄 **数据流向设计**: 缓存优先级和数据源降级策略
- ⚡ **性能优化**: API限制、缓存策略、批量处理建议

### 3. 快速参考手册

**文档**: [stock_data_quick_reference.md](stock_data_quick_reference.md)

**核心内容**:
- 🚀 **推荐接口**: 最佳实践和推荐使用的统一接口
- 📋 **按场景分类**: 基本面分析、量化交易、新闻分析、风险管理
- 🎯 **数据源选择**: 质量排序、成本对比、使用建议
- 🔧 **性能优化**: 缓存配置、批量处理、常见问题解决

## 🔄 设计演进

### 最新更新 (2025-09-28)

**股票数据模型设计 v2.0**:
- ✅ 新增多市场支持 (CN/HK/US)
- ✅ 技术指标分类扩展机制
- ✅ 索引优化和查询性能提升
- ✅ 数据标准化和版本管理

**架构优化**:
- 🔧 数据获取与使用服务解耦
- 📊 MongoDB标准化数据模型
- 🚀 支持动态扩展新数据源SDK

## 📞 使用指南

### 查看设计文档
```bash
# 查看股票数据模型设计
cat docs/design/stock_data_model_design.md

# 查看数据方法分析
cat docs/design/stock_data_methods_analysis.md

# 查看快速参考
cat docs/design/stock_data_quick_reference.md
```

### 实现新功能时的参考顺序
1. **系统架构** → `stock_analysis_system_design.md`
2. **数据模型** → `stock_data_model_design.md`
3. **API设计** → `api_specification.md`
4. **数据获取** → `stock_data_methods_analysis.md`
5. **快速参考** → `stock_data_quick_reference.md`

## 🤝 贡献指南

### 更新设计文档
1. 在对应的设计文档中进行修改
2. 更新本 README.md 中的状态和描述
3. 如有重大变更，创建新的版本目录

### 新增设计文档
1. 在 `docs/design/` 目录下创建新文档
2. 在本 README.md 中添加索引条目
3. 遵循现有的文档格式和命名规范

---

*设计文档目录 - 最后更新: 2025-09-28*
