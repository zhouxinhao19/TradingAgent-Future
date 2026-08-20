#!/usr/bin/env python3
"""检查数据库中的 config_reports 集合"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

async def check_config_reports():
    """检查 config_reports 集合"""
    load_dotenv()
    
    # 连接 MongoDB
    mongo_uri = os.getenv("MONGODB_CONNECTION_STRING", "mongodb://admin:CHANGE_ME_LOCAL_PASSWORD@127.0.0.1:27017/")
    db_name = os.getenv("MONGODB_DATABASE_NAME", "tradingagents")
    
    print(f"📊 连接数据库: {db_name}")
    
    client = AsyncIOMotorClient(mongo_uri)
    db = client[db_name]
    
    try:
        # 列出所有集合
        collections = await db.list_collection_names()
        print(f"\n=== 数据库中的所有集合 ({len(collections)}) ===")
        for coll in sorted(collections):
            if not coll.startswith("system."):
                count = await db[coll].count_documents({})
                print(f"  - {coll}: {count} 条文档")
        
        # 检查 config_reports
        print(f"\n=== 检查 config_reports 集合 ===")
        if "config_reports" in collections:
            count = await db.config_reports.count_documents({})
            print(f"✅ config_reports 集合存在: {count} 条文档")
            
            if count > 0:
                # 显示第一条数据
                first_doc = await db.config_reports.find_one()
                print(f"\n第一条数据的字段:")
                for key in first_doc.keys():
                    print(f"  - {key}")
        else:
            print(f"❌ config_reports 集合不存在")
        
        # 检查分析报告相关集合
        print(f"\n=== 分析报告相关集合 ===")
        report_collections = [
            "config_reports",
            "analysis_results",
            "analysis_tasks", 
            "debate_records"
        ]
        
        for coll in report_collections:
            if coll in collections:
                count = await db[coll].count_documents({})
                print(f"  ✅ {coll}: {count} 条")
            else:
                print(f"  ❌ {coll}: 不存在")
        
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(check_config_reports())

