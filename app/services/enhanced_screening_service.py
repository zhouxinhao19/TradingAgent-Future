"""
增强的股票筛选服务
结合数据库优化和传统筛选方式，提供高效的股票筛选功能
"""

import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

from app.models.screening import ScreeningCondition, FieldType, BASIC_FIELDS_INFO
from app.services.database_screening_service import get_database_screening_service
from app.services.screening_service import ScreeningService, ScreeningParams

logger = logging.getLogger(__name__)


class EnhancedScreeningService:
    """增强的股票筛选服务"""
    
    def __init__(self):
        self.db_service = get_database_screening_service()
        self.traditional_service = ScreeningService()
        
        # 支持数据库优化的字段
        self.db_supported_fields = set(BASIC_FIELDS_INFO.keys())
    
    async def screen_stocks(
        self,
        conditions: List[ScreeningCondition],
        market: str = "CN",
        date: Optional[str] = None,
        adj: str = "qfq",
        limit: int = 50,
        offset: int = 0,
        order_by: Optional[List[Dict[str, str]]] = None,
        use_database_optimization: bool = True
    ) -> Dict[str, Any]:
        """
        智能股票筛选
        
        Args:
            conditions: 筛选条件列表
            market: 市场
            date: 交易日期
            adj: 复权方式
            limit: 返回数量限制
            offset: 偏移量
            order_by: 排序条件
            use_database_optimization: 是否使用数据库优化
            
        Returns:
            Dict: 筛选结果
        """
        start_time = time.time()
        
        try:
            # 分析筛选条件
            analysis = self._analyze_conditions(conditions)
            
            # 决定使用哪种筛选方式
            if (use_database_optimization and 
                analysis["can_use_database"] and 
                not analysis["needs_technical_indicators"]):
                
                # 使用数据库优化筛选
                result = await self._screen_with_database(
                    conditions, limit, offset, order_by
                )
                optimization_used = "database"
                source = "mongodb"
                
            else:
                # 使用传统筛选方式
                result = await self._screen_with_traditional_method(
                    conditions, market, date, adj, limit, offset, order_by
                )
                optimization_used = "traditional"
                source = "api"
            
            # 计算耗时
            took_ms = int((time.time() - start_time) * 1000)
            
            # 返回结果
            return {
                "total": result[1] if isinstance(result, tuple) else result.get("total", 0),
                "items": result[0] if isinstance(result, tuple) else result.get("items", []),
                "took_ms": took_ms,
                "optimization_used": optimization_used,
                "source": source,
                "analysis": analysis
            }
            
        except Exception as e:
            logger.error(f"❌ 股票筛选失败: {e}")
            took_ms = int((time.time() - start_time) * 1000)
            
            return {
                "total": 0,
                "items": [],
                "took_ms": took_ms,
                "optimization_used": "none",
                "source": "error",
                "error": str(e)
            }
    
    def _analyze_conditions(self, conditions: List[ScreeningCondition]) -> Dict[str, Any]:
        """
        分析筛选条件，决定最优的筛选策略
        
        Args:
            conditions: 筛选条件列表
            
        Returns:
            Dict: 分析结果
        """
        analysis = {
            "total_conditions": len(conditions),
            "database_supported_conditions": 0,
            "technical_conditions": 0,
            "fundamental_conditions": 0,
            "basic_conditions": 0,
            "can_use_database": True,
            "needs_technical_indicators": False,
            "unsupported_fields": [],
            "condition_types": []
        }
        
        for condition in conditions:
            field = condition.field
            
            # 检查字段类型
            if field in BASIC_FIELDS_INFO:
                field_info = BASIC_FIELDS_INFO[field]
                field_type = field_info.field_type
                
                if field_type == FieldType.BASIC:
                    analysis["basic_conditions"] += 1
                elif field_type == FieldType.FUNDAMENTAL:
                    analysis["fundamental_conditions"] += 1
                elif field_type == FieldType.TECHNICAL:
                    analysis["technical_conditions"] += 1
                
                analysis["condition_types"].append(field_type.value)
                
                # 检查是否支持数据库查询
                if field in self.db_supported_fields:
                    analysis["database_supported_conditions"] += 1
                else:
                    analysis["can_use_database"] = False
                    analysis["unsupported_fields"].append(field)
            else:
                # 未知字段，可能是技术指标
                analysis["can_use_database"] = False
                analysis["needs_technical_indicators"] = True
                analysis["unsupported_fields"].append(field)
        
        # 如果有技术指标条件，需要使用传统方法
        if analysis["technical_conditions"] > 0 or analysis["needs_technical_indicators"]:
            analysis["needs_technical_indicators"] = True
        
        logger.info(f"📊 筛选条件分析: {analysis}")
        
        return analysis
    
    async def _screen_with_database(
        self,
        conditions: List[ScreeningCondition],
        limit: int,
        offset: int,
        order_by: Optional[List[Dict[str, str]]]
    ) -> Tuple[List[Dict[str, Any]], int]:
        """使用数据库优化筛选"""
        logger.info("🚀 使用数据库优化筛选")
        
        return await self.db_service.screen_stocks(
            conditions=conditions,
            limit=limit,
            offset=offset,
            order_by=order_by
        )
    
    async def _screen_with_traditional_method(
        self,
        conditions: List[ScreeningCondition],
        market: str,
        date: Optional[str],
        adj: str,
        limit: int,
        offset: int,
        order_by: Optional[List[Dict[str, str]]]
    ) -> Dict[str, Any]:
        """使用传统筛选方法"""
        logger.info("🔄 使用传统筛选方法")
        
        # 转换条件格式为传统服务支持的格式
        traditional_conditions = self._convert_conditions_to_traditional_format(conditions)
        
        # 创建筛选参数
        params = ScreeningParams(
            market=market,
            date=date,
            adj=adj,
            limit=limit,
            offset=offset,
            order_by=order_by
        )
        
        # 执行传统筛选
        result = self.traditional_service.run(traditional_conditions, params)
        
        return result
    
    def _convert_conditions_to_traditional_format(
        self, 
        conditions: List[ScreeningCondition]
    ) -> Dict[str, Any]:
        """将新格式的筛选条件转换为传统格式"""
        traditional_conditions = {}
        
        for condition in conditions:
            field = condition.field
            operator = condition.operator
            value = condition.value
            
            # 构建传统格式的条件
            if operator == "between" and isinstance(value, list) and len(value) == 2:
                traditional_conditions[field] = {
                    "min": value[0],
                    "max": value[1]
                }
            elif operator in [">", "<", ">=", "<="]:
                traditional_conditions[field] = {
                    operator: value
                }
            elif operator == "==":
                traditional_conditions[field] = value
            elif operator in ["in", "not_in"]:
                traditional_conditions[field] = {
                    operator: value
                }
            else:
                # 其他操作符的处理
                traditional_conditions[field] = {
                    operator: value
                }
        
        return traditional_conditions
    
    async def get_field_info(self, field: str) -> Optional[Dict[str, Any]]:
        """
        获取字段信息
        
        Args:
            field: 字段名
            
        Returns:
            Dict: 字段信息
        """
        if field in BASIC_FIELDS_INFO:
            field_info = BASIC_FIELDS_INFO[field]
            
            # 获取统计信息
            stats = await self.db_service.get_field_statistics(field)
            
            # 获取可选值（对于枚举类型字段）
            available_values = None
            if field_info.data_type == "string":
                available_values = await self.db_service.get_available_values(field)
            
            return {
                "name": field_info.name,
                "display_name": field_info.display_name,
                "field_type": field_info.field_type.value,
                "data_type": field_info.data_type,
                "description": field_info.description,
                "unit": field_info.unit,
                "supported_operators": [op.value for op in field_info.supported_operators],
                "statistics": stats,
                "available_values": available_values
            }
        
        return None
    
    async def get_all_supported_fields(self) -> List[Dict[str, Any]]:
        """获取所有支持的字段信息"""
        fields = []
        
        for field_name in BASIC_FIELDS_INFO.keys():
            field_info = await self.get_field_info(field_name)
            if field_info:
                fields.append(field_info)
        
        return fields
    
    async def validate_conditions(self, conditions: List[ScreeningCondition]) -> Dict[str, Any]:
        """
        验证筛选条件
        
        Args:
            conditions: 筛选条件列表
            
        Returns:
            Dict: 验证结果
        """
        validation_result = {
            "valid": True,
            "errors": [],
            "warnings": []
        }
        
        for i, condition in enumerate(conditions):
            field = condition.field
            operator = condition.operator
            value = condition.value
            
            # 检查字段是否支持
            if field not in BASIC_FIELDS_INFO:
                validation_result["errors"].append(
                    f"条件 {i+1}: 不支持的字段 '{field}'"
                )
                validation_result["valid"] = False
                continue
            
            field_info = BASIC_FIELDS_INFO[field]
            
            # 检查操作符是否支持
            if operator not in [op.value for op in field_info.supported_operators]:
                validation_result["errors"].append(
                    f"条件 {i+1}: 字段 '{field}' 不支持操作符 '{operator}'"
                )
                validation_result["valid"] = False
            
            # 检查值的类型和范围
            if field_info.data_type == "number":
                if operator == "between":
                    if not isinstance(value, list) or len(value) != 2:
                        validation_result["errors"].append(
                            f"条件 {i+1}: between操作符需要两个数值"
                        )
                        validation_result["valid"] = False
                    elif not all(isinstance(v, (int, float)) for v in value):
                        validation_result["errors"].append(
                            f"条件 {i+1}: between操作符的值必须是数字"
                        )
                        validation_result["valid"] = False
                elif not isinstance(value, (int, float)):
                    validation_result["errors"].append(
                        f"条件 {i+1}: 数值字段 '{field}' 的值必须是数字"
                    )
                    validation_result["valid"] = False
        
        return validation_result


# 全局服务实例
_enhanced_screening_service: Optional[EnhancedScreeningService] = None


def get_enhanced_screening_service() -> EnhancedScreeningService:
    """获取增强筛选服务实例"""
    global _enhanced_screening_service
    if _enhanced_screening_service is None:
        _enhanced_screening_service = EnhancedScreeningService()
    return _enhanced_screening_service
