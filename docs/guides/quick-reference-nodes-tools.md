# 📋 TradingAgents 节点工具快速参考

## 🔄 分析流程概览

```
🚀 开始 → 🔍 验证 → 🔧 准备 → 💰 预估 → ⚙️ 配置 → 🏗️ 初始化
    ↓
👥 分析师团队 (并行执行)
├── 📈 市场分析师      ← get_stock_market_data_unified
├── 📊 基本面分析师    ← get_stock_fundamentals_unified  
├── 📰 新闻分析师      ← get_realtime_stock_news
└── 💬 社交媒体分析师  ← get_stock_news_openai
    ↓
🎯 研究员辩论
├── 🐂 看涨研究员 ←→ 🐻 看跌研究员
└── 👔 研究经理 (形成共识)
    ↓
💼 交易员 (制定交易策略)
    ↓
⚠️ 风险评估团队
├── 🔥 激进评估 ← 🛡️ 保守评估 → ⚖️ 中性评估
└── 🎯 风险经理 (最终风险决策)
    ↓
📡 信号处理 → ✅ 最终决策
```

## 👥 核心节点速查

| 节点类型 | 节点名称 | 主要职责 | 核心工具 |
|---------|---------|---------|---------|
| **分析师** | 📈 市场分析师 | 技术分析、趋势识别 | `get_stock_market_data_unified` |
| **分析师** | 📊 基本面分析师 | 财务分析、估值模型 | `get_stock_fundamentals_unified` |
| **分析师** | 📰 新闻分析师 | 新闻事件、宏观分析 | `get_realtime_stock_news` |
| **分析师** | 💬 社交媒体分析师 | 情绪分析、舆论监控 | `get_stock_news_openai` |
| **研究员** | 🐂 看涨研究员 | 乐观角度、增长潜力 | LLM推理 + 记忆 |
| **研究员** | 🐻 看跌研究员 | 悲观角度、风险识别 | LLM推理 + 记忆 |
| **管理层** | 👔 研究经理 | 辩论主持、共识形成 | LLM推理 + 记忆 |
| **交易** | 💼 交易员 | 交易决策、仓位管理 | LLM推理 + 记忆 |
| **风险** | 🔥 激进评估 | 高风险高收益策略 | LLM推理 |
| **风险** | 🛡️ 保守评估 | 低风险稳健策略 | LLM推理 |
| **风险** | ⚖️ 中性评估 | 平衡风险收益 | LLM推理 |
| **管理层** | 🎯 风险经理 | 风险控制、政策制定 | LLM推理 + 记忆 |
| **处理** | 📡 信号处理 | 信号整合、最终输出 | 信号处理算法 |

## 🔧 核心工具速查

### 📈 市场数据工具
```python
# 统一市场数据工具 (推荐)
get_stock_market_data_unified(ticker, start_date, end_date)
# 自动识别期货品种类型，调用最佳数据源
# A股: Tushare + AKShare | 港股: AKShare + Yahoo | 美股: Yahoo + FinnHub

# 备用工具
get_YFin_data_online(symbol, start_date, end_date)           # Yahoo Finance
get_stockstats_indicators_report_online(symbol, period)     # 技术指标
```

### 📊 基本面工具
```python
# 统一基本面工具 (推荐)
get_stock_fundamentals_unified(ticker, start_date, end_date, curr_date)
# 自动识别期货品种类型，调用最佳数据源
# A股: Tushare + AKShare | 港股: AKShare | 美股: FinnHub + SimFin

# 补充工具
get_finnhub_company_insider_sentiment(symbol)               # 内部人士情绪
get_simfin_balance_sheet(ticker, year, period)             # 资产负债表
get_simfin_income_stmt(ticker, year, period)               # 利润表
```

### 📰 新闻工具
```python
# 实时新闻
get_realtime_stock_news(symbol, days_back)                 # 实时期货品种新闻
get_global_news_openai(query, max_results)                 # 全球新闻 (OpenAI)
get_google_news(query, lang, country)                      # Google 新闻

# 历史新闻
get_finnhub_news(symbol, start_date, end_date)             # FinnHub 新闻
get_reddit_news(subreddit, limit)                          # Reddit 新闻
```

### 💬 社交媒体工具
```python
# 情绪分析
get_stock_news_openai(symbol, sentiment_focus)             # 期货品种新闻情绪
get_reddit_stock_info(symbol, limit)                       # Reddit 讨论
get_chinese_social_sentiment(symbol, platform)             # 中国社交媒体
```

## 🎯 数据源映射

| 期货品种类型 | 识别规则 | 市场数据源 | 基本面数据源 | 新闻数据源 |
|---------|---------|-----------|-------------|-----------|
| **A股** | 6位数字 (000001) | Tushare + AKShare | Tushare + AKShare | 财联社 + 新浪财经 |
| **港股** | .HK后缀 (0700.HK) | AKShare + Yahoo | AKShare | Google News |
| **美股** | 字母代码 (AAPL) | Yahoo + FinnHub | FinnHub + SimFin | FinnHub + Google |

## ⚙️ 配置速查

### 分析师选择
```python
# 快速分析 (1-2分钟)
selected_analysts = ["market"]

# 基础分析 (3-5分钟)  
selected_analysts = ["market", "fundamentals"]

# 完整分析 (5-10分钟)
selected_analysts = ["market", "fundamentals", "news", "social"]
```

### 研究深度
```python
research_depth = 1    # 快速: 减少工具调用，快速模型
research_depth = 2    # 标准: 平衡速度和质量 (推荐)
research_depth = 3    # 深度: 增加辩论轮次，深度模型
```

### LLM提供商
```python
llm_provider = "dashscope"    # 阿里百炼 (推荐，中文优化)
llm_provider = "deepseek"     # DeepSeek (性价比高)
llm_provider = "google"       # Google Gemini (质量高)
```

## 🔄 工具调用循环

每个分析师都遵循LangGraph的标准循环：

```
1️⃣ 分析师节点
    ↓ (决定需要什么数据)
2️⃣ 条件判断 
    ↓ (检查是否有工具调用)
3️⃣ 工具节点
    ↓ (执行数据获取)
4️⃣ 回到分析师节点
    ↓ (处理数据，生成报告)
5️⃣ 条件判断
    ↓ (检查是否完成)
6️⃣ 消息清理 → 下一个分析师
```

**日志示例**:
```
📊 [模块开始] market_analyst - 期货品种: 000858
📊 [市场分析师] 工具调用: ['get_stock_market_data_unified']  
📊 [模块完成] market_analyst - ✅ 成功 - 耗时: 41.73s
```

## 🚀 快速使用

### 基本用法
```python
from tradingagents.graph.trading_graph import TradingAgentsGraph

# 创建分析图
graph = TradingAgentsGraph(
    selected_analysts=["market", "fundamentals"],
    config={"llm_provider": "dashscope", "research_depth": 2}
)

# 执行分析
state, decision = graph.propagate("000858", "2025-01-17")
print(f"建议: {decision['action']}, 置信度: {decision['confidence']}")
```

### Web界面使用
```bash
# 启动Web界面
python web/run_web.py

# 访问 http://localhost:8501
# 1. 输入品种代码
# 2. 选择分析师和研究深度  
# 3. 点击"开始分析"
# 4. 查看实时进度和结果
```

## ❓ 常见问题速查

| 问题 | 原因 | 解决方案 |
|-----|------|---------|
| 分析时间过长 | 研究深度过高/网络慢 | 降低research_depth，检查网络 |
| 重复分析师调用 | LangGraph正常机制 | 正常现象，等待完成 |
| 基本面分析师多轮调用 | 强制工具调用机制 | 正常现象，确保数据质量 |
| API调用失败 | 密钥错误/限额超出 | 检查.env配置，确认API额度 |
| 进度卡住 | 网络超时/API异常 | 刷新页面，检查日志 |
| 中文乱码 | 编码问题 | 使用UTF-8编码，检查字体 |

## 🔄 工具调用机制详解

### 📈 市场分析师（简单模式）
```
1️⃣ 分析师决策 → 2️⃣ 调用统一工具 → 3️⃣ 生成报告
```

### 📊 基本面分析师（复杂模式）
```
1️⃣ 尝试LLM自主调用 → 2️⃣ 工具执行 → 3️⃣ 数据处理
                ↓ (如果LLM未调用工具)
4️⃣ 强制工具调用 → 5️⃣ 重新生成报告
```

### 🧠 LLM工具选择逻辑
1. **系统提示词引导** (权重最高)
2. **工具描述匹配度**
3. **工具名称语义理解**
4. **参数简洁性偏好**
5. **模型特性差异**

## 📊 输出格式

### 最终决策格式
```json
{
    "action": "买入/持有/卖出",
    "confidence": 8.5,
    "target_price": "45.80",
    "stop_loss": "38.20", 
    "position_size": "中等仓位",
    "time_horizon": "3-6个月",
    "reasoning": "详细分析理由..."
}
```

### 分析报告结构
```
📈 市场分析报告
├── 期货品种基本信息
├── 技术指标分析  
├── 价格趋势分析
├── 成交量分析
└── 投资建议

📊 基本面分析报告  
├── 财务状况分析
├── 估值分析
├── 行业对比
├── 风险评估
└── 投资建议
```

---

*快速参考 | TradingAgents v0.1.7 | 更多详情请查看完整文档*
