# 更新日志 | Changelog

本文档记录了 TradingAgents 中文增强版的所有重要更改。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
并且本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.1.1] - 2025-06-26

### 🎉 首个预览版本 | First Preview Release

#### ✨ 新增功能 | Added Features

**🇨🇳 阿里百炼大模型集成**

- 完整的ChatDashScope适配器实现
- 支持qwen-turbo、qwen-plus、qwen-max模型
- 优化的中文理解和生成能力
- 与LangChain框架完美兼容

**🏗️ 项目结构重构**

- 创建规范的examples/目录存放演示程序
- 创建tests/目录存放测试程序
- 按功能分类组织子目录
- 添加完整的Python包结构

**🖥️ CLI工具中文化**

- 完整的中文用户界面
- 双语命令说明和帮助信息
- 中文错误提示和用户引导
- 新增config、version、examples、test、help命令

**📚 示例程序**

- demo_dashscope_chinese.py: 中文优化的股票分析演示
- demo_dashscope.py: 完整功能演示
- demo_dashscope_simple.py: 简化测试版本
- demo_dashscope_no_memory.py: 无记忆版本
- demo_openai.py: OpenAI模型演示

**🧪 测试系统**

- 集成测试框架
- 阿里百炼连接测试
- LangChain适配器测试
- 自动化测试脚本

#### 📊 项目统计 | Project Statistics

- **新增文件**: 27个
- **代码行数**: +2720行
- **支持的LLM**: 阿里百炼、OpenAI、Anthropic、Google AI
- **示例程序**: 6个
- **测试覆盖**: 集成测试

#### ⚠️ 预览版本说明 | Preview Version Notes

- 这是一个早期预览版本，功能仍在完善中
- 建议在测试环境中使用
- 欢迎反馈问题和建议
- 后续版本可能包含破坏性更改

## [未发布] | Unreleased

### 计划中 | Planned

- 中国股票市场支持（A股、港股、新三板）
- 中文数据源集成（Tushare、AkShare、Wind）
- 更多国产大语言模型支持（文心一言、智谱清言）
- 中文金融术语和表达优化
- 监管合规功能（风险提示、免责声明）
- 私有化部署支持

## [0.1.0-cn] - 2025-06-26 (历史版本)

### 新增

- ✅ **完整的中文文档体系**

  - 项目概述和快速开始指南
  - 详细的安装说明文档
  - 系统架构和设计文档
  - 智能体架构详细说明
  - 数据流处理架构文档
  - LangGraph 图结构设计说明
- ✅ **智能体详细文档**

  - 分析师团队设计和实现
  - 研究员团队和辩论机制
  - 交易员智能体决策流程
  - 风险管理智能体设计
  - 管理层智能体协调机制
- ✅ **数据处理文档**

  - 支持的数据源和API集成
  - 数据获取、清洗和处理流程
  - 多层缓存策略和优化
- ✅ **配置和使用指南**

  - 详细的配置选项说明
  - LLM模型配置和优化
  - 基础使用示例（8个实用示例）
  - 高级使用示例和扩展开发
- ✅ **帮助和支持文档**

  - 常见问题解答（FAQ）
  - 故障排除指南
  - 贡献指南和开发规范
- ✅ **项目管理文件**

  - 中文版 README.md
  - 贡献指南 (CONTRIBUTING.md)
  - 更新日志 (CHANGELOG.md)
  - 文档结构说明

### 改进

- 🔄 **文档组织结构**

  - 按功能模块组织文档
  - 清晰的导航和索引
  - 丰富的代码示例和图表
- 🔄 **用户体验优化**

  - 详细的安装和配置说明
  - 从入门到高级的学习路径
  - 实用的故障排除指南

### 基于

- **原始项目**: [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)
- **许可证**: Apache 2.0
- **开发语言**: Python 3.10+
- **核心框架**: LangChain, LangGraph

## [原始版本] - TauricResearch/TradingAgents

### 核心功能

- 🤖 多智能体协作架构
- 📊 多数据源集成（FinnHub、Yahoo Finance、Reddit、Google News）
- 🧠 多LLM支持（OpenAI、Anthropic、Google AI）
- 📈 专业化分析师团队
- 🔬 结构化研究员辩论
- 💼 智能交易决策
- 🛡️ 多层风险管理
- ⚡ 高性能并行处理

### 智能体系统

- **分析师团队**: 基本面、技术面、新闻面、社交媒体分析师
- **研究员团队**: 看涨/看跌研究员辩论机制
- **交易员**: 综合决策制定
- **风险管理**: 多角度风险评估

### 技术特性

- **实时数据处理**: 支持实时市场数据分析
- **灵活配置**: 高度可定制的智能体行为
- **缓存优化**: 智能缓存减少API调用成本
- **错误处理**: 完善的错误处理和重试机制

## 版本说明

### 版本号格式

我们使用语义化版本号：`主版本号.次版本号.修订号-标识符`

- **主版本号**: 不兼容的API修改
- **次版本号**: 向下兼容的功能性新增
- **修订号**: 向下兼容的问题修正
- **标识符**:
  - `cn`: 中文增强版标识
  - `alpha`: 内测版本
  - `beta`: 公测版本
  - `rc`: 发布候选版本

### 更新类型说明

- **新增 (Added)**: 新功能
- **改进 (Changed)**: 对现有功能的更改
- **弃用 (Deprecated)**: 即将移除的功能
- **移除 (Removed)**: 已移除的功能
- **修复 (Fixed)**: Bug修复
- **安全 (Security)**: 安全相关的修复

## 贡献者

感谢所有为 TradingAgents 中文增强版做出贡献的开发者：

### 核心团队

- [@hsliuping](https://github.com/hsliuping) - 项目发起人，文档架构师

### 贡献者

- 欢迎更多贡献者加入！

### 特别感谢

- [Tauric Research](https://github.com/TauricResearch) - 原始项目开发团队
- 所有提供反馈和建议的用户

## 路线图

### 短期目标 (1-3个月)

- [ ]  完善现有文档的细节
- [ ]  添加更多使用示例
- [ ]  集成第一个中文数据源 (Tushare)
- [ ]  支持第一个国产LLM (文心一言)

### 中期目标 (3-6个月)

- [ ]  完整的中国市场支持
- [ ]  多个中文数据源集成
- [ ]  多个国产LLM支持
- [ ]  性能优化和稳定性改进

### 长期目标 (6-12个月)

- [ ]  企业级功能和部署支持
- [ ]  高级量化分析功能
- [ ]  实时交易系统集成
- [ ]  移动端和Web界面

## 反馈和建议

我们非常重视用户的反馈和建议：

- **GitHub Issues**: [提交问题和建议](https://github.com/hsliuping/TradingAgents-CN/issues)
- **GitHub Discussions**: [参与讨论](https://github.com/hsliuping/TradingAgents-CN/discussions)
- **邮箱**: hsliup@163.com

## 许可证

本项目基于 Apache 2.0 许可证开源，详见 [LICENSE](LICENSE) 文件。

---

**注意**: 本更新日志将持续更新，记录项目的所有重要变更。建议用户定期查看以了解最新功能和改进。
