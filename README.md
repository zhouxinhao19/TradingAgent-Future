# TradingAgent-Future

**多智能体期货交易分析平台** — 基于 LangGraph + LangChain 构建的多智能体协作框架，专注于大宗商品期货的深度分析。

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-teal.svg)](https://fastapi.tiangolo.com/)
[![Vue 3](https://img.shields.io/badge/Vue-3.5-4FC08D.svg)](https://vuejs.org/)

---

## 项目简介

TradingAgent-Future 是一个多智能体期货交易分析平台，通过多个专业化 AI 智能体（分析师、研究员、交易员、风控官、CIO）的协作，对期货标的进行全方位深度分析并生成决策报告。

### 核心能力

- **多智能体辩论决策** — 看涨/看跌研究员辩论 → 研究经理汇总 → 交易员决策 → 多层风控 → CIO 终审的完整决策链
- **大宗商品期货覆盖** — 6 大交易所 80+ 品种（黑色系、有色、能源化工、农产品、金融期货、贵金属）
- **多维度分析** — 技术面、基本面、持仓分析、期限结构、基差、库存、新闻情绪
- **灵活 LLM 接入** — 支持 DeepSeek、OpenAI、Qwen（通义千问）、GLM（智谱）、Google Gemini、Anthropic Claude、Ollama 等多种模型
- **多级数据源** — AKShare → Tushare → BaoStock 多级降级链，确保数据可用性
- **流式更新** — SSE + WebSocket 实时推送分析进度

### 架构示意

```
┌─────────────────────────────────────────────────────────────┐
│                    TradingAgentsGraph                        │
├──────────┬──────────┬──────────┬──────────┬─────────────────┤
│ Analysts │Researchers│ Managers │  Trader  │  Risk Mgmt + CIO│
│ (4-6个)  │ (多空)   │ (汇总)   │ (决策)   │  (风控+审计)    │
├──────────┴──────────┴──────────┴──────────┴─────────────────┤
│                   tradingagents/ 核心引擎                     │
├──────────────────────────────────┬──────────────────────────┤
│           FastAPI 后端           │      Vue 3 前端           │
│       (app/ 专有组件)            │   (frontend/ 专有组件)   │
└──────────────────────────────────┴──────────────────────────┘
```

---

## 快速开始

### 环境要求

- Python 3.11+
- MongoDB 6.0+
- Redis 7.0+
- Node.js 18+（仅前端构建需要）

### 安装

```bash
# 克隆仓库
git clone <your-repo-url>
cd TradingAgent-Future

# 安装 Python 依赖
pip install -e .

# 安装前端依赖
cd frontend && npm install && cd ..

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入你的 API 密钥（LLM、数据源等）
```

### 启动

```bash
# 启动后端（开发模式，自动重载）
python -m app --reload

# 启动前端开发服务器
cd frontend && npm run dev
```

访问 `http://localhost:3000` 进入前端界面，后端 API 位于 `http://localhost:8000`。

### Docker 部署

```bash
docker compose up -d
```

也可使用带 Nginx 反向代理的配置：

```bash
docker compose -f docker-compose.hub.nginx.yml up -d
```

---

## 项目结构

```
TradingAgent-Future/
├── tradingagents/          # 核心分析引擎（Apache 2.0 开源）
│   ├── graph/              # LangGraph 图编排（入口：trading_graph.py）
│   ├── agents/             # 多智能体节点（分析师/研究员/交易员/风控/CIO）
│   ├── llm_clients/        # LLM 客户端抽象层（OpenAI/DeepSeek/Qwen/GLM 等）
│   ├── dataflows/          # 数据流引擎 + 多级数据源降级链
│   │   └── providers/      # 数据提供者（股票 / 商品期货）
│   └── tools/              # 数据工具封装
├── app/                    # FastAPI 后端（专有组件）
│   ├── main.py             # FastAPI 入口
│   ├── core/               # 配置、数据库、日志、中间件
│   ├── routers/            # API 路由
│   ├── services/           # 业务服务层
│   └── models/             # MongoDB ODM 模型
├── frontend/               # Vue 3 + Element Plus 前端（专有组件）
│   ├── src/
│   │   ├── views/          # 页面组件
│   │   ├── stores/         # Pinia 状态管理
│   │   ├── api/            # API 封装
│   │   └── components/     # 通用组件
│   └── ...
├── cli/                    # 交互式 CLI 工具
├── tests/                  # 测试（pytest）
├── docs/                   # 完整文档目录
└── docker/                 # Docker 部署配置
```

---

## 文档

完整文档位于 [docs/](docs/) 目录，涵盖：

| 分类 | 内容 |
|------|------|
| 入门指南 | 安装部署、快速开始 |
| 架构设计 | 系统架构、数据流设计 |
| 配置管理 | 配置指南、LLM 配置 |
| 分析能力 | 期货分析、新闻分析 |
| Docker 部署 | 部署指南 |
| 开发扩展 | 新增数据源、API 规范 |

---

## 许可证

本项目采用 **混合许可证** 模式：

| 组件 | 许可证 | 说明 |
|------|--------|------|
| `tradingagents/` | **Apache 2.0** | 核心引擎，可自由使用和修改 |
| `app/` | **专有** | FastAPI 后端，商业使用需单独授权 |
| `frontend/` | **专有** | Vue 3 前端，商业使用需单独授权 |
| `cli/` | **Apache 2.0** | CLI 工具，可自由使用 |

详见 [LICENSE](LICENSE) 和 [LICENSING.md](LICENSING.md)。

---

## 致谢

- [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) — 上游多智能体交易框架
- [AKShare](https://github.com/akfamily/akshare) — 开源证券数据接口
- [Tushare](https://tushare.pro/) — 金融大数据平台
- [BaoStock](https://baostock.com/) — 证券数据服务

---

> **风险声明**：本框架**仅用于研究与教学**，**不构成投资建议**。所有分析结果仅供参考，实际投资决策需自行判断。