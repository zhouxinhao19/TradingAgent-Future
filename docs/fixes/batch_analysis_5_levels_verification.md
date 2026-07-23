# 批量分析5个深度级别验证

## 📋 验证目标

确认批量分析功能正确支持5个研究深度级别，并且每个任务都使用正确的配置。

## ✅ 验证结果

### 1. 前端验证

#### BatchAnalysis.vue 界面
- ✅ 显示5个深度选项：
  - ⚡ 1级 - 快速分析 (2-4分钟/只)
  - 📈 2级 - 基础分析 (4-6分钟/只)
  - 🎯 3级 - 标准分析 (6-10分钟/只，推荐)
  - 🔍 4级 - 深度分析 (10-15分钟/只)
  - 🏆 5级 - 全面分析 (15-25分钟/只)

#### 请求参数
```javascript
const batchRequest = {
  title: batchForm.title,
  description: batchForm.description,
  symbols: symbols.value,
  parameters: {
    market_type: batchForm.market,
    research_depth: batchForm.depth,  // ✅ 正确传递深度参数
    selected_analysts: convertAnalystNamesToIds(batchForm.analysts),
    include_sentiment: batchForm.includeSentiment,
    include_risk: batchForm.includeRisk,
    language: batchForm.language,
    quick_analysis_model: modelSettings.value.quickAnalysisModel,
    deep_analysis_model: modelSettings.value.deepAnalysisModel
  }
}
```

### 2. 后端验证

#### API端点：POST /api/analysis/batch
```python
@router.post("/batch", response_model=Dict[str, Any])
async def submit_batch_analysis(
    request: BatchAnalysisRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user)
):
    # 为每只期货品种创建单股分析任务
    for symbol in stock_symbols:
        single_req = SingleAnalysisRequest(
            symbol=symbol,
            stock_code=symbol,
            parameters=request.parameters  # ✅ 继承批量分析的参数
        )
        # 创建并执行任务
        create_res = await simple_service.create_analysis_task(user["id"], single_req)
        background_tasks.add_task(run_analysis_task_wrapper)
```

#### 配置生成
每个单股任务都会调用 `create_analysis_config()`，根据 `research_depth` 参数生成正确的配置：

| research_depth | max_debate_rounds | max_risk_discuss_rounds | memory_enabled | online_tools |
|----------------|-------------------|-------------------------|----------------|--------------|
| "快速"         | 1                 | 1                       | False          | False        |
| "基础"         | 1                 | 1                       | True           | True         |
| "标准"         | 1                 | 2                       | True           | True         |
| "深度"         | 2                 | 2                       | True           | True         |
| "全面"         | 3                 | 3                       | True           | True         |

### 3. 数据流验证

```
前端 BatchAnalysis.vue
  ↓ (选择深度: "标准")
  ↓
POST /api/analysis/batch
  {
    title: "测试批次",
    symbols: ["000001", "600519"],
    parameters: {
      research_depth: "标准",  // ✅
      ...
    }
  }
  ↓
后端 submit_batch_analysis()
  ↓ (为每只期货品种创建任务)
  ↓
SingleAnalysisRequest(
  symbol="000001",
  parameters={research_depth: "标准"}  // ✅
)
  ↓
create_analysis_config(
  research_depth="标准"  // ✅
)
  ↓
返回配置:
  {
    max_debate_rounds: 1,
    max_risk_discuss_rounds: 2,
    memory_enabled: True,
    online_tools: True
  }
```

## 🧪 单元测试验证

### 测试文件：tests/test_research_depth_5_levels.py

运行结果：
```bash
$ pytest tests/test_research_depth_5_levels.py -v

tests/test_research_depth_5_levels.py::TestResearchDepth5Levels::test_depth_level_1_fast PASSED
tests/test_research_depth_5_levels.py::TestResearchDepth5Levels::test_depth_level_2_basic PASSED
tests/test_research_depth_5_levels.py::TestResearchDepth5Levels::test_depth_level_3_standard PASSED
tests/test_research_depth_5_levels.py::TestResearchDepth5Levels::test_depth_level_4_deep PASSED
tests/test_research_depth_5_levels.py::TestResearchDepth5Levels::test_depth_level_5_comprehensive PASSED
tests/test_research_depth_5_levels.py::TestResearchDepth5Levels::test_unknown_depth_defaults_to_standard PASSED
tests/test_research_depth_5_levels.py::TestResearchDepth5Levels::test_all_depths_have_correct_progression PASSED
tests/test_research_depth_5_levels.py::TestAnalysisParametersDefault::test_default_research_depth_is_standard PASSED
tests/test_research_depth_5_levels.py::TestAnalysisParametersDefault::test_research_depth_accepts_all_5_levels PASSED

===================================== 9 passed, 1 warning in 4.38s ======================================
```

✅ **所有测试通过！**

## 📊 批量分析场景示例

### 场景1：快速扫描多只期货品种（1级）
```
批次：日常监控
期货品种：000001, 600519, 000002, 600036, 000858
深度：⚡ 1级 - 快速分析
预期：每只 2-4分钟，总计 10-20分钟
配置：禁用记忆和在线工具，使用缓存数据
```

### 场景2：常规投资组合分析（2级）
```
批次：月度投资组合
期货品种：000001, 600519, 000002
深度：📈 2级 - 基础分析
预期：每只 4-6分钟，总计 12-18分钟
配置：启用记忆和在线工具，获取最新数据
```

### 场景3：重点期货品种深度研究（3级，推荐）
```
批次：重点关注期货品种
期货品种：000001, 600519
深度：🎯 3级 - 标准分析
预期：每只 6-10分钟，总计 12-20分钟
配置：1轮辩论 + 2轮风险讨论
```

### 场景4：投资决策前的全面评估（4级）
```
批次：投资决策候选
期货品种：000001, 600519
深度：🔍 4级 - 深度分析
预期：每只 10-15分钟，总计 20-30分钟
配置：2轮辩论 + 2轮风险讨论
```

### 场景5：重大投资的完整研究（5级）
```
批次：重大投资研究
期货品种：000001
深度：🏆 5级 - 全面分析
预期：15-25分钟
配置：3轮辩论 + 3轮风险讨论，最高质量
```

## 🎯 批量分析优势

### 1. 统一配置
- 所有期货品种使用相同的分析深度
- 确保结果的可比性
- 便于批量决策

### 2. 灵活选择
- 根据批次重要性选择合适的深度
- 平衡时间成本和分析质量
- 5个级别满足不同需求

### 3. 并发执行
- 多只期货品种并发分析
- 充分利用系统资源
- 提高整体效率

### 4. 进度跟踪
- 每只期货品种独立跟踪进度
- 实时查看完成情况
- 支持部分成功

## 📝 使用建议

### 批量分析深度选择

| 批次规模 | 推荐深度 | 理由 |
|----------|----------|------|
| 10只以上 | 1-2级 | 快速扫描，控制总耗时 |
| 5-10只 | 2-3级 | 平衡质量和效率 |
| 3-5只 | 3-4级 | 确保分析质量 |
| 1-2只 | 4-5级 | 深度研究，充分评估 |

### 时间预估

| 深度 | 单只耗时 | 10只总耗时 | 适用场景 |
|------|----------|------------|----------|
| 1级 | 2-4分钟 | 20-40分钟 | 日常监控 |
| 2级 | 4-6分钟 | 40-60分钟 | 常规分析 |
| 3级 | 6-10分钟 | 60-100分钟 | 重点研究 |
| 4级 | 10-15分钟 | 100-150分钟 | 深度评估 |
| 5级 | 15-25分钟 | 150-250分钟 | 全面研究 |

## ✅ 验证结论

1. ✅ **前端界面**：正确显示5个深度选项
2. ✅ **参数传递**：正确传递 research_depth 参数
3. ✅ **后端处理**：正确为每只期货品种创建任务
4. ✅ **配置生成**：正确根据深度生成配置
5. ✅ **单元测试**：所有测试通过
6. ✅ **数据流**：完整的数据流验证通过

**批量分析功能已完全支持5个研究深度级别！** 🎉

## 📅 验证日期

2025-01-XX

## 👥 验证人员

- 开发者：AI Assistant
- 测试者：自动化测试

