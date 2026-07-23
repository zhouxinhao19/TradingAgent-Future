"""
数据流接口层 (Phase 5: 已移除股票数据流, 仅保留商品数据接口)
"""
import logging

logger = logging.getLogger("dataflows.interface")

def set_config(**kwargs):
    """兼容性占位 — 原用于数据源配置"""
    pass

__all__ = ["set_config"]
