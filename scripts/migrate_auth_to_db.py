#!/usr/bin/env python3
"""
认证系统迁移脚本
将基于配置文件的认证迁移到基于数据库的认证
"""

import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.services.user_service import user_service

# 尝试导入日志管理器
try:
    from tradingagents.utils.logging_manager import get_logger
except ImportError:
    # 如果导入失败，使用标准日志
    import logging
    def get_logger(name: str) -> logging.Logger:
        return logging.getLogger(name)

logger = get_logger('auth_migration')

async def migrate_config_file_auth():
    """迁移配置文件认证到数据库"""
    logger.info("🔄 开始认证系统迁移...")
    
    try:
        # 1. 读取现有的配置文件密码
        config_file = project_root / "config" / "admin_password.json"
        admin_password = "CHANGE_ME_ADMIN_PASSWORD"  # 默认密码
        
        if config_file.exists():
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    admin_password = config.get("password", "CHANGE_ME_ADMIN_PASSWORD")
                logger.info(f"✅ 从配置文件读取管理员密码")
            except Exception as e:
                logger.warning(f"⚠️ 读取配置文件失败，使用默认密码: {e}")
        else:
            logger.info("⚠️ 配置文件不存在，使用默认密码")
        
        # 2. 创建或更新数据库中的管理员用户
        admin_user = await user_service.create_admin_user(
            username="admin",
            password=admin_password,
            email="admin@tradingagents.cn"
        )
        
        if admin_user:
            logger.info("✅ 管理员用户已创建/更新到数据库")
            logger.info(f"   用户名: admin")
            logger.info(f"   密码: {admin_password}")
        else:
            logger.error("❌ 创建管理员用户失败")
            return False
        
        # 3. 迁移 Web 应用用户配置
        await migrate_web_users()
        
        # 4. 备份原配置文件
        await backup_config_files()
        
        logger.info("✅ 认证系统迁移完成！")
        logger.info("\n📋 迁移后的登录信息:")
        logger.info(f"- 用户名: admin")
        logger.info(f"- 密码: {admin_password}")
        logger.info("\n⚠️  重要提醒:")
        logger.info("1. 原配置文件已备份到 config/backup/ 目录")
        logger.info("2. 现在可以使用新的基于数据库的认证 API")
        logger.info("3. 建议立即修改默认密码")
        logger.info("4. 可以通过 API 创建更多用户")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 认证系统迁移失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def migrate_web_users():
    """迁移 Web 应用用户配置"""
    logger.info("👤 迁移 Web 应用用户配置...")
    
    try:
        web_users_file = project_root / "web" / "config" / "users.json"
        
        if not web_users_file.exists():
            logger.info("⚠️ Web 用户配置文件不存在，跳过迁移")
            return
        
        # 读取 Web 用户配置
        with open(web_users_file, "r", encoding="utf-8") as f:
            web_users = json.load(f)
        
        # 迁移每个用户
        for username, user_info in web_users.items():
            if username == "admin":
                # 管理员用户已经处理过了
                continue
            
            # 检查用户是否已存在
            existing_user = await user_service.get_user_by_username(username)
            if existing_user:
                logger.info(f"✓ 用户 {username} 已存在，跳过")
                continue
            
            # 创建用户（需要从哈希密码推导，这里使用默认密码）
            # 注意：由于原密码已经哈希，无法直接迁移，使用默认密码
            default_password = f"{username}123"  # 默认密码规则
            
            from app.models.user import UserCreate
            user_create = UserCreate(
                username=username,
                email=f"{username}@tradingagents.cn",
                password=default_password
            )
            
            new_user = await user_service.create_user(user_create)
            if new_user:
                logger.info(f"✅ 用户 {username} 迁移成功，默认密码: {default_password}")
            else:
                logger.warning(f"⚠️ 用户 {username} 迁移失败")
        
        logger.info("✅ Web 用户配置迁移完成")
        
    except Exception as e:
        logger.error(f"❌ Web 用户配置迁移失败: {e}")

async def backup_config_files():
    """备份原配置文件"""
    logger.info("💾 备份原配置文件...")
    
    try:
        backup_dir = project_root / "config" / "backup"
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 备份管理员密码配置
        config_file = project_root / "config" / "admin_password.json"
        if config_file.exists():
            backup_file = backup_dir / f"admin_password_{timestamp}.json"
            import shutil
            shutil.copy2(config_file, backup_file)
            logger.info(f"✅ 备份管理员密码配置: {backup_file}")
        
        # 备份 Web 用户配置
        web_users_file = project_root / "web" / "config" / "users.json"
        if web_users_file.exists():
            backup_file = backup_dir / f"web_users_{timestamp}.json"
            import shutil
            shutil.copy2(web_users_file, backup_file)
            logger.info(f"✅ 备份 Web 用户配置: {backup_file}")
        
        logger.info("✅ 配置文件备份完成")
        
    except Exception as e:
        logger.error(f"❌ 备份配置文件失败: {e}")

async def verify_migration():
    """验证迁移结果"""
    logger.info("🔍 验证迁移结果...")
    
    try:
        # 验证管理员用户
        admin_user = await user_service.get_user_by_username("admin")
        if admin_user:
            logger.info("✅ 管理员用户验证成功")
            logger.info(f"   用户名: {admin_user.username}")
            logger.info(f"   邮箱: {admin_user.email}")
            logger.info(f"   是否管理员: {admin_user.is_admin}")
            logger.info(f"   是否激活: {admin_user.is_active}")
        else:
            logger.error("❌ 管理员用户验证失败")
            return False
        
        # 测试认证
        config_file = project_root / "config" / "admin_password.json"
        admin_password = "CHANGE_ME_ADMIN_PASSWORD"
        
        if config_file.exists():
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    admin_password = config.get("password", "CHANGE_ME_ADMIN_PASSWORD")
            except:
                pass
        
        auth_user = await user_service.authenticate_user("admin", admin_password)
        if auth_user:
            logger.info("✅ 管理员认证测试成功")
        else:
            logger.error("❌ 管理员认证测试失败")
            return False
        
        # 获取用户列表
        users = await user_service.list_users()
        logger.info(f"✅ 数据库中共有 {len(users)} 个用户")
        for user in users:
            logger.info(f"   - {user.username} ({user.email}) - {'管理员' if user.is_admin else '普通用户'}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 验证迁移结果失败: {e}")
        return False

async def create_migration_guide():
    """创建迁移指南"""
    logger.info("📖 创建迁移指南...")
    
    try:
        guide_content = """# 认证系统迁移指南

## 迁移完成

✅ 认证系统已成功从配置文件迁移到数据库！

## 主要变化

### 1. 用户数据存储
- **之前**: 存储在 `config/admin_password.json` 和 `web/config/users.json`
- **现在**: 存储在 MongoDB 数据库的 `users` 集合中

### 2. 密码安全性
- **之前**: 明文存储（后端）或 SHA-256 哈希（Web）
- **现在**: 统一使用 SHA-256 哈希存储

### 3. API 端点
- **新的认证 API**: `/api/auth-db/` 前缀
- **支持的操作**:
  - 登录: `POST /api/auth-db/login`
  - 刷新令牌: `POST /api/auth-db/refresh`
  - 修改密码: `POST /api/auth-db/change-password`
  - 重置密码: `POST /api/auth-db/reset-password` (管理员)
  - 创建用户: `POST /api/auth-db/create-user` (管理员)
  - 用户列表: `GET /api/auth-db/users` (管理员)

## 使用新的认证系统

### 1. 更新前端配置
将前端的认证 API 端点从 `/api/auth/` 更改为 `/api/auth-db/`

### 2. 管理用户
现在可以通过 API 动态创建、管理用户，不再需要手动编辑配置文件。

### 3. 密码管理
- 用户可以通过 API 修改自己的密码
- 管理员可以重置任何用户的密码

## 备份文件
原配置文件已备份到 `config/backup/` 目录，包含时间戳。

## 安全建议
1. 立即修改默认密码
2. 为其他用户设置强密码
3. 定期备份数据库
4. 考虑启用更强的密码哈希算法（如 bcrypt）

## 回滚方案
如果需要回滚到原系统：
1. 停止使用新的 `/api/auth-db/` 端点
2. 从 `config/backup/` 恢复配置文件
3. 重新使用原有的 `/api/auth/` 端点
"""
        
        guide_file = project_root / "docs" / "auth_migration_guide.md"
        with open(guide_file, "w", encoding="utf-8") as f:
            f.write(guide_content)
        
        logger.info(f"✅ 迁移指南已创建: {guide_file}")
        
    except Exception as e:
        logger.error(f"❌ 创建迁移指南失败: {e}")

async def main():
    """主函数"""
    logger.info("🚀 认证系统迁移工具")
    logger.info("=" * 60)
    logger.info("此工具将把基于配置文件的认证迁移到基于数据库的认证")
    logger.info()
    
    try:
        # 1. 执行迁移
        if not await migrate_config_file_auth():
            logger.error("❌ 迁移失败")
            return False
        
        # 2. 验证迁移结果
        if not await verify_migration():
            logger.error("❌ 迁移验证失败")
            return False
        
        # 3. 创建迁移指南
        await create_migration_guide()
        
        logger.info("\n" + "=" * 60)
        logger.info("✅ 认证系统迁移成功完成！")
        logger.info("=" * 60)
        
        logger.info("\n📋 下一步操作:")
        logger.info("1. 更新前端配置，使用新的认证 API 端点")
        logger.info("2. 测试登录功能")
        logger.info("3. 修改默认密码")
        logger.info("4. 创建其他用户账号")
        logger.info("5. 查看迁移指南: docs/auth_migration_guide.md")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 迁移过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
