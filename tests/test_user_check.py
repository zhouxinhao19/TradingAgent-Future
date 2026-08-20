"""检查用户数据库"""
from pymongo import MongoClient

# 直接连接 MongoDB
mongo_uri = "mongodb://admin:CHANGE_ME_LOCAL_PASSWORD@localhost:27017/"
client = MongoClient(mongo_uri)

print(f"🔍 MongoDB URI: {mongo_uri}")
print()

# 列出所有数据库
print("📊 所有数据库:")
for db_name in client.list_database_names():
    print(f"  - {db_name}")
print()

# 检查两个可能的数据库
for db_name in ["tradingagents"]:
    print(f"=" * 60)
    print(f"🔍 检查数据库: {db_name}")
    print(f"=" * 60)

    db = client[db_name]

    # 列出所有集合
    collections = db.list_collection_names()
    print(f"📁 集合列表: {collections}")
    print()

    if "users" in collections:
        # 查询所有用户
        users = list(db.users.find({}))
        print(f"📊 找到 {len(users)} 个用户:")
        print()

        for user in users:
            print(f"用户名: {user.get('username')}")
            print(f"  - ID: {user.get('_id')}")
            print(f"  - Email: {user.get('email')}")
            print(f"  - 激活状态: {user.get('is_active')}")
            print(f"  - 管理员: {user.get('is_admin')}")
            print(f"  - 密码哈希: {user.get('hashed_password', '')[:20]}...")
            print()

        # 测试查询 admin 用户
        print("🔍 测试查询 admin 用户:")
        admin_user = db.users.find_one({"username": "admin"})
        if admin_user:
            print(f"✅ 找到 admin 用户:")
            print(f"  - ID: {admin_user.get('_id')}")
            print(f"  - Email: {admin_user.get('email')}")
            print(f"  - 激活状态: {admin_user.get('is_active')}")
        else:
            print("❌ 未找到 admin 用户")
    else:
        print("⚠️ 没有 users 集合")

    print()

client.close()

