# 快速开始

下面给出一个尽量简洁、适合公开仓库使用的安装与启动流程。

## 1. 前置条件

- Python 3.11+
- Node.js 18+（如果你要启动前端）
- MongoDB 6.0+ 与 Redis 7.0+（建议用于完整后端体验）

## 2. 安装依赖

```bash
git clone <your-repo-url>
cd TradingAgent-Future
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -e .
cp .env.example .env
```

然后编辑 [.env](../.env.example) 中的配置，例如 LLM API Key、数据库地址和数据源 Token。

## 3. 启动后端

```bash
python -m app --reload
```

后端默认监听 http://localhost:8000。

## 4. 启动前端（可选）

```bash
cd frontend
npm install
npm run dev
```

前端默认监听 http://localhost:3000。

## 5. Docker 方式（可选）

```bash
docker compose up -d
```

## 6. 推荐的第一步验证

- 先确认后端能正常启动
- 再确认前端能正常打开
- 最后尝试使用一个简单的分析入口做一次最小测试

## 7. 常见问题

### Q: 我只想体验核心分析能力，但不想部署前端
可以只安装 Python 依赖并启动后端，后续通过 API/CLI 接入即可。

### Q: 我没有 MongoDB / Redis
可以先使用最小配置运行，但完整 Web 功能和任务队列会受到影响。

### Q: 我没有 LLM Key
可以先查看 [.env.example](../.env.example) 中的示例配置并准备好至少一个模型提供商的 Key。

## 8. 下一步

- 查看 [README.md](../README.md) 了解项目结构与许可边界
- 查看 [BUILD_GUIDE.md](BUILD_GUIDE.md) 了解构建与部署细节
- 查看 [ANALYST_DATA_CONFIGURATION.md](ANALYST_DATA_CONFIGURATION.md) 了解数据配置
