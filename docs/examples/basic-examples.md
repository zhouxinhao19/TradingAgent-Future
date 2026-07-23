# 基本使用示例

## 概述

本文档提供了 TradingAgents 框架的基本使用示例，帮助您快速上手并了解各种功能的使用方法。

## 示例 1: 基本期货分析

### 最简单的使用方式
```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# 使用默认配置
ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())

# 分析苹果公司期货品种
state, decision = ta.propagate("AAPL", "2024-01-15")

print(f"推荐动作: {decision['action']}")
print(f"置信度: {decision['confidence']:.2f}")
print(f"推理: {decision['reasoning']}")
```

### 输出示例
```
推荐动作: buy
置信度: 0.75
推理: 基于强劲的基本面数据和积极的技术指标，建议买入AAPL期货品种...
```

## 示例 2: 自定义配置分析

### 配置优化的分析
```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

def analyze_with_custom_config(symbol, date):
    """使用自定义配置进行分析"""
    
    # 创建自定义配置
    config = DEFAULT_CONFIG.copy()
    config.update({
        "deep_think_llm": "gpt-4o-mini",      # 使用经济模型
        "quick_think_llm": "gpt-4o-mini",     # 使用经济模型
        "max_debate_rounds": 2,               # 增加辩论轮次
        "max_risk_discuss_rounds": 1,         # 风险讨论轮次
        "online_tools": True,                 # 使用实时数据
    })
    
    # 选择特定的分析师
    selected_analysts = ["market", "fundamentals", "news"]
    
    # 初始化分析器
    ta = TradingAgentsGraph(
        selected_analysts=selected_analysts,
        debug=True,
        config=config
    )
    
    print(f"开始分析 {symbol} ({date})...")
    
    # 执行分析
    state, decision = ta.propagate(symbol, date)
    
    return state, decision

# 使用示例
state, decision = analyze_with_custom_config("TSLA", "2024-01-15")

print("\n=== 分析结果 ===")
print(f"期货品种: TSLA")
print(f"动作: {decision['action']}")
print(f"数量: {decision.get('quantity', 0)}")
print(f"置信度: {decision['confidence']:.1%}")
print(f"风险评分: {decision['risk_score']:.1%}")
```

## 示例 3: 批量期货分析

### 分析多只期货品种
```python
import pandas as pd
from datetime import datetime, timedelta

def batch_analysis(symbols, date):
    """批量分析多只期货品种"""
    
    # 配置
    config = DEFAULT_CONFIG.copy()
    config["max_debate_rounds"] = 1  # 减少辩论轮次以提高速度
    config["online_tools"] = True
    
    ta = TradingAgentsGraph(debug=False, config=config)
    
    results = []
    
    for symbol in symbols:
        try:
            print(f"正在分析 {symbol}...")
            
            # 执行分析
            state, decision = ta.propagate(symbol, date)
            
            # 收集结果
            result = {
                "symbol": symbol,
                "action": decision.get("action", "hold"),
                "confidence": decision.get("confidence", 0.5),
                "risk_score": decision.get("risk_score", 0.5),
                "reasoning": decision.get("reasoning", "")[:100] + "..."  # 截取前100字符
            }
            
            results.append(result)
            print(f"✅ {symbol}: {result['action']} (置信度: {result['confidence']:.1%})")
            
        except Exception as e:
            print(f"❌ {symbol}: 分析失败 - {e}")
            results.append({
                "symbol": symbol,
                "action": "error",
                "confidence": 0.0,
                "risk_score": 1.0,
                "reasoning": f"分析失败: {e}"
            })
    
    return pd.DataFrame(results)

# 使用示例
tech_stocks = ["AAPL", "GOOGL", "MSFT", "TSLA", "NVDA"]
analysis_date = "2024-01-15"

results_df = batch_analysis(tech_stocks, analysis_date)

print("\n=== 批量分析结果 ===")
print(results_df[["symbol", "action", "confidence", "risk_score"]])

# 筛选买入建议
buy_recommendations = results_df[results_df["action"] == "buy"]
print(f"\n买入建议 ({len(buy_recommendations)} 只):")
for _, row in buy_recommendations.iterrows():
    print(f"  {row['symbol']}: 置信度 {row['confidence']:.1%}")
```

## 示例 4: 不同LLM提供商对比

### 对比不同LLM的分析结果
```python
def compare_llm_providers(symbol, date):
    """对比不同LLM提供商的分析结果"""
    
    providers_config = {
        "OpenAI": {
            "llm_provider": "openai",
            "deep_think_llm": "gpt-4o-mini",
            "quick_think_llm": "gpt-4o-mini",
        },
        "Google": {
            "llm_provider": "google",
            "deep_think_llm": "gemini-pro",
            "quick_think_llm": "gemini-pro",
        },
        # 注意: 需要相应的API密钥
    }
    
    results = {}
    
    for provider_name, provider_config in providers_config.items():
        try:
            print(f"使用 {provider_name} 分析 {symbol}...")
            
            # 创建配置
            config = DEFAULT_CONFIG.copy()
            config.update(provider_config)
            config["max_debate_rounds"] = 1
            
            # 初始化分析器
            ta = TradingAgentsGraph(debug=False, config=config)
            
            # 执行分析
            state, decision = ta.propagate(symbol, date)
            
            results[provider_name] = {
                "action": decision.get("action", "hold"),
                "confidence": decision.get("confidence", 0.5),
                "risk_score": decision.get("risk_score", 0.5),
            }
            
            print(f"✅ {provider_name}: {results[provider_name]['action']}")
            
        except Exception as e:
            print(f"❌ {provider_name}: 失败 - {e}")
            results[provider_name] = {"error": str(e)}
    
    return results

# 使用示例
comparison_results = compare_llm_providers("AAPL", "2024-01-15")

print("\n=== LLM提供商对比结果 ===")
for provider, result in comparison_results.items():
    if "error" not in result:
        print(f"{provider}:")
        print(f"  动作: {result['action']}")
        print(f"  置信度: {result['confidence']:.1%}")
        print(f"  风险评分: {result['risk_score']:.1%}")
    else:
        print(f"{provider}: 错误 - {result['error']}")
```

## 示例 5: 历史回测分析

### 简单的历史回测
```python
from datetime import datetime, timedelta
import matplotlib.pyplot as plt

def historical_backtest(symbol, start_date, end_date, interval_days=7):
    """简单的历史回测"""
    
    # 配置
    config = DEFAULT_CONFIG.copy()
    config["max_debate_rounds"] = 1
    config["online_tools"] = True
    
    ta = TradingAgentsGraph(debug=False, config=config)
    
    # 生成日期列表
    current_date = datetime.strptime(start_date, "%Y-%m-%d")
    end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")
    
    results = []
    
    while current_date <= end_date_obj:
        date_str = current_date.strftime("%Y-%m-%d")
        
        try:
            print(f"分析 {symbol} 在 {date_str}...")
            
            # 执行分析
            state, decision = ta.propagate(symbol, date_str)
            
            result = {
                "date": date_str,
                "action": decision.get("action", "hold"),
                "confidence": decision.get("confidence", 0.5),
                "risk_score": decision.get("risk_score", 0.5),
            }
            
            results.append(result)
            print(f"  {result['action']} (置信度: {result['confidence']:.1%})")
            
        except Exception as e:
            print(f"  错误: {e}")
        
        # 移动到下一个日期
        current_date += timedelta(days=interval_days)
    
    return pd.DataFrame(results)

# 使用示例
backtest_results = historical_backtest(
    symbol="AAPL",
    start_date="2024-01-01",
    end_date="2024-01-31",
    interval_days=7
)

print("\n=== 历史回测结果 ===")
print(backtest_results)

# 统计分析
action_counts = backtest_results["action"].value_counts()
print(f"\n动作分布:")
for action, count in action_counts.items():
    print(f"  {action}: {count} 次")

avg_confidence = backtest_results["confidence"].mean()
print(f"\n平均置信度: {avg_confidence:.1%}")
```

## 示例 6: 实时监控

### 实时期货品种监控
```python
import time
from datetime import datetime

def real_time_monitor(symbols, check_interval=300):
    """实时监控期货品种"""
    
    config = DEFAULT_CONFIG.copy()
    config["max_debate_rounds"] = 1
    config["online_tools"] = True
    
    ta = TradingAgentsGraph(debug=False, config=config)
    
    print(f"开始监控 {len(symbols)} 只期货品种...")
    print(f"检查间隔: {check_interval} 秒")
    print("按 Ctrl+C 停止监控\n")
    
    try:
        while True:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            current_date = datetime.now().strftime("%Y-%m-%d")
            
            print(f"=== {current_time} ===")
            
            for symbol in symbols:
                try:
                    # 执行分析
                    state, decision = ta.propagate(symbol, current_date)
                    
                    action = decision.get("action", "hold")
                    confidence = decision.get("confidence", 0.5)
                    
                    # 输出结果
                    status_emoji = "🟢" if action == "buy" else "🔴" if action == "sell" else "🟡"
                    print(f"{status_emoji} {symbol}: {action.upper()} (置信度: {confidence:.1%})")
                    
                    # 高置信度买入/卖出提醒
                    if confidence > 0.8 and action in ["buy", "sell"]:
                        print(f"  ⚠️  高置信度{action}信号!")
                
                except Exception as e:
                    print(f"❌ {symbol}: 分析失败 - {e}")
            
            print(f"下次检查: {check_interval} 秒后\n")
            time.sleep(check_interval)
    
    except KeyboardInterrupt:
        print("\n监控已停止")

# 使用示例（注释掉以避免长时间运行）
# watch_list = ["AAPL", "GOOGL", "TSLA"]
# real_time_monitor(watch_list, check_interval=300)  # 每5分钟检查一次
```

## 示例 7: 错误处理和重试

### 健壮的分析函数
```python
import time
from typing import Optional, Tuple

def robust_analysis(symbol: str, date: str, max_retries: int = 3) -> Optional[Tuple[dict, dict]]:
    """带错误处理和重试的分析函数"""
    
    config = DEFAULT_CONFIG.copy()
    config["max_debate_rounds"] = 1
    
    for attempt in range(max_retries):
        try:
            print(f"分析 {symbol} (尝试 {attempt + 1}/{max_retries})...")
            
            ta = TradingAgentsGraph(debug=False, config=config)
            state, decision = ta.propagate(symbol, date)
            
            # 验证结果
            if not decision or "action" not in decision:
                raise ValueError("分析结果无效")
            
            print(f"✅ 分析成功: {decision['action']}")
            return state, decision
            
        except Exception as e:
            print(f"❌ 尝试 {attempt + 1} 失败: {e}")
            
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 指数退避
                print(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
            else:
                print(f"所有尝试都失败了")
                return None

# 使用示例
result = robust_analysis("AAPL", "2024-01-15", max_retries=3)

if result:
    state, decision = result
    print(f"最终结果: {decision['action']}")
else:
    print("分析失败")
```

## 示例 8: 结果保存和加载

### 保存分析结果
```python
import json
import pickle
from datetime import datetime

def save_analysis_result(symbol, date, state, decision, format="json"):
    """保存分析结果"""
    
    # 创建结果目录
    import os
    results_dir = "analysis_results"
    os.makedirs(results_dir, exist_ok=True)
    
    # 生成文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{symbol}_{date}_{timestamp}"
    
    # 准备数据
    result_data = {
        "symbol": symbol,
        "date": date,
        "timestamp": timestamp,
        "decision": decision,
        "state_summary": {
            "analyst_reports": getattr(state, "analyst_reports", {}),
            "research_reports": getattr(state, "research_reports", {}),
            "trader_decision": getattr(state, "trader_decision", {}),
            "risk_assessment": getattr(state, "risk_assessment", {}),
        }
    }
    
    if format == "json":
        filepath = os.path.join(results_dir, f"{filename}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(result_data, f, indent=2, ensure_ascii=False)
    
    elif format == "pickle":
        filepath = os.path.join(results_dir, f"{filename}.pkl")
        with open(filepath, "wb") as f:
            pickle.dump(result_data, f)
    
    print(f"结果已保存到: {filepath}")
    return filepath

# 使用示例
ta = TradingAgentsGraph(debug=False, config=DEFAULT_CONFIG.copy())
state, decision = ta.propagate("AAPL", "2024-01-15")

# 保存结果
save_analysis_result("AAPL", "2024-01-15", state, decision, format="json")
```

这些基本示例展示了 TradingAgents 框架的主要功能和使用模式。您可以根据自己的需求修改和扩展这些示例。
