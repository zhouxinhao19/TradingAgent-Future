# TradingAgents v0.1.4 发布说明 | Release Notes

发布日期 | Release Date: 2024-12-19

## 🎯 主要功能 | Major Features

### 数据目录配置系统 | Data Directory Configuration System

本版本引入了完整的数据目录配置管理系统，解决了路径硬编码和跨平台兼容性问题。

This version introduces a complete data directory configuration management system, solving path hardcoding and cross-platform compatibility issues.

#### 核心功能 | Core Features

- **灵活的配置方式** | Flexible Configuration Methods
  - CLI命令配置 | CLI command configuration
  - 环境变量配置 | Environment variable configuration
  - 程序化配置 | Programmatic configuration

- **自动目录管理** | Automatic Directory Management
  - 自动创建必要的目录结构 | Automatically create necessary directory structure
  - 跨平台路径处理 | Cross-platform path handling
  - 目录存在性验证 | Directory existence validation

- **配置优先级** | Configuration Priority
  1. 环境变量 | Environment Variables (最高优先级 | Highest Priority)
  2. CLI设置 | CLI Settings
  3. 默认配置 | Default Configuration

## 🔧 新增功能 | New Features

### CLI命令增强 | CLI Command Enhancement

#### 新增 `data-config` 命令 | New `data-config` Command

```bash
# 查看当前配置 | View current configuration
python -m cli.main data-config
python -m cli.main data-config --show

# 设置自定义数据目录 | Set custom data directory
python -m cli.main data-config --set "C:\MyTradingData"

# 重置为默认配置 | Reset to default configuration
python -m cli.main data-config --reset
```

### 环境变量支持 | Environment Variable Support

- `TRADINGAGENTS_DATA_DIR` - 数据目录路径 | Data directory path
- `TRADINGAGENTS_CACHE_DIR` - 缓存目录路径 | Cache directory path
- `TRADINGAGENTS_RESULTS_DIR` - 结果目录路径 | Results directory path

### 配置管理器增强 | Configuration Manager Enhancement

- 新增数据目录相关配置项 | Added data directory related configuration items
- 支持动态配置更新 | Support dynamic configuration updates
- 集成目录自动创建功能 | Integrated automatic directory creation

## 🐛 问题修复 | Bug Fixes

### Finnhub新闻数据路径修复 | Finnhub News Data Path Fix

- **问题** | Issue: 硬编码的Unix路径导致Windows系统无法正常工作
- **解决方案** | Solution: 实现跨平台路径处理和动态配置
- **影响** | Impact: 解决了"No such file or directory"错误

### 跨平台兼容性改进 | Cross-Platform Compatibility Improvements

- 修复路径分隔符问题 | Fixed path separator issues
- 改进错误处理和用户提示 | Improved error handling and user prompts
- 增强目录权限检查 | Enhanced directory permission checks

## 📁 目录结构 | Directory Structure

配置数据目录后，系统自动创建以下结构：

After configuring the data directory, the system automatically creates the following structure:

```
data/
├── cache/                          # 缓存目录 | Cache directory
├── finnhub_data/                   # Finnhub数据目录 | Finnhub data directory
│   ├── news_data/                  # 新闻数据 | News data
│   ├── insider_sentiment/          # 内部人情绪数据 | Insider sentiment data
│   └── insider_transactions/       # 内部人交易数据 | Insider transaction data
└── results/                        # 分析结果 | Analysis results
```

## 📚 新增文档 | New Documentation

### 配置指南 | Configuration Guides

- **数据目录配置指南** | Data Directory Configuration Guide
  - 文件位置 | File Location: `docs/configuration/data-directory-configuration.md`
  - 详细的配置方法和最佳实践 | Detailed configuration methods and best practices

- **故障排除指南** | Troubleshooting Guide
  - 文件位置 | File Location: `docs/troubleshooting/finnhub-news-data-setup.md`
  - Finnhub新闻数据配置问题解决方案 | Finnhub news data configuration issue solutions

### 示例和测试 | Examples and Tests

- **配置演示脚本** | Configuration Demo Script
  - 文件位置 | File Location: `examples/data_dir_config_demo.py`
  - 展示各种配置方法的使用 | Demonstrates usage of various configuration methods

- **测试脚本** | Test Scripts
  - 文件位置 | File Location: `test_data_config_cli.py`
  - 验证配置功能的完整性 | Validates the completeness of configuration features

- **示例数据生成脚本** | Sample Data Generation Script
  - 文件位置 | File Location: `scripts/download_finnhub_sample_data.py`
  - 生成Finnhub测试数据 | Generates Finnhub test data

## 🔄 升级指南 | Upgrade Guide

### 从v0.1.3升级 | Upgrading from v0.1.3

1. **更新代码** | Update Code
   ```bash
   git pull origin main
   ```

2. **配置数据目录** | Configure Data Directory
   ```bash
   # 查看当前配置 | View current configuration
   python -m cli.main data-config
   
   # 如需要，设置自定义路径 | Set custom path if needed
   python -m cli.main data-config --set "your/custom/path"
   ```

3. **验证配置** | Verify Configuration
   ```bash
   python test_data_config_cli.py
   ```

### 迁移现有数据 | Migrating Existing Data

如果您有现有的数据文件，可以：

If you have existing data files, you can:

1. 将现有数据复制到新的数据目录 | Copy existing data to the new data directory
2. 使用环境变量指向现有数据位置 | Use environment variables to point to existing data location
3. 使用CLI命令设置数据目录到现有位置 | Use CLI commands to set data directory to existing location

## 🧪 测试验证 | Testing and Validation

### 功能测试 | Feature Testing

- ✅ 数据目录配置功能 | Data directory configuration functionality
- ✅ CLI命令完整性 | CLI command completeness
- ✅ 环境变量支持 | Environment variable support
- ✅ 跨平台兼容性 | Cross-platform compatibility
- ✅ 自动目录创建 | Automatic directory creation
- ✅ 错误处理和用户提示 | Error handling and user prompts

### 兼容性测试 | Compatibility Testing

- ✅ Windows 10/11
- ✅ Linux (Ubuntu, CentOS)
- ✅ macOS
- ✅ Python 3.8+

## 🔮 下一步计划 | Next Steps

### v0.1.5 计划功能 | Planned Features for v0.1.5

- 配置文件导入/导出功能 | Configuration file import/export functionality
- 数据目录备份和恢复 | Data directory backup and restore
- 更多数据源配置选项 | More data source configuration options
- 配置模板系统 | Configuration template system

## 🤝 贡献者 | Contributors

感谢所有为本版本做出贡献的开发者和用户。

Thanks to all developers and users who contributed to this version.

## 📞 技术支持 | Technical Support

如果在使用过程中遇到问题，请：

If you encounter issues during use, please:

1. 查看文档 | Check documentation
2. 运行诊断脚本 | Run diagnostic scripts
3. 提交Issue | Submit an issue
4. 参与社区讨论 | Participate in community discussions

---

**完整更新日志** | Full Changelog: [GitHub Releases](https://github.com/your-repo/releases)

**下载地址** | Download: [GitHub Releases](https://github.com/your-repo/releases/tag/v0.1.4)