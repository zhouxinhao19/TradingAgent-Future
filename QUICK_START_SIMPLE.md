# 🚀 5分钟快速开始

> **目标**：让您在5分钟内开始使用TradingAgents-CN进行股票分析

## 📋 准备工作

### 1. 确保已安装Python

```bash
# 检查Python版本（需要3.10或更高）
python --version
```

如果未安装，请访问 [python.org](https://www.python.org/downloads/) 下载安装。

### 2. 获取API密钥（选择一个）

| 提供商 | 获取地址 | 推荐理由 | 成本 |
|--------|---------|---------|------|
| **DeepSeek** | [platform.deepseek.com](https://platform.deepseek.com/) | 性价比最高 | 💰 极低 |
| **通义千问** | [dashscope.aliyun.com](https://dashscope.aliyun.com/) | 国产稳定 | 💰 低 |
| **Google Gemini** | [aistudio.google.com](https://aistudio.google.com/) | 免费额度大 | 💰 免费 |

## 🎯 一键安装

### Windows 用户

1. **下载项目**
   ```powershell
   git clone https://github.com/hsliuping/TradingAgents-CN.git
   cd TradingAgents-CN
   ```

2. **运行安装脚本**
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\easy_install.ps1
   ```

3. **按照提示操作**
   - 选择LLM提供商（推荐DeepSeek）
   - 输入API密钥
   - 等待自动安装

4. **自动启动**
   - 浏览器自动打开 http://localhost:8501
   - 开始使用！

### Linux/Mac 用户

1. **下载项目**
   ```bash
   git clone https://github.com/hsliuping/TradingAgents-CN.git
   cd TradingAgents-CN
   ```

2. **运行安装脚本**
   ```bash
   chmod +x scripts/easy_install.sh
   ./scripts/easy_install.sh
   ```

3. **按照提示操作**
   - 选择LLM提供商
   - 输入API密钥
   - 等待自动安装

4. **自动启动**
   - 浏览器自动打开 http://localhost:8501
   - 开始使用！

## 📊 开始分析

### 1. 输入股票代码

在Web界面输入股票代码：

```
# A股示例
000001  # 平安银行
600519  # 贵州茅台

# 美股示例
AAPL    # 苹果
TSLA    # 特斯拉
```

### 2. 选择分析深度

- **快速分析** (2-4分钟)：日常监控
- **标准分析** (6-10分钟)：推荐使用 ⭐
- **深度分析** (15-25分钟)：重要决策

### 3. 开始分析

点击"🚀 开始分析"按钮，等待分析完成。

### 4. 查看结果

- 投资建议（买入/持有/卖出）
- 置信度评分
- 风险评估
- 详细分析报告

### 5. 导出报告（可选）

支持导出为：
- Markdown（在线查看）
- Word（编辑修改）
- PDF（打印分享）

## 🔧 日常使用

安装完成后，日常使用非常简单：

### Windows

```powershell
# 双击运行
.\start_simple.bat

# 或使用命令行
python start_web.py
```

### Linux/Mac

```bash
# 运行启动脚本
./start_simple.sh

# 或使用命令行
python start_web.py
```

## 🆘 遇到问题？

### 问题1：Python版本过低

```bash
# 下载最新Python
https://www.python.org/downloads/
```

### 问题2：网络连接失败

```bash
# 检查网络
ping api.deepseek.com

# 或切换其他LLM提供商
```

### 问题3：API密钥无效

```bash
# 验证API密钥
python scripts/validate_api_keys.py

# 重新配置
powershell -ExecutionPolicy Bypass -File scripts\easy_install.ps1 -Reconfigure
```

### 问题4：端口被占用

```bash
# 修改端口（在.env文件中）
STREAMLIT_PORT=8502
```

### 系统诊断

运行诊断脚本检查所有问题：

```bash
python scripts/diagnose_system.py
```

## 💡 使用技巧

### 技巧1：批量分析

在输入框中输入多个股票代码（逗号分隔）：

```
000001, 600519, 300750
```

### 技巧2：快速切换模型

在侧边栏可以快速切换不同的LLM模型，无需重启。

### 技巧3：保存常用配置

系统会自动记住您的配置选择，下次使用更方便。

### 技巧4：离线使用

提前缓存数据后，可以在无网络环境下使用：

```bash
python scripts/prefetch_stock_data.py 000001 600519
```

## 📚 进阶学习

### 了解更多功能

- [完整文档](./docs/)
- [配置指南](./docs/configuration/)
- [API文档](./docs/api/)
- [常见问题](./docs/faq/faq.md)

### 个人用户详细指南

- [简化部署指南](./docs/SIMPLE_DEPLOYMENT_GUIDE.md)

### 专业用户

- [Docker部署](./README.md#-docker部署-推荐)
- [开发指南](./docs/DEVELOPMENT_SETUP.md)
- [架构文档](./docs/architecture/)

## 🎯 性能对比

| 部署方式 | 启动时间 | 配置难度 | 适用场景 |
|---------|---------|---------|---------|
| **一键安装** | 10秒 | ⭐ 简单 | 个人用户 |
| **Docker部署** | 30秒 | ⭐⭐ 中等 | 有Docker用户 |
| **本地部署** | 60秒 | ⭐⭐⭐ 复杂 | 开发者 |

## 🆘 获取帮助

- **GitHub Issues**: [提交问题](https://github.com/hsliuping/TradingAgents-CN/issues)
- **QQ群**: 782124367
- **邮箱**: hsliup@163.com

## ⚠️ 重要提示

1. **投资风险**：本工具仅供研究和教育目的，不构成投资建议
2. **API成本**：使用LLM API会产生费用，请注意控制成本
3. **数据准确性**：数据来源于第三方，请以官方数据为准
4. **网络要求**：需要稳定的网络连接访问API

---

**🎉 祝您使用愉快！**

如果觉得有用，请给我们一个 ⭐ Star！

