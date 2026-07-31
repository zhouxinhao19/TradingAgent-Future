"""
数据流接口层 (Phase 5: 已移除股票数据流, 仅保留商品数据接口)
"""
import logging

logger = logging.getLogger("dataflows.interface")

def set_config(*args, **kwargs):
    """兼容性占位 — 原用于数据源配置。

    兼容两种调用方式（trading_graph.py:211 用 positional 传 dict）：
      - set_config(self.config)  # positional dict（推荐）
      - set_config(**self.config)  # kwargs 展开
    """
    pass

__all__ = ["set_config"]
