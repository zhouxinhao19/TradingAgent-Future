"""
分析结果管理组件
提供股票分析历史结果的查看和管理功能
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from typing import Dict, List, Any
import json
import os
from pathlib import Path

def get_analysis_results_dir():
    """获取分析结果目录"""
    results_dir = Path(__file__).parent.parent / "data" / "analysis_results"
    results_dir.mkdir(parents=True, exist_ok=True)
    return results_dir

def load_analysis_results(start_date=None, end_date=None, stock_symbol=None, analyst_type=None, limit=100):
    """加载分析结果"""
    results_dir = get_analysis_results_dir()
    all_results = []
    
    # 遍历结果文件
    for result_file in results_dir.glob("*.json"):
        try:
            with open(result_file, 'r', encoding='utf-8') as f:
                result = json.load(f)
                all_results.append(result)
        except Exception as e:
            st.warning(f"读取分析结果文件 {result_file.name} 失败: {e}")
    
    # 过滤结果
    filtered_results = []
    for result in all_results:
        # 时间过滤
        if start_date or end_date:
            result_time = datetime.fromtimestamp(result.get('timestamp', 0))
            if start_date and result_time.date() < start_date:
                continue
            if end_date and result_time.date() > end_date:
                continue
        
        # 股票代码过滤
        if stock_symbol and result.get('stock_symbol', '').upper() != stock_symbol.upper():
            continue
        
        # 分析师类型过滤
        if analyst_type and analyst_type not in result.get('analysts', []):
            continue
        
        filtered_results.append(result)
    
    # 按时间倒序排列
    filtered_results.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
    
    # 限制数量
    return filtered_results[:limit]

def render_analysis_results():
    """渲染分析结果管理界面"""
    
    # 检查权限
    try:
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.dirname(__file__)))
        from utils.auth_manager import auth_manager
        
        if not auth_manager or not auth_manager.check_permission("analysis"):
            st.error("❌ 您没有权限访问分析结果")
            st.info("💡 提示：分析结果功能需要 'analysis' 权限")
            return
    except Exception as e:
        st.error(f"❌ 权限检查失败: {e}")
        return
    
    st.title("📊 分析结果管理")
    
    # 侧边栏过滤选项
    with st.sidebar:
        st.header("🔍 过滤选项")
        
        # 日期范围选择
        date_range = st.selectbox(
            "📅 时间范围",
            ["最近1天", "最近3天", "最近7天", "最近30天", "自定义"],
            index=2
        )
        
        if date_range == "自定义":
            start_date = st.date_input("开始日期", datetime.now() - timedelta(days=7))
            end_date = st.date_input("结束日期", datetime.now())
        else:
            days_map = {"最近1天": 1, "最近3天": 3, "最近7天": 7, "最近30天": 30}
            days = days_map[date_range]
            end_date = datetime.now().date()
            start_date = (datetime.now() - timedelta(days=days)).date()
        
        # 股票代码过滤
        stock_filter = st.text_input("📈 股票代码过滤", placeholder="如: 000001, AAPL")
        
        # 分析师类型过滤
        analyst_filter = st.selectbox(
            "👥 分析师类型",
            ["全部", "market_analyst", "social_media_analyst", "news_analyst", "fundamental_analyst"]
        )
        
        if analyst_filter == "全部":
            analyst_filter = None
    
    # 加载分析结果
    results = load_analysis_results(
        start_date=start_date,
        end_date=end_date,
        stock_symbol=stock_filter if stock_filter else None,
        analyst_type=analyst_filter,
        limit=100
    )
    
    if not results:
        st.warning("📭 未找到符合条件的分析结果")
        return
    
    # 显示统计概览
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("📊 总分析数", len(results))
    
    with col2:
        unique_stocks = len(set(result.get('stock_symbol', 'unknown') for result in results))
        st.metric("📈 分析股票", unique_stocks)
    
    with col3:
        successful_analyses = sum(1 for result in results if result.get('status') == 'completed')
        success_rate = (successful_analyses / len(results) * 100) if results else 0
        st.metric("✅ 成功率", f"{success_rate:.1f}%")
    
    with col4:
        recent_results = [result for result in results if datetime.fromtimestamp(result.get('timestamp', 0)) > datetime.now() - timedelta(hours=24)]
        st.metric("🕐 近24小时", len(recent_results))
    
    # 标签页
    tab1, tab2, tab3, tab4 = st.tabs(["📈 统计图表", "📋 结果列表", "📊 详细分析", "📤 导出数据"])
    
    with tab1:
        render_results_charts(results)
    
    with tab2:
        render_results_list(results)
    
    with tab3:
        render_detailed_analysis(results)
    
    with tab4:
        render_results_export(results)

def render_results_charts(results: List[Dict[str, Any]]):
    """渲染分析结果统计图表"""
    
    # 按股票统计
    st.subheader("📈 按股票统计")
    stock_counts = {}
    for result in results:
        stock = result.get('stock_symbol', 'unknown')
        stock_counts[stock] = stock_counts.get(stock, 0) + 1
    
    if stock_counts:
        # 只显示前10个最常分析的股票
        top_stocks = sorted(stock_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        stocks = [item[0] for item in top_stocks]
        counts = [item[1] for item in top_stocks]
        
        fig_bar = px.bar(
            x=stocks,
            y=counts,
            title="最常分析的股票 (前10名)",
            labels={'x': '股票代码', 'y': '分析次数'}
        )
        st.plotly_chart(fig_bar, use_container_width=True)
    
    # 按时间统计
    st.subheader("📅 按时间统计")
    daily_results = {}
    for result in results:
        date_str = datetime.fromtimestamp(result.get('timestamp', 0)).strftime('%Y-%m-%d')
        daily_results[date_str] = daily_results.get(date_str, 0) + 1
    
    if daily_results:
        dates = sorted(daily_results.keys())
        counts = [daily_results[date] for date in dates]
        
        fig_line = go.Figure()
        fig_line.add_trace(go.Scatter(
            x=dates,
            y=counts,
            mode='lines+markers',
            name='每日分析数',
            line=dict(color='#2E8B57', width=2),
            marker=dict(size=6)
        ))
        fig_line.update_layout(
            title="每日分析趋势",
            xaxis_title="日期",
            yaxis_title="分析数量"
        )
        st.plotly_chart(fig_line, use_container_width=True)
    
    # 按分析师类型统计
    st.subheader("👥 按分析师类型统计")
    analyst_counts = {}
    for result in results:
        analysts = result.get('analysts', [])
        for analyst in analysts:
            analyst_counts[analyst] = analyst_counts.get(analyst, 0) + 1
    
    if analyst_counts:
        fig_pie = px.pie(
            values=list(analyst_counts.values()),
            names=list(analyst_counts.keys()),
            title="分析师使用分布"
        )
        st.plotly_chart(fig_pie, use_container_width=True)

def render_results_list(results: List[Dict[str, Any]]):
    """渲染分析结果列表"""
    
    st.subheader("📋 分析结果列表")
    
    # 分页设置
    page_size = st.selectbox("每页显示", [5, 10, 20, 50], index=1)
    total_pages = (len(results) + page_size - 1) // page_size
    
    if total_pages > 1:
        page = st.number_input("页码", min_value=1, max_value=total_pages, value=1) - 1
    else:
        page = 0
    
    # 获取当前页数据
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, len(results))
    page_results = results[start_idx:end_idx]
    
    # 显示结果卡片
    for i, result in enumerate(page_results):
        with st.expander(f"📊 {result.get('stock_symbol', 'unknown')} - {datetime.fromtimestamp(result.get('timestamp', 0)).strftime('%Y-%m-%d %H:%M')}"):
            col1, col2 = st.columns([2, 1])
            
            with col1:
                st.write(f"**股票代码**: {result.get('stock_symbol', 'unknown')}")
                st.write(f"**分析时间**: {datetime.fromtimestamp(result.get('timestamp', 0)).strftime('%Y-%m-%d %H:%M:%S')}")
                st.write(f"**分析师**: {', '.join(result.get('analysts', []))}")
                st.write(f"**研究深度**: {result.get('research_depth', 'unknown')}")
                st.write(f"**状态**: {'✅ 完成' if result.get('status') == 'completed' else '❌ 失败'}")
            
            with col2:
                if st.button(f"查看详情", key=f"view_{start_idx + i}"):
                    st.session_state[f"selected_result_{start_idx + i}"] = result
            
            # 显示分析摘要
            if result.get('summary'):
                st.write("**分析摘要**:")
                st.write(result['summary'][:200] + "..." if len(result['summary']) > 200 else result['summary'])
    
    # 显示分页信息
    if total_pages > 1:
        st.info(f"第 {page + 1} 页，共 {total_pages} 页，总计 {len(results)} 条记录")

def render_detailed_analysis(results: List[Dict[str, Any]]):
    """渲染详细分析"""
    
    st.subheader("📊 详细分析")
    
    if not results:
        st.info("没有可分析的数据")
        return
    
    # 选择要查看的分析结果
    result_options = []
    for i, result in enumerate(results[:20]):  # 只显示前20个
        option = f"{result.get('stock_symbol', 'unknown')} - {datetime.fromtimestamp(result.get('timestamp', 0)).strftime('%m-%d %H:%M')}"
        result_options.append(option)
    
    if result_options:
        selected_option = st.selectbox("选择分析结果", result_options)
        selected_index = result_options.index(selected_option)
        selected_result = results[selected_index]
        
        # 显示详细信息
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**基本信息**")
            st.json({
                "股票代码": selected_result.get('stock_symbol', 'unknown'),
                "分析时间": datetime.fromtimestamp(selected_result.get('timestamp', 0)).strftime('%Y-%m-%d %H:%M:%S'),
                "分析师": selected_result.get('analysts', []),
                "研究深度": selected_result.get('research_depth', 'unknown'),
                "状态": selected_result.get('status', 'unknown')
            })
        
        with col2:
            st.write("**性能指标**")
            performance = selected_result.get('performance', {})
            if performance:
                st.json(performance)
            else:
                st.info("暂无性能数据")
        
        # 显示完整分析结果
        if st.checkbox("显示完整分析结果"):
            render_detailed_analysis(selected_result)

def render_detailed_analysis(selected_result):
    """渲染详细分析结果"""
    st.subheader("📊 完整分析数据")
    
    # 添加自定义CSS样式美化标签页
    st.markdown("""
    <style>
    /* 标签页容器样式 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: #f8f9fa;
        padding: 8px;
        border-radius: 10px;
        margin-bottom: 20px;
    }

    /* 单个标签页样式 */
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        padding: 8px 16px;
        background-color: #ffffff;
        border-radius: 8px;
        border: 1px solid #e1e5e9;
        color: #495057;
        font-weight: 500;
        transition: all 0.3s ease;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }

    /* 标签页悬停效果 */
    .stTabs [data-baseweb="tab"]:hover {
        background-color: #e3f2fd;
        border-color: #2196f3;
        transform: translateY(-1px);
        box-shadow: 0 2px 8px rgba(33,150,243,0.2);
    }

    /* 选中的标签页样式 */
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
        color: white !important;
        border-color: #667eea !important;
        box-shadow: 0 4px 12px rgba(102,126,234,0.3) !important;
        transform: translateY(-2px);
    }

    /* 标签页内容区域 */
    .stTabs [data-baseweb="tab-panel"] {
        padding: 20px;
        background-color: #ffffff;
        border-radius: 10px;
        border: 1px solid #e1e5e9;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }

    /* 标签页文字样式 */
    .stTabs [data-baseweb="tab"] p {
        margin: 0;
        font-size: 14px;
        font-weight: 600;
    }

    /* 选中标签页的文字样式 */
    .stTabs [aria-selected="true"] p {
        color: white !important;
        text-shadow: 0 1px 2px rgba(0,0,0,0.1);
    }
    </style>
    """, unsafe_allow_html=True)
    
    # 定义分析模块 - 包含完整的团队决策报告，与CLI端保持一致
    analysis_modules = [
        {
            'key': 'market_report',
            'title': '📈 市场技术分析',
            'icon': '📈',
            'description': '技术指标、价格趋势、支撑阻力位分析'
        },
        {
            'key': 'fundamentals_report',
            'title': '💰 基本面分析',
            'icon': '💰',
            'description': '财务数据、估值水平、盈利能力分析'
        },
        {
            'key': 'sentiment_report',
            'title': '💭 市场情绪分析',
            'icon': '💭',
            'description': '投资者情绪、社交媒体情绪指标'
        },
        {
            'key': 'news_report',
            'title': '📰 新闻事件分析',
            'icon': '📰',
            'description': '相关新闻事件、市场动态影响分析'
        },
        {
            'key': 'risk_assessment',
            'title': '⚠️ 风险评估',
            'icon': '⚠️',
            'description': '风险因素识别、风险等级评估'
        },
        {
            'key': 'investment_plan',
            'title': '📋 投资建议',
            'icon': '📋',
            'description': '具体投资策略、仓位管理建议'
        },
        # 添加团队决策报告模块
        {
            'key': 'investment_debate_state',
            'title': '🔬 研究团队决策',
            'icon': '🔬',
            'description': '多头/空头研究员辩论分析，研究经理综合决策'
        },
        {
            'key': 'trader_investment_plan',
            'title': '💼 交易团队计划',
            'icon': '💼',
            'description': '专业交易员制定的具体交易执行计划'
        },
        {
            'key': 'risk_debate_state',
            'title': '⚖️ 风险管理团队',
            'icon': '⚖️',
            'description': '激进/保守/中性分析师风险评估，投资组合经理最终决策'
        },
        {
            'key': 'final_trade_decision',
            'title': '🎯 最终交易决策',
            'icon': '🎯',
            'description': '综合所有团队分析后的最终投资决策'
        }
    ]
    
    # 过滤出有数据的模块
    available_modules = []
    for module in analysis_modules:
        if module['key'] in selected_result and selected_result[module['key']]:
            # 检查字典类型的数据是否有实际内容
            if isinstance(selected_result[module['key']], dict):
                # 对于字典，检查是否有非空的值
                has_content = any(v for v in selected_result[module['key']].values() if v)
                if has_content:
                    available_modules.append(module)
            else:
                # 对于字符串或其他类型，直接添加
                available_modules.append(module)

    if not available_modules:
        # 显示占位符
        st.info("📊 该分析结果暂无详细报告数据")
        # 显示原始JSON数据作为备选
        with st.expander("查看原始数据"):
            st.json(selected_result)
        return

    # 只为有数据的模块创建标签页
    tabs = st.tabs([module['title'] for module in available_modules])

    for i, (tab, module) in enumerate(zip(tabs, available_modules)):
        with tab:
            # 在内容区域显示图标和描述
            st.markdown(f"## {module['icon']} {module['title']}")
            st.markdown(f"*{module['description']}*")
            st.markdown("---")

            # 格式化显示内容
            content = selected_result[module['key']]
            if isinstance(content, str):
                st.markdown(content)
            elif isinstance(content, dict):
                # 特殊处理团队决策报告的字典结构
                if module['key'] == 'investment_debate_state':
                    render_investment_debate_content(content)
                elif module['key'] == 'risk_debate_state':
                    render_risk_debate_content(content)
                else:
                    # 普通字典格式化显示
                    for key, value in content.items():
                        if value:  # 只显示非空值
                            st.subheader(key.replace('_', ' ').title())
                            if isinstance(value, str):
                                st.markdown(value)
                            else:
                                st.write(value)
            else:
                st.write(content)

def render_investment_debate_content(content):
    """渲染投资辩论内容"""
    if 'bull_analyst_report' in content and content['bull_analyst_report']:
        st.subheader("🐂 多头分析师观点")
        st.markdown(content['bull_analyst_report'])
    
    if 'bear_analyst_report' in content and content['bear_analyst_report']:
        st.subheader("🐻 空头分析师观点")
        st.markdown(content['bear_analyst_report'])
    
    if 'research_manager_decision' in content and content['research_manager_decision']:
        st.subheader("👨‍💼 研究经理决策")
        st.markdown(content['research_manager_decision'])

def render_risk_debate_content(content):
    """渲染风险辩论内容"""
    if 'aggressive_analyst_report' in content and content['aggressive_analyst_report']:
        st.subheader("🔥 激进分析师观点")
        st.markdown(content['aggressive_analyst_report'])
    
    if 'conservative_analyst_report' in content and content['conservative_analyst_report']:
        st.subheader("🛡️ 保守分析师观点")
        st.markdown(content['conservative_analyst_report'])
    
    if 'neutral_analyst_report' in content and content['neutral_analyst_report']:
        st.subheader("⚖️ 中性分析师观点")
        st.markdown(content['neutral_analyst_report'])
    
    if 'portfolio_manager_decision' in content and content['portfolio_manager_decision']:
        st.subheader("👨‍💼 投资组合经理决策")
        st.markdown(content['portfolio_manager_decision'])

def render_results_export(results: List[Dict[str, Any]]):
    """渲染分析结果导出功能"""
    
    st.subheader("📤 导出分析结果")
    
    if not results:
        st.warning("没有可导出的分析结果")
        return
    
    # 导出选项
    export_type = st.selectbox("选择导出内容", ["摘要信息", "完整数据"])
    export_format = st.selectbox("选择导出格式", ["CSV", "JSON", "Excel"])
    
    if st.button("📥 导出结果"):
        try:
            if export_type == "摘要信息":
                # 导出摘要信息
                summary_data = []
                for result in results:
                    summary_data.append({
                        '分析时间': datetime.fromtimestamp(result.get('timestamp', 0)).strftime('%Y-%m-%d %H:%M:%S'),
                        '股票代码': result.get('stock_symbol', 'unknown'),
                        '分析师': ', '.join(result.get('analysts', [])),
                        '研究深度': result.get('research_depth', 'unknown'),
                        '状态': result.get('status', 'unknown'),
                        '摘要': result.get('summary', '')[:100] + '...' if len(result.get('summary', '')) > 100 else result.get('summary', '')
                    })
                
                if export_format == "CSV":
                    df = pd.DataFrame(summary_data)
                    csv_data = df.to_csv(index=False, encoding='utf-8-sig')
                    
                    st.download_button(
                        label="下载 CSV 文件",
                        data=csv_data,
                        file_name=f"analysis_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv"
                    )
                
                elif export_format == "JSON":
                    json_data = json.dumps(summary_data, ensure_ascii=False, indent=2)
                    
                    st.download_button(
                        label="下载 JSON 文件",
                        data=json_data,
                        file_name=f"analysis_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                        mime="application/json"
                    )
                
                elif export_format == "Excel":
                    df = pd.DataFrame(summary_data)
                    
                    from io import BytesIO
                    output = BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        df.to_excel(writer, index=False, sheet_name='分析摘要')
                    
                    excel_data = output.getvalue()
                    
                    st.download_button(
                        label="下载 Excel 文件",
                        data=excel_data,
                        file_name=f"analysis_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
            
            else:  # 完整数据
                if export_format == "JSON":
                    json_data = json.dumps(results, ensure_ascii=False, indent=2)
                    
                    st.download_button(
                        label="下载完整数据 JSON 文件",
                        data=json_data,
                        file_name=f"analysis_full_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                        mime="application/json"
                    )
                else:
                    st.warning("完整数据只支持 JSON 格式导出")
            
            st.success(f"✅ {export_format} 文件准备完成，请点击下载按钮")
            
        except Exception as e:
            st.error(f"❌ 导出失败: {e}")

def save_analysis_result(analysis_id: str, stock_symbol: str, analysts: List[str], 
                        research_depth: int, result_data: Dict, status: str = "completed"):
    """保存分析结果"""
    try:
        from web.utils.async_progress_tracker import safe_serialize
        
        results_dir = get_analysis_results_dir()
        
        # 创建结果文件
        result_file = results_dir / f"analysis_{analysis_id}.json"
        
        # 创建结果条目，使用安全序列化
        result_entry = {
            'analysis_id': analysis_id,
            'timestamp': datetime.now().timestamp(),
            'stock_symbol': stock_symbol,
            'analysts': analysts,
            'research_depth': research_depth,
            'status': status,
            'summary': safe_serialize(result_data.get('summary', '')),
            'performance': safe_serialize(result_data.get('performance', {})),
            'full_data': safe_serialize(result_data)
        }
        
        # 写入文件
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result_entry, f, ensure_ascii=False, indent=2)
        
        return True
        
    except Exception as e:
        print(f"保存分析结果失败: {e}")
        return False