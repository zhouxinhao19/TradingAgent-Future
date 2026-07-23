"""
自选品种统一数据模型
持久化到独立的 user_favorites MongoDB 集合
"""

from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, Field
from uuid import uuid4

from app.utils.timezone import now_tz

AssetType = Literal['stock', 'commodity']


class FavoriteItem(BaseModel):
    """自选品种统一模型"""
    id: str = Field(default_factory=lambda: str(uuid4()), alias="_id")
    user_id: str = Field(..., description="用户ID")
    asset_type: AssetType = Field(..., description="资产类型: stock/commodity")

    # ---- 历史兼容字段（旧 stock 数据） ----
    stock_code: Optional[str] = Field(default=None, description="股票代码,如 000001.SZ")
    stock_name: Optional[str] = Field(default=None, description="股票名称")
    market: Optional[str] = Field(default=None, description="市场: A股/港股/美股")

    # ---- 商品期货特有字段 ----
    full_symbol: Optional[str] = Field(default=None, description="商品合约代码,如 RB2510.SHF")
    commodity_name: Optional[str] = Field(default=None, description="商品名称")
    exchange: Optional[str] = Field(default=None, description="交易所代码 SHF/DCE/...")
    category: Optional[str] = Field(default=None, description="品类如 black/metal/...")

    # ---- 共有字段 ----
    display_name: str = Field(default="", description="展示名称")
    added_at: datetime = Field(default_factory=now_tz)
    tags: List[str] = Field(default_factory=list)
    notes: str = Field(default="")
    alert_price_high: Optional[float] = Field(default=None)
    alert_price_low: Optional[float] = Field(default=None)

    # 可选的价格快照（添加时的参考价）
    snapshot_price: Optional[float] = Field(default=None, description="添加时的价格快照")
    snapshot_change: Optional[float] = Field(default=None)
    snapshot_pct: Optional[float] = Field(default=None)
