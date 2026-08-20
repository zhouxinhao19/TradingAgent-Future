// MongoDB 初始化脚本 - 调试版本
// 用于排查初始化问题

print('========================================');
print('🔍 MongoDB 初始化脚本开始执行');
print('========================================');

// 检查环境变量
print('\n📋 环境变量检查:');
print('MONGO_INITDB_ROOT_USERNAME: ' + (typeof MONGO_INITDB_ROOT_USERNAME !== 'undefined' ? MONGO_INITDB_ROOT_USERNAME : '未设置'));
print('MONGO_INITDB_ROOT_PASSWORD: ' + (typeof MONGO_INITDB_ROOT_PASSWORD !== 'undefined' ? '已设置' : '未设置'));
print('MONGO_INITDB_DATABASE: ' + (typeof MONGO_INITDB_DATABASE !== 'undefined' ? MONGO_INITDB_DATABASE : '未设置'));

// 切换到 admin 数据库
print('\n📋 切换到 admin 数据库...');
db = db.getSiblingDB('admin');
print('✅ 当前数据库: ' + db.getName());

// 检查现有用户
print('\n📋 检查现有用户...');
try {
  var users = db.getUsers();
  print('现有用户数量: ' + users.users.length);
  if (users.users.length > 0) {
    print('用户列表:');
    users.users.forEach(function(user) {
      print('  - ' + user.user + ' (角色: ' + JSON.stringify(user.roles) + ')');
    });
  }
} catch (e) {
  print('⚠️  无法获取用户列表: ' + e.message);
}

// 创建 root 用户
print('\n📋 创建 root 用户 (admin)...');
try {
  db.createUser({
    user: 'admin',
    pwd: 'CHANGE_ME_LOCAL_PASSWORD',
    roles: [
      {
        role: 'root',
        db: 'admin'
      }
    ]
  });
  print('✅ root 用户创建成功');
} catch (e) {
  print('⚠️  用户可能已存在: ' + e.message);
}

// 创建应用用户
print('\n📋 创建应用用户 (tradingagents)...');
try {
  db.createUser({
    user: 'tradingagents',
    pwd: 'CHANGE_ME_LOCAL_PASSWORD',
    roles: [
      {
        role: 'readWrite',
        db: 'tradingagents'
      }
    ]
  });
  print('✅ 应用用户创建成功');
} catch (e) {
  print('⚠️  用户可能已存在: ' + e.message);
}

// 验证用户创建
print('\n📋 验证用户创建...');
try {
  var users = db.getUsers();
  print('当前用户数量: ' + users.users.length);
  users.users.forEach(function(user) {
    print('  ✅ ' + user.user + ' (角色: ' + JSON.stringify(user.roles) + ')');
  });
} catch (e) {
  print('❌ 无法验证用户: ' + e.message);
}

// 切换到应用数据库
print('\n📋 切换到应用数据库 (tradingagents)...');
db = db.getSiblingDB('tradingagents');
print('✅ 当前数据库: ' + db.getName());

// 创建测试集合
print('\n📋 创建测试集合...');
try {
  db.createCollection('test_collection');
  print('✅ 测试集合创建成功');
} catch (e) {
  print('❌ 集合创建失败: ' + e.message);
}

// 插入测试数据
print('\n📋 插入测试数据...');
try {
  db.test_collection.insertOne({
    message: 'MongoDB 初始化成功',
    timestamp: new Date()
  });
  print('✅ 测试数据插入成功');
} catch (e) {
  print('❌ 数据插入失败: ' + e.message);
}

// 验证数据
print('\n📋 验证数据...');
try {
  var count = db.test_collection.countDocuments();
  print('✅ 测试集合文档数量: ' + count);
} catch (e) {
  print('❌ 数据验证失败: ' + e.message);
}

print('\n========================================');
print('✅ MongoDB 初始化脚本执行完成');
print('========================================');

