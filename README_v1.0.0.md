# TradingAgents-CN v1.0.0-preview

[![License](https://img.shields.io/badge/License-Mixed-blue.svg)](./LICENSING.md)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Version](https://img.shields.io/badge/Version-v1.0.0--preview-orange.svg)](./VERSION)
[![Documentation](https://img.shields.io/badge/docs-中文文档-green.svg)](./docs/v1.0.0-preview/)
[![Original](https://img.shields.io/badge/基于-TauricResearch/TradingAgents-orange.svg)](https://github.com/TauricResearch/TradingAgents)

> 🚀 **基于多智能体大语言模型的中文金融交易决策框架**
> 
> 专为中文用户优化，提供完整的A股/港股/美股分析能力

## ✨ v1.0.0-preview 核心特性

### 🎯 全新架构

- **前后端分离架构**: Vue 3 + FastAPI，现代化的Web应用架构
- **实时进度跟踪**: SSE/WebSocket双通道，实时查看分析进度
- **智能任务调度**: 支持单股分析、批量分析、定时任务
- **专业报告系统**: 9大模块完整报告，支持多格式导出

### 🤖 多智能体系统

- **7个专业智能体**: 分析师、研究员、交易员、风险管理、新闻分析等
- **5级分析深度**: 从快速概览到深度研究，灵活选择
- **智能协作机制**: 辩论、反思、记忆系统，确保分析质量

### 📊 实时数据支持

- **实时PE/PB计算**: 基于30秒更新的实时行情，数据实时性提升2880倍
- **多数据源支持**: Tushare、AKShare、东方财富等
- **智能缓存系统**: Redis + 本地缓存，提升性能

### 🔧 强大的配置系统

- **多LLM支持**: OpenAI、DeepSeek、Google AI、通义千问等
- **灵活配置**: 环境变量、配置文件、数据库配置三级管理
- **成本优化**: 智能模型选择，降低使用成本

### 🎨 现代化Web界面

- **响应式设计**: 适配桌面和移动设备
- **实时更新**: 自动刷新数据，无需手动操作
- **丰富的可视化**: 图表、表格、卡片等多种展示方式

## 🚀 快速开始

### 方式一：Docker部署（推荐）

```bash
# 1. 克隆仓库
git clone https://github.com/hsliuping/TradingAgents-CN.git
cd TradingAgents-CN

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，配置你的API密钥

# 3. 启动服务
docker-compose up -d

# 4. 访问应用
# 前端: http://localhost:5173
# 后端API: http://localhost:8000
# API文档: http://localhost:8000/docs
```

### 方式二：本地开发部署

```bash
# 1. 克隆仓库
git clone https://github.com/hsliuping/TradingAgents-CN.git
cd TradingAgents-CN

# 2. 安装Python依赖
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 文件

# 4. 启动MongoDB和Redis
docker-compose up -d mongodb redis

# 5. 启动后端
python -m uvicorn app.main:app --reload

# 6. 启动前端（新终端）
cd frontend
npm install
npm run dev

# 7. 访问应用
# 前端: http://localhost:5173
# 后端API: http://localhost:8000
```

## 📚 文档导航

### 快速入门

- [快速开始指南](docs/v1.0.0-preview/01-overview/02-quick-start.md) - 5分钟快速上手
- [安装指南](docs/v1.0.0-preview/01-overview/03-installation.md) - 详细安装步骤
- [完整使用手册](docs/v1.0.0-preview/04-features/USER_MANUAL.md) - 用户使用指南

### 架构设计

- [系统架构](docs/v1.0.0-preview/02-architecture/01-system-architecture.md) - 整体架构设计
- [多智能体架构](docs/v1.0.0-preview/02-architecture/02-agent-architecture.md) - 智能体协作机制
- [数据流架构](docs/v1.0.0-preview/02-architecture/03-data-flow-architecture.md) - 数据处理流程

### 功能特性

- [股票分析](docs/v1.0.0-preview/04-features/01-stock-analysis.md) - 单股和批量分析
- [智能筛选](docs/v1.0.0-preview/04-features/02-screening.md) - 多维度股票筛选
- [报告生成](docs/v1.0.0-preview/04-features/03-reports.md) - 专业报告导出

### 开发指南

- [开发指南](docs/v1.0.0-preview/06-development/01-development-guide.md) - 开发环境配置
- [API参考](docs/v1.0.0-preview/05-api-reference/01-rest-api.md) - REST API文档
- [贡献指南](docs/v1.0.0-preview/06-development/04-contributing.md) - 如何贡献代码

### 部署运维

- [Docker部署](docs/v1.0.0-preview/07-deployment/01-docker-deployment.md) - 容器化部署
- [生产环境部署](docs/v1.0.0-preview/07-deployment/02-production-deployment.md) - 生产环境配置
- [故障排除](docs/v1.0.0-preview/07-deployment/05-troubleshooting.md) - 常见问题解决

## 🎯 核心功能

### 1. 股票分析

- **单股深度分析**: 5级分析深度，从快速概览到深度研究
- **批量分析**: 支持批量处理多只股票，自动生成对比报告
- **实时进度**: SSE实时推送分析进度，随时了解分析状态

### 2. 智能筛选

- **多维度筛选**: 基本面、技术面、估值等多维度筛选条件
- **预设策略**: 价值投资、成长投资、技术分析等预设策略
- **自定义条件**: 灵活组合筛选条件，满足个性化需求

### 3. 报告生成

- **9大报告模块**: 
  - 执行摘要 (Executive Summary)
  - 关键指标 (Key Metrics)
  - 基本面分析 (Fundamental Analysis)
  - 技术分析 (Technical Analysis)
  - 估值分析 (Valuation Analysis)
  - 风险评估 (Risk Assessment)
  - 新闻分析 (News Analysis)
  - 研究团队决策 (Research Team Decision)
  - 风险管理决策 (Risk Management Decision)

- **多格式导出**: JSON、Markdown、PDF等多种格式
- **自定义模板**: 支持自定义报告模板和样式

### 4. 任务管理

- **任务队列**: 自动管理分析任务，支持优先级调度
- **任务监控**: 实时查看任务状态、进度、日志
- **任务历史**: 完整的任务历史记录和结果查询

### 5. 用户管理

- **多用户支持**: 支持多用户注册、登录、权限管理
- **个人空间**: 每个用户独立的分析历史和收藏夹
- **权限控制**: 灵活的角色和权限管理

## 🔧 技术栈

### 后端

- **框架**: FastAPI 0.104+
- **语言**: Python 3.10+
- **数据库**: MongoDB 4.4+
- **缓存**: Redis 7.0+
- **任务队列**: Celery + Redis
- **LLM**: OpenAI、DeepSeek、Google AI等

### 前端

- **框架**: Vue 3.4+
- **UI库**: Element Plus 2.4+
- **状态管理**: Pinia
- **路由**: Vue Router 4
- **HTTP客户端**: Axios
- **构建工具**: Vite 5

### 数据源

- **Tushare**: 主要数据源，提供完整的A股数据
- **AKShare**: 补充数据源，提供实时行情
- **东方财富**: 新闻和公告数据

## 📊 系统要求

### 最低配置

- **CPU**: 2核
- **内存**: 4GB
- **磁盘**: 20GB
- **网络**: 稳定的互联网连接

### 推荐配置

- **CPU**: 4核+
- **内存**: 8GB+
- **磁盘**: 50GB+ SSD
- **网络**: 高速互联网连接

## 🤝 贡献

欢迎贡献代码、报告问题、提出建议！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

详见 [贡献指南](docs/v1.0.0-preview/06-development/04-contributing.md)

## 📄 许可证

本项目采用混合许可证模式：

- **开源组件**: Apache 2.0 License
- **专有组件**: Proprietary License（个人免费，商业需授权）

详见 [LICENSING.md](LICENSING.md)

## 🙏 致谢

- 感谢 [Tauric Research](https://github.com/TauricResearch) 团队创造的原始框架
- 感谢所有贡献者的辛勤付出
- 感谢开源社区的支持

## 📞 联系方式

- **GitHub Issues**: https://github.com/hsliuping/TradingAgents-CN/issues
- **QQ群**: 782124367
- **邮箱**: hsliup@163.com

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=hsliuping/TradingAgents-CN&type=Date)](https://star-history.com/#hsliuping/TradingAgents-CN&Date)

---

**开始使用**: [快速开始指南](docs/v1.0.0-preview/01-overview/02-quick-start.md) →

