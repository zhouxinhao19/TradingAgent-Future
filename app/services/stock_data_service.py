"""
股票数据服务层 - 统一数据访问接口
基于现有MongoDB集合，提供标准化的数据访问服务
"""
import logging
from datetime import datetime, date
from typing import Optional, Dict, Any, List
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import get_mongo_db
from app.models.stock_models import (
    StockBasicInfoExtended, 
    MarketQuotesExtended,
    MarketInfo,
    MarketType,
    ExchangeType,
    CurrencyType
)

logger = logging.getLogger(__name__)


class StockDataService:
    """
    股票数据服务 - 统一数据访问层
    基于现有集合扩展，保持向后兼容
    """
    
    def __init__(self):
        self.basic_info_collection = "stock_basic_info"
        self.market_quotes_collection = "market_quotes"
    
    async def get_stock_basic_info(self, code: str) -> Optional[StockBasicInfoExtended]:
        """
        获取股票基础信息
        Args:
            code: 6位股票代码
        Returns:
            StockBasicInfoExtended: 扩展的股票基础信息
        """
        try:
            db = get_mongo_db()
            code6 = str(code).zfill(6)
            
            # 从现有集合查询
            doc = await db[self.basic_info_collection].find_one(
                {"code": code6}, 
                {"_id": 0}
            )
            
            if not doc:
                return None
            
            # 数据标准化处理
            standardized_doc = self._standardize_basic_info(doc)
            
            return StockBasicInfoExtended(**standardized_doc)
            
        except Exception as e:
            logger.error(f"获取股票基础信息失败 code={code}: {e}")
            return None
    
    async def get_market_quotes(self, code: str) -> Optional[MarketQuotesExtended]:
        """
        获取实时行情数据
        Args:
            code: 6位股票代码
        Returns:
            MarketQuotesExtended: 扩展的实时行情数据
        """
        try:
            db = get_mongo_db()
            code6 = str(code).zfill(6)
            
            # 从现有集合查询
            doc = await db[self.market_quotes_collection].find_one(
                {"code": code6},
                {"_id": 0}
            )
            
            if not doc:
                return None
            
            # 数据标准化处理
            standardized_doc = self._standardize_market_quotes(doc)
            
            return MarketQuotesExtended(**standardized_doc)
            
        except Exception as e:
            logger.error(f"获取实时行情失败 code={code}: {e}")
            return None
    
    async def get_stock_list(
        self, 
        market: Optional[str] = None,
        industry: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> List[StockBasicInfoExtended]:
        """
        获取股票列表
        Args:
            market: 市场筛选
            industry: 行业筛选
            page: 页码
            page_size: 每页大小
        Returns:
            List[StockBasicInfoExtended]: 股票列表
        """
        try:
            db = get_mongo_db()
            
            # 构建查询条件
            query = {}
            if market:
                query["market"] = market
            if industry:
                query["industry"] = industry
            
            # 分页查询
            skip = (page - 1) * page_size
            cursor = db[self.basic_info_collection].find(
                query, 
                {"_id": 0}
            ).skip(skip).limit(page_size)
            
            docs = await cursor.to_list(length=page_size)
            
            # 数据标准化处理
            result = []
            for doc in docs:
                standardized_doc = self._standardize_basic_info(doc)
                result.append(StockBasicInfoExtended(**standardized_doc))
            
            return result
            
        except Exception as e:
            logger.error(f"获取股票列表失败: {e}")
            return []
    
    async def update_stock_basic_info(
        self, 
        code: str, 
        update_data: Dict[str, Any]
    ) -> bool:
        """
        更新股票基础信息
        Args:
            code: 6位股票代码
            update_data: 更新数据
        Returns:
            bool: 更新是否成功
        """
        try:
            db = get_mongo_db()
            code6 = str(code).zfill(6)
            
            # 添加更新时间
            update_data["updated_at"] = datetime.utcnow()
            
            # 执行更新
            result = await db[self.basic_info_collection].update_one(
                {"code": code6},
                {"$set": update_data},
                upsert=True
            )
            
            return result.modified_count > 0 or result.upserted_id is not None
            
        except Exception as e:
            logger.error(f"更新股票基础信息失败 code={code}: {e}")
            return False
    
    async def update_market_quotes(
        self,
        code: str,
        quote_data: Dict[str, Any]
    ) -> bool:
        """
        更新实时行情数据
        Args:
            code: 6位股票代码
            quote_data: 行情数据
        Returns:
            bool: 更新是否成功
        """
        try:
            db = get_mongo_db()
            code6 = str(code).zfill(6)
            
            # 添加更新时间
            quote_data["updated_at"] = datetime.utcnow()
            
            # 执行更新
            result = await db[self.market_quotes_collection].update_one(
                {"code": code6},
                {"$set": quote_data},
                upsert=True
            )
            
            return result.modified_count > 0 or result.upserted_id is not None
            
        except Exception as e:
            logger.error(f"更新实时行情失败 code={code}: {e}")
            return False
    
    def _standardize_basic_info(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """
        标准化股票基础信息数据
        将现有字段映射到标准化字段
        """
        # 保持现有字段不变
        result = doc.copy()
        
        # 添加标准化字段
        code = doc.get("code", "")
        result["symbol"] = code
        
        # 生成完整代码
        if code and len(code) == 6:
            # 根据代码判断交易所
            if code.startswith(('60', '68', '90')):
                result["full_symbol"] = f"{code}.SS"
                exchange = "SSE"
                exchange_name = "上海证券交易所"
            elif code.startswith(('00', '30', '20')):
                result["full_symbol"] = f"{code}.SZ"
                exchange = "SZSE"
                exchange_name = "深圳证券交易所"
            else:
                result["full_symbol"] = f"{code}.SZ"  # 默认深交所
                exchange = "SZSE"
                exchange_name = "深圳证券交易所"
            
            # 添加市场信息
            result["market_info"] = {
                "market": "CN",
                "exchange": exchange,
                "exchange_name": exchange_name,
                "currency": "CNY",
                "timezone": "Asia/Shanghai",
                "trading_hours": {
                    "open": "09:30",
                    "close": "15:00",
                    "lunch_break": ["11:30", "13:00"]
                }
            }
        
        # 字段映射和标准化
        result["board"] = doc.get("sse")  # 板块标准化
        result["sector"] = doc.get("sec")  # 所属板块标准化
        result["status"] = "L"  # 默认上市状态
        result["data_version"] = 1

        # 处理日期字段格式转换
        list_date = doc.get("list_date")
        if list_date and isinstance(list_date, int):
            # 将整数日期转换为字符串格式 (YYYYMMDD -> YYYY-MM-DD)
            date_str = str(list_date)
            if len(date_str) == 8:
                result["list_date"] = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
            else:
                result["list_date"] = str(list_date)
        elif list_date:
            result["list_date"] = str(list_date)

        return result
    
    def _standardize_market_quotes(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """
        标准化实时行情数据
        将现有字段映射到标准化字段
        """
        # 保持现有字段不变
        result = doc.copy()
        
        # 添加标准化字段
        code = doc.get("code", "")
        result["symbol"] = code
        
        # 生成完整代码和市场标识
        if code and len(code) == 6:
            if code.startswith(('60', '68', '90')):
                result["full_symbol"] = f"{code}.SS"
            else:
                result["full_symbol"] = f"{code}.SZ"
            result["market"] = "CN"
        
        # 字段映射
        result["current_price"] = doc.get("close")  # 当前价格
        if doc.get("close") and doc.get("pre_close"):
            try:
                result["change"] = float(doc["close"]) - float(doc["pre_close"])
            except (ValueError, TypeError):
                result["change"] = None
        
        result["data_source"] = "market_quotes"
        result["data_version"] = 1
        
        return result


# 全局服务实例
_stock_data_service = None

def get_stock_data_service() -> StockDataService:
    """获取股票数据服务实例"""
    global _stock_data_service
    if _stock_data_service is None:
        _stock_data_service = StockDataService()
    return _stock_data_service
