"""
大宗商品统一服务(Phase 3a)

⚠️ 该文件在 Phase 4 工作树中为最小 stub。
Phase 3a 完整实现在主分支中,待 Phase 4 完成后合并回主分支时自动补齐。
当前 stub 仅确保 commodity routers 可导入不报错。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("webapi")


class _StubCommodityService:
    """最小 stub,所有方法返回空值。"""

    async def get_basic_info(self, full_symbol: str) -> Optional[Dict[str, Any]]:
        logger.debug("stub get_basic_info(%s)", full_symbol)
        return None

    async def get_quotes(self, full_symbol: str) -> Optional[Dict[str, Any]]:
        logger.debug("stub get_quotes(%s)", full_symbol)
        return None

    async def get_historical(self, full_symbol: str, start: str, end: Optional[str] = None) -> Optional[Dict[str, Any]]:
        return None

    async def get_categories(self) -> List[Dict[str, Any]]:
        return []

    async def get_exchanges(self) -> List[Dict[str, Any]]:
        return []

    async def get_realtime_quote(self, full_symbol: str) -> float:
        return 0.0


service = _StubCommodityService()
