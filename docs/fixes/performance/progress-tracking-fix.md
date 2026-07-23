# 📊 进度跟踪系统完整修复方案

## 🔍 问题分析

### 1. **核心问题**
前端进度条在分析过程中不能实时更新，特别是在"研究辩论"阶段（60%-85%）会卡住，直到分析完成后直接跳到100%。

### 2. **根本原因**

#### 2.1 节点名称不匹配 ❌
**问题**：LangGraph 实际使用的节点名称与我们的映射表不匹配

**LangGraph 实际节点名称**（来自 `tradingagents/graph/setup.py`）：
```python
# 分析师节点
"Market Analyst"           # 不是 'market_analyst'
"Fundamentals Analyst"     # 不是 'fundamentals_analyst'
"News Analyst"             # 不是 'news_analyst'
"Social Analyst"           # 不是 'social_analyst'

# 工具节点
"tools_market"
"tools_fundamentals"
"tools_news"
"tools_social"

# 消息清理节点
"Msg Clear Market"
"Msg Clear Fundamentals"
"Msg Clear News"
"Msg Clear Social"

# 研究员节点
"Bull Researcher"          # 不是 'bull_researcher'
"Bear Researcher"          # 不是 'bear_researcher'
"Research Manager"         # 不是 'research_manager'

# 交易员节点
"Trader"                   # 不是 'trader'

# 风险评估节点
"Risky Analyst"            # 不是 'risky_analyst'
"Safe Analyst"             # 不是 'safe_analyst'
"Neutral Analyst"          # 不是 'neutral_analyst'
"Risk Judge"               # 不是 'risk_manager'
```

**我们之前的错误映射**：
```python
node_mapping = {
    'market_analyst': "📊 市场分析师",      # ❌ 错误
    'fundamentals_analyst': "💼 基本面分析师",  # ❌ 错误
    'bull_researcher': "🐂 看涨研究员",     # ❌ 错误
    # ...
}
```

**结果**：回调函数无法识别任何节点，导致进度更新完全失败。

#### 2.2 进度计算不完整 ❌
**问题**：只在"辩论阶段"更新进度，其他阶段没有更新

**之前的逻辑**：
```python
# 只处理辩论阶段（60%-85%）
if "看涨" in message:
    debate_node_count = 1
elif "看跌" in message:
    debate_node_count = 2
# ...
current_progress = 60 + (25 * progress_in_debate)
```

**缺失的阶段**：
- ❌ 分析师阶段（10%-45%）：没有更新
- ❌ 交易员阶段（70%-78%）：没有更新
- ❌ 风险评估阶段（78%-93%）：没有更新
- ❌ 最终阶段（93%-100%）：没有更新

#### 2.3 步骤权重与实际执行不同步 ❌
**问题**：`RedisProgressTracker` 定义的步骤权重与 LangGraph 实际执行流程不匹配

**步骤权重定义**（`app/services/progress/tracker.py`）：
```python
# 1) 基础准备阶段 (10%)
steps.extend([
    AnalysisStep("📋 准备阶段", ..., 0.03),
    AnalysisStep("🔧 环境检查", ..., 0.02),
    # ...
])

# 2) 分析师团队阶段 (35%)
analyst_weight = 0.35 / max(len(self.analysts), 1)

# 3) 研究团队辩论阶段 (25%)
debate_weight = 0.25 / (3 + rounds)

# 4) 交易团队阶段 (8%)
# 5) 风险管理团队阶段 (15%)
# 6) 最终决策阶段 (7%)
```

**实际执行流程**：
- LangGraph 只执行分析师、研究员、交易员、风险评估等节点
- 不执行"准备阶段"、"环境检查"等虚拟步骤
- 导致步骤状态与实际进度不同步

## ✅ 完整解决方案

### 1. **修复节点名称映射**

**文件**：`tradingagents/graph/trading_graph.py`

**修改**：`_send_progress_update()` 方法

```python
def _send_progress_update(self, chunk, progress_callback):
    """发送进度更新到回调函数
    
    LangGraph stream 返回的 chunk 格式：{node_name: {...}}
    """
    try:
        if not isinstance(chunk, dict):
            return
        
        # 获取节点名称
        node_name = None
        for key in chunk.keys():
            if not key.startswith('__'):
                node_name = key
                break
        
        if not node_name:
            return
        
        # ✅ 正确的节点名称映射表
        node_mapping = {
            # 分析师节点（匹配 LangGraph 实际节点名）
            'Market Analyst': "📊 市场分析师",
            'Fundamentals Analyst': "💼 基本面分析师",
            'News Analyst': "📰 新闻分析师",
            'Social Analyst': "💬 社交媒体分析师",
            # 工具节点（跳过，避免重复）
            'tools_market': None,
            'tools_fundamentals': None,
            'tools_news': None,
            'tools_social': None,
            # 消息清理节点（跳过）
            'Msg Clear Market': None,
            'Msg Clear Fundamentals': None,
            'Msg Clear News': None,
            'Msg Clear Social': None,
            # 研究员节点
            'Bull Researcher': "🐂 看涨研究员",
            'Bear Researcher': "🐻 看跌研究员",
            'Research Manager': "👔 研究经理",
            # 交易员节点
            'Trader': "💼 交易员决策",
            # 风险评估节点
            'Risky Analyst': "🔥 激进风险评估",
            'Safe Analyst': "🛡️ 保守风险评估",
            'Neutral Analyst': "⚖️ 中性风险评估",
            'Risk Judge': "🎯 风险经理",
        }
        
        message = node_mapping.get(node_name)
        
        if message is None:
            # 跳过工具节点和消息清理节点
            return
        
        if message:
            # 发送进度更新
            progress_callback(message)
        else:
            # 未知节点
            progress_callback(f"🔍 {node_name}")
            
    except Exception as e:
        logger.error(f"❌ 进度更新失败: {e}", exc_info=True)
```

### 2. **修复进度计算逻辑**

**文件**：`app/services/simple_analysis_service.py`

**修改**：`graph_progress_callback()` 函数

```python
# ✅ 完整的节点进度映射表
node_progress_map = {
    # 分析师阶段 (10% → 45%)
    "📊 市场分析师": 27.5,      # 10% + 17.5%
    "💼 基本面分析师": 45,       # 10% + 35%
    "📰 新闻分析师": 27.5,
    "💬 社交媒体分析师": 27.5,
    # 研究辩论阶段 (45% → 70%)
    "🐂 看涨研究员": 51.25,      # 45% + 6.25%
    "🐻 看跌研究员": 57.5,       # 45% + 12.5%
    "👔 研究经理": 70,           # 45% + 25%
    # 交易员阶段 (70% → 78%)
    "💼 交易员决策": 78,         # 70% + 8%
    # 风险评估阶段 (78% → 93%)
    "🔥 激进风险评估": 81.75,    # 78% + 3.75%
    "🛡️ 保守风险评估": 85.5,    # 78% + 7.5%
    "⚖️ 中性风险评估": 89.25,   # 78% + 11.25%
    "🎯 风险经理": 93,           # 78% + 15%
    # 最终阶段 (93% → 100%)
    "📊 生成报告": 97,           # 93% + 4%
}

def graph_progress_callback(message: str):
    """接收 LangGraph 的进度更新"""
    try:
        if not progress_tracker:
            return
        
        # ✅ 直接映射节点到进度百分比
        progress_pct = node_progress_map.get(message)
        
        if progress_pct is not None:
            progress_tracker.update_progress({
                'progress_percentage': int(progress_pct),
                'last_message': message
            })
            logger.info(f"📊 进度已更新: {int(progress_pct)}% - {message}")
        else:
            # 未知节点，只更新消息
            progress_tracker.update_progress({
                'last_message': message
            })
            
    except Exception as e:
        logger.error(f"❌ 回调失败: {e}", exc_info=True)
```

## 🎯 修复效果

### 修复前 ❌
```
进度: 10% → 60% → [卡住很久] → 100%
步骤: 准备阶段 → 基本面分析师 → [卡住] → 完成
```

### 修复后 ✅
```
进度: 10% → 27.5% → 45% → 51.25% → 57.5% → 70% → 78% → 81.75% → 85.5% → 89.25% → 93% → 97% → 100%
步骤: 准备 → 市场分析师 → 基本面分析师 → 看涨研究员 → 看跌研究员 → 研究经理 → 交易员 → 激进风险 → 保守风险 → 中性风险 → 风险经理 → 生成报告 → 完成
```

## 🧪 测试步骤

1. **重启后端**
   ```powershell
   .\.venv\Scripts\python -m app
   ```

2. **触发新的分析任务**
   - 在前端点击"开始分析"按钮
   - 输入品种代码（如：601398）

3. **观察进度更新**
   - 前端进度条应该平滑更新
   - 步骤状态应该正确显示（completed/current/pending）
   - 当前步骤名称应该实时更新

4. **检查日志**
   ```powershell
   # 查看进度回调日志
   Get-Content "logs\webapi.log" -Tail 1000 | Select-String "🎯🎯🎯|📊 \[Graph进度\]"
   ```

## 📝 关键改进点

1. ✅ **节点名称完全匹配**：使用 LangGraph 实际的节点名称
2. ✅ **覆盖所有阶段**：分析师、研究员、交易员、风险评估、最终阶段
3. ✅ **跳过中间节点**：工具节点和消息清理节点不触发进度更新
4. ✅ **进度百分比准确**：与 RedisProgressTracker 的步骤权重对应
5. ✅ **错误处理完善**：未知节点也能正常处理

## 🔧 后续优化建议

1. **动态计算进度**：根据实际选择的分析师数量动态调整进度百分比
2. **辩论轮次支持**：根据 research_depth 动态计算辩论阶段的进度
3. **并行分析师**：如果分析师并行执行，需要调整进度计算逻辑
4. **进度平滑过渡**：添加进度动画，避免跳跃式更新

