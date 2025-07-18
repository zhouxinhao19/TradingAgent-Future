"""
基于文件的会话管理器 - 不依赖Redis的可靠方案
适用于没有Redis或Redis连接失败的情况
"""

import streamlit as st
import json
import time
import hashlib
import os
import uuid
from typing import Optional, Dict, Any
from pathlib import Path

class FileSessionManager:
    """基于文件的会话管理器"""
    
    def __init__(self):
        self.data_dir = Path("./data/sessions")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.max_age_hours = 24  # 会话有效期24小时
        
    def _get_browser_fingerprint(self) -> str:
        """生成浏览器指纹"""
        try:
            # 方法1：尝试从Streamlit获取session信息
            if hasattr(st, 'session_state'):
                # 使用Streamlit内部的session信息
                session_info = str(st.session_state)
                if session_info and len(session_info) > 10:
                    fingerprint = hashlib.md5(session_info.encode()).hexdigest()[:16]
                    return f"st_{fingerprint}"
            
            # 方法2：使用时间窗口 + 随机数（按小时分组）
            hour_window = int(time.time() / 3600)  # 按小时分组
            
            # 检查是否已经有这个时间窗口的session文件
            pattern = f"time_{hour_window}_*.json"
            existing_files = list(self.data_dir.glob(pattern))
            
            if existing_files:
                # 使用现有的session文件
                filename = existing_files[0].stem
                return filename.replace('.json', '')
            else:
                # 创建新的session
                random_id = uuid.uuid4().hex[:8]
                return f"time_{hour_window}_{random_id}"
                
        except Exception:
            # 方法3：最后的fallback
            timestamp = int(time.time() / 1800)  # 30分钟窗口
            return f"fallback_{timestamp}"
    
    def _get_session_file_path(self, fingerprint: str) -> Path:
        """获取会话文件路径"""
        return self.data_dir / f"{fingerprint}.json"
    
    def _cleanup_old_sessions(self):
        """清理过期的会话文件"""
        try:
            current_time = time.time()
            max_age_seconds = self.max_age_hours * 3600
            
            for session_file in self.data_dir.glob("*.json"):
                try:
                    # 检查文件修改时间
                    file_age = current_time - session_file.stat().st_mtime
                    if file_age > max_age_seconds:
                        session_file.unlink()
                except Exception:
                    continue
                    
        except Exception:
            pass  # 清理失败不影响主要功能
    
    def save_analysis_state(self, analysis_id: str, status: str = "running",
                           stock_symbol: str = "", market_type: str = "",
                           form_config: Dict[str, Any] = None):
        """保存分析状态和表单配置"""
        try:
            # 清理过期文件
            self._cleanup_old_sessions()

            fingerprint = self._get_browser_fingerprint()
            session_file = self._get_session_file_path(fingerprint)

            session_data = {
                "analysis_id": analysis_id,
                "status": status,
                "stock_symbol": stock_symbol,
                "market_type": market_type,
                "timestamp": time.time(),
                "last_update": time.time(),
                "fingerprint": fingerprint
            }

            # 添加表单配置
            if form_config:
                session_data["form_config"] = form_config
            
            # 保存到文件
            with open(session_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)
            
            # 同时保存到session state
            st.session_state.current_analysis_id = analysis_id
            st.session_state.analysis_running = (status == 'running')
            st.session_state.last_stock_symbol = stock_symbol
            st.session_state.last_market_type = market_type
            st.session_state.session_fingerprint = fingerprint
            
            return True
            
        except Exception as e:
            st.warning(f"⚠️ 保存会话状态失败: {e}")
            return False
    
    def load_analysis_state(self) -> Optional[Dict[str, Any]]:
        """加载分析状态"""
        try:
            fingerprint = self._get_browser_fingerprint()
            session_file = self._get_session_file_path(fingerprint)
            
            # 检查文件是否存在
            if not session_file.exists():
                return None
            
            # 读取会话数据
            with open(session_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
            
            # 检查是否过期
            timestamp = session_data.get("timestamp", 0)
            if time.time() - timestamp > (self.max_age_hours * 3600):
                # 过期了，删除文件
                session_file.unlink()
                return None
            
            return session_data
            
        except Exception as e:
            st.warning(f"⚠️ 加载会话状态失败: {e}")
            return None
    
    def clear_analysis_state(self):
        """清除分析状态"""
        try:
            fingerprint = self._get_browser_fingerprint()
            session_file = self._get_session_file_path(fingerprint)
            
            # 删除文件
            if session_file.exists():
                session_file.unlink()
            
            # 清除session state
            keys_to_remove = ['current_analysis_id', 'analysis_running', 'last_stock_symbol', 'last_market_type', 'session_fingerprint']
            for key in keys_to_remove:
                if key in st.session_state:
                    del st.session_state[key]
            
        except Exception as e:
            st.warning(f"⚠️ 清除会话状态失败: {e}")
    
    def get_debug_info(self) -> Dict[str, Any]:
        """获取调试信息"""
        try:
            fingerprint = self._get_browser_fingerprint()
            session_file = self._get_session_file_path(fingerprint)
            
            debug_info = {
                "fingerprint": fingerprint,
                "session_file": str(session_file),
                "file_exists": session_file.exists(),
                "data_dir": str(self.data_dir),
                "session_state_keys": [k for k in st.session_state.keys() if 'analysis' in k.lower() or 'session' in k.lower()]
            }
            
            # 统计会话文件数量
            session_files = list(self.data_dir.glob("*.json"))
            debug_info["total_session_files"] = len(session_files)
            debug_info["session_files"] = [f.name for f in session_files]
            
            if session_file.exists():
                try:
                    with open(session_file, 'r', encoding='utf-8') as f:
                        session_data = json.load(f)
                    debug_info["session_data"] = session_data
                    debug_info["age_hours"] = (time.time() - session_data.get("timestamp", 0)) / 3600
                except Exception as e:
                    debug_info["file_error"] = str(e)
            
            return debug_info
            
        except Exception as e:
            return {"error": str(e)}

# 全局文件会话管理器实例
file_session_manager = FileSessionManager()

def get_persistent_analysis_id() -> Optional[str]:
    """获取持久化的分析ID（优先级：session state > 文件会话 > Redis/文件）"""
    try:
        # 1. 首先检查session state
        if st.session_state.get('current_analysis_id'):
            return st.session_state.current_analysis_id
        
        # 2. 检查文件会话数据
        session_data = file_session_manager.load_analysis_state()
        if session_data:
            analysis_id = session_data.get('analysis_id')
            if analysis_id:
                # 恢复到session state
                st.session_state.current_analysis_id = analysis_id
                st.session_state.analysis_running = (session_data.get('status') == 'running')
                st.session_state.last_stock_symbol = session_data.get('stock_symbol', '')
                st.session_state.last_market_type = session_data.get('market_type', '')
                st.session_state.session_fingerprint = session_data.get('fingerprint', '')
                return analysis_id
        
        # 3. 最后从Redis/文件恢复最新分析
        try:
            from .async_progress_tracker import get_latest_analysis_id
            latest_id = get_latest_analysis_id()
            if latest_id:
                st.session_state.current_analysis_id = latest_id
                return latest_id
        except Exception:
            pass
        
        return None
        
    except Exception as e:
        st.warning(f"⚠️ 获取持久化分析ID失败: {e}")
        return None

def set_persistent_analysis_id(analysis_id: str, status: str = "running", 
                              stock_symbol: str = "", market_type: str = ""):
    """设置持久化的分析ID"""
    try:
        # 设置到session state
        st.session_state.current_analysis_id = analysis_id
        st.session_state.analysis_running = (status == 'running')
        st.session_state.last_stock_symbol = stock_symbol
        st.session_state.last_market_type = market_type
        
        # 保存到文件会话
        file_session_manager.save_analysis_state(analysis_id, status, stock_symbol, market_type)
        
    except Exception as e:
        st.warning(f"⚠️ 设置持久化分析ID失败: {e}")
