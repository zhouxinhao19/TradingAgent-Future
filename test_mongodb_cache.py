#!/usr/bin/env python3
"""测试 MongoDB 缓存统计功能"""

import os
from tradingagents.dataflows.cache.db_cache import DatabaseCacheManager
from tradingagents.dataflows.cache.integrated import IntegratedCacheManager
import json

def test_mongodb_connection():
    """测试 MongoDB 连接"""
    print("=" * 60)
    print("测试 MongoDB 连接")
    print("=" * 60)
    
    # 检查环境变量
    mongodb_uri = os.getenv('MONGODB_URI')
    print(f"MONGODB_URI: {mongodb_uri if mongodb_uri else '未设置'}")
    
    if not mongodb_uri:
        print("⚠️ MONGODB_URI 未设置，跳过 MongoDB 测试")
        return None
    
    try:
        db_manager = DatabaseCacheManager()
        
        print(f"\nMongoDB 可用: {db_manager.is_mongodb_available()}")
        print(f"Redis 可用: {db_manager.is_redis_available()}")
        print(f"数据库可用: {db_manager.is_database_available()}")
        
        if db_manager.is_mongodb_available():
            # 获取 MongoDB 客户端
            client = db_manager.get_mongodb_client()
            db = client.tradingagents
            
            print("\n" + "=" * 60)
            print("MongoDB 集合统计:")
            print("=" * 60)
            
            for collection_name in ["stock_data", "news_data", "fundamentals_data"]:
                if collection_name in db.list_collection_names():
                    collection = db[collection_name]
                    count = collection.count_documents({})
                    print(f"{collection_name}: {count} 条记录")
                    
                    # 获取集合大小
                    try:
                        stats = db.command("collStats", collection_name)
                        size_bytes = stats.get("size", 0)
                        size_mb = round(size_bytes / (1024 * 1024), 2)
                        print(f"  大小: {size_bytes} 字节 ({size_mb} MB)")
                    except Exception as e:
                        print(f"  获取大小失败: {e}")
                else:
                    print(f"{collection_name}: 集合不存在")
        
        return db_manager
        
    except Exception as e:
        print(f"❌ MongoDB 连接失败: {e}")
        return None

def test_db_cache_stats(db_manager):
    """测试数据库缓存统计"""
    if not db_manager:
        print("\n⚠️ 跳过数据库缓存统计测试")
        return
    
    print("\n" + "=" * 60)
    print("数据库缓存统计:")
    print("=" * 60)
    
    stats = db_manager.get_cache_stats()
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    
    # 验证关键字段
    assert 'total_files' in stats, "缺少 total_files 字段"
    assert 'total_size' in stats, "缺少 total_size 字段"
    assert 'stock_data_count' in stats, "缺少 stock_data_count 字段"
    
    print(f"\n✅ 数据库缓存统计测试通过！")
    print(f"   总文件数: {stats['total_files']}")
    print(f"   总大小: {stats['total_size']} 字节 ({stats.get('total_size_mb', 0)} MB)")
    print(f"   股票数据: {stats['stock_data_count']}")
    print(f"   新闻数据: {stats['news_count']}")
    print(f"   基本面数据: {stats['fundamentals_count']}")

def test_integrated_cache_stats():
    """测试集成缓存统计"""
    print("\n" + "=" * 60)
    print("集成缓存统计:")
    print("=" * 60)
    
    try:
        cache = IntegratedCacheManager()
        stats = cache.get_cache_stats()
        
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        
        # 验证关键字段
        assert 'total_files' in stats, "缺少 total_files 字段"
        assert 'total_size' in stats, "缺少 total_size 字段"
        assert 'cache_system' in stats, "缺少 cache_system 字段"
        
        print(f"\n✅ 集成缓存统计测试通过！")
        print(f"   缓存系统: {stats['cache_system']}")
        print(f"   总文件数: {stats['total_files']}")
        print(f"   总大小: {stats['total_size']} 字节 ({stats.get('total_size_mb', 0)} MB)")
        
    except Exception as e:
        print(f"❌ 集成缓存统计测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # 测试 MongoDB 连接
    db_manager = test_mongodb_connection()
    
    # 测试数据库缓存统计
    test_db_cache_stats(db_manager)
    
    # 测试集成缓存统计
    test_integrated_cache_stats()

