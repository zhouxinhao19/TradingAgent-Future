# 🚀 DeepSeek V3 预览版快速开始

## ⚡ 5分钟快速体验

### 第一步：获取代码
```bash
# 克隆预览分支
git clone -b feature/deepseek-v3-integration https://github.com/hsliuping/TradingAgents-CN.git
cd TradingAgents-CN

# 创建虚拟环境
python -m venv env
env\Scripts\activate  # Windows
# source env/bin/activate  # Linux/macOS

# 安装依赖
pip install -r requirements.txt
```

### 第二步：配置API密钥
```bash
# 复制配置文件
cp .env.example .env

# 编辑.env文件，添加以下内容：
# DEEPSEEK_API_KEY=sk-your_deepseek_api_key_here
# DEEPSEEK_ENABLED=true
```

**获取DeepSeek API密钥**：
1. 访问 [DeepSeek平台](https://platform.deepseek.com/)
2. 注册账号 → 控制台 → API Keys → 创建新密钥

### 第三步：快速测试
```bash
# 测试连接
python -c "
from tradingagents.llm_adapters.deepseek_adapter import ChatDeepSeek
llm = ChatDeepSeek()
print('✅ DeepSeek连接成功')
"

# 启动Web界面
streamlit run web/app.py
```

### 第四步：开始分析
1. 打开浏览器访问 http://localhost:8501
2. 在左侧选择"DeepSeek V3"模型
3. 输入股票代码（如：000001、AAPL）
4. 点击"开始分析"

## 🎯 核心功能演示

### 1. 基本面分析（推荐）
```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# 配置DeepSeek
config = DEFAULT_CONFIG.copy()
config.update({
    "llm_provider": "deepseek",
    "llm_model": "deepseek-chat"
})

# 创建分析器
ta = TradingAgentsGraph(
    selected_analysts=["fundamentals"],
    config=config
)

# 分析平安银行
result = ta.run_analysis("000001", "2025-01-08")
print("投资建议:", result["decision"]["action"])
print("基本面评分:", result["analysis"]["fundamental_score"])
```

### 2. 成本统计
```python
from tradingagents.config.config_manager import config_manager

# 查看使用统计
stats = config_manager.get_usage_statistics(1)
print(f"今日成本: ¥{stats['total_cost']:.4f}")
print(f"Token使用: {stats['total_tokens']}")
```

## 💡 推荐测试股票

### A股（中国股票）
- **000001** - 平安银行（银行业）
- **600519** - 贵州茅台（白酒业）
- **000858** - 五粮液（白酒业）
- **002594** - 比亚迪（新能源汽车）
- **300750** - 宁德时代（电池）

### 美股
- **AAPL** - 苹果公司
- **MSFT** - 微软
- **GOOGL** - 谷歌
- **TSLA** - 特斯拉

## 🔍 预期结果示例

### 基本面分析输出
```
## 💰 财务数据分析

### 估值指标
- 市盈率(PE): 5.2倍（银行业平均水平）
- 市净率(PB): 0.65倍（破净状态，银行业常见）
- 股息收益率: 4.2%（银行业分红较高）

### 盈利能力指标
- 净资产收益率(ROE): 12.5%（银行业平均）
- 总资产收益率(ROA): 0.95%

## 💡 投资建议
**投资建议**: 🟢 **买入**
- 基本面良好，估值合理，具有较好的投资价值
- 建议分批建仓，长期持有

## 📊 评分系统
- 基本面评分: 7.5/10
- 估值吸引力: 8.0/10
- 成长潜力: 6.5/10
- 风险等级: 中等
```

### 成本统计示例
```
📊 Token使用统计:
- 输入Token: 2,156
- 输出Token: 1,847
- 总成本: ¥0.0058
- 会话ID: analysis_20250108_001
```

## ⚠️ 注意事项

### 预览版限制
- 🧪 **实验性功能**：可能存在未知问题
- 📊 **数据估算**：基本面分析基于估算，非实时财务数据
- ⏱️ **响应时间**：首次调用可能较慢（5-15秒）
- 🔄 **Token精度**：统计可能有轻微误差

### 使用建议
- 💰 **成本控制**：监控每日使用量，避免超支
- 🔍 **结果验证**：分析结果仅供参考，请结合其他信息
- 🐛 **问题反馈**：发现问题请及时反馈
- 📚 **文档参考**：详细使用方法请查看完整文档

## 🆘 遇到问题？

### 常见问题快速解决

#### 1. API密钥错误
```bash
# 检查配置
python -c "
import os
from dotenv import load_dotenv
load_dotenv()
print('API Key:', '✅ 已配置' if os.getenv('DEEPSEEK_API_KEY') else '❌ 未配置')
"
```

#### 2. 依赖安装问题
```bash
# 重新安装依赖
pip install --upgrade -r requirements.txt
```

#### 3. 网络连接问题
```bash
# 测试网络连接
python -c "
import requests
try:
    response = requests.get('https://api.deepseek.com', timeout=10)
    print('✅ 网络连接正常')
except:
    print('❌ 网络连接失败')
"
```

### 获取帮助
- 📖 **详细文档**：查看 [完整使用指南](docs/usage/deepseek-usage-guide.md)
- 🧪 **测试指南**：查看 [测试指南](TESTING_GUIDE.md)
- 🐛 **问题反馈**：[GitHub Issues](https://github.com/hsliuping/TradingAgents-CN/issues)
- 💬 **社区讨论**：[GitHub Discussions](https://github.com/hsliuping/TradingAgents-CN/discussions)

## 📚 下一步

### 深入学习
1. **阅读完整文档**：[DeepSeek使用指南](docs/usage/deepseek-usage-guide.md)
2. **查看配置选项**：[DeepSeek配置指南](docs/configuration/deepseek-config.md)
3. **学习最佳实践**：[投资分析指南](docs/usage/investment_analysis_guide.md)

### 参与贡献
1. **测试反馈**：使用不同股票进行测试，反馈问题和建议
2. **文档改进**：帮助完善文档和示例
3. **代码贡献**：修复Bug或添加新功能

---

**🎉 欢迎体验DeepSeek V3预览版！您的反馈对我们非常宝贵。**

---

**快速链接**：
- 📖 [预览版说明](DEEPSEEK_PREVIEW_README.md)
- 🧪 [测试指南](TESTING_GUIDE.md)
- 📋 [发布说明](RELEASE_NOTES_PREVIEW.md)
- 🔧 [配置指南](docs/configuration/deepseek-config.md)
