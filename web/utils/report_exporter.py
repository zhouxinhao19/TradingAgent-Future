#!/usr/bin/env python3
"""
报告导出工具
支持将分析结果导出为多种格式
"""

import streamlit as st
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import tempfile
import base64

# 导入导出相关库
try:
    import markdown
    import re
    import tempfile
    import os
    from pathlib import Path

    # 导入pypandoc（用于markdown转docx和pdf）
    import pypandoc

    # 检查pandoc是否可用，如果不可用则尝试下载
    try:
        pypandoc.get_pandoc_version()
        PANDOC_AVAILABLE = True
    except OSError:
        print("⚠️ 未找到pandoc，正在尝试自动下载...")
        try:
            pypandoc.download_pandoc()
            PANDOC_AVAILABLE = True
            print("✅ pandoc下载成功！")
        except Exception as download_error:
            print(f"❌ pandoc下载失败: {download_error}")
            PANDOC_AVAILABLE = False

    EXPORT_AVAILABLE = True

except ImportError as e:
    EXPORT_AVAILABLE = False
    PANDOC_AVAILABLE = False
    print(f"导出功能依赖包缺失: {e}")
    print("请安装: pip install pypandoc markdown")


class ReportExporter:
    """报告导出器"""

    def __init__(self):
        self.export_available = EXPORT_AVAILABLE
        self.pandoc_available = PANDOC_AVAILABLE
    
    def generate_markdown_report(self, results: Dict[str, Any]) -> str:
        """生成Markdown格式的报告"""
        
        stock_symbol = results.get('stock_symbol', 'N/A')
        decision = results.get('decision', {})
        state = results.get('state', {})
        is_demo = results.get('is_demo', False)
        
        # 生成时间戳
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 构建Markdown内容
        md_content = f"""# {stock_symbol} 股票分析报告

**生成时间**: {timestamp}  
**分析状态**: {'演示模式' if is_demo else '正式分析'}

---

## 🎯 投资决策摘要

| 指标 | 数值 |
|------|------|
| **投资建议** | {decision.get('action', 'N/A').upper()} |
| **置信度** | {decision.get('confidence', 0):.1%} |
| **风险评分** | {decision.get('risk_score', 0):.1%} |
| **目标价位** | {decision.get('target_price', 'N/A')} |

### 分析推理
{decision.get('reasoning', '暂无分析推理')}

---

## 📋 分析配置信息

- **LLM提供商**: {results.get('llm_provider', 'N/A')}
- **AI模型**: {results.get('llm_model', 'N/A')}
- **分析师数量**: {len(results.get('analysts', []))}个
- **研究深度**: {results.get('research_depth', 'N/A')}

### 参与分析师
{', '.join(results.get('analysts', []))}

---

## 📊 详细分析报告

"""
        
        # 添加各个分析模块的内容
        analysis_modules = [
            ('market_report', '📈 市场技术分析', '技术指标、价格趋势、支撑阻力位分析'),
            ('fundamentals_report', '💰 基本面分析', '财务数据、估值水平、盈利能力分析'),
            ('sentiment_report', '💭 市场情绪分析', '投资者情绪、社交媒体情绪指标'),
            ('news_report', '📰 新闻事件分析', '相关新闻事件、市场动态影响分析'),
            ('risk_assessment', '⚠️ 风险评估', '风险因素识别、风险等级评估'),
            ('investment_plan', '📋 投资建议', '具体投资策略、仓位管理建议')
        ]
        
        for key, title, description in analysis_modules:
            md_content += f"\n### {title}\n\n"
            md_content += f"*{description}*\n\n"
            
            if key in state and state[key]:
                content = state[key]
                if isinstance(content, str):
                    md_content += f"{content}\n\n"
                elif isinstance(content, dict):
                    for sub_key, sub_value in content.items():
                        md_content += f"#### {sub_key.replace('_', ' ').title()}\n\n"
                        md_content += f"{sub_value}\n\n"
                else:
                    md_content += f"{content}\n\n"
            else:
                md_content += "暂无数据\n\n"
        
        # 添加风险提示
        md_content += f"""
---

## ⚠️ 重要风险提示

**投资风险提示**:
- **仅供参考**: 本分析结果仅供参考，不构成投资建议
- **投资风险**: 股票投资有风险，可能导致本金损失
- **理性决策**: 请结合多方信息进行理性投资决策
- **专业咨询**: 重大投资决策建议咨询专业财务顾问
- **自担风险**: 投资决策及其后果由投资者自行承担

---
*报告生成时间: {timestamp}*
"""
        
        return md_content
    
    def generate_docx_report(self, results: Dict[str, Any]) -> bytes:
        """生成Word文档格式的报告"""

        if not self.pandoc_available:
            raise Exception("Pandoc不可用，无法生成Word文档。请安装pandoc或使用Markdown格式导出。")

        # 首先生成markdown内容
        md_content = self.generate_markdown_report(results)

        try:
            # 创建临时文件用于docx输出
            with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as tmp_file:
                output_file = tmp_file.name

            # 使用pypandoc将markdown转换为docx
            pypandoc.convert_text(
                md_content,
                'docx',
                format='markdown',
                outputfile=output_file,
                extra_args=[
                    '--toc',
                    '--number-sections',
                    '--highlight-style=tango'
                ]
            )

            # 读取生成的docx文件
            with open(output_file, 'rb') as f:
                docx_content = f.read()

            # 清理临时文件
            os.unlink(output_file)

            return docx_content
        except Exception as e:
            raise Exception(f"生成Word文档失败: {e}")
    
    
    def generate_pdf_report(self, results: Dict[str, Any]) -> bytes:
        """生成PDF格式的报告"""

        if not self.pandoc_available:
            raise Exception("Pandoc不可用，无法生成PDF文档。请安装pandoc或使用Markdown格式导出。")

        # 首先生成markdown内容
        md_content = self.generate_markdown_report(results)
        
        # 尝试多种PDF引擎
        pdf_engines = [
            'wkhtmltopdf',  # 基于HTML的引擎，支持中文
            'weasyprint',   # 现代HTML转PDF引擎
            'prince',       # 商业级HTML转PDF引擎
            'pdflatex',     # 基础LaTeX引擎
            'xelatex'       # 最后备选
        ]
        
        for engine in pdf_engines:
            try:
                # 创建临时文件用于PDF输出
                with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
                    output_file = tmp_file.name
                
                # 根据引擎类型设置不同的参数
                extra_args = ['--toc', '--number-sections', '--highlight-style=tango']
                
                if engine in ['wkhtmltopdf', 'weasyprint', 'prince']:
                    # HTML引擎参数
                    extra_args.extend([
                        '--pdf-engine=' + engine,
                        '-V', 'geometry:margin=2cm'
                    ])
                elif engine == 'pdflatex':
                    # 基础LaTeX引擎参数
                    extra_args.extend([
                        '--pdf-engine=pdflatex',
                        '-V', 'geometry:margin=2cm',
                        '-V', 'documentclass=article',
                        '-V', 'fontsize=11pt'
                    ])
                else:
                    # xelatex参数（最后备选）
                    extra_args.extend([
                        '--pdf-engine=xelatex',
                        '-V', 'mainfont=SimSun',
                        '-V', 'CJKmainfont=SimSun',
                        '-V', 'geometry:margin=2cm'
                    ])
                
                # 使用pypandoc将markdown转换为PDF
                pypandoc.convert_text(
                    md_content,
                    'pdf',
                    format='markdown',
                    outputfile=output_file,
                    extra_args=extra_args
                )
                
                # 读取生成的PDF文件
                with open(output_file, 'rb') as f:
                    pdf_content = f.read()
                
                # 清理临时文件
                os.unlink(output_file)
                
                return pdf_content
                
            except Exception as e:
                print(f"PDF引擎 {engine} 失败: {e}")
                continue
        
        # 如果所有引擎都失败，抛出异常
        raise Exception("所有PDF引擎都无法生成PDF，请检查系统是否安装了相关依赖")
    
    def export_report(self, results: Dict[str, Any], format_type: str) -> Optional[bytes]:
        """导出报告为指定格式"""
        
        if not self.export_available:
            st.error("❌ 导出功能不可用，请安装必要的依赖包")
            return None
        
        try:
            if format_type == 'markdown':
                content = self.generate_markdown_report(results)
                return content.encode('utf-8')
            elif format_type == 'docx':
                return self.generate_docx_report(results)
            elif format_type == 'pdf':
                return self.generate_pdf_report(results)
            else:
                st.error(f"❌ 不支持的导出格式: {format_type}")
                return None
        except Exception as e:
            st.error(f"❌ 导出失败: {str(e)}")
            return None


# 创建全局导出器实例
report_exporter = ReportExporter()


def render_export_buttons(results: Dict[str, Any]):
    """渲染导出按钮"""

    if not results:
        return

    st.markdown("---")
    st.subheader("📤 导出报告")

    # 检查导出功能是否可用
    if not report_exporter.export_available:
        st.warning("⚠️ 导出功能需要安装额外依赖包")
        st.code("pip install pypandoc markdown")
        return

    # 检查pandoc是否可用
    if not report_exporter.pandoc_available:
        st.warning("⚠️ Word和PDF导出需要pandoc工具")
        st.info("💡 您仍可以使用Markdown格式导出")

        with st.expander("📖 如何安装pandoc"):
            st.markdown("""
            **Windows用户:**
            ```bash
            # 使用Chocolatey (推荐)
            choco install pandoc

            # 或下载安装包
            # https://github.com/jgm/pandoc/releases
            ```

            **或者使用Python自动下载:**
            ```python
            import pypandoc
            pypandoc.download_pandoc()
            ```
            """)

        # 只显示Markdown导出按钮
        if st.button("📄 导出 Markdown", help="导出为Markdown格式"):
            content = report_exporter.export_report(results, 'markdown')
            if content:
                stock_symbol = results.get('stock_symbol', 'analysis')
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"{stock_symbol}_analysis_{timestamp}.md"
                st.download_button(
                    label="📥 下载 Markdown",
                    data=content,
                    file_name=filename,
                    mime="text/markdown"
                )
        return
    
    # 生成文件名
    stock_symbol = results.get('stock_symbol', 'analysis')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("📄 导出 Markdown", help="导出为Markdown格式"):
            content = report_exporter.export_report(results, 'markdown')
            if content:
                filename = f"{stock_symbol}_analysis_{timestamp}.md"
                st.download_button(
                    label="📥 下载 Markdown",
                    data=content,
                    file_name=filename,
                    mime="text/markdown"
                )
    
    with col2:
        if st.button("📝 导出 Word", help="导出为Word文档格式"):
            content = report_exporter.export_report(results, 'docx')
            if content:
                filename = f"{stock_symbol}_analysis_{timestamp}.docx"
                st.download_button(
                    label="📥 下载 Word",
                    data=content,
                    file_name=filename,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )
    
    with col3:
        if st.button("📊 导出 PDF", help="导出为PDF格式"):
            content = report_exporter.export_report(results, 'pdf')
            if content:
                filename = f"{stock_symbol}_analysis_{timestamp}.pdf"
                st.download_button(
                    label="📥 下载 PDF",
                    data=content,
                    file_name=filename,
                    mime="application/pdf"
                )
    
 