"""
模型能力管理服务

提供模型能力评估、验证和推荐功能。
"""

from typing import Tuple, Dict, Optional, List, Any
from app.constants.model_capabilities import (
    ANALYSIS_DEPTH_REQUIREMENTS,
    DEFAULT_MODEL_CAPABILITIES,
    CAPABILITY_DESCRIPTIONS,
    ModelRole,
    ModelFeature
)
from app.core.unified_config import unified_config
import logging

logger = logging.getLogger(__name__)


class ModelCapabilityService:
    """模型能力管理服务"""
    
    def get_model_capability(self, model_name: str) -> int:
        """
        获取模型的能力等级
        
        Args:
            model_name: 模型名称
            
        Returns:
            能力等级 (1-5)
        """
        # 1. 优先从数据库配置读取
        try:
            llm_configs = unified_config.get_llm_configs()
            for config in llm_configs:
                if config.model_name == model_name:
                    return getattr(config, 'capability_level', 2)
        except Exception as e:
            logger.warning(f"从配置读取模型能力失败: {e}")
        
        # 2. 从默认映射表读取
        if model_name in DEFAULT_MODEL_CAPABILITIES:
            return DEFAULT_MODEL_CAPABILITIES[model_name]["capability_level"]
        
        # 3. 默认返回标准等级
        logger.warning(f"未找到模型 {model_name} 的能力等级，使用默认值2")
        return 2
    
    def get_model_config(self, model_name: str) -> Dict[str, Any]:
        """
        获取模型的完整配置信息
        
        Args:
            model_name: 模型名称
            
        Returns:
            模型配置字典
        """
        # 1. 优先从数据库配置读取
        try:
            llm_configs = unified_config.get_llm_configs()
            for config in llm_configs:
                if config.model_name == model_name:
                    return {
                        "model_name": config.model_name,
                        "capability_level": getattr(config, 'capability_level', 2),
                        "suitable_roles": getattr(config, 'suitable_roles', [ModelRole.BOTH]),
                        "features": getattr(config, 'features', []),
                        "recommended_depths": getattr(config, 'recommended_depths', ["快速", "基础", "标准"]),
                        "performance_metrics": getattr(config, 'performance_metrics', None)
                    }
        except Exception as e:
            logger.warning(f"从配置读取模型信息失败: {e}")
        
        # 2. 从默认映射表读取
        if model_name in DEFAULT_MODEL_CAPABILITIES:
            return DEFAULT_MODEL_CAPABILITIES[model_name]
        
        # 3. 返回默认配置
        logger.warning(f"未找到模型 {model_name} 的配置，使用默认配置")
        return {
            "model_name": model_name,
            "capability_level": 2,
            "suitable_roles": [ModelRole.BOTH],
            "features": [ModelFeature.TOOL_CALLING],
            "recommended_depths": ["快速", "基础", "标准"],
            "performance_metrics": {"speed": 3, "cost": 3, "quality": 3}
        }
    
    def validate_model_pair(
        self,
        quick_model: str,
        deep_model: str,
        research_depth: str
    ) -> Dict[str, Any]:
        """
        验证模型对是否适合当前分析深度
        
        Args:
            quick_model: 快速分析模型名称
            deep_model: 深度分析模型名称
            research_depth: 研究深度（快速/基础/标准/深度/全面）
            
        Returns:
            验证结果字典，包含 valid, warnings, recommendations
        """
        requirements = ANALYSIS_DEPTH_REQUIREMENTS.get(research_depth, ANALYSIS_DEPTH_REQUIREMENTS["标准"])
        
        quick_config = self.get_model_config(quick_model)
        deep_config = self.get_model_config(deep_model)
        
        result = {
            "valid": True,
            "warnings": [],
            "recommendations": []
        }
        
        # 检查快速模型
        quick_level = quick_config["capability_level"]
        if quick_level < requirements["quick_model_min"]:
            result["warnings"].append(
                f"⚠️ 快速模型 {quick_model} (能力等级{quick_level}) "
                f"低于 {research_depth} 分析的建议等级({requirements['quick_model_min']})"
            )
        
        # 检查快速模型角色适配
        quick_roles = quick_config.get("suitable_roles", [])
        if ModelRole.QUICK_ANALYSIS not in quick_roles and ModelRole.BOTH not in quick_roles:
            result["warnings"].append(
                f"💡 模型 {quick_model} 不是为快速分析优化的，可能影响数据收集效率"
            )
        
        # 检查快速模型是否支持工具调用
        quick_features = quick_config.get("features", [])
        if ModelFeature.TOOL_CALLING not in quick_features:
            result["valid"] = False
            result["warnings"].append(
                f"❌ 快速模型 {quick_model} 不支持工具调用，无法完成数据收集任务"
            )
        
        # 检查深度模型
        deep_level = deep_config["capability_level"]
        if deep_level < requirements["deep_model_min"]:
            result["valid"] = False
            result["warnings"].append(
                f"❌ 深度模型 {deep_model} (能力等级{deep_level}) "
                f"不满足 {research_depth} 分析的最低要求(等级{requirements['deep_model_min']})"
            )
            result["recommendations"].append(
                self._recommend_model("deep", requirements["deep_model_min"])
            )
        
        # 检查深度模型角色适配
        deep_roles = deep_config.get("suitable_roles", [])
        if ModelRole.DEEP_ANALYSIS not in deep_roles and ModelRole.BOTH not in deep_roles:
            result["warnings"].append(
                f"💡 模型 {deep_model} 不是为深度推理优化的，可能影响分析质量"
            )
        
        # 检查必需特性
        for feature in requirements["required_features"]:
            if feature == ModelFeature.REASONING:
                deep_features = deep_config.get("features", [])
                if feature not in deep_features:
                    result["warnings"].append(
                        f"💡 {research_depth} 分析建议使用具有强推理能力的深度模型"
                    )
        
        return result
    
    def recommend_models_for_depth(
        self,
        research_depth: str
    ) -> Tuple[str, str]:
        """
        根据分析深度推荐合适的模型对
        
        Args:
            research_depth: 研究深度（快速/基础/标准/深度/全面）
            
        Returns:
            (quick_model, deep_model) 元组
        """
        requirements = ANALYSIS_DEPTH_REQUIREMENTS.get(research_depth, ANALYSIS_DEPTH_REQUIREMENTS["标准"])
        
        # 获取所有启用的模型
        try:
            llm_configs = unified_config.get_llm_configs()
            enabled_models = [c for c in llm_configs if c.enabled]
        except Exception as e:
            logger.error(f"获取模型配置失败: {e}")
            # 使用默认模型
            return self._get_default_models()
        
        if not enabled_models:
            logger.warning("没有启用的模型，使用默认配置")
            return self._get_default_models()
        
        # 筛选适合快速分析的模型
        quick_candidates = []
        for m in enabled_models:
            roles = getattr(m, 'suitable_roles', [ModelRole.BOTH])
            level = getattr(m, 'capability_level', 2)
            features = getattr(m, 'features', [])
            
            if (ModelRole.QUICK_ANALYSIS in roles or ModelRole.BOTH in roles) and \
               level >= requirements["quick_model_min"] and \
               ModelFeature.TOOL_CALLING in features:
                quick_candidates.append(m)
        
        # 筛选适合深度分析的模型
        deep_candidates = []
        for m in enabled_models:
            roles = getattr(m, 'suitable_roles', [ModelRole.BOTH])
            level = getattr(m, 'capability_level', 2)
            
            if (ModelRole.DEEP_ANALYSIS in roles or ModelRole.BOTH in roles) and \
               level >= requirements["deep_model_min"]:
                deep_candidates.append(m)
        
        # 按性价比排序（能力等级 vs 成本）
        quick_candidates.sort(
            key=lambda x: (
                getattr(x, 'capability_level', 2),
                -getattr(x, 'performance_metrics', {}).get("cost", 3) if getattr(x, 'performance_metrics', None) else 0
            ),
            reverse=True
        )
        
        deep_candidates.sort(
            key=lambda x: (
                getattr(x, 'capability_level', 2),
                getattr(x, 'performance_metrics', {}).get("quality", 3) if getattr(x, 'performance_metrics', None) else 0
            ),
            reverse=True
        )
        
        # 选择最佳模型
        quick_model = quick_candidates[0].model_name if quick_candidates else None
        deep_model = deep_candidates[0].model_name if deep_candidates else None
        
        # 如果没找到合适的，使用系统默认
        if not quick_model or not deep_model:
            return self._get_default_models()
        
        logger.info(
            f"🤖 为 {research_depth} 分析推荐模型: "
            f"quick={quick_model} (角色:快速分析), "
            f"deep={deep_model} (角色:深度推理)"
        )
        
        return quick_model, deep_model
    
    def _get_default_models(self) -> Tuple[str, str]:
        """获取默认模型对"""
        try:
            quick_model = unified_config.get_quick_analysis_model()
            deep_model = unified_config.get_deep_analysis_model()
            logger.info(f"使用系统默认模型: quick={quick_model}, deep={deep_model}")
            return quick_model, deep_model
        except Exception as e:
            logger.error(f"获取默认模型失败: {e}")
            return "qwen-turbo", "qwen-plus"
    
    def _recommend_model(self, model_type: str, min_level: int) -> str:
        """推荐满足要求的模型"""
        try:
            llm_configs = unified_config.get_llm_configs()
            for config in llm_configs:
                if config.enabled and getattr(config, 'capability_level', 2) >= min_level:
                    display_name = config.model_display_name or config.model_name
                    return f"建议使用: {display_name}"
        except Exception as e:
            logger.warning(f"推荐模型失败: {e}")
        
        return "建议升级模型配置"


# 单例
_model_capability_service = None


def get_model_capability_service() -> ModelCapabilityService:
    """获取模型能力服务单例"""
    global _model_capability_service
    if _model_capability_service is None:
        _model_capability_service = ModelCapabilityService()
    return _model_capability_service

