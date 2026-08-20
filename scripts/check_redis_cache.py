#!/usr/bin/env python3
"""
检查 Redis 缓存中的美股数据
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import redis
import pickle
from datetime import datetime

def check_redis_cache():
    """检查 Redis 缓存"""
    print("=" * 80)
    print("📊 Redis 缓存检查")
    print("=" * 80)
    
    try:
        # 连接 Redis
        redis_client = redis.Redis(
            host='127.0.0.1',
            port=6379,
            password='CHANGE_ME_LOCAL_PASSWORD',
            db=0,
            decode_responses=False  # 不自动解码，因为数据是 pickle 序列化的
        )
        
        # 测试连接
        redis_client.ping()
        print("✅ Redis 连接成功\n")
        
        # 获取所有键
        all_keys = redis_client.keys('*')
        print(f"📋 Redis 中的键数量: {len(all_keys)}\n")
        
        if not all_keys:
            print("❌ Redis 中没有缓存数据")
            return
        
        # 分类统计
        stock_data_keys = []
        fundamentals_keys = []
        news_keys = []
        other_keys = []
        
        for key in all_keys:
            key_str = key.decode('utf-8') if isinstance(key, bytes) else key
            
            # 尝试加载数据
            try:
                data = redis_client.get(key)
                if data:
                    cache_data = pickle.loads(data)
                    metadata = cache_data.get('metadata', {})
                    data_type = metadata.get('data_type', 'unknown')
                    
                    if data_type == 'stock_data':
                        stock_data_keys.append((key_str, metadata))
                    elif data_type == 'fundamentals_data':
                        fundamentals_keys.append((key_str, metadata))
                    elif data_type == 'news_data':
                        news_keys.append((key_str, metadata))
                    else:
                        other_keys.append(key_str)
            except Exception as e:
                other_keys.append(key_str)
        
        # 显示统计
        print("📊 缓存数据分类统计:")
        print("-" * 80)
        print(f"  历史行情数据 (stock_data): {len(stock_data_keys)} 个")
        print(f"  基本面数据 (fundamentals_data): {len(fundamentals_keys)} 个")
        print(f"  新闻数据 (news_data): {len(news_keys)} 个")
        print(f"  其他数据: {len(other_keys)} 个")
        print()
        
        # 显示历史行情数据详情
        if stock_data_keys:
            print("📈 历史行情数据详情:")
            print("-" * 80)
            for key, metadata in stock_data_keys[:10]:  # 只显示前10个
                symbol = metadata.get('symbol', 'N/A')
                data_source = metadata.get('data_source', 'N/A')
                start_date = metadata.get('start_date', 'N/A')
                end_date = metadata.get('end_date', 'N/A')
                print(f"  {symbol} ({data_source}): {start_date} ~ {end_date}")
            
            if len(stock_data_keys) > 10:
                print(f"  ... 还有 {len(stock_data_keys) - 10} 个")
            print()
        
        # 显示基本面数据详情
        if fundamentals_keys:
            print("📊 基本面数据详情:")
            print("-" * 80)
            for key, metadata in fundamentals_keys[:10]:  # 只显示前10个
                symbol = metadata.get('symbol', 'N/A')
                data_source = metadata.get('data_source', 'N/A')
                print(f"  {symbol} ({data_source})")
            
            if len(fundamentals_keys) > 10:
                print(f"  ... 还有 {len(fundamentals_keys) - 10} 个")
            print()
        
        # 显示新闻数据详情
        if news_keys:
            print("📰 新闻数据详情:")
            print("-" * 80)
            for key, metadata in news_keys[:10]:  # 只显示前10个
                symbol = metadata.get('symbol', 'N/A')
                data_source = metadata.get('data_source', 'N/A')
                print(f"  {symbol} ({data_source})")
            
            if len(news_keys) > 10:
                print(f"  ... 还有 {len(news_keys) - 10} 个")
            print()
        
        # 显示其他数据
        if other_keys:
            print("🔧 其他数据:")
            print("-" * 80)
            for key in other_keys[:10]:
                print(f"  {key}")
            
            if len(other_keys) > 10:
                print(f"  ... 还有 {len(other_keys) - 10} 个")
            print()
        
        # 显示 Redis 内存使用情况
        info = redis_client.info('memory')
        used_memory = info.get('used_memory_human', 'N/A')
        print("💾 Redis 内存使用:")
        print("-" * 80)
        print(f"  已使用内存: {used_memory}")
        print()
        
    except redis.ConnectionError as e:
        print(f"❌ Redis 连接失败: {e}")
        print("请确保 Redis 服务正在运行")
    except Exception as e:
        print(f"❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("=" * 80)

if __name__ == "__main__":
    check_redis_cache()

