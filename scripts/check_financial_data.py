import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import get_mongo_db, init_database

async def main():
    await init_database()
    db = get_mongo_db()
    
    # 检查 stock_financial_data 集合
    print("🔍 检查 stock_financial_data 集合...")
    
    codes = ['601398', '300033', '000001']
    
    for code in codes:
        doc = await db['stock_financial_data'].find_one({'code': code})
        if doc:
            print(f"\n✅ {code} ({doc.get('name')}):")
            print(f"  更新时间: {doc.get('updated_at')}")
            
            # 检查财务指标
            indicators = doc.get('financial_indicators', [])
            if indicators:
                print(f"  财务指标记录数: {len(indicators)}")
                # 显示最新一期
                latest = indicators[0] if indicators else {}
                print(f"  最新一期:")
                print(f"    报告期: {latest.get('end_date')}")
                print(f"    ROE: {latest.get('roe')}")
                print(f"    净利润率: {latest.get('netprofit_margin')}")
                print(f"    总资产收益率: {latest.get('roa')}")
            else:
                print(f"  ⚠️ 无财务指标数据")
        else:
            print(f"\n❌ {code}: 未找到财务数据")
    
    # 统计总数
    total = await db['stock_financial_data'].count_documents({})
    print(f"\n📊 stock_financial_data 集合总记录数: {total}")

if __name__ == '__main__':
    asyncio.run(main())

