# 📤 报告导出功能使用指南

## 🎯 功能概述

TradingAgents-CN支持将股票分析报告导出为多种格式，方便保存、分享和进一步处理。

### 支持的导出格式

- **📄 Markdown (.md)** - 轻量级标记语言，适合技术用户
- **📝 Word (.docx)** - Microsoft Word文档，适合商务使用
- **📊 PDF (.pdf)** - 便携式文档格式，适合打印和分享

## 🚀 快速开始

### 1. 安装依赖

导出功能需要额外的Python包：

```bash
# 基础依赖
pip install markdown pypandoc

# 对于PDF导出，还需要安装pandoc系统工具
```

### 2. 安装Pandoc系统工具

#### Windows
```bash
# 使用Chocolatey
choco install pandoc

# 或下载安装包
# https://github.com/jgm/pandoc/releases
```

#### macOS
```bash
# 使用Homebrew
brew install pandoc

# 使用MacPorts
sudo port install pandoc
```

#### Linux (Ubuntu/Debian)
```bash
sudo apt-get install pandoc
```

#### Linux (CentOS/RHEL)
```bash
sudo yum install pandoc
# 或
sudo dnf install pandoc
```

### 3. PDF导出额外依赖

为了更好地支持中文PDF导出，建议安装以下工具之一：

#### wkhtmltopdf (推荐)
```bash
# Windows
choco install wkhtmltopdf

# macOS
brew install wkhtmltopdf

# Ubuntu/Debian
sudo apt-get install wkhtmltopdf

# CentOS/RHEL
sudo yum install wkhtmltopdf
```

#### LaTeX (备选)
```bash
# Windows
choco install miktex

# macOS
brew install mactex

# Ubuntu/Debian
sudo apt-get install texlive-full

# CentOS/RHEL
sudo yum install texlive-scheme-full
```

## 📋 使用方法

### Web界面使用

1. **完成股票分析**
   - 在Web界面中输入股票代码
   - 等待分析完成

2. **选择导出格式**
   - 在分析结果页面底部找到"📤 导出报告"部分
   - 点击对应的导出按钮：
     - 📄 导出 Markdown
     - 📝 导出 Word  
     - 📊 导出 PDF

3. **下载文件**
   - 点击导出按钮后会出现下载按钮
   - 点击"📥 下载"按钮保存文件

### 文件命名规则

导出的文件会自动命名为：
```
{股票代码}_analysis_{时间戳}.{格式}

例如：
AAPL_analysis_20250712_143022.pdf
000001_analysis_20250712_143022.docx
```

## 📊 报告内容结构

### 报告包含以下部分：

1. **📋 基本信息**
   - 股票代码和名称
   - 生成时间
   - 分析状态（正式/演示）

2. **🎯 投资决策摘要**
   - 投资建议（买入/持有/卖出）
   - 置信度评分
   - 风险评分
   - 目标价位

3. **📊 详细分析报告**
   - 📈 市场技术分析
   - 💰 基本面分析
   - 💭 市场情绪分析
   - 📰 新闻事件分析
   - ⚠️ 风险评估
   - 📋 投资建议

4. **⚠️ 风险提示**
   - 投资风险声明
   - 免责条款

## 🔧 故障排除

### 常见问题

#### 1. 导出按钮不显示
**原因**: 缺少必要依赖
**解决**: 
```bash
pip install markdown pypandoc
```

#### 2. PDF导出失败
**原因**: 缺少PDF引擎
**解决**: 安装wkhtmltopdf或LaTeX
```bash
# 推荐安装wkhtmltopdf
choco install wkhtmltopdf  # Windows
brew install wkhtmltopdf   # macOS
sudo apt-get install wkhtmltopdf  # Linux
```

#### 3. 中文PDF显示异常
**原因**: 缺少中文字体支持
**解决**: 
- Windows: 系统自带中文字体
- macOS: 安装中文字体包
- Linux: 安装中文字体
```bash
# Ubuntu/Debian
sudo apt-get install fonts-wqy-zenhei fonts-wqy-microhei
```

#### 4. Word文档格式异常
**原因**: pypandoc版本过低
**解决**: 更新到最新版本
```bash
pip install --upgrade pypandoc
```

### 调试信息

如果遇到问题，可以查看控制台输出的详细错误信息：

```python
# 在Python环境中测试
import pypandoc
print(pypandoc.get_pandoc_version())
print(pypandoc.get_pandoc_formats())
```

## 💡 最佳实践

### 1. 格式选择建议

- **Markdown**: 适合技术用户，便于版本控制和进一步编辑
- **Word**: 适合商务报告，便于添加注释和修改
- **PDF**: 适合正式分享，格式固定不易修改

### 2. 性能优化

- PDF导出相对较慢，请耐心等待
- 大量导出时建议选择Markdown格式
- 定期清理下载文件夹

### 3. 安全提醒

- 导出的报告包含分析结果，请妥善保管
- 不要在公共场所下载敏感的投资分析报告
- 定期备份重要的分析报告

## 📞 技术支持

如果遇到导出功能相关问题：

1. 查看本文档的故障排除部分
2. 检查依赖安装是否完整
3. 提交Issue到GitHub仓库
4. 联系项目维护者

---

**祝您使用愉快！** 📈
