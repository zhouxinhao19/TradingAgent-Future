#!/usr/bin/env python3
"""
数据库缓存管理页面
MongoDB + Redis 缓存管理和监控
"""

import streamlit as st
import sys
import os
from pathlib import Path
import json
from datetime import datetime, timedelta

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

try:
    from tradingagents.dataflows.db_cache_manager import get_db_cache
    DB_CACHE_AVAILABLE = True
except ImportError as e:
    DB_CACHE_AVAILABLE = False
    st.error(f"数据库缓存管理器不可用: {e}")

def main():
    st.set_page_config(
        page_title="数据库管理 - TradingAgents",
        page_icon="🗄️",
        layout="wide"
    )
    
    st.title("🗄️ MongoDB + Redis 数据库管理")
    st.markdown("---")
    
    if not DB_CACHE_AVAILABLE:
        st.error("❌ 数据库缓存管理器不可用")
        st.info("""
        请按以下步骤设置数据库环境：
        
        1. 安装依赖包：
        ```bash
        pip install -r requirements_db.txt
        ```
        
        2. 设置数据库：
        ```bash
        python scripts/setup_databases.py
        ```
        
        3. 测试连接：
        ```bash
        python scripts/setup_databases.py --test
        ```
        """)
        return
    
    # 获取数据库缓存实例
    db_cache = get_db_cache()
    
    # 侧边栏操作
    with st.sidebar:
        st.header("🛠️ 数据库操作")
        
        # 连接状态
        st.subheader("📡 连接状态")
        mongodb_status = "✅ 已连接" if db_cache.mongodb_client else "❌ 未连接"
        redis_status = "✅ 已连接" if db_cache.redis_client else "❌ 未连接"
        
        st.write(f"**MongoDB**: {mongodb_status}")
        st.write(f"**Redis**: {redis_status}")
        
        st.markdown("---")
        
        # 刷新按钮
        if st.button("🔄 刷新统计", type="primary"):
            st.rerun()
        
        st.markdown("---")
        
        # 清理操作
        st.subheader("🧹 清理数据")
        
        max_age_days = st.slider(
            "清理多少天前的数据",
            min_value=1,
            max_value=30,
            value=7,
            help="删除指定天数之前的缓存数据"
        )
        
        if st.button("🗑️ 清理过期数据", type="secondary"):
            with st.spinner("正在清理过期数据..."):
                cleared_count = db_cache.clear_old_cache(max_age_days)
            st.success(f"✅ 已清理 {cleared_count} 条过期记录")
            st.rerun()
    
    # 主要内容区域
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("📊 MongoDB 统计")
        
        try:
            stats = db_cache.get_cache_stats()
            mongodb_stats = stats.get("mongodb", {})
            
            if mongodb_stats.get("available"):
                collections = mongodb_stats.get("collections", {})
                
                # 总体统计
                total_records = sum(col.get("count", 0) for col in collections.values())
                total_size = sum(col.get("size_mb", 0) for col in collections.values())
                
                metric_col1, metric_col2 = st.columns(2)
                with metric_col1:
                    st.metric("总记录数", f"{total_records:,}")
                with metric_col2:
                    st.metric("总大小", f"{total_size:.2f} MB")
                
                # 各集合统计
                st.markdown("**集合详情：**")
                for collection_name, collection_stats in collections.items():
                    count = collection_stats.get("count", 0)
                    size = collection_stats.get("size_mb", 0)
                    
                    collection_display = {
                        "stock_data": "📈 股票数据",
                        "news_data": "📰 新闻数据",
                        "fundamentals_data": "💼 基本面数据"
                    }.get(collection_name, collection_name)
                    
                    st.write(f"**{collection_display}**: {count:,} 条记录, {size:.2f} MB")
            else:
                st.error("MongoDB 未连接")
                
        except Exception as e:
            st.error(f"获取MongoDB统计失败: {e}")
    
    with col2:
        st.subheader("⚡ Redis 统计")
        
        try:
            stats = db_cache.get_cache_stats()
            redis_stats = stats.get("redis", {})
            
            if redis_stats.get("available"):
                metric_col1, metric_col2 = st.columns(2)
                with metric_col1:
                    st.metric("缓存键数量", redis_stats.get("keys", 0))
                with metric_col2:
                    st.metric("内存使用", redis_stats.get("memory_usage", "N/A"))
                
                st.info("""
                **Redis 缓存策略：**
                
                🔹 **股票数据**：6小时自动过期
                🔹 **新闻数据**：24小时自动过期  
                🔹 **基本面数据**：24小时自动过期
                
                Redis 主要用于热点数据的快速访问，
                过期后会自动从 MongoDB 重新加载。
                """)
            else:
                st.error("Redis 未连接")
                
        except Exception as e:
            st.error(f"获取Redis统计失败: {e}")
    
    st.markdown("---")
    
    # 数据库配置信息
    st.subheader("⚙️ 数据库配置")
    
    config_col1, config_col2 = st.columns([1, 1])
    
    with config_col1:
        st.markdown("**MongoDB 配置：**")
        st.code(f"""
连接URL: {db_cache.mongodb_url}
数据库: {db_cache.mongodb_db_name}
状态: {mongodb_status}
        """)
        
        if db_cache.mongodb_client:
            st.markdown("**集合结构：**")
            st.code("""
📁 tradingagents/
├── 📊 stock_data        # 股票历史数据
├── 📰 news_data         # 新闻和市场情绪
└── 💼 fundamentals_data # 基本面分析数据
            """)
    
    with config_col2:
        st.markdown("**Redis 配置：**")
        st.code(f"""
连接URL: {db_cache.redis_url}
数据库: {db_cache.redis_db}
状态: {redis_status}
        """)
        
        if db_cache.redis_client:
            st.markdown("**缓存键格式：**")
            st.code("""
stock:SYMBOL:HASH     # 股票数据缓存
news:SYMBOL:HASH      # 新闻数据缓存  
fundamentals:SYMBOL:HASH # 基本面缓存
            """)
    
    st.markdown("---")
    
    # 性能对比
    st.subheader("🚀 性能优势")
    
    perf_col1, perf_col2, perf_col3 = st.columns(3)
    
    with perf_col1:
        st.metric(
            label="Redis 缓存速度",
            value="< 1ms",
            delta="比API快 1000+ 倍",
            help="Redis内存缓存的超快访问速度"
        )
    
    with perf_col2:
        st.metric(
            label="MongoDB 查询速度", 
            value="< 10ms",
            delta="比API快 100+ 倍",
            help="MongoDB索引优化的查询速度"
        )
    
    with perf_col3:
        st.metric(
            label="存储容量",
            value="无限制",
            delta="vs API 配额限制",
            help="本地存储不受API调用次数限制"
        )
    
    # 架构说明
    st.markdown("---")
    st.subheader("🏗️ 缓存架构")
    
    st.info("""
    **三层缓存架构：**
    
    1. **Redis (L1缓存)** - 内存缓存，毫秒级访问
       - 存储最热点的数据
       - 自动过期管理
       - 高并发支持
    
    2. **MongoDB (L2缓存)** - 持久化存储，秒级访问  
       - 存储所有历史数据
       - 支持复杂查询
       - 数据持久化保证
    
    3. **API (L3数据源)** - 外部数据源，分钟级访问
       - 通达信API (中国A股)
       - FINNHUB API (美股数据)
       - Yahoo Finance API (补充数据)
    
    **数据流向：** API → MongoDB → Redis → 应用程序
    """)
    
    # 页脚信息
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: #666; font-size: 0.9em;'>
        🗄️ 数据库缓存管理系统 | TradingAgents v0.1.2 | 
        <a href='https://github.com/your-repo/TradingAgents' target='_blank'>GitHub</a>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
