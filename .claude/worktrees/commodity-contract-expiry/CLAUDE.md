# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 回复约定

- 始终使用中文回复（见 `~/.claude/CLAUDE.md` 用户全局指令）。
- 当前日期：2026-07-13。

---

## 项目概览

**TradingAgents-CN** 是面向中文用户的多智能体股票分析学习平台，基于 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) 多智能体交易框架改造，采用 Apache 2.0 + 专有组件的混合许可证。当前版本 `v1.0.1`（见根目录 `VERSION`）。

**注意**：
- `app/`（FastAPI 后端）和 `frontend/`（Vue 前端）属于**专有组件**，商业使用需单独授权（`app/LICENSE`、`frontend/LICENSE`）。
- 项目组未给任何组织或个人进行过商业授权，注意识别侵权网站。

---

## 代码架构

项目分三大子系统：**核心分析引擎**（Apache 2.0）、**专有后端**（FastAPI）、**专有前端**（Vue 3）。

### 1. `tradingagents/` — 核心分析引擎（开源）

LangGraph + LangChain 驱动的多智能体编排，初始化入口是 `tradingagents/graph/trading_graph.py:TradingAgentsGraph`。

```
tradingagents/
├── default_config.py          # DEFAULT_CONFIG：llm_provider/debate_rounds/online_tools
├── llm_clients/               # ⭐ 新版 LLM 抽象层（v1.0.1 主链路）
│   ├── factory.py             # create_llm_client(provider, model, base_url, ...) 派发
│   ├── base_client.py         # BaseLLMClient + normalize_content
│   ├── openai_client.py       # 兼容 openai/deepseek/qwen/glm/qianfan/openrouter/aihubmix/ollama/custom_openai/siliconflow
│   ├── google_client.py
│   ├── anthropic_client.py
│   ├── model_catalog.py       # 共享模型目录（轻量校验）
│   ├── provider_keys.py       # normalize_provider_key / env_key_for_provider / default_backend_url
│   └── validators.py
├── llm_adapters/              # 旧版兼容性 OpenAI 兼容适配器（dashscope/deepseek/google）
├── graph/
│   ├── trading_graph.py       # TradingAgentsGraph 主类 + create_llm_by_provider()
│   ├── setup.py               # GraphSetup 节点/边装配
│   ├── conditional_logic.py   # ConditionalLogic 多智能体路由条件
│   ├── propagation.py         # Propagator 状态传播
│   ├── reflection.py          # Reflector.reflect_and_remember()（注释掉，未启用）
│   └── signal_processing.py   # SignalProcessor
├── agents/                    # 多智能体（按角色分目录）
│   ├── analysts/              # market/news/social_media/fundamentals/china_market
│   ├── researchers/           # bull/bear
│   ├── risk_mgmt/             # aggressive/conservative/neutral debator
│   ├── managers/              # research_manager/risk_manager
│   ├── trader/                # trader
│   └── utils/                 # Toolkit/AgentState/InvestDebateState/RiskDebateState/memory
├── dataflows/
│   ├── interface.py           # set_config() + 多市场统一接口
│   ├── data_source_manager.py # 中国市场主调度（AKShare/Tushare/BaoStock 多级降级链）
│   ├── optimized_china_data.py
│   ├── realtime_metrics.py
│   ├── providers/{china,hk,us,examples}/  # 按市场分目录的 provider
│   ├── cache/{file_cache,db_cache,mongodb_cache_adapter,integrated,adaptive,app_adapter}.py
│   └── news/, technical/
├── tools/                     # 数据工具（YFinance/Tushare/AKShare 等 wrapper）
├── api/                       # YAML 化的多智能体能力 API
├── config/, constants/, models/
└── utils/logging_init.py      # get_logger() 统一日志入口
```

**关键调用链**：
```
main.py → TradingAgentsGraph(config).propagate(ticker, date)
  → GraphSetup.set_graph(...)
  → Propagator.astream/graph.stream(...) 推进 AgentState
  → 各 analyst/researcher/manager/risk_mgmt/trader 节点
  → SignalProcessor.process_signal() 输出最终决策
```

### 2. `app/` — FastAPI 后端（专有，Apache 2.0 之外）

`app/main.py` 是 FastAPI 应用入口，路由前缀大部分以 `/api` 开头。在 `app/__main__.py`（`python -m app`）启动时设置全局 UTF-8 编码并打印配置摘要。

```
app/
├── main.py                    # FastAPI app + lifespan + 全部 include_router
├── __main__.py                # python -m app 入口（UTF-8/uvicorn 配置）
├── core/
│   ├── config.py              # Pydantic Settings，单一 settings 对象
│   ├── dev_config.py          # DEV_CONFIG.get_uvicorn_config()
│   ├── database.py            # MongoDB（motor）+ Redis 客户端管理
│   ├── redis_client.py
│   ├── unified_config.py      # 统一配置层（数据库优先，否则回退 .env）
│   ├── config_bridge.py       # bridge_config_to_env() 把 DB 配置写入 os.environ 供 tradingagents 使用
│   ├── logging_config.py      # setup_logging()
│   ├── startup_validator.py
│   ├── rate_limiter.py
│   └── response.py            # 统一响应封装
├── routers/                   # 每个领域一个 router 文件（详细列表见 app/main.py 第 31-40 行）
│   ├── auth_db.py, analysis.py, screening.py, queue.py, sse.py, health.py, ...
│   ├── websocket_notifications.py, scheduler.py, multi_source_sync.py
│   └── tushare_init.py / akshare_init.py / baostock_init.py  # 数据源初始化路由
├── services/
│   ├── analysis_service.py / simple_analysis_service.py / queue_service.py
│   ├── config_service.py / config_provider.py
│   ├── scheduler_service.py / quotes_service.py / quotes_ingestion_service.py
│   ├── multi_source_basics_sync_service.py
│   ├── websocket_manager.py / redis_progress_tracker.py
│   └── progress/, screening/, data_sources/ ... 子包
├── models/                    # MongoDB ODM（Pydantic v2）
├── middleware/operation_log_middleware.py
├── worker/                    # Tushare/AKShare/BaoStock 同步 worker
├── worker.py                  # 后台 worker 进程入口
├── scripts/                   # 一次性运维脚本（密码迁移、配置导出等）
└── utils/                     # 报告导出（Markdown/Word/PDF）、错误格式化、时区
```

**后端启动约定**：
- 启动顺序：`init_db()` → `bridge_config_to_env()` → `setup_logging()` → 启动 `AsyncIOScheduler` → 注册 Tushare/AKShare/BaoStock 同步 cron + 实时行情入库 job。
- 数据库/Redis 配置在 `.env` 中读取，LLM 与数据源配置走 `services/config_service.py` + `unified_config.py` 持久化到 MongoDB，并通过 `config_bridge.py` 回写到环境变量供 `tradingagents` 核心库读取。
- MongoDB 数据库命名受 `MONGODB_DATABASE_SCOPE=auto|fixed|instance` 控制（实例隔离开发），`ALLOW_SHARED_DB_IN_DEBUG=false` 默认禁止共享库。

### 3. `frontend/` — Vue 3 + Element Plus 前端（专有）

`package.json` 中 scripts:
- `dev` / `build` / `preview` / `lint` / `format` / `type-check`

```
frontend/src/
├── api/                       # axios 封装，按后端路由分文件
├── components/{Global,Layout}/
├── views/                     # 页面级组件（每个功能域一个目录）
├── stores/                    # Pinia
├── router/
├── layouts/, constants/, styles/, types/, utils/
├── App.vue, main.ts
└── test-import.js
```

`vite.config.ts` 配置了路径别名 `@`、`@components`、`@views`、`@stores`、`@utils`、`@types`、`@api`，并启用了 `unplugin-auto-import` 和 `ElementPlusResolver` 自动按需导入。

### 4. `cli/main.py` — 交互式 CLI（开源）

基于 `questionary` + `rich` 的多步交互式 CLI（10万字符级别的体量）。子命令：`akshare_init.py`、`baostock_init.py`、`tushare_init.py`、`utils.py`。

### 5. 其他常用目录

- `tests/` — pytest 测试、根目录有 `pytest.ini`（`testpaths = tests`，默认跳过 `-m integration`）；大量 `test_*.py` / `debug_*.py`。
- `scripts/` — 一键运维脚本（Docker 构建、配置初始化、用户初始化、日志诊断等），多有 `.ps1` 和 `.sh` 双版本。
- `docker/`、`docker-compose.yml`、`docker-compose.hub.nginx.yml`、Dockerfile.backend / Dockerfile.frontend、Nginx 反代配置 `nginx/nginx.conf`。
- `install/`、`docs/`（详细分类见 `docs/architecture/`、`docs/deployment/`、`docs/maintenance/upstream-sync.md`）、`examples/`、`config/`、`data/`、`reports/`、`results/`、`logs/`、`assets/`、`images/`。

---

## 常用命令

### 环境与依赖

```bash
# 安装依赖（推荐 uv；也可 pip install -e .）
uv pip install -e .

# 需要时可装千帆可选依赖
uv pip install -e ".[qianfan]"

# 前端依赖
cd frontend && npm install
```

> ⚠️ `requirements.txt` 已弃用（首行注释），请使用 `pyproject.toml`。

### 开发与运行

```bash
# 后端（开发模式，自动重载 + 日志级别 DEBUG）
python -m app --reload    # 或 python -m app.main
# 等价：uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 前端开发服务器（http://localhost:3000，通过 vite.config 端口设置）
cd frontend && npm run dev

# 前端生产构建（vue-tsc 类型检查 + vite build）
cd frontend && npm run build

# 前端 lint / format / 类型检查
cd frontend && npm run lint
cd frontend && npm run format
cd frontend && npm run type-check
```

### Docker 部署（前后端分离 + MongoDB + Redis）

```bash
docker compose up -d                    # 基础三服务
# 或带 Nginx 反向代理 / 多架构镜像：
docker compose -f docker-compose.hub.nginx.yml up -d
# 多架构发布：
./scripts/build-multiarch.sh
```

### CLI / 直接运行多智能体图

```bash
python main.py                                          # 示例调用 TradingAgentsGraph，对 NVDA 做示例分析
python cli/main.py                                      # 交互式 CLI
python examples/basic_example.py                        # 基础示例（见 examples/ 目录）
```

### 测试

```bash
# pytest 默认配置（pytest.ini）：只扫 tests/、跳过 integration 标记
python -m pytest                                        # 全部
python -m pytest tests/test_xxx.py                      # 单文件
python -m pytest tests/test_xxx.py::test_xxx -v         # 单测试
python -m pytest -m integration                          # 显式运行集成测试
python -m pytest -k "config"                            # 按名称筛选

# 调试脚本（tests/debug_*.py）与诊断工具通常需 .env 内配置真实 API key 才能跑通
python tests/debug_docker.py
```

### 上游同步

项目采用**人工选择性吸收**上游 `TauricResearch/TradingAgents` 更新（不再自动 merge）。流程、冲突优先级、清单见：
- `docs/maintenance/upstream-sync.md`
- `docs/maintenance/manual-upstream-absorption-checklist.md`

`.github/workflows/upstream-sync-check.yml` 用于定时检测上游变更。

---

## 关键约定

### LLM 客户端（重要 — v1.0.1 主链路）

新增 LLM 集成时优先接入 `tradingagents/llm_clients/`：

1. 在 `llm_clients/provider_keys.py` 注册 provider 标准化键、别名 (`_ALIASES`)、默认环境变量名 (`env_key_for_provider`)、默认 backend URL (`default_backend_url`)。
2. 在 `llm_clients/factory.py` 的 `_OPENAI_COMPATIBLE` / `google` / `anthropic` 分支加好派发；OpenAI 兼容的可直接复用 `OpenAIClient`。
3. 仅当官方 SDK 非 OpenAI 协议（如未来新增非兼容厂家）才新建 `xxx_client.py`。
4. Provider 命名遵循 canonical key（`qwen`/`glm`），中文名 `阿里百炼`/`智谱` 在 `normalize_provider_key` 中映射。
5. 共享模型目录参考 `llm_clients/model_catalog.py`。

兼容性适配器层（仅历史兼容保留）：`tradingagents/llm_adapters/`。

### 数据源

`tradingagents/dataflows/data_source_manager.py` 实现中国市场多级降级链（AKShare → Tushare → BaoStock）。新增数据源：
- 在 `dataflows/providers/{china,hk,us}/` 新建 provider，继承 `dataflows/providers/base_provider.py`。
- 在 `data_source_manager.py` 注册优先级与降级链。
- 对应的同步 worker 放在 `app/worker/` 和 CLI 初始化脚本 `cli/{akshare,tushare,baostock}_init.py`。
- 单股实时行情降级链：`stock_bid_ask_em → stock_zh_a_spot → stock_zh_a_spot_em → stock_zh_a_hist`。

### 后端路由/服务

- 新增业务模块：在 `app/routers/` 加路由文件 → `app/main.py` 中 `include_router`。
- 服务层放在 `app/services/`，模型 ODM 在 `app/models/`，Pydantic schema 复杂时使用 `app/schemas/`。
- 长时间任务走队列：`app/services/queue_service.py` + Redis 进度跟踪 `redis_progress_tracker.py`。
- 实时通知：SSE（`routers/sse.py`）+ WebSocket（`routers/websocket_notifications.py`，推荐）。
- 异步日志通过 `app/services/progress_log_handler.py` + `app/core/logging_config.py`。

### 日志

统一通过 `tradingagents.utils.logging_init.get_logger("name")` 获取 logger（`tradingagents/graph/__init__.py` 已示范）。后端初始化走 `app/core/logging_config.setup_logging()`。

### 环境变量与配置优先级

`.env`（项目根）→ Pydantic Settings (`app/core/config.py`) → 数据库持久化配置 (`services/config_service.py`、`unified_config.py`) → `config_bridge.py` 回写到 `os.environ` 给 `tradingagents` 读取。运行时应避免在 `tradingagents/` 里硬编码 key。

### 数据库版本隔离 / Provider 规范化

详见 `docs/deployment/database/DB_VERSION_ISOLATION_AND_PROVIDER_NORMALIZATION.md`。

---

## CI/CD

- `.github/workflows/docker-publish.yml`：tag `v*` 推送时构建并推送多架构（amd64+arm64）backend/frontend 镜像到 Docker Hub。
- `.github/workflows/upstream-sync-check.yml`：上游变更检测。

## 风险与免责

本框架**仅用于研究与教学**，**不构成投资建议**。本项目主要负责人：hsliuping；官方邮箱 `hsliup@163.com`，微信公众号 `TradingAgents-CN`。

---

## 当前进行中的任务

按 [`docs/plans/stock-to-commodity.md`](docs/plans/stock-to-commodity.md) 推进 **"股票 → 大宗商品"改造**。

- **当前阶段**：Phase 0 - 抽象统一（未开始）
- **关键约束**：
  - 开发期间**股票/商品并存**，每个 Phase 都能 `docker compose up` 跑通
  - **Feature Flag 渐进开启**：4 个 `FEATURE_COMMODITY_*` 默认全 `false`，完成后翻 `true` 即可演示
  - 进度产出：`docs/progress/phase-N.md` + 截图
  - 新建模块统一用 `commodity_*` 前缀，与 `stock_*` 隔离
- **下次启动第一句话**：直接说"继续 Phase 0"即可
- **迁移说明**：plan 原文已从 `~/.claude/plans/encapsulated-forging-hoare.md` 移到本仓库 `docs/plans/stock-to-commodity.md`，跨机器可用
