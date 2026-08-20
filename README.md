# TradingAgent-Future

TradingAgent-Future 是一个面向中文用户的多智能体期货分析平台，基于 LangGraph、LangChain 与多角色智能体协作，聚焦于大宗商品期货的研究、分析与决策支持。

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-Mixed%20License-blue.svg)](LICENSE)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-teal.svg)](https://fastapi.tiangolo.com/)
[![Vue 3](https://img.shields.io/badge/Vue-3.5-4FC08D.svg)](https://vuejs.org/)

---

## 项目定位

这个仓库同时包含两类内容：

- 开源核心引擎：位于 [tradingagents](tradingagents) 和 [cli](cli)，用于多智能体分析、数据流编排、LLM 适配与研究流程。
- Web 应用层：位于 [app](app) 与 [frontend](frontend)，提供 FastAPI 后端和 Vue 3 前端体验。它们采用专有许可，适合内部评估或学习使用。

如果你想快速体验“分析能力”，建议先从核心引擎和 CLI 开始；如果你想查看完整 Web 界面，则需要同时部署后端与前端。

---

## 核心能力

- 多智能体决策链：研究员辩论 → 研究经理汇总 → 交易员决策 → 风控审核 → CIO 终审
- 期货覆盖面广：支持 6 大交易所、80+ 品种的商品期货分析
- 多维分析能力：技术面、基本面、持仓、基差、库存、期限结构、新闻情绪
- 多 LLM 支持：DeepSeek、OpenAI、Qwen、GLM、Gemini、Claude、Ollama 等
- 数据源降级链：AKShare → Tushare → BaoStock，提升可用性
- 实时进度反馈：支持 SSE/WebSocket 推送

---

## 快速开始

### 1. 环境要求

- Python 3.11+
- Node.js 18+（仅前端构建需要）
- MongoDB 6.0+ 与 Redis 7.0+（建议用于完整后端体验）

### 2. 安装

```bash
git clone https://github.com/zhouxinhao19/TradingAgent-Future.git
cd TradingAgent-Future
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -e .
cp .env.example .env
```

然后根据需要编辑 [.env](.env.example) 中的 LLM Key、数据库配置与数据源配置。

### 3. 启动后端

```bash
python -m app --reload
```

默认后端会在 http://localhost:8000 提供 API。

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端默认在 http://localhost:3000。

### 5. Docker 方式（可选）

```bash
docker compose up -d
```

---

## 项目结构

```text
TradingAgent-Future/
├── tradingagents/      # 核心分析引擎（Apache 2.0）
├── app/                # FastAPI 后端（专有）
├── frontend/           # Vue 3 前端（专有）
├── cli/                # CLI 工具
├── tests/              # pytest 测试
├── docs/               # 文档中心
├── docker/             # Docker 配置
└── pyproject.toml      # Python 工程配置
```

---

## 文档

建议按以下顺序阅读：

1. [docs/QUICK_START.md](docs/QUICK_START.md) – 先完成安装与启动
2. [docs/README.md](docs/README.md) – 查看文档地图
3. [docs/BUILD_GUIDE.md](docs/BUILD_GUIDE.md) – 了解构建与部署
4. [docs/ANALYST_DATA_CONFIGURATION.md](docs/ANALYST_DATA_CONFIGURATION.md) – 配置分析数据源

---

## 贡献方式

欢迎提交 issue、修复、文档改进或功能建议。请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 了解开发流程与提交规范。

---

## 安全与隐私

请勿将真实的 API Key、访问令牌、数据库密码或私有服务地址提交到仓库。更多说明请见 [SECURITY.md](SECURITY.md)。

---

## 许可证

项目采用混合许可证：

| 组件 | 许可证 |
|------|--------|
| tradingagents / cli | Apache 2.0 |
| app / frontend | 专有许可证 |

详情请见 [LICENSE](LICENSE)、[LICENSING.md](LICENSING.md) 与目录下各自的许可证文件。

---

## 免责声明

本项目仅用于研究、学习与技术交流，不构成投资建议。所有分析结果仅供参考，最终决策需由用户自行判断。