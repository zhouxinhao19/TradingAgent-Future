#!/usr/bin/env python3
"""
TradingAgents-CN Streamlit Web界面
基于Streamlit的股票分析Web应用程序
"""

import streamlit as st
import os
import sys
from pathlib import Path
import datetime
import time
from dotenv import load_dotenv

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载环境变量
load_dotenv(project_root / ".env", override=True)

# 导入自定义组件
from components.sidebar import render_sidebar
from components.header import render_header
from components.analysis_form import render_analysis_form
from components.results_display import render_results
from utils.api_checker import check_api_keys
from utils.analysis_runner import run_stock_analysis, validate_analysis_params, format_analysis_results
from utils.progress_tracker import StreamlitProgressDisplay, create_progress_callback

# 设置页面配置
st.set_page_config(
    page_title="TradingAgents-CN 股票分析平台",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': 'https://github.com/TauricResearch/TradingAgents',
        'Report a bug': 'https://github.com/TauricResearch/TradingAgents/issues',
        'About': """
        # TradingAgents-CN 股票分析平台
        
        基于多智能体大语言模型的中文金融交易决策框架
        
        **主要特性:**
        - 🤖 多智能体协作分析
        - 🇨🇳 中文优化的AI模型
        - 📊 实时股票数据分析
        - 🎯 专业投资建议
        
        **版本:** 1.0.0
        **开发团队:** TradingAgents-CN
        """
    }
)

# 自定义CSS样式
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(90deg, #1f77b4, #ff7f0e);
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 2rem;
        color: white;
        text-align: center;
    }
    
    .metric-card {
        background: #f0f2f6;
        padding: 1rem;
        border-radius: 10px;
        border-left: 4px solid #1f77b4;
        margin: 0.5rem 0;
    }
    
    .analysis-section {
        background: white;
        padding: 1.5rem;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin: 1rem 0;
    }
    
    .success-box {
        background: #d4edda;
        border: 1px solid #c3e6cb;
        border-radius: 5px;
        padding: 1rem;
        margin: 1rem 0;
    }
    
    .warning-box {
        background: #fff3cd;
        border: 1px solid #ffeaa7;
        border-radius: 5px;
        padding: 1rem;
        margin: 1rem 0;
    }
    
    .error-box {
        background: #f8d7da;
        border: 1px solid #f5c6cb;
        border-radius: 5px;
        padding: 1rem;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

def initialize_session_state():
    """初始化会话状态"""
    if 'analysis_results' not in st.session_state:
        st.session_state.analysis_results = None
    if 'analysis_running' not in st.session_state:
        st.session_state.analysis_running = False
    if 'last_analysis_time' not in st.session_state:
        st.session_state.last_analysis_time = None

def main():
    """主应用程序"""
    
    # 初始化会话状态
    initialize_session_state()
    
    # 渲染页面头部
    render_header()
    
    # 检查API密钥
    api_status = check_api_keys()
    
    if not api_status['all_configured']:
        st.error("⚠️ API密钥配置不完整，请先配置必要的API密钥")
        
        with st.expander("📋 API密钥配置指南", expanded=True):
            st.markdown("""
            ### 🔑 必需的API密钥
            
            1. **阿里百炼API密钥** (DASHSCOPE_API_KEY)
               - 获取地址: https://dashscope.aliyun.com/
               - 用途: AI模型推理
            
            2. **金融数据API密钥** (FINNHUB_API_KEY)  
               - 获取地址: https://finnhub.io/
               - 用途: 获取股票数据
            
            ### ⚙️ 配置方法
            
            1. 复制项目根目录的 `.env.example` 为 `.env`
            2. 编辑 `.env` 文件，填入您的真实API密钥
            3. 重启Web应用
            
            ```bash
            # .env 文件示例
            DASHSCOPE_API_KEY=sk-your-dashscope-key
            FINNHUB_API_KEY=your-finnhub-key
            ```
            """)
        
        # 显示当前API密钥状态
        st.subheader("🔍 当前API密钥状态")
        for key, status in api_status['details'].items():
            if status['configured']:
                st.success(f"✅ {key}: {status['display']}")
            else:
                st.error(f"❌ {key}: 未配置")
        
        return
    
    # 渲染侧边栏
    config = render_sidebar()
    
    # 主内容区域
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.header("📊 股票分析")
        
        # 渲染分析表单
        form_data = render_analysis_form()

        # 检查是否提交了表单
        if form_data.get('submitted', False):
            if not form_data['stock_symbol']:
                st.error("请输入股票代码")
            elif not form_data['analysts']:
                st.error("请至少选择一个分析师")
            else:
                # 执行分析
                st.session_state.analysis_running = True

                # 创建进度显示
                progress_container = st.container()
                progress_display = StreamlitProgressDisplay(progress_container)
                progress_callback = create_progress_callback(progress_display)

                try:
                    results = run_stock_analysis(
                        stock_symbol=form_data['stock_symbol'],
                        analysis_date=form_data['analysis_date'],
                        analysts=form_data['analysts'],
                        research_depth=form_data['research_depth'],
                        llm_provider=config['llm_provider'],
                        llm_model=config['llm_model'],
                        progress_callback=progress_callback
                    )

                    # 清除进度显示
                    progress_display.clear()

                    # 格式化结果
                    formatted_results = format_analysis_results(results)

                    st.session_state.analysis_results = formatted_results
                    st.session_state.last_analysis_time = datetime.datetime.now()
                    st.success("✅ 分析完成！")

                except Exception as e:
                    # 清除进度显示
                    progress_display.clear()

                    st.error(f"❌ 分析失败: {str(e)}")
                    st.markdown("""
                    **可能的解决方案:**
                    1. 检查API密钥是否正确配置
                    2. 确认网络连接正常
                    3. 验证股票代码是否有效
                    4. 尝试减少研究深度或更换模型
                    """)
                finally:
                    st.session_state.analysis_running = False
        
        # 显示分析结果
        if st.session_state.analysis_results:
            render_results(st.session_state.analysis_results)
    
    with col2:
        st.header("ℹ️ 使用指南")
        
        # 快速开始指南
        with st.expander("🎯 快速开始", expanded=True):
            st.markdown("""
            1. **输入股票代码** (如 AAPL, TSLA, MSFT)
            2. **选择分析日期** (默认今天)
            3. **选择分析师团队** (至少一个)
            4. **设置研究深度** (1-5级)
            5. **点击开始分析**
            """)
        
        # 分析师说明
        with st.expander("👥 分析师团队说明"):
            st.markdown("""
            - **📈 市场分析师**: 技术面分析，价格趋势
            - **💭 社交媒体分析师**: 投资者情绪分析
            - **📰 新闻分析师**: 新闻事件影响分析
            - **💰 基本面分析师**: 财务数据分析
            """)
        
        # 模型选择说明
        with st.expander("🧠 AI模型说明"):
            st.markdown("""
            - **Turbo**: 快速响应，适合快速查询
            - **Plus**: 平衡性能，推荐日常使用  
            - **Max**: 最强性能，适合深度分析
            """)
        
        # 风险提示
        st.warning("""
        ⚠️ **投资风险提示**
        
        - 分析结果仅供参考，不构成投资建议
        - 投资有风险，入市需谨慎
        - 请结合多方信息进行决策
        - 重大投资建议咨询专业顾问
        """)
        
        # 显示系统状态
        if st.session_state.last_analysis_time:
            st.info(f"🕒 上次分析时间: {st.session_state.last_analysis_time.strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()
