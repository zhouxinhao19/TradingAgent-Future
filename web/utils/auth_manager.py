"""
用户认证管理器
处理用户登录、权限验证等功能
"""

import streamlit as st
import hashlib
import os
import json
from pathlib import Path
from typing import Dict, Optional, Tuple
import time

# 导入日志模块
from tradingagents.utils.logging_manager import get_logger
logger = get_logger('auth')

# 导入用户活动记录器
try:
    from .user_activity_logger import user_activity_logger
except ImportError:
    user_activity_logger = None
    logger.warning("⚠️ 用户活动记录器导入失败")

class AuthManager:
    """用户认证管理器"""
    
    def __init__(self):
        self.users_file = Path(__file__).parent.parent / "config" / "users.json"
        self.session_timeout = 3600  # 1小时超时
        self._ensure_users_file()
    
    def _ensure_users_file(self):
        """确保用户配置文件存在"""
        self.users_file.parent.mkdir(exist_ok=True)
        
        if not self.users_file.exists():
            # 创建默认用户配置
            default_users = {
                "admin": {
                    "password_hash": self._hash_password("admin123"),
                    "role": "admin",
                    "permissions": ["analysis", "config", "admin"],
                    "created_at": time.time()
                },
                "user": {
                    "password_hash": self._hash_password("user123"),
                    "role": "user", 
                    "permissions": ["analysis"],
                    "created_at": time.time()
                }
            }
            
            with open(self.users_file, 'w', encoding='utf-8') as f:
                json.dump(default_users, f, indent=2, ensure_ascii=False)
            
            logger.info(f"✅ 用户认证系统初始化完成")
            logger.info(f"📁 用户配置文件: {self.users_file}")
    
    def _hash_password(self, password: str) -> str:
        """密码哈希"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def _load_users(self) -> Dict:
        """加载用户配置"""
        try:
            with open(self.users_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"❌ 加载用户配置失败: {e}")
            return {}
    
    def authenticate(self, username: str, password: str) -> Tuple[bool, Optional[Dict]]:
        """
        用户认证
        
        Args:
            username: 用户名
            password: 密码
            
        Returns:
            (认证成功, 用户信息)
        """
        users = self._load_users()
        
        if username not in users:
            logger.warning(f"⚠️ 用户不存在: {username}")
            # 记录登录失败
            if user_activity_logger:
                user_activity_logger.log_login(username, False, "用户不存在")
            return False, None
        
        user_info = users[username]
        password_hash = self._hash_password(password)
        
        if password_hash == user_info["password_hash"]:
            logger.info(f"✅ 用户登录成功: {username}")
            # 记录登录成功
            if user_activity_logger:
                user_activity_logger.log_login(username, True)
            return True, {
                "username": username,
                "role": user_info["role"],
                "permissions": user_info["permissions"]
            }
        else:
            logger.warning(f"⚠️ 密码错误: {username}")
            # 记录登录失败
            if user_activity_logger:
                user_activity_logger.log_login(username, False, "密码错误")
            return False, None
    
    def check_permission(self, permission: str) -> bool:
        """
        检查当前用户权限
        
        Args:
            permission: 权限名称
            
        Returns:
            是否有权限
        """
        if not self.is_authenticated():
            return False
        
        user_info = st.session_state.get('user_info', {})
        permissions = user_info.get('permissions', [])
        
        return permission in permissions
    
    def is_authenticated(self) -> bool:
        """检查用户是否已认证"""
        if 'authenticated' not in st.session_state:
            return False
        
        if not st.session_state.authenticated:
            return False
        
        # 检查会话超时
        login_time = st.session_state.get('login_time', 0)
        if time.time() - login_time > self.session_timeout:
            self.logout()
            return False
        
        return True
    
    def login(self, username: str, password: str) -> bool:
        """
        用户登录
        
        Args:
            username: 用户名
            password: 密码
            
        Returns:
            登录是否成功
        """
        success, user_info = self.authenticate(username, password)
        
        if success:
            st.session_state.authenticated = True
            st.session_state.user_info = user_info
            st.session_state.login_time = time.time()
            logger.info(f"✅ 用户 {username} 登录成功")
            return True
        else:
            st.session_state.authenticated = False
            st.session_state.user_info = None
            return False
    
    def logout(self):
        """用户登出"""
        username = st.session_state.get('user_info', {}).get('username', 'unknown')
        st.session_state.authenticated = False
        st.session_state.user_info = None
        st.session_state.login_time = None
        logger.info(f"✅ 用户 {username} 登出")
        
        # 记录登出活动
        if user_activity_logger:
            user_activity_logger.log_logout(username)
    
    def get_current_user(self) -> Optional[Dict]:
        """获取当前用户信息"""
        if self.is_authenticated():
            return st.session_state.get('user_info')
        return None
    
    def require_permission(self, permission: str) -> bool:
        """
        要求特定权限，如果没有权限则显示错误信息
        
        Args:
            permission: 权限名称
            
        Returns:
            是否有权限
        """
        if not self.check_permission(permission):
            st.error(f"❌ 您没有 '{permission}' 权限，请联系管理员")
            return False
        return True

# 全局认证管理器实例
auth_manager = AuthManager()