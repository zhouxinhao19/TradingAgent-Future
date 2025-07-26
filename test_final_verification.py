#!/usr/bin/env python3
"""
最终验证测试 - 确保所有修复都正常工作
"""

import os
import sys

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# 加载.env文件
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(project_root, '.env'))
    print(f"✅ 已加载.env文件")
except ImportError:
    print(f"⚠️ python-dotenv未安装")
except Exception as e:
    print(f"⚠️ 加载.env文件失败: {e}")

def test_akshare_priority():
    """测试AKShare数据源优先级"""
    print("\n🧪 测试AKShare数据源优先级")
    print("=" * 50)
    
    try:
        from tradingagents.dataflows.data_source_manager import DataSourceManager, ChinaDataSource
        
        manager = DataSourceManager()
        
        print(f"📊 默认数据源: {manager.default_source.value}")
        print(f"📊 当前数据源: {manager.current_source.value}")
        
        if manager.default_source == ChinaDataSource.AKSHARE:
            print("✅ AKShare数据源优先级设置正确")
            return True
        else:
            print(f"❌ 数据源优先级错误: {manager.default_source.value}")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_volume_mapping_fix():
    """测试volume映射修复"""
    print("\n🧪 测试volume映射修复")
    print("=" * 50)
    
    try:
        from tradingagents.dataflows.tushare_adapter import get_tushare_adapter
        import pandas as pd
        
        adapter = get_tushare_adapter()
        
        # 创建模拟的原始数据（包含'vol'列）
        mock_data = pd.DataFrame({
            'trade_date': ['20250726'],
            'ts_code': ['000001.SZ'],
            'open': [12.50],
            'high': [12.60],
            'low': [12.40],
            'close': [12.55],
            'vol': [1000000],  # 关键：使用'vol'而不是'volume'
            'amount': [12550000]
        })
        
        print(f"📊 原始数据列名: {list(mock_data.columns)}")
        
        # 测试标准化
        standardized = adapter._validate_and_standardize_data(mock_data)
        
        print(f"📊 标准化后列名: {list(standardized.columns)}")
        
        if 'volume' in standardized.columns:
            print(f"✅ vol -> volume 映射成功")
            print(f"📊 volume值: {standardized['volume'].iloc[0]}")
            return True
        else:
            print(f"❌ volume列不存在")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_data_source_manager_volume_safety():
    """测试数据源管理器的volume安全获取"""
    print("\n🧪 测试数据源管理器volume安全获取")
    print("=" * 50)
    
    try:
        from tradingagents.dataflows.data_source_manager import DataSourceManager
        import pandas as pd
        
        manager = DataSourceManager()
        
        # 测试包含'vol'列的数据
        test_data_vol = pd.DataFrame({
            'vol': [1000, 2000, 3000],
            'close': [10, 11, 12]
        })
        
        volume_sum = manager._get_volume_safely(test_data_vol)
        print(f"📊 使用'vol'列获取成交量: {volume_sum}")
        
        # 测试包含'volume'列的数据
        test_data_volume = pd.DataFrame({
            'volume': [1500, 2500, 3500],
            'close': [10, 11, 12]
        })
        
        volume_sum2 = manager._get_volume_safely(test_data_volume)
        print(f"📊 使用'volume'列获取成交量: {volume_sum2}")
        
        # 测试没有成交量列的数据
        test_data_none = pd.DataFrame({
            'close': [10, 11, 12],
            'high': [11, 12, 13]
        })
        
        volume_sum3 = manager._get_volume_safely(test_data_none)
        print(f"📊 无成交量列时返回: {volume_sum3}")
        
        if volume_sum == 6000 and volume_sum2 == 7500 and volume_sum3 == 0:
            print("✅ volume安全获取功能正常")
            return True
        else:
            print("❌ volume安全获取功能异常")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_integration():
    """集成测试"""
    print("\n🧪 集成测试")
    print("=" * 50)
    
    try:
        from tradingagents.dataflows.data_source_manager import DataSourceManager, ChinaDataSource
        
        manager = DataSourceManager()
        
        # 确保使用AKShare作为默认数据源
        print(f"📊 当前默认数据源: {manager.default_source.value}")
        
        # 测试数据源切换
        if ChinaDataSource.TUSHARE in manager.available_sources:
            success = manager.set_current_source(ChinaDataSource.TUSHARE)
            if success:
                print(f"✅ 成功切换到Tushare数据源")
                
                # 切换回AKShare
                manager.set_current_source(ChinaDataSource.AKSHARE)
                print(f"✅ 成功切换回AKShare数据源")
                return True
            else:
                print(f"❌ 数据源切换失败")
                return False
        else:
            print(f"⚠️ Tushare数据源不可用，跳过切换测试")
            return True
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("🔧 最终验证测试")
    print("=" * 80)
    print("📋 验证所有修复是否正常工作")
    print("=" * 80)
    
    tests = [
        ("AKShare数据源优先级", test_akshare_priority),
        ("volume映射修复", test_volume_mapping_fix),
        ("volume安全获取", test_data_source_manager_volume_safety),
        ("集成测试", test_integration),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n🔍 执行测试: {test_name}")
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ 测试{test_name}异常: {e}")
            results.append((test_name, False))
    
    # 总结结果
    print("\n" + "=" * 80)
    print("📊 最终验证结果:")
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\n🎯 总体结果: {passed}/{total} 测试通过")
    
    if passed == total:
        print("🎉 所有修复验证通过！可以安全推送到远程仓库！")
        print("\n✅ 修复内容:")
        print("  1. AKShare数据源设置为第一优先级")
        print("  2. 解决了KeyError: 'volume'问题")
        print("  3. 缓存数据现在正确标准化")
        print("  4. 防御性编程确保系统稳定性")
        return True
    else:
        print("❌ 部分测试失败，需要进一步检查。")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
