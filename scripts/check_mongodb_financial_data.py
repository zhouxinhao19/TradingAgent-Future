"""
检查 MongoDB 中的财务数据
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def check_mongodb_data():
    """检查 MongoDB 中的财务数据"""
    print("=" * 70)
    print("🔍 检查 MongoDB 财务数据")
    print("=" * 70)

    test_symbol = "601288"  # 农业银行

    try:
        # 导入数据库连接
        print("\n📦 步骤1: 连接 MongoDB...")
        from pymongo import MongoClient

        # 直接连接 MongoDB
        client = MongoClient("mongodb://admin:CHANGE_ME_LOCAL_PASSWORD@localhost:27017/")
        db = client["tradingagents"]
        print(f"✅ MongoDB 连接成功")
        
        # 检查 stock_financial_data 集合
        print(f"\n📊 步骤2: 检查 stock_financial_data 集合...")
        
        # 查询数据
        financial_data = db.stock_financial_data.find_one(
            {"symbol": test_symbol},
            sort=[("report_period", -1)]  # 按报告期降序
        )
        
        if financial_data:
            print(f"✅ 找到 {test_symbol} 的财务数据")
            print(f"\n📋 数据结构:")
            print(f"   字段列表: {list(financial_data.keys())}")
            
            # 显示关键字段
            print(f"\n📊 关键字段:")
            print(f"   symbol: {financial_data.get('symbol')}")
            print(f"   report_period: {financial_data.get('report_period')}")
            print(f"   data_source: {financial_data.get('data_source')}")
            print(f"   updated_at: {financial_data.get('updated_at')}")
            
            # 检查财务指标
            if 'balance_sheet' in financial_data:
                print(f"   ✅ balance_sheet: {type(financial_data['balance_sheet'])}")
            if 'income_statement' in financial_data:
                print(f"   ✅ income_statement: {type(financial_data['income_statement'])}")
            if 'cash_flow' in financial_data:
                print(f"   ✅ cash_flow: {type(financial_data['cash_flow'])}")
            if 'main_indicators' in financial_data:
                main_indicators = financial_data['main_indicators']
                print(f"   ✅ main_indicators: {type(main_indicators)}")
                if isinstance(main_indicators, list) and len(main_indicators) > 0:
                    print(f"      数量: {len(main_indicators)}")
                    print(f"      第一条数据字段: {list(main_indicators[0].keys())}")
                elif isinstance(main_indicators, dict):
                    print(f"      字段: {list(main_indicators.keys())}")
            
            # 显示完整数据（截断）
            print(f"\n📄 完整数据（前500字符）:")
            import json
            data_str = json.dumps(financial_data, default=str, ensure_ascii=False)
            print(data_str[:500])
            print("...")
            
        else:
            print(f"❌ 未找到 {test_symbol} 的财务数据")
            
            # 检查是否有其他股票的数据
            print(f"\n🔍 检查集合中是否有其他数据...")
            count = db.stock_financial_data.count_documents({})
            print(f"   集合总记录数: {count}")

            if count > 0:
                # 显示一条示例数据
                sample = db.stock_financial_data.find_one()
                print(f"\n📋 示例数据:")
                print(f"   symbol: {sample.get('symbol')}")
                print(f"   report_period: {sample.get('report_period')}")
                print(f"   字段列表: {list(sample.keys())}")
        
        # 测试 mongodb_cache_adapter
        print(f"\n" + "=" * 70)
        print(f"📦 步骤3: 测试 mongodb_cache_adapter...")
        print("=" * 70)
        
        from tradingagents.dataflows.cache.mongodb_cache_adapter import get_mongodb_cache_adapter
        
        adapter = get_mongodb_cache_adapter()
        print(f"✅ Adapter 初始化成功")
        print(f"   use_app_cache: {adapter.use_app_cache}")
        
        # 调用 get_financial_data
        print(f"\n🔍 调用 adapter.get_financial_data('{test_symbol}')...")
        result = adapter.get_financial_data(test_symbol)
        
        if result:
            print(f"✅ 返回数据")
            print(f"   类型: {type(result)}")
            if isinstance(result, dict):
                print(f"   字段: {list(result.keys())}")
            elif isinstance(result, list):
                print(f"   长度: {len(result)}")
        else:
            print(f"❌ 返回 None 或空值")
            print(f"   返回值: {result}")
        
        print("\n" + "=" * 70)
        print("✅ 检查完成")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    check_mongodb_data()

