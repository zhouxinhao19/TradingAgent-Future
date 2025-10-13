#!/usr/bin/env python3
"""
MongoDB连接测试脚本
"""
import os
import sys
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

def test_mongodb_connection():
    """测试MongoDB连接"""
    print("🔍 测试MongoDB连接...")
    
    # 从环境变量读取配置
    host = os.getenv("MONGODB_HOST", "localhost")
    port = int(os.getenv("MONGODB_PORT", "27017"))
    username = os.getenv("MONGODB_USERNAME", "admin")
    password = os.getenv("MONGODB_PASSWORD", "tradingagents123")
    database = os.getenv("MONGODB_DATABASE", "tradingagents")
    auth_source = os.getenv("MONGODB_AUTH_SOURCE", "admin")
    
    print(f"📊 连接配置:")
    print(f"   Host: {host}")
    print(f"   Port: {port}")
    print(f"   Username: {username}")
    print(f"   Password: {'***' if password else '未设置'}")
    print(f"   Database: {database}")
    print(f"   Auth Source: {auth_source}")
    
    try:
        # 构建连接字符串
        if username and password:
            connection_string = f"mongodb://{username}:{password}@{host}:{port}/?authSource={auth_source}"
        else:
            connection_string = f"mongodb://{host}:{port}/"
        
        print(f"🔗 连接字符串: {connection_string.replace(password, '***' if password else '')}")
        
        # 创建客户端
        client = MongoClient(
            connection_string,
            serverSelectionTimeoutMS=5000,  # 5秒超时
            connectTimeoutMS=5000
        )
        
        # 测试连接
        client.admin.command('ping')
        print("✅ MongoDB连接成功!")
        
        # 测试数据库访问
        db = client[database]
        collections = db.list_collection_names()
        print(f"📁 数据库 '{database}' 中的集合: {collections}")
        
        # 测试写入权限
        test_collection = db.test_connection
        test_doc = {"test": "connection", "timestamp": "2024-01-01"}
        result = test_collection.insert_one(test_doc)
        print(f"✅ 写入测试成功，文档ID: {result.inserted_id}")
        
        # 清理测试文档
        test_collection.delete_one({"_id": result.inserted_id})
        print("🧹 清理测试文档完成")
        
        client.close()
        return True
        
    except ConnectionFailure as e:
        print(f"❌ MongoDB连接失败: {e}")
        return False
    except ServerSelectionTimeoutError as e:
        print(f"❌ MongoDB服务器选择超时: {e}")
        print("💡 可能的原因:")
        print("   1. MongoDB服务未启动")
        print("   2. 网络连接问题")
        print("   3. 防火墙阻止连接")
        return False
    except Exception as e:
        print(f"❌ MongoDB连接出现未知错误: {e}")
        return False

if __name__ == "__main__":
    success = test_mongodb_connection()
    sys.exit(0 if success else 1)