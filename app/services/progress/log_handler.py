"""
进度日志处理器（过渡期）：提供稳定的新导入路径
- ProgressLogHandler
- get_progress_log_handler
- register_analysis_tracker
- unregister_analysis_tracker
当前实现委托给旧模块 app.services.progress_log_handler
"""

from app.services.progress_log_handler import (
    ProgressLogHandler as _ProgressLogHandler,
    get_progress_log_handler as _get_progress_log_handler,
    register_analysis_tracker as _register_analysis_tracker,
    unregister_analysis_tracker as _unregister_analysis_tracker,
)

ProgressLogHandler = _ProgressLogHandler  # type: ignore
get_progress_log_handler = _get_progress_log_handler  # type: ignore
register_analysis_tracker = _register_analysis_tracker  # type: ignore
unregister_analysis_tracker = _unregister_analysis_tracker  # type: ignore

