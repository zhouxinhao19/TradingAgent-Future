"""
日志导出服务
提供日志文件的查询、过滤和导出功能
"""

import logging
import os
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any
import re
import json

logger = logging.getLogger("webapi")


class LogExportService:
    """日志导出服务"""

    def __init__(self, log_dir: str = "./logs"):
        """
        初始化日志导出服务
        
        Args:
            log_dir: 日志文件目录
        """
        self.log_dir = Path(log_dir)
        if not self.log_dir.exists():
            logger.warning(f"日志目录不存在: {self.log_dir}")
            self.log_dir.mkdir(parents=True, exist_ok=True)

    def list_log_files(self) -> List[Dict[str, Any]]:
        """
        列出所有日志文件
        
        Returns:
            日志文件列表，包含文件名、大小、修改时间等信息
        """
        log_files = []
        
        try:
            for file_path in self.log_dir.glob("*.log*"):
                if file_path.is_file():
                    stat = file_path.stat()
                    log_files.append({
                        "name": file_path.name,
                        "path": str(file_path),
                        "size": stat.st_size,
                        "size_mb": round(stat.st_size / (1024 * 1024), 2),
                        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "type": self._get_log_type(file_path.name)
                    })
            
            # 按修改时间倒序排序
            log_files.sort(key=lambda x: x["modified_at"], reverse=True)
            
            logger.info(f"📋 找到 {len(log_files)} 个日志文件")
            return log_files
            
        except Exception as e:
            logger.error(f"❌ 列出日志文件失败: {e}")
            return []

    def _get_log_type(self, filename: str) -> str:
        """
        根据文件名判断日志类型
        
        Args:
            filename: 文件名
            
        Returns:
            日志类型
        """
        if "error" in filename.lower():
            return "error"
        elif "webapi" in filename.lower():
            return "webapi"
        elif "worker" in filename.lower():
            return "worker"
        elif "access" in filename.lower():
            return "access"
        else:
            return "other"

    def read_log_file(
        self,
        filename: str,
        lines: int = 1000,
        level: Optional[str] = None,
        keyword: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        读取日志文件内容（支持过滤）
        
        Args:
            filename: 日志文件名
            lines: 读取的行数（从末尾开始）
            level: 日志级别过滤（ERROR, WARNING, INFO, DEBUG）
            keyword: 关键词过滤
            start_time: 开始时间（ISO格式）
            end_time: 结束时间（ISO格式）
            
        Returns:
            日志内容和统计信息
        """
        file_path = self.log_dir / filename
        
        if not file_path.exists():
            raise FileNotFoundError(f"日志文件不存在: {filename}")
        
        try:
            # 读取文件内容
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                all_lines = f.readlines()
            
            # 从末尾开始读取指定行数
            recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
            
            # 应用过滤器
            filtered_lines = []
            stats = {
                "total_lines": len(all_lines),
                "filtered_lines": 0,
                "error_count": 0,
                "warning_count": 0,
                "info_count": 0,
                "debug_count": 0
            }
            
            for line in recent_lines:
                # 统计日志级别
                if "ERROR" in line:
                    stats["error_count"] += 1
                elif "WARNING" in line:
                    stats["warning_count"] += 1
                elif "INFO" in line:
                    stats["info_count"] += 1
                elif "DEBUG" in line:
                    stats["debug_count"] += 1
                
                # 应用过滤条件
                if level and level.upper() not in line:
                    continue
                
                if keyword and keyword.lower() not in line.lower():
                    continue
                
                # 时间过滤（简单实现，假设日志格式为 YYYY-MM-DD HH:MM:SS）
                if start_time or end_time:
                    time_match = re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', line)
                    if time_match:
                        log_time = time_match.group()
                        if start_time and log_time < start_time:
                            continue
                        if end_time and log_time > end_time:
                            continue
                
                filtered_lines.append(line.rstrip())
            
            stats["filtered_lines"] = len(filtered_lines)
            
            return {
                "filename": filename,
                "lines": filtered_lines,
                "stats": stats
            }
            
        except Exception as e:
            logger.error(f"❌ 读取日志文件失败: {e}")
            raise

    def export_logs(
        self,
        filenames: Optional[List[str]] = None,
        level: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        format: str = "zip"
    ) -> str:
        """
        导出日志文件
        
        Args:
            filenames: 要导出的日志文件名列表（None表示导出所有）
            level: 日志级别过滤
            start_time: 开始时间
            end_time: 结束时间
            format: 导出格式（zip, txt）
            
        Returns:
            导出文件的路径
        """
        try:
            # 确定要导出的文件
            if filenames:
                files_to_export = [self.log_dir / f for f in filenames if (self.log_dir / f).exists()]
            else:
                files_to_export = list(self.log_dir.glob("*.log*"))
            
            if not files_to_export:
                raise ValueError("没有找到要导出的日志文件")
            
            # 创建导出目录
            export_dir = Path("./exports/logs")
            export_dir.mkdir(parents=True, exist_ok=True)
            
            # 生成导出文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            if format == "zip":
                export_path = export_dir / f"logs_export_{timestamp}.zip"
                
                # 创建ZIP文件
                with zipfile.ZipFile(export_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for file_path in files_to_export:
                        # 如果有过滤条件，先过滤再添加
                        if level or start_time or end_time:
                            filtered_data = self.read_log_file(
                                file_path.name,
                                lines=999999,  # 读取所有行
                                level=level,
                                start_time=start_time,
                                end_time=end_time
                            )
                            # 将过滤后的内容写入临时文件
                            temp_file = export_dir / f"temp_{file_path.name}"
                            with open(temp_file, 'w', encoding='utf-8') as f:
                                f.write('\n'.join(filtered_data['lines']))
                            zipf.write(temp_file, file_path.name)
                            temp_file.unlink()  # 删除临时文件
                        else:
                            zipf.write(file_path, file_path.name)
                
                logger.info(f"✅ 日志导出成功: {export_path}")
                return str(export_path)
            
            elif format == "txt":
                export_path = export_dir / f"logs_export_{timestamp}.txt"
                
                # 合并所有日志到一个文本文件
                with open(export_path, 'w', encoding='utf-8') as outf:
                    for file_path in files_to_export:
                        outf.write(f"\n{'='*80}\n")
                        outf.write(f"文件: {file_path.name}\n")
                        outf.write(f"{'='*80}\n\n")
                        
                        if level or start_time or end_time:
                            filtered_data = self.read_log_file(
                                file_path.name,
                                lines=999999,
                                level=level,
                                start_time=start_time,
                                end_time=end_time
                            )
                            outf.write('\n'.join(filtered_data['lines']))
                        else:
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as inf:
                                outf.write(inf.read())
                        
                        outf.write('\n\n')
                
                logger.info(f"✅ 日志导出成功: {export_path}")
                return str(export_path)
            
            else:
                raise ValueError(f"不支持的导出格式: {format}")
                
        except Exception as e:
            logger.error(f"❌ 导出日志失败: {e}")
            raise

    def get_log_statistics(self, days: int = 7) -> Dict[str, Any]:
        """
        获取日志统计信息
        
        Args:
            days: 统计最近几天的日志
            
        Returns:
            日志统计信息
        """
        try:
            cutoff_time = datetime.now() - timedelta(days=days)
            
            stats = {
                "total_files": 0,
                "total_size_mb": 0,
                "error_files": 0,
                "recent_errors": [],
                "log_types": {}
            }
            
            for file_path in self.log_dir.glob("*.log*"):
                if not file_path.is_file():
                    continue
                
                stat = file_path.stat()
                modified_time = datetime.fromtimestamp(stat.st_mtime)
                
                if modified_time < cutoff_time:
                    continue
                
                stats["total_files"] += 1
                stats["total_size_mb"] += stat.st_size / (1024 * 1024)
                
                log_type = self._get_log_type(file_path.name)
                stats["log_types"][log_type] = stats["log_types"].get(log_type, 0) + 1
                
                # 统计错误日志
                if log_type == "error":
                    stats["error_files"] += 1
                    # 读取最近的错误
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            lines = f.readlines()
                            error_lines = [line for line in lines[-100:] if "ERROR" in line]
                            stats["recent_errors"].extend(error_lines[-10:])
                    except Exception:
                        pass
            
            stats["total_size_mb"] = round(stats["total_size_mb"], 2)
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ 获取日志统计失败: {e}")
            return {}


# 全局服务实例
_log_export_service: Optional[LogExportService] = None


def get_log_export_service() -> LogExportService:
    """获取日志导出服务实例"""
    global _log_export_service
    
    if _log_export_service is None:
        # 从配置中获取日志目录
        from app.core.config import settings
        log_dir = settings.log_dir if hasattr(settings, 'log_dir') else "./logs"
        _log_export_service = LogExportService(log_dir=log_dir)
    
    return _log_export_service

