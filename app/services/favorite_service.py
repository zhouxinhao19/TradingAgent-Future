"""
自选品种服务 - 独立集合 user_favorites
CRUD 操作，遵循 tags_service 模式
"""

from typing import List, Optional, Dict, Any
from uuid import uuid4

from app.core.database import get_mongo_db
from app.models.favorite import FavoriteItem


class FavoriteService:
    def __init__(self) -> None:
        self.db = None
        self._indexes_ensured = False

    async def _get_db(self):
        if self.db is None:
            self.db = get_mongo_db()
        return self.db

    async def ensure_indexes(self) -> None:
        if self._indexes_ensured:
            return
        db = await self._get_db()
        # 清理可能存在的旧版错误索引(bad partial_filter_expression)
        for bad_name in ("uniq_user_stock", "uniq_user_commodity"):
            try:
                await db.user_favorites.drop_index(bad_name)
            except Exception:
                pass
        # 每个用户的商品不可重复（full_symbol 唯一）
        await db.user_favorites.create_index(
            [("user_id", 1), ("asset_type", 1), ("full_symbol", 1)],
            unique=True,
            name="uniq_user_commodity"
        )
        # 按添加时间倒排
        await db.user_favorites.create_index(
            [("user_id", 1), ("added_at", -1)],
            name="idx_user_added_at"
        )
        self._indexes_ensured = True

    async def list_favorites(self, user_id: str, asset_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取用户自选列表，可选按 asset_type 过滤"""
        db = await self._get_db()
        await self.ensure_indexes()
        query: Dict[str, Any] = {"user_id": user_id}
        if asset_type and asset_type in ("commodity",):
            query["asset_type"] = asset_type
        cursor = db.user_favorites.find(query).sort("added_at", -1)
        docs = await cursor.to_list(length=None)
        return [self._format_doc(doc) for doc in docs]

    async def add_favorite(self, user_id: str, item: FavoriteItem) -> Dict[str, Any]:
        """添加自选"""
        db = await self._get_db()
        await self.ensure_indexes()
        item.user_id = user_id
        if not item.display_name:
            item.display_name = (
                item.commodity_name or item.full_symbol or ""
            )
        doc = item.model_dump(by_alias=True)
        await db.user_favorites.insert_one(doc)
        return self._format_doc(doc)

    async def remove_favorite(self, favorite_id: str, user_id: str) -> bool:
        """删除自选"""
        db = await self._get_db()
        result = await db.user_favorites.delete_one({"_id": favorite_id, "user_id": user_id})
        return result.deleted_count > 0

    async def update_favorite(self, favorite_id: str, user_id: str, updates: dict) -> Optional[Dict[str, Any]]:
        """更新自选（tags, notes, alert_price 等）"""
        db = await self._get_db()
        updates["updated_at"] = datetime.utcnow()
        result = await db.user_favorites.find_one_and_update(
            {"_id": favorite_id, "user_id": user_id},
            {"$set": updates},
            return_document=True,
        )
        return self._format_doc(result) if result else None

    async def batch_remove(self, user_id: str, ids: List[str]) -> int:
        """批量删除"""
        db = await self._get_db()
        result = await db.user_favorites.delete_many({"_id": {"$in": ids}, "user_id": user_id})
        return result.deleted_count

    @staticmethod
    def _format_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": str(doc.get("_id")),
            "user_id": doc.get("user_id"),
            "asset_type": doc.get("asset_type"),
            "full_symbol": doc.get("full_symbol"),
            "commodity_name": doc.get("commodity_name"),
            "exchange": doc.get("exchange"),
            "category": doc.get("category"),
            "display_name": doc.get("display_name", ""),
            "added_at": doc.get("added_at").isoformat() if doc.get("added_at") else "",
            "tags": doc.get("tags", []),
            "notes": doc.get("notes", ""),
            "alert_price_high": doc.get("alert_price_high"),
            "alert_price_low": doc.get("alert_price_low"),
            "snapshot_price": doc.get("snapshot_price"),
            "snapshot_change": doc.get("snapshot_change"),
            "snapshot_pct": doc.get("snapshot_pct"),
        }


favorite_service = FavoriteService()
