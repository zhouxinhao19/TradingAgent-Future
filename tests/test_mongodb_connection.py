#!/usr/bin/env python3
"""
测试MongoDB连接和现有用户
"""

from pymongo import MongoClient
from pymongo.errors import OperationFailure, ServerSelectionTimeoutError

def test_connections():
    """测试不同的MongoDB连接"""
    
    # 测试连接配置
    test_configs = [
        {
            "name": "Docker配置 (admin/CHANGE_ME_LOCAL_PASSWORD)",
            "uri": "mongodb://admin:CHANGE_ME_LOCAL_PASSWORD@localhost:27017/tradingagents?authSource=admin"
        },
        {
            "name": "之前导入时使用的配置",
            "uri": "mongodb://admin:CHANGE_ME_ADMIN_PASSWORD@localhost:27017/tradingagents?authSource=admin"
        },
        {
            "name": "无认证连接",
            "uri": "mongodb://localhost:27017/"
        }
    ]
    
    for config in test_configs:
        print(f"\n🔍 测试: {config['name']}")
        print(f"URI: {config['uri']}")
        
        try:
            client = MongoClient(config['uri'], serverSelectionTimeoutMS=5000)
            
            # 尝试ping
            client.admin.command('ping')
            print("✅ 连接成功")
            
            # 列出数据库
            dbs = client.list_database_names()
            print(f"📊 可用数据库: {dbs}")
            
            # 如果有tradingagents数据库，列出集合
            if 'tradingagents' in dbs:
                collections = client.tradingagents.list_collection_names()
                print(f"📁 tradingagents数据库中的集合: {collections}")
                
                # 检查system_configs集合的文档数量
                if 'system_configs' in collections:
                    count = client.tradingagents.system_configs.count_documents({})
                    print(f"📄 system_configs集合中的文档数量: {count}")
            
            client.close()
            return config
            
        except OperationFailure as e:
            print(f"❌ 认证失败: {e}")
        except ServerSelectionTimeoutError as e:
            print(f"❌ 连接超时: {e}")
        except Exception as e:
            print(f"❌ 连接失败: {e}")
    
    return None

if __name__ == "__main__":
    print("🔧 测试MongoDB连接...")
    working_config = test_connections()
    
    if working_config:
        print(f"\n✅ 找到可用配置: {working_config['name']}")
    else:
        print("\n❌ 没有找到可用的连接配置")