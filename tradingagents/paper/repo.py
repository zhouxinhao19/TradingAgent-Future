"""
MongoDB 仓库层(`tradingagents/paper/repo.py`)

Phase 4 第三刀交付:
- 4 个 Repo 类(PaperAccountRepo / PaperOrderRepo / PaperPositionRepo /
  PaperFillRepo / PaperDailySnapshotRepo),对应 MongoDB 5 集合的 CRUD
- 通过 `app.core.database.get_mongo_db()` 注入 motor 异步集合
- ODM ↔ MongoDB dict 双向序列化:写库前 exclude_none 不写入 None,读库后
  model_validate 自动校验

设计原则:
1. Repo 类**不持有** db 句柄(每次方法调用传入 db),便于多租户/分库测试
2. 暴露**最小公共 API**:insert / get / list / update / delete / count + 专用方法
3. 索引管理:`ensure_indexes()` 函数集中创建,启动期调用一次
4. 测试友好:所有方法接受可选 `collection` 参数(默认从 `get_mongo_db()` 取),
   允许单测用 mongomock 直接注入
"""
from __future__ import annotations

import logging
from datetime import date as _date, datetime
from typing import Any, Dict, List, Optional

# Pydantic v2 ODM(避免直接依赖 app.models 反向引用,允许纯 tradingagents 包内调用)
try:
    from app.models.commodity_paper import (  # type: ignore
        PaperAccount,
        PaperDailySnapshot,
        PaperFill,
        PaperOrder,
        PaperPosition,
    )
except ImportError:  # pragma: no cover - 纯 tradingagents 单测时 app 不可用
    PaperAccount = PaperDailySnapshot = PaperFill = PaperOrder = PaperPosition = None  # type: ignore

from app.core.database import get_mongo_db

logger = logging.getLogger(__name__)


# =============================================================================
# 集合名常量(单点源,避免拼写错误)
# =============================================================================

COLL_ACCOUNTS = "paper_accounts"
COLL_ORDERS = "paper_orders"
COLL_POSITIONS = "paper_positions"
COLL_FILLS = "paper_fills"
COLL_SNAPSHOTS = "paper_daily_snapshots"


# =============================================================================
# 序列化辅助
# =============================================================================

def _to_dict(model: BaseModel) -> Dict[str, Any]:  # type: ignore[name-defined]
    """Pydantic v2 BaseModel → MongoDB dict。

    - dump mode='python':datetime 保留,date 转 ISO 字符串(BSON 不支持 date)
    - exclude_none:不写 None 字段,节约存储
    """
    if model is None:
        return {}
    data = model.model_dump(mode="python", exclude_none=True)
    # BSON 不直接支持 datetime.date,转 ISO 字符串存储(读出时再 model_validate 转回)
    if isinstance(data.get("date"), _date):
        data["date"] = data["date"].isoformat()
    # _id 用 id 字段,但 MongoDB 习惯 _id;我们选 id 作为业务 id,_id 用相同字符串
    if "id" in data and "_id" not in data:
        data["_id"] = data["id"]
    return data


def _from_dict(cls, data: Optional[Dict[str, Any]]):  # type: ignore[no-untyped-def]
    """MongoDB dict → Pydantic v2 BaseModel。data 为 None 返回 None。

    - date 字段从 ISO 字符串转回 _date 对象
    - _id 字段丢弃(id 已携带)
    """
    if not cls or data is None:
        return None
    payload = {k: v for k, v in data.items() if k != "_id"}
    if isinstance(payload.get("date"), str):
        try:
            payload["date"] = _date.fromisoformat(payload["date"])
        except (TypeError, ValueError):
            pass
    return cls.model_validate(payload)


# =============================================================================
# PaperAccountRepo
# =============================================================================

class PaperAccountRepo:
    """`paper_accounts` 集合读写。"""

    COLLECTION = COLL_ACCOUNTS

    def __init__(self, db=None):
        self._db = db

    @property
    def db(self):
        if self._db is None:
            self._db = get_mongo_db()
        return self._db

    @property
    def collection(self):
        return self.db[self.COLLECTION]

    # -------- C / R / U / D --------

    async def insert(self, account: PaperAccount) -> PaperAccount:
        """插入账户(若 id 已存在则抛 DuplicateKeyError)。"""
        doc = _to_dict(account)
        await self.collection.insert_one(doc)
        return account

    async def get(self, account_id: str) -> Optional[PaperAccount]:
        """按 id 查单个账户。"""
        doc = await self.collection.find_one({"_id": account_id})
        return _from_dict(PaperAccount, doc)

    async def get_or_404(self, account_id: str) -> PaperAccount:
        """按 id 查,不存在则抛 ValueError(供上层统一捕获转 HTTPException)。"""
        acc = await self.get(account_id)
        if acc is None:
            raise ValueError(f"paper account not found: {account_id}")
        return acc

    async def list_by_user(self, user_id: str, *, status: Optional[str] = None) -> List[PaperAccount]:
        """按 user 列出账户(支持 status 过滤)。"""
        query: Dict[str, Any] = {"user_id": user_id}
        if status:
            query["status"] = status
        cursor = self.collection.find(query).sort("created_at", -1)
        docs = await cursor.to_list(length=None)
        return [_from_dict(PaperAccount, d) for d in docs if d]

    async def list_all(self, *, status: Optional[str] = None, limit: int = 100) -> List[PaperAccount]:
        """列出全部账户(管理后台用,默认 status='active')。"""
        query: Dict[str, Any] = {}
        if status:
            query["status"] = status
        cursor = self.collection.find(query).sort("created_at", -1).limit(limit)
        docs = await cursor.to_list(length=limit)
        return [_from_dict(PaperAccount, d) for d in docs if d]

    async def update(self, account: PaperAccount) -> PaperAccount:
        """按 id 覆盖式更新(upsert=False,要求已存在)。"""
        doc = _to_dict(account)
        doc["updated_at"] = datetime.utcnow()
        result = await self.collection.replace_one({"_id": account.id}, doc)
        if result.matched_count == 0:
            raise ValueError(f"paper account not found for update: {account.id}")
        return account

    async def update_fields(self, account_id: str, fields: Dict[str, Any]) -> bool:
        """按 id 部分字段更新(单层字段,不做 $set 嵌套)。"""
        fields = dict(fields)
        fields["updated_at"] = datetime.now()
        result = await self.collection.update_one({"_id": account_id}, {"$set": fields})
        return result.matched_count > 0

    async def soft_delete(self, account_id: str) -> bool:
        """软删(改 status='closed',保留审计)。"""
        return await self.update_fields(account_id, {"status": "closed"})

    async def reset(self, account_id: str) -> bool:
        """重置账户到初始资金(余额/浮盈/已实现清零,不动订单/成交历史)。"""
        acc = await self.get_or_404(account_id)
        fields = {
            "balance": acc.initial_capital,
            "available": acc.initial_capital,
            "margin_used": 0.0,
            "frozen": 0.0,
            "equity": acc.initial_capital,
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "risk_ratio": 0.0,
        }
        return await self.update_fields(account_id, fields)

    async def count(self, *, user_id: Optional[str] = None) -> int:
        query: Dict[str, Any] = {}
        if user_id:
            query["user_id"] = user_id
        return await self.collection.count_documents(query)


# =============================================================================
# PaperOrderRepo
# =============================================================================

class PaperOrderRepo:
    """`paper_orders` 集合读写。"""

    COLLECTION = COLL_ORDERS

    def __init__(self, db=None):
        self._db = db

    @property
    def db(self):
        if self._db is None:
            self._db = get_mongo_db()
        return self._db

    @property
    def collection(self):
        return self.db[self.COLLECTION]

    async def insert(self, order: PaperOrder) -> PaperOrder:
        doc = _to_dict(order)
        await self.collection.insert_one(doc)
        return order

    async def get(self, order_id: str) -> Optional[PaperOrder]:
        doc = await self.collection.find_one({"_id": order_id})
        return _from_dict(PaperOrder, doc)

    async def get_or_404(self, order_id: str) -> PaperOrder:
        o = await self.get(order_id)
        if o is None:
            raise ValueError(f"paper order not found: {order_id}")
        return o

    async def list_by_account(
        self,
        account_id: str,
        *,
        status: Optional[str] = None,
        full_symbol: Optional[str] = None,
        limit: int = 50,
        skip: int = 0,
    ) -> List[PaperOrder]:
        query: Dict[str, Any] = {"account_id": account_id}
        if status:
            query["status"] = status
        if full_symbol:
            query["full_symbol"] = full_symbol
        cursor = (
            self.collection.find(query)
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [_from_dict(PaperOrder, d) for d in docs if d]

    async def count_by_account(self, account_id: str, *, status: Optional[str] = None) -> int:
        query: Dict[str, Any] = {"account_id": account_id}
        if status:
            query["status"] = status
        return await self.collection.count_documents(query)

    async def update(self, order: PaperOrder) -> PaperOrder:
        doc = _to_dict(order)
        doc["updated_at"] = datetime.utcnow()
        result = await self.collection.replace_one({"_id": order.id}, doc)
        if result.matched_count == 0:
            raise ValueError(f"paper order not found for update: {order.id}")
        return order

    async def update_fields(self, order_id: str, fields: Dict[str, Any]) -> bool:
        fields = dict(fields)
        fields["updated_at"] = datetime.utcnow()
        result = await self.collection.update_one({"_id": order_id}, {"$set": fields})
        return result.matched_count > 0

    async def find_pending_by_account(self, account_id: str) -> List[PaperOrder]:
        """查询某账户所有 pending 订单(供后台撮合 / 撤单批量处理)。"""
        cursor = self.collection.find({"account_id": account_id, "status": "pending"}).sort("created_at", 1)
        docs = await cursor.to_list(length=None)
        return [_from_dict(PaperOrder, d) for d in docs if d]


# =============================================================================
# PaperPositionRepo
# =============================================================================

class PaperPositionRepo:
    """`paper_positions` 集合读写。"""

    COLLECTION = COLL_POSITIONS

    def __init__(self, db=None):
        self._db = db

    @property
    def db(self):
        if self._db is None:
            self._db = get_mongo_db()
        return self._db

    @property
    def collection(self):
        return self.db[self.COLLECTION]

    async def upsert(self, position: PaperPosition) -> PaperPosition:
        """按 (account_id, full_symbol, direction) upsert 持仓(净持仓模型核心)。"""
        doc = _to_dict(position)
        doc["updated_at"] = datetime.utcnow()
        # _id 在 update_one 中是不可变字段,upsert 时首次插入用 doc(包含 _id),
        # 后续 $set 不能再带 _id(否则 mongomock / MongoDB 都会拒绝)
        set_doc = {k: v for k, v in doc.items() if k != "_id"}
        # 唯一键:同一账户同一品种同一方向只能有 1 条
        await self.collection.update_one(
            {
                "account_id": position.account_id,
                "full_symbol": position.full_symbol,
                "direction": position.direction,
            },
            {
                "$set": set_doc,
                "$setOnInsert": {"_id": position.id},
            },
            upsert=True,
        )
        return position

    async def get(
        self,
        account_id: str,
        full_symbol: str,
        direction: str,
    ) -> Optional[PaperPosition]:
        doc = await self.collection.find_one(
            {"account_id": account_id, "full_symbol": full_symbol, "direction": direction}
        )
        return _from_dict(PaperPosition, doc)

    async def list_by_account(
        self,
        account_id: str,
        *,
        full_symbol: Optional[str] = None,
        open_only: bool = True,
    ) -> List[PaperPosition]:
        """列出账户当前持仓。open_only=True 过滤 lots > 0(默认)。"""
        query: Dict[str, Any] = {"account_id": account_id}
        if full_symbol:
            query["full_symbol"] = full_symbol
        if open_only:
            query["lots"] = {"$gt": 0}
        cursor = self.collection.find(query).sort("updated_at", -1)
        docs = await cursor.to_list(length=None)
        return [_from_dict(PaperPosition, d) for d in docs if d]

    async def delete(self, position_id: str) -> bool:
        result = await self.collection.delete_one({"_id": position_id})
        return result.deleted_count > 0

    async def count(self, account_id: str, *, open_only: bool = True) -> int:
        query: Dict[str, Any] = {"account_id": account_id}
        if open_only:
            query["lots"] = {"$gt": 0}
        return await self.collection.count_documents(query)


# =============================================================================
# PaperFillRepo
# =============================================================================

class PaperFillRepo:
    """`paper_fills` 集合读写(append-only)。"""

    COLLECTION = COLL_FILLS

    def __init__(self, db=None):
        self._db = db

    @property
    def db(self):
        if self._db is None:
            self._db = get_mongo_db()
        return self._db

    @property
    def collection(self):
        return self.db[self.COLLECTION]

    async def insert(self, fill: PaperFill) -> PaperFill:
        doc = _to_dict(fill)
        await self.collection.insert_one(doc)
        return fill

    async def list_by_account(
        self,
        account_id: str,
        *,
        full_symbol: Optional[str] = None,
        limit: int = 100,
        skip: int = 0,
        since: Optional[datetime] = None,
    ) -> List[PaperFill]:
        query: Dict[str, Any] = {"account_id": account_id}
        if full_symbol:
            query["full_symbol"] = full_symbol
        if since:
            query["matched_at"] = {"$gte": since}
        cursor = (
            self.collection.find(query)
            .sort("matched_at", -1)
            .skip(skip)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [_from_dict(PaperFill, d) for d in docs if d]

    async def count_by_account(self, account_id: str) -> int:
        return await self.collection.count_documents({"account_id": account_id})

    async def list_by_order(self, order_id: str) -> List[PaperFill]:
        cursor = self.collection.find({"order_id": order_id}).sort("matched_at", 1)
        docs = await cursor.to_list(length=None)
        return [_from_dict(PaperFill, d) for d in docs if d]


# =============================================================================
# PaperDailySnapshotRepo
# =============================================================================

class PaperDailySnapshotRepo:
    """`paper_daily_snapshots` 集合读写。"""

    COLLECTION = COLL_SNAPSHOTS

    def __init__(self, db=None):
        self._db = db

    @property
    def db(self):
        if self._db is None:
            self._db = get_mongo_db()
        return self._db

    @property
    def collection(self):
        return self.db[self.COLLECTION]

    async def upsert(self, snap: PaperDailySnapshot) -> PaperDailySnapshot:
        """按 (account_id, date) 唯一键 upsert 日终快照。"""
        doc = _to_dict(snap)
        doc["snapshot_at"] = datetime.utcnow()
        set_doc = {k: v for k, v in doc.items() if k != "_id"}
        await self.collection.update_one(
            {"account_id": snap.account_id, "date": snap.date.isoformat()},
            {
                "$set": set_doc,
                "$setOnInsert": {"_id": snap.id},
            },
            upsert=True,
        )
        return snap

    async def get_by_date(self, account_id: str, day: _date) -> Optional[PaperDailySnapshot]:
        doc = await self.collection.find_one(
            {"account_id": account_id, "date": day.isoformat()}
        )
        return _from_dict(PaperDailySnapshot, doc)

    async def list_by_account(
        self,
        account_id: str,
        *,
        days: int = 30,
    ) -> List[PaperDailySnapshot]:
        """按时间倒序返回最近 N 天快照。"""
        cursor = (
            self.collection.find({"account_id": account_id})
            .sort("date", -1)
            .limit(days)
        )
        docs = await cursor.to_list(length=days)
        # 时间正序返回(供绘图)
        return [_from_dict(PaperDailySnapshot, d) for d in docs if d][::-1]


# =============================================================================
# 索引初始化(启动期调一次)
# =============================================================================

async def ensure_indexes(db=None) -> Dict[str, int]:
    """创建 5 集合的核心索引。返回 {集合名: 索引数}。

    注意:重复调用是幂等的(motor create_index 对已存在索引 no-op)。

    索引设计:
    - paper_accounts:user_id 单字段,user_id+status 复合
    - paper_orders:(account_id, created_at)/(account_id, status)/(user 间接走 account_id)
    - paper_positions:唯一复合 (account_id, full_symbol, direction)
    - paper_fills:(account_id, matched_at)/(order_id)
    - paper_daily_snapshots:唯一复合 (account_id, date)
    """
    if db is None:
        db = get_mongo_db()

    counts: Dict[str, int] = {}

    # accounts
    acc = db[COLL_ACCOUNTS]
    await acc.create_index([("user_id", 1), ("status", 1)])
    counts[COLL_ACCOUNTS] = 2

    # orders
    od = db[COLL_ORDERS]
    await od.create_index([("account_id", 1), ("created_at", -1)])
    await od.create_index([("account_id", 1), ("status", 1)])
    await od.create_index([("full_symbol", 1)])
    counts[COLL_ORDERS] = 3

    # positions
    pos = db[COLL_POSITIONS]
    # 唯一复合索引:净持仓模型下,同账户同品种同方向只能有一条
    await pos.create_index(
        [("account_id", 1), ("full_symbol", 1), ("direction", 1)],
        unique=True,
        name="uniq_account_symbol_direction",
    )
    await pos.create_index([("account_id", 1), ("lots", 1)])
    counts[COLL_POSITIONS] = 2

    # fills
    fl = db[COLL_FILLS]
    await fl.create_index([("account_id", 1), ("matched_at", -1)])
    await fl.create_index([("order_id", 1)])
    counts[COLL_FILLS] = 2

    # snapshots
    snap = db[COLL_SNAPSHOTS]
    await snap.create_index(
        [("account_id", 1), ("date", -1)],
        unique=True,
        name="uniq_account_date",
    )
    counts[COLL_SNAPSHOTS] = 1

    logger.info("✅ Phase 4 paper indexes ensured: %s", counts)
    return counts


# =============================================================================
# 便捷单例(上层 service 层直接复用)
# =============================================================================

def get_account_repo() -> PaperAccountRepo:
    return PaperAccountRepo()


def get_order_repo() -> PaperOrderRepo:
    return PaperOrderRepo()


def get_position_repo() -> PaperPositionRepo:
    return PaperPositionRepo()


def get_fill_repo() -> PaperFillRepo:
    return PaperFillRepo()


def get_snapshot_repo() -> PaperDailySnapshotRepo:
    return PaperDailySnapshotRepo()


__all__ = [
    "COLL_ACCOUNTS",
    "COLL_ORDERS",
    "COLL_POSITIONS",
    "COLL_FILLS",
    "COLL_SNAPSHOTS",
    "PaperAccountRepo",
    "PaperOrderRepo",
    "PaperPositionRepo",
    "PaperFillRepo",
    "PaperDailySnapshotRepo",
    "ensure_indexes",
    "get_account_repo",
    "get_order_repo",
    "get_position_repo",
    "get_fill_repo",
    "get_snapshot_repo",
]
