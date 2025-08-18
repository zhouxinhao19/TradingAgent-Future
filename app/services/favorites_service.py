"""
自选股服务
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from bson import ObjectId

from app.core.database import get_mongo_db
from app.models.user import FavoriteStock


class FavoritesService:
    """自选股服务类"""
    
    def __init__(self):
        self.db = None
    
    async def _get_db(self):
        """获取数据库连接"""
        if self.db is None:
            self.db = get_mongo_db()
        return self.db
    
    async def get_user_favorites(self, user_id: str) -> List[Dict[str, Any]]:
        """获取用户自选股列表"""
        db = await self._get_db()
        users_collection = db.users
        
        # 查找用户
        user = await users_collection.find_one({"_id": ObjectId(user_id)})
        if not user:
            return []
        
        favorites = user.get("favorite_stocks", [])
        
        # 获取实时股价数据（模拟）
        result = []
        for favorite in favorites:
            favorite_data = {
                "stock_code": favorite["stock_code"],
                "stock_name": favorite["stock_name"],
                "market": favorite["market"],
                "added_at": favorite["added_at"].isoformat() if isinstance(favorite["added_at"], datetime) else favorite["added_at"],
                "tags": favorite.get("tags", []),
                "notes": favorite.get("notes", ""),
                "alert_price_high": favorite.get("alert_price_high"),
                "alert_price_low": favorite.get("alert_price_low"),
                # 模拟实时数据
                "current_price": self._get_mock_price(favorite["stock_code"]),
                "change_percent": self._get_mock_change(favorite["stock_code"]),
                "volume": self._get_mock_volume(favorite["stock_code"])
            }
            result.append(favorite_data)
        
        return result
    
    async def add_favorite(
        self,
        user_id: str,
        stock_code: str,
        stock_name: str,
        market: str = "A股",
        tags: List[str] = None,
        notes: str = "",
        alert_price_high: Optional[float] = None,
        alert_price_low: Optional[float] = None
    ) -> bool:
        """添加股票到自选股"""
        db = await self._get_db()
        users_collection = db.users
        
        favorite_stock = {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "market": market,
            "added_at": datetime.utcnow(),
            "tags": tags or [],
            "notes": notes,
            "alert_price_high": alert_price_high,
            "alert_price_low": alert_price_low
        }
        
        # 添加到用户的自选股列表
        result = await users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$push": {"favorite_stocks": favorite_stock}}
        )
        
        return result.modified_count > 0
    
    async def remove_favorite(self, user_id: str, stock_code: str) -> bool:
        """从自选股中移除股票"""
        db = await self._get_db()
        users_collection = db.users
        
        result = await users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$pull": {"favorite_stocks": {"stock_code": stock_code}}}
        )
        
        return result.modified_count > 0
    
    async def update_favorite(
        self,
        user_id: str,
        stock_code: str,
        tags: Optional[List[str]] = None,
        notes: Optional[str] = None,
        alert_price_high: Optional[float] = None,
        alert_price_low: Optional[float] = None
    ) -> bool:
        """更新自选股信息"""
        db = await self._get_db()
        users_collection = db.users
        
        # 构建更新字段
        update_fields = {}
        if tags is not None:
            update_fields["favorite_stocks.$.tags"] = tags
        if notes is not None:
            update_fields["favorite_stocks.$.notes"] = notes
        if alert_price_high is not None:
            update_fields["favorite_stocks.$.alert_price_high"] = alert_price_high
        if alert_price_low is not None:
            update_fields["favorite_stocks.$.alert_price_low"] = alert_price_low
        
        if not update_fields:
            return True
        
        result = await users_collection.update_one(
            {
                "_id": ObjectId(user_id),
                "favorite_stocks.stock_code": stock_code
            },
            {"$set": update_fields}
        )
        
        return result.modified_count > 0
    
    async def is_favorite(self, user_id: str, stock_code: str) -> bool:
        """检查股票是否在自选股中"""
        db = await self._get_db()
        users_collection = db.users
        
        user = await users_collection.find_one(
            {
                "_id": ObjectId(user_id),
                "favorite_stocks.stock_code": stock_code
            }
        )
        
        return user is not None
    
    async def get_user_tags(self, user_id: str) -> List[str]:
        """获取用户使用的所有标签"""
        db = await self._get_db()
        users_collection = db.users
        
        # 使用聚合查询获取所有标签
        pipeline = [
            {"$match": {"_id": ObjectId(user_id)}},
            {"$unwind": "$favorite_stocks"},
            {"$unwind": "$favorite_stocks.tags"},
            {"$group": {"_id": "$favorite_stocks.tags"}},
            {"$sort": {"_id": 1}}
        ]
        
        result = await users_collection.aggregate(pipeline).to_list(None)
        return [item["_id"] for item in result if item["_id"]]
    
    def _get_mock_price(self, stock_code: str) -> float:
        """获取模拟股价"""
        # 基于股票代码生成模拟价格
        base_price = hash(stock_code) % 100 + 10
        return round(base_price + (hash(stock_code) % 1000) / 100, 2)
    
    def _get_mock_change(self, stock_code: str) -> float:
        """获取模拟涨跌幅"""
        # 基于股票代码生成模拟涨跌幅
        change = (hash(stock_code) % 2000 - 1000) / 100
        return round(change, 2)
    
    def _get_mock_volume(self, stock_code: str) -> int:
        """获取模拟成交量"""
        # 基于股票代码生成模拟成交量
        return (hash(stock_code) % 10000 + 1000) * 100


# 创建全局实例
favorites_service = FavoritesService()
