#!/usr/bin/env python3
"""测试缓存统计功能"""

from tradingagents.dataflows.cache import get_cache
import json

def test_cache_stats():
    """测试缓存统计"""
    cache = get_cache()
    stats = cache.get_cache_stats()
    
    print("=" * 60)
    print("缓存统计信息:")
    print("=" * 60)
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    print("=" * 60)
    
    # 验证关键字段
    assert 'total_files' in stats, "缺少 total_files 字段"
    assert 'total_size' in stats, "缺少 total_size 字段"
    assert 'total_size_mb' in stats, "缺少 total_size_mb 字段"
    assert 'stock_data_count' in stats, "缺少 stock_data_count 字段"
    assert 'news_count' in stats, "缺少 news_count 字段"
    assert 'fundamentals_count' in stats, "缺少 fundamentals_count 字段"
    
    print(f"\n✅ 测试通过！")
    print(f"   总文件数: {stats['total_files']}")
    print(f"   总大小: {stats['total_size']} 字节 ({stats['total_size_mb']} MB)")
    print(f"   股票数据: {stats['stock_data_count']}")
    print(f"   新闻数据: {stats['news_count']}")
    print(f"   基本面数据: {stats['fundamentals_count']}")

if __name__ == "__main__":
    test_cache_stats()

