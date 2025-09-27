# 配置方案A（分层集中式）与数据库配置治理

本文档定义运行时配置的“单一事实来源（SoT）”、优先级、边界与迁移路线，适用于 app 与 tradingagents 两侧。

## 一、优先级与职责边界

优先级（高 → 低）：
1) 请求级覆盖（仅本次请求生效）
2) 用户/租户偏好（DB）
3) 系统运营参数（DB：system_configs、market_categories、datasource_groupings、llm_providers 等）
4) 环境变量/.env（Pydantic Settings，含密钥与基础设施连接）
5) 代码默认值（default_*）

职责划分：
- 环境变量/.env：Mongo/Redis/队列/加密密钥、第三方 API Key 等敏感/基础设施项
- 数据库：运营/动态参数（开关、阈值、优先级、默认项）与目录数据（分类、分组、厂家）
- 代码默认：开发兜底默认

## 二、SoT 模式开关

Settings.CONFIG_SOT: file|db|hybrid
- file：以文件/env 为准（推荐，生产缺省）
- db：以数据库为准（仅兼容旧版，不推荐）
- hybrid：文件/env 优先，DB 兜底

## 三、敏感信息策略

- API 响应一律对敏感项脱敏（api_key/api_secret/password 等）
- REST 写入不接受敏感字段（清空/忽略），密钥统一来自环境变量或厂家目录
- 导出配置（export）时对敏感项清空；导入（import）忽略敏感项
- 生产环境不在 DB 持久化明文密钥；仅记录 has_key 与 source（environment/db）

## 四、读取与合并

- 读取顺序：env → DB（系统运营参数/目录数据）→ 用户偏好
- 合并后在统一入口（ConfigProvider/UnifiedConfigManager）返回“生效视图”
- 加入短缓存（30~60s）与版本失效（SystemConfig.version/事件）

## 五、迁移路线

P0：安全与基线
- 文档化方案A与权责矩阵（本文档）
- 清理/屏蔽 DB 中明文密钥（生产）；统一响应脱敏
- 禁止通过 REST 写入密钥；从文件读/写去除 api_key

P1：合并与缓存
- 实现 ConfigProvider（env→DB→用户偏好合并 + 缓存 + 版本失效）
- migrate_env_to_providers：dev 允许写入以便演示；prod 仅标记 has_key
- 写配置操作审计日志

P2：扩展
- 用户/租户偏好优先级接入
- 导入/导出 + 回滚
- 前端配置中心区分“敏感只读/运营可改”

## 六、与 tradingagents 协同

- 短期：tradingagents 复用 app 的配置读取与模型，不重复实现
- 中期：抽取 shared 配置模型与合并逻辑，两侧共同依赖
- 文件（models.json/settings.json）用于导入/导出与本地开发，不作为运行时真相


## 七、执行记录（持续更新）

- 2025-09-27（P0 完成项）
  - API：/config/system、/config/settings 读取端对 system_settings 中敏感键统一脱敏；LLM/数据源/数据库配置读取端继续脱敏
  - 导出：export_config 对 system_settings 敏感键脱敏，导入忽略敏感字段
  - DB 清理：执行 scripts/config/cleanup_sensitive_in_db.py --apply，处理 48 条记录（system_configs 41 条、llm_providers 7 条），清空 api_key/api_secret/password
  - REST 写入：/config 相关写入端清洗敏感字段，禁止密钥落库
  - 审计：为“更新系统设置”写入操作接入操作日志（ActionType.CONFIG_MANAGEMENT）

- 待办（P1 进行中）
  - ConfigProvider：env→DB→用户偏好合并 + 短缓存 + 版本失效
  - 更全面的写入审计覆盖（LLM/数据源/数据库配置增改删）
  - system_settings 中第三方 key/secret 逐步迁移至环境变量，前端仅展示“已配置/来源ENV”状态
